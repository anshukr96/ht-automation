import asyncio
import os
from typing import Any, Dict, Tuple

import httpx

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.ollama")

_OLLAMA_SEMAPHORE: asyncio.Semaphore | None = None

class OllamaError(RuntimeError):
    pass


def _get_semaphore() -> asyncio.Semaphore:
    global _OLLAMA_SEMAPHORE
    if _OLLAMA_SEMAPHORE is None:
        limit = int(os.getenv("OLLAMA_CONCURRENCY", "1"))
        _OLLAMA_SEMAPHORE = asyncio.Semaphore(max(1, limit))
    return _OLLAMA_SEMAPHORE


async def chat(
    prompt: str,
    *,
    system: str,
    max_tokens: int,
    temperature: float = 0.2,
) -> Tuple[str, Dict[str, Any]]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("OLLAMA_MODEL", "")
    if not model:
        raise OllamaError("OLLAMA_MODEL is not set")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError, OllamaError))
    async def _request() -> Tuple[str, Dict[str, Any]]:
        timeout = httpx.Timeout(120.0, connect=10.0)
        async with _get_semaphore():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()

        message = data.get("message", {})
        content = message.get("content")
        if not content:
            raise OllamaError("Empty response from Ollama")

        metadata = {
            "model": model,
            "usage": {
                "prompt_eval_count": data.get("prompt_eval_count"),
                "eval_count": data.get("eval_count"),
            },
            "cost_usd": 0.0,
        }
        return str(content), metadata

    log_event(LOGGER, "ollama_request", model=model)
    text, metadata = await _request()
    log_event(LOGGER, "ollama_response", usage=metadata.get("usage"))
    return text, metadata
