"""Script Writer Engine for Script Factory V1."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from apps.script_factory.cost_control import CostController
from apps.script_factory.models import ApprovalStatus, FullScript, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.story_qc import StoryQCEngine

logger = logging.getLogger("VieNeu.ScriptWriter")

SERIES_BIBLE_PATH = Path("script_factory/series_bible.json")
STORY_FORMULA_PATH = Path("script_factory/story_formula_v1.json")


class ScriptWriter:
    """Generates full episodic scripts adhering to locked facts and delivery profiles."""

    def __init__(
        self,
        provider: ScriptAIProvider,
        cost_controller: CostController,
        episodes_root: Optional[Path] = None,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller
        self.episodes_root = Path(episodes_root) if episodes_root else Path("episodes")
        self.story_qc = StoryQCEngine()

    def generate_script_from_bible(
        self,
        story_bible: StoryBible,
        model: Optional[str] = None,
    ) -> FullScript:
        """Writes full episodic script from Story Bible."""
        if story_bible.episode_id == "EP001":
            raise ValueError("EP001 is golden reference and cannot be regenerated.")

        # Reveal Justification & Story Logic Hard Gate
        if not getattr(story_bible, "approved_by", None):
            bible_qc = self.story_qc.audit_story_bible(story_bible)
            if bible_qc.status != "PASS":
                codes_str = ", ".join(bible_qc.rule_codes) or "STORY_LOGIC_FAIL"
                details = "; ".join(bible_qc.logic_issues)
                raise ValueError(f"Story Bible QC blocked ScriptWriter [{codes_str}]: {details}")

        self.cost_ctrl.check_budget_pre_flight(episode_id=story_bible.episode_id)

        series_bible = {}
        if SERIES_BIBLE_PATH.exists():
            with open(SERIES_BIBLE_PATH, "r", encoding="utf-8") as f:
                series_bible = json.load(f)

        story_formula = {}
        if STORY_FORMULA_PATH.exists():
            with open(STORY_FORMULA_PATH, "r", encoding="utf-8") as f:
                story_formula = json.load(f)

        # Ensure protagonist has a real character name from AI, not generic internal role placeholder
        if isinstance(story_bible.protagonist, dict):
            curr_name = str(story_bible.protagonist.get("name", "")).strip()
            if not curr_name or curr_name.lower() in ("nhân vật chính", "người", "protagonist"):
                cand = None
                for sc in story_bible.supporting_characters:
                    if isinstance(sc, dict) and sc.get("name") and sc.get("name").lower() not in ("nhân vật chính", "người thân", "nhân vật phụ"):
                        cand = sc.get("name")
                        break
                story_bible.protagonist["name"] = cand or "Minh Tuấn"
        elif not story_bible.protagonist or str(story_bible.protagonist).strip().lower() in ("nhân vật chính", "người", "protagonist"):
            story_bible.protagonist = {"name": "Minh Tuấn", "age": 32, "description": "Người gửi lá thư tâm sự về chương trình"}

        t0 = time.time()
        try:
            script, in_tokens, out_tokens = self.provider.write_script(
                story_bible=story_bible,
                story_formula=story_formula,
                series_bible=series_bible,
                model=model,
            )
            # Post-generation sanitize to ensure 0 template labels leak into narration
            from apps.script_factory.leakage_guard import StoryBibleLeakageGuard
            lg = StoryBibleLeakageGuard()
            protag_name = story_bible.protagonist.get("name", "Tuấn") if isinstance(story_bible.protagonist, dict) else str(story_bible.protagonist or "Tuấn")
            for s in script.segments:
                s.text = lg.clean_text_from_leakage(s.text, protagonist_name=protag_name)

            # Writers pile moral summaries and thank-yous onto the ending; keep
            # one reflection, one audience question and the sign-off.
            from apps.script_factory.script_craft import trim_overlong_closing
            trimmed = trim_overlong_closing(script.segments)
            if len(trimmed) != len(script.segments):
                script.segments = trimmed
                for index, segment in enumerate(script.segments, start=1):
                    segment.id = f"{index:03d}"

            from apps.script_factory.vietnamese_cleaner import clean_garbled_vietnamese
            for seg in script.segments:
                seg.text = clean_garbled_vietnamese(seg.text)
            script.total_words = sum(len(seg.text.split()) for seg in script.segments)

            lat = time.time() - t0
            self.cost_ctrl.record_operation(
                operation="write_script",
                episode_id=story_bible.episode_id,
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
                operation="write_script",
                episode_id=story_bible.episode_id,
                provider=self.provider.provider_name,
                model=model or "default",
                status="FAILED",
                latency_sec=lat,
                input_tokens=0,
                output_tokens=0,
                error=str(exc),
            )
            raise exc

        script.status = ApprovalStatus.DRAFT
        self.save_script(script)
        return script

    def save_script(self, script: FullScript) -> Path:
        """Saves script to episodes/EPXXX/script.json."""
        ep_dir = self.episodes_root / script.episode_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        script.updated_at = time.time()
        file_path = ep_dir / "script.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"[ScriptWriter] Saved script for {script.episode_id} ({len(script.segments)} segments)")
        return file_path

    def load_script(self, episode_id: str) -> Optional[FullScript]:
        """Loads script for an episode."""
        file_path = self.episodes_root / episode_id / "script.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return FullScript.from_dict(data)
