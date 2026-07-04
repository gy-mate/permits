const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

// Returns a GeoJSON-style array of permit objects intersecting `bbox`.
// `bbox` is [minLon, minLat, maxLon, maxLat].
// When `inEffectOn` (a YYYY-MM-DD string) is null, 
// permits of all dates are returned
export async function fetchPermits(bbox, { inEffectOn = null, signal } = {}) {
  const params = new URLSearchParams({ bbox: bbox.join(',') })

  if (inEffectOn) {
    params.set('in_effect_on', inEffectOn)
  }

  const response = await fetch(`${BASE}/permits?${params}`, { signal })
  if (!response.ok) {
    throw new Error(`permits request failed: ${response.status}`)
  }

  return response.json()
}

// Dataset-wide coverage bounds for the timeline (earliest dates, daily count histogram)
export async function fetchCoverage() {
  const response = await fetch(`${BASE}/permits/coverage`)
  if (!response.ok) {
    throw new Error(`coverage request failed: ${response.status}`)
  }

  return response.json()
}
