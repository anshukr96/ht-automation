import os
from typing import Any, Dict, List

import httpx

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.brave_search")

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_BASE_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchError(RuntimeError):
    pass


def _headers() -> Dict[str, str]:
    if not BRAVE_SEARCH_API_KEY:
        raise BraveSearchError("BRAVE_SEARCH_API_KEY is not set")
    return {"Accept": "application/json", "X-Subscription-Token": BRAVE_SEARCH_API_KEY}


async def web_search(query: str, *, count: int = 5) -> List[Dict[str, Any]]:
    log_event(LOGGER, "brave_search", query=query)

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _request() -> Dict[str, Any]:
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                BRAVE_BASE_URL,
                headers=_headers(),
                params={"q": query, "count": count},
            )
            response.raise_for_status()
            return response.json()

    data = await _request()
    results = data.get("web", {}).get("results", [])
    return [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
        }
        for item in results
    ]
