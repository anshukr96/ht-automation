import os
import re
from typing import Any, Dict, List, Tuple

from app.core.models import AnalysisResult, SEOReport, TranslationResult


STOPWORDS = {
    "The",
    "A",
    "An",
    "This",
    "That",
    "These",
    "Those",
    "He",
    "She",
    "It",
    "They",
    "We",
    "You",
    "I",
    "In",
    "On",
    "At",
    "For",
    "With",
    "By",
    "From",
    "To",
    "As",
    "Of",
}


def analyze_content(article_text: str) -> Tuple[AnalysisResult, Dict[str, Any]]:
    lines = [line.strip() for line in article_text.splitlines() if line.strip()]
    headline = lines[0] if lines else "Untitled"
    body = " ".join(lines[1:]) if len(lines) > 1 else article_text
    sentences = _split_sentences(body)

    category = _guess_category(body)
    tone = "urgent" if re.search(r"breaking|urgent|alert", body, re.IGNORECASE) else "neutral"
    facts = sentences[:5]
    quotes = _extract_quotes(body)
    entities = _extract_entities(body)
    narrative_arc = {
        "setup": " ".join(sentences[:2]).strip(),
        "conflict": sentences[len(sentences) // 2] if sentences else "",
        "resolution": sentences[-1] if sentences else "",
    }

    analysis = AnalysisResult(
        headline=headline,
        category=category,
        tone=tone,
        facts=facts,
        quotes=quotes,
        entities=entities,
        narrative_arc=narrative_arc,
    )
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return analysis, metadata


def generate_video_script(analysis: AnalysisResult) -> Tuple[str, Dict[str, Any]]:
    hook = f"{analysis.headline}. Here are the key developments."
    body = " ".join(analysis.facts[:3])
    conclusion = "Read full article at HT.com."
    script = f"{hook} {body} {conclusion}".strip()
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return script, metadata


def generate_podcast_script(analysis: AnalysisResult) -> Tuple[str, Dict[str, Any]]:
    intro = f"Welcome to HT's quick briefing. Today: {analysis.headline}."
    middle = " ".join(analysis.facts)
    outro = "That's the update. Read full article at HT.com."
    script = f"{intro}\n\n{middle}\n\n{outro}"
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return script, metadata


def generate_social_posts(analysis: AnalysisResult) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    thread = [analysis.headline] + analysis.facts[:5]
    linkedin = "\n\n".join([analysis.headline] + analysis.facts)
    instagram = {
        "slides": [analysis.headline] + analysis.facts[:4],
        "caption": f"{analysis.headline} #HT #News",
    }
    facebook = " ".join(analysis.facts[:3])
    whatsapp = " ".join(analysis.facts[:2])
    posts = {
        "twitter_thread": thread[:7],
        "linkedin": linkedin,
        "instagram": instagram,
        "facebook": facebook,
        "whatsapp": whatsapp,
    }
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return posts, metadata


def generate_translation(analysis: AnalysisResult, article_text: str) -> Tuple[TranslationResult, Dict[str, Any]]:
    translated = _translate_with_argos(article_text)
    if translated:
        return TranslationResult(hindi_text=translated, notes="Argos Translate"), {
            "model": "argos_translate",
            "usage": {},
            "cost_usd": 0.0,
        }
    translated = "[Hindi placeholder] " + article_text
    metadata = {"model": "local_placeholder", "usage": {}, "cost_usd": 0.0}
    return TranslationResult(hindi_text=translated, notes="Offline placeholder"), metadata


def generate_seo_package(analysis: AnalysisResult) -> Tuple[SEOReport, Dict[str, Any]]:
    headline_variants = [
        analysis.headline,
        f"Explained: {analysis.headline}",
        f"What to know: {analysis.headline}",
        f"Top takeaways from {analysis.headline}",
        f"Why it matters: {analysis.headline}",
        f"5 key points on {analysis.headline}",
        f"Latest update: {analysis.headline}",
        f"All you need to know about {analysis.headline}",
        f"In depth: {analysis.headline}",
        f"HT report: {analysis.headline}",
    ]
    meta_descriptions = [
        f"{analysis.headline} - key highlights, context, and what it means for readers.",
        f"A quick breakdown of {analysis.headline} with impacts and next steps.",
        f"HT analysis of {analysis.headline}: facts, context, and what to watch next.",
    ]
    faqs = [
        {"question": f"What happened in {analysis.headline}?", "answer": analysis.facts[0] if analysis.facts else ""},
        {"question": "Why does it matter?", "answer": analysis.narrative_arc.get("conflict", "")},
        {"question": "What is the impact?", "answer": analysis.narrative_arc.get("resolution", "")},
        {"question": "Who is involved?", "answer": ", ".join(analysis.entities[:5])},
        {"question": "What happens next?", "answer": "Watch for official updates."},
    ]
    keywords = analysis.entities[:12]
    internal_links = [
        "HT Markets",
        "HT Policy",
        "HT Explainers",
    ]
    report = SEOReport(
        headline_variants=headline_variants,
        meta_descriptions=meta_descriptions,
        faqs=faqs,
        keywords=keywords,
        internal_links=internal_links,
    )
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return report, metadata


def verify_fact(fact: str, sources: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    verification = {
        "verified": False,
        "confidence": "low",
        "sources": [],
    }
    metadata = {"model": "local_heuristic", "usage": {}, "cost_usd": 0.0}
    return verification, metadata


def _split_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def _guess_category(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ["stock", "market", "ipo", "shares", "sebi"]):
        return "Markets"
    if any(word in lower for word in ["policy", "government", "ministry", "parliament"]):
        return "Policy"
    if any(word in lower for word in ["tech", "startup", "ai", "software"]):
        return "Technology"
    if any(word in lower for word in ["sport", "match", "cricket", "football"]):
        return "Sports"
    return "News"


def _extract_quotes(text: str) -> List[Dict[str, str]]:
    quotes = []
    for match in re.findall(r"\"([^\"]+)\"", text):
        quotes.append({"quote": match, "speaker": ""})
    return quotes[:5]


def _extract_entities(text: str) -> List[str]:
    candidates = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b", text)
    entities = []
    for candidate in candidates:
        if candidate in STOPWORDS:
            continue
        if candidate not in entities:
            entities.append(candidate)
    return entities[:12]


def _translate_with_argos(text: str) -> str | None:
    if os.getenv("USE_ARGOS_TRANSLATE", "0").lower() not in {"1", "true", "yes"}:
        return None
    try:
        import argostranslate.package  # type: ignore
        import argostranslate.translate  # type: ignore

        installed_languages = argostranslate.translate.get_installed_languages()
        from_lang = next((lang for lang in installed_languages if lang.code == "en"), None)
        to_lang = next((lang for lang in installed_languages if lang.code == "hi"), None)
        if not from_lang or not to_lang:
            return None
        translation = from_lang.get_translation(to_lang)
        return translation.translate(text)
    except Exception:
        return None
