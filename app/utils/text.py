import math
import re
from typing import List


def _count_syllables(word: str) -> int:
    word = word.lower()
    word = re.sub(r"[^a-z]", "", word)
    if not word:
        return 0
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def flesch_reading_ease(text: str) -> float:
    sentences = re.split(r"[.!?]+", text)
    sentences = [s for s in sentences if s.strip()]
    words = re.findall(r"\b[\w'-]+\b", text)
    if not sentences or not words:
        return 0.0
    syllables = sum(_count_syllables(word) for word in words)
    words_count = len(words)
    sentences_count = len(sentences)
    asl = words_count / sentences_count
    asw = syllables / words_count
    score = 206.835 - (1.015 * asl) - (84.6 * asw)
    return round(max(min(score, 100.0), 0.0), 2)


def find_prohibited_phrases(text: str, phrases: List[str]) -> List[str]:
    lowered = text.lower()
    return [phrase for phrase in phrases if phrase.lower() in lowered]
