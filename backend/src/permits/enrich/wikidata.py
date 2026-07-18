"""Wikidata SPARQL lookups: client identity (P1448/P1813), KSH code (P939), timezone.

Responses are memoised per import process with :func:`functools.lru_cache` (keyed on
the query text) because Wikidata's public endpoint enforces a low request rate and the
same city metadata / client names recur many times within a single run.
"""

import asyncio
import logging
from functools import lru_cache

import httpx

from permits.config import get_settings
from permits.enrich.client_name import wikidata_search_names
from permits.enrich.http import retrying

logger = logging.getLogger("permits.enrich.wikidata")

BUDAPEST_QID = "Q1781"
BUSINESS_QID = "Q4830453"
DEFAULT_RETRY_AFTER = 60.0  # Fallback when a 429 response omits (or mangles) its Retry-After header

SPARQL_PREFIXES = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def retry_after_seconds(response: httpx.Response) -> float:
    """Seconds to wait per a 429's ``Retry-After`` header.

    Wikidata sends delta-seconds; fall back to :data:`DEFAULT_RETRY_AFTER` if the
    header is missing or not a plain integer.
    """

    value = (response.headers.get("Retry-After") or "").strip()
    return float(value) if value.isdigit() else DEFAULT_RETRY_AFTER


async def run_sparql(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Run a SPARQL query and return the result bindings (no caching).

    Wikidata throttles with HTTP 429; rather than burning the tenacity budget we honour
    the ``Retry-After`` header and wait exactly as long as the endpoint asks. Other
    transient failures (transport errors, 5xx) still retry via :func:`retrying`.
    """

    logger.debug("Wikidata SPARQL query: %s", " ".join(query.split()))

    async for attempt in retrying():
        with attempt:
            while True:
                response = await client.get(
                    get_settings().wikidata_sparql_api_url,
                    params={"query": query, "format": "json"},
                    headers={"Accept": "application/sparql-results+json"},
                )

                if response.status_code == 429:
                    delay = retry_after_seconds(response)
                    logger.warning(
                        "Wikidata throttled us (HTTP 429); waiting %.0fs per Retry-After.",
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                break
            response.raise_for_status()

            bindings = response.json()["results"]["bindings"]
            logger.debug("Wikidata SPARQL returned %d binding(s)", len(bindings))
            return bindings

    return []


@lru_cache(maxsize=4096)
def sparql_task(client: httpx.AsyncClient, query: str) -> asyncio.Task:
    """Memoised shared task per (client, query).

    Awaiting an already-finished task repeatedly returns its cached result, so this
    deduplicates identical queries across the whole import. The client is part of the
    key, so a fresh import (with a fresh client) never reuses a task from a closed loop.
    """

    return asyncio.ensure_future(run_sparql(client, query))


async def sparql(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Run (or replay from cache) a SPARQL query and return the result bindings."""
    return await sparql_task(client, query)


def escape(text: str) -> str:
    """Escape a literal for safe inclusion in a SPARQL string."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


async def client_wikidata_id(
    client: httpx.AsyncClient, name: str, city_wikidata_id: str
) -> str | None:
    """Find the Wikidata entity matching a client's name.

    Matches the official name (P1448), the short name (P1813) or a Hungarian label
    against any of the name variants derived by :func:`wikidata_search_names` — both
    the expanded official form (``Zrt.`` spelt out) and the original abbreviated name,
    since Wikidata stores clients under either. Candidates are restricted to businesses
    — instances (P31) of ``Q4830453`` or any of its subclasses (P279) — located in the
    same country (P17) as ``city_wikidata_id``. Returns the bare QID or ``None``.
    """

    searches = wikidata_search_names(name)
    if not searches:
        return None

    # Lowercased values for the case-insensitive name/short-name comparisons, and
    # original-cased, Hungarian-tagged values for the exact rdfs:label match
    needles = " ".join(f'"{escape(s.lower())}"' for s in searches)
    labels = " ".join(f'"{escape(s)}"@hu' for s in searches)

    query = f"""{SPARQL_PREFIXES}
    SELECT ?item WHERE {{
      ?item wdt:P31/wdt:P279* wd:{BUSINESS_QID}.
      ?item wdt:P17 ?country.
      wd:{city_wikidata_id} wdt:P17 ?country.
      {{
        {{ VALUES ?needle {{ {needles} }} ?item p:P1448/ps:P1448 ?on. FILTER(LCASE(STR(?on)) = ?needle) }}
        UNION
        {{ VALUES ?needle {{ {needles} }} ?item wdt:P1813 ?sn. FILTER(LCASE(STR(?sn)) = ?needle) }}
        UNION
        {{ VALUES ?label {{ {labels} }} ?item rdfs:label ?label. }}
      }}
    }} LIMIT 1
    """

    logger.info("Resolving client on Wikidata: %r (searches: %r)", name, searches)

    bindings = await sparql(client, query)
    if not bindings:
        logger.info("No Wikidata match for client %r", name)
        return None

    qid = bindings[0]["item"]["value"].rsplit("/", 1)[-1]
    logger.info("Client %r -> %s", name, qid)
    return qid


async def ksh_code(client: httpx.AsyncClient, city_wikidata_id: str) -> str | None:
    """KSH settlement code (P939) of a city. Budapest is always ``budap``."""

    if city_wikidata_id == BUDAPEST_QID:
        return "budap"

    query = f"""{SPARQL_PREFIXES}
    SELECT ?code WHERE {{ wd:{city_wikidata_id} wdt:P939 ?code. }} LIMIT 1
    """

    bindings = await sparql(client, query)
    if not bindings:
        return None

    return bindings[0]["code"]["value"]


async def iana_timezone(client: httpx.AsyncClient, city_wikidata_id: str) -> str | None:
    """Resolve an IANA timezone id for a city.

    Budapest is hardcoded; otherwise we try the located-timezone item's IANA id
    (P6237) via the located administrative area. Returns ``None`` on no match.
    """

    if city_wikidata_id == BUDAPEST_QID:
        return "Europe/Budapest"

    query = f"""{SPARQL_PREFIXES}
    SELECT ?iana WHERE {{
      wd:{city_wikidata_id} wdt:P421 ?tz.
      ?tz wdt:P6237 ?iana.
    }} LIMIT 1
    """
    
    bindings = await sparql(client, query)
    if not bindings:
        return None

    return bindings[0]["iana"]["value"]
