"""Public read API and the internal fetch trigger."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import Date, cast, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from permits import backup, fetch
from permits.db import get_session
from permits.models import Permit
from permits.schemas import CoveragePoint, PermitOut, PermitsCoverage

router = APIRouter()


def serialize(permit: Permit) -> PermitOut:
    geometry = mapping(to_shape(permit.location)) if permit.location is not None else None

    return PermitOut(
        id=permit.id,
        queried_at=permit.queried_at,
        city_wikidata_id=permit.city_wikidata_id,
        city_ksh_code=permit.hu.ksh_code,
        reference_number=permit.reference_number,
        client_is_natural_person=permit.client_is_natural_person,
        client=permit.client,
        client_wikidata_id=permit.client_wikidata_id,
        location_source_text=permit.location_source_text,
        location_conscription_number=permit.location_conscription_number,
        location=geometry,
        usage_type=permit.usage_type.value,
        occupied_area_in_square_metres=permit.occupied_area_in_square_metres,
        time_from=permit.time_from,
        time_to=permit.time_to,
    )


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in bbox.split(","))
    except ValueError as exc:
        raise HTTPException(422, "bbox must be 'minLon,minLat,maxLon,maxLat'") from exc

    return min_lon, min_lat, max_lon, max_lat


@router.get("/permits", response_model=list[PermitOut])
async def list_permits(
    bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat (WGS84)"),
    in_effect_on: dt.date | None = Query(
        None, description="Only permits in effect on this day; omit for all dates."
    ),
    usage_type: list[str] | None = Query(None, description="Filter by usage type(s)."),
    client: str | None = Query(None, description="Filter by client (substring)."),
    session: AsyncSession = Depends(get_session),
) -> list[PermitOut]:
    """Return every column of all permits whose geometry intersects ``bbox``."""
    
    min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox)
    envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)

    statement = select(Permit).where(
        Permit.location.isnot(None),
        ST_Intersects(Permit.location, envelope),
    )

    if in_effect_on is not None:
        statement = statement.where(
            Permit.time_from <= in_effect_on,
            Permit.time_to > in_effect_on,
        )

    if usage_type:
        statement = statement.where(Permit.usage_type.in_(usage_type))

    if client:
        statement = statement.where(Permit.client.ilike(f"%{client}%"))

    permits = (await session.scalars(statement)).all()
    return [serialize(p) for p in permits]


@router.get("/permits/coverage", response_model=PermitsCoverage)
async def permits_coverage(session: AsyncSession = Depends(get_session)) -> PermitsCoverage:
    """Dataset bounds plus the daily in-effect-permit count, for the timeline."""

    bounds = (
        await session.execute(
            select(
                func.min(Permit.queried_at),
                func.min(Permit.time_from),
                func.max(Permit.time_to),
            )
        )
    ).one()

    # Sweep line: +1 on the day a permit takes effect, -1 on the day it ends
    # (time_to is exclusive, matching list_permits). The running total over the
    # change days is the count of permits in effect from each day onward.
    starts = select(
        cast(Permit.time_from, Date).label("day"), literal(1).label("delta")
    ).where(Permit.time_from.isnot(None))
    ends = select(
        cast(Permit.time_to, Date).label("day"), literal(-1).label("delta")
    ).where(Permit.time_to.isnot(None))
    events = union_all(starts, ends).subquery()
    daily = (
        select(events.c.day, func.sum(events.c.delta).label("delta"))
        .group_by(events.c.day)
        .subquery()
    )
    running = func.sum(daily.c.delta).over(order_by=daily.c.day)
    points = (
        await session.execute(select(daily.c.day, running).order_by(daily.c.day))
    ).all()

    return PermitsCoverage(
        earliest_queried_at=bounds[0],
        earliest_time_from=bounds[1],
        latest_time_to=bounds[2],
        histogram=[CoveragePoint(date=day, count=count) for day, count in points],
    )


@router.post("/permits/fetch")
async def trigger_fetch() -> dict[str, int]:
    """Run a full import."""

    inserted = await fetch.run()
    return {"inserted": inserted}


@router.post("/permits/backup")
async def trigger_backup() -> dict[str, str]:
    """Dump the whole database, compress it and upload it to S3.

    Returns the ``s3://`` URI of the upload.
    """
    
    location = await backup.run()
    return {"backup": location}
