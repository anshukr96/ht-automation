from typing import Tuple


class ValidationError(ValueError):
    pass


def validate_article(text: str) -> Tuple[str, str]:
    cleaned = text.strip()
    if not cleaned:
        raise ValidationError("Article text is empty")

    words = cleaned.split()
    word_count = len(words)
    if word_count < 200 or word_count > 10000:
        raise ValidationError("Article must be between 200 and 10,000 words")

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValidationError("Article must include a headline and body")

    headline = lines[0]
    body = "\n".join(lines[1:]).strip()
    if len(body.split()) < 50:
        raise ValidationError("Article body is too short")

    return headline, body
