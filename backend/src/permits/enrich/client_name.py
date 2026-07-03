"""Normalising the free-text ``client`` (requester) field and deriving the
strings to search for on Wikidata.

Two concerns are kept separate:

* :func:`correct_client` produces the *stored* client name — tidied spelling and
  abbreviations (``e.v.`` → ``e. v.``, ``Kft`` → ``Kft.``), the long
  ``Zártkörűen Működő Részvénytársaság`` shortened to ``Zrt.``, and a bare personal
  name turned into a sole-proprietor (``… e. v.``).
* :func:`wikidata_search_name` produces the *query* string — the company name up to
  and including its legal form (dropping any trailing organisational division), with
  ``Zrt.`` expanded back to its long form so it matches Wikidata's official names.
"""

import re

ZRT_LONG = "Zártkörűen Működő Részvénytársaság"

# Hungarian legal-form abbreviations, longest first so e.g. "Nyrt." wins over "Rt.".
# A company name is considered to *end* at the last of these tokens; anything after
# it (a divízió / department) is dropped before searching Wikidata
LEGAL_FORMS = ["Nyrt.", "Zrt.", "Kft.", "Kkt.", "Kht.", "Bt.", "Rt.", "e. v."]

# A bare personal name: 2–4 capitalised words (allowing an initial "Dr." etc.)
NAME_WORD = r"[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]+\.?"
PERSON_NAME = re.compile(rf"^(?:{NAME_WORD}\s+){{1,3}}{NAME_WORD}$")

WHITESPACE = re.compile(r"\s+")
SOLE_PROPRIETOR = re.compile(r"\be\.\s*v\.?", re.IGNORECASE)
LTD = re.compile(r"\bKft\b\.?")
PLC_LONG = re.compile(ZRT_LONG, re.IGNORECASE)


def correct_client(name: str) -> str:
    """Tidy a raw requester string into the canonical stored ``client`` name."""

    name = WHITESPACE.sub(" ", name.strip())

    name = SOLE_PROPRIETOR.sub("e. v.", name)
    name = LTD.sub("Kft.", name)
    name = PLC_LONG.sub("Zrt.", name)

    # A bare personal name with no legal form is a sole proprietor
    if not has_legal_form(name) and PERSON_NAME.match(name):
        name = f"{name} e. v."

    return name


def has_legal_form(name: str) -> bool:
    return any(form in name for form in LEGAL_FORMS)


def strip_division(name: str) -> str:
    """Truncate ``name`` right after its last legal-form token.

    ``"BKM … Nonprofit Zrt. Hulladékgazdálkodási Divízió"`` → ``"BKM … Nonprofit Zrt."``
    Names without a legal form are returned unchanged.
    """

    best_end: int | None = None
    for form in LEGAL_FORMS:
        for match in re.finditer(re.escape(form), name):
            if best_end is None or match.end() > best_end:
                best_end = match.end()

    return name[:best_end].strip() if best_end is not None else name


def wikidata_search_name(name: str) -> str:
    """Derive the Wikidata query string from a (corrected) client name.

    Drops a trailing organisational division and expands the ``Zrt.`` abbreviation
    back to ``Zártkörűen Működő Részvénytársaság`` (Wikidata's official-name form).
    """

    search = strip_division(name)
    search = re.sub(r"\bZrt\.", ZRT_LONG, search)

    return WHITESPACE.sub(" ", search).strip()


def wikidata_search_names(name: str) -> list[str]:
    """All name variants to look a client up by on Wikidata.

    Both have the trailing organisational division dropped, but Wikidata stores some
    clients under the long legal form (``… Zártkörűen Működő Részvénytársaság``) and
    others under the abbreviation (``BKV Zrt.``), so we query for both: the expanded
    official form from :func:`wikidata_search_name` and the original abbreviated name.
    Deduplicated, order-preserving (expanded first).
    """

    original = WHITESPACE.sub(" ", strip_division(name)).strip()
    names: list[str] = []

    for candidate in (wikidata_search_name(name), original):
        if candidate and candidate not in names:
            names.append(candidate)
            
    return names
