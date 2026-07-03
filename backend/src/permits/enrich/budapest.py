"""Fetching the raw permit rows from budapest.hu."""

import httpx

from permits.enrich.http import retrying

PAGE_URL = (
    "https://einfoszab.budapest.hu/publicSpaceUsing"
    "?key=kozterulet-hasznalati-hatarozatok"
)
DATATABLE_URL = "https://einfoszab.budapest.hu/PublicSpaceUsing/GetDataTable"

# DataTables column order expected by the endpoint
COLUMNS = [
    "regNum",
    "anonymizedRequester",
    "place",
    "parcelNum",
    "size",
    "purposeOfUse",
    "startOfUse",
    "endOfUse",
]


def form_payload(length: int) -> dict[str, str]:
    """Build the DataTables form payload requesting up to ``length`` rows."""

    data: dict[str, str] = {"draw": "1", "start": "0", "length": str(length)}
    for i, name in enumerate(COLUMNS):
        data[f"columns[{i}][data]"] = name
        data[f"columns[{i}][name]"] = ""
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"

    data["order[0][column]"] = "0"
    data["order[0][dir]"] = "asc"
    data["order[0][name]"] = ""
    data["search[value]"] = ""
    data["search[regex]"] = "false"

    return data


async def fetch_rows(client: httpx.AsyncClient, length: int = 10000) -> list[dict]:
    """Bootstrap a fresh antiforgery cookie, then fetch all permit rows.

    The public page sets the ``.AspNetCore.Antiforgery.*`` cookie on the shared
    client's jar; the subsequent POST reuses it.
    """

    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://einfoszab.budapest.hu",
        "Referer": PAGE_URL,
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    async for attempt in retrying():
        with attempt:
            bootstrap = await client.get(PAGE_URL)  # GET the page so the antiforgery cookie lands in the jar
            bootstrap.raise_for_status()

            response = await client.post(
                DATATABLE_URL,
                data=form_payload(length),
                headers=headers,
            )
            response.raise_for_status()
            
            return response.json().get("data", [])

    return []
