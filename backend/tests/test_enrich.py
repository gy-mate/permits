"""Unit tests for the pure enrichment helpers (no network)."""

import datetime as dt

from permits.enrich.client_name import (
    correct_client,
    wikidata_search_name,
    wikidata_search_names,
)
from permits.enrich.parse import extract_conscription_number, parse_address
from permits.enrich.tz import day_start
from permits.usage_types import UsageType, translate_purpose


def test_translate_known_and_unknown():
    assert translate_purpose("vendéglátó terasz") is UsageType.hospitality_terrace

    assert translate_purpose("Egyéb") is UsageType.uncategorized
    assert translate_purpose("valami ismeretlen") is UsageType.uncategorized
    assert translate_purpose(None) is UsageType.uncategorized


def test_extract_conscription_number_variants():
    assert extract_conscription_number("13. ker. Lehel tér hrsz. 28222/2") == "28222/2"
    assert extract_conscription_number("... hrsz: 155563") == "155563"
    assert extract_conscription_number("..., 25123/2 hrsz.") == "25123/2"
    assert extract_conscription_number("hrsz. (23800/8)") == "23800/8"

    assert extract_conscription_number("nothing here") is None


def test_parse_address_variants():
    assert parse_address("8. ker. Múzeum körút 10. szám előtti járdán") == (
        "Múzeum körút",
        "10",
    )
    assert parse_address("15. ker. Rákos út 73-75. sz. előtt") == ("Rákos út", "73-75")
    assert parse_address("3. ker. Flórián tér aluljáró falán") is None


def test_correct_client_abbreviations():
    assert correct_client("Valami e.v.") == "Valami e. v."
    assert correct_client("Valami Kft") == "Valami Kft."
    assert correct_client("Valami Kft.") == "Valami Kft."

    assert (
        correct_client("Magyar Posta Zártkörűen Működő Részvénytársaság")
        == "Magyar Posta Zrt."
    )


def test_correct_client_bare_name_becomes_sole_proprietor():
    assert correct_client("Kovács János") == "Kovács János e. v."
    assert correct_client("Dr. Nagy Péter") == "Dr. Nagy Péter e. v."

    assert correct_client("Magyar Telekom Nyrt.") == "Magyar Telekom Nyrt."


def test_wikidata_search_name_strips_division_and_expands_zrt():
    assert (
        wikidata_search_name(
            "BKM Budapesti Közművek Nonprofit Zrt. Hulladékgazdálkodási Divízió"
        )
        == "BKM Budapesti Közművek Nonprofit Zártkörűen Működő Részvénytársaság"
    )

    assert wikidata_search_name("Valami Kft.") == "Valami Kft."


def test_wikidata_search_names_includes_abbreviated_and_expanded():
    assert wikidata_search_names("BKV Zrt. Forgalmi Divízió") == [
        "BKV Zártkörűen Működő Részvénytársaság",
        "BKV Zrt.",
    ]

    assert wikidata_search_names("Valami Kft.") == ["Valami Kft."]


def test_day_start_is_midnight_in_city_timezone():
    result = day_start("2026-05-01", "Europe/Budapest")
    
    assert result == dt.datetime(2026, 5, 1, tzinfo=result.tzinfo)
    assert result.utcoffset() == dt.timedelta(hours=2)
    assert day_start(None, "Europe/Budapest") is None
