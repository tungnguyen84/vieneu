"""Idea Generator and Idea Bank Manager for Script Factory V1."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.script_factory.cost_control import CostController
from apps.script_factory.models import IdeaItem
from apps.script_factory.novelty_engine import NoveltyEngine
from apps.script_factory.providers.base import ScriptAIProvider

logger = logging.getLogger("VieNeu.IdeaGenerator")

IDEA_BANK_PATH = Path("script_factory/idea_bank.json")
SERIES_BIBLE_PATH = Path("script_factory/series_bible.json")
STORY_FORMULA_PATH = Path("script_factory/story_formula_v1.json")


class IdeaGenerator:
    """Manages premise idea generation, novelty checks, and persistence."""

    def __init__(
        self,
        provider: ScriptAIProvider,
        cost_controller: CostController,
        novelty_engine: Optional[NoveltyEngine] = None,
        idea_bank_file: Optional[Path] = None,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller
        self.novelty = novelty_engine or NoveltyEngine(provider=provider)
        self.bank_file = Path(idea_bank_file) if idea_bank_file else IDEA_BANK_PATH
        self.bank_file.parent.mkdir(parents=True, exist_ok=True)

    def load_idea_bank(self) -> List[IdeaItem]:
        """Loads all ideas currently stored in idea_bank.json."""
        if not self.bank_file.exists():
            return []
        try:
            with open(self.bank_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_list = data.get("ideas", [])
            return [IdeaItem.from_dict(item) for item in raw_list]
        except Exception as e:
            logger.error(f"[IdeaGenerator] Failed to load idea bank: {e}")
            return []

    def save_idea_bank(self, ideas: List[IdeaItem]) -> None:
        """Saves ideas list to idea_bank.json."""
        data = {
            "ideas": [item.to_dict() for item in ideas],
            "updated_at": time.time(),
            "total_count": len(ideas),
        }
        with open(self.bank_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[IdeaGenerator] Saved {len(ideas)} ideas to {self.bank_file}")

    def generate_batch(
        self,
        count: int = 10,
        model: Optional[str] = None,
    ) -> List[IdeaItem]:
        """
        Generates a batch of premise ideas (10, 20, 50, 100).
        Strict constraint: NEVER generates full scripts here.
        """
        if count not in [10, 20, 50, 100]:
            # Allow flexible count if tested, but default targets are 10, 20, 50, 100
            pass

        self.cost_ctrl.check_budget_pre_flight(batch_size=count)

        existing = self.load_idea_bank()

        # Load categories from story formula
        diversity_categories = []
        hook_archetypes = []
        if STORY_FORMULA_PATH.exists():
            try:
                with open(STORY_FORMULA_PATH, "r", encoding="utf-8") as f:
                    formula = json.load(f)
                diversity_categories = formula.get("diversity_categories", [])
                hook_archetypes = formula.get("hook_archetypes", [])
            except Exception:
                pass

        t0 = time.time()
        try:
            new_ideas, in_tokens, out_tokens = self.provider.generate_ideas(
                count=count,
                existing_ideas=existing,
                diversity_categories=diversity_categories,
                hook_archetypes=hook_archetypes,
                model=model,
            )
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="generate_ideas",
                episode_id=None,
                provider=self.provider.provider_name,
                model=model or "default",
                status="SUCCESS",
                latency_sec=lat,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
            )
        except Exception as exc:
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="generate_ideas",
                episode_id=None,
                provider=self.provider.provider_name,
                model=model or "default",
                status="FAILED",
                latency_sec=lat,
                input_tokens=0,
                output_tokens=0,
                error=str(exc),
            )
            raise exc

        # Check novelty for each new idea against all prior ideas
        for idea in new_ideas:
            report = self.novelty.check_idea_novelty(idea, existing + new_ideas)
            idea.novelty_score = report.novelty_score
            if report.status == "BLOCK_DUPLICATE":
                idea.status = "BLOCKED_DUPLICATE"

        # Append and persist
        all_ideas = existing + new_ideas
        self.save_idea_bank(all_ideas)
        return new_ideas
