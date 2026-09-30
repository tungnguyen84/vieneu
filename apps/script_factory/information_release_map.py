"""Information Release Map Engine for Script Factory V1.3.

Enforces structural pacing and prevents premature revelation of secrets.
Maps every protected fact from the Story Bible / Fact Lock to its earliest allowed narration segment.

Rules:
- SETUP / TRIGGER / PREMISE facts: earliest_allowed_segment = 1 (Segments 1-15)
- ANOMALY / CLUES / INVESTIGATION facts: earliest_allowed_segment = 16-25 (Segments 16-60)
- REVEAL 1 (Climax 1 / First Major Twist): earliest_allowed_segment >= 61 (Segments 61-75)
- REVEAL 2 (Climax 2 / Core Hidden Truth / Emotional Payoff): earliest_allowed_segment >= 76 (Segments 76-90)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.script_factory.models import LockedFact, StoryBible

logger = logging.getLogger("VieNeu.InformationReleaseMap")


@dataclass
class InformationReleaseRule:
    fact_id: str
    fact_type: str  # "SETUP", "CLUE", "INVESTIGATION", "REVEAL_1", "REVEAL_2", "RESOLUTION"
    field: str
    description: str
    target_value: str
    earliest_allowed_segment: int
    latest_allowed_segment: Optional[int] = None
    forbidden_before_segment: int = 1
    key_entities: List[str] = field(default_factory=list)
    sensitivity_level: str = "HIGH"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InformationReleaseRule:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class InformationReleaseMap:
    episode_id: str
    total_segments: int = 90
    rules: List[InformationReleaseRule] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "total_segments": self.total_segments,
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> InformationReleaseMap:
        rules = [InformationReleaseRule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            episode_id=data.get("episode_id", ""),
            total_segments=data.get("total_segments", 90),
            rules=rules,
        )

    def save(self, output_path: str | Path) -> Path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return out_p

    @classmethod
    def load(cls, file_path: str | Path) -> InformationReleaseMap:
        with open(Path(file_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def extract_key_entities_from_text(text: str) -> List[str]:
    """Extracts distinctive names, places, and key phrases from fact description/value."""
    if not text:
        return []
    proper_nouns_raw = re.findall(r"\b[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ][a-zàáâãèéêìíòóôõùúăđĩũơưăạảấầẩẫậắằẳẵặẹẻẽềềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ][a-zàáâãèéêìíòóôõùúăđĩũơưăạảấầẩẫậắằẳẵặẹẻẽềềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+)*\b", text)
    
    stop_words = {
        "người", "bước", "nội", "thời", "toàn", "địa", "một", "bí", "khi", "sau", "trong",
        "theo", "và", "nhưng", "tại", "nếu", "để", "các", "những", "do", "từ", "cháu",
        "bạn", "hai", "ba", "bà", "ông", "anh", "chị", "em", "cô", "chú", "bác", "mẹ",
        "bố", "cha", "con", "chiếc", "cuộc", "sự", "việc", "điều", "đáng", "được",
        "bước ngoặt", "thông tin", "tài sản", "chi tiết", "quan hệ", "giải", "lời", "đáp",
        "thực sự", "bản chất", "lý do", "khoản", "tiền", "khoản tiền", "nợ", "phần",
        "năm", "ngày", "tháng", "đoạn", "trang", "hồi", "tập", "chương", "giấy", "hồ sơ",
        "chứng từ", "biên bản", "chân", "tướng", "chân tướng", "bước", "ngoặt", "manh",
        "mối", "bí mật", "sự thật", "tiết lộ", "phát hiện", "chứng cứ", "nhân chứng",
        "hồ sơ", "tài liệu", "cơ quan", "địa phương", "nguyên nhân", "bên dưới", "trên",
        "giấu", "chàng", "không", "biết", "hiểu", "thấy", "làm", "tìm", "gặp", "chọn",
        "nghĩ", "mang", "giữ", "đưa", "nhận", "gửi", "vợ", "chồng", "phụ nữ", "hàng xóm"
    }

    proper_nouns = []
    for pn in proper_nouns_raw:
        pn_clean = pn.strip()
        pn_low = pn_clean.lower()
        if pn_low not in stop_words and len(pn_clean) >= 3:
            # Don't add generic capitalized words that often appear at start of phrases
            if pn_low in ("chân", "bước", "manh", "sự", "điều", "người", "giấu", "chàng", "không", "chọn"):
                continue
            # For single words, require length >= 4 unless known name
            if " " not in pn_clean and len(pn_clean) < 4:
                continue
            proper_nouns.append(pn_clean)
    
    distinctive_terms = []
    lower = text.lower()
    distinctive_keywords = [
        "nhà tình thương", "trẻ mồ côi", "viện dưỡng lão", "con nuôi", "di chúc",
        "hồ sơ bệnh án", "tiết kiệm", "bảo lộc", "lâm đồng", "đổi tên", "giả giọng",
        "thân phận thật", "cha ruột", "mẹ ruột", "anh em sinh đôi",
        "quỹ chung", "bị lừa", "bể dầu",
        "cây khế", "gốc cây khế", "mộc lan", "nam định", "hải dương"
    ]
    for kw in distinctive_keywords:
        if kw in lower:
            distinctive_terms.append(kw)

    combined = list(dict.fromkeys(proper_nouns + distinctive_terms))
    return combined


def build_information_release_map(
    story_bible: StoryBible,
    fact_locks: Optional[List[Dict[str, Any] | LockedFact]] = None,
) -> InformationReleaseMap:
    """
    Constructs the Information Release Map enforcing:
    - Reveal 1 facts: Earliest segment >= 61
    - Reveal 2 facts: Earliest segment >= 76
    - Clues / Investigation: Earliest segment 16-25
    - Setup / Premise: Earliest segment 1-15
    """
    ep_id = story_bible.episode_id
    rules: List[InformationReleaseRule] = []

    facts: List[Dict[str, Any]] = []
    seen_ids = set()

    if fact_locks:
        for f in fact_locks:
            fd = f.to_dict() if isinstance(f, LockedFact) else dict(f)
            facts.append(fd)
            seen_ids.add(fd.get("fact_id", ""))

    for cf in story_bible.critical_facts:
        cfd = cf.to_dict() if isinstance(cf, LockedFact) else dict(cf)
        if cfd.get("fact_id") not in seen_ids:
            facts.append(cfd)
            seen_ids.add(cfd.get("fact_id", ""))

    if story_bible.reveal_1 and not any("reveal_1" in f.get("field", "") for f in facts):
        facts.append({
            "fact_id": "FACT_REVEAL_1_AUTO",
            "field": "reveal_1_truth",
            "value": story_bible.reveal_1,
            "description": "Nội dung cốt lõi của Bước ngoặt 1 (Reveal 1)",
            "status": "LOCKED",
        })
    if story_bible.reveal_2 and not any("reveal_2" in f.get("field", "") for f in facts):
        facts.append({
            "fact_id": "FACT_REVEAL_2_AUTO",
            "field": "reveal_2_truth",
            "value": story_bible.reveal_2,
            "description": "Nội dung gốc rễ của Bước ngoặt 2 (Reveal 2)",
            "status": "LOCKED",
        })

    for f in facts:
        f_id = f.get("fact_id", "FACT_UNKNOWN")
        field_name = f.get("field", "").lower()
        desc = f.get("description", "")
        desc_lower = desc.lower()
        val = f.get("value", "")
        val_lower = val.lower()

        if "reveal_2" in field_name or "bước ngoặt 2" in desc_lower or "twist_2" in field_name or "mục đích nhân văn" in desc_lower:
            f_type = "REVEAL_2"
            earliest = 76
            forbidden_before = 76
            sens = "CRITICAL"
        elif "reveal_1" in field_name or "bước ngoặt 1" in desc_lower or "twist_1" in field_name or "thân phận" in desc_lower:
            f_type = "REVEAL_1"
            earliest = 61
            forbidden_before = 61
            sens = "CRITICAL"
        elif "location_of_friend" in field_name or "viện dưỡng lão" in val_lower or "địa điểm hiện tại" in desc_lower:
            f_type = "INVESTIGATION"
            earliest = 20
            forbidden_before = 20
            sens = "MEDIUM"
        elif "property_details" in field_name or "sổ tiết kiệm" in val_lower or "mảnh đất" in val_lower:
            f_type = "CLUE"
            earliest = 16
            forbidden_before = 16
            sens = "MEDIUM"
        elif "clue" in field_name or "investigation" in field_name:
            f_type = "CLUE"
            earliest = 16
            forbidden_before = 16
            sens = "MEDIUM"
        elif "timeline" in field_name or "years" in field_name:
            f_type = "SETUP"
            earliest = 1
            forbidden_before = 1
            sens = "LOW"
        elif "relationship" in field_name:
            f_type = "SETUP"
            earliest = 1
            forbidden_before = 1
            sens = "LOW"
        elif "evidence_origin" in field_name or "vật chứng" in desc_lower:
            f_type = "SETUP"
            earliest = 1
            forbidden_before = 1
            sens = "LOW"
        else:
            if "bí mật cốt lõi" in desc_lower or "sự thật" in desc_lower:
                f_type = "REVEAL_1"
                earliest = 61
                forbidden_before = 61
                sens = "CRITICAL"
            else:
                f_type = "SETUP"
                earliest = 1
                forbidden_before = 1
                sens = "LOW"

        entities = extract_key_entities_from_text(f"{desc} {val}")
        rules.append(InformationReleaseRule(
            fact_id=f_id,
            fact_type=f_type,
            field=f.get("field", ""),
            description=desc,
            target_value=val,
            earliest_allowed_segment=earliest,
            latest_allowed_segment=90,
            forbidden_before_segment=forbidden_before,
            key_entities=entities,
            sensitivity_level=sens,
        ))

    return InformationReleaseMap(episode_id=ep_id, total_segments=90, rules=rules)
