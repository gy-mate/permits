"""Geocoding fallback via QLever's OSM-planet SPARQL endpoint.

Used when a permit has neither a conscription number nor one embedded in its
``place`` text. A parsed ``(street, house_number)`` is matched against OSM address
features, preferring those tagged as being in Budapest.
"""

import logging

import httpx
from shapely import wkt as shapely_wkt
from shapely.geometry.base import BaseGeometry

from permits.config import get_settings
from permits.enrich.http import retrying

logger = logging.getLogger("permits.enrich.osm")

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


def build_clock_query(area: BaseGeometry) -> str:
    """SPARQL for ``amenity=clock`` nodes whose geometry lies within ``area``.

    ``LIMIT 2`` is enough for the caller to tell "exactly one" from "several".
    """

    return f"""{PREFIXES}
    SELECT ?geom WHERE {{
      VALUES ?area {{ "{area.wkt}"^^geo:wktLiteral }}
      ?osm osmkey:amenity "clock" .
      ?osm geo:hasGeometry/geo:asWKT ?geom .
      FILTER(geof:sfContains(?area, ?geom))
    }}
    LIMIT 2
    """


def build_branded_amenity_query(
    area: BaseGeometry, amenity: str, wikidata_id: str
) -> str:
    """SPARQL for ``amenity`` nodes within ``area`` whose brand or operator matches.

    A node qualifies when its ``brand:wikidata`` or ``operator:wikidata`` tag equals
    ``wikidata_id``. The two tags form a UNION; each branch repeats the amenity and
    spatial constraints, since SPARQL needs both operands of ``geof:sfContains`` bound
    within the same branch.

    ``LIMIT 2`` is enough to tell "exactly one" from "several".
    """

    qid = escape(wikidata_id)
    match = (
        f'VALUES ?area {{ "{area.wkt}"^^geo:wktLiteral }} '
        f'?osm osmkey:amenity "{escape(amenity)}" . '
        '?osm geo:hasGeometry/geo:asWKT ?geom . '
        'FILTER(geof:sfContains(?area, ?geom))'
    )

    return f"""{PREFIXES}
    SELECT DISTINCT ?osm ?geom WHERE {{
      {{ ?osm osmkey:brand:wikidata "{qid}" . {match} }}
      UNION
      {{ ?osm osmkey:operator:wikidata "{qid}" . {match} }}
    }}
    LIMIT 2
    """


async def query_geometries(
    client: httpx.AsyncClient, query: str
) -> list[BaseGeometry]:
    """POST a SPARQL query and parse every ``?geom`` binding as a WGS84 geometry."""

    async for attempt in retrying():
        with attempt:
            response = await client.post(
                get_settings().osm_sparql_api_url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
            )
            if response.is_server_error:
                logger.warning(
                    "OSM SPARQL request failed with HTTP %d; query: %s",
                    response.status_code,
                    " ".join(query.split()),
                )
            response.raise_for_status()

            bindings = response.json()["results"]["bindings"]
            return [
                shapely_wkt.loads(strip_crs(binding["geom"]["value"]))
                for binding in bindings
            ]

    return []


async def query_geometry(client: httpx.AsyncClient, query: str) -> BaseGeometry | None:
    """POST a SPARQL query returning a single ``?geom`` and parse it as WGS84."""

    geometries = await query_geometries(client, query)
    return geometries[0] if geometries else None


async def single_geometry(
    client: httpx.AsyncClient, query: str
) -> BaseGeometry | None:
    """Parse a query's geometries, returning it only when exactly one is found.
    An ambiguous (multiple) or empty result yields ``None``.
    """

    geometries = await query_geometries(client, query)
    return geometries[0] if len(geometries) == 1 else None


async def geocode_address(
    client: httpx.AsyncClient, street: str, house_number: str
) -> BaseGeometry | None:
    """Resolve a parsed address to a WGS84 geometry, or ``None`` when unmatched."""

    logger.info("QLever address geocode: %s %s", street, house_number)
    return await query_geometry(client, build_query(street, house_number))


async def find_clock(
    client: httpx.AsyncClient, area: BaseGeometry
) -> BaseGeometry | None:
    """Find the single OSM ``amenity=clock`` within ``area`` (WGS84).
    Returns the point only when exactly one clock lies within ``area``.
    """

    logger.info("QLever clock search within area with bounds %s", area.bounds)
    geometry = await single_geometry(client, build_clock_query(area))

    if geometry is not None:
        logger.info("QLever: clock found at %s", geometry.centroid.coords[0])
    return geometry


async def find_branded_amenity(
    client: httpx.AsyncClient,
    area: BaseGeometry,
    amenity: str,
    wikidata_id: str,
) -> BaseGeometry | None:
    """Find the sole ``amenity`` node in ``area`` matching ``wikidata_id``.
    Returns the geometry only when exactly one OSM node of that amenity within ``area``
    carries a matching ``brand:wikidata`` or ``operator:wikidata``.
    """

    logger.info(
        "QLever %s search for %s within area with bounds %s",
        amenity,
        wikidata_id,
        area.bounds,
    )
    geometry = await single_geometry(
        client, build_branded_amenity_query(area, amenity, wikidata_id)
    )

    if geometry is not None:
        logger.info("QLever: %s found at %s", amenity, geometry.centroid.coords[0])
    return geometry
