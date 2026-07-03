"""The ``usage_type`` enum and the Hungarian -> English translation map.

The members are derived from the distinct ``purposeOfUse`` values returned by the
budapest.hu DataTables endpoint, translated to English ``snake_case``. ``Egyéb`` and
any value not present in the map fall back to ``uncategorized``.

This module is the single source of truth for the enum; the frontend mirrors the
member -> label mapping for its legend and i18n.
"""

import enum

HU_TO_USAGE_TYPE: dict[str, str] = {
    "vendéglátó terasz": "hospitality_terrace",
    "napvédő ponyva reklám nélkül": "sun_canopy_without_advertising",
    "kereskedelmi pavilon ( 6 - 12 m2 )": "commercial_pavilion_6_to_12_sqm",
    "rendezvényterület, építmény, berendezés": "event_area_structure_equipment",
    "üzemanyag-töltőállomás": "fuel_station",
    "kereskedelmi épület   (18 m2 - )": "commercial_building_over_18_sqm",
    "védőtető, előtető reklám nélkül": "canopy_porch_roof_without_advertising",
    "árubemutatás (virág)": "goods_display_flowers",
    "kereskedelmi pavilon ( - 6 m2 )": "commercial_pavilion_under_6_sqm",
    "építési terület": "construction_site",
    "közszolgáltatási személyhajó-kikötő": "public_service_passenger_ship_port",
    "Virágláda": "flower_box",
    "üzemanyag-egységárat jelző berendezés": "fuel_unit_price_display_device",
    "vendéglátó épület (18 m2 - )": "hospitality_building_over_18_sqm",
    "rendezvény (terület és elhelyezett építmény)": "event_area_and_structure",
    "árusító automata": "vending_machine",
    "konténer": "container",
    "rendezvényhez kapcsolódó vendéglátó tevékenység": "event_related_hospitality_activity",
    "gyümölcs, zöldség árusítása": "fruit_and_vegetable_sales",
    "árubemutatás": "goods_display",
    "virág-ajándék árusító épület (12 m2 - 18 m2)": "flower_gift_sales_building_12_to_18_sqm",
    "bringó-hintó": "pedal_carriage",
    "Ünnepekhez kapcsolódó árusítás": "holiday_related_sales",
    "vattacukor árusítása": "cotton_candy_sales",
    "reklámtábla": "advertising_board",
    "virág-ajándék árusító pavilon ( - 6 m2 )": "flower_gift_sales_pavilion_under_6_sqm",
    "építési állványzat": "construction_scaffolding",
    "virágárusító épület (12 m2 - 18 m2)": "flower_sales_building_12_to_18_sqm",
    "rendezvény (vendéglátó tevékenység)": "event_hospitality_activity",
    "sétatricikli": "walking_tricycle",
    "köztéri óra reklámmal": "public_clock_with_advertising",
    "kereskedelmi épület (12 m2 - 18 m2)": "commercial_building_12_to_18_sqm",
    "jégkrém árusítása": "ice_cream_sales",
    "vendéglátó épület (12 m2 - 18 m2)": "hospitality_building_12_to_18_sqm",
    "építési terület (betonpumpa)": "construction_site_concrete_pump",
    "építési terület (daruzás)": "construction_site_crane",
    "Rakodás, költözés": "loading_and_moving",
    "virágárusító épület (18 m2 - )": "flower_sales_building_over_18_sqm",
    "filmforgatás": "film_shooting",
    "fagylaltárusítás": "gelato_sales",
    "utcazenélés": "street_music",
    "árubemutatás (zöldség-gyümölcs)": "goods_display_vegetables_fruit",
    "elektromos miniautó": "electric_mini_car",
    "óriásplakát (normál, 8-20 m2 felülettel)": "billboard_standard_8_to_20_sqm",
    "rendezvényhez kapcsolódó kereskedelmi tevékenység": "event_related_commercial_activity",
    "Megállítótábla": "sandwich_board",
    "Kisvonat": "road_train",
    "virág-ajándék árusító épület (18 m2 - )": "flower_gift_sales_building_over_18_sqm",
    "roller, kerékpár": "scooter_bicycle",
    "virágárusító pavilon ( 6 - 12 m2 )": "flower_sales_pavilion_6_to_12_sqm",
    "közforgalmú személyhajó-kikötő": "public_passenger_ship_port",
    "rendezvény (kereskedelmi tevékenység)": "event_commercial_activity",
    "reklámzászló": "advertising_flag",
    "szórólap": "flyer_distribution",
    "építési védőtető reklám nélkül": "construction_protective_roof_without_advertising",
    "csomagolt édesség árusítása": "packaged_sweets_sales",
    "árubemutatás (könyv)": "goods_display_books",
    "egyéb automata": "other_vending_machine",
    "vitrin": "display_case",
    "virág-ajándék árusító pavilon ( 6 - 12 m2 )": "flower_gift_sales_pavilion_6_to_12_sqm",
    "rendezvény (karitatív tevékenység)": "event_charitable_activity",
    "Köztéri óra reklám nélkül": "public_clock_without_advertising",
    "álló rendezvényhajó": "moored_event_boat",
    "tároló és karbantartó kikötő": "storage_and_maintenance_port",
    "óriásplakát (világított, 8-20 m2 felülettel)": "billboard_illuminated_8_to_20_sqm",
    "virágárusító pavilon ( - 6 m2 )": "flower_sales_pavilion_under_6_sqm",
    "vendéglátó pavilon ( - 6 m2 )": "hospitality_pavilion_under_6_sqm",
}


MEMBERS = sorted(set(HU_TO_USAGE_TYPE.values())) + ["uncategorized"]

UsageType = enum.Enum("UsageType", {m: m for m in MEMBERS}, type=str)


def translate_purpose(purpose: str | None) -> UsageType:
    """Map a Hungarian ``purposeOfUse`` to a :class:`UsageType` member.

    ``Egyéb`` and unknown values become ``uncategorized``.
    """
    
    if not purpose:
        return UsageType.uncategorized

    member = HU_TO_USAGE_TYPE.get(purpose.strip())
    if member is None:
        return UsageType.uncategorized

    return UsageType(member)
