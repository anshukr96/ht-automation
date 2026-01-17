import os
import subprocess
from typing import Dict, Optional, Tuple

from app.utils.logging import get_logger, log_event
from app.utils.media import ffmpeg_available

LOGGER = get_logger("services.free_media")


def generate_placeholder_video(script: str, output_path: str) -> Tuple[str, Dict[str, str]]:
    if not ffmpeg_available():
        text_path = output_path.replace(".mp4", ".txt")
        with open(text_path, "w", encoding="utf-8") as handle:
            handle.write("Video placeholder. ffmpeg not available.\n")
            handle.write(script)
        return text_path, {"provider": "local_placeholder", "note": "ffmpeg unavailable"}

    safe_text = script.replace("'", "").replace(":", "-")
    font = "/System/Library/Fonts/Supplemental/Arial.ttf"
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x0B1F3A:s=1920x1080:d=60",
        "-vf",
        f"drawtext=fontfile={font}:text='{safe_text[:200]}':fontcolor=white:fontsize=36:x=80:y=H/2",
        "-c:v",
        "libx264",
        "-t",
        "60",
        output_path,
    ]
    log_event(LOGGER, "placeholder_video_start", output_path=output_path)
    subprocess.run(command, check=True, capture_output=True)
    log_event(LOGGER, "placeholder_video_done", output_path=output_path)
    return output_path, {"provider": "local_ffmpeg"}


def generate_tts_audio(text: str, output_path: str) -> Tuple[str, Dict[str, str]]:
    aiff_path = output_path.replace(".mp3", ".aiff")
    command = ["say", "-o", aiff_path, text]
    log_event(LOGGER, "local_tts_start", output_path=aiff_path)
    subprocess.run(command, check=True, capture_output=True)
    log_event(LOGGER, "local_tts_done", output_path=aiff_path)

    if ffmpeg_available():
        command = ["ffmpeg", "-y", "-i", aiff_path, output_path]
        subprocess.run(command, check=True, capture_output=True)
        os.remove(aiff_path)
        return output_path, {"provider": "local_say", "format": "mp3"}

    return aiff_path, {"provider": "local_say", "format": "aiff"}


def has_say() -> bool:
    return subprocess.call(["which", "say"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def resolve_voice() -> Optional[str]:
    return None
