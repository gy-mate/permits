// Ported from the homepage project's Map.js: loads the self-hosted VersaTiles
// style JSON and resolves the relative sprite/glyph URLs to absolute ones
const STYLES_FOLDER = '/OSM/styles/'

const STYLE_LIGHT = STYLES_FOLDER + 'colorful.json'
const STYLE_DARK = STYLES_FOLDER + 'eclipse.json'

export function prefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export async function loadStyle(dark) {
  const response = await fetch(dark ? STYLE_DARK : STYLE_LIGHT)

  const style = await response.json()
  if (Array.isArray(style.sprite)) {
    style.sprite = style.sprite.map((sprite) => ({
      ...sprite,
      url: new URL(sprite.url, window.location.origin).toString(),
    }))
  } else if (typeof style.sprite === 'string') {
    style.sprite = new URL(style.sprite, window.location.origin).toString()
  }
  
  return style
}
