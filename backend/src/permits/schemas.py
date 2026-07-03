"""Pydantic response models for the public read API."""

import datetime as dt

from pydantic import BaseModel


class PermitOut(BaseModel):
    """A permit serialised with all columns; ``location`` as a GeoJSON geometry."""

    id: int
    queried_at: dt.datetime

    city_wikidata_id: str
    city_ksh_code: str

    reference_number: str

    client_is_natural_person: bool
    client: str | None
    client_wikidata_id: str | None

    location_source_text: str | None
    location_conscription_number: str | None
    location: dict | None

    usage_type: str
    occupied_area_in_square_metres: int | None
    
    time_from: dt.datetime | None
    time_to: dt.datetime | None


class CoveragePoint(BaseModel):
    """A change point in the daily count of in-effect permits.

    ``count`` permits are in effect from ``date`` (inclusive) until the next
    point's date; the series is a step function, not one entry per calendar day.
    """

    date: dt.date
    count: int


class PermitsCoverage(BaseModel):
    """Dataset-wide bounds used by the frontend timeline."""

    # Earliest budapest.hu query time — before this, coverage is partial
    earliest_queried_at: dt.datetime | None
    # Earliest in-effect date present in the dataset
    earliest_time_from: dt.datetime | None
    latest_time_to: dt.datetime | None
    # Daily count of in-effect permits, as a step function over change points
    histogram: list[CoveragePoint]
