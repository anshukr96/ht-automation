import os
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

from app.utils.logging import get_logger, log_event
from app.utils.media import ffmpeg_available

LOGGER = get_logger("services.free_media")


def generate_placeholder_video(
    script: str,
    output_path: str,
    avatar_path: str | None = None,
) -> Tuple[str, Dict[str, str]]:
    text_path = output_path.replace(".mp4", "_caption.txt")
    with open(text_path, "w", encoding="utf-8") as handle:
        handle.write("HT Content Multiplier Demo\n")
        handle.write(script[:240].replace("\n", " "))

    if not ffmpeg_available():
        return text_path, {"provider": "local_placeholder", "note": "ffmpeg unavailable"}

    drawtext = (
        f"drawtext=textfile={text_path}:"
        "fontcolor=white:fontsize=36:x=560:y=(H-text_h)/2"
    )
    command = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0B1F3A:s=1920x1080:d=60"]
    filter_graph = drawtext
    if avatar_path and os.path.exists(avatar_path):
        command.extend(["-loop", "1", "-i", avatar_path])
        filter_graph = (
            "[1:v]scale=420:-1[av];"
            "[0:v][av]overlay=80:(H-h)/2,"
            + drawtext
        )
    command.extend(["-vf", filter_graph, "-c:v", "libx264", "-t", "60", output_path])
    log_event(LOGGER, "placeholder_video_start", output_path=output_path)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        log_event(LOGGER, "placeholder_video_done", output_path=output_path)
        return output_path, {"provider": "local_ffmpeg"}
    except subprocess.CalledProcessError as exc:
        log_event(
            LOGGER,
            "placeholder_video_failed",
            error=str(exc),
            stderr=(exc.stderr or "")[:400],
        )
        fallback_command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0B1F3A:s=1920x1080:d=10",
            "-c:v",
            "libx264",
            "-t",
            "10",
            output_path,
        ]
        try:
            subprocess.run(fallback_command, check=True, capture_output=True, text=True)
            log_event(LOGGER, "placeholder_video_fallback_ok", output_path=output_path)
            return output_path, {"provider": "local_ffmpeg", "note": "fallback_no_text"}
        except subprocess.CalledProcessError as fallback_exc:
            log_event(
                LOGGER,
                "placeholder_video_fallback_failed",
                error=str(fallback_exc),
                stderr=(fallback_exc.stderr or "")[:400],
            )
            return text_path, {"provider": "local_placeholder", "note": "ffmpeg failed"}


def generate_avatar_video(
    script: str,
    output_path: str,
    avatar_path: str,
    voice: str | None = None,
) -> Tuple[str, Dict[str, str]]:
    if not ffmpeg_available():
        return generate_placeholder_video(script, output_path, avatar_path=None)

    audio_path, audio_meta = generate_tts_audio(script, output_path.replace(".mp4", ".mp3"), voice=voice)
    filter_complex = (
        "[0:v]scale=1920:-1,"
        "zoompan=z='min(zoom+0.0005,1.03)':d=1800:s=1920x1080:fps=30,"
        "format=yuv420p[v]"
    )
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        avatar_path,
        "-i",
        audio_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    log_event(LOGGER, "avatar_video_start", output_path=output_path)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        log_event(LOGGER, "avatar_video_done", output_path=output_path)
        metadata = {
            "provider": "local_avatar",
            "voice": voice or "",
            "audio_path": audio_path,
            **audio_meta,
        }
        return output_path, metadata
    except subprocess.CalledProcessError as exc:
        log_event(
            LOGGER,
            "avatar_video_failed",
            error=str(exc),
            stderr=(exc.stderr or "")[:400],
        )
        fallback_path, meta = generate_placeholder_video(script, output_path, avatar_path=None)
        meta["note"] = "avatar_ffmpeg_failed"
        return fallback_path, meta


def generate_tts_audio(text: str, output_path: str, voice: str | None = None) -> Tuple[str, Dict[str, str]]:
    aiff_path = output_path.replace(".mp3", ".aiff")
    command = ["say"]
    if voice:
        command.extend(["-v", voice])
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
        handle.write(text)
        text_path = handle.name
    command.extend(["-f", text_path, "-o", aiff_path])
    log_event(LOGGER, "local_tts_start", output_path=aiff_path, voice=voice)
    subprocess.run(command, check=True, capture_output=True)
    log_event(LOGGER, "local_tts_done", output_path=aiff_path, voice=voice)

    if ffmpeg_available():
        command = ["ffmpeg", "-y", "-i", aiff_path, output_path]
        subprocess.run(command, check=True, capture_output=True)
        os.remove(aiff_path)
        return output_path, {"provider": "local_say", "format": "mp3"}

    return aiff_path, {"provider": "local_say", "format": "aiff", "voice": voice}


def has_say() -> bool:
    return subprocess.call(["which", "say"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0


def resolve_voice() -> Optional[str]:
    return None
