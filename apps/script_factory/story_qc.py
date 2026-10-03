"""Story Quality Engine (QC V1.2) for Script Factory.

Implements Sections 8 to 20:
- Clue -> Reveal Causality (at least 2 STRONG clues for Reveal 1, seeded clue for Reveal 2)
- Reveal Quality (surprise, fairness, reveal_2_value)
- False Lead Quality (false_lead_strength)
- Coincidence Budget (coincidence_count)
- Genre Guard (genre_fit_score, checks horror/thriller/supernatural drift)
- Vietnamese Social Fit (vietnamese_social_fit_score)
- Emotional Restraint & Tragedy Saturation (emotional_device, has_death_or_tragedy)
- Title QC (title_strength, title_specificity, title_curiosity_gap)
- Final Status Resolution (AWAITING_USER_REVIEW, NEEDS_NOVELTY_REWRITE, NEEDS_LOGIC_REWRITE,
  NEEDS_GENRE_REWRITE, BLOCKED_NARRATIVE_DUPLICATE, BLOCKED_IMPLAUSIBLE)
- Strictly enforces: AI cannot assign USER_APPROVED.
"""
from __future__ import annotations

import json
import copy
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("VieNeu.StoryQC")

from apps.script_factory.models import ApprovalStatus, IdeaItem, StoryBible
from apps.script_factory.novelty_engine import (
    NoveltyEngine,
    compute_narrative_skeleton_similarity,
    extract_narrative_skeleton,
)
from apps.script_factory.plausibility_qc import PlausibilityEngine, PlausibilityResult


@dataclass
class StoryBibleQCReport:
    episode_id: str
    status: str  # "PASS", "FAIL", "NEEDS_LOGIC_REWRITE"
    issues: List[Dict[str, Any]] = field(default_factory=list)
    logic_issues: List[str] = field(default_factory=list)
    rule_codes: List[str] = field(default_factory=list)
    semantic_review: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Supernatural, horror, dungeon thriller, and fantasy trigger terms
GENRE_BREACH_PATTERNS = [
    (r"\b(ma|quỷ|hồn ma|oan hồn|nhập hồn|bùa chú|tâm linh|siêu nhiên|cõi âm|đầu thai|kiếp trước|bóng ma)\b", "supernatural"),
    (r"\b(căn nhà không cửa sổ|tiếng đàn lúc nửa đêm|ngôi nhà ma|hầm ngục|bắt cóc giam cầm|tra tấn)\b", "horror_thriller"),
    (r"\b(giết người hàng loạt|sát nhân hàng loạt|tội phạm xuyên quốc gia|mạng lưới mafia)\b", "crime_thriller"),
    (r"\b(phép màu|thần tiên|tiên tri|phù thủy)\b", "fantasy"),
]

# Emotional devices
EMOTIONAL_DEVICES = [
    ("BETRAYAL", ["phản bội", "ngoại tình", "gian dối", "hai lòng", "lừa gạt", "chiếm đoạt"]),
    ("SACRIFICE", ["hy sinh", "nhường", "thầm lặng", "chịu đựng", "gánh vác", "vì con", "vì em"]),
    ("GUILT", ["cắn rứt", "tội lỗi", "hối hận", "day dứt", "giá như", "nỗi ân hận"]),
    ("REGRET", ["tiếc nuối", "muộn màng", "bỏ lỡ", "dang dở"]),
    ("MISUNDERSTANDING", ["hiểu lầm", "oan ức", "ngờ vực", "nghi ngờ sai", "hiểu sai"]),
    ("FORGIVENESS", ["tha thứ", "bao dung", "hóa giải", "chữa lành", "ôm chầm", "bỏ qua"]),
    ("PARENTAL_LOVE", ["tình mẫu tử", "tình phụ tử", "con ruột", "con nuôi", "thương con", "bố mẹ"]),
    ("MARITAL_TRUST", ["tình nghĩa vợ chồng", "lòng tin", "hôn nhân", "chung thủy", "nắm tay"]),
    ("IDENTITY", ["thân phận", "nguồn cội", "con ai", "máu mủ", "danh tính"]),
    ("LOYALTY", ["trung thành", "lời hứa", "giữ lời", "ân tình"]),
    ("SHAME", ["xấu hổ", "mặc cảm", "tủi hổ", "che giấu quá khứ"]),
    ("RESPONSIBILITY", ["trách nhiệm", "bổn phận", "nghĩa vụ"]),
]


@dataclass
class IdeaQCReport:
    idea_id: str
    status: str
    novelty_score: float
    narrative_skeleton_similarity: float
    plausibility_score: float
    genre_fit_score: float
    vietnamese_social_fit_score: float
    false_lead_strength: float
    reveal_qc: Dict[str, float]
    clues_causality: List[Dict[str, Any]]
    coincidence_count: int
    skeptical_viewer_questions: List[str]
    logic_issues: List[str]
    emotional_device: str
    has_death_or_tragedy: bool
    title_strength: float
    title_specificity: float
    title_curiosity_gap: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StoryQCEngine:
    """Audits and hardens premise ideas before Story Bible creation."""

    def __init__(self, novelty_engine: Optional[NoveltyEngine] = None, provider: Optional[Any] = None):
        self.novelty_engine = novelty_engine or NoveltyEngine()
        self.plausibility_engine = PlausibilityEngine()
        self.provider = provider
        self._bible_review_cache: Dict[str, Dict[str, Any]] = {}

    def _semantic_bible_review(self, bible: StoryBible) -> Optional[Dict[str, Any]]:
        """LLM plot-logic review, cached per Story Bible content (audits repeat often)."""
        complete_json = getattr(self.provider, "complete_json", None)
        if not callable(complete_json):
            return None
        from apps.script_factory.semantic_review import review_story_bible_logic, story_bible_content_hash, valid_story_semantic_review
        key = story_bible_content_hash(bible)
        stored = (bible.story_qc_report or {}).get('semantic_review')
        if valid_story_semantic_review(bible, stored):
            return stored
        if key not in self._bible_review_cache or self._bible_review_cache[key].get('status') == 'ERROR':
            try:
                self._bible_review_cache[key] = review_story_bible_logic(
                    bible, lambda system, prompt: complete_json(system, prompt),
                    _require_grounding=bool(getattr(self.provider, 'requires_grounded_review', False)),
                )
            except Exception as exc:
                logger.warning(f"[StoryQCEngine] Semantic Story Bible review failed: {exc}")
                return {"status": "ERROR", "error": str(exc), "issues": []}
        return self._bible_review_cache[key]

    def audit_idea(
        self,
        idea: IdeaItem,
        corpus_ideas: Optional[List[IdeaItem]] = None,
    ) -> IdeaQCReport:
        corpus = corpus_ideas or []
        full_text = (
            f"{idea.working_title} {idea.hook} {idea.protagonist} {idea.relationship} "
            f"{idea.central_secret} {idea.mystery_question} {idea.false_lead} "
            f"{idea.clue_1} {idea.clue_2} {idea.clue_3} {idea.reveal_1} {idea.reveal_2} "
            f"{idea.emotional_payoff} {idea.reflection_theme}"
        ).lower()

        reasons: List[str] = []

        # 1. Narrative Skeleton & Novelty Check
        nov_report = self.novelty_engine.check_idea_novelty(idea, corpus)
        skel_sim = nov_report.narrative_skeleton_similarity_pct
        novelty_score = nov_report.novelty_score

        # 2. Plausibility Check
        plaus_res = self.plausibility_engine.evaluate_idea(idea)
        plausibility_score = plaus_res.score
        skeptical_questions = plaus_res.skeptical_viewer_questions
        logic_issues = list(plaus_res.issues)

        # 3. Genre Guard Evaluation (Section 13 & 24 IDEA_013 test case)
        genre_breaches = []
        for pattern, genre_type in GENRE_BREACH_PATTERNS:
            if re.search(pattern, full_text):
                genre_breaches.append(genre_type)

        if genre_breaches:
            if "horror_thriller" in genre_breaches or "supernatural" in genre_breaches:
                genre_fit_score = 55.0
                reasons.append("Phát hiện nguy cơ trôi dạt sang phong cách kinh dị/giật gân (horror/captivity thriller), lệch khỏi tôn chỉ bí ẩn xã hội/gia đình.")
            else:
                genre_fit_score = 65.0
                reasons.append(f"Yếu tố thể loại ({', '.join(genre_breaches)}) chưa thuần chất tâm lý gia đình Việt Nam.")
        else:
            genre_fit_score = 90.0

        # 4. Vietnamese Social Fit Evaluation (Section 14)
        vn_score = 85.0
        # Positive indicators: family relations, Vietnamese culture, realistic locations
        vn_tokens = ["gia đình", "bố", "mẹ", "ông", "bà", "quê", "xóm", "hàng xóm", "ngân hàng", "sổ đỏ", "di chúc", "bệnh viện"]
        matched_vn = sum(1 for tok in vn_tokens if tok in full_text)
        if matched_vn >= 4:
            vn_score += 10.0
        vn_social_fit = min(98.0, vn_score)

        # 5. Clue -> Reveal Causality (Section 9)
        # Check clue 1, clue 2, clue 3
        clues_causality = []
        strong_clues_count = 0
        r2_seeded = False

        clues = [("clue_1", idea.clue_1), ("clue_2", idea.clue_2), ("clue_3", idea.clue_3)]
        for c_field, c_text in clues:
            c_low = c_text.lower()
            # Determine support
            supports = []
            # Check overlap with reveal 1 vs reveal 2
            rev1_overlap = sum(1 for w in _tokenize(c_low) if w in _tokenize(idea.reveal_1.lower()))
            rev2_overlap = sum(1 for w in _tokenize(c_low) if w in _tokenize(idea.reveal_2.lower()))

            if rev2_overlap > rev1_overlap:
                supports.append("REVEAL_2")
                r2_seeded = True
            else:
                supports.append("REVEAL_1")

            # Determine strength: concrete evidence vs vague suspicion
            has_concrete_proof = any(w in c_low for w in ["giấy", "hồ sơ", "ảnh", "bức ảnh", "tin nhắn", "cuộc gọi", "sổ", "tiền", "vết", "khăn", "đồng hồ", "hộp"])
            if has_concrete_proof and len(c_text) > 15:
                strength = "STRONG"
                if "REVEAL_1" in supports:
                    strong_clues_count += 1
            elif len(c_text) > 20:
                strength = "MEDIUM"
            else:
                strength = "WEAK"

            clues_causality.append({
                "clue_field": c_field,
                "clue": c_text,
                "supports": supports,
                "causal_strength": strength,
            })

        if strong_clues_count < 2:
            logic_issues.append("Cần tối thiểu 2 manh mối vững chắc (STRONG clues) để chứng minh cho Bước ngoặt 1.")
        if not r2_seeded:
            # Seed clue check
            logic_issues.append("Bước ngoặt 2 (Reveal 2) chưa được gieo mầm (seeded) từ các manh mối ban đầu.")

        # 6. Reveal Quality (Section 10)
        # reveal_1_surprise, reveal_1_fairness, reveal_2_surprise, reveal_2_fairness, reveal_2_value
        r1_surprise = 8.5 if len(idea.reveal_1) > 20 else 6.0
        r1_fairness = 9.0 if strong_clues_count >= 2 else 6.5

        # Check if reveal 2 merely restates reveal 1 or provides genuinely new meaning
        r1_tokens = _tokenize(idea.reveal_1.lower())
        r2_tokens = _tokenize(idea.reveal_2.lower())
        overlap_r1_r2 = len(r1_tokens & r2_tokens) / max(1, len(r2_tokens))
        
        if overlap_r1_r2 > 0.65:
            r2_value = 5.0
            logic_issues.append("Bước ngoặt 2 có nguy cơ chỉ lặp lại chi tiết của Bước ngoặt 1 mà không thay đổi bản chất ý nghĩa cảm xúc.")
        else:
            r2_value = 8.8

        reveal_qc = {
            "reveal_1_surprise": round(r1_surprise, 1),
            "reveal_1_fairness": round(r1_fairness, 1),
            "reveal_2_surprise": 8.6,
            "reveal_2_fairness": 8.9,
            "reveal_2_value": round(r2_value, 1),
        }

        # 7. False Lead Quality (Section 11)
        fl_len = len(idea.false_lead)
        false_lead_strength = 8.5 if fl_len > 25 and not any(w in idea.false_lead.lower() for w in ["không rõ", "tùy ý"]) else 6.0

        # 8. Coincidence Budget (Section 12)
        coincidence_count = 0
        coincidence_triggers = [
            r"tình cờ nghe được",
            r"vô tình bắt gặp",
            r"người lạ tự nhiên kể",
            r"đột nhiên thú nhận",
            r"vô tình nhặt được",
            r"bỗng nhiên xuất hiện",
        ]
        for trg in coincidence_triggers:
            if re.search(trg, full_text):
                coincidence_count += 1

        if coincidence_count >= 3:
            logic_issues.append(f"Số lượng tình tiết ngẫu nhiên/trùng hợp ({coincidence_count}) vượt ngân sách tối đa cho phép (0-1).")

        # 9. Emotional Device & Tragedy Saturation (Sections 15 & 16)
        detected_device = "MISUNDERSTANDING"
        for dev_name, keywords in EMOTIONAL_DEVICES:
            if any(kw in full_text for kw in keywords):
                detected_device = dev_name
                break

        has_death_or_tragedy = any(w in full_text for w in ["đã mất", "đã khuất", "qua đời", "tai nạn", "bệnh nặng", "ung thư", "tử vong", "hy sinh mạng sống"])

        # 10. Title QC (Section 17)
        # Prefer concrete, specific titles over abstract clichés like "Bí mật đằng sau nụ cười"
        title_low = idea.working_title.lower()
        is_cliche_abstract = any(c in title_low for c in ["bí mật đằng sau nụ cười", "nỗi niềm", "góc khuất cuộc đời"])
        title_strength = 6.0 if is_cliche_abstract else 8.5
        title_spec = 6.0 if is_cliche_abstract or len(idea.working_title) < 15 else 8.8
        title_curiosity = 8.0 if any(w in title_low for w in ["chiếc", "bức", "lá thư", "khoản", "cuộc gọi", "tin nhắn", "năm", "đêm"]) else 7.0

        # 11. Final Status Resolution (Section 20 Hard Gates)
        # Priority order:
        # 1. BLOCKED_NARRATIVE_DUPLICATE (skel_sim >= 70%)
        # 2. BLOCKED_IMPLAUSIBLE (plausibility < 55)
        # 3. NEEDS_NOVELTY_REWRITE (60% <= skel_sim < 70%)
        # 4. NEEDS_LOGIC_REWRITE (plausibility < 70 or coincidence_count >= 3 or r2_value < 6.0)
        # 5. NEEDS_GENRE_REWRITE (genre_fit_score < 70)
        # 6. AWAITING_USER_REVIEW (default pass)
        # Under NO circumstances can AI assign USER_APPROVED!
        final_status = "AWAITING_USER_REVIEW"

        if skel_sim >= 70.0:
            final_status = ApprovalStatus.BLOCKED_NARRATIVE_DUPLICATE.value
            reasons.append(f"Khung truyện (Narrative Skeleton) trùng lặp {skel_sim:.1f}% >= 70%. Bị chặn trùng lặp.")
        elif plausibility_score < 55.0:
            final_status = ApprovalStatus.BLOCKED_IMPLAUSIBLE.value
            reasons.append(f"Điểm logic đời thực {plausibility_score:.1f} < 55. Bị chặn do phi lý.")
        elif 60.0 <= skel_sim < 70.0:
            final_status = ApprovalStatus.NEEDS_NOVELTY_REWRITE.value
            reasons.append(f"Khung truyện trùng lặp {skel_sim:.1f}% trong khoảng cảnh báo 60-69.9%. Yêu cầu viết lại tính độc bản.")
        elif plausibility_score < 70.0 or coincidence_count >= 3 or r2_value < 6.0:
            final_status = ApprovalStatus.NEEDS_LOGIC_REWRITE.value
            reasons.append("Yêu cầu sửa đổi logic (thiếu manh mối chứng minh, sự trùng hợp ngẫu nhiên hoặc mâu thuẫn thời gian).")
        elif genre_fit_score < 70.0:
            final_status = ApprovalStatus.NEEDS_GENRE_REWRITE.value
            reasons.append(f"Điểm phù hợp thể loại {genre_fit_score:.1f} < 70. Yêu cầu sửa đổi để loại bỏ yếu tố giật gân/kinh dị lệch chuẩn.")
        else:
            final_status = ApprovalStatus.AWAITING_USER_REVIEW.value

        # STRICT ENFORCEMENT: AI cannot assign USER_APPROVED
        assert final_status != ApprovalStatus.USER_APPROVED.value, "Security fault: AI attempted to assign USER_APPROVED!"

        # Update idea fields
        idea.status = final_status
        idea.narrative_skeleton = extract_narrative_skeleton(idea)
        idea.narrative_skeleton_similarity = skel_sim
        idea.plausibility_score = plausibility_score
        idea.plausibility_issues = logic_issues
        idea.required_explanations = plaus_res.required_explanations
        idea.skeptical_viewer_questions = skeptical_questions
        idea.logic_issues = logic_issues
        idea.clues_causality = clues_causality
        idea.reveal_qc = reveal_qc
        idea.false_lead_strength = false_lead_strength
        idea.coincidence_count = coincidence_count
        idea.genre_fit_score = genre_fit_score
        idea.vietnamese_social_fit_score = vn_social_fit
        idea.emotional_device = detected_device
        idea.has_death_or_tragedy = has_death_or_tragedy
        idea.title_strength = title_strength
        idea.title_specificity = title_spec
        idea.title_curiosity_gap = title_curiosity

        return IdeaQCReport(
            idea_id=idea.idea_id,
            status=final_status,
            novelty_score=novelty_score,
            narrative_skeleton_similarity=skel_sim,
            plausibility_score=plausibility_score,
            genre_fit_score=genre_fit_score,
            vietnamese_social_fit_score=vn_social_fit,
            false_lead_strength=false_lead_strength,
            reveal_qc=reveal_qc,
            clues_causality=clues_causality,
            coincidence_count=coincidence_count,
            skeptical_viewer_questions=skeptical_questions,
            logic_issues=logic_issues,
            emotional_device=detected_device,
            has_death_or_tragedy=has_death_or_tragedy,
            title_strength=title_strength,
            title_specificity=title_spec,
            title_curiosity_gap=title_curiosity,
            reasons=reasons,
        )

    def audit_story_bible(self, bible: StoryBible) -> StoryBibleQCReport:
        """
        Audits Story Bible for deep causal logic, character secret knowledge consistency,
        evidence-to-claim validity, and reveal justification support before ScriptWriter runs.
        """
        issues: List[Dict[str, Any]] = []
        logic_issues: List[str] = []
        rule_codes: List[str] = []

        def _add_issue(rule: str, message: str, severity: str = "CRITICAL", target: str = "story_bible") -> None:
            issues.append({
                "rule": rule,
                "severity": severity,
                "target": target,
                "message": message,
            })
            logic_issues.append(f"[{rule}] {message}")
            if rule not in rule_codes:
                rule_codes.append(rule)

        from apps.script_factory.event_facts import bible_timeline_conflicts
        for message in bible_timeline_conflicts(bible):
            _add_issue('EVENT_TIMELINE_CONTRADICTION', message, target='timeline')
        from apps.script_factory.story_contract import bible_age_conflicts
        for target, message in bible_age_conflicts(bible):
            _add_issue('CHARACTER_IDENTITY_CONTRADICTION', message, target=target)

        # "Minh" is the fixed on-air host. Reusing that name for a story
        # character makes narration ambiguous ("Minh nói với Minh") and can
        # corrupt speaker/voice mapping later in the pipeline.
        protagonist_name = (
            str(bible.protagonist.get("name", ""))
            if isinstance(bible.protagonist, dict)
            else str(bible.protagonist or "")
        ).strip()
        reserved_name_hits: List[str] = []
        if protagonist_name.casefold() == "minh":
            reserved_name_hits.append("protagonist")
        for idx, character in enumerate(bible.supporting_characters or []):
            if not isinstance(character, dict):
                continue
            char_name = str(character.get("name", "")).strip()
            char_id = str(character.get("char_id", "")).strip()
            if char_name.casefold() == "minh" or char_id.upper() == "MINH":
                reserved_name_hits.append(f"supporting_characters[{idx}]")
        if reserved_name_hits and not (bible.adaptation_context and bible.adaptation_context['brief']['adaptation_mode'] == 'FACTUAL_RETELLING'):
            _add_issue(
                "HOST_CHARACTER_NAME_COLLISION",
                "Tên 'Minh' được dành riêng cho MC. Hãy đổi tên nhân vật trong truyện để lời dẫn và ánh xạ giọng không bị nhập nhằng.",
                target=", ".join(reserved_name_hits),
            )

        # ------------------------------------------------------------------
        # 1. CAUSAL_GAP CHECK (CAUSE -> DECISION -> ACTION -> CONSEQUENCE)
        # ------------------------------------------------------------------
        combined_story_text = " ".join([
            str(bible.secret or ""),
            str(bible.reveal_1 or ""),
            str(bible.reveal_2 or ""),
            " ".join(str(t) for t in (bible.timeline or [])),
        ]).lower()

        if bible.causal_chains:
            for idx, chain in enumerate(bible.causal_chains):
                if not isinstance(chain, dict):
                    continue
                c_cause = str(chain.get("cause", "")).strip()
                c_decision = str(chain.get("decision", "")).strip()
                c_action = str(chain.get("action", "")).strip()
                c_conseq = str(chain.get("consequence", "")).strip()
                c_why = str(chain.get("why", "") or c_cause).strip()
                c_motiv = str(chain.get("motivation", "")).strip()
                c_how = str(chain.get("how", "")).strip()

                missing_parts = []
                if len(c_cause) < 8 or c_cause.lower() in ("không rõ", "tự nhiên", "ngẫu nhiên"):
                    missing_parts.append("CAUSE/WHY")
                if len(c_decision) < 8:
                    missing_parts.append("DECISION")
                if len(c_action) < 8:
                    missing_parts.append("ACTION")
                if len(c_conseq) < 8:
                    missing_parts.append("CONSEQUENCE")
                if "motivation" in chain and (len(c_motiv) < 10 or c_motiv.lower() in ("không rõ", "vì thương", "vì lời hứa")):
                    missing_parts.append("MOTIVATION (why simpler alternative was impossible)")
                if "how" in chain and (len(c_how) < 10 or c_how.lower() in ("không rõ", "tự nhiên")):
                    missing_parts.append("HOW (real-life mechanism over duration)")

                if missing_parts:
                    _add_issue(
                        "CAUSAL_GAP",
                        f"Chuỗi nhân quả #{idx + 1} thiếu hoặc yếu ở mắt xích: {', '.join(missing_parts)}.",
                        target=f"causal_chains[{idx}]",
                    )

                # Check if cause is a minor request but action is an extreme lifelong/multi-decade transformation without necessity
                chain_text = f"{c_cause} {c_decision} {c_action} {c_motiv} {c_how}".lower()
                if _has_weak_cause_to_extreme_action(chain_text, has_strong_necessity=bool(len(c_motiv) >= 25 and _has_necessity_markers(c_motiv.lower()))):
                    _add_issue(
                        "CAUSAL_GAP",
                        f"Chuỗi nhân quả #{idx + 1} có bước nhảy vô lý: nguyên nhân đơn giản ('{c_cause[:60]}') không đủ bắt buộc hành động cực đoan ('{c_action[:60]}') khi chưa giải thích tại sao giải pháp bình thường là bất khả thi.",
                        target=f"causal_chains[{idx}]",
                    )

        # Also check raw story text (secret / reveal_1 / reveal_2) for weak cause -> extreme action jump
        causal_chains_text = json.dumps(bible.causal_chains, ensure_ascii=False).lower() if bible.causal_chains else ""
        if _has_weak_cause_to_extreme_action(
            combined_story_text + " " + causal_chains_text,
            has_strong_necessity=_has_necessity_markers(combined_story_text + " " + causal_chains_text),
        ):
            _add_issue(
                "CAUSAL_GAP",
                "Story Bible tồn tại khoảng trống nhân quả (CAUSAL_GAP): Nguyên nhân/lời nhờ vả ban đầu không đủ sức nặng bắt buộc nhân vật thực hiện hành động cực đoan kéo dài nhiều năm (thiếu lý do tại sao không thể giúp đỡ dưới danh tính/cách thức bình thường).",
                target="reveal_2",
            )

        # ------------------------------------------------------------------
        # 2. CHARACTER_KNOWLEDGE_CONTRADICTION CHECK
        # ------------------------------------------------------------------
        knowing_characters: List[str] = []
        ignorant_characters: List[str] = []

        for sc in (bible.supporting_characters or []):
            if not isinstance(sc, dict):
                continue
            sc_name = str(sc.get("name", "") or sc.get("char_id", "")).strip()
            sc_desc = " ".join(str(sc.get(k, "")) for k in ("description", "role", "reason_for_silence", "want", "fear")).lower()
            if any(p in sc_desc for p in ["biết toàn bộ", "biết sự thật", "biết rõ", "biết hết", "cùng che giấu", "chọn cách câm lặng", "giữ kín bí mật cùng"]):
                if sc_name:
                    knowing_characters.append(sc_name)
            if any(p in sc_desc for p in ["không hề biết", "không hay biết", "hoàn toàn không biết", "bị giấu kín"]):
                if sc_name:
                    ignorant_characters.append(sc_name)

        ledger_scopes: Dict[str, str] = {}
        for entry in (bible.knowledge_ledger or []):
            if not isinstance(entry, dict):
                continue
            char_name = str(entry.get("character", "") or entry.get("who_knows_what", "")).strip()
            scope = str(entry.get("knowledge_scope", "")).strip().lower()
            when_learned = str(entry.get("when_they_learned_it", "")).strip()
            how_learned = str(entry.get("how_they_learned_it", "")).strip()

            if scope in ("full", "partial"):
                if not when_learned or not how_learned:
                    _add_issue(
                        "CHARACTER_KNOWLEDGE_CONTRADICTION",
                        f"Nhân vật '{char_name}' có knowledge_scope='{scope}' nhưng thiếu thời điểm ('when_they_learned_it') hoặc cách thức biết ('how_they_learned_it').",
                        target="knowledge_ledger",
                    )
                if char_name:
                    knowing_characters.append(char_name)
            elif scope == "none" and char_name:
                ignorant_characters.append(char_name)

            if char_name:
                norm_name = char_name.lower()
                if norm_name in ledger_scopes and ledger_scopes[norm_name] != scope:
                    _add_issue(
                        "CHARACTER_KNOWLEDGE_CONTRADICTION",
                        f"Nhân vật '{char_name}' bị khai báo mâu thuẫn trong knowledge_ledger ('{ledger_scopes[norm_name]}' vs '{scope}').",
                        target="knowledge_ledger",
                    )
                ledger_scopes[norm_name] = scope

        # Check overlap between knowing_characters and ignorant_characters
        knowing_low = {c.lower() for c in knowing_characters}
        ignorant_low = {c.lower() for c in ignorant_characters}
        overlap_chars = knowing_low & ignorant_low
        if overlap_chars:
            _add_issue(
                "CHARACTER_KNOWLEDGE_CONTRADICTION",
                f"Mâu thuẫn nhận thức nhân vật: {', '.join(overlap_chars)} vừa được mô tả là biết bí mật vừa được mô tả là không hề hay biết.",
                target="supporting_characters",
            )

        # Check if someone knows the secret while Story Bible claims "nobody knew / could not tell spouse"
        nobody_knew_patterns = [
            r"không\s+một\s+ai\s+biết",
            r"không\s+một\s+ai\s+hay\s+biết",
            r"không\s+ai\s+trên\s+đời\s+biết",
            r"không\s+thể\s+sẻ\s+chia\s+cùng\s+ai",
            r"kể\s+cả\s+(?:với\s+)?người\s+vợ",
            r"kể\s+cả\s+vợ\s+con",
            r"chỉ\s+một\s+mình\s+[^\s,]+\s+biết",
        ]
        if knowing_characters:
            for pat in nobody_knew_patterns:
                if re.search(pat, combined_story_text, re.IGNORECASE):
                    _add_issue(
                        "CHARACTER_KNOWLEDGE_CONTRADICTION",
                        f"Story Bible ghi nhận nhân vật ({', '.join(knowing_characters)}) biết sự thật, nhưng phần mô tả bí mật/reveal lại khẳng định tuyệt đối không ai biết hoặc không thể chia sẻ cùng ai.",
                        target="knowledge_ledger",
                    )
                    break

        # ------------------------------------------------------------------
        # 3. EVIDENCE_DOES_NOT_PROVE_CLAIM CHECK
        # ------------------------------------------------------------------
        for idx, sc_item in enumerate(bible.structured_clues or []):
            if not isinstance(sc_item, dict):
                continue
            clue_txt = str(sc_item.get("clue", "")).strip()
            proves_txt = str(sc_item.get("what_it_proves", "")).strip()
            not_proves_txt = str(
                sc_item.get("what_it_does_NOT_prove")
                or sc_item.get("what_it_does_not_prove")
                or ""
            ).strip()
            next_q_txt = str(sc_item.get("next_question", "")).strip()

            if not clue_txt or not proves_txt or not not_proves_txt or not next_q_txt:
                _add_issue(
                    "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    f"Manh mối có cấu trúc #{idx + 1} thiếu trường bắt buộc (clue, what_it_proves, what_it_does_NOT_prove, next_question).",
                    target=f"structured_clues[{idx}]",
                )
                continue

            # Check if what_it_proves claims the exact conclusion that what_it_does_NOT_prove says it cannot prove
            proves_clean = re.sub(r"\b(không|chưa|chẳng|đừng)\b", "", proves_txt.lower())
            not_proves_clean = re.sub(r"\b(không|chưa|chẳng|đừng)\b", "", not_proves_txt.lower())
            p_toks = {w for w in _tokenize(proves_clean) if len(w) > 2}
            np_toks = {w for w in _tokenize(not_proves_clean) if len(w) > 2}
            if p_toks and np_toks:
                overlap_ratio = len(p_toks & np_toks) / max(1, min(len(p_toks), len(np_toks)))
                # If proves_txt does NOT negate the claim and overlaps heavily with what_it_does_NOT_prove
                if overlap_ratio >= 0.75 and not any(neg in proves_txt.lower() for neg in ["chỉ chứng minh", "chưa chứng minh", "không chứng minh"]):
                    _add_issue(
                        "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                        f"Manh mối #{idx + 1} ('{clue_txt[:50]}') tuyên bố chứng minh điều vượt quá giá trị vật chứng ('{proves_txt[:60]}' trùng với điều chưa thể chứng minh '{not_proves_txt[:60]}').",
                        target=f"structured_clues[{idx}]",
                    )

            # Check if an initial single object clue jumps directly to proving full identity theft / crime
            if _is_overreaching_clue_claim(clue_txt, proves_txt):
                _add_issue(
                    "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    f"Manh mối #{idx + 1} ('{clue_txt[:50]}') nhảy cóc từ vật chứng đơn lẻ sang kết luận cuối cùng ('{proves_txt[:60]}') mà thiếu bằng chứng trung gian.",
                    target=f"structured_clues[{idx}]",
                )

        for idx, raw_clue in enumerate(bible.clues or []):
            if _is_overreaching_raw_clue(str(raw_clue)):
                _add_issue(
                    "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    f"Manh mối #{idx + 1} ('{str(raw_clue)[:70]}') nhảy cóc trực tiếp tới kết luận cuối cùng mà không qua chuỗi xác minh trung gian.",
                    target=f"clues[{idx}]",
                )

        # ------------------------------------------------------------------
        # 4. REVEAL JUSTIFICATION GATE (UNSUPPORTED_REVEAL)
        # ------------------------------------------------------------------
        justifications = bible.reveal_justifications or {}
        if justifications:
            r1_just = justifications.get("reveal_1")
            r2_just = justifications.get("reveal_2")
            r1_required = ("evidence_support", "motivation_support", "timeline_support")
            r2_required = ("evidence_support", "motivation_support", "character_knowledge_support")

            if not isinstance(r1_just, dict) and (bible.reveal_1 or not bible.adaptation_context):
                _add_issue(
                    "UNSUPPORTED_REVEAL",
                    "Reveal 1 thiếu cấu trúc chứng minh (reveal_justifications.reveal_1).",
                    target="reveal_1",
                )
            elif isinstance(r1_just, dict):
                for req_key in r1_required:
                    val = r1_just.get(req_key)
                    if not val or str(val).strip().lower() in ("", "none", "false", "unsupported", "không có", "thiếu"):
                        _add_issue(
                            "UNSUPPORTED_REVEAL",
                            f"Reveal 1 không đủ căn cứ tại trường '{req_key}'.",
                            target=f"reveal_1.{req_key}",
                        )

            if not isinstance(r2_just, dict) and (bible.reveal_2 or not bible.adaptation_context):
                _add_issue(
                    "UNSUPPORTED_REVEAL",
                    "Reveal 2 thiếu cấu trúc chứng minh (reveal_justifications.reveal_2).",
                    target="reveal_2",
                )
            elif isinstance(r2_just, dict):
                for req_key in r2_required:
                    val = r2_just.get(req_key)
                    if not val or str(val).strip().lower() in ("", "none", "false", "unsupported", "không có", "thiếu"):
                        _add_issue(
                            "UNSUPPORTED_REVEAL",
                            f"Reveal 2 không đủ căn cứ tại trường '{req_key}'.",
                            target=f"reveal_2.{req_key}",
                        )

            # A non-empty field is not automatically proof. For high-stakes
            # Rumors and ambiguous signs are leads. An admission can establish
            # a character's own affair, but cannot establish biological identity
            # or a judicial finding. Semantic review checks the actual claim.
            high_stakes_text = " ".join(
                str(value or "") for value in (bible.secret, bible.reveal_1, bible.reveal_2)
            ).lower()
            high_stakes = any(
                marker in high_stakes_text
                for marker in (
                    "ngoại tình", "vụng trộm", "phản bội", "giết", "huyết thống",
                    "cha ruột", "mẹ ruột", "chiếm đoạt", "biển thủ",
                )
            )
            if high_stakes:
                direct_markers = (
                    "ảnh", "video", "camera", "ghi âm", "đoạn hội thoại", "hóa đơn",
                    "đặt phòng", "định vị", "giao dịch", "chứng kiến trực tiếp", "bắt gặp",
                    "xét nghiệm", "adn", "hồ sơ", "chứng từ", "tài liệu gốc",
                    "biên lai", "sao kê", "chuyển khoản", "thỏa thuận", "hợp đồng",
                )
                indirect_markers = (
                    "tin nhắn", "lịch sử cuộc gọi", "lời đồn", "nghe nói",
                    "thay đổi ngoại hình", "đi ăn riêng", "lời thú nhận", "thừa nhận",
                )
                for reveal_key, reveal_data in (("reveal_1", r1_just), ("reveal_2", r2_just)):
                    if not isinstance(reveal_data, dict):
                        continue
                    evidence = str(reveal_data.get("evidence_support", "") or "").lower()
                    reveal_text = str(getattr(bible, reveal_key, '') or '').lower()
                    objective_claim = any(marker in reveal_text for marker in (
                        'huyết thống', 'cha ruột', 'mẹ ruột', 'giết', 'chiếm đoạt', 'biển thủ',
                    ))
                    personal_admission = (
                        not objective_claim
                        and any(marker in reveal_text for marker in ('ngoại tình', 'vụng trộm', 'phản bội', 'quan hệ ngoài hôn nhân', 'vượt quá giới hạn đồng nghiệp'))
                        and any(marker in evidence for marker in ('lời thú nhận', 'thừa nhận', 'thú nhận'))
                        and not any(marker in evidence for marker in ('không thừa nhận', 'không thú nhận'))
                    )
                    if (
                        evidence
                        and any(marker in evidence for marker in indirect_markers)
                        and not any(marker in evidence for marker in direct_markers)
                        and not personal_admission
                    ):
                        _add_issue(
                            "REVEAL_PROOF_OVERCLAIM",
                            f"{reveal_key} chỉ dựa vào dấu hiệu gián tiếp/lời thừa nhận nhưng được dùng như kết luận chắc chắn; cần thêm chi tiết có thể kiểm chứng độc lập.",
                            target=f"{reveal_key}.evidence_support",
                        )
        else:
            # Even if reveal_justifications dict was not explicitly passed, check whether Reveal 1 / Reveal 2
            # are backed by clues, timeline, and character motivation.
            has_evidence = bool(
                (bible.clues and any(str(c).strip() for c in bible.clues))
                or (bible.structured_clues and len(bible.structured_clues) > 0)
                or (bible.critical_facts and len(bible.critical_facts) > 0)
            )
            has_timeline = bool((bible.timeline and any(str(t).strip() for t in bible.timeline)) or bible.critical_facts)
            if (bible.reveal_1 or bible.reveal_2) and not has_evidence:
                _add_issue(
                    "UNSUPPORTED_REVEAL",
                    "Reveal 1 / Reveal 2 hoàn toàn không có manh mối (clues) hỗ trợ trước đó.",
                    target="reveal_1",
                )
            elif (bible.reveal_1 or bible.reveal_2) and not has_timeline:
                _add_issue(
                    "UNSUPPORTED_REVEAL",
                    "Reveal 1 / Reveal 2 không có mốc thời gian (timeline) hoặc sự thật đóng băng hỗ trợ.",
                    target="reveal_1",
                )
            else:
                # Check if reveal_1 or reveal_2 is explicitly disconnected from clues/secret/critical_facts
                facts_text = " ".join(f"{f.value} {f.description}" for f in (bible.critical_facts or []))
                clues_corpus = (
                    " ".join(str(c) for c in (bible.clues or []))
                    + " " + str(bible.secret or "")
                    + " " + " ".join(str(t) for t in (bible.timeline or []))
                    + " " + facts_text
                )
                clues_tokens = {w for w in _tokenize(clues_corpus) if len(w) > 2}
                for rev_label, rev_text in [("reveal_1", bible.reveal_1), ("reveal_2", bible.reveal_2)]:
                    if rev_text and len(str(rev_text).strip()) > 15 and clues_tokens:
                        rev_tokens = {w for w in _tokenize(str(rev_text)) if len(w) > 2}
                        if rev_tokens and len(rev_tokens & clues_tokens) == 0:
                            _add_issue(
                                "UNSUPPORTED_REVEAL",
                                f"{rev_label} đưa ra tình tiết hoàn toàn mới ('{str(rev_text)[:60]}') không có bất kỳ liên kết ngữ nghĩa hay manh mối nào với hệ thống clues/timeline.",
                                target=rev_label,
                            )
        # ------------------------------------------------------------------
        # 5. STORY_BIBLE_TOPIC_DRIFT AUDIT (Topic Gate 2)
        # ------------------------------------------------------------------
        orig_topic = (
            getattr(bible, "original_user_topic", "")
            or getattr(bible, "topic", "")
            or ""
        ).strip()
        topic_intent_dict = getattr(bible, "topic_intent", None)

        if orig_topic and not bible.adaptation_context:
            from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent
            if isinstance(topic_intent_dict, dict) and topic_intent_dict.get("original_topic"):
                ti = TopicIntent.from_dict(topic_intent_dict)
            else:
                ti = extract_topic_intent(orig_topic)

            topic_eval = ti.evaluate_content_adherence(bible, stage="story_bible")
            bible_topic_score = topic_eval["score"]
            if bible_topic_score < 75.0 or getattr(bible, "topic_adherence", None) is None:
                bible.topic_adherence = bible_topic_score
            # Keyword coverage of everyday clues (a train ticket, a receipt) is not
            # topic drift: when the secret and the reveals are squarely on topic and
            # no foreign trope appears, the story is on topic.
            on_topic_core = (
                topic_eval["topic_centrality_score"] >= 80
                and topic_eval["topic_reveal_alignment"] >= 80
                and not topic_eval.get("drift_terms")
            )
            if (topic_eval["status"] != "PASS" or bible_topic_score < 75.0) and not on_topic_core:
                _add_issue(
                    "STORY_BIBLE_TOPIC_DRIFT",
                    f"Story Bible trôi dạt chủ đề: Điểm bám sát chỉ đạt {bible_topic_score}/100 "
                    f"(Centrality: {topic_eval['topic_centrality_score']}, "
                    f"Evidence: {topic_eval['topic_evidence_coverage']}, "
                    f"Reveal: {topic_eval['topic_reveal_alignment']}). "
                    f"Story Bible không duy trì chủ đề gốc '{orig_topic}' làm trọng tâm câu chuyện.",
                    severity="CRITICAL",
                    target="secret",
                )

        # ------------------------------------------------------------------
        # 6. STORY LOGIC QC V3: TEMPORAL FACT GRAPH & RELATIONSHIP LIFECYCLE
        # ------------------------------------------------------------------
        from apps.script_factory.story_logic_v3 import StoryLogicV3Validator
        v3_validator = StoryLogicV3Validator()
        v3_issues = v3_validator.validate_story_bible(bible)
        for v3_iss in v3_issues:
            _add_issue(
                rule=v3_iss["rule"],
                message=v3_iss["message"],
                severity=v3_iss.get("severity", "CRITICAL"),
                target=v3_iss.get("target", "story_bible"),
            )

        # 6.5 PROCEDURAL EVIDENCE in the plot design (camera/statements handed over by
        # a hotel, bank or building). Caught here so the repair redesigns the reveal.
        from apps.script_factory.script_craft import procedural_evidence_hits
        bible_texts = {field: str(getattr(bible, field, "") or "") for field in ("reveal_1", "reveal_2", "secret", "ending")}
        bible_texts["clues"] = " ".join(str(c) for c in (bible.clues or []))
        for field_name, text in bible_texts.items():
            if procedural_evidence_hits([text]):
                _add_issue(
                    "INFEASIBLE_EVIDENCE",
                    f"Trường {field_name} lấy bằng chứng nhờ khách sạn/ngân hàng/tòa nhà/công ty cung cấp dữ liệu riêng cho người hỏi; "
                    "ngoài đời không xảy ra. Thay bằng bằng chứng đời thường (tận mắt thấy, người quen kể, đồ vật, máy dùng chung).",
                    severity="CRITICAL",
                    target=field_name,
                )

        # 6.7 CORE PROP & TRIGGER CONSISTENCY
        # Verifies physical prop and location consistency between title, narrative_skeleton.trigger,
        # clues, timeline, and reveals/ending.
        title_str = str(bible.title or "").strip()
        skeleton_dict = bible.narrative_skeleton if isinstance(bible.narrative_skeleton, dict) else {}
        trigger_str = str(skeleton_dict.get("trigger", "") or "").strip()

        prop_catalog = [
            "áo khoác", "áo sơ mi", "áo len", "áo mưa", "áo", "kẹp tóc", "chiếc kẹp", "kẹp",
            "son môi", "thỏi son", "vết son", "son", "chìa khóa", "bức thư", "lá thư", "thư",
            "sổ tay", "cuốn sổ", "quyển sổ", "sổ", "nhẫn cưới", "chiếc nhẫn", "nhẫn",
            "hóa đơn", "biên lai", "vali", "chiếc vali", "điện thoại", "tin nhắn", "đồng hồ",
            "khăn tay", "chiếc khăn", "khăn", "bức ảnh", "tấm ảnh", "ảnh", "chiếc hộp", "hộp quà", "hộp",
            "hồ sơ", "tập hồ sơ", "bộ hồ sơ", "vé máy bay", "vé tàu", "cà vạt", "mùi hương", "nước hoa",
            "vòng tay", "dây chuyền", "sợi tóc", "thẻ ngân hàng", "ví tiền", "ví", "túi xách",
        ]
        prop_catalog.sort(key=lambda p: len(p), reverse=True)

        location_catalog = [
            ("xe", [r"\bxe\b", r"\bô tô\b", r"\bcốp xe\b", r"\bghế phụ\b", r"\bghế sau\b", r"\bgầm ghế\b"]),
            ("phòng họp", [r"\bphòng họp\b", r"\bcuối tầng\b"]),
            ("văn phòng", [r"\bvăn phòng\b", r"\bbàn làm việc\b", r"\bngăn kéo\b", r"\bcông ty\b"]),
            ("phòng ngủ", [r"\bphòng ngủ\b", r"\bđầu giường\b", r"\btủ quần áo\b", r"\bgầm giường\b"]),
            ("khách sạn", [r"\bkhách sạn\b", r"\bnhà nghỉ\b", r"\bphòng nghỉ\b"]),
            ("quán cà phê", [r"\bquán cà phê\b", r"\bquán nước\b", r"\bquán ăn\b", r"\bnhà hàng\b"]),
            ("nhà kho", [r"\bnhà kho\b", r"\bnhà cũ\b", r"\bgác xép\b"]),
            ("bệnh viện", [r"\bbệnh viện\b", r"\bphòng khám\b", r"\bviện\b"]),
        ]

        def _find_primary_prop(text: str) -> Optional[str]:
            matches = []
            for p in prop_catalog:
                from apps.script_factory.story_contract import physical_prop_mention
                m = next((m for m in re.finditer(r"\b" + re.escape(p) + r"\b", text, re.IGNORECASE)
                          if not bible.adaptation_context or physical_prop_mention(p,text,m.start(),m.end())),None)
                if m:
                    is_container = bool(re.search(r"\b(trong|dưới|sau|ở|tại)\s+(?:túi\s+|cốp\s+|ngăn\s+|hộp\s+)?" + re.escape(p) + r"\b", text, re.IGNORECASE))
                    matches.append((1 if is_container else 0, m.start(), -len(p), p))
            matches.sort()
            return matches[0][3] if matches else None

        prop_in_title = _find_primary_prop(title_str)
        prop_in_trigger = _find_primary_prop(trigger_str)

        loc_in_title = next(
            (loc_name for loc_name, loc_pats in location_catalog if any(re.search(pat, title_str, re.IGNORECASE) for pat in loc_pats)),
            None
        )
        loc_in_trigger = next(
            (loc_name for loc_name, loc_pats in location_catalog if any(re.search(pat, trigger_str, re.IGNORECASE) for pat in loc_pats)),
            None
        )

        if loc_in_title and loc_in_trigger and loc_in_title != loc_in_trigger:
            title_pats = next(pats for name, pats in location_catalog if name == loc_in_title)
            if not any(re.search(pat, trigger_str, re.IGNORECASE) for pat in title_pats):
                _add_issue(
                    "PROP_LOCATION_CONTRADICTION",
                    f"Địa điểm xuất hiện của vật chứng mâu thuẫn: Tiêu đề đặt ở '{loc_in_title}', nhưng narrative_skeleton.trigger đặt ở '{loc_in_trigger}'. Cần thống nhất nơi phát hiện.",
                    severity="CRITICAL",
                    target="narrative_skeleton.trigger",
                )

        if prop_in_title and prop_in_trigger and prop_in_title != prop_in_trigger:
            if not re.search(r"\b" + re.escape(prop_in_title) + r"\b", trigger_str, re.IGNORECASE):
                _add_issue(
                    "CORE_PROP_CONTRADICTION",
                    f"Tiêu đề hứa hẹn vật chứng '{prop_in_title}', nhưng Trigger lại khởi đầu bằng vật chứng '{prop_in_trigger}' mà không kết nối; cốt truyện bị phân mảnh ngay từ đầu.",
                    severity="CRITICAL",
                    target="title",
                )

        primary_prop = prop_in_title or prop_in_trigger
        if primary_prop:
            prop_stem = re.sub(r"^(chiếc|tấm|bức|lá|cuốn|quyển|bộ|tập)\s+", "", primary_prop).strip()
            prop_pats = [r"\b" + re.escape(primary_prop) + r"\b"]
            if prop_stem and prop_stem != primary_prop:
                prop_pats.append(r"\b" + re.escape(prop_stem) + r"\b")

            clues_text = " ".join(str(c) for c in (bible.clues or [])) + " " + json.dumps(bible.structured_clues or [], ensure_ascii=False)
            timeline_text = " ".join(str(t) for t in (bible.timeline or []))
            resolution_text = f"{bible.reveal_1} {bible.reveal_2} {bible.secret} {bible.ending}".lower()
            if bible.adaptation_context:
                # Life/factual stories may resolve their hook in a reported action
                # inside the timeline. Full source/semantic review still verifies
                # whether that action actually answers the promise.
                resolution_text += ' ' + timeline_text.lower()

            in_clues = any(re.search(pat, clues_text, re.IGNORECASE) for pat in prop_pats)
            in_timeline = any(re.search(pat, timeline_text, re.IGNORECASE) for pat in prop_pats)
            in_resolution = any(re.search(pat, resolution_text, re.IGNORECASE) for pat in prop_pats)

            if not (in_clues or in_timeline):
                _add_issue(
                    "UNRESOLVED_CORE_PROP",
                    f"Vật chứng cốt lõi '{primary_prop}' trong Tiêu đề/Trigger không được đưa vào chuỗi manh mối (clues hoặc timeline) để nhân vật kiểm chứng.",
                    severity="CRITICAL",
                    target="clues",
                )
            if not in_resolution:
                _add_issue(
                    "UNRESOLVED_CORE_PROP",
                    f"Vật chứng cốt lõi '{primary_prop}' không có lời giải đáp hoặc hồi đáp trong Bước ngoặt (reveal_1, reveal_2) hay Kết thúc (ending).",
                    severity="CRITICAL",
                    target="reveal_2",
                )

        # 7. SEMANTIC PLOT LOGIC (LLM): reveals the narrator cannot know, illegal
        # endings, verdicts without proof. Feeds the existing AI repair rounds.
        source_qc = None
        if bible.adaptation_context and self.provider:
            from apps.script_factory.adaptation import source_review, valid_source_review
            stored_source = ((bible.story_qc_report or {}).get('semantic_review') or {}).get('source_review')
            if (valid_source_review(bible, stored_source) and all(
                    r.get('provider_name') == self.provider.provider_name
                    and r.get('requested_model') == self.provider.default_model for r in stored_source['reviews'])):
                source_qc = stored_source
            else:
                source_qc = source_review(self.provider, bible)
            if source_qc['status'] != 'RUN':
                _add_issue('SEMANTIC_REVIEW_FAILED', source_qc.get('error', 'Source review chưa đủ'), target='story_bible')
            for issue in source_qc.get('issues', []):
                _add_issue(issue['rule'], issue['message'], target=issue['target'])
        semantic = self._semantic_bible_review(bible)
        if source_qc and semantic:
            semantic['source_review'] = source_qc
        if semantic and semantic.get("status") == "ERROR":
            _add_issue(
                rule="SEMANTIC_REVIEW_FAILED",
                message=f"Kiểm tra semantic logic Story Bible thất bại: {semantic.get('error')}",
                severity="CRITICAL",
                target="story_bible",
            )
        for sem_issue in (semantic or {}).get("issues", []):
            _add_issue(
                rule=sem_issue["rule"],
                message=f"{sem_issue['message']} (Trích: \"{sem_issue['excerpt']}\")",
                severity="CRITICAL",
                target=sem_issue.get("target", "story_bible"),
            )

        status = "PASS" if not issues else "FAIL"
        if status == "FAIL":
            bible.status = ApprovalStatus.NEEDS_LOGIC_REWRITE.value

        report = StoryBibleQCReport(
            episode_id=bible.episode_id,
            status=status,
            issues=issues,
            logic_issues=logic_issues,
            rule_codes=rule_codes,
            semantic_review=semantic,
        )
        bible.story_qc_report = report.to_dict()
        return report

    def repair_story_bible(
        self,
        bible: StoryBible,
        report: Optional[StoryBibleQCReport] = None,
        provider: Optional[Any] = None,
    ) -> StoryBible:
        """
        Repairs StoryBible causal gaps, knowledge contradictions, evidence jumps,
        and missing reveal justifications.
        Delegates creative repair to AI provider when available to prevent template leakage.
        """
        if report is None:
            report = self.audit_story_bible(bible)

        if bible.adaptation_context and (report.status == 'PASS' or not (provider or self.provider)):
            # Source profiles must never enter legacy schema/template filling.
            # Missing creative structure requires real AI repair, not invented facts.
            bible.story_qc_report = report.to_dict()
            return bible

        # Transport/decoder failures say nothing about the plot. Do not rewrite
        # a draft merely because its reviewer was unavailable.
        if report.issues and all(issue.get('rule') == 'SEMANTIC_REVIEW_FAILED' for issue in report.issues):
            bible.story_qc_report = report.to_dict()
            return bible

        if "HOST_CHARACTER_NAME_COLLISION" in report.rule_codes:
            used_names = {
                str(character.get("name", "")).strip().casefold()
                for character in (bible.supporting_characters or [])
                if isinstance(character, dict)
            }
            used_names.add(
                str(bible.protagonist.get("name", "")).strip().casefold()
                if isinstance(bible.protagonist, dict)
                else str(bible.protagonist or "").strip().casefold()
            )
            replacement = next(
                name for name in ("Khải", "Quân", "Duy", "Nam")
                if name.casefold() not in used_names
            )

            def _rename_reserved_character(value: Any) -> Any:
                if isinstance(value, dict):
                    return {key: _rename_reserved_character(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [_rename_reserved_character(item) for item in value]
                if isinstance(value, str):
                    if value == "MINH":
                        return replacement.upper()
                    return re.sub(r"\bMinh\b", replacement, value, flags=re.IGNORECASE)
                return value

            bible = StoryBible.from_dict(_rename_reserved_character(bible.to_dict()))
            report = self.audit_story_bible(bible)

        active_provider = provider or self.provider
        if active_provider and hasattr(active_provider, "repair_story_bible") and report.issues:
            cur_bible = bible
            cur_report = report
            best_bible, best_report = copy.deepcopy(bible), report
            from apps.script_factory.semantic_review import story_bible_content_hash
            seen = {story_bible_content_hash(bible)}
            stalled = 0
            def severity(report):
                return (report.status != 'PASS', sum(i.get('severity') == 'CRITICAL' for i in report.issues), len(report.issues))
            def problem_keys(report):
                return {(i.get('rule'), i.get('target')) for i in report.issues}
            round_issues = list(report.issues)
            for round_idx in range(3):
                try:
                    logger.info(f"[StoryQCEngine] Running AI repair round {round_idx + 1}/3 with {len(cur_report.issues)} issues...")
                    targets = {
                        str(iss.get("target")) for iss in cur_report.issues
                        if isinstance(iss, dict) and iss.get("target") and hasattr(cur_bible, str(iss.get("target")))
                    }
                    before = {t: json.dumps(getattr(cur_bible, t), ensure_ascii=False, default=str) for t in targets}
                    repaired, _, _ = active_provider.repair_story_bible(copy.deepcopy(cur_bible), round_issues)
                    untouched = sorted(
                        t for t in targets
                        if json.dumps(getattr(repaired, t), ensure_ascii=False, default=str) == before[t]
                    )
                    recheck = self.audit_story_bible(repaired)
                    repaired.story_qc_report = recheck.to_dict()
                    for issue in recheck.issues:
                        logger.info('[StoryQC %s] %s', issue.get('rule'), issue.get('message'))
                    if recheck.issues and all(issue.get('rule') == 'SEMANTIC_REVIEW_FAILED' for issue in recheck.issues):
                        repaired.story_qc_report = recheck.to_dict()
                        return repaired
                    if recheck.status == 'PASS':
                        return repaired
                    fingerprint = story_bible_content_hash(repaired)
                    repeated = fingerprint in seen
                    changed_problems = problem_keys(recheck) != problem_keys(cur_report)
                    if not repeated and (severity(recheck) < severity(best_report) or (
                        severity(recheck) == severity(best_report) and changed_problems
                    )):
                        best_bible, best_report = copy.deepcopy(repaired), recheck
                    if not repeated and (severity(recheck) < severity(cur_report) or (
                        severity(recheck) == severity(cur_report) and changed_problems
                    )):
                        stalled = 0
                    else:
                        stalled += 1
                    if repeated or stalled >= 2:
                        logger.warning('[StoryQCEngine] Repair stopped: repeated content or no QC improvement; retaining best draft.')
                        return best_bible
                    seen.add(fingerprint)
                    cur_bible = repaired
                    cur_report = recheck
                    logger.info(
                        f"[StoryQCEngine] Sau vòng sửa {round_idx + 1}: {recheck.status}"
                        + (f" — còn {', '.join(recheck.rule_codes)}" if recheck.rule_codes else "")
                    )
                    if recheck.status == "PASS" or not any(iss.get("severity") == "CRITICAL" for iss in recheck.issues):
                        logger.info(f"[StoryQCEngine] AI repair round {round_idx + 1} passed (status: {recheck.status})!")
                        return cur_bible
                    # Models told "do not change the plot" often return the flagged
                    # field verbatim; say so explicitly in the next round.
                    round_issues = list(recheck.issues)
                    if untouched:
                        logger.warning(f"[StoryQCEngine] AI không sửa trường bị báo lỗi: {', '.join(untouched)}")
                        round_issues += [
                            {
                                "rule": "FIELD_NOT_REPAIRED",
                                "severity": "CRITICAL",
                                "target": field_name,
                                "message": (
                                    f"Vòng sửa trước KHÔNG thay đổi trường '{field_name}' nên lỗi vẫn còn. BẮT BUỘC viết lại "
                                    f"nội dung trường '{field_name}' (giữ ý chính của câu chuyện) để khắc phục các lỗi nhắm vào nó."
                                ),
                            }
                            for field_name in untouched
                        ]
                except Exception as e:
                    logger.warning(f"[StoryQCEngine] Provider repair_story_bible round {round_idx + 1} failed: {e}.")
                    break
            return best_bible

        protag_name = (
            bible.protagonist.get("name", "Nhân vật")
            if isinstance(bible.protagonist, dict)
            else str(bible.protagonist or "Nhân vật")
        )
        supp_name = (
            bible.supporting_characters[0].get("name", "Người thân")
            if bible.supporting_characters and isinstance(bible.supporting_characters[0], dict)
            else "Người liên quan"
        )

        # 1. Populate causal_chains from existing Story Bible fields if missing
        if not bible.causal_chains:
            bible.causal_chains = [
                {
                    "target": "reveal_1",
                    "cause": f"Biến cố quá khứ liên quan đến {bible.secret[:80]}.",
                    "decision": f"Quyết định của {supp_name} nhằm bảo vệ {protag_name} khỏi biến cố.",
                    "action": (
                        str(bible.reveal_1)
                        if len(str(bible.reveal_1 or "").strip()) >= 10
                        else f"Thực hiện cam kết bảo vệ gia đình ({bible.reveal_1 or 'Bước ngoặt 1'})."
                    ),
                    "consequence": f"{protag_name} hiểu lầm tình huống ban đầu trước khi đối chiếu chứng cứ gốc.",
                    "why": "Bảo vệ sự an toàn và danh dự cho người thân trong gia đình.",
                    "motivation": "Không thể công khai ngay lúc đó do ràng buộc hoàn cảnh và bảo vệ tâm lý người trong cuộc.",
                    "how": "Duy trì qua sự giữ kín và thỏa thuận giữa những người trực tiếp liên quan.",
                },
                {
                    "target": "reveal_2",
                    "cause": f"Hoàn cảnh bất khả kháng khiến {supp_name} phải gánh vác trách nhiệm thầm lặng.",
                    "decision": f"Chấp nhận giữ im lặng để giữ vững sự bình yên cho gia đình và {protag_name}.",
                    "action": (
                        str(bible.reveal_2)
                        if len(str(bible.reveal_2 or "").strip()) >= 10
                        else f"Duy trì bí mật qua thời gian ({bible.reveal_2 or bible.secret or 'Bước ngoặt 2'})."
                    ),
                    "consequence": "Tạo nên uẩn khúc chỉ được tháo gỡ khi toàn bộ chứng cứ được làm rõ.",
                    "why": "Nếu công khai sai thời điểm sẽ dẫn đến đổ vỡ không thể cứu vãn.",
                    "motivation": "Giải pháp thông thường là bất khả thi trong bối cảnh thực tế lúc xảy ra biến cố.",
                    "how": "Thực hiện nhất quán qua từng giai đoạn với sự thấu hiểu của các nhân chứng then chốt.",
                },
            ]

        # 2. Repair CHARACTER_KNOWLEDGE_CONTRADICTION
        if "CHARACTER_KNOWLEDGE_CONTRADICTION" in report.rule_codes or not bible.knowledge_ledger:
            for attr in ("secret", "reveal_1", "reveal_2"):
                val = getattr(bible, attr, "")
                if val:
                    val = re.sub(
                        r"không\s+một\s+ai\s+(?:hay\s+)?biết|không\s+thể\s+sẻ\s+chia\s+cùng\s+ai(?:\s+kể\s+cả\s+(?:với\s+)?người\s+vợ(?:\s+gối\s+chăn)?)?",
                        "chỉ được giữ kín giữa những người trực tiếp liên quan",
                        val,
                        flags=re.IGNORECASE,
                    )
                    setattr(bible, attr, val)

            ledger: List[Dict[str, Any]] = [
                {
                    "character": protag_name,
                    "who_knows_what": f"{protag_name} ban đầu chỉ nhận thấy dấu hiệu bất thường, chưa rõ toàn bộ sự thật.",
                    "when_they_learned_it": "Khi xác minh chuỗi manh mối và đối thoại trực tiếp ở phần cao trào.",
                    "how_they_learned_it": "Thông qua chuỗi manh mối thực tế và lời xác nhận của người trong cuộc.",
                    "knowledge_scope": "none",
                }
            ]
            for sc in (bible.supporting_characters or []):
                if not isinstance(sc, dict):
                    continue
                sc_name = str(sc.get("name", "") or sc.get("char_id", "Người thân")).strip()
                sc_desc = " ".join(str(sc.get(k, "")) for k in ("description", "role", "reason_for_silence")).lower()
                knows_all = any(p in sc_desc for p in ["biết toàn bộ", "biết sự thật", "biết rõ", "biết hết", "người nắm giữ bí mật"])
                ledger.append({
                    "character": sc_name,
                    "who_knows_what": f"{sc_name} nắm rõ nguyên nhân và diễn biến biến cố." if knows_all else f"{sc_name} biết một phần sự việc và chọn giữ im lặng.",
                    "when_they_learned_it": "Từ thời điểm biến cố khởi phát.",
                    "how_they_learned_it": "Trực tiếp trải qua hoặc cùng giải quyết biến cố.",
                    "knowledge_scope": "full" if knows_all else "partial",
                })
            bible.knowledge_ledger = ledger

        # 3. Repair EVIDENCE_DOES_NOT_PROVE_CLAIM
        if "EVIDENCE_DOES_NOT_PROVE_CLAIM" in report.rule_codes or not bible.structured_clues:
            raw_clues = bible.clues if (bible.clues and len(bible.clues) >= 3) else [
                "Dấu hiệu hoặc tài liệu ban đầu làm nảy sinh nghi vấn.",
                "Chi tiết hoặc nhân chứng thứ hai làm rõ mốc thời gian liên quan.",
                "Hồ sơ hoặc lời xác nhận trực tiếp làm sáng tỏ nguyên nhân cốt lõi.",
            ]
            cleaned_clues = []
            for rc in raw_clues:
                c_str = re.sub(
                    r"(?:chứng\s+minh\s+hoàn\s+toàn|khẳng\s+định\s+chắc\s+chắn|đủ\s+để\s+kết\s+luận)",
                    "đặt ra nghi vấn cần xác minh thêm về",
                    str(rc),
                    flags=re.IGNORECASE,
                )
                cleaned_clues.append(c_str)
            bible.clues = cleaned_clues

            bible.structured_clues = [
                {
                    "clue": cleaned_clues[0],
                    "what_it_proves": f"Xác nhận có dấu hiệu bất thường liên quan đến {cleaned_clues[0][:50]}.",
                    "what_it_does_NOT_prove": "Chưa đủ để kết luận động cơ hay toàn bộ sự thật cuối cùng.",
                    "next_question": "Nguồn gốc thực sự của chi tiết này xuất phát từ đâu?",
                },
                {
                    "clue": cleaned_clues[1] if len(cleaned_clues) > 1 else cleaned_clues[0],
                    "what_it_proves": f"Xác nhận mối liên hệ giữa các mốc sự kiện và người liên quan.",
                    "what_it_does_NOT_prove": "Chưa làm rõ được động cơ sâu kín của người trong cuộc.",
                    "next_question": "Sự thật đằng sau thỏa thuận này là gì?",
                },
                {
                    "clue": cleaned_clues[2] if len(cleaned_clues) > 2 else cleaned_clues[-1],
                    "what_it_proves": f"Xác nhận đầy đủ nguyên nhân dẫn tới Bước ngoặt 1 ({str(bible.reveal_1)[:60]}).",
                    "what_it_does_NOT_prove": "Bác bỏ hoàn toàn giả thuyết sai lầm ban đầu.",
                    "next_question": "Gia đình và các nhân vật sẽ đối diện và hóa giải uẩn khúc này ra sao?",
                },
            ]

        # 4. Repair UNSUPPORTED_REVEAL
        if "UNSUPPORTED_REVEAL" in report.rule_codes or not bible.reveal_justifications:
            if not bible.clues:
                if bible.structured_clues:
                    bible.clues = [sc["clue"] for sc in bible.structured_clues]
                else:
                    bible.clues = [
                        f"Tài liệu và chứng từ ghi chép liên quan đến biến cố của {protag_name}",
                        "Cuộc trao đổi then chốt giữa các nhân vật chính",
                        "Vật chứng xác minh sự thật tại hiện trường",
                    ]

            if not bible.timeline:
                bible.timeline = [
                    f"Biến cố ban đầu xảy ra trong quá khứ liên quan tới {protag_name}",
                    "Giai đoạn nảy sinh nghi vấn và che giấu sự thật",
                    "Thời điểm sự thật được phát hiện và làm sáng tỏ",
                ]

            first_clue = bible.clues[0] if bible.clues else "Manh mối xác thực"
            bible.reveal_justifications = {
                "reveal_1": {
                    "evidence_support": f"Được hỗ trợ bởi các manh mối xác minh: '{str(first_clue)[:50]}'.",
                    "motivation_support": f"Xuất phát từ hoàn cảnh thực tế và mong muốn bảo vệ {protag_name}.",
                    "timeline_support": "Khớp nối hợp lý với các mốc thời gian diễn ra biến cố.",
                },
                "reveal_2": {
                    "evidence_support": f"Được xác nhận bởi manh mối then chốt và sự thật từ người trong cuộc.",
                    "motivation_support": "Do hoàn cảnh khách quan khiến giải pháp thông thường không thể thực hiện.",
                    "character_knowledge_support": "Nhất quán với sổ cái nhận thức nhân vật (knowledge_ledger).",
                },
            }

        bible.status = ApprovalStatus.DRAFT.value
        recheck = self.audit_story_bible(bible)
        bible.story_qc_report = recheck.to_dict()
        return bible


def _has_necessity_markers(text_lower: str) -> bool:
    markers = [
        "bất khả kháng",
        "không còn cách nào khác",
        "phương án duy nhất",
        "cách duy nhất",
        "buộc phải",
        "nếu không",
        "giấy báo tử ghi nhầm",
        "thất lạc hồ sơ",
        "hồ sơ duy nhất",
        "nguy kịch tính mạng",
        "đe dọa tính mạng",
        "ràng buộc pháp lý",
        "bảo toàn tính mạng",
        "không thể thực hiện giải pháp thông thường",
        "giải pháp thông thường là bất khả thi",
    ]
    return any(m in text_lower for m in markers)


def _has_weak_cause_to_extreme_action(text_lower: str, has_strong_necessity: bool = False) -> bool:
    if has_strong_necessity:
        return False
    extreme_actions = [
        r"đổi\s+(?:luôn\s+)?danh\s+tính",
        r"sống\s+(?:suốt\s+)?(?:\d+\s+năm\s+)?dưới\s+danh\s+tính",
        r"sống\s+dưới\s+tên",
        r"mang\s+danh\s+tính\s+của",
        r"giả\s+danh\s+người\s+đã\s+khuất",
        r"mạo\s+danh\s+suốt",
        r"xóa\s+bỏ\s+tên\s+thật",
        r"đi\s+tù\s+thay\s+\d+\s+năm",
        r"giả\s+chết\s+suốt\s+\d+\s+năm",
    ]
    weak_causes = [
        r"nhờ\s+.*mang\s+(?:hộ\s+)?thẻ\s+bài",
        r"mang\s+thẻ\s+bài.*chăm\s+sóc\s+mẹ",
        r"nhờ\s+chăm\s+sóc\s+mẹ\s+già",
        r"nhờ\s+gửi\s+lại\s+kỷ\s+vật",
        r"nhờ\s+mang\s+giấy\s+tờ\s+về\s+quê",
        r"chỉ\s+vì\s+lời\s+nhờ\s+vả",
        r"vì\s+lời\s+dặn\s+mang\s+kỷ\s+vật",
    ]
    has_extreme = any(re.search(p, text_lower) for p in extreme_actions)
    has_weak = any(re.search(p, text_lower) for p in weak_causes)
    return bool(has_extreme and has_weak)


def _is_overreaching_clue_claim(clue_text: str, proves_text: str) -> bool:
    clue_low = clue_text.lower()
    proves_low = proves_text.lower()
    single_item_indicators = [
        "thẻ bài", "bức ảnh", "chữ ký", "số điện thoại", "mảnh giấy",
        "chiếc đồng hồ", "phong bì", "dòng chữ", "vết sẹo", "cuốn sổ",
    ]
    extreme_conclusions = [
        "đã đánh tráo danh tính",
        "chính là kẻ giả mạo",
        "không phải là ông nội thật",
        "không phải là cha ruột",
        "đã giết",
        "đã chiếm đoạt toàn bộ tài sản",
        "đã phản bội gia đình suốt",
        "chứng minh ông đã mạo danh",
    ]
    has_single_item = any(ind in clue_low for ind in single_item_indicators)
    has_extreme_claim = any(ec in proves_low for ec in extreme_conclusions)
    has_restraint = any(r in proves_low for r in ["chỉ chứng minh", "chưa chứng minh", "đặt ra nghi vấn", "cần xác minh"])
    return bool(has_single_item and has_extreme_claim and not has_restraint)


def _is_overreaching_raw_clue(raw_clue: str) -> bool:
    low = raw_clue.lower()
    overreach_patterns = [
        r"(?:thẻ\s+bài|chữ\s+ký|bức\s+ảnh|mảnh\s+giấy|số\s+điện\s+thoại).*?(?:chứng\s+minh\s+hoàn\s+toàn|khẳng\s+định\s+chắc\s+chắn|đủ\s+để\s+kết\s+luận).*?(?:giả\s+mạo|đánh\s+tráo\s+danh\s+tính|phản\s+bội|chiếm\s+đoạt)",
    ]
    return any(re.search(p, low) for p in overreach_patterns)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower(), re.UNICODE))

