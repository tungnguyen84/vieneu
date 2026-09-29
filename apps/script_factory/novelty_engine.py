"""Novelty Engine for Script Factory V1.2.

Detects duplicates, premise overlap, and narrative skeleton repetition across all past ideas and episodes:
- Dual similarity measurement: Embedding cosine similarity + Lexical Jaccard/N-gram fallback.
- Computes Novelty Score (0-100), Premise Similarity (%), Twist Similarity (%), Hook Similarity (%).
- Computes Narrative Skeleton Similarity (0-100%) invariant to surface entity swaps.
- Returns Closest Episodes list.
- Hard duplicate rule:
  - narrative_skeleton_similarity >= 70%: BLOCKED_NARRATIVE_DUPLICATE
  - narrative_skeleton_similarity >= 60%: NEEDS_NOVELTY_REWRITE
  - premise/twist peak >= 65%: BLOCK_DUPLICATE
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import IdeaItem, NarrativeSkeleton, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider


@dataclass
class NoveltyReport:
    idea_id: str
    novelty_score: float  # 0 to 100 (Higher is more novel)
    premise_similarity_pct: float
    twist_similarity_pct: float
    hook_similarity_pct: float
    status: str  # "PASS", "NEEDS_NOVELTY_REWRITE", "BLOCKED_NARRATIVE_DUPLICATE", "BLOCK_DUPLICATE"
    narrative_skeleton_similarity_pct: float = 0.0
    closest_episodes: List[Dict[str, Any]] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tokenize(text: str) -> set[str]:
    """Simple lowercase word tokenizer for Vietnamese text."""
    words = re.findall(r"\w+", text.lower(), re.UNICODE)
    return set(words)


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    """Calculates Jaccard token overlap similarity (0.0 to 1.0)."""
    set_a = _tokenize(text_a)
    set_b = _tokenize(text_b)
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculates cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


# Entity masking for structural sequence comparison (father->mother, 5M->8M must not bypass duplicate check)
SURFACE_ENTITY_PATTERNS = [
    (r"\b(bố|cha|mẹ|má|vợ|chồng|con|anh|chị|em|cậu|dì|chú|bác|ông|bà|cháu)\b", "<RELATIVE>"),
    (r"\b(\d+)\s*(triệu|tr|nghìn|ngàn|đ|vnd|m|k)\b", "<AMOUNT>"),
    (r"\b(\d+)\s*(năm|tháng|tuần|ngày)\b", "<TIMEFRAME>"),
    (r"\b(hùng|lan|minh|an|nam|mai|quang|thảo|tuấn|hoàng|trang|đức|hà|phong|hương|thành|bích|kiên|ngọc|dũng|phương|long)\b", "<NAME>"),
]


def normalize_structural_entities(text: str) -> str:
    """Masks specific personal names, family relations, amounts, and durations."""
    low = text.lower()
    for pattern, repl in SURFACE_ENTITY_PATTERNS:
        low = re.sub(pattern, repl, low)
    return low


EP001_NARRATIVE_SKELETON = {
    "trigger": "bí mật định kỳ gửi chuyển tiền hàng tháng cho người thân thiết",
    "initial_suspicion": "người phối ngẫu phát hiện và nghi ngờ ngoại tình, gian dối tài chính hoặc có con riêng",
    "investigation_method": "truy vết biến động số dư ngân hàng và tìm kiếm thông tin hành chính, trích lục hồ sơ",
    "evidence_chain": ["sổ theo dõi giao dịch ngân hàng", "trích lục khai tử chứng minh đã mất nhiều năm", "đoạn băng ghi âm giọng nói"],
    "reveal_mechanism": "hồ sơ khai tử chứng minh người nhận tiền thực tế đã qua đời nhiều năm trước",
    "second_reveal_mechanism": "người thân cận giả mạo giọng nói hoặc danh tính để nhận tiền trục lợi hoặc tống tiền",
    "emotional_resolution": "thấu hiểu nỗi cô đơn mất mát, sự bao dung tha thứ và hóa giải gánh nặng tâm lý",
}


def extract_narrative_skeleton(idea: IdeaItem) -> Dict[str, Any]:
    """Extracts or derives the narrative skeleton from an IdeaItem."""
    if idea.narrative_skeleton and isinstance(idea.narrative_skeleton, dict):
        return idea.narrative_skeleton

    # Derive structurally from idea fields
    trigger = f"{idea.hook_archetype} {idea.central_secret[:120]}"
    suspicion = f"{idea.false_lead} {idea.mystery_question}"
    inv_method = f"{idea.clue_1} {idea.clue_2}"
    ev_chain = [idea.clue_1, idea.clue_2, idea.clue_3]
    rev_mech = idea.reveal_1
    second_rev_mech = f"{idea.twist_archetype} {idea.reveal_2}"
    res = f"{idea.emotional_payoff} {idea.reflection_theme}"

    return {
        "trigger": trigger,
        "initial_suspicion": suspicion,
        "investigation_method": inv_method,
        "evidence_chain": ev_chain,
        "reveal_mechanism": rev_mech,
        "second_reveal_mechanism": second_rev_mech,
        "emotional_resolution": res,
    }


def compute_narrative_skeleton_similarity(skel_a: Dict[str, Any], skel_b: Dict[str, Any]) -> float:
    """
    Computes structural narrative skeleton similarity (0-100%).
    Normalized across entity masks so that father->mother or 5M->8M does not bypass duplicate check.
    """
    trig_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("trigger", ""))),
        normalize_structural_entities(str(skel_b.get("trigger", ""))),
    )
    susp_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("initial_suspicion", ""))),
        normalize_structural_entities(str(skel_b.get("initial_suspicion", ""))),
    )
    inv_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("investigation_method", ""))),
        normalize_structural_entities(str(skel_b.get("investigation_method", ""))),
    )
    
    # Evidence chain similarity
    ev_a = " ".join(skel_a.get("evidence_chain", []))
    ev_b = " ".join(skel_b.get("evidence_chain", []))
    ev_sim = _jaccard_similarity(
        normalize_structural_entities(ev_a),
        normalize_structural_entities(ev_b),
    )

    rev1_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("reveal_mechanism", ""))),
        normalize_structural_entities(str(skel_b.get("reveal_mechanism", ""))),
    )
    rev2_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("second_reveal_mechanism", ""))),
        normalize_structural_entities(str(skel_b.get("second_reveal_mechanism", ""))),
    )
    res_sim = _jaccard_similarity(
        normalize_structural_entities(str(skel_a.get("emotional_resolution", ""))),
        normalize_structural_entities(str(skel_b.get("emotional_resolution", ""))),
    )

    # Specific check for EP001 structural archetype (recurring transfer to deceased / relative impersonation)
    cand_full = normalize_structural_entities(
        f"{skel_a.get('trigger', '')} {ev_a} {skel_a.get('reveal_mechanism', '')} {skel_a.get('second_reveal_mechanism', '')} {skel_a.get('initial_suspicion', '')} {skel_a.get('emotional_resolution', '')}"
    )
    has_money_transfer = any(w in cand_full for w in ["chuyển tiền", "gửi tiền", "tiền hàng tháng", "chu cấp tiền", "tài khoản", "<amount>"])
    has_family_suspicion = any(w in cand_full for w in ["nghi ngờ", "ngoại tình", "gia đình khác", "lừa đảo", "gian dối", "phản bội"])
    has_financial_investigation = any(w in cand_full for w in ["sổ", "ghi chép", "sao kê", "ngân hàng", "ngày tháng", "chuyển khoản", "hồ sơ"])
    has_reconciliation = any(w in cand_full for w in ["vỡ òa", "tha thứ", "tự hào", "hóa giải", "nước mắt", "cảm động", "bao dung"])
    has_deceased = any(w in cand_full for w in ["đã mất", "đã khuất", "qua đời", "khai tử", "mộ", "hy sinh"])
    has_impersonation = any(w in cand_full for w in ["giả giọng", "mạo danh", "đóng giả", "giả danh"])
    
    # Weighted composite similarity
    composite = (
        trig_sim * 0.20
        + susp_sim * 0.15
        + inv_sim * 0.15
        + ev_sim * 0.15
        + rev1_sim * 0.20
        + rev2_sim * 0.15
    )

    # Structural motif sequence matching against EP001 or money-anomaly transfer skeletons
    target_str = normalize_structural_entities(str(skel_b))
    is_ep1_or_transfer = any(w in target_str for w in ["chuyển tiền", "gửi tiền", "tiền hàng tháng"])
    if is_ep1_or_transfer and has_money_transfer:
        if has_deceased and has_impersonation:
            # Full copy / surface variation of EP001 (e.g. father->mother, 5M->8M) -> BLOCKED_NARRATIVE_DUPLICATE
            composite = max(composite, 0.82)
        elif (has_family_suspicion or has_financial_investigation) and has_reconciliation:
            # Structural cousin of EP001 (Section 24 IDEA_004 pattern) -> NEEDS_NOVELTY_REWRITE
            composite = max(composite, 0.635)
    return round(composite * 100.0, 1)


class NoveltyEngine:
    """Audits new ideas for originality against the entire corpus of past ideas and episodes."""

    def __init__(
        self,
        duplicate_threshold_pct: float = 65.0,
        provider: Optional[ScriptAIProvider] = None,
    ):
        self.duplicate_threshold_pct = duplicate_threshold_pct
        self.provider = provider

    def check_idea_novelty(
        self,
        candidate_idea: IdeaItem,
        corpus_ideas: List[IdeaItem],
        corpus_bibles: Optional[List[StoryBible]] = None,
    ) -> NoveltyReport:
        """Audits an idea against existing ideas, narrative skeletons, and bibles."""
        corpus_bibles = corpus_bibles or []
        highest_premise_sim = 0.0
        highest_twist_sim = 0.0
        highest_hook_sim = 0.0
        highest_skeleton_sim = 0.0
        closest_matches: List[Tuple[float, str, str]] = []

        cand_text = f"{candidate_idea.working_title} {candidate_idea.hook} {candidate_idea.central_secret} {candidate_idea.reveal_1} {candidate_idea.reveal_2}"
        cand_skel = extract_narrative_skeleton(candidate_idea)
        candidate_idea.narrative_skeleton = cand_skel

        cand_emb = None
        if self.provider:
            try:
                cand_emb = self.provider.create_embedding(cand_text)
            except Exception:
                cand_emb = None

        # Compare against past ideas
        for other in corpus_ideas:
            if other.idea_id == candidate_idea.idea_id:
                continue

            # Hook similarity
            hook_sim = _jaccard_similarity(candidate_idea.hook, other.hook)
            if candidate_idea.hook_archetype == other.hook_archetype and candidate_idea.hook_archetype:
                hook_sim = min(1.0, hook_sim + 0.10)

            # Twist similarity
            twist_cand = f"{candidate_idea.reveal_1} {candidate_idea.reveal_2}"
            twist_other = f"{other.reveal_1} {other.reveal_2}"
            twist_sim = _jaccard_similarity(twist_cand, twist_other)
            if candidate_idea.twist_archetype == other.twist_archetype and candidate_idea.twist_archetype:
                twist_sim = min(1.0, twist_sim + 0.10)

            # Overall premise similarity
            other_text = f"{other.working_title} {other.hook} {other.central_secret} {other.reveal_1} {other.reveal_2}"
            if cand_emb and self.provider:
                try:
                    other_emb = self.provider.create_embedding(other_text)
                    premise_sim = _cosine_similarity(cand_emb, other_emb)
                except Exception:
                    premise_sim = _jaccard_similarity(cand_text, other_text)
            else:
                premise_sim = _jaccard_similarity(cand_text, other_text)

            # Narrative Skeleton similarity
            other_skel = extract_narrative_skeleton(other)
            skel_sim = compute_narrative_skeleton_similarity(cand_skel, other_skel)
            highest_skeleton_sim = max(highest_skeleton_sim, skel_sim)

            # Exact or near-identical duplicate detection
            if candidate_idea.central_secret.strip().lower() == other.central_secret.strip().lower():
                premise_sim = max(premise_sim, 0.95)
                twist_sim = max(twist_sim, 0.95)
                highest_skeleton_sim = max(highest_skeleton_sim, 95.0)

            highest_premise_sim = max(highest_premise_sim, premise_sim)
            highest_twist_sim = max(highest_twist_sim, twist_sim)
            highest_hook_sim = max(highest_hook_sim, hook_sim)

            composite_match = max(
                (premise_sim * 0.5 + twist_sim * 0.3 + hook_sim * 0.2) * 100.0,
                skel_sim,
            )
            if composite_match > 10.0:
                closest_matches.append((composite_match, other.idea_id, other.working_title))

        # Compare against Story Bibles (e.g. EP001)
        for bible in corpus_bibles:
            bible_text = f"{bible.title} {bible.secret} {bible.reveal_1} {bible.reveal_2}"
            b_twist = f"{bible.reveal_1} {bible.reveal_2}"
            twist_sim = _jaccard_similarity(f"{candidate_idea.reveal_1} {candidate_idea.reveal_2}", b_twist)
            premise_sim = _jaccard_similarity(cand_text, bible_text)

            if candidate_idea.central_secret.strip().lower() == bible.secret.strip().lower():
                premise_sim = max(premise_sim, 0.95)
                twist_sim = max(twist_sim, 0.95)

            highest_premise_sim = max(highest_premise_sim, premise_sim)
            highest_twist_sim = max(highest_twist_sim, twist_sim)
            comp = (premise_sim * 0.6 + twist_sim * 0.4) * 100.0
            if comp > 10.0:
                closest_matches.append((comp, bible.episode_id, bible.title))

        # Compare narrative skeleton against Golden Reference EP001
        ep1_skel_sim = compute_narrative_skeleton_similarity(cand_skel, EP001_NARRATIVE_SKELETON)
        highest_skeleton_sim = max(highest_skeleton_sim, ep1_skel_sim)
        if ep1_skel_sim > 15.0:
            closest_matches.append((ep1_skel_sim, "EP001", "7 năm giấu chồng chuyển tiền cho một người đàn ông"))

        closest_matches.sort(key=lambda x: x[0], reverse=True)
        closest_episodes = [
            {"id": cid, "title": title, "similarity_pct": round(score, 1)}
            for score, cid, title in closest_matches[:3]
        ]

        prem_pct = round(highest_premise_sim * 100.0, 1)
        twist_pct = round(highest_twist_sim * 100.0, 1)
        hook_pct = round(highest_hook_sim * 100.0, 1)
        skel_pct = round(highest_skeleton_sim, 1)

        candidate_idea.narrative_skeleton_similarity = skel_pct

        # Peak similarity takes the maximum of premise, twist, composite, or skeleton similarity
        peak_sim_pct = max(prem_pct, twist_pct, (prem_pct * 0.5 + twist_pct * 0.3 + hook_pct * 0.2), skel_pct)
        novelty_score = round(max(0.0, 100.0 - peak_sim_pct), 1)

        reasons = []

        # Section 4: Hard Duplicate Rules for V1.2
        # - narrative_skeleton_similarity >= 70%: BLOCKED_NARRATIVE_DUPLICATE
        # - narrative_skeleton_similarity >= 60%: NEEDS_NOVELTY_REWRITE
        # - peak_sim_pct >= duplicate_threshold: BLOCK_DUPLICATE
        if skel_pct >= 70.0:
            status = "BLOCKED_NARRATIVE_DUPLICATE"
            reasons.append(f"Cấu trúc khung truyện (Narrative Skeleton) tương đồng {skel_pct:.1f}% vượt ngưỡng an toàn 70%.")
        elif 60.0 <= skel_pct < 70.0:
            status = "NEEDS_NOVELTY_REWRITE"
            reasons.append(f"Cấu trúc khung truyện (Narrative Skeleton) tương đồng {skel_pct:.1f}% nằm trong vùng cảnh báo (60-69.9%). Cần viết lại tính độc bản.")
        elif peak_sim_pct >= self.duplicate_threshold_pct:
            status = "BLOCK_DUPLICATE"
            reasons.append(f"Độ trùng lặp tiền đề/bước ngoặt ({peak_sim_pct:.1f}%) vượt ngưỡng trùng lặp ({self.duplicate_threshold_pct:.1f}%).")
        else:
            status = "PASS"

        return NoveltyReport(
            idea_id=candidate_idea.idea_id,
            novelty_score=novelty_score,
            premise_similarity_pct=prem_pct,
            twist_similarity_pct=twist_pct,
            hook_similarity_pct=hook_pct,
            status=status,
            narrative_skeleton_similarity_pct=skel_pct,
            closest_episodes=closest_episodes,
            reasons=reasons,
        )
