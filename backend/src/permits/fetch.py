"""Orchestrates an import: fetch raw rows, enrich, insert incrementally.

Each new permit is enriched and committed on its own, immediately, so progress is
never lost: an enrichment lookup that keeps failing past its tenacity budget only
skips that one permit instead of aborting the whole run. Only rows whose
``reference_number`` is not already stored are imported (the column's unique key is
the dedup boundary). A *no match* (empty enrichment result) is not a failure — the
corresponding field is simply left ``NULL``.
"""

import asyncio
import datetime as dt
import logging

from geoalchemy2.shape import from_shape
from shapely.geometry.base import BaseGeometry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tqdm import tqdm

from permits.db import SessionLocal
from permits.enrich import budapest, oeny, qlever, tz, wikidata
from permits.enrich.client_name import correct_client
from permits.enrich.http import make_client
from permits.enrich.parse import extract_conscription_number, parse_address
from permits.logging_handler import TqdmLoggingHandler
from permits.models import HU, Permit
from permits.usage_types import translate_purpose

logger = logging.getLogger("permits.fetch")

CITY_WIKIDATA_ID = wikidata.BUDAPEST_QID
NATURAL_PERSON_MARKER = "Magánszemély"
PROGRESS_BAR_REFRESH_SECONDS = 30


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

    number = conscription_number or extract_conscription_number(place)
    if number:
        parcel_id = await oeny.find_parcel_id(client, ksh_code, number)
        if parcel_id is not None:
            geometry = await oeny.parcel_geometry(client, parcel_id)
            if geometry is not None:
                return geometry

    address = parse_address(place)
    if address:
        return await qlever.geocode_address(client, *address)

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

    clock = await qlever.find_clock(client, geometry.bounds)
    if clock is not None:
        logger.info("Using OSM clock coordinates for a %s permit.", usage_type.value)
        return clock

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


async def get_or_create_hu(session: AsyncSession, city_wikidata_id: str, ksh_code: str) -> HU:
    """Ensure the local.hu row for this city exists, returning it."""

    hu = await session.get(HU, city_wikidata_id)
    if hu is None:
        hu = HU(city_wikidata_id=city_wikidata_id, ksh_code=ksh_code)
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

        existing = set(
            (await session.scalars(select(Permit.reference_number))).all()
        )
        logger.info("Database already holds %d permits.", len(existing))

        logger.info("Resolving city metadata (KSH code, timezone) from Wikidata…")
        ksh_code = await wikidata.ksh_code(client, CITY_WIKIDATA_ID)
        timezone = await wikidata.iana_timezone(client, CITY_WIKIDATA_ID)
        logger.info("City KSH code=%s, timezone=%s.", ksh_code, timezone)
        await get_or_create_hu(session, CITY_WIKIDATA_ID, ksh_code)

        # Seed the client→QID cache with names already resolved in the DB, so recurring
        # clients reuse the stored id instead of re-querying Wikidata
        client_qid_cache: dict[str, str | None] = await existing_client_qids(session)
        logger.info("Reusing %d known client Wikidata id(s).", len(client_qid_cache))

        new_rows = [
            row
            for row in rows
            if (row.get("regNum") or "").strip()
            and (row.get("regNum") or "").strip() not in existing
        ]
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
            if reference_number in existing:
                continue
            existing.add(reference_number)

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

    conscription_number = (row.get("parcelNum") or "").strip() or None
    place = (row.get("place") or "").strip() or None
    usage_type = translate_purpose(row.get("purposeOfUse"))

    geometry = await resolve_location(client, ksh_code, conscription_number, place)
    geometry = await refine_clock_location(client, usage_type, geometry)

    return Permit(
        queried_at=queried_at,
        city_wikidata_id=CITY_WIKIDATA_ID,
        reference_number=reference_number,
        client_is_natural_person=is_natural_person,
        client=client_name,
        client_wikidata_id=client_qid,
        location_source_text=place,
        location_conscription_number=conscription_number,
        location=from_shape(geometry, srid=4326) if geometry else None,
        usage_type=usage_type,
        occupied_area_in_square_metres=to_int(row.get("size")),
        time_from=tz.day_start(row.get("startOfUse"), timezone),
        time_to=tz.day_start(row.get("endOfUse"), timezone),
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
