import { area } from '@turf/area'
import { booleanDisjoint } from '@turf/boolean-disjoint'
import { difference } from '@turf/difference'
import { intersect } from '@turf/intersect'
import type { Feature, FeatureCollection, MultiPolygon, Polygon, Position } from 'geojson'

import { boundingBox, type Bbox } from './geometry'

const MIN_OVERLAP_AREA_IN_SQUARE_METRES = 10  // Intersections below this are floating-point slivers between parcels, not real overlaps

// MultiPolygon coordinates: every outline below is held in this shape, so single
// polygons are lifted into it on the way in
type MultiPolygonCoordinates = Position[][][]

// A permit area on the way in: the id it belongs to and the outline it covers
export interface PermitArea {
  id: number
  geometry: Polygon | MultiPolygon
}

// A patch of ground and every permit covering it
interface Patch {
  coordinates: MultiPolygonCoordinates
  box: Bbox
  ids: number[]
}

export interface CoverageCell {
  geometry: MultiPolygon
  ids: number[]
}

function multiPolygon(coordinates: MultiPolygonCoordinates): MultiPolygon {
  return { type: 'MultiPolygon', coordinates }  // Wrap coordinates into a GeoJSON as turf expects them
}

function polygonFeature(coordinates: MultiPolygonCoordinates): Feature<MultiPolygon> {
  return { type: 'Feature', geometry: multiPolygon(coordinates), properties: {} }
}

function pair(
  a: MultiPolygonCoordinates,
  b: MultiPolygonCoordinates,
): FeatureCollection<MultiPolygon> {
  return { type: 'FeatureCollection', features: [polygonFeature(a), polygonFeature(b)] }
}

function coordinatesOf(
  clipped: Feature<Polygon | MultiPolygon> | null,
): MultiPolygonCoordinates | null {
  if (!clipped) {
    return null
  }

  const { type, coordinates } = clipped.geometry
  return type === 'Polygon' ? [coordinates] : coordinates
}

function boxesOverlap(a: Bbox, b: Bbox): boolean {
  return a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3]
}

function squareMetres(coordinates: MultiPolygonCoordinates): number {
  return area(multiPolygon(coordinates))
}

// Permits are routinely issued for the very same parcel, and those outlines come back
// coordinate-identical. Collapsing them up front leaves the clipping below only distinct
// shapes to cut — on a full Budapest dataset that is two thirds of the polygons gone,
// and it is never asked to clip a 200-vertex outline against an exact copy of itself.
function distinctOutlines(areas: PermitArea[]): Patch[] {
  const outlines = new Map<string, Patch>()

  for (const { id, geometry } of areas) {
    const key = JSON.stringify(geometry.coordinates)
    const outline = outlines.get(key)

    if (outline) {
      outline.ids.push(id)
      continue
    }

    // Everything below works in MultiPolygon coordinates, so single polygons are lifted
    const coordinates =
      geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates

    outlines.set(key, {
      coordinates,
      box: boundingBox(multiPolygon(coordinates)),
      ids: [id],
    })
  }

  return [...outlines.values()]
}

// Group the outlines into clusters that could possibly overlap, so the (comparatively
// expensive) clipping only ever runs within a cluster. Connected components of the
// "bounding boxes touch" graph.
function overlapGroups(outlines: Patch[]): Patch[][] {
  const grouped = new Array<boolean>(outlines.length).fill(false)
  const groups: Patch[][] = []

  for (const [start, first] of outlines.entries()) {
    if (grouped[start]) {
      continue
    }

    grouped[start] = true
    const group = [first]

    // The group grows while it is walked; an array iterator re-reads the length on every
    // step, so outlines appended here are visited in turn — that is the breadth-first pass
    for (const outline of group) {
      for (const [other, candidate] of outlines.entries()) {
        if (!grouped[other] && boxesOverlap(outline.box, candidate.box)) {
          grouped[other] = true
          group.push(candidate)
        }
      }
    }

    groups.push(group)
  }

  return groups
}

// Overlay one cluster's outlines into disjoint cells. Each outline is cut against the
// cells accumulated so far: the shared part becomes a cell covered by both, and what is
// left of either side stays covered by just its own permits.
function arrange(outlines: Patch[]): Patch[] {
  let cells: Patch[] = []

  for (const outline of outlines) {
    const next: Patch[] = []
    let rest: MultiPolygonCoordinates | null = outline.coordinates  // The part no existing cell has claimed yet
    let restBox = outline.box

    for (const cell of cells) {
      // Touching bounding boxes are only a first sieve, and clipping is expensive enough
      // that it is worth ruling out the parcels that merely sit close to one another
      // with a test that does not clip at all
      if (
        !rest ||
        !boxesOverlap(cell.box, restBox) ||
        booleanDisjoint(polygonFeature(cell.coordinates), polygonFeature(rest))
      ) {
        next.push(cell)
        continue
      }

      const shared = coordinatesOf(intersect(pair(cell.coordinates, rest)))

      if (!shared || squareMetres(shared) < MIN_OVERLAP_AREA_IN_SQUARE_METRES) {
        next.push(cell)
        continue
      }

      const cellOnly = coordinatesOf(difference(pair(cell.coordinates, rest)))

      if (cellOnly) {
        next.push({
          coordinates: cellOnly,
          box: boundingBox(multiPolygon(cellOnly)),
          ids: cell.ids,
        })
      }

      next.push({
        coordinates: shared,
        box: boundingBox(multiPolygon(shared)),
        ids: [...cell.ids, ...outline.ids],
      })

      rest = coordinatesOf(difference(pair(rest, cell.coordinates)))

      if (rest) {
        restBox = boundingBox(multiPolygon(rest))
      }
    }

    if (rest) {
      next.push({ coordinates: rest, box: restBox, ids: outline.ids })
    }

    cells = next
  }

  return cells
}

// Split possibly overlapping permit areas — `{ id, geometry }` objects — into disjoint
// cells, each tagged with the ids of every permit covering it. A cell with one id is a
// patch nothing else overlaps; a cell with several is an overlap, drawn striped.
//
// The result depends on the permits alone, not on the map view or the active filters,
// so the caller works it out once per fetch and reuses it while panning and zooming.
export function splitByCoverage(areas: PermitArea[]): CoverageCell[] {
  const cells: Patch[] = []

  for (const group of overlapGroups(distinctOutlines(areas))) {
    if (group.length === 1) {
      cells.push(...group)
      continue
    }

    try {
      cells.push(...arrange(group))
    } catch (error) {
      // One malformed geometry must not take the rest of the map down with it: draw
      // this cluster as plain overlapping fills instead
      console.error(error)
      cells.push(...group)
    }
  }

  return cells.map(({ coordinates, ids }) => ({ geometry: multiPolygon(coordinates), ids }))
}
