from typing import Optional

import httpx
import trafilatura

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("utils.extract")


async def extract_article_from_url(url: str) -> str:
    log_event(LOGGER, "url_fetch_start", url=url)

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _fetch() -> str:
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    html = await _fetch()
    extracted = _extract_main_text(html)
    if not extracted:
        raise ValueError("Unable to extract article text from URL")
    log_event(LOGGER, "url_fetch_complete", url=url, chars=len(extracted))
    return extracted


def _extract_main_text(html: str) -> Optional[str]:
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not text:
        text = trafilatura.extract(html, include_comments=False, include_tables=True)
    return text
