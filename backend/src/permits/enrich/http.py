"""Shared async HTTP client and the tenacity retry policy for enrichment."""

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)

from permits.config import get_settings

settings = get_settings()

RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


def make_client() -> httpx.AsyncClient:
    """A client carrying the project User-Agent and a shared cookie jar.

    The same client is reused across the whole import so the budapest.hu
    antiforgery cookie obtained during bootstrap is sent with later calls.
    """

    return httpx.AsyncClient(
        headers={"User-Agent": settings.user_agent},
        timeout=httpx.Timeout(120.0),
        follow_redirects=True,
        http2=True,
    )


def retrying() -> AsyncRetrying:
    """An :class:`AsyncRetrying` with increasing waits and a large total budget.

    When the total ``enrich_timeout`` budget is exhausted, the underlying error is
    re-raised, which (inside the fetch transaction) aborts the whole import.
    """
    
    return AsyncRetrying(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_delay(settings.enrich_timeout),
        retry=retry_if_exception_type(RETRYABLE),
        reraise=True,
    )
