"""Decode one complete AI JSON document without consuming trailing commentary."""
import json
import re
from typing import Any, Optional


def parse_json_response(raw: str) -> Optional[Any]:
    text = str(raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    starts = [position for position in (text.find("{"), text.find("[")) if position >= 0]
    if not starts:
        return None
    # Do not salvage a nested fragment from a truncated outer document.
    start = min(starts)
    for strict in (True, False):
        try:
            value, _ = json.JSONDecoder(strict=strict).raw_decode(text, start)
            return value if isinstance(value, (dict, list)) else None
        except ValueError:
            pass
    return None
