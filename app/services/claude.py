import json
import os
from typing import Any, Dict, Tuple

import httpx

from app.core.models import AnalysisResult
from app.utils.logging import get_logger, log_event
from app.utils.retry import async_retry

LOGGER = get_logger("services.claude")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

PRICE_PER_1K_INPUT = 0.008
PRICE_PER_1K_OUTPUT = 0.024


class ClaudeError(RuntimeError):
    pass


def _extract_json(text: str) -> Dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ClaudeError("Claude response missing JSON payload")
    payload = text[start : end + 1]
    return json.loads(payload)


def _validate_analysis(data: Dict[str, Any]) -> AnalysisResult:
    required = ["headline", "category", "tone", "facts", "quotes", "entities", "narrative_arc"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ClaudeError(f"Missing keys in analysis output: {', '.join(missing)}")
    return AnalysisResult(
        headline=str(data["headline"]),
        category=str(data["category"]),
        tone=str(data["tone"]),
        facts=[str(item) for item in data.get("facts", [])],
        quotes=[{"quote": str(q.get("quote", "")), "speaker": str(q.get("speaker", ""))} for q in data.get("quotes", [])],
        entities=[str(item) for item in data.get("entities", [])],
        narrative_arc={
            "setup": str(data.get("narrative_arc", {}).get("setup", "")),
            "conflict": str(data.get("narrative_arc", {}).get("conflict", "")),
            "resolution": str(data.get("narrative_arc", {}).get("resolution", "")),
        },
    )


async def _post(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    if not ANTHROPIC_API_KEY:
        raise ClaudeError("ANTHROPIC_API_KEY is not set")

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    @async_retry(attempts=3, base_delay=0.8, exceptions=(httpx.HTTPError, ClaudeError))
    async def _request() -> Tuple[Dict[str, Any], float]:
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(ANTHROPIC_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage", {})
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
            cost = (input_tokens / 1000.0) * PRICE_PER_1K_INPUT + (output_tokens / 1000.0) * PRICE_PER_1K_OUTPUT
            return data, cost

    return await _request()


async def _call_claude(prompt: str, *, max_tokens: int, temperature: float, system: str) -> Tuple[str, Dict[str, Any]]:
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    log_event(LOGGER, "claude_request", model=ANTHROPIC_MODEL)
    response, cost = await _post(payload)
    content_blocks = response.get("content", [])
    if not content_blocks:
        raise ClaudeError("Empty response from Claude")
    text = content_blocks[0].get("text", "")
    metadata = {
        "model": ANTHROPIC_MODEL,
        "usage": response.get("usage", {}),
        "cost_usd": round(cost, 6),
    }
    log_event(LOGGER, "claude_response", cost_usd=metadata["cost_usd"], usage=metadata["usage"])
    return text, metadata


async def analyze_content(article_text: str) -> Tuple[AnalysisResult, Dict[str, Any]]:
    prompt = (
        "Analyze this news article and extract:\n"
        "1. Headline, category, tone (neutral/urgent/investigative)\n"
        "2. Key facts (list all verifiable claims)\n"
        "3. Key quotes (with attribution)\n"
        "4. Named entities (people, places, organizations)\n"
        "5. Narrative arc (setup, conflict, resolution)\n\n"
        f"Article: {article_text}\n\n"
        "Return as structured JSON."
    )

    text, metadata = await _call_claude(
        prompt,
        max_tokens=1200,
        temperature=0.2,
        system="You are a newsroom analyst. Return strict JSON only.",
    )
    data = _extract_json(text)
    analysis = _validate_analysis(data)
    return analysis, metadata


async def generate_video_script(analysis: AnalysisResult) -> Tuple[str, Dict[str, Any]]:
    prompt = (
        "Create a 60-second news video script.\n\n"
        f"Source: {analysis.headline} - {analysis.category}\n"
        f"Key Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Requirements:\n"
        "- Max 150 words (comfortable speaking pace)\n"
        "- Structure: Hook (5s) -> Body (45s) -> Conclusion (10s)\n"
        "- Conversational yet authoritative\n"
        "- Include 1-2 key statistics or quotes\n"
        "- End with CTA: \"Read full article at HT.com\"\n\n"
        "Output only the script, no preamble."
    )
    script, metadata = await _call_claude(
        prompt,
        max_tokens=500,
        temperature=0.3,
        system="You write broadcast-ready scripts. Output plain text only.",
    )
    words = script.split()
    if len(words) > 160:
        script = " ".join(words[:150]).strip()
        metadata["note"] = "script_trimmed"
    return script.strip(), metadata


async def generate_podcast_script(analysis: AnalysisResult) -> Tuple[str, Dict[str, Any]]:
    prompt = (
        "Write a 3-5 minute podcast script based on the article analysis.\n\n"
        f"Headline: {analysis.headline}\n"
        f"Key Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Requirements:\n"
        "- 450-700 words\n"
        "- Friendly, informative tone\n"
        "- Include a brief intro and wrap-up\n"
        "- Mention source attribution\n\n"
        "Output only the script, no preamble."
    )
    script, metadata = await _call_claude(
        prompt,
        max_tokens=1200,
        temperature=0.4,
        system="You write podcast narration. Output plain text only.",
    )
    return script.strip(), metadata


async def generate_social_posts(analysis: AnalysisResult) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = (
        "Generate platform-specific social posts based on the article analysis.\n\n"
        f"Headline: {analysis.headline}\n"
        f"Key Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Return strict JSON with keys:\n"
        "twitter_thread (list of 5-7 tweets),\n"
        "linkedin (500-700 words),\n"
        "instagram (object with slides list and caption),\n"
        "facebook (200-300 words),\n"
        "whatsapp (150-word summary).\n"
    )
    text, metadata = await _call_claude(
        prompt,
        max_tokens=1600,
        temperature=0.4,
        system="You are a social editor. Return strict JSON only.",
    )
    data = _extract_json(text)
    _validate_social(data)
    return data, metadata


def _validate_social(data: Dict[str, Any]) -> None:
    required = ["twitter_thread", "linkedin", "instagram", "facebook", "whatsapp"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ClaudeError(f"Missing keys in social output: {', '.join(missing)}")
