import ast
import json
import re
from typing import Any, Dict, List, Tuple

from app.core.models import AnalysisResult, SEOReport, TranslationResult
from app.services.ollama import chat
from app.utils.logging import get_logger, log_event

LOGGER = get_logger("services.free_llm")


class LocalLLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LocalLLMError("Response missing JSON payload")
    payload = cleaned[start : end + 1]
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        payload = payload.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
        payload = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", payload)
        return json.loads(payload)


async def _repair_json(raw: str) -> Dict[str, Any]:
    prompt = (
        "Fix this into strict JSON only. Do not include markdown or commentary. "
        "Escape any newlines inside JSON strings.\n\n"
        f"Raw:\n{raw}\n"
    )
    fixed, _ = await chat(
        prompt,
        max_tokens=800,
        temperature=0.0,
        system="You fix JSON. Return strict JSON only.",
    )
    try:
        return _extract_json(fixed)
    except Exception as exc:
        log_event(LOGGER, "json_repair_failed", error=str(exc))
        raise


def _validate_analysis(data: Dict[str, Any]) -> AnalysisResult:
    headline = str(data.get("headline", "")).strip()
    category = str(data.get("category", "")).strip()
    tone = str(data.get("tone", "")).strip()
    if not headline or not category or not tone:
        raise LocalLLMError("Missing required keys in analysis output")

    facts = [str(item) for item in data.get("facts", []) if str(item).strip()]
    quotes = [
        {"quote": str(q.get("quote", "")), "speaker": str(q.get("speaker", ""))}
        for q in data.get("quotes", [])
        if isinstance(q, dict)
    ]
    entities = [str(item) for item in data.get("entities", []) if str(item).strip()]
    narrative_arc = data.get("narrative_arc") or {}
    if not isinstance(narrative_arc, dict):
        narrative_arc = {}

    missing = [key for key in ["facts", "quotes", "entities", "narrative_arc"] if key not in data]
    if missing:
        log_event(LOGGER, "analysis_missing_optional_keys", missing=missing)

    return AnalysisResult(
        headline=headline,
        category=category,
        tone=tone,
        facts=facts,
        quotes=quotes,
        entities=entities,
        narrative_arc={
            "setup": str(narrative_arc.get("setup", "")),
            "conflict": str(narrative_arc.get("conflict", "")),
            "resolution": str(narrative_arc.get("resolution", "")),
        },
    )


def _validate_social(data: Dict[str, Any]) -> None:
    required = ["twitter_thread", "linkedin", "instagram", "facebook", "whatsapp"]
    missing = [key for key in required if key not in data]
    if missing:
        raise LocalLLMError(f"Missing keys in social output: {', '.join(missing)}")


def _validate_seo(data: Dict[str, Any]) -> SEOReport:
    required = ["headline_variants", "meta_descriptions", "faqs", "keywords", "internal_links"]
    missing = [key for key in required if key not in data]
    if missing:
        raise LocalLLMError(f"Missing keys in SEO output: {', '.join(missing)}")
    return SEOReport(
        headline_variants=[str(item) for item in data.get("headline_variants", [])],
        meta_descriptions=[str(item) for item in data.get("meta_descriptions", [])],
        faqs=[{"question": str(item.get("question", "")), "answer": str(item.get("answer", ""))} for item in data.get("faqs", [])],
        keywords=[str(item) for item in data.get("keywords", [])],
        internal_links=[str(item) for item in data.get("internal_links", [])],
    )


def _fallback_social(analysis: AnalysisResult) -> Dict[str, Any]:
    lead = analysis.headline or "HT Update"
    facts = analysis.facts[:5]
    return {
        "twitter_thread": [lead] + facts,
        "linkedin": "\n\n".join([lead] + facts),
        "instagram": {"slides": [lead] + facts[:4], "caption": lead},
        "facebook": " ".join(facts[:3]),
        "whatsapp": " ".join(facts[:2]),
    }


def _normalize_social_item(item: Any) -> str:
    if isinstance(item, dict):
        return _format_fact(item)
    if isinstance(item, str):
        stripped = item.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = ast.literal_eval(stripped)
                if isinstance(parsed, dict):
                    return _format_fact(parsed)
            except (ValueError, SyntaxError):
                pass
        return stripped
    return str(item)


def _format_fact(fact: Dict[str, Any]) -> str:
    company = fact.get("company") or fact.get("entity") or ""
    quarter = fact.get("quarter") or fact.get("period") or ""
    date = fact.get("date") or fact.get("time") or ""
    pieces = [str(p).strip() for p in [company, quarter, date] if str(p).strip()]
    if pieces:
        return " | ".join(pieces)
    return ", ".join(f"{k}: {v}" for k, v in fact.items())


def _normalize_social_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    thread = [_normalize_social_item(item) for item in payload.get("twitter_thread", [])]
    linkedin = payload.get("linkedin", "")
    if isinstance(linkedin, list):
        linkedin = "\n\n".join(_normalize_social_item(item) for item in linkedin)
    else:
        linkedin = _normalize_social_item(linkedin)
    instagram = payload.get("instagram", {}) if isinstance(payload.get("instagram"), dict) else {}
    slides = [_normalize_social_item(item) for item in instagram.get("slides", [])]
    caption = _normalize_social_item(instagram.get("caption", ""))
    facebook = _normalize_social_item(payload.get("facebook", ""))
    whatsapp = _normalize_social_item(payload.get("whatsapp", ""))
    return {
        "twitter_thread": thread,
        "linkedin": linkedin,
        "instagram": {"slides": slides, "caption": caption},
        "facebook": facebook,
        "whatsapp": whatsapp,
    }


def _fallback_seo(analysis: AnalysisResult) -> SEOReport:
    headline = analysis.headline or "HT Report"
    return SEOReport(
        headline_variants=[headline],
        meta_descriptions=[f"{headline} - HT summary."],
        faqs=[{"question": f"What happened in {headline}?", "answer": analysis.facts[0] if analysis.facts else ""}],
        keywords=analysis.entities[:10],
        internal_links=["HT Markets", "HT Policy", "HT Explainers"],
    )


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
    text, metadata = await chat(
        prompt,
        max_tokens=1200,
        temperature=0.2,
        system="You are a newsroom analyst. Return strict JSON only.",
    )
    try:
        data = _extract_json(text)
    except Exception:
        data = await _repair_json(text)
    analysis = _validate_analysis(data)
    if not analysis.facts or not analysis.entities:
        repair_prompt = (
            "Extract missing fields from the article. Return JSON with keys: facts, quotes, entities, narrative_arc.\n\n"
            f"Article: {article_text}\n"
        )
        try:
            repaired, _ = await chat(
                repair_prompt,
                max_tokens=800,
                temperature=0.2,
                system="You are a newsroom analyst. Return strict JSON only.",
            )
            repaired_data = _extract_json(repaired)
            analysis = _validate_analysis({**data, **repaired_data})
        except Exception as exc:
            log_event(LOGGER, "analysis_repair_failed", error=str(exc))
    return analysis, metadata


async def generate_video_script(analysis: AnalysisResult, *, style_variant: int = 0) -> Tuple[str, Dict[str, Any]]:
    prompt = (
        "Write a 3-minute news anchor script for a video segment.\n\n"
        f"Source: {analysis.headline} - {analysis.category}\n"
        f"Key Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Requirements:\n"
        "- 420-520 words (3+ minutes at 140-160 wpm)\n"
        "- Professional, confident anchor voice\n"
        "- No section labels like Hook/Body/Conclusion\n"
        "- No stage directions, just spoken narration\n"
        "- Include 1-2 statistics or quotes\n"
        "- End with CTA: \"Read full article at HT.com\"\n\n"
        "Output only the script."
    )
    script, metadata = await chat(
        prompt,
        max_tokens=1200,
        temperature=0.3,
        system="You are a live news anchor. Output plain narration only.",
    )
    if len(script.split()) < 420:
        expand_prompt = (
            "Expand this news anchor script to 420-520 words. "
            "Keep it in a natural, spoken-news style. "
            "No labels or stage directions.\n\n"
            f"Script:\n{script}"
        )
        script, _ = await chat(
            expand_prompt,
            max_tokens=900,
            temperature=0.3,
            system="You are a live news anchor. Output plain narration only.",
        )
    return script.strip(), metadata


async def generate_podcast_script(analysis: AnalysisResult, *, style_variant: int = 0) -> Tuple[str, Dict[str, Any]]:
    prompt = (
        "Write a 3-minute podcast script for a news briefing.\n\n"
        f"Headline: {analysis.headline}\n"
        f"Key Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Requirements:\n"
        "- 420-520 words\n"
        "- Sounds like a real host, not a list\n"
        "- No section labels or stage directions\n"
        "- End with CTA: \"Read full article at HT.com\"\n\n"
        "Output only the script."
    )
    script, metadata = await chat(
        prompt,
        max_tokens=1200,
        temperature=0.3,
        system="You are a podcast host. Output plain narration only.",
    )
    if len(script.split()) < 420:
        expand_prompt = (
            "Expand this podcast script to 420-520 words. "
            "Keep it natural and conversational. "
            "No labels or stage directions.\n\n"
            f"Script:\n{script}"
        )
        script, _ = await chat(
            expand_prompt,
            max_tokens=900,
            temperature=0.3,
            system="You are a podcast host. Output plain narration only.",
        )
    return script.strip(), metadata


async def generate_social_posts(analysis: AnalysisResult, *, style_variant: int = 0) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = (
        "Create platform-specific social posts from this news analysis.\n"
        "Return JSON with keys: twitter_thread (list), linkedin (string), "
        "instagram (object with slides list and caption), facebook (string), whatsapp (string).\n\n"
        f"Headline: {analysis.headline}\n"
        f"Facts: {analysis.facts}\n"
        f"Tone: {analysis.tone}\n\n"
        "Constraints:\n"
        "- Twitter thread 5-7 tweets with hooks\n"
        "- LinkedIn 500-700 words professional\n"
        "- Instagram 5 slides + caption\n"
        "- Facebook 200-300 words\n"
        "- WhatsApp 150 words\n"
        "Return strict JSON only."
    )
    text, metadata = await chat(
        prompt,
        max_tokens=1400,
        temperature=0.4,
        system="You are a social editor. Return strict JSON only.",
    )
    try:
        data = _extract_json(text)
        _validate_social(data)
        return _normalize_social_payload(data), metadata
    except Exception as exc:
        log_event(LOGGER, "social_parse_failed", error=str(exc))
        try:
            data = await _repair_json(text)
            _validate_social(data)
            return _normalize_social_payload(data), metadata
        except Exception as repair_exc:
            log_event(LOGGER, "social_repair_failed", error=str(repair_exc))
            return _normalize_social_payload(_fallback_social(analysis)), {**metadata, "warning": "fallback_social"}


async def generate_translation(analysis: AnalysisResult, article_text: str) -> Tuple[TranslationResult, Dict[str, Any]]:
    prompt = (
        "Translate the full article into Hindi with cultural adaptation, not literal translation.\n"
        "Preserve named entities and proper nouns.\n\n"
        f"Headline: {analysis.headline}\n"
        f"Entities: {analysis.entities}\n\n"
        f"Article: {article_text}\n\n"
        "Return JSON with keys: hindi_text, notes."
    )
    text, metadata = await chat(
        prompt,
        max_tokens=2000,
        temperature=0.3,
        system="You are a bilingual editor. Return strict JSON only.",
    )
    try:
        data = _extract_json(text)
        if "hindi_text" not in data:
            raise LocalLLMError("Missing hindi_text in translation output")
        return TranslationResult(hindi_text=str(data["hindi_text"]), notes=str(data.get("notes", "")) or None), metadata
    except Exception as exc:
        log_event(LOGGER, "translation_parse_failed", error=str(exc))
        try:
            data = await _repair_json(text)
            if "hindi_text" not in data:
                raise LocalLLMError("Missing hindi_text in translation output")
            return TranslationResult(hindi_text=str(data["hindi_text"]), notes=str(data.get("notes", "")) or None), metadata
        except Exception as repair_exc:
            log_event(LOGGER, "translation_repair_failed", error=str(repair_exc))
            return TranslationResult(hindi_text=text.strip(), notes="raw_output"), {**metadata, "warning": "fallback_translation"}


async def generate_seo_package(analysis: AnalysisResult) -> Tuple[SEOReport, Dict[str, Any]]:
    prompt = (
        "Create an SEO package for the news story.\n"
        "Return JSON with keys: headline_variants (10), meta_descriptions (3), "
        "faqs (5 objects with question/answer), keywords (10-15), internal_links (3).\n\n"
        f"Headline: {analysis.headline}\n"
        f"Facts: {analysis.facts}\n"
        f"Entities: {analysis.entities}\n\n"
        "Return strict JSON only."
    )
    text, metadata = await chat(
        prompt,
        max_tokens=1000,
        temperature=0.3,
        system="You are an SEO editor. Return strict JSON only.",
    )
    try:
        data = _extract_json(text)
        report = _validate_seo(data)
        return report, metadata
    except Exception as exc:
        log_event(LOGGER, "seo_parse_failed", error=str(exc))
        try:
            data = await _repair_json(text)
            report = _validate_seo(data)
            return report, metadata
        except Exception as repair_exc:
            log_event(LOGGER, "seo_repair_failed", error=str(repair_exc))
            return _fallback_seo(analysis), {**metadata, "warning": "fallback_seo"}


async def verify_fact(fact: str, sources: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = (
        "Verify this claim against the provided sources.\n"
        "Return JSON with keys: verified (true/false), confidence (high/medium/low), sources (list).\n\n"
        f"Claim: {fact}\n"
        f"Sources: {sources}\n\n"
        "Return strict JSON only."
    )
    text, metadata = await chat(
        prompt,
        max_tokens=500,
        temperature=0.2,
        system="You are a fact-checking editor. Return strict JSON only.",
    )
    try:
        data = _extract_json(text)
    except Exception:
        data = await _repair_json(text)
    return {
        "verified": bool(data.get("verified")),
        "confidence": str(data.get("confidence", "low")),
        "sources": data.get("sources", []),
    }, metadata
