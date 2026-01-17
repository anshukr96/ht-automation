import asyncio
import base64
import json
import os
import ssl
import subprocess
import tempfile
from typing import Dict, Optional, Tuple

from PIL import Image

from app.utils.logging import get_logger, log_event

try:
    import websockets
except Exception:
    websockets = None

try:
    from decart import DecartClient, models
    from decart.realtime import RealtimeConnectOptions
except Exception:
    DecartClient = None
    models = None
    RealtimeConnectOptions = None

try:
    from aiortc.contrib.media import MediaRecorder
except Exception:
    MediaRecorder = None

try:
    import certifi
except Exception:
    certifi = None

LOGGER = get_logger("services.decart")


def decart_available() -> bool:
    caps = decart_capabilities()
    return caps["api_key"] and (caps["sdk"] or caps["ws"])


def decart_capabilities() -> Dict[str, bool]:
    return {
        "api_key": bool(os.getenv("DECART_API_KEY")),
        "sdk": DecartClient is not None,
        "ws": websockets is not None,
        "aiortc": MediaRecorder is not None,
    }


async def generate_lipsync_video(
    image_path: str,
    audio_path: str,
    output_path: str,
    *,
    fps: int = 8,
    sample_rate: int = 16000,
    max_seconds: int = 45,
) -> Tuple[str, Dict[str, str]]:
    if not decart_available():
        raise RuntimeError("Decart not available. Install decart/websockets and set DECART_API_KEY.")

    log_event(
        LOGGER,
        "decart_capabilities",
        sdk=bool(DecartClient),
        ws=bool(websockets),
        aiortc=bool(MediaRecorder),
    )

    prefer_ws = os.getenv("DECART_PREFER_WS", "1").lower() in {"1", "true", "yes"}
    if not prefer_ws and DecartClient is not None and RealtimeConnectOptions is not None:
        try:
            log_event(LOGGER, "decart_sdk_attempt")
            return await _generate_lipsync_video_sdk(
                image_path=image_path,
                audio_path=audio_path,
                output_path=output_path,
                max_seconds=max_seconds,
            )
        except Exception as exc:
            log_event(LOGGER, "decart_sdk_failed", error=str(exc))

    if websockets is None:
        raise RuntimeError("Decart websocket client not available. Install websockets.")

    duration = _audio_duration(audio_path)
    segment_seconds = int(os.getenv("DECART_SEGMENT_SECONDS", "15"))
    if duration > segment_seconds:
        segments = _split_audio(audio_path, segment_seconds)
        segment_videos: list[str] = []
        for idx, segment_path in enumerate(segments):
            segment_out = output_path.replace(".mp4", f"_seg{idx + 1}.mp4")
            await _generate_lipsync_video_ws(
                image_path=image_path,
                audio_path=segment_path,
                output_path=segment_out,
                fps=fps,
                sample_rate=sample_rate,
                max_seconds=max_seconds,
            )
            segment_videos.append(segment_out)
        _concat_videos(segment_videos, output_path)
        return output_path, {"provider": "decart_ws", "segments": str(len(segment_videos))}

    await _generate_lipsync_video_ws(
        image_path=image_path,
        audio_path=audio_path,
        output_path=output_path,
        fps=fps,
        sample_rate=sample_rate,
        max_seconds=max_seconds,
    )
    return output_path, {"provider": "decart_ws", "segments": "1"}


async def _generate_lipsync_video_ws(
    image_path: str,
    audio_path: str,
    output_path: str,
    *,
    fps: int,
    sample_rate: int,
    max_seconds: int,
) -> None:
    api_key = os.getenv("DECART_API_KEY", "").strip()
    ws_url = f"wss://api.decart.ai/router/lipsync/ws?api_key={api_key}"
    tmp_dir = tempfile.mkdtemp(prefix="decart_lipsync_")
    pcm_path = os.path.join(tmp_dir, "audio.pcm")
    wav_path = os.path.join(tmp_dir, "audio.wav")
    frame_dir = os.path.join(tmp_dir, "frames")
    os.makedirs(frame_dir, exist_ok=True)

    _encode_audio_to_pcm(audio_path, pcm_path, sample_rate)
    duration = _pcm_duration(pcm_path, sample_rate)
    duration = min(duration, max_seconds)
    total_frames = max(1, int(duration * fps))
    audio_chunk_bytes = int(sample_rate / fps) * 2

    image_bytes = _load_image_bytes(image_path)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    log_event(LOGGER, "decart_ws_connect", fps=fps, sample_rate=sample_rate, frames=total_frames)
    ssl_context = ssl.create_default_context(cafile=certifi.where()) if certifi else ssl.create_default_context()
    try:
        async with websockets.connect(
            ws_url,
            max_size=2**25,
            ssl=ssl_context,
            ping_interval=15,
            ping_timeout=15,
        ) as ws:
            await ws.send(json.dumps({"type": "config", "video_fps": fps, "audio_sample_rate": sample_rate}))
            await _await_config_ack(ws)

            with open(pcm_path, "rb") as handle:
                pcm_bytes = handle.read()

            async def _receiver() -> int:
                received = 0
                while received < total_frames:
                    message = await _await_synced_result(ws)
                    frame_b64 = message.get("video_frame")
                    if frame_b64:
                        _write_frame(frame_b64, os.path.join(frame_dir, f"frame_{received:05d}.png"))
                        received += 1
                return received

            async def _keepalive() -> None:
                while True:
                    await asyncio.sleep(10)
                    await ws.ping()

            receiver_task = asyncio.create_task(_receiver())
            keepalive_task = asyncio.create_task(_keepalive())
            frame_interval = 1.0 / fps
            for idx in range(total_frames):
                start = idx * audio_chunk_bytes
                end = start + audio_chunk_bytes
                chunk = pcm_bytes[start:end]
                if len(chunk) < audio_chunk_bytes:
                    chunk = chunk + b"\x00" * (audio_chunk_bytes - len(chunk))
                audio_b64 = base64.b64encode(chunk).decode("ascii")
                await ws.send(json.dumps({"type": "video_input", "video_frame": image_b64}))
                await ws.send(json.dumps({"type": "audio_input", "audio_data": audio_b64}))
                await asyncio.sleep(frame_interval)

            silent_chunk = b"\x00" * audio_chunk_bytes
            end_time = asyncio.get_event_loop().time() + max_seconds + 30
            while not receiver_task.done() and asyncio.get_event_loop().time() < end_time:
                await ws.send(json.dumps({"type": "video_input", "video_frame": image_b64}))
                await ws.send(json.dumps({"type": "audio_input", "audio_data": base64.b64encode(silent_chunk).decode("ascii")}))
                await asyncio.sleep(frame_interval)

            received_frames = None
            try:
                received_frames = await asyncio.wait_for(receiver_task, timeout=10)
            except asyncio.TimeoutError:
                log_event(LOGGER, "decart_ws_timeout_partial", sent_frames=total_frames)
                receiver_task.cancel()
            finally:
                keepalive_task.cancel()

            frame_files = sorted(
                name for name in os.listdir(frame_dir) if name.endswith(".png")
            )
            received_frames = received_frames or len(frame_files)
            log_event(LOGGER, "decart_ws_complete", sent_frames=total_frames, received_frames=received_frames)
            if received_frames == 0:
                raise RuntimeError("Decart returned no frames.")
    except Exception as exc:
        log_event(LOGGER, "decart_ws_error", error=repr(exc))
        raise

    _trim_audio(audio_path, wav_path, duration, sample_rate)
    _encode_frames_to_video(frame_dir, fps, output_path, wav_path)


async def _generate_lipsync_video_sdk(
    image_path: str,
    audio_path: str,
    output_path: str,
    max_seconds: int,
) -> Tuple[str, Dict[str, str]]:
    if DecartClient is None or RealtimeConnectOptions is None:
        raise RuntimeError("Decart SDK not available.")
    if MediaRecorder is None:
        raise RuntimeError("aiortc not available to record Decart stream.")

    api_key = os.getenv("DECART_API_KEY", "").strip()
    client = DecartClient(api_key=api_key)
    model = _resolve_realtime_model()
    avatar_bytes = _load_image_bytes(image_path)
    audio_bytes = _read_bytes(audio_path)
    duration = min(_audio_duration(audio_path), max_seconds)

    recorder_ready = asyncio.Event()
    recorder: Optional[MediaRecorder] = None

    def _on_remote_stream(stream) -> None:
        nonlocal recorder
        recorder = MediaRecorder(output_path)
        for track in stream.getTracks():
            recorder.addTrack(track)
        asyncio.get_event_loop().create_task(recorder.start())
        recorder_ready.set()

    options = RealtimeConnectOptions(
        model=model,
        avatar={"avatar_image": avatar_bytes},
        on_remote_stream=_on_remote_stream,
    )
    realtime_client = await client.realtime.connect(stream=None, options=options)
    await recorder_ready.wait()
    await realtime_client.play_audio(audio_bytes)
    await asyncio.sleep(duration + 0.25)
    await realtime_client.disconnect()
    if recorder:
        await recorder.stop()
    return output_path, {"provider": "decart_sdk", "duration": f"{duration:.2f}"}


def _resolve_realtime_model():
    env_model = os.getenv("DECART_MODEL")
    if env_model:
        return models.realtime(env_model.strip())
    candidates = ["avatar_live", "avatar-live", "live_avatar", "Avatar Live"]
    last_error = None
    for name in candidates:
        try:
            return models.realtime(name)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Decart realtime model not found. Tried: {', '.join(candidates)}") from last_error


def _await_config_ack(ws) -> asyncio.Future:
    async def _wait():
        while True:
            payload = json.loads(await ws.recv())
            log_event(LOGGER, "decart_ws_message", type=payload.get("type", "unknown"))
            if payload.get("type") == "config_ack":
                log_event(LOGGER, "decart_ws_config_ack")
                return payload
            if payload.get("type") == "error":
                raise RuntimeError(payload.get("message", "Decart config error"))
    return _wait()


def _await_synced_result(ws) -> asyncio.Future:
    async def _wait():
        while True:
            payload = json.loads(await ws.recv())
            log_event(LOGGER, "decart_ws_message", type=payload.get("type", "unknown"))
            if payload.get("type") == "synced_result":
                return payload
            if payload.get("type") == "error":
                raise RuntimeError(payload.get("message", "Decart sync error"))
    return _wait()


def _encode_audio_to_pcm(input_path: str, output_path: str, sample_rate: int) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        output_path,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def _pcm_duration(path: str, sample_rate: int) -> float:
    size = os.path.getsize(path)
    return size / float(sample_rate * 2)


def _load_image_bytes(path: str) -> bytes:
    with Image.open(path) as image:
        image = image.convert("RGB")
        buffer = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        image.save(buffer.name, format="JPEG", quality=92)
        with open(buffer.name, "rb") as handle:
            return handle.read()


def _write_frame(frame_b64: str, path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(base64.b64decode(frame_b64))


def _trim_audio(input_path: str, output_path: str, duration: float, sample_rate: int) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-t",
        f"{duration:.2f}",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        output_path,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def _encode_frames_to_video(frame_dir: str, fps: int, output_path: str, audio_path: str) -> None:
    video_tmp = output_path.replace(".mp4", "_decart_tmp.mp4")
    command_frames = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        os.path.join(frame_dir, "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        video_tmp,
    ]
    subprocess.run(command_frames, check=True, capture_output=True, text=True)
    command_mux = [
        "ffmpeg",
        "-y",
        "-i",
        video_tmp,
        "-i",
        audio_path,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]
    subprocess.run(command_mux, check=True, capture_output=True, text=True)


def _split_audio(path: str, segment_seconds: int) -> list[str]:
    tmp_dir = tempfile.mkdtemp(prefix="decart_segments_")
    pattern = os.path.join(tmp_dir, "segment_%03d.mp3")
    command = [
        "ffmpeg",
        "-y",
        "-i",
        path,
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-c",
        "copy",
        pattern,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    segments = sorted(
        os.path.join(tmp_dir, name)
        for name in os.listdir(tmp_dir)
        if name.endswith(".mp3")
    )
    return segments


def _concat_videos(paths: list[str], output_path: str) -> None:
    tmp_list = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    with open(tmp_list.name, "w", encoding="utf-8") as handle:
        for path in paths:
            handle.write(f"file '{path}'\n")
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        tmp_list.name,
        "-c",
        "copy",
        output_path,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def _audio_duration(path: str) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        path,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0
