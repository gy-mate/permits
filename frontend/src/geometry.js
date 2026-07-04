import { bbox } from '@turf/bbox'
import { bboxPolygon } from '@turf/bbox-polygon'
import { booleanContains } from '@turf/boolean-contains'
import { center } from '@turf/center'
import { transformScale } from '@turf/transform-scale'

export function bboxCenter(box) {
  return center(bboxPolygon(box)).geometry.coordinates
}

// Approximate on-screen size (px) of a geometry's bbox at the current map view
export function pixelSize(map, [minX, minY, maxX, maxY]) {
  const a = map.project([minX, minY])
  const b = map.project([maxX, maxY])
  return Math.max(Math.abs(b.x - a.x), Math.abs(b.y - a.y))
}

// Expand a [minLon,minLat,maxLon,maxLat] bbox outward by `factor` on each side
export function bufferBbox(box, factor = 1) {
  return bbox(transformScale(bboxPolygon(box), 1 + 2 * factor))
}

// True when `outer` fully contains `inner`
export function bboxContains(outer, inner) {
  return booleanContains(bboxPolygon(outer), bboxPolygon(inner))
}
