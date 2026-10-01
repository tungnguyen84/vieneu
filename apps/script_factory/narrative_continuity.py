"""Deterministic continuity checks for multi-part long-form scripts."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Set


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").lower())
    return "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    ).replace("đ", "d")


_STOP_WORDS = {
    _ascii_fold(word)
    for word in (
        "của và là có đã được trong một những cho với khi này đó anh chị cô ông bà "
        "họ mình chúng ta nhưng rồi vẫn cũng về từ như rất đang sẽ không thì mà chỉ lại "
        "để đến ra vào trên dưới sau trước qua vì nên nơi theo từng mỗi người điều câu chuyện"
    ).split()
}


def _segment_text(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("text", "") or "")
    return str(getattr(segment, "text", "") or "")


def _content_tokens(text: str) -> Set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _ascii_fold(text))
        if len(token) >= 3 and token not in _STOP_WORDS
    }


def find_repeated_narrative_block(
    segments: Sequence[Any],
    *,
    window_size: int = 4,
    min_gap: int = 8,
    similarity_threshold: float = 0.56,
    min_common_tokens: int = 16,
) -> Optional[Dict[str, Any]]:
    """Find the strongest distant block that retells the same sequence of events.

    The score uses overlap against the smaller window. This catches a compressed
    retelling in Part 2 while avoiding ordinary callbacks to a single clue.
    Returned indexes are zero-based and the end indexes are exclusive.
    """
    if len(segments) < (window_size * 2 + min_gap):
        return None

    windows: List[Set[str]] = []
    for start in range(len(segments) - window_size + 1):
        tokens: Set[str] = set()
        for segment in segments[start : start + window_size]:
            tokens.update(_content_tokens(_segment_text(segment)))
        windows.append(tokens)

    best: Optional[Dict[str, Any]] = None
    for first_start, first_tokens in enumerate(windows):
        second_min = first_start + window_size + min_gap
        for second_start in range(second_min, len(windows)):
            second_tokens = windows[second_start]
            if not first_tokens or not second_tokens:
                continue
            common = first_tokens & second_tokens
            score = len(common) / max(1, min(len(first_tokens), len(second_tokens)))
            if score < similarity_threshold or len(common) < min_common_tokens:
                continue
            # Shared topic vocabulary is not a replay of a sequence. Require
            # several corresponding events in the same order; otherwise a
            # reflective ending can be mistaken for the investigation itself.
            matching_events = 0
            for offset in range(window_size):
                earlier = _content_tokens(_segment_text(segments[first_start + offset]))
                later = _content_tokens(_segment_text(segments[second_start + offset]))
                shared = earlier & later
                if len(shared) >= 4 and len(shared) / max(1, min(len(earlier), len(later))) >= similarity_threshold:
                    matching_events += 1
            if matching_events < max(2, window_size - 1):
                continue
            candidate = {
                "first_start": first_start,
                "first_end": first_start + window_size,
                "second_start": second_start,
                "second_end": second_start + window_size,
                "score": round(score, 3),
                "common_terms": sorted(common)[:24],
            }
            if best is None or candidate["score"] > best["score"]:
                best = candidate
    return best


def has_repeated_narrative_block(segments: Sequence[Any]) -> bool:
    return find_repeated_narrative_block(segments) is not None
