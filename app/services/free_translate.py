import os
from typing import Optional

import httpx

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.free_translate")

DEFAULT_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


def _endpoint() -> str:
    return os.getenv("FREE_TRANSLATE_ENDPOINT", DEFAULT_ENDPOINT)


async def translate_text(text: str, source: str = "en", target: str = "hi") -> Optional[str]:
    endpoint = _endpoint()
    if not endpoint:
        return None

    chunks = _chunk_text(text, max_chars=1500)
    translated_chunks: list[str] = []

    for chunk in chunks:
        payload = {"q": chunk, "source": source, "target": target, "format": "text"}

        @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
        async def _request() -> object:
            timeout = httpx.Timeout(20.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                if "translate.googleapis.com" in endpoint:
                    response = await client.get(
                        endpoint,
                        params={
                            "client": "gtx",
                            "sl": source,
                            "tl": target,
                            "dt": "t",
                            "q": chunk,
                        },
                    )
                else:
                    response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                return response.json()

        try:
            log_event(LOGGER, "free_translate_request", endpoint=endpoint)
            data = await _request()
            translated = _parse_translation(data)
            if not translated:
                return None
            translated_chunks.append(translated)
        except Exception as exc:
            log_event(LOGGER, "free_translate_failed", error=str(exc))
            return None

    return "\n\n".join(translated_chunks)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 > max_chars:
            if current:
                chunks.append(current)
                current = ""
        if not current:
            current = paragraph
        else:
            current += "\n" + paragraph
    if current:
        chunks.append(current)
    if not chunks:
        return [text[:max_chars]]
    return chunks


def _parse_translation(data: object) -> Optional[str]:
    if isinstance(data, dict):
        return data.get("translatedText")
    if isinstance(data, list) and data and isinstance(data[0], list):
        try:
            return "".join(segment[0] for segment in data[0] if segment and segment[0])
        except Exception:
            return None
    return None
