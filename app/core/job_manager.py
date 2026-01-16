import asyncio
import json
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Tuple

import httpx

from app.core.models import AnalysisResult, Job
from app.services.claude import analyze_content
from app.storage import db
from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry
from app.utils.validation import validate_article

LOGGER = get_logger("core.job_manager")

ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "storage", "artifacts")


class JobManager:
    def __init__(self) -> None:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        db.insert_job(job_id, "queued", 0)
        log_event(LOGGER, "job_created", job_id=job_id)
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        row = db.fetch_job(job_id)
        if not row:
            return None
        return Job(
            id=row["id"],
            status=row["status"],
            progress=int(row["progress"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            error=row["error"],
        )

    def list_artifacts(self, job_id: str) -> list[Dict[str, Any]]:
        rows = db.fetch_artifacts(job_id)
        artifacts: list[Dict[str, Any]] = []
        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
            artifacts.append({"type": row["type"], "path": row["path"], "metadata": metadata})
        return artifacts

    def start_analysis(self, job_id: str, source_type: str, source_payload: str) -> None:
        thread = threading.Thread(
            target=self._run_async_job,
            args=(job_id, source_type, source_payload),
            daemon=True,
        )
        thread.start()

    def _run_async_job(self, job_id: str, source_type: str, source_payload: str) -> None:
        asyncio.run(self._analyze_job(job_id, source_type, source_payload))

    async def _analyze_job(self, job_id: str, source_type: str, source_payload: str) -> None:
        try:
            db.update_job(job_id, status="running", progress=5)
            log_event(LOGGER, "job_started", job_id=job_id)

            db.update_job(job_id, progress=15)
            article_text = await _resolve_article_text(source_type, source_payload)
            validate_article(article_text)
            db.update_job(job_id, progress=25)
            analysis, metadata = await analyze_content(article_text)
            db.update_job(job_id, progress=80)

            artifact_path = os.path.join(ARTIFACT_DIR, f"{job_id}_analysis.json")
            with open(artifact_path, "w", encoding="utf-8") as handle:
                json.dump(_analysis_to_dict(analysis), handle, ensure_ascii=True, indent=2)

            db.insert_artifact(job_id, "analysis", artifact_path, metadata)
            db.update_job(job_id, status="completed", progress=100, finished=True)
            log_event(LOGGER, "job_completed", job_id=job_id)
        except Exception as exc:
            log_event(LOGGER, "job_failed", job_id=job_id, error=str(exc))
            db.update_job(job_id, status="failed", progress=100, error=str(exc), finished=True)


def _analysis_to_dict(analysis: AnalysisResult) -> Dict[str, Any]:
    return {
        "headline": analysis.headline,
        "category": analysis.category,
        "tone": analysis.tone,
        "facts": analysis.facts,
        "quotes": analysis.quotes,
        "entities": analysis.entities,
        "narrative_arc": analysis.narrative_arc,
    }


async def _resolve_article_text(source_type: str, source_payload: str) -> str:
    if source_type == "paste":
        return source_payload
    if source_type == "url":
        return await _fetch_url_text(source_payload)
    if source_type == "upload":
        return source_payload
    raise ValueError(f"Unsupported source type: {source_type}")


async def _fetch_url_text(url: str) -> str:
    log_event(LOGGER, "fetch_url_start", url=url)

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError,))
    async def _request() -> str:
        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    text = await _request()
    log_event(LOGGER, "fetch_url_complete", url=url, bytes=len(text))
    return text
