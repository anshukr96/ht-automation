import asyncio
import shutil
import subprocess
from typing import Optional

from app.utils.logging import get_logger, log_event

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
        "showwaves=s=1080x1080:mode=line:rate=25,format=yuv420p",
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

    command = [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-i",
        logo_path,
        "-filter_complex",
        "overlay=W-w-40:H-h-40",
        "-c:a",
        "copy",
        output_path,
    ]

    log_event(LOGGER, "ffmpeg_overlay_start", output_path=output_path)
    await asyncio.to_thread(_run_command, command)
    log_event(LOGGER, "ffmpeg_overlay_done", output_path=output_path)


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True)
