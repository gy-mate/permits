import { reactive } from 'vue'

const ENTITY_URL = 'https://www.wikidata.org/wiki/Special:EntityData'

export const logoUrls = reactive({})  // Wikidata ID → Wikimedia Commons logo URL

const inFlight = new Set()

export function loadLogoUrl(wikidataId) {
  if (!wikidataId || wikidataId in logoUrls || inFlight.has(wikidataId)) {
    return
  }

  inFlight.add(wikidataId)
  fetchWikimediaCommonsLogoUrl(wikidataId).then((url) => {
    logoUrls[wikidataId] = url
    inFlight.delete(wikidataId)
  })
}

async function fetchWikimediaCommonsLogoUrl(wikidataId) {
  try {
    const response = await fetch(`${ENTITY_URL}/${wikidataId}.json`)
    if (response.ok) {
      const data = await response.json()
      const claims = data.entities?.[wikidataId]?.claims

      const filename = claims?.P154?.[0]?.mainsnak?.datavalue?.value
      if (filename) {
        return commonsThumbnailUrl(filename)
      }
    }
  } catch {
    return null
  }

  return null
}

function commonsThumbnailUrl(filename) {
  const encoded = encodeURIComponent(filename.replace(/ /g, '_'))
  return `https://commons.wikimedia.org/wiki/Special:FilePath/${encoded}?width=240`
}
