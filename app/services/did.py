import asyncio
import os
from typing import Any, Dict, Tuple

import httpx

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.did")

DID_API_KEY = os.getenv("DID_API_KEY", "")
DID_BASE_URL = os.getenv("DID_BASE_URL", "https://api.d-id.com")
DID_SOURCE_URL = os.getenv("DID_SOURCE_URL", "")


class DIDError(RuntimeError):
    pass


def _headers() -> Dict[str, str]:
    if not DID_API_KEY:
        raise DIDError("DID_API_KEY is not set")
    return {"Authorization": f"Basic {DID_API_KEY}", "Content-Type": "application/json"}


async def create_talk(script: str, source_url: str | None = None) -> Tuple[str, Dict[str, Any]]:
    source = source_url or DID_SOURCE_URL
    if not source:
        raise DIDError("DID_SOURCE_URL is not set")

    payload = {
        "script": {"type": "text", "input": script},
        "source_url": source,
        "config": {"fluent": True, "pad_audio": 0.2},
    }

    log_event(LOGGER, "did_create_talk", source_url=source)

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _create() -> Dict[str, Any]:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{DID_BASE_URL}/talks", headers=_headers(), json=payload)
            response.raise_for_status()
            return response.json()

    result = await _create()
    talk_id = result.get("id")
    if not talk_id:
        raise DIDError("D-ID response missing talk id")

    video_url = await _wait_for_talk(talk_id)
    metadata = {
        "provider": "d-id",
        "talk_id": talk_id,
        "cost_usd": 0.0,
    }
    return video_url, metadata


async def _wait_for_talk(talk_id: str) -> str:
    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _fetch() -> Dict[str, Any]:
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{DID_BASE_URL}/talks/{talk_id}", headers=_headers())
            response.raise_for_status()
            return response.json()

    for _ in range(40):
        data = await _fetch()
        status = data.get("status")
        if status == "done":
            result_url = data.get("result_url")
            if not result_url:
                raise DIDError("D-ID talk missing result_url")
            log_event(LOGGER, "did_talk_ready", talk_id=talk_id)
            return result_url
        if status == "error":
            raise DIDError(f"D-ID talk failed: {data}")
        await asyncio.sleep(3)

    raise DIDError("D-ID talk timed out")
