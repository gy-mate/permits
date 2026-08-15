// Diagonal stripe patterns for map areas covered by more than one permit: one stripe per
// distinct usage colour, with a thin black line between every pair of stripes so that
// neighbouring stripes stay separable even when their colours are identical or similar.

const STRIPE_WIDTH = 12  // Target stripe thickness, measured perpendicular
const SEPARATOR_WIDTH = 0.5  // Black divider drawn on every stripe boundary

// Area fills let the basemap show through. The pattern carries that translucency in the
// stripes themselves rather than on the layer, so that the separators can stay opaque —
// a translucent black picks up whatever it happens to sit on and stops reading as black.
// The plain fills use the same value, so the two kinds of area match
export const FILL_OPACITY = 0.45
const PIXEL_RATIO = 2  // Render at 2× so the diagonals stay crisp on HiDPI screens
const DEGREES = 180 / Math.PI

// MapLibre only tiles a fill pattern seamlessly when both of its dimensions are a power
// of two, so the tile size — not the stripe width — is the fixed quantity here
function tileSize(colorCount) {
  const ideal = colorCount * STRIPE_WIDTH * Math.SQRT2
  return 2 ** Math.min(9, Math.max(4, Math.round(Math.log2(ideal))))
}

// Stripes running the same way as the outline they fill read as a handful of long lines
// rather than as stripes, so the pattern takes whichever diagonal cuts across the shape:
// an outline whose edges mostly run north-easterly (a bearing between 0° and 90°) is
// striped at 315°, everything else at 45°. Web Mercator is conformal, so an edge's
// bearing on the ground is also the angle it is drawn at
export function stripeAngle(geometry) {
  let northEasterly = 0
  let other = 0

  for (const polygon of geometry.coordinates) {
    for (const ring of polygon) {
      const cosLatitude = Math.cos(ring[0][1] / DEGREES)  // Longitudes converge towards the poles; bearings would be skewed without this

      for (let index = 1; index < ring.length; index += 1) {
        const east = (ring[index][0] - ring[index - 1][0]) * cosLatitude
        const north = ring[index][1] - ring[index - 1][1]

        const bearing = (Math.atan2(east, north) * DEGREES + 180) % 180  // A line has no head or tail, so opposite bearings are the same direction

        if (bearing > 0 && bearing < 90) {
          northEasterly += Math.hypot(east, north)
        } else {
          other += Math.hypot(east, north)
        }
      }
    }
  }

  return northEasterly > other ? 315 : 45
}

// Stable image name for a colour combination and direction, so each pattern is generated only once
export function stripePatternId(colors, angle) {
  return `stripes:${angle}:${colors.join('|')}`
}

export function stripePatternImage(colors, angle) {
  const size = tileSize(colors.length)
  // Whole colour cycles per tile: the stripes must divide the tile exactly, otherwise
  // the pattern would visibly jump at the tile seams
  const cycles = Math.max(
    1,
    Math.round(size / (colors.length * STRIPE_WIDTH * Math.SQRT2)),
  )
  const width = size / (cycles * colors.length * Math.SQRT2)

  const canvas = document.createElement('canvas')
  canvas.width = size * PIXEL_RATIO
  canvas.height = size * PIXEL_RATIO

  const context = canvas.getContext('2d')
  context.scale(PIXEL_RATIO, PIXEL_RATIO)

  // Rotating by a quarter turn puts the first axis along the stripes' normal: a point
  // (u, v) here lands on an (x, y) with x ± y = u√2, which repeats every `size` in both
  // x and y — which is what makes the tiling seamless. Turning the other way mirrors the
  // stripes onto the opposite diagonal without disturbing that
  context.rotate(angle === 45 ? Math.PI / 4 : -Math.PI / 4)

  // The tile's far corner sits `size × √2` out along either axis, and which axis needs
  // the reach swaps with the rotation, so both are covered to that distance either way
  const reach = size * Math.SQRT2
  const stripes = Math.ceil(reach / width)
  const from = -reach
  const height = 2 * reach  // Spans the tile's full extent along the stripes

  context.globalAlpha = FILL_OPACITY

  for (let index = -stripes; index <= stripes; index += 1) {
    context.fillStyle = colors[((index % colors.length) + colors.length) % colors.length]
    context.fillRect(index * width, from, width, height)
  }

  // Separators go on last, at full opacity, so each one sits on top of both stripes it
  // divides and hides the seam where their antialiased edges overlap
  context.globalAlpha = 1
  context.fillStyle = '#000'
  for (let index = -stripes; index <= stripes; index += 1) {
    context.fillRect(index * width - SEPARATOR_WIDTH / 2, from, SEPARATOR_WIDTH, height)
  }

  return {
    image: context.getImageData(0, 0, canvas.width, canvas.height),
    pixelRatio: PIXEL_RATIO,
  }
}
