"""Geocoding fallback via QLever's OSM-planet SPARQL endpoint.

Used when a permit has neither a conscription number nor one embedded in its
``place`` text. A parsed ``(street, house_number)`` is matched against OSM address
features, preferring those tagged as being in Budapest.
"""

import logging

import httpx
from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry

from permits.enrich.http import retrying

logger = logging.getLogger("permits.enrich.qlever")

QLEVER_URL = "https://qlever.dev/api/osm-planet"

PREFIXES = """
PREFIX osmkey: <https://www.openstreetmap.org/wiki/Key:>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
"""


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_query(street: str, house_number: str) -> str:
    """Address-matching SPARQL, ordering Budapest-tagged matches first."""

    street_l = escape(street)
    num_l = escape(house_number)

    return f"""{PREFIXES}
    SELECT ?geom WHERE {{
      ?osm osmkey:addr:street "{street_l}" .
      ?osm osmkey:addr:housenumber "{num_l}" .
      OPTIONAL {{ ?osm osmkey:addr:city ?city . }}
      ?osm geo:hasGeometry/geo:asWKT ?geom .
    }}
    ORDER BY DESC(BOUND(?city))
    LIMIT 1
    """


def strip_crs(literal: str) -> str:
    """Drop any leading CRS URI from a geo:asWKT literal."""

    if literal.startswith("<"):
        return literal.split("> ", 1)[-1]

    return literal


def bbox_wkt(bbox: tuple[float, float, float, float]) -> str:
    """A closed WKT polygon for a ``(min_lon, min_lat, max_lon, max_lat)`` bbox."""

    min_lon, min_lat, max_lon, max_lat = bbox
    return (
        f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    )


def build_clock_query(bbox: tuple[float, float, float, float]) -> str:
    """SPARQL for an ``amenity=clock`` whose geometry lies within ``bbox``."""

    return f"""{PREFIXES}
    SELECT ?geom WHERE {{
      ?osm osmkey:amenity "clock" .
      ?osm geo:hasGeometry/geo:asWKT ?geom .
      FILTER(geof:sfWithin(?geom, "{bbox_wkt(bbox)}"^^geo:wktLiteral))
    }}
    LIMIT 1
    """


async def query_geometry(client: httpx.AsyncClient, query: str) -> BaseGeometry | None:
    """POST a SPARQL query returning a single ``?geom`` and parse it as WGS84."""

    async for attempt in retrying():
        with attempt:
            response = await client.post(
                QLEVER_URL,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            response.raise_for_status()

            bindings = response.json()["results"]["bindings"]
            if not bindings:
                return None

            return shapely_wkt.loads(strip_crs(bindings[0]["geom"]["value"]))

    return None


async def geocode_address(
    client: httpx.AsyncClient, street: str, house_number: str
) -> BaseGeometry | None:
    """Resolve a parsed address to a WGS84 geometry, or ``None`` when unmatched."""

    logger.info("QLever address geocode: %s %s", street, house_number)
    return await query_geometry(client, build_query(street, house_number))


async def find_clock(
    client: httpx.AsyncClient, bbox: tuple[float, float, float, float]
) -> BaseGeometry | None:
    """Find an OSM ``amenity=clock`` point within ``bbox`` (WGS84), or ``None``."""

    logger.info("QLever clock search within bbox %s", bbox)
    
    geometry = await query_geometry(client, build_clock_query(bbox))
    if geometry is not None:
        logger.info("QLever: clock found at %s", geometry.centroid.coords[0])
    return geometry
