"""Spoiler Timing Guard for Script Factory V1.3.

Prevents premature reveals, story spoilers, and narrative pacing collapses.
Ensures that secrets and twists mapped in InformationReleaseMap remain strictly
concealed until their designated narrative act and segment range.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.information_release_map import InformationReleaseMap, InformationReleaseRule
from apps.script_factory.models import FullScript, ScriptSegment

logger = logging.getLogger("VieNeu.SpoilerTimingGuard")


@dataclass
class SpoilerViolation:
    violation_code: str  # "BLOCKED_PREMATURE_REVEAL"
    segment_id: str
    fact_id: str
    fact_type: str
    earliest_allowed_segment: int
    matched_term: str
    excerpt: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    message: str
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SpoilerTimingGuard:
    """Audits script segments against an InformationReleaseMap."""

    def __init__(self, release_map: InformationReleaseMap, known_setup_entities: Optional[Set[str]] = None):
        self.release_map = release_map
        self.setup_entities = set(known_setup_entities or [])
        # Auto-collect entities from SETUP rules so setup characters are not falsely marked as spoilers
        for r in release_map.rules:
            if r.fact_type == "SETUP":
                for e in r.key_entities:
                    self.setup_entities.add(e.lower())
        # Standard narrator and character baseline
        for g in ["minh", "hùng", "mai", "lan", "nam", "linh", "người", "khán giả"]:
            self.setup_entities.add(g)

    def check_segment(self, segment: ScriptSegment) -> List[SpoilerViolation]:
        """Checks a single segment for premature reveals."""
        try:
            seg_num = int(segment.id)
        except ValueError:
            return []

        text = segment.text.strip()
        text_lower = text.lower()
        violations: List[SpoilerViolation] = []

        for rule in self.release_map.rules:
            if seg_num < rule.earliest_allowed_segment:
                # Check for premature exposure of sensitive facts
                if rule.fact_type in ["REVEAL_1", "REVEAL_2"]:
                    # 1. Distinctive proper nouns or specific location/entity
                    for ent in rule.key_entities:
                        ent_lower = ent.lower()
                        # Only trigger on specific entities (>3 chars, not generic common words)
                        if len(ent_lower) > 3 and ent_lower in text_lower:
                            # Avoid false positives if entity was already introduced as setup character
                            if ent_lower in self.setup_entities:
                                continue
                            excerpt = self._extract_excerpt(text, ent_lower)
                            violations.append(SpoilerViolation(
                                violation_code="BLOCKED_PREMATURE_REVEAL",
                                segment_id=segment.id,
                                fact_id=rule.fact_id,
                                fact_type=rule.fact_type,
                                earliest_allowed_segment=rule.earliest_allowed_segment,
                                matched_term=ent,
                                excerpt=excerpt,
                                severity=rule.sensitivity_level,
                                message=(
                                    f"Phân đoạn [{segment.id}] làm lộ tình tiết của {rule.fact_type} ('{ent}') "
                                    f"trước phân đoạn cho phép (Tối thiểu phân đoạn [{rule.earliest_allowed_segment:03d}])."
                                ),
                                recommended_action=(
                                    f"Xóa bỏ hoặc chuyển tình tiết liên quan đến '{ent}' về đúng vị trí cao trào "
                                    f"(từ phân đoạn {rule.earliest_allowed_segment} trở đi)."
                                ),
                            ))
                            break

                    # 2. Check for core truth phrases
                    val_lower = rule.target_value.lower()
                    if "xây nhà tình thương" in val_lower and "nhà tình thương" in text_lower:
                        violations.append(SpoilerViolation(
                            violation_code="BLOCKED_PREMATURE_REVEAL",
                            segment_id=segment.id,
                            fact_id=rule.fact_id,
                            fact_type=rule.fact_type,
                            earliest_allowed_segment=rule.earliest_allowed_segment,
                            matched_term="nhà tình thương",
                            excerpt=self._extract_excerpt(text, "nhà tình thương"),
                            severity="CRITICAL",
                            message=f"Lộ mục đích cốt lõi ({rule.fact_type}) ở phân đoạn [{segment.id}].",
                            recommended_action="Chỉ được hé lộ mục đích từ thiện/nhà tình thương ở Act 8/9.",
                        ))
                elif rule.fact_type == "INVESTIGATION":
                    for ent in rule.key_entities:
                        ent_lower = ent.lower()
                        if len(ent_lower) > 4 and ent_lower in text_lower:
                            excerpt = self._extract_excerpt(text, ent_lower)
                            violations.append(SpoilerViolation(
                                violation_code="BLOCKED_PREMATURE_REVEAL",
                                segment_id=segment.id,
                                fact_id=rule.fact_id,
                                fact_type=rule.fact_type,
                                earliest_allowed_segment=rule.earliest_allowed_segment,
                                matched_term=ent,
                                excerpt=excerpt,
                                severity="HIGH",
                                message=(
                                    f"Phân đoạn [{segment.id}] sớm đưa ra kết quả điều tra '{ent}' "
                                    f"trước phân đoạn [{rule.earliest_allowed_segment:03d}]."
                                ),
                                recommended_action="Giữ cho quá trình điều tra phát triển dần, không đưa kết quả sớm.",
                            ))
                            break

        return violations

    def audit_script(self, script: FullScript) -> List[SpoilerViolation]:
        """Audits all segments in a script and aggregates violations."""
        all_violations: List[SpoilerViolation] = []
        for seg in script.segments:
            v_list = self.check_segment(seg)
            all_violations.extend(v_list)
        return all_violations

    def _extract_excerpt(self, full_text: str, match_term: str, window: int = 60) -> str:
        idx = full_text.lower().find(match_term.lower())
        if idx == -1:
            return full_text[:100] + ("..." if len(full_text) > 100 else "")
        start = max(0, idx - window // 2)
        end = min(len(full_text), idx + len(match_term) + window // 2)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(full_text) else ""
        return f"{prefix}{full_text[start:end]}{suffix}"
