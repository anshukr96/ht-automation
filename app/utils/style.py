import json
import os
from typing import Any, Dict

STYLE_PATH = os.path.join(os.path.dirname(__file__), "..", "storage", "ht_style_guide.json")


def load_style_guide() -> Dict[str, Any]:
    if not os.path.exists(STYLE_PATH):
        return {}
    with open(STYLE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)
