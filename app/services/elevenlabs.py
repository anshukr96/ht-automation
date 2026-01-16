import os
from typing import Any, Dict, Tuple

import httpx

from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.elevenlabs")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")
ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")


class ElevenLabsError(RuntimeError):
    pass


def _headers() -> Dict[str, str]:
    if not ELEVENLABS_API_KEY:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not set")
    return {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}


async def text_to_speech(script: str, voice_id: str | None = None) -> Tuple[bytes, Dict[str, Any]]:
    voice = voice_id or ELEVENLABS_VOICE_ID
    if not voice:
        raise ElevenLabsError("ELEVENLABS_VOICE_ID is not set")

    payload = {
        "text": script,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.7},
    }

    log_event(LOGGER, "elevenlabs_tts", voice_id=voice)

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _request() -> bytes:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice}",
                headers=_headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.content

    audio = await _request()
    metadata = {"provider": "elevenlabs", "voice_id": voice, "cost_usd": 0.0}
    return audio, metadata
