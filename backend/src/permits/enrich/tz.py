"""Interpreting the permit's ISO dates as 00:00 in the city's timezone."""

import datetime as dt
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

# Fallback when Wikidata yields no IANA ID (the dataset is Budapest-only today)
DEFAULT_TZ = "Europe/Budapest"


def day_start(date_text: str | None, iana_tz: str | None) -> dt.datetime | None:
    """Parse an ISO date and return 00:00 of that day in the given timezone.

    Returns a timezone-aware datetime, or ``None`` when ``date_text`` is empty.
    """

    if not date_text:
        return None

    parsed = date_parser.isoparse(date_text)
    tz = ZoneInfo(iana_tz or DEFAULT_TZ)
    
    return dt.datetime(parsed.year, parsed.month, parsed.day, tzinfo=tz)
