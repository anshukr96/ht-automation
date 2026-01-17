import asyncio
import threading
import os
import subprocess
import sys
import tempfile
from typing import Dict, Optional, Tuple

from app.utils.logging import get_logger, log_event
from app.services.decart import decart_available, decart_capabilities, generate_lipsync_video as decart_lipsync
from app.utils.media import ffmpeg_available

LOGGER = get_logger("services.free_media")
WAV2LIP_DIR = os.getenv(
    "WAV2LIP_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "tools", "wav2lip"),
)
WAV2LIP_CHECKPOINT = os.getenv(
    "WAV2LIP_CHECKPOINT",
    os.path.join(WAV2LIP_DIR, "checkpoints", "wav2lip_gan.pth"),
)
WAV2LIP_FACE_MODEL = os.getenv(
    "WAV2LIP_FACE_MODEL",
    os.path.join(WAV2LIP_DIR, "face_detection", "detection", "sfd", "s3fd.pth"),
)


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
    wav2lip_error = ""
    decart_error = ""
    if not ffmpeg_available():
        return generate_placeholder_video(script, output_path, avatar_path=None)

    audio_path, audio_meta = generate_tts_audio(script, output_path.replace(".mp4", ".mp3"), voice=voice)
    decart_only = os.getenv("DECART_ONLY", "1").lower() in {"1", "true", "yes"}
    caps = decart_capabilities()
    available = caps["api_key"] and (caps["sdk"] or caps["ws"])
    log_event(LOGGER, "decart_precheck", **caps, available=available, decart_only=decart_only)
    if available:
        try:
            decart_path = output_path.replace(".mp4", "_decart.mp4")
            decart_path, decart_meta = asyncio_run(decart_lipsync(avatar_path, audio_path, decart_path))
            decart_meta.update({"voice": voice or "", **audio_meta, "lipsync": "decart"})
            return decart_path, decart_meta
        except Exception as exc:
            log_event(LOGGER, "decart_failed", error=repr(exc))
            decart_error = str(exc)
            if decart_only:
                raise
    elif decart_only:
        raise RuntimeError("Decart is required but not available in this environment.")

    if _use_wav2lip() and _wav2lip_ready():
        try:
            wav2lip_path = output_path.replace(".mp4", "_lipsync.mp4")
            wav2lip_path, wav2lip_meta = generate_lipsync_video(
                avatar_path,
                audio_path,
                wav2lip_path,
            )
            wav2lip_meta.update({"voice": voice or "", **audio_meta, "lipsync": "wav2lip"})
            return wav2lip_path, wav2lip_meta
        except Exception as exc:
            log_event(LOGGER, "wav2lip_failed", error=str(exc))
            wav2lip_error = str(exc)
    else:
        wav2lip_error = "wav2lip_unavailable"

    filter_complex = (
        "[0:v]scale=1920:-1,"
        "zoompan="
        "z='min(zoom+0.0006,1.04)':"
        "x='iw/2-(iw/zoom/2)+sin(on/12)*12':"
        "y='ih/2-(ih/zoom/2)+sin(on/17)*10':"
        "d=1800:s=1920x1080:fps=30,"
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
            "lipsync": "fallback",
            "wav2lip_error": wav2lip_error,
            "decart_error": decart_error,
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


def _use_wav2lip() -> bool:
    return os.getenv("USE_WAV2LIP", "0").lower() in {"1", "true", "yes"}


def _wav2lip_ready() -> bool:
    if not os.path.isdir(WAV2LIP_DIR):
        return False
    if not os.path.exists(os.path.join(WAV2LIP_DIR, "inference.py")):
        return False
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        return False
    if not os.path.exists(WAV2LIP_FACE_MODEL):
        return False
    if os.path.getsize(WAV2LIP_CHECKPOINT) < 50_000_000:
        return False
    if os.path.getsize(WAV2LIP_FACE_MODEL) < 10_000_000:
        return False
    return True


def _resolve_wav2lip_python() -> str:
    override = os.getenv("WAV2LIP_PYTHON")
    if override:
        return override
    venv_python = os.path.join(WAV2LIP_DIR, ".venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    python310 = "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3"
    if os.path.exists(python310):
        return python310
    return sys.executable


def asyncio_run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    result: dict[str, object] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def generate_lipsync_video(
    image_path: str,
    audio_path: str,
    output_path: str,
) -> Tuple[str, Dict[str, str]]:
    pads = os.getenv("WAV2LIP_PADS", "0,20,0,0")
    pad_vals = [item.strip() for item in pads.split(",") if item.strip()]
    if len(pad_vals) != 4:
        pad_vals = ["0", "20", "0", "0"]
    ext = os.path.splitext(image_path)[1].lower()
    static_flag = ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    os.makedirs(os.path.join(WAV2LIP_DIR, "temp"), exist_ok=True)
    command = [
        _resolve_wav2lip_python(),
        os.path.join(WAV2LIP_DIR, "inference.py"),
        "--checkpoint_path",
        WAV2LIP_CHECKPOINT,
        "--face",
        image_path,
        "--audio",
        audio_path,
        "--outfile",
        output_path,
        "--pads",
        *pad_vals,
    ]
    if static_flag:
        command.extend(["--static", "1"])
    env = os.environ.copy()
    env["PYTHONPATH"] = WAV2LIP_DIR + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("NUMBA_CACHE_DIR", tempfile.mkdtemp(prefix="numba_cache_"))
    env.setdefault("NUMBA_DISABLE_CACHING", "1")
    log_event(LOGGER, "wav2lip_start", output_path=output_path)
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=WAV2LIP_DIR,
        timeout=300,
    )
    log_event(LOGGER, "wav2lip_done", output_path=output_path)
    return output_path, {"provider": "wav2lip"}
