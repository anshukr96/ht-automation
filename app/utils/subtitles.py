import re
from typing import List, Tuple


def build_srt(text: str, *, max_words: int = 10, seconds_per_chunk: float = 3.5) -> str:
    words = re.findall(r"\S+", text)
    chunks: List[List[str]] = []
    for idx in range(0, len(words), max_words):
        chunks.append(words[idx : idx + max_words])

    lines: List[str] = []
    current = 0.0
    for index, chunk in enumerate(chunks, start=1):
        start = current
        end = current + seconds_per_chunk
        lines.append(str(index))
        lines.append(f"{_format_time(start)} --> {_format_time(end)}")
        lines.append(" ".join(chunk))
        lines.append("")
        current = end
    return "\n".join(lines).strip() + "\n"


def _format_time(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    total = int(seconds)
    hrs = total // 3600
    mins = (total % 3600) // 60
    secs = total % 60
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"
