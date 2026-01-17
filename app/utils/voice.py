import os
from typing import Optional


def get_anchor_gender(avatar_path: Optional[str]) -> str:
    configured = os.getenv("HT_ANCHOR_GENDER", "").strip().lower()
    if configured in {"female", "male"}:
        return configured
    if not avatar_path:
        return "male"
    filename = os.path.basename(avatar_path).lower()
    if any(token in filename for token in ("female", "woman", "lady", "girl")):
        return "female"
    return "male"


def select_voice(language: str, gender: str) -> str:
    lang = language.lower()
    gender = gender.lower()
    if lang.startswith("hi"):
        if gender == "female":
            return os.getenv("LOCAL_HINDI_FEMALE_VOICE", os.getenv("LOCAL_HINDI_VOICE", "Lekha"))
        return os.getenv("LOCAL_HINDI_MALE_VOICE", os.getenv("LOCAL_HINDI_VOICE", "Aman"))
    if gender == "female":
        return os.getenv("LOCAL_FEMALE_VOICE", "Samantha")
    return os.getenv("LOCAL_TTS_VOICE", "Aman")
