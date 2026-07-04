const ENTITY_URL = 'https://www.wikidata.org/wiki/Special:EntityData'

const cache = new Map()

// Fetches a client's logo image (Wikidata P154) on demand, 
// returning a Wikimedia Commons image URL or null
export async function fetchWikimediaCommonsLogoUrl(wikidataId) {
  if (!wikidataId) {
    return null
  }

  if (cache.has(wikidataId)) {
    return cache.get(wikidataId)
  }

  let url = null
  try {
    const response = await fetch(`${ENTITY_URL}/${wikidataId}.json`)
    if (response.ok) {
      const data = await response.json()
      const claims = data.entities?.[wikidataId]?.claims

      const filename = claims?.P154?.[0]?.mainsnak?.datavalue?.value
      if (filename) {
        url = commonsThumbnailUrl(filename)
      }
    }
  } catch {
    url = null
  }

  cache.set(wikidataId, url)

  return url
}

function commonsThumbnailUrl(filename) {
  const encoded = encodeURIComponent(filename.replace(/ /g, '_'))
  return `https://commons.wikimedia.org/wiki/Special:FilePath/${encoded}?width=240`
}
