import json
import os
from typing import Any, Dict, List

from app.core.models import AnalysisResult
from app.services.brave_search import BraveSearchError, web_search
from app.services.claude import verify_fact
from app.utils.logging import get_logger, log_event
from app.utils.text import find_prohibited_phrases, flesch_reading_ease

LOGGER = get_logger("pipelines.qa")

PROHIBITED_PHRASES = ["I think", "In my opinion", "We believe"]


async def run_qa_pipeline(
    job_id: str,
    analysis: AnalysisResult,
    article_text: str,
    output_dir: str,
) -> List[Dict[str, Any]]:
    fact_checks: List[Dict[str, Any]] = []

    for fact in analysis.facts:
        try:
            results = await web_search(fact)
            verification, meta = await verify_fact(fact, results)
            fact_checks.append(
                {
                    "fact": fact,
                    "verified": bool(verification.get("verified")),
                    "confidence": verification.get("confidence", "low"),
                    "sources": verification.get("sources", []),
                    "meta": meta,
                }
            )
        except BraveSearchError as exc:
            log_event(LOGGER, "qa_search_unavailable", job_id=job_id, error=str(exc))
            fact_checks.append(
                {
                    "fact": fact,
                    "verified": False,
                    "confidence": "low",
                    "sources": [],
                    "meta": {"error": str(exc)},
                }
            )
        except Exception as exc:
            log_event(LOGGER, "qa_fact_error", job_id=job_id, error=str(exc))
            fact_checks.append(
                {
                    "fact": fact,
                    "verified": False,
                    "confidence": "low",
                    "sources": [],
                    "meta": {"error": str(exc)},
                }
            )

    readability = flesch_reading_ease(article_text)
    prohibited = find_prohibited_phrases(article_text, PROHIBITED_PHRASES)
    compliance_notes = []
    if prohibited:
        compliance_notes.append(f"Prohibited phrases found: {', '.join(prohibited)}")

    verified_count = sum(1 for item in fact_checks if item.get("verified"))
    score = 0.0
    if fact_checks:
        score = round((verified_count / len(fact_checks)) * 100.0, 2)

    qa_payload = {
        "score": score,
        "readability": readability,
        "compliance_notes": compliance_notes,
        "fact_checks": fact_checks,
        "plagiarism": {"status": "unverified", "notes": "plagiarism check not configured"},
    }

    path = os.path.join(output_dir, f"{job_id}_qa.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(qa_payload, handle, ensure_ascii=True, indent=2)

    return [{"type": "qa", "path": path, "metadata": {"score": score}}]
