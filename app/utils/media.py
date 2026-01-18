import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.utils.logging import get_logger, log_event
from PIL import Image

LOGGER = get_logger("utils.media")


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def create_audiogram(audio_path: str, output_path: str) -> None:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is not available")

    command = [
        "ffmpeg",
        "-y",
        "-i",
        audio_path,
        "-filter_complex",
        "[0:a]showwaves=s=1080x1080:mode=line:rate=25,format=yuv420p[v]",
        "-map",
        "[v]",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]

    log_event(LOGGER, "ffmpeg_audiogram_start", output_path=output_path)
    await asyncio.to_thread(_run_command, command)
    log_event(LOGGER, "ffmpeg_audiogram_done", output_path=output_path)


async def overlay_logo(video_path: str, output_path: str, logo_path: Optional[str]) -> None:
    if not logo_path:
        return
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is not available")

    resolved_logo = logo_path
    temp_path = None
    if logo_path.lower().endswith(".webp"):
        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_path = temp_file.name
        with Image.open(logo_path) as img:
            img.convert("RGBA").save(temp_file.name, format="PNG")
        resolved_logo = temp_file.name

    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        resolved_logo,
        "-filter_complex",
        "overlay=W-w-40:H-h-40",
        "-c:a",
        "copy",
        output_path,
    ]

    log_event(LOGGER, "ffmpeg_overlay_start", output_path=output_path)
    try:
        await asyncio.to_thread(_run_command, command)
        log_event(LOGGER, "ffmpeg_overlay_done", output_path=output_path)
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)
