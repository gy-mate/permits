"""Orchestrates an import: fetch raw rows, enrich, insert incrementally.

Each new permit is enriched and committed on its own, immediately, so progress is
never lost: an enrichment lookup that keeps failing past its tenacity budget only
skips that one permit instead of aborting the whole run. Only rows whose parsed
reference number (department, main/sub registration numbers and year) is not already
stored are imported. A *no match* (empty enrichment result) is not a failure — the
corresponding field is simply left ``NULL``.
"""

import asyncio
import datetime as dt
import logging
import re

from geoalchemy2.shape import from_shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from permits.db import SessionLocal
from permits.enrich import budapest, oeny, osm, tz, wikidata
from permits.enrich.client_name import correct_client
from permits.enrich.http import make_client
from permits.enrich.parse import extract_conscription_number, parse_address
from permits.logging_handler import TqdmLoggingHandler
from permits.models import HU, Permit
from permits.usage_types import UsageType, translate_purpose

logger = logging.getLogger("permits.fetch")

CITY_WIKIDATA_ID = wikidata.BUDAPEST_QID
LOCAL_AUTHORITY_ID = "FPH"  # Budapest City Council (FőPolgármesteri Hivatal)
NATURAL_PERSON_MARKER = "Magánszemély"
REFERENCE_NUMBER_PATTERN = re.compile(r"(\d+)-(\d*)/(\d+)/(\d+)")
PROGRESS_BAR_REFRESH_SECONDS = 30
OSM_MATCH_BUFFER_METRES = 5  # If the OSM node lies just outside the land plot


def parse_reference_number(
    raw: str, time_from: dt.datetime
) -> tuple[int, int | None, int, int] | None:
    """Split e.g. '58-2712/4/25' into department, 
    main/sub registration number and full year (2025).

    The main registration number may be absent by accident (e.g. '58-/2/25'), 
    yielding ``None`` for it. The century of the two-digit year 
    is inferred from ``time_from``. Returns ``None`` when 
    ``raw`` does not match the expected format.
    """

    match = REFERENCE_NUMBER_PATTERN.fullmatch(raw)
    if match is None:
        return None

    department, main, sub, year = (int(group) if group else None for group in match.groups())
    if year < 100:
        year += (time_from.year // 100) * 100

    return department, main, sub, year


def reference_key(
    row: dict, timezone: str | None
) -> tuple[str, int, int | None, int, int] | None:
    """The dedup key of a raw row: city + parsed reference number, or ``None``
    when the reference number is missing or unparseable, 
    or when the row has no start date 
    to infer the century from.
    """

    raw = (row.get("regNum") or "").strip()
    time_from = tz.day_start(row.get("startOfUse"), timezone)
    if not raw or time_from is None:
        return None

    parts = parse_reference_number(raw, time_from)
    if parts is None:
        return None

    return (CITY_WIKIDATA_ID, *parts)


def to_int(value: str | None) -> int | None:
    """Parse an integer area, tolerating blanks and stray formatting."""

    if not value:
        return None

    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


async def resolve_location(
    client, ksh_code: str, conscription_number: str | None, place: str | None
) -> BaseGeometry | None:
    """OENY parcel geometry by conscription number, else QLever address geocode."""

    if conscription_number:
        parcel_id = await oeny.find_parcel_id(client, ksh_code, conscription_number)
        if parcel_id is not None:
            geometry = await oeny.parcel_geometry(client, parcel_id)
            if geometry is not None:
                return geometry

    address = parse_address(place)
    if address:
        return await osm.geocode_address(client, *address)

    return None


async def refine_clock_location(
    client, usage_type, geometry: BaseGeometry | None
) -> BaseGeometry | None:
    """For public-clock permits, replace the area with the OSM clock point inside it.

    If the usage type is a public clock and we have a permit area, look up an
    ``amenity=clock`` within that area on OSM (via QLever) and prefer its precise
    coordinates. Falls back to the original geometry when nothing is found.
    """

    if geometry is None or "public_clock" not in usage_type.value:
        return geometry

    area = oeny.buffer_metres(geometry, OSM_MATCH_BUFFER_METRES)
    clock = await osm.find_clock(client, area)
    if clock is not None:
        logger.info("Using OSM clock coordinates for a %s permit.", usage_type.value)
        return clock

    return geometry


OSM_AMENITY_BY_USAGE_TYPE = {
    UsageType.fuel_station: "fuel",
    UsageType.vending_machine: "vending_machine",
}


async def refine_branded_amenity_location(
    client, usage_type, geometry: BaseGeometry | None, client_wikidata_id: str | None
) -> BaseGeometry | None:
    """For branded-amenity permits, snap the area to the single matching OSM node.

    If the usage type maps to an OSM amenity and we have both a permit area and the
    client's Wikidata ID, look up nodes of that amenity within the area whose
    ``brand:wikidata`` or ``operator:wikidata`` equals the client's ID. When exactly one
    matches, use its precise coordinates; otherwise keep the original geometry.
    """

    if geometry is None or client_wikidata_id is None:
        return geometry

    amenity = OSM_AMENITY_BY_USAGE_TYPE.get(usage_type)
    if amenity is None:
        return geometry

    area = oeny.buffer_metres(geometry, OSM_MATCH_BUFFER_METRES)
    node = await osm.find_branded_amenity(client, area, amenity, client_wikidata_id)
    if node is not None:
        logger.info("Using OSM %s coordinates for a %s permit", amenity, usage_type.value)
        return node

    return geometry


async def existing_client_qids(session: AsyncSession) -> dict[str, str]:
    """Map already-resolved ``client`` names to their stored Wikidata QID.

    Lets a recurring client reuse a previously resolved id instead of re-querying
    Wikidata (which enforces a low request rate).
    """

    rows = (
        await session.execute(
            select(Permit.client, Permit.client_wikidata_id).where(
                Permit.client.isnot(None),
                Permit.client_wikidata_id.isnot(None),
            )
        )
    ).all()

    return {client: qid for client, qid in rows}


async def get_or_create_hu(
    session: AsyncSession, city_wikidata_id: str, ksh_code: str, local_authority_id: str
) -> HU:
    """Ensure the local.hu row for this city exists, returning it."""

    hu = await session.scalar(select(HU).where(HU.city_wikidata_id == city_wikidata_id))
    if hu is None:
        hu = HU(
            city_wikidata_id=city_wikidata_id,
            ksh_code=ksh_code,
            local_authority_id=local_authority_id,
        )
        session.add(hu)
        await session.commit()

    return hu


async def import_permits(session: AsyncSession) -> int:
    """Run a full import within ``session``'s transaction. Returns the inserted rows."""

    queried_at = dt.datetime.now(dt.UTC)

    async with make_client() as client:
        logger.info("Fetching raw permit rows from budapest.hu…")
        rows = await budapest.fetch_rows(client)
        logger.info("Fetched %d raw rows.", len(rows))

        existing = {
            tuple(row)
            for row in await session.execute(
                select(
                    Permit.city_wikidata_id,
                    Permit.department_id,
                    Permit.main_registration_number,
                    Permit.sub_registration_number,
                    Permit.year_number,
                )
            )
        }
        logger.info("Database already holds %d permits.", len(existing))

        logger.info("Resolving city metadata (KSH code, timezone) from Wikidata…")
        ksh_code = await wikidata.ksh_code(client, CITY_WIKIDATA_ID)
        timezone = await wikidata.iana_timezone(client, CITY_WIKIDATA_ID)
        logger.info("City KSH code=%s, timezone=%s.", ksh_code, timezone)
        await get_or_create_hu(session, CITY_WIKIDATA_ID, ksh_code, LOCAL_AUTHORITY_ID)

        # Seed the client→QID cache with names already resolved in the DB, so recurring
        # clients reuse the stored id instead of re-querying Wikidata
        client_qid_cache: dict[str, str | None] = await existing_client_qids(session)
        logger.info("Reusing %d known client Wikidata id(s).", len(client_qid_cache))

        new_rows = []
        for row in rows:
            key = reference_key(row, timezone)

            if key is None:
                raw = (row.get("regNum") or "").strip()
                if raw:
                    logger.warning("Cannot parse reference number %r; skipping row.", raw)
                continue

            if key not in existing:
                new_rows.append(row)
        logger.info("%d of %d rows are new and will be imported.", len(new_rows), len(rows))

        inserted = 0
        progress = tqdm(
            new_rows,
            desc="Importing permits",
            unit="permit",
            mininterval=PROGRESS_BAR_REFRESH_SECONDS,
            maxinterval=PROGRESS_BAR_REFRESH_SECONDS,
        )

        for row in progress:
            reference_number = (row.get("regNum") or "").strip()

            key = reference_key(row, timezone)
            if key in existing:
                continue

            existing.add(key)

            try:
                permit = await build_permit(
                    client, session, row, queried_at, ksh_code, timezone, client_qid_cache
                )
            except Exception:
                logger.exception("Failed to enrich permit %s; skipping.", reference_number)
                continue

            session.add(permit)
            try:
                await session.commit()
            except Exception:
                logger.exception("Failed to insert permit %s; skipping.", reference_number)
                await session.rollback()
                continue
            inserted += 1

    logger.info("Imported %d new permits (of %d fetched).", inserted, len(rows))
    return inserted


async def build_permit(
    client,
    session: AsyncSession,
    row: dict,
    queried_at: dt.datetime,
    ksh_code: str,
    timezone: str | None,
    client_qid_cache: dict[str, str | None],
) -> Permit:
    """Enrich a single raw row into a :class:`Permit` (no DB side effects)."""

    reference_number = (row.get("regNum") or "").strip()
    logger.debug("Enriching permit %s…", reference_number)

    time_from = tz.day_start(row.get("startOfUse"), timezone)
    time_to = tz.day_start(row.get("endOfUse"), timezone)
    if time_from is None or time_to is None:
        raise ValueError(f"Permit {reference_number} has no start or end date.")

    parts = parse_reference_number(reference_number, time_from)
    if parts is None:
        raise ValueError(f"Cannot parse reference number {reference_number!r}.")
    department, main, sub, year = parts

    requester = (row.get("anonymizedRequester") or "").strip()
    is_natural_person = requester == NATURAL_PERSON_MARKER
    client_name = None if is_natural_person else (correct_client(requester) or None)

    client_qid = None
    if client_name:
        if client_name not in client_qid_cache:
            client_qid_cache[client_name] = await wikidata.client_wikidata_id(
                client, client_name, CITY_WIKIDATA_ID
            )
        client_qid = client_qid_cache[client_name]

    place = (row.get("place") or "").strip() or None
    conscription_number = (
        row.get("parcelNum") or ""
    ).strip() or extract_conscription_number(place)

    usage_type = translate_purpose(row.get("purposeOfUse"))

    geometry = await resolve_location(client, ksh_code, conscription_number, place)
    geometry = await refine_clock_location(client, usage_type, geometry)
    geometry = await refine_branded_amenity_location(client, usage_type, geometry, client_qid)

    return Permit(
        queried_at=queried_at,
        city_wikidata_id=CITY_WIKIDATA_ID,
        department_id=department,
        main_registration_number=main,
        sub_registration_number=sub,
        year_number=year,
        client_is_natural_person=is_natural_person,
        client=client_name,
        client_wikidata_id=client_qid,
        location_source_text=place,
        location_conscription_number=conscription_number,
        location=from_shape(geometry, srid=4326) if geometry else None,
        usage_type=usage_type,
        occupied_area_in_square_metres=to_int(row.get("size")),
        time_from=time_from,
        time_to=time_to,
    )


async def run() -> int:
    """Open a session and run the import; each permit commits itself incrementally."""

    async with SessionLocal() as session:
        return await import_permits(session)


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main() -> None:
    handler = TqdmLoggingHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    asyncio.run(run())


if __name__ == "__main__":
    main()
