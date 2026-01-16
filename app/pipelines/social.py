import json
import os
from typing import Any, Dict, List

from app.core.models import AnalysisResult
from app.services.claude import generate_social_posts


async def run_social_pipeline(
    job_id: str,
    analysis: AnalysisResult,
    output_dir: str,
    style_guide: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    posts, meta = await generate_social_posts(analysis, style_guide)
    path = os.path.join(output_dir, f"{job_id}_social.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(posts, handle, ensure_ascii=True, indent=2)
    return [{"type": "social", "path": path, "metadata": meta}]
