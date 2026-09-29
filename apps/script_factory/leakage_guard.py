"""Story Bible Leakage Guard for Script Factory V1.3.

Detects and eliminates mechanical database phrasing, prompt leakage,
and metadata contamination in spoken voiceover narration.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from apps.script_factory.models import FullScript, ScriptSegment

logger = logging.getLogger("VieNeu.StoryBibleLeakageGuard")

# Strict blacklist of mechanical / prompt / database leakage phrases
LEAKAGE_PATTERNS = [
    r"đáng chú ý,?\s*chi tiết liên quan đến",
    r"được xác định là",
    r"nội dung cốt lõi của bước ngoặt",
    r"nội dung gốc rễ của bước ngoặt",
    r"nguồn gốc của vật chứng chính",
    r"nguồn gốc xác thực",
    r"mối quan hệ giữa hai người chính là",
    r"toàn bộ số tiền liên đới được xác định",
    r"thời gian sự việc kéo dài tròn",
    r"địa điểm hiện tại của bạn thân",
    r"địa điểm hiện tại của",
    r"thông tin chi tiết về tài sản được tìm thấy",
    r"theo hồ sơ lưu trữ",
    r"theo story bible",
    r"story_bible",
    r"fact_id",
    r"fact_\d{3}",
    r"delivery_profile",
    r"audience_address",
    r"bước ngoặt 1 được xác định",
    r"bước ngoặt 2 được xác định",
    r"bí mật được xác định là",
]


@dataclass
class LeakageViolation:
    violation_code: str  # "STORY_BIBLE_LEAKAGE"
    segment_id: str
    matched_pattern: str
    excerpt: str
    severity: str  # Always "CRITICAL"
    message: str
    recommended_action: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StoryBibleLeakageGuard:
    """Audits script segments for database/prompt leakage contamination."""

    def __init__(self, patterns: Optional[List[str]] = None):
        self.patterns = patterns or LEAKAGE_PATTERNS
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.patterns]

    def check_segment(self, segment: ScriptSegment) -> List[LeakageViolation]:
        """Checks a single segment text for leakage patterns."""
        text = segment.text.strip()
        violations: List[LeakageViolation] = []

        for pattern, regex in zip(self.patterns, self._compiled):
            match = regex.search(text)
            if match:
                matched_str = match.group(0)
                excerpt = self._extract_excerpt(text, match.start(), match.end())
                violations.append(LeakageViolation(
                    violation_code="STORY_BIBLE_LEAKAGE",
                    segment_id=segment.id,
                    matched_pattern=pattern,
                    excerpt=excerpt,
                    severity="CRITICAL",
                    message=(
                        f"Phát hiện rò rỉ ngôn ngữ database/prompt ('{matched_str}') "
                        f"tại phân đoạn [{segment.id}]."
                    ),
                    recommended_action=(
                        "Viết lại câu văn theo phong cách kể chuyện tự nhiên của MC tài liệu, "
                        "loại bỏ hoàn toàn các cấu trúc từ ngữ khai báo máy móc."
                    ),
                ))

        return violations

    def audit_script(self, script: FullScript) -> List[LeakageViolation]:
        """Audits all segments in a script."""
        all_violations: List[LeakageViolation] = []
        for seg in script.segments:
            v_list = self.check_segment(seg)
            all_violations.extend(v_list)
        return all_violations

    def clean_text_from_leakage(self, text: str) -> str:
        """Removes known mechanical injection clauses from text while preserving narrative context."""
        cleaned = text
        # If segment contains appended 'Đáng chú ý, chi tiết liên quan đến', strip to end
        cleaned = re.sub(r"\s*Đáng chú ý,?\s*chi tiết liên quan đến.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"\s*Mối quan hệ giữa hai người chính là.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*Toàn bộ số tiền liên đới được xác định.*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*Thời gian sự việc kéo dài tròn.*$", "", cleaned, flags=re.IGNORECASE)
        
        # Additional cleanup for isolated leakage patterns
        injection_cleaners = [
            r"Đáng chú ý,?\s*chi tiết liên quan đến.*?(?=\.\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ]|\.$)",
            r"Nội dung cốt lõi của Bước ngoặt.*?(?=\.\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ]|\.$)",
            r"Nội dung gốc rễ của Bước ngoặt.*?(?=\.\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ]|\.$)",
            r"được xác định là.*?(?=\.\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ]|\.$)",
        ]
        for pattern in injection_cleaners:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Normalize whitespace and double punctuation
        cleaned = re.sub(r"\.\s*\.", ".", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned

    def _extract_excerpt(self, full_text: str, start_idx: int, end_idx: int, window: int = 60) -> str:
        start = max(0, start_idx - window // 2)
        end = min(len(full_text), end_idx + window // 2)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(full_text) else ""
        return f"{prefix}{full_text[start:end]}{suffix}"
