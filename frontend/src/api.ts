import type { Geometry } from 'geojson'

import type { Bbox } from './geometry'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// Mirrors PermitOut in backend/src/permits/schemas.py. Datetimes arrive as ISO strings
export interface Permit {
  id: number
  queried_at: string

  city_wikidata_id: string
  city_ksh_code: string

  reference_number: string

  client_is_natural_person: boolean
  client: string | null
  client_wikidata_id: string | null

  location_source_text: string | null
  location_conscription_number: string | null
  location: Geometry | null

  usage_type: string
  occupied_area_in_square_metres: number | null

  time_from: string
  time_to: string
}

// A change point in the daily count of in-effect permits: `count` permits are in effect
// from `date` (inclusive) until the next point's date
export interface CoveragePoint {
  date: string
  count: number
}

// Mirrors PermitsCoverage in backend/src/permits/schemas.py
export interface PermitsCoverage {
  earliest_queried_at: string | null
  earliest_time_from: string | null
  latest_time_to: string | null
  histogram: CoveragePoint[]
}

export interface FetchPermitsOptions {
  inEffectOn?: string | null
  signal?: AbortSignal | null
}

// Returns a GeoJSON-style array of permit objects intersecting `bbox`.
// `bbox` is [minLon, minLat, maxLon, maxLat].
// When `inEffectOn` (a YYYY-MM-DD string) is null,
// permits of all dates are returned
export async function fetchPermits(
  bbox: Bbox,
  { inEffectOn = null, signal = null }: FetchPermitsOptions = {},
): Promise<Permit[]> {
  const params = new URLSearchParams({ bbox: bbox.join(',') })

  if (inEffectOn) {
    params.set('in_effect_on', inEffectOn)
  }

  const response = await fetch(`${BASE}/permits?${params}`, { signal })
  if (!response.ok) {
    throw new Error(`permits request failed: ${response.status}`)
  }

  return response.json() as Promise<Permit[]>
}

// Dataset-wide coverage bounds for the timeline (earliest dates, daily count histogram)
export async function fetchCoverage(): Promise<PermitsCoverage> {
  const response = await fetch(`${BASE}/permits/coverage`)
  if (!response.ok) {
    throw new Error(`coverage request failed: ${response.status}`)
  }

  return response.json() as Promise<PermitsCoverage>
}
