import { reactive } from 'vue'

const ENTITY_URL = 'https://www.wikidata.org/wiki/Special:EntityData'

// Only the sliver of Wikidata's entity JSON this reads: the logo image (P154) claim,
// whose datavalue is a Commons filename
interface EntityData {
  entities?: Record<
    string,
    {
      claims?: Record<string, { mainsnak?: { datavalue?: { value?: string } } }[]>
    }
  >
}

export const logoUrls = reactive<Record<string, string | null>>({})  // Wikidata ID → Wikimedia Commons logo URL

const inFlight = new Set<string>()

export function loadLogoUrl(wikidataId: string | null | undefined): void {
  if (!wikidataId || wikidataId in logoUrls || inFlight.has(wikidataId)) {
    return
  }

  inFlight.add(wikidataId)
  fetchWikimediaCommonsLogoUrl(wikidataId).then((url) => {
    logoUrls[wikidataId] = url
    inFlight.delete(wikidataId)
  })
}

async function fetchWikimediaCommonsLogoUrl(wikidataId: string): Promise<string | null> {
  try {
    const response = await fetch(`${ENTITY_URL}/${wikidataId}.json`)
    if (response.ok) {
      const data = (await response.json()) as EntityData
      const claims = data.entities?.[wikidataId]?.claims

      const filename = claims?.['P154']?.[0]?.mainsnak?.datavalue?.value
      if (filename) {
        return commonsThumbnailUrl(filename)
      }
    }
  } catch {
    return null
  }

  return null
}

function commonsThumbnailUrl(filename: string): string {
  const encoded = encodeURIComponent(filename.replace(/ /g, '_'))
  return `https://commons.wikimedia.org/wiki/Special:FilePath/${encoded}?width=240`
}
