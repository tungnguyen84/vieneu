"""Novelty Engine for Script Factory V1.

Detects duplicates, premise overlap, and twist repetition across all past ideas and episodes:
- Dual similarity measurement: Embedding cosine similarity + Lexical Jaccard/N-gram fallback.
- Computes Novelty Score (0-100), Premise Similarity (%), Twist Similarity (%), Hook Similarity (%).
- Returns Closest Episodes list.
- Flags BLOCK_DUPLICATE when similarity breaches safety threshold.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import IdeaItem, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider


@dataclass
class NoveltyReport:
    idea_id: str
    novelty_score: float  # 0 to 100 (Higher is more novel)
    premise_similarity_pct: float
    twist_similarity_pct: float
    hook_similarity_pct: float
    status: str  # "PASS" or "BLOCK_DUPLICATE"
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
        """Audits an idea against existing ideas and bibles."""
        corpus_bibles = corpus_bibles or []
        highest_premise_sim = 0.0
        highest_twist_sim = 0.0
        highest_hook_sim = 0.0
        closest_matches: List[Tuple[float, str, str]] = []

        cand_text = f"{candidate_idea.working_title} {candidate_idea.hook} {candidate_idea.central_secret} {candidate_idea.reveal_1} {candidate_idea.reveal_2}"
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
                hook_sim = max(hook_sim, 0.40)

            # Twist similarity
            twist_cand = f"{candidate_idea.twist_archetype} {candidate_idea.reveal_1} {candidate_idea.reveal_2}"
            twist_other = f"{other.twist_archetype} {other.reveal_1} {other.reveal_2}"
            twist_sim = _jaccard_similarity(twist_cand, twist_other)
            if candidate_idea.twist_archetype == other.twist_archetype and candidate_idea.twist_archetype:
                twist_sim = max(twist_sim, 0.45)

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

            # Exact or near-identical duplicate detection
            if candidate_idea.central_secret.strip().lower() == other.central_secret.strip().lower():
                premise_sim = max(premise_sim, 0.95)
                twist_sim = max(twist_sim, 0.95)

            highest_premise_sim = max(highest_premise_sim, premise_sim)
            highest_twist_sim = max(highest_twist_sim, twist_sim)
            highest_hook_sim = max(highest_hook_sim, hook_sim)

            composite_match = (premise_sim * 0.5 + twist_sim * 0.3 + hook_sim * 0.2) * 100.0
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

        closest_matches.sort(key=lambda x: x[0], reverse=True)
        closest_episodes = [
            {"id": cid, "title": title, "similarity_pct": round(score, 1)}
            for score, cid, title in closest_matches[:3]
        ]

        prem_pct = round(highest_premise_sim * 100.0, 1)
        twist_pct = round(highest_twist_sim * 100.0, 1)
        hook_pct = round(highest_hook_sim * 100.0, 1)

        # Novelty score is 100 minus highest composite similarity
        peak_sim_pct = max(prem_pct, twist_pct, (prem_pct * 0.5 + twist_pct * 0.3 + hook_pct * 0.2))
        novelty_score = round(max(0.0, 100.0 - peak_sim_pct), 1)

        reasons = []
        is_blocked = peak_sim_pct >= self.duplicate_threshold_pct

        if is_blocked:
            reasons.append(f"Premise or twist similarity ({peak_sim_pct:.1f}%) exceeds safety threshold ({self.duplicate_threshold_pct:.1f}%).")
            status = "BLOCK_DUPLICATE"
        else:
            status = "PASS"

        return NoveltyReport(
            idea_id=candidate_idea.idea_id,
            novelty_score=novelty_score,
            premise_similarity_pct=prem_pct,
            twist_similarity_pct=twist_pct,
            hook_similarity_pct=hook_pct,
            status=status,
            closest_episodes=closest_episodes,
            reasons=reasons,
        )
