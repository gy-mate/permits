import { USAGE_TYPE_KEYS, USAGE_TYPES } from './usageTypes'

// Order here is the display order
const GROUPS = [
  {
    key: 'advertising',
    en: 'Advertising',
    hu: 'Hirdetés',
    types: [
      'advertising_board',
      'advertising_flag',
      'billboard_standard_8_to_20_sqm',
      'billboard_illuminated_8_to_20_sqm',
      'sandwich_board',
      'flyer_distribution',
    ],
  },
  {
    key: 'commercial',
    en: 'Commercial sales',
    hu: 'Kereskedelem',
    types: [
      'commercial_building_12_to_18_sqm',
      'commercial_building_over_18_sqm',
      'commercial_pavilion_6_to_12_sqm',
      'commercial_pavilion_under_6_sqm',
      'goods_display',
      'goods_display_books',
      'display_case',
      'vending_machine',
      'other_vending_machine',
    ],
  },
  {
    key: 'food',
    en: 'Food & drink sales',
    hu: 'Élelmiszer-árusítás',
    types: [
      'cotton_candy_sales',
      'gelato_sales',
      'ice_cream_sales',
      'packaged_sweets_sales',
      'fruit_and_vegetable_sales',
      'goods_display_vegetables_fruit',
      'holiday_related_sales',
    ],
  },
  {
    key: 'hospitality',
    en: 'Hospitality',
    hu: 'Vendéglátás',
    types: [
      'hospitality_terrace',
      'hospitality_building_12_to_18_sqm',
      'hospitality_building_over_18_sqm',
      'hospitality_pavilion_under_6_sqm',
    ],
  },
  {
    key: 'flowers',
    en: 'Flowers & gifts',
    hu: 'Virág-ajándék',
    types: [
      'flower_box',
      'goods_display_flowers',
      'flower_sales_pavilion_under_6_sqm',
      'flower_sales_pavilion_6_to_12_sqm',
      'flower_sales_building_12_to_18_sqm',
      'flower_sales_building_over_18_sqm',
      'flower_gift_sales_pavilion_under_6_sqm',
      'flower_gift_sales_pavilion_6_to_12_sqm',
      'flower_gift_sales_building_12_to_18_sqm',
      'flower_gift_sales_building_over_18_sqm',
    ],
  },
  {
    key: 'event',
    en: 'Event',
    hu: 'Rendezvény',
    types: [
      'event_area_and_structure',
      'event_area_structure_equipment',
      'event_charitable_activity',
      'event_commercial_activity',
      'event_hospitality_activity',
      'event_related_commercial_activity',
      'event_related_hospitality_activity',
      'film_shooting',
      'street_music',
      'moored_event_boat',
    ],
  },
  {
    key: 'construction',
    en: 'Construction',
    hu: 'Építkezés',
    types: [
      'construction_site',
      'construction_site_concrete_pump',
      'construction_site_crane',
      'construction_scaffolding',
      'construction_protective_roof_without_advertising',
      'canopy_porch_roof_without_advertising',
      'sun_canopy_without_advertising',
      'container',
      'loading_and_moving',
    ],
  },
  {
    key: 'transport',
    en: 'Transport',
    hu: 'Közlekedés',
    types: [
      'pedal_carriage',
      'walking_tricycle',
      'road_train',
      'scooter_bicycle',
      'electric_mini_car',
      'public_passenger_ship_port',
      'public_service_passenger_ship_port',
      'storage_and_maintenance_port',
      'fuel_station',
      'fuel_unit_price_display_device',
    ],
  },
  {
    key: 'clocks',
    en: 'Public clock',
    hu: 'Köztéri óra',
    types: ['public_clock_without_advertising', 'public_clock_with_advertising'],
  },
]

// Fold every otherwise-unlisted usage type into a trailing "Other" group
const assigned = new Set(GROUPS.flatMap((group) => group.types))
const leftover = USAGE_TYPE_KEYS.filter((key) => !assigned.has(key))

const RAW_CATEGORIES = [
  ...GROUPS.map((group) => ({
    ...group,
    types: group.types.filter((key) => key in USAGE_TYPES),
  })),
  { key: 'other', en: 'Other', hu: 'Egyéb', types: leftover },
].filter((group) => group.types.length)

// Colours are derived from the category structure rather than the per-type palette in
// usageTypes.js: each category gets its own hue (spread evenly around the wheel), and
// its subcategories share that hue, differing only slightly in lightness
const CATEGORY_SATURATION = 60
const CATEGORY_LIGHTNESS = 50

function subtypeColor(hue, index, count) {
  // Spread subcategories across a narrow lightness band around the category colour
  const lightness =
    count <= 1 ? CATEGORY_LIGHTNESS : Math.round(38 + (index / (count - 1)) * 26)
  return `hsl(${hue}, ${CATEGORY_SATURATION}%, ${lightness}%)`
}

// usageTypeKey -> colour, derived below. Used by the map and the legend swatches
const TYPE_COLORS = {}

export const USAGE_CATEGORIES = RAW_CATEGORIES.map((category, index) => {
  const hue = Math.round((index / RAW_CATEGORIES.length) * 360)

  category.types.forEach((key, typeIndex) => {
    TYPE_COLORS[key] = subtypeColor(hue, typeIndex, category.types.length)
  })

  return {
    ...category,
    // A category with a single subcategory is shown as a plain category, so its swatch
    // is that subcategory's colour rather than the (unused) neutral category hue
    color:
      category.types.length === 1
        ? TYPE_COLORS[category.types[0]]
        : `hsl(${hue}, ${CATEGORY_SATURATION}%, ${CATEGORY_LIGHTNESS}%)`,
  }
})

export function categoryLabel(category, locale) {
  return locale === 'hu' ? category.hu : category.en
}

// Colour for a usage type, derived from its category, with a fallback
export function usageColor(key) {
  return TYPE_COLORS[key] ?? 'hsl(0, 0%, 60%)'
}
