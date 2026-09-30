"""Structured Topic Intent and Adherence Engine for Script Factory.

Enforces USER TOPIC / USER PREMISE as an authoritative hard generation constraint:
USER TOPIC / USER PREMISE
        ↓ HARD CONSTRAINT
SERIES BIBLE
        ↓ STYLE + FORMAT CONSTRAINT
NOVELTY ENGINE
        ↓ VARIATION
IDEA GENERATOR
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("VieNeu.TopicIntent")


@dataclass
class TopicIntent:
    """Structured representation of a user's topic to prevent semantic drift."""
    original_topic: str
    primary_theme: str
    context: str
    central_conflict: str
    required_semantic_elements: List[str] = field(default_factory=list)
    optional_elements: List[str] = field(default_factory=list)
    forbidden_drift: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TopicIntent:
        if not data:
            return cls(
                original_topic="",
                primary_theme="",
                context="",
                central_conflict="",
            )
        return cls(
            original_topic=data.get("original_topic", ""),
            primary_theme=data.get("primary_theme", ""),
            context=data.get("context", ""),
            central_conflict=data.get("central_conflict", ""),
            required_semantic_elements=data.get("required_semantic_elements", []),
            optional_elements=data.get("optional_elements", []),
            forbidden_drift=data.get("forbidden_drift", []),
        )

    def to_prompt_constraint(self) -> str:
        """Builds an authoritative prompt constraint block for AI models."""
        req_bullets = "\n".join(f"  - {el}" for el in self.required_semantic_elements) if self.required_semantic_elements else "  - Bám sát chủ đề chính"
        opt_bullets = "\n".join(f"  - {el}" for el in self.optional_elements) if self.optional_elements else "  - Các chi tiết đời thực liên quan"
        forbid_bullets = "\n".join(f"  - KHÔNG biến tướng sang: {el}" for el in self.forbidden_drift) if self.forbidden_drift else "  - Không biến tướng sang các chủ đề ngẫu nhiên khác"

        return (
            f"=== CHỦ ĐỀ BẮT BUỘC TỪ NGƯỜI DÙNG (AUTHORITATIVE USER TOPIC) ===\n"
            f"Chủ đề gốc của người dùng: \"{self.original_topic}\"\n"
            f"- Chủ đề chính (Primary Theme): {self.primary_theme}\n"
            f"- Bối cảnh bắt buộc (Context): {self.context}\n"
            f"- Xung đột trung tâm (Central Conflict): {self.central_conflict}\n\n"
            f"YẾU TỐ BẮT BUỘC PHẢI XUẤT HIỆN TRONG TẤT CẢ Ý TƯỞNG (REQUIRED ELEMENTS):\n"
            f"{req_bullets}\n\n"
            f"YẾU TỐ GỢI Ý MỞ RỘNG (OPTIONAL CONTEXT ELEMENTS):\n"
            f"{opt_bullets}\n\n"
            f"CÁC HƯỚNG BỊ NGHIÊM CẤM BIẾN TƯỚNG (FORBIDDEN TOPIC DRIFT):\n"
            f"{forbid_bullets}\n\n"
            f"QUY TẮC ĐA DẠNG HÓA Ý TƯỞNG (DIVERSITY WITHOUT DRIFT):\n"
            f"- Người dùng là người quyết định đề tài. Tuyệt đối KHÔNG thay thế bằng các chủ đề mặc định của Series Bible (như bí mật thừa kế, tìm cha thất lạc, con nuôi...) trừ khi chính chủ đề người dùng yêu cầu.\n"
            f"- Sự đa dạng giữa các ý tưởng phải đến từ: nhân vật khác nhau, chứng cứ khác nhau, động cơ khác nhau, hoàn cảnh khác nhau, nhận định sai lầm khác nhau, cơ chế vạch trần khác nhau và hệ quả cảm xúc khác nhau.\n"
            f"- Tất cả các ý tưởng được sinh ra PHẢI giữ vững chủ đề cốt lõi trên.\n"
            f"================================================================"
        )

    def calculate_adherence_score(self, idea_or_text: Any) -> float:
        """Calculates adherence score (0-100) of an idea against this TopicIntent."""
        if not self.original_topic.strip():
            return 100.0

        if isinstance(idea_or_text, dict):
            text_blocks = [
                idea_or_text.get("title", ""),
                idea_or_text.get("working_title", ""),
                idea_or_text.get("hook", ""),
                idea_or_text.get("premise", ""),
                idea_or_text.get("central_secret", ""),
                idea_or_text.get("core_mystery", ""),
                idea_or_text.get("mystery_question", ""),
                idea_or_text.get("false_lead", ""),
                idea_or_text.get("reveal_1", ""),
                idea_or_text.get("reveal_2", ""),
                idea_or_text.get("possible_reveal", ""),
                idea_or_text.get("emotional_payoff", ""),
            ]
            full_text = " ".join(t for t in text_blocks if isinstance(t, str)).lower()
        elif hasattr(idea_or_text, "to_dict"):
            d = idea_or_text.to_dict()
            full_text = " ".join(str(v) for v in d.values() if isinstance(v, str)).lower()
        else:
            full_text = str(idea_or_text).lower()

        score = 70.0  # Base starting score

        # 1. Primary theme presence (+15)
        if self.primary_theme:
            theme_phrases = [w.strip() for w in re.split(r"[,/|;]|\bvà\b", self.primary_theme.lower()) if len(w.strip()) >= 3]
            theme_kw = [w.strip() for w in re.split(r"[^\w]+", self.primary_theme.lower()) if len(w.strip()) >= 3]
            theme_matches = sum(1 for tw in set(theme_phrases + theme_kw) if tw in full_text)
            if theme_matches > 0:
                score += min(15.0, 10.0 + theme_matches * 2.0)
            else:
                score -= 25.0

        # 2. Context presence (+10)
        if self.context:
            context_phrases = [w.strip() for w in re.split(r"[,/|;]|\bvà\b", self.context.lower()) if len(w.strip()) >= 3]
            context_kw = [w.strip() for w in re.split(r"[^\w]+", self.context.lower()) if len(w.strip()) >= 3]
            context_matches = sum(1 for cw in set(context_phrases + context_kw) if cw in full_text)
            if context_matches > 0:
                score += min(10.0, 7.0 + context_matches * 1.5)
            else:
                score -= 15.0

        # 3. Required semantic elements (+15 max)
        if self.required_semantic_elements:
            matched_req = 0
            for req in self.required_semantic_elements:
                req_lower = req.lower()
                kw_list = [w for w in re.split(r"[^\w]+", req_lower) if len(w) >= 3]
                if any(w in full_text for w in kw_list) or req_lower in full_text:
                    matched_req += 1
            ratio = matched_req / max(1, len(self.required_semantic_elements))
            score += ratio * 15.0
            if ratio < 0.5:
                score -= 15.0

        # 4. Optional context elements bonus (+5 max)
        if self.optional_elements:
            matched_opt = sum(1 for opt in self.optional_elements if opt.lower() in full_text)
            score += min(5.0, matched_opt * 1.5)

        # 5. Forbidden drift penalty (up to -40)
        drift_hits = []
        for drift in self.forbidden_drift:
            drift_lower = drift.lower().strip()
            if drift_lower and drift_lower in full_text:
                drift_hits.append(drift_lower)

        if drift_hits:
            score -= min(40.0, len(drift_hits) * 20.0)

        # Ensure within 0.0 - 100.0
        return max(0.0, min(100.0, round(score, 1)))


def extract_topic_intent(topic_text: str, provider: Optional[Any] = None) -> TopicIntent:
    """
    Parses a user topic/premise into a structured TopicIntent.
    Uses rule-based semantic analysis with fallback, or AI provider if available.
    """
    clean_topic = topic_text.strip()
    if not clean_topic:
        return TopicIntent(
            original_topic="",
            primary_theme="Bí mật và uẩn khúc đời thường",
            context="Gia đình và xã hội",
            central_conflict="Uẩn khúc tâm lý hoặc mâu thuẫn quan hệ",
            required_semantic_elements=["bí mật", "uẩn khúc"],
            optional_elements=["người thân", "kỷ vật", "sự thật"],
            forbidden_drift=["chủ đề phi thực tế", "yếu tố ma mị siêu nhiên"],
        )

    # Heuristic Rule-Based Semantic Engine (Extensible across all topics)
    topic_lower = clean_topic.lower()

    # Domain 1: Infidelity / Betrayal (Ngoại tình / Phản bội)
    if any(k in topic_lower for k in ["ngoại tình", "tiểu tam", "người thứ ba", "bồ nhí", "phản bội tình cảm", "vụng trộm", "gian dâm"]):
        is_workplace = any(k in topic_lower for k in ["công sở", "nơi làm việc", "công ty", "văn phòng", "đồng nghiệp", "sếp", "cấp trên", "đối tác"])
        primary = "Ngoại tình / Phản bội tình cảm trong hôn nhân hoặc quan hệ"
        ctx = "Môi trường công sở / Văn phòng / Công ty" if is_workplace else "Đời sống quan hệ / Gia đình"
        conflict = "Sự phản bội lòng tin và nguy cơ đổ vỡ gia đình/sự nghiệp"
        req = [
            "ngoại tình" if not is_workplace else "ngoại tình công sở",
            "mối quan hệ vụng trộm",
            "chứng cứ hoặc dấu hiệu bất thường"
        ]
        if is_workplace:
            req.extend(["yếu tố liên quan đến công việc hoặc đồng nghiệp"])
        opt = [
            "tin nhắn bí mật", "chuyến công tác", "làm thêm giờ bất thường",
            "tài khoản chi tiêu ẩn", "đồng nghiệp cùng cơ quan", "người bạn đời nghi ngờ",
            "nhân viên / cấp dưới", "đối tác làm ăn", "áp lực công việc"
        ]
        drift = [
            "thừa kế gia tài không liên quan", "bí mật con nuôi không liên quan",
            "tìm kiếm người cha mất tích không liên quan", "mâu thuẫn đất đai dòng họ xa xưa"
        ]
        return TopicIntent(
            original_topic=clean_topic,
            primary_theme=primary,
            context=ctx,
            central_conflict=conflict,
            required_semantic_elements=req,
            optional_elements=opt,
            forbidden_drift=drift,
        )

    # Domain 2: Workplace Mystery / Corporate Fraud (Bí mật nơi làm việc / Kinh tế / Gian lận)
    elif any(k in topic_lower for k in ["công sở", "công ty", "doanh nghiệp", "rút ruột", "tham ô", "quỹ đen", "lừa đảo công ty", "chèn ép"]):
        return TopicIntent(
            original_topic=clean_topic,
            primary_theme="Gian lận hoặc mâu thuẫn lợi ích nơi làm việc",
            context="Doanh nghiệp / Môi trường công sở / Đồng nghiệp",
            central_conflict="Cuộc đối đầu giữa đạo đức nghề nghiệp và lợi ích tài chính",
            required_semantic_elements=["môi trường công sở hoặc doanh nghiệp", "sai phạm hoặc bí mật nghề nghiệp", "chứng từ hoặc hồ sơ nội bộ"],
            optional_elements=["đồng nghiệp", "quản lý", "kế toán", "báo cáo tài chính", "hợp đồng giả", "áp lực thăng tiến"],
            forbidden_drift=["chuyện tình cảm gia đình thuần túy không gắn liền công việc", "tranh chấp thừa kế dòng họ"],
        )

    # Domain 3: Missing Person / Hidden Identity / War Veteran (Danh tính / Mất tích / Đồng đội)
    elif any(k in topic_lower for k in ["danh tính", "đổi tên", "giả danh", "đồng đội", "chiến trường", "mất tích", "hy sinh"]):
        return TopicIntent(
            original_topic=clean_topic,
            primary_theme="Bí mật danh tính và sự hy sinh thay thế",
            context="Quá khứ chiến tranh / Hồ sơ lưu trữ / Gia đình cựu chiến binh",
            central_conflict="Nghĩa vụ bảo vệ danh dự đồng đội đối đầu với khao khát được sống thật",
            required_semantic_elements=["đánh tráo hoặc gánh vác danh tính", "kỷ vật hoặc hồ sơ quá khứ", "nguyên nhân bắt buộc"],
            optional_elements=["thẻ bài", "giấy báo tử", "đồng đội", "bức ảnh cũ", "cơ quan lưu trữ địa phương"],
            forbidden_drift=["ngoại tình công sở", "lừa đảo thương mại", "tranh giành đất đai hiện đại"],
        )

    # Domain 4: Inheritance / Wills / Property (Thừa kế / Di chúc / Tài sản)
    elif any(k in topic_lower for k in ["thừa kế", "di chúc", "chia đất", "sổ đỏ", "tài sản gia đình"]):
        return TopicIntent(
            original_topic=clean_topic,
            primary_theme="Tranh chấp và bí mật phân chia tài sản thừa kế",
            context="Gia tộc / Anh chị em ruột / Nhà đất hương hỏa",
            central_conflict="Lòng tham vật chất thử thách tình cảm gia đình",
            required_semantic_elements=["di chúc hoặc tài sản thừa kế", "uẩn khúc trong phân chia", "chứng cứ pháp lý hoặc thỏa thuận ngầm"],
            optional_elements=["sổ đỏ", "người con thứ", "lời dặn trước khi mất", "hợp đồng tặng cho"],
            forbidden_drift=["mối quan hệ công sở không liên quan", "vụ án hình sự bạo lực"],
        )

    # Domain 5: Generic / Custom Extractor (Universal Fallback)
    words = [w for w in re.split(r"[\s,.-]+", clean_topic) if len(w) >= 2]
    keywords = words[:6]
    return TopicIntent(
        original_topic=clean_topic,
        primary_theme=clean_topic,
        context=f"Bối cảnh xoay quanh đề tài '{clean_topic}'",
        central_conflict=f"Mâu thuẫn và bí mật nảy sinh từ '{clean_topic}'",
        required_semantic_elements=keywords,
        optional_elements=["nhân vật trực tiếp liên quan", "chứng cứ xác minh", "hệ quả cảm xúc"],
        forbidden_drift=["chủ đề gia đình chung chung không liên quan đến đề tài người dùng", "sự việc hư cấu siêu nhiên"],
    )
