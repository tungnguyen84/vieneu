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

    def evaluate_content_adherence(self, idea_or_text: Any, stage: str = "auto") -> Dict[str, Any]:
        """
        Deeply evaluates content adherence against this TopicIntent.
        Scores CENTRALITY, EVIDENCE COVERAGE, and REVEAL ALIGNMENT on actual generated content.
        Does NOT trust metadata or single keyword occurrences.
        """
        if not self.original_topic.strip():
            return {
                "score": 100.0,
                "topic_centrality_score": 100.0,
                "topic_evidence_coverage": 100.0,
                "topic_reveal_alignment": 100.0,
                "drift_detected": False,
                "drift_terms": [],
                "status": "PASS",
                "details": "No specific user topic constraint applied.",
            }

        # Extract text blocks depending on object type
        title_text = ""
        premise_text = ""
        clues_text = ""
        reveals_text = ""
        full_text = ""
        segments_texts: List[str] = []

        if isinstance(idea_or_text, dict):
            title_text = str(idea_or_text.get("title") or idea_or_text.get("working_title") or "")
            premise_text = " ".join(str(idea_or_text.get(k) or "") for k in ("hook", "premise", "central_secret", "core_mystery", "mystery_question", "secret"))
            clues_val = idea_or_text.get("clues") or []
            if isinstance(clues_val, list):
                clues_text = " ".join(str(c.get("clue", "") if isinstance(c, dict) else c) for c in clues_val)
            else:
                clues_text = str(clues_val)
            clues_text += " " + " ".join(str(idea_or_text.get(f"clue_{i}") or "") for i in range(1, 4))
            reveals_text = " ".join(str(idea_or_text.get(k) or "") for k in ("reveal_1", "reveal_2", "possible_reveal", "emotional_payoff", "reflection_theme"))
            
            # If dict represents FullScript with segments
            if "segments" in idea_or_text and isinstance(idea_or_text["segments"], list):
                segments_texts = [str(s.get("text", "")) for s in idea_or_text["segments"] if isinstance(s, dict)]
                full_text = " ".join(segments_texts)
                n_seg = len(segments_texts)
                if n_seg > 0:
                    premise_text = " ".join(segments_texts[:max(1, int(n_seg * 0.25))])
                    clues_text = " ".join(segments_texts[int(n_seg * 0.25):int(n_seg * 0.65)])
                    reveals_text = " ".join(segments_texts[int(n_seg * 0.65):])
            else:
                full_text = f"{title_text} {premise_text} {clues_text} {reveals_text}"

        elif hasattr(idea_or_text, "segments"):  # FullScript
            segments_texts = [s.text for s in getattr(idea_or_text, "segments", [])]
            full_text = " ".join(segments_texts)
            title_text = getattr(idea_or_text, "title", "")
            # Split roughly into acts if segments exist
            n_seg = len(segments_texts)
            if n_seg > 0:
                premise_text = " ".join(segments_texts[:max(1, int(n_seg * 0.25))])
                clues_text = " ".join(segments_texts[int(n_seg * 0.25):int(n_seg * 0.65)])
                reveals_text = " ".join(segments_texts[int(n_seg * 0.65):])

        elif hasattr(idea_or_text, "secret"):  # StoryBible
            title_text = getattr(idea_or_text, "title", "")
            premise_text = f"{getattr(idea_or_text, 'hook', '')} {getattr(idea_or_text, 'secret', '')} {getattr(idea_or_text, 'mystery_question', '')}"
            clues_data = getattr(idea_or_text, "structured_clues", []) or getattr(idea_or_text, "clues", []) or []
            clues_text = " ".join(str(c.get("clue", "") if isinstance(c, dict) else c) for c in clues_data)
            reveals_text = f"{getattr(idea_or_text, 'reveal_1', '')} {getattr(idea_or_text, 'reveal_2', '')} {getattr(idea_or_text, 'emotional_payoff', '')}"
            full_text = f"{title_text} {premise_text} {clues_text} {reveals_text}"

        elif hasattr(idea_or_text, "to_dict"):
            d = idea_or_text.to_dict()
            return self.evaluate_content_adherence(d, stage=stage)
        else:
            full_text = str(idea_or_text)
            premise_text = full_text[:len(full_text)//3]
            clues_text = full_text[len(full_text)//3: 2*len(full_text)//3]
            reveals_text = full_text[2*len(full_text)//3:]

        full_lower = full_text.lower()
        title_lower = title_text.lower()
        premise_lower = premise_text.lower()
        clues_lower = clues_text.lower()
        reveals_lower = reveals_text.lower()

        # Keywords for Primary Theme (require meaningful compound terms >= 4 chars or specific key terms)
        primary_phrases = [w.strip() for w in re.split(r"[,/|;]|\bvà\b", self.primary_theme.lower()) if len(w.strip()) >= 4]
        # Specific core keywords for theme
        primary_core = [w for w in [
            "ngoại tình", "tiểu tam", "người thứ ba", "bồ nhí", "phản bội", "vụng trộm", "gian dâm",
            "hai lòng", "người tình", "nhân tình", "lén lút qua lại", "bắt gian", "đánh ghen",
        ] if w in self.primary_theme.lower() or w in self.original_topic.lower()]
        if not primary_core:
            primary_core = [w.strip() for w in re.split(r"[,/|;]", self.primary_theme.lower()) if len(w.strip()) >= 4]
        primary_tokens = list(dict.fromkeys(primary_phrases + primary_core))

        # Keywords for Context (require meaningful compound terms)
        context_phrases = [w.strip() for w in re.split(r"[,/|;]|\bvà\b", self.context.lower()) if len(w.strip()) >= 4]
        # Include optional elements specified by topic intent (e.g. tin nhắn bí mật, đồng nghiệp, chuyến công tác)
        opt_tokens = [w.strip().lower() for w in self.optional_elements if len(w.strip()) >= 4]
        # Common workplace context terms if workplace is in context/topic
        workplace_terms = []
        if any(w in self.context.lower() or w in self.original_topic.lower() for w in ["công sở", "văn phòng", "công ty", "đồng nghiệp", "làm việc"]):
            workplace_terms = [
                "công sở", "văn phòng", "công ty", "đồng nghiệp", "sếp", "cấp trên", "cấp dưới",
                "nơi làm việc", "tăng ca", "làm thêm giờ", "công tác", "đối tác", "họp hành",
                "tin nhắn", "điện thoại", "khách sạn", "hẹn hò", "hợp đồng", "phòng làm việc",
                "ảnh", "chụp lén", "lịch họp", "sao kê", "tài chính", "dữ liệu", "camera", "máy tính",
                "báo cáo", "bảo vệ bí mật", "thương mại", "gián điệp", "mối quan hệ", "quan hệ"
            ]
        # Common family context terms if family is in context/topic
        family_terms = []
        if any(w in self.context.lower() or w in self.original_topic.lower() for w in ["gia đình", "người thân", "dòng họ", "bố mẹ", "vợ chồng", "con cái"]):
            family_terms = [
                "gia đình", "người thân", "bố", "mẹ", "ông", "bà", "con", "cháu", "hàng xóm",
                "quê", "nhà cũ", "căn nhà", "kỷ vật", "di vật", "thư từ", "ảnh cũ", "nhật ký", "cuốn sổ"
            ]
        # Core investigative evidence terms across Sau Cánh Cửa mystery stories
        investigative_terms = [
            "chứng từ", "hồ sơ", "giấy tờ", "phong bì", "chữ viết", "con dấu", "bức ảnh",
            "cuốn sổ", "nhật ký", "kỷ vật", "di vật", "nhân chứng", "hàng xóm", "tin nhắn",
            "cuộc gọi", "chìa khóa", "lưu trữ", "xác minh", "bằng chứng", "vật chứng", "lời khai", "biên bản"
        ]
        context_tokens = list(dict.fromkeys(context_phrases + opt_tokens + workplace_terms + family_terms + investigative_terms))

        # Required semantic tokens - keep as compound concepts
        req_tokens: List[str] = []
        for r in self.required_semantic_elements:
            r_lower = r.lower().strip()
            if len(r_lower) >= 4:
                req_tokens.append(r_lower)
        # Extract meaningful multi-word terms from required elements
        for r in self.required_semantic_elements:
            for term in ["ngoại tình", "vụng trộm", "tiểu tam", "người thứ ba", "đồng nghiệp", "công sở", "gian dâm", "phản bội"]:
                if term in r.lower():
                    req_tokens.append(term)
        req_tokens = list(dict.fromkeys(req_tokens))

        # ----------------------------------------------------
        # 1. TOPIC CENTRALITY SCORE (0 - 100)
        # Does the primary theme dominate throughout the story?
        # Extract meaningful constituent n-grams (bigrams and trigrams) and keywords from original_topic
        topic_words = [w for w in re.split(r"[\s,.-]+", self.original_topic.lower()) if w]
        stop_words_topic = {"cho", "một", "suốt", "từ", "được", "các", "những", "trong", "với", "về", "của", "và", "là", "có"}
        content_ngrams = []
        for i in range(len(topic_words) - 1):
            w1, w2 = topic_words[i], topic_words[i+1]
            if w1 not in stop_words_topic or w2 not in stop_words_topic:
                content_ngrams.append(f"{w1} {w2}")
            if i < len(topic_words) - 2:
                w3 = topic_words[i+2]
                content_ngrams.append(f"{w1} {w2} {w3}")
        content_words = [w for w in topic_words if len(w) >= 3 and w not in stop_words_topic and w not in ("người", "nhận", "phát", "hiện")]

        is_infidelity = any(k in self.original_topic.lower() for k in ["ngoại tình", "tiểu tam", "người thứ ba", "bồ nhí", "vụng trộm"])
        is_family = any(k in self.original_topic.lower() or k in self.primary_theme.lower() for k in ["gia đình", "người thân", "dòng họ", "cha mẹ", "bố mẹ", "con cái", "ruột thịt"])
        if is_infidelity:
            strict_theme_tokens = [
                "ngoại tình", "tiểu tam", "người thứ ba", "bồ nhí", "vụng trộm", "gian dâm",
                "nhân tình", "người tình", "lén lút", "lừa dối", "phản bội", "ly hôn", "ngoài luồng",
                "mối quan hệ tình cảm", "quan hệ tình cảm bí mật", "mối quan hệ bí mật",
                "vượt qua ranh giới đồng nghiệp", "không chung thủy", "che giấu mối quan hệ",
                # Shown rather than labelled: the writer prompt forbids naming the
                # affair outright, so centrality must also credit described behaviour.
                "hẹn hò", "thân mật", "qua lại với", "mối quan hệ với", "vượt mức đồng nghiệp",
                "vượt quá giới hạn", "quan hệ riêng tư", "cuộc hẹn riêng", "dối trá",
            ]
        elif is_family and not any(k in self.original_topic.lower() for k in ["gửi tiền", "cuộc gọi", "đã mất", "8 năm", "5 năm"]):
            strict_theme_tokens = list(dict.fromkeys(primary_tokens + ["gia đình", "người thân", "ruột thịt", "máu mủ", "mái ấm", "bố mẹ", "cha mẹ", "con cái", "ông bà", "anh em", "vợ chồng", "bí mật gia đình"]))
        else:
            strict_theme_tokens = list(dict.fromkeys([p for p in primary_tokens if len(p) <= 30] + content_ngrams + content_words))

        context_tokens = list(dict.fromkeys(context_tokens + content_ngrams + content_words))

        if segments_texts:
            # Multi-segment script evaluation
            # Count segments genuinely discussing the primary theme
            theme_hit_segments = 0
            for st in segments_texts:
                st_low = st.lower()
                # Exclude purely template leakage hits from counting towards valid theme presence
                cleaned_st = re.sub(r"bước ngoặt [12]:.*", "", st_low)
                cleaned_st = re.sub(r"manh mối [123]:.*", "", cleaned_st)
                if any(pt in cleaned_st for pt in strict_theme_tokens):
                    theme_hit_segments += 1
            
            seg_ratio = theme_hit_segments / max(1, len(segments_texts))
            # In a genuine story about this topic, theme compound terms should appear in at least 5-10+ segments
            if seg_ratio >= 0.08:
                centrality = 95.0
            elif seg_ratio >= 0.05:
                centrality = 80.0
            elif seg_ratio >= 0.03:
                centrality = 60.0
            elif theme_hit_segments >= 2:
                centrality = 30.0
            elif theme_hit_segments == 1:
                centrality = 10.0
            else:
                centrality = 0.0
        else:
            # Idea / StoryBible evaluation: check across title, premise, secret, clues, and reveals
            premise_occurrences = sum(1 for pt in strict_theme_tokens if pt in premise_lower)
            title_occurrences = sum(1 for pt in strict_theme_tokens if pt in title_lower)
            all_occurrences = sum(1 for pt in strict_theme_tokens if pt in full_lower)
            if premise_occurrences >= 2 or (premise_occurrences >= 1 and title_occurrences >= 1) or all_occurrences >= 3:
                centrality = 95.0
            elif premise_occurrences >= 1 or title_occurrences >= 1 or all_occurrences >= 1:
                centrality = 85.0
            else:
                centrality = 25.0

        # ----------------------------------------------------
        # 2. TOPIC EVIDENCE COVERAGE (0 - 100)
        # Are clues / investigation scenes tied to the topic context?
        # ----------------------------------------------------
        context_hits = sum(1 for ct in context_tokens if ct in clues_lower)
        theme_hits_clues = sum(1 for st in strict_theme_tokens if st in clues_lower)
        
        if not clues_text.strip():
            evidence_cov = centrality
        elif (context_hits >= 2 and theme_hits_clues >= 1) or context_hits >= 3 or theme_hits_clues >= 2:
            evidence_cov = 95.0
        elif (context_hits >= 1 and theme_hits_clues >= 1) or context_hits >= 2:
            evidence_cov = 85.0
        elif context_hits >= 1 or theme_hits_clues >= 1:
            evidence_cov = 80.0
        elif any(ct in clues_lower for ct in context_tokens):
            evidence_cov = 75.0 if stage in ("idea", "story_bible") else 25.0
        else:
            evidence_cov = 25.0

        # ----------------------------------------------------
        # 3. TOPIC REVEAL ALIGNMENT (0 - 100)
        # Do the reveals resolve or develop the central topic?
        # ----------------------------------------------------
        # Clean template leakage from reveals_lower to prevent false credit
        cleaned_reveals = re.sub(r"bước ngoặt [12]:.*?(?=\.|$)", "", reveals_lower)
        cleaned_reveals = re.sub(r"chân tướng sự thật về bí mật.*?(?=\.|$)", "", cleaned_reveals)

        reveal_theme_hits = sum(1 for pt in strict_theme_tokens if pt in cleaned_reveals)
        reveal_context_hits = sum(1 for ct in context_tokens if ct in cleaned_reveals)

        # Check if reveals are hijacked by foreign medical/land tropes
        # "bệnh viện" alone is not a hijack: childbirth or a DNA test happens there in
        # perfectly on-topic affair stories. Surgery/fees/records/land sales are the trope.
        has_hijacked_reveals = any(tr in cleaned_reveals for tr in ["phẫu thuật", "bán mảnh đất", "đất hương hỏa", "viện phí", "100.000.000", "bệnh án"])

        if has_hijacked_reveals and is_infidelity:
            reveal_align = 0.0
        elif not reveals_text.strip():
            reveal_align = centrality
        elif (reveal_theme_hits >= 1 and reveal_context_hits >= 1) or reveal_theme_hits >= 2 or reveal_context_hits >= 2:
            reveal_align = 95.0
        elif reveal_theme_hits >= 1 or reveal_context_hits >= 1:
            reveal_align = 85.0
        else:
            reveal_align = 40.0 if stage in ("idea", "story_bible") else 20.0

        # ----------------------------------------------------
        # 4. FORBIDDEN DRIFT PENALTY
        # Checks for completely unrelated dominant narrative tropes
        # (e.g. medical surgery/100M VND/selling land when topic is workplace infidelity)
        # ----------------------------------------------------
        drift_hits: List[str] = []
        for drift in self.forbidden_drift:
            drift_lower = drift.lower().strip()
            if drift_lower and drift_lower in full_lower:
                drift_hits.append(drift_lower)

        # Domain-specific severe foreign tropes:
        # If user topic is about infidelity / workplace affair, medical surgery / ancestral land / orphanage debt are severe foreign tropes
        is_infidelity_topic = any(k in self.original_topic.lower() for k in ["ngoại tình", "tiểu tam", "người thứ ba", "bồ nhí", "phản bội tình cảm", "vụng trộm"])
        if is_infidelity_topic:
            foreign_tropes = [
                ("phẫu thuật", 25.0),
                ("bán mảnh đất", 25.0),
                ("đất hương hỏa", 25.0),
                ("viện phí", 20.0),
                ("100.000.000", 25.0),
                ("100 triệu", 25.0),
                ("trại trẻ mồ côi", 25.0),
                ("hồ sơ bệnh án", 20.0),
                ("hoãn lại ca phẫu thuật", 30.0),
            ]
            for trope, pen in foreign_tropes:
                if trope in full_lower:
                    drift_hits.append(f"foreign_trope:{trope}")

        drift_penalty = min(70.0, len(drift_hits) * 15.0)

        # ----------------------------------------------------
        # 5. OVERALL COMPOSITE ADHERENCE SCORE
        # ----------------------------------------------------
        base_composite = (
            centrality * 0.40
            + evidence_cov * 0.30
            + reveal_align * 0.30
        )
        final_score = max(0.0, min(100.0, round(base_composite - drift_penalty, 1)))

        # Pass condition: score >= 75.0 AND centrality >= 50.0 AND reveal_align >= 40.0
        status = "PASS" if (final_score >= 75.0 and centrality >= 50.0 and reveal_align >= 40.0) else "FAIL"

        return {
            "score": final_score,
            "topic_centrality_score": centrality,
            "topic_evidence_coverage": evidence_cov,
            "topic_reveal_alignment": reveal_align,
            "drift_detected": bool(drift_hits),
            "drift_terms": drift_hits,
            "status": status,
            "details": f"Centrality: {centrality}, Evidence: {evidence_cov}, Reveal: {reveal_align}, Drift penalty: -{drift_penalty}",
        }

    def calculate_adherence_score(self, idea_or_text: Any) -> float:
        """Calculates adherence score (0-100) of an idea or script against this TopicIntent."""
        res = self.evaluate_content_adherence(idea_or_text)
        return res["score"]


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
    stop_words_topic = {"cho", "một", "suốt", "từ", "được", "các", "những", "trong", "với", "về", "của", "và", "là", "có"}
    topic_words = [w for w in re.split(r"[\s,.-]+", clean_topic) if w]
    meaningful_ngrams = []
    for i in range(len(topic_words) - 1):
        w1, w2 = topic_words[i].lower(), topic_words[i+1].lower()
        if w1 not in stop_words_topic or w2 not in stop_words_topic:
            meaningful_ngrams.append(f"{w1} {w2}")
    meaningful_words = [w.lower() for w in topic_words if len(w) >= 3 and w.lower() not in stop_words_topic and w.lower() not in ("người", "nhận", "phát", "hiện")]
    keywords = list(dict.fromkeys(meaningful_ngrams + meaningful_words))[:8]
    if not keywords:
        keywords = topic_words[:4]

    return TopicIntent(
        original_topic=clean_topic,
        primary_theme=clean_topic,
        context=f"Bối cảnh xoay quanh đề tài '{clean_topic}'",
        central_conflict=f"Mâu thuẫn và bí mật nảy sinh từ '{clean_topic}'",
        required_semantic_elements=keywords,
        optional_elements=["nhân vật trực tiếp liên quan", "chứng cứ xác minh", "hệ quả cảm xúc", "sự thật được hé lộ"],
        forbidden_drift=["chủ đề gia đình chung chung không liên quan đến đề tài người dùng", "sự việc hư cấu siêu nhiên"],
    )
