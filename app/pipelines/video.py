import os
from typing import Any, Dict, List

import httpx

from app.core.models import AnalysisResult
from app.services.claude import generate_video_script
from app.services.did import create_talk
from app.utils.logging import get_logger, log_event
from app.utils.media import overlay_logo
from app.utils.retry import async_retry

LOGGER = get_logger("pipelines.video")


async def run_video_pipeline(job_id: str, analysis: AnalysisResult, output_dir: str) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    script, script_meta = await generate_video_script(analysis)

    script_path = os.path.join(output_dir, f"{job_id}_video_script.txt")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    artifacts.append({"type": "video_script", "path": script_path, "metadata": script_meta})

    video_url, did_meta = await create_talk(script)
    video_path = os.path.join(output_dir, f"{job_id}_video_raw.mp4")
    await _download_file(video_url, video_path)
    artifacts.append({"type": "video_raw", "path": video_path, "metadata": did_meta})

    branded_path = os.path.join(output_dir, f"{job_id}_video_branded.mp4")
    logo_path = os.getenv("HT_LOGO_PATH", "")
    try:
        await overlay_logo(video_path, branded_path, logo_path or None)
        if os.path.exists(branded_path):
            artifacts.append({"type": "video_branded", "path": branded_path, "metadata": {"logo": logo_path}})
        else:
            artifacts.append({"type": "video_branded", "path": video_path, "metadata": {"logo": None}})
    except Exception as exc:
        log_event(LOGGER, "video_branding_failed", job_id=job_id, error=str(exc))
        artifacts.append({"type": "video_branded", "path": video_path, "metadata": {"logo": None, "error": str(exc)}})

    return artifacts


async def _download_file(url: str, path: str) -> None:
    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _request() -> bytes:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    log_event(LOGGER, "video_download_start", url=url)
    data = await _request()
    with open(path, "wb") as handle:
        handle.write(data)
    log_event(LOGGER, "video_download_done", bytes=len(data))
