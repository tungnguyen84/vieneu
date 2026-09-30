"""Story Planner and Fact Lock Manager for Script Factory V1."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.script_factory.cost_control import CostController
from apps.script_factory.models import ApprovalStatus, IdeaItem, LockedFact, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.story_qc import StoryBibleQCReport, StoryQCEngine

logger = logging.getLogger("VieNeu.StoryPlanner")

SERIES_BIBLE_PATH = Path("script_factory/series_bible.json")


class StoryPlanner:
    """Creates, validates, and persists episode Story Bibles with Fact Locks."""

    def __init__(
        self,
        provider: ScriptAIProvider,
        cost_controller: CostController,
        episodes_root: Optional[Path] = None,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller
        self.episodes_root = Path(episodes_root) if episodes_root else Path("episodes")
        self.episodes_root.mkdir(parents=True, exist_ok=True)
        self.story_qc = StoryQCEngine()

    def validate_story_bible(
        self,
        bible: StoryBible,
        auto_repair: bool = False,
    ) -> StoryBibleQCReport:
        """Validates Story Bible against causal, knowledge, clue, and reveal justification gates."""
        report = self.story_qc.audit_story_bible(bible)
        if auto_repair and (
            report.status != "PASS"
            or not bible.causal_chains
            or not bible.knowledge_ledger
            or not bible.structured_clues
            or not bible.reveal_justifications
        ):
            self.story_qc.repair_story_bible(bible, report)
            report = self.story_qc.audit_story_bible(bible)
        return report

    def get_next_episode_id(self) -> str:
        """Determines the next sequential episode ID (EP002, EP003...). EP001 is reserved."""
        existing = [p.name for p in self.episodes_root.iterdir() if p.is_dir() and p.name.startswith("EP")]
        nums = []
        for name in existing:
            try:
                num = int(name.replace("EP", ""))
                nums.append(num)
            except ValueError:
                pass
        next_num = max(nums, default=1) + 1
        return f"EP{next_num:03d}"

    def create_story_bible_from_idea(
        self,
        idea: IdeaItem,
        episode_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> StoryBible:
        """Expands an Idea into a complete Story Bible with Fact Lock."""
        target_ep_id = episode_id or self.get_next_episode_id()
        if target_ep_id == "EP001":
            raise ValueError("EP001 is reserved for Golden Reference and cannot be created or overwritten.")

        self.cost_ctrl.check_budget_pre_flight(episode_id=target_ep_id)

        # Load series bible
        series_bible = {}
        if SERIES_BIBLE_PATH.exists():
            with open(SERIES_BIBLE_PATH, "r", encoding="utf-8") as f:
                series_bible = json.load(f)

        t0 = time.time()
        try:
            bible, in_tokens, out_tokens = self.provider.create_story_bible(
                idea=idea,
                series_bible=series_bible,
                model=model,
            )
            bible.episode_id = target_ep_id
            if idea.original_user_topic:
                bible.original_user_topic = idea.original_user_topic
            if idea.topic_intent:
                bible.topic_intent = idea.topic_intent
            if idea.topic_adherence_score is not None:
                bible.topic_adherence = idea.topic_adherence_score

            # Audit and auto-repair causal gaps, knowledge contradictions, clue jumps, and reveal justifications
            self.validate_story_bible(bible, auto_repair=True)
            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="create_story_bible",
                episode_id=target_ep_id,
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
                operation="create_story_bible",
                episode_id=target_ep_id,
                provider=self.provider.provider_name,
                model=model or "default",
                status="FAILED",
                latency_sec=lat,
                input_tokens=0,
                output_tokens=0,
                error=str(exc),
            )
            raise exc

        # Save to disk
        self.save_story_bible(bible)
        return bible

    def save_story_bible(self, bible: StoryBible) -> Path:
        """Saves Story Bible, Character Bible, and Location Bible to episode directory."""
        ep_dir = self.episodes_root / bible.episode_id
        ep_dir.mkdir(parents=True, exist_ok=True)

        bible.last_modified_at = time.time()
        file_path = ep_dir / "story_bible.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(bible.to_dict(), f, ensure_ascii=False, indent=2)

        # Character Bible export
        char_bible: Dict[str, Any] = {}
        if bible.protagonist:
            p_id = bible.protagonist.get("char_id", "PROTAGONIST")
            char_bible[p_id] = bible.protagonist
        for sc in bible.supporting_characters:
            sc_id = sc.get("char_id", sc.get("name", "CHAR"))
            char_bible[sc_id] = sc
        char_file = ep_dir / "character_bible.json"
        with open(char_file, "w", encoding="utf-8") as f:
            json.dump(char_bible, f, ensure_ascii=False, indent=2)

        # Location Bible export
        loc_bible = {"locations": bible.locations}
        loc_file = ep_dir / "location_bible.json"
        with open(loc_file, "w", encoding="utf-8") as f:
            json.dump(loc_bible, f, ensure_ascii=False, indent=2)

        logger.info(f"[StoryPlanner] Saved Story Bible and bibles for {bible.episode_id}")
        return file_path

    def load_story_bible(self, episode_id: str) -> Optional[StoryBible]:
        """Loads Story Bible for a given episode."""
        file_path = self.episodes_root / episode_id / "story_bible.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return StoryBible.from_dict(data)

    def modify_story_bible(self, bible: StoryBible) -> StoryBible:
        """
        Modifies a Story Bible. If the Story Bible was previously approved,
        resets status to STORY_BIBLE_CHANGED so old QC/approval cannot silently pass!
        """
        if bible.status == ApprovalStatus.APPROVED or bible.status == ApprovalStatus.QC_PASS:
            bible.status = ApprovalStatus.STORY_BIBLE_CHANGED
            bible.approved_by = None
            bible.approved_at = None

        self.save_story_bible(bible)
        return bible
