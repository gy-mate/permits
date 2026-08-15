import { bbox } from '@turf/bbox'
import { bboxPolygon } from '@turf/bbox-polygon'
import { booleanContains } from '@turf/boolean-contains'
import { center } from '@turf/center'
import { transformScale } from '@turf/transform-scale'
import type { GeoJSON, Geometry, MultiPolygon, Polygon } from 'geojson'
import type { Map as MapLibreMap } from 'maplibre-gl'

// [minLon, minLat, maxLon, maxLat]. Turf's own BBox also admits the 3D, six-number form,
// which nothing here produces or handles, so the 2D one is the type used throughout
export type Bbox = [number, number, number, number]

export function boundingBox(geojson: GeoJSON): Bbox {
  return bbox(geojson) as Bbox
}

// Only true areas can be cut against each other; every other geometry is drawn as a point
export function isPolygonal(
  geometry: Geometry | null | undefined,
): geometry is Polygon | MultiPolygon {
  return geometry?.type === 'Polygon' || geometry?.type === 'MultiPolygon'
}

export function bboxCenter(box: Bbox): [number, number] {
  return center(bboxPolygon(box)).geometry.coordinates as [number, number]
}

// Approximate on-screen size (px) of a geometry's bbox at the current map view
export function pixelSize(map: MapLibreMap, [minX, minY, maxX, maxY]: Bbox): number {
  const a = map.project([minX, minY])
  const b = map.project([maxX, maxY])
  return Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y))
}

// Expand a [minLon,minLat,maxLon,maxLat] bbox outward by `factor` on each side
export function bufferBbox(box: Bbox, factor = 1): Bbox {
  return boundingBox(transformScale(bboxPolygon(box), 1 + 2 * factor))
}

// True when `outer` fully contains `inner`
export function bboxContains(outer: Bbox, inner: Bbox): boolean {
  return booleanContains(bboxPolygon(outer), bboxPolygon(inner))
}
