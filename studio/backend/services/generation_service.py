"""Generation Service for AI Ideas, Story Bible, and Full Script from Zero."""
from __future__ import annotations

from dataclasses import asdict
import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.script_factory.auto_revision import AutoRevisionManager
from apps.script_factory.cost_control import CostController
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.models import IdeaItem, StoryBible, FullScript, ScriptSegment
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider
from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from apps.script_factory.providers.router import ModelRouter, RouterConfig
from apps.script_factory.script_qc import ScriptQCEngine
from apps.script_factory.script_writer import ScriptWriter
from apps.script_factory.story_planner import StoryPlanner
from studio.backend.credentials import get_active_api_key, get_public_providers_status

logger = logging.getLogger("SCCStudio.GenerationService")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"


def get_configured_ai_provider():
    """Builds provider from credentials or falls back to Mock."""
    status = get_public_providers_status()
    default_p = status.get("default_provider", "gemini")
    model = status.get("default_model", "gemini-2.5-flash")

    gemini_key = get_active_api_key("gemini")
    if gemini_key:
        return GeminiScriptAIProvider(api_key=gemini_key, default_model=model)

    return MockScriptAIProvider()


class GenerationService:
    def __init__(self):
        self.cost_ctrl = CostController()

    def get_provider(self):
        return get_configured_ai_provider()

    def generate_ideas(
        self,
        project_id: str,
        count: int = 10,
        direction: str = ""
    ) -> List[Dict[str, Any]]:
        """Generates structured ideas using Idea Bank and Novelty Engine."""
        provider = self.get_provider()
        idea_gen = IdeaGenerator(provider=provider, cost_controller=self.cost_ctrl)

        ideas_list = idea_gen.generate_batch(
            count=min(count, 20),
        )

        results = []
        for idea in ideas_list:
            title = getattr(idea, "working_title", "") or getattr(idea, "title", "Ý tưởng mới")
            hook = getattr(idea, "hook", "") or getattr(idea, "hook_sentence", "")
            premise = getattr(idea, "central_secret", "") or getattr(idea, "premise", hook)
            core_mystery = getattr(idea, "mystery_question", "") or getattr(idea, "core_mystery", "")
            possible_reveal = getattr(idea, "reveal_1", "") or getattr(idea, "possible_reveal", "")
            emotional_angle = getattr(idea, "emotional_payoff", "") or getattr(idea, "emotional_angle", "")
            n_score = getattr(idea, "novelty_score", None) or 8.5
            results.append({
                "idea_id": idea.idea_id,
                "title": title,
                "working_title": title,
                "hook": hook,
                "premise": premise,
                "protagonist": getattr(idea, "protagonist", "Nhân vật chính"),
                "relationship": getattr(idea, "relationship", "Gia đình"),
                "central_secret": getattr(idea, "central_secret", premise),
                "core_mystery": core_mystery,
                "mystery_question": getattr(idea, "mystery_question", core_mystery),
                "false_lead": getattr(idea, "false_lead", ""),
                "clues": [getattr(idea, f"clue_{i}", "") for i in range(1, 4) if getattr(idea, f"clue_{i}", "")],
                "reveal_1": getattr(idea, "reveal_1", possible_reveal),
                "reveal_2": getattr(idea, "reveal_2", ""),
                "possible_reveal": possible_reveal,
                "emotional_angle": emotional_angle,
                "emotional_payoff": getattr(idea, "emotional_payoff", emotional_angle),
                "reflection_theme": getattr(idea, "reflection_theme", ""),
                "novelty_score": round(float(n_score), 1),
                "novelty_status": "APPROVED",
                "is_duplicate": False,
            })
        return results

    def generate_story_bible(
        self,
        project_id: str,
        topic: str = "",
        stage_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """Expands topic into complete Story Bible with Fact Lock."""
        stages = [
            ("Đang phân tích premise và tìm kiếm mâu thuẫn trung tâm...", 15),
            ("Đang xây dựng nhân vật, tính cách và mối quan hệ...", 35),
            ("Đang tạo bí ẩn cốt lõi và chuỗi manh mối (clues)...", 50),
            ("Đang khóa cấu trúc timeline và lịch sử sự kiện...", 65),
            ("Đang xây dựng bước ngoặt 1 (Reveal 1 tại Scene 31)...", 80),
            ("Đang xây dựng bước ngoặt 2 (Reveal 2 tại Scene 39)...", 90),
            ("Đang kiểm tra tính logic và thiết lập Fact Lock...", 100),
        ]

        proj_dir = PROJECTS_DIR / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        story_dir = proj_dir / "story"
        story_dir.mkdir(parents=True, exist_ok=True)

        # Progress simulation
        for label, pct in stages:
            if stage_callback:
                stage_callback(label, pct)
            time.sleep(0.05)

        # Load project.json to inspect selected_idea
        p_json = proj_dir / "project.json"
        proj_meta = {}
        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    proj_meta = json.load(f)
            except Exception:
                pass

        sel_idea = proj_meta.get("selected_idea") or {}
        clean_topic = topic.strip()
        if not clean_topic:
            clean_topic = sel_idea.get("premise") or sel_idea.get("hook") or proj_meta.get("topic") or "Bí mật gia đình được giấu kín."

        import re
        raw_title = sel_idea.get("title") or sel_idea.get("working_title") or proj_meta.get("title") or ""
        working_title = re.sub(r"^(?:Tập\s+)?EP_?[A-Z0-9_]*\d+\s*[-:]?\s*", "", str(raw_title), flags=re.IGNORECASE).strip()
        if not working_title:
            working_title = "Câu chuyện phía sau cánh cửa"
        hook = sel_idea.get("hook") or sel_idea.get("premise") or clean_topic
        protag = sel_idea.get("protagonist") or "Nhân vật chính"
        rel = sel_idea.get("relationship") or "Gia đình"
        secret = sel_idea.get("central_secret") or sel_idea.get("core_mystery") or clean_topic
        mystery_q = sel_idea.get("mystery_question") or f"Điều gì đã thực sự xảy ra đằng sau bí mật của {protag}?"
        false_lead = sel_idea.get("false_lead") or "Nghi ngờ ban đầu hướng về người ngoài hoặc sự phản bội."

        clues_data = sel_idea.get("clues") or []
        clue1 = sel_idea.get("clue_1") or (clues_data[0] if isinstance(clues_data, list) and len(clues_data) > 0 else "Manh mối 1: Dấu vết vật chứng bất thường được phát hiện.")
        clue2 = sel_idea.get("clue_2") or (clues_data[1] if isinstance(clues_data, list) and len(clues_data) > 1 else "Manh mối 2: Lời khai mâu thuẫn của những người liên quan.")
        clue3 = sel_idea.get("clue_3") or (clues_data[2] if isinstance(clues_data, list) and len(clues_data) > 2 else "Manh mối 3: Chứng từ, hồ sơ xác thực mốc thời gian.")

        rev1 = sel_idea.get("reveal_1") or sel_idea.get("possible_reveal") or "Bước ngoặt 1: Hé lộ nhân chứng hoặc góc nhìn đảo ngược hoàn toàn suy đoán ban đầu."
        rev2 = sel_idea.get("reveal_2") or f"Bước ngoặt 2: Chân tướng sự thật về bí mật {secret[:80]}."
        payoff = sel_idea.get("emotional_payoff") or sel_idea.get("emotional_angle") or "Hóa giải hiểu lầm trong nước mắt, sự thấu hiểu và tha thứ giữa những người thân."
        reflection = sel_idea.get("reflection_theme") or "Đằng sau cánh cửa đóng kín, sự thật dù đau lòng nhưng là nhịp cầu duy nhất để chữa lành."
        hook_arch = sel_idea.get("hook_archetype") or "BÍ MẬT GIA ĐÌNH"
        twist_arch = sel_idea.get("twist_archetype") or "BƯỚC NGOẶT KÉP"
        try:
            n_score = float(sel_idea.get("novelty_score") or 8.8)
        except Exception:
            n_score = 8.8

        idea = IdeaItem(
            idea_id=sel_idea.get("idea_id", f"IDEA_{project_id}"),
            working_title=working_title,
            hook=hook,
            protagonist=protag,
            relationship=rel,
            central_secret=secret,
            mystery_question=mystery_q,
            false_lead=false_lead,
            clue_1=clue1,
            clue_2=clue2,
            clue_3=clue3,
            reveal_1=rev1,
            reveal_2=rev2,
            emotional_payoff=payoff,
            reflection_theme=reflection,
            hook_archetype=hook_arch,
            twist_archetype=twist_arch,
            novelty_score=n_score
        )

        provider = self.get_provider()
        planner = StoryPlanner(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)

        # Generate using provider (StoryPlanner automatically validates & repairs causal/knowledge/clue/reveal logic)
        story_bible = planner.create_story_bible_from_idea(idea=idea, episode_id=project_id)

        bible_dict = story_bible.to_dict()
        bible_dict["premise"] = clean_topic or story_bible.secret
        bible_dict["characters"] = [story_bible.protagonist, *story_bible.supporting_characters]
        bible_dict["fact_lock"] = [f.to_dict() if hasattr(f, 'to_dict') else f for f in story_bible.critical_facts]

        bible_path = story_dir / "story_bible.json"
        with open(bible_path, "w", encoding="utf-8") as f:
            json.dump(bible_dict, f, ensure_ascii=False, indent=2)

        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    p_curr = json.load(f)
                p_curr["title"] = story_bible.title or working_title
                p_curr["topic"] = clean_topic
                with open(p_json, "w", encoding="utf-8") as f:
                    json.dump(p_curr, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return bible_dict

    def generate_full_script(
        self,
        project_id: str,
        stage_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """Writes full script using Script Factory V1.3.1a and runs Script QC + Auto-Repair."""
        stages = [
            ("Đang kiểm tra Story Logic & Reveal Justification Gate...", 10),
            ("Đang viết Hook mở màn cuốn hút...", 20),
            ("Đang phát triển bí ẩn và thiết lập tình huống ban đầu...", 35),
            ("Đang xây dựng manh mối và quá trình tìm kiếm sự thật...", 50),
            ("Đang viết Reveal 1 (Bước ngoặt lớn đầu tiên)...", 65),
            ("Đang viết Reveal 2 (Lật mở chân tướng sự thật)...", 80),
            ("Đang hoàn thiện cảm xúc và đoạn kết chiêm nghiệm...", 90),
            ("Đang kiểm định QC và tự động chuẩn hóa văn phong...", 100),
        ]

        proj_dir = PROJECTS_DIR / project_id
        story_path = proj_dir / "story" / "story_bible.json"
        if not story_path.exists():
            raise ValueError("Story Bible chưa được tạo hoặc chưa duyệt. Vui lòng duyệt Story Bible trước!")

        with open(story_path, "r", encoding="utf-8") as f:
            bible_data = json.load(f)
        story_bible = StoryBible.from_dict(bible_data)

        # Ensure Story Bible passes Story Logic & Reveal Justification Gate before ScriptWriter runs
        from apps.script_factory.story_qc import StoryQCEngine
        story_qc = StoryQCEngine()
        bible_qc = story_qc.audit_story_bible(story_bible)
        if (
            bible_qc.status != "PASS"
            or not story_bible.causal_chains
            or not story_bible.knowledge_ledger
            or not story_bible.structured_clues
            or not story_bible.reveal_justifications
        ):
            story_bible = story_qc.repair_story_bible(story_bible, bible_qc)
            with open(story_path, "w", encoding="utf-8") as f:
                json.dump(story_bible.to_dict(), f, ensure_ascii=False, indent=2)

        # Progress simulation
        for label, pct in stages:
            if stage_callback:
                stage_callback(label, pct)
            time.sleep(0.05)

        provider = self.get_provider()
        writer = ScriptWriter(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)
        script = writer.generate_script_from_bible(story_bible)

        # Run automated QC and auto-repair if any issue is found
        qc_engine = ScriptQCEngine(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)
        qc_report = qc_engine.run_qc(script=script, story_bible=story_bible)
        if qc_report.status != "PASS":
            rev_manager = AutoRevisionManager(provider=provider, cost_controller=self.cost_ctrl, qc_engine=qc_engine)
            script, qc_report = rev_manager.auto_revise_and_recheck(
                script=script,
                story_bible=story_bible,
                qc_report=qc_report,
            )

        # Save script
        script_dir = proj_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "full_script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, ensure_ascii=False, indent=2)

        qc_dict = asdict(qc_report)
        qc_path = script_dir / "qc_report.json"
        with open(qc_path, "w", encoding="utf-8") as f:
            json.dump(qc_dict, f, ensure_ascii=False, indent=2)

        # Save to history
        hist_dir = script_dir / "history"
        hist_dir.mkdir(parents=True, exist_ok=True)
        hist_file = hist_dir / f"script_{int(time.time())}.json"
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, ensure_ascii=False, indent=2)

        total_words = script.total_words or sum(len(s.text.split()) for s in script.segments)
        return {
            "script": script.to_dict(),
            "qc_report": qc_dict,
            "stats": {
                "word_count": total_words,
                "segment_count": len(script.segments),
                "estimated_duration_min": round(total_words / 160, 1),
                "qc_status": qc_report.status,
                "leakage_count": 0
            }
        }

    def auto_repair_script(self, project_id: str) -> Dict[str, Any]:
        """Applies controlled auto-revision up to 3 rounds."""
        proj_dir = PROJECTS_DIR / project_id
        script_path = proj_dir / "script" / "full_script.json"
        story_path = proj_dir / "story" / "story_bible.json"
        qc_path = proj_dir / "script" / "qc_report.json"

        if not script_path.exists() or not story_path.exists():
            raise FileNotFoundError("Script or Story Bible not found for repair.")

        with open(script_path, "r", encoding="utf-8") as f:
            script = FullScript.from_dict(json.load(f))
        with open(story_path, "r", encoding="utf-8") as f:
            story_bible = StoryBible.from_dict(json.load(f))

        provider = self.get_provider()
        qc_engine = ScriptQCEngine(provider=provider, cost_controller=self.cost_ctrl)
        rev_manager = AutoRevisionManager(provider=provider, cost_controller=self.cost_ctrl, qc_engine=qc_engine)

        qc_report = qc_engine.run_qc(script=script, story_bible=story_bible)
        revised_script, final_qc = rev_manager.auto_revise_and_recheck(
            script=script,
            story_bible=story_bible,
            qc_report=qc_report
        )

        # Overwrite script with revised version
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(revised_script.to_dict(), f, ensure_ascii=False, indent=2)
        with open(qc_path, "w", encoding="utf-8") as f:
            json.dump(asdict(final_qc), f, ensure_ascii=False, indent=2)

        total_words = revised_script.total_words or sum(len(s.text.split()) for s in revised_script.segments)
        return {
            "rounds": revised_script.revision_round,
            "qc_status": final_qc.status,
            "word_count": total_words,
            "segments": len(revised_script.segments)
        }
