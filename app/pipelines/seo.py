import json
import os
from typing import Any, Dict, List

from app.core.models import AnalysisResult
from app.services.claude import generate_seo_package


async def run_seo_pipeline(job_id: str, analysis: AnalysisResult, output_dir: str) -> List[Dict[str, Any]]:
    report, meta = await generate_seo_package(analysis)
    path = os.path.join(output_dir, f"{job_id}_seo.json")
    payload = {
        "headline_variants": report.headline_variants,
        "meta_descriptions": report.meta_descriptions,
        "faqs": report.faqs,
        "keywords": report.keywords,
        "internal_links": report.internal_links,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
    return [{"type": "seo", "path": path, "metadata": meta}]
