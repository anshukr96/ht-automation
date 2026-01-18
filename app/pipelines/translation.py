import json
import os
from typing import Any, Dict, List

from app.core.models import AnalysisResult
from app.services.claude import generate_translation
from app.services.free_media import generate_tts_audio
from app.utils.logging import get_logger, log_event
from app.utils.voice import get_anchor_gender, select_voice

LOGGER = get_logger("pipelines.translation")


async def run_translation_pipeline(
    job_id: str,
    analysis: AnalysisResult,
    article_text: str,
    output_dir: str,
    style_guide: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    translation, meta = await generate_translation(analysis, article_text, style_guide)

    translation_path = os.path.join(output_dir, f"{job_id}_hindi.txt")
    with open(translation_path, "w", encoding="utf-8") as handle:
        handle.write(translation.hindi_text)
    artifacts.append({"type": "translation", "path": translation_path, "metadata": meta})

    try:
        audio_path = os.path.join(output_dir, f"{job_id}_hindi_voiceover.mp3")
        if translation.notes and "placeholder" in translation.notes.lower():
            raise RuntimeError("Hindi translation unavailable")
        anchor_gender = get_anchor_gender(os.getenv("HT_AVATAR_PATH"))
        voice = select_voice("hi", anchor_gender)
        audio_path, audio_meta = generate_tts_audio(translation.hindi_text, audio_path, voice=voice)
        artifacts.append({"type": "translation_audio", "path": audio_path, "metadata": audio_meta})
    except Exception as exc:
        log_event(LOGGER, "translation_tts_failed", job_id=job_id, error=str(exc))
        artifacts.append({"type": "translation_audio", "path": translation_path, "metadata": {"error": str(exc)}})

    notes_path = os.path.join(output_dir, f"{job_id}_translation_notes.json")
    with open(notes_path, "w", encoding="utf-8") as handle:
        json.dump({"notes": translation.notes}, handle, ensure_ascii=True, indent=2)
    artifacts.append({"type": "translation_notes", "path": notes_path, "metadata": {}})

    return artifacts
