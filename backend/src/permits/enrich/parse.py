"""Parsing the free-text ``place`` field of a permit.

The ``place`` strings are highly irregular, e.g.::

    "8. ker. Múzeum körút 10. szám előtti járdán"
    "15. ker. Rákos út 73-75. sz. előtt"
    "13. ker. Lehel tér hrsz. 28222/2"
    "18. ker. Ráday Gedeon utca 39. szám előtt - Nefelejcs utca sarkán hrsz: 155563"
    "Budapest XIII/27-28 raszter vonalában, 25123/2 hrsz."
    "3. ker. Flórián tér aluljáró falán"

Many parcel-less rows still embed a conscription number (Hungarian ``hrsz``), which we
prefer to reuse the exact OENY parcel-geometry path over fuzzy geocoding.
"""

import re

# A conscription number embedded as "hrsz" — value may precede or follow the keyword,
# optionally parenthesised, e.g. "hrsz. (23800/8)", "hrsz: 155563", "38017/7 hrsz."
NUMBER = r"\d+(?:/\d+)?"
CONSCRIPTION_AFTER = re.compile(rf"hrsz\.?:?\s*\(?\s*(?P<num>{NUMBER})", re.IGNORECASE)
CONSCRIPTION_BEFORE = re.compile(rf"(?P<num>{NUMBER})\s*hrsz", re.IGNORECASE)

# Street + house number, anchored on the "sz."/"szám" that follows the number.
# Street is everything after an optional "<N>. ker." up to that number
DISTRICT = r"(?:\d+\.\s*ker\.\s*)?"
HOUSE_NUMBER = r"\d+(?:-\d+)?(?:/\d+)?"
ADDRESS = re.compile(
    rf"{DISTRICT}(?P<street>.+?)\s+(?P<num>{HOUSE_NUMBER})\.?\s*sz",
    re.IGNORECASE,
)


def extract_conscription_number(place: str | None) -> str | None:
    """Return an embedded conscription number from ``place``, if present."""

    if not place:
        return None

    match = CONSCRIPTION_AFTER.search(place) or CONSCRIPTION_BEFORE.search(place)
    if not match:
        return None

    return match.group("num")


def parse_address(place: str | None) -> tuple[str, str] | None:
    """Return ``(street, house_number)`` parsed from ``place``, if present."""
    
    if not place:
        return None

    match = ADDRESS.search(place)
    if not match:
        return None

    return match.group("street").strip(), match.group("num").strip()
