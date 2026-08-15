"""The OENY and SPARQL lookups are memoised per client, so repeats cost no request."""

import httpx
import pytest

from permits.config import get_settings
from permits.enrich import oeny, osm, wikidata

PARCEL_SEARCH_BODY = [{"id": 7, "lotNumber": "123"}]
PARCEL_BBOX_BODY = {"outline": {"type": "Point", "coordinates": [650000, 240000]}}
GEOM_BINDINGS = {"results": {"bindings": [{"geom": {"value": "POINT(19 47)"}}]}}
CODE_BINDINGS = {"results": {"bindings": [{"code": {"value": "abcde"}}]}}


@pytest.fixture
def routes():
    """Record every outgoing request and serve canned bodies per endpoint."""

    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)

        if request.url.path.endswith("/search"):
            return httpx.Response(200, json=PARCEL_SEARCH_BODY)
        if request.url.path.endswith("/bounding-box"):
            return httpx.Response(200, json=PARCEL_BBOX_BODY)
        if request.url == get_settings().wikidata_sparql_api_url:
            return httpx.Response(200, json=CODE_BINDINGS)
        return httpx.Response(200, json=GEOM_BINDINGS)

    return recorded, handler


@pytest.fixture
def make_client(routes):
    """Build clients sharing one request log, so counts span every client made."""

    _, handler = routes

    def build() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return build


async def test_parcel_search_is_cached_per_lot(routes, make_client):
    recorded, _ = routes
    client = make_client()

    results = [await oeny.find_parcel_id(client, "budap", "123") for _ in range(3)]

    assert results == [7, 7, 7]
    assert len(recorded) == 1


async def test_parcel_geometry_is_cached_per_id(routes, make_client):
    recorded, _ = routes
    client = make_client()

    first = await oeny.parcel_geometry(client, 7)
    again = await oeny.parcel_geometry(client, 7)

    assert first is again
    assert len(recorded) == 1


async def test_osm_query_is_cached_per_address(routes, make_client):
    recorded, _ = routes
    client = make_client()

    for _ in range(3):
        await osm.geocode_address(client, "Fő utca", "1")
    await osm.geocode_address(client, "Más utca", "2")

    assert len(recorded) == 2


async def test_wikidata_query_is_cached_per_city(routes, make_client):
    recorded, _ = routes
    client = make_client()

    codes = [await wikidata.ksh_code(client, "Q42") for _ in range(3)]

    assert codes == ["abcde", "abcde", "abcde"]
    assert len(recorded) == 1


@pytest.mark.parametrize(
    "lookup",
    [
        lambda client: oeny.find_parcel_id(client, "budap", "456"),
        lambda client: oeny.parcel_geometry(client, 8),
        lambda client: osm.geocode_address(client, "Harmadik utca", "3"),
        lambda client: wikidata.ksh_code(client, "Q43"),
    ],
    ids=["parcel-search", "parcel-geometry", "osm", "wikidata"],
)
async def test_a_fresh_client_does_not_replay_a_closed_loops_task(
    routes, make_client, lookup
):
    """The client is part of the cache key, so each import re-fetches from scratch."""

    recorded, _ = routes

    await lookup(make_client())
    await lookup(make_client())

    assert len(recorded) == 2
