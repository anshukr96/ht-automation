import os
from typing import Any, Dict, List

from app.core.models import AnalysisResult
from app.services.claude import generate_podcast_script
from app.services.elevenlabs import text_to_speech
from app.utils.logging import get_logger, log_event
from app.utils.media import create_audiogram

LOGGER = get_logger("pipelines.audio")


async def run_audio_pipeline(
    job_id: str,
    analysis: AnalysisResult,
    output_dir: str,
    style_guide: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    script, script_meta = await generate_podcast_script(analysis, style_guide)

    script_path = os.path.join(output_dir, f"{job_id}_podcast_script.txt")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    artifacts.append({"type": "audio_script", "path": script_path, "metadata": script_meta})

    audio_bytes, audio_meta = await text_to_speech(script)
    audio_path = os.path.join(output_dir, f"{job_id}_podcast.mp3")
    with open(audio_path, "wb") as handle:
        handle.write(audio_bytes)
    artifacts.append({"type": "audio", "path": audio_path, "metadata": audio_meta})

    audiogram_path = os.path.join(output_dir, f"{job_id}_audiogram.mp4")
    try:
        await create_audiogram(audio_path, audiogram_path)
        artifacts.append({"type": "audiogram", "path": audiogram_path, "metadata": {"source": audio_path}})
    except Exception as exc:
        log_event(LOGGER, "audiogram_failed", job_id=job_id, error=str(exc))
        artifacts.append({"type": "audiogram", "path": audio_path, "metadata": {"error": str(exc)}})

    return artifacts
