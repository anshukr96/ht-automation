from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class AnalysisResult:
    headline: str
    category: str
    tone: str
    facts: List[str]
    quotes: List[Dict[str, str]]
    entities: List[str]
    narrative_arc: Dict[str, str]


@dataclass
class Job:
    id: str
    status: str
    progress: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


@dataclass
class Artifact:
    job_id: str
    type: str
    path: str
    metadata: Dict[str, Any]
