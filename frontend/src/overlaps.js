import { area } from '@turf/area'
import { bbox } from '@turf/bbox'
import { booleanDisjoint } from '@turf/boolean-disjoint'
import { difference } from '@turf/difference'
import { intersect } from '@turf/intersect'

const MIN_OVERLAP_AREA_IN_SQUARE_METRES = 10  // Intersections below this are floating-point slivers between parcels, not real overlaps

function multiPolygon(coordinates) {
  return { type: 'MultiPolygon', coordinates }  // Wrap coordinates into a GeoJSON as turf expects them
}

function polygonFeature(coordinates) {
  return { type: 'Feature', geometry: multiPolygon(coordinates), properties: {} }
}

function pair(a, b) {
  return { type: 'FeatureCollection', features: [polygonFeature(a), polygonFeature(b)] }
}

function coordinatesOf(clipped) {
  if (!clipped) {
    return null
  }

  const { type, coordinates } = clipped.geometry
  return type === 'Polygon' ? [coordinates] : coordinates
}

function boxesOverlap(a, b) {
  return a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3]
}

function squareMetres(coordinates) {
  return area(multiPolygon(coordinates))
}

// Permits are routinely issued for the very same parcel, and those outlines come back
// coordinate-identical. Collapsing them up front leaves the clipping below only distinct
// shapes to cut — on a full Budapest dataset that is two thirds of the polygons gone,
// and it is never asked to clip a 200-vertex outline against an exact copy of itself.
function distinctOutlines(areas) {
  const outlines = new Map()

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

    outlines.set(key, { coordinates, box: bbox(multiPolygon(coordinates)), ids: [id] })
  }

  return [...outlines.values()]
}

// Group the outlines into clusters that could possibly overlap, so the (comparatively
// expensive) clipping only ever runs within a cluster. Connected components of the
// "bounding boxes touch" graph.
function overlapGroups(outlines) {
  const grouped = new Array(outlines.length).fill(false)
  const groups = []

  for (let start = 0; start < outlines.length; start += 1) {
    if (grouped[start]) {
      continue
    }

    grouped[start] = true
    const group = [start]

    for (let cursor = 0; cursor < group.length; cursor += 1) {
      for (let other = 0; other < outlines.length; other += 1) {
        if (!grouped[other] && boxesOverlap(outlines[group[cursor]].box, outlines[other].box)) {
          grouped[other] = true
          group.push(other)
        }
      }
    }

    groups.push(group.map((index) => outlines[index]))
  }

  return groups
}

// Overlay one cluster's outlines into disjoint cells. Each outline is cut against the
// cells accumulated so far: the shared part becomes a cell covered by both, and what is
// left of either side stays covered by just its own permits.
function arrange(outlines) {
  let cells = []

  for (const outline of outlines) {
    const next = []
    let rest = outline.coordinates  // The part no existing cell has claimed yet
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
        next.push({ coordinates: cellOnly, box: bbox(multiPolygon(cellOnly)), ids: cell.ids })
      }

      next.push({
        coordinates: shared,
        box: bbox(multiPolygon(shared)),
        ids: [...cell.ids, ...outline.ids],
      })

      rest = coordinatesOf(difference(pair(rest, cell.coordinates)))

      if (rest) {
        restBox = bbox(multiPolygon(rest))
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
export function splitByCoverage(areas) {
  const cells = []

  for (const group of overlapGroups(distinctOutlines(areas))) {
    if (group.length === 1) {
      cells.push(group[0])
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
