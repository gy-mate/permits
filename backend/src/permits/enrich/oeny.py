"""OENY parcel lookup: conscription number -> parcel geometry (WGS84).

The OENY ``bounding-box`` endpoint returns the parcel outline in the Hungarian EOV
projection (EPSG:23700); we reproject it to WGS84 (EPSG:4326) before storing.

Both lookups are memoised per import process with :func:`functools.lru_cache`, since
many permits share a lot number (and so a parcel id) within a single run.
"""

import asyncio
import logging
from functools import lru_cache

import httpx
from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

from permits.enrich.http import retrying

logger = logging.getLogger("permits.enrich.oeny")

API_BASE = "https://www.oeny.hu/hk-api/parcels"
SEARCH_URL = f"{API_BASE}/search"
BBOX_URL = f"{API_BASE}/bounding-box"

EOV_TO_WGS84 = Transformer.from_crs("EPSG:23700", "EPSG:4326", always_xy=True)
WGS84_TO_EOV = Transformer.from_crs("EPSG:4326", "EPSG:23700", always_xy=True)


def buffer_metres(geometry: BaseGeometry, metres: float) -> BaseGeometry:
    """Grow a WGS84 geometry by ``metres``, buffering in EOV projection."""

    geom_eov = shapely_transform(
        lambda x, y, z=None: WGS84_TO_EOV.transform(x, y), geometry
    )
    return shapely_transform(
        lambda x, y, z=None: EOV_TO_WGS84.transform(x, y), geom_eov.buffer(metres)
    )


def select_parcel(results: list[dict], lot_number: str) -> dict | None:
    """Pick the result whose lot number matches exactly, else the first one.

    The search can return several parcels (e.g. a numerator hit and its sub-lots);
    prefer the one whose ``lotNumber`` equals the requested number verbatim.
    """

    for result in results:
        if str(result.get("lotNumber", "")).strip() == lot_number:
            return result

    logger.warning(
        "OENY search for lot %r returned %d result(s) but none matched exactly; "
        "using the first.",
        lot_number,
        len(results),
    )
    return results[0] if results else None


async def run_parcel_search(
    client: httpx.AsyncClient, ksh_code: str, lot_number: str
) -> int | None:
    """Resolve a conscription (lot) number to an OENY parcel id."""

    logger.info("OENY parcel search: kshCode=%s lotNumber=%s", ksh_code, lot_number)

    async for attempt in retrying():
        with attempt:
            response = await client.get(
                SEARCH_URL,
                params={"kshCode": ksh_code, "lotNumber": lot_number},
                headers={"Accept": "application/json, text/plain, */*"},
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                logger.info("OENY: no parcel for lot %s", lot_number)
                return None

            match = select_parcel(results, lot_number)
            parcel_id = match["id"] if match else None

            logger.info("OENY: lot %s -> parcel id %s", lot_number, parcel_id)
            return parcel_id

    return None


@lru_cache(maxsize=4096)
def parcel_search_task(
    client: httpx.AsyncClient, ksh_code: str, lot_number: str
) -> asyncio.Task:
    """Memoised shared task per (client, ksh_code, lot_number).

    The same lot is looked up once per import however many permits reference it; the
    client is part of the key so a fresh import never reuses a closed loop's task.
    """

    return asyncio.ensure_future(run_parcel_search(client, ksh_code, lot_number))


async def find_parcel_id(
    client: httpx.AsyncClient, ksh_code: str, lot_number: str
) -> int | None:
    """Resolve (or replay from cache) a conscription number to an OENY parcel id."""

    return await parcel_search_task(client, ksh_code, lot_number)


async def run_parcel_geometry(
    client: httpx.AsyncClient, parcel_id: int
) -> BaseGeometry | None:
    """Fetch a parcel's outline and return a WGS84 shapely geometry (or ``None``)."""

    logger.info("OENY parcel geometry: id=%s", parcel_id)

    async for attempt in retrying():
        with attempt:
            response = await client.get(
                BBOX_URL,
                params={"id": parcel_id},
                headers={"Accept": "application/json, text/plain, */*"},
            )
            response.raise_for_status()
            data = response.json()
            
            outline = data.get("outline")
            if not outline:
                return None

            geom_eov = shape(outline)
            return shapely_transform(
                lambda x, y, z=None: EOV_TO_WGS84.transform(x, y),
                geom_eov,
            )

    return None


@lru_cache(maxsize=4096)
def parcel_geometry_task(client: httpx.AsyncClient, parcel_id: int) -> asyncio.Task:
    """Memoised shared task per (client, parcel_id); see :func:`parcel_search_task`."""

    return asyncio.ensure_future(run_parcel_geometry(client, parcel_id))


async def parcel_geometry(
    client: httpx.AsyncClient, parcel_id: int
) -> BaseGeometry | None:
    """Fetch (or replay from cache) a parcel's outline as a WGS84 shapely geometry."""

    return await parcel_geometry_task(client, parcel_id)
