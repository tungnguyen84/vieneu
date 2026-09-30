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
    """Builds provider from credentials. NEVER silently falls back to Mock in production."""
    status = get_public_providers_status()
    default_p = (status.get("default_provider") or "gemini").strip().lower()
    model = (status.get("default_model") or "gemini-2.5-flash").strip()

    is_test_env = os.environ.get("APP_ENV") == "test" or os.environ.get("ALLOW_MOCK_AI") == "1"

    if default_p == "gemini":
        gemini_key = get_active_api_key("gemini")
        if gemini_key:
            return GeminiScriptAIProvider(api_key=gemini_key, default_model=model)
        elif is_test_env or default_p == "mock":
            return MockScriptAIProvider()
        else:
            raise RuntimeError(
                "AI GENERATION FAILED: Google Gemini API key is missing or not configured. "
                "Please configure a valid GEMINI_API_KEY in Settings."
            )
    elif default_p in ("openai", "openai_compatible", "local"):
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        prov_data = status.get("providers", {}).get(default_p, {})
        key = get_active_api_key(default_p) or ""
        base_url = prov_data.get("base_url") or ("http://localhost:11434/v1" if default_p == "local" else "https://api.openai.com/v1")
        if key or default_p == "local":
            return OpenAICompatibleProvider(
                api_key=key,
                default_model=model,
                base_url=base_url,
                provider_name=default_p
            )
        elif is_test_env or default_p == "mock":
            return MockScriptAIProvider()
        else:
            raise RuntimeError(
                f"AI GENERATION FAILED: {default_p.upper()} API key is missing. "
                "Please configure your provider credentials in Settings."
            )

    # Secondary checks
    gemini_key = get_active_api_key("gemini")
    if gemini_key:
        return GeminiScriptAIProvider(api_key=gemini_key, default_model=model)

    openai_key = get_active_api_key("openai")
    if openai_key:
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(api_key=openai_key, default_model=model, provider_name="openai")

    if is_test_env or default_p == "mock":
        return MockScriptAIProvider()

    raise RuntimeError(
        "AI GENERATION FAILED: No valid AI provider credentials found. "
        "Silent fallback to mock is forbidden in production."
    )


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
        """Generates structured ideas using Idea Bank, TopicIntent and Novelty Engine."""
        from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

        proj_dir = PROJECTS_DIR / project_id
        p_json = proj_dir / "project.json"
        proj_meta = {}
        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    proj_meta = json.load(f)
            except Exception:
                pass

        user_topic = direction.strip()
        if not user_topic:
            user_topic = (proj_meta.get("topic") or proj_meta.get("premise") or "").strip()

        topic_intent_obj = None
        if user_topic:
            topic_intent_obj = extract_topic_intent(user_topic)
            if p_json.exists():
                try:
                    proj_meta["topic"] = user_topic
                    proj_meta["original_user_topic"] = user_topic
                    proj_meta["topic_intent"] = topic_intent_obj.to_dict()
                    with open(p_json, "w", encoding="utf-8") as f:
                        json.dump(proj_meta, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        provider = self.get_provider()
        prov_source = "MOCK" if isinstance(provider, MockScriptAIProvider) else "REAL_AI"
        logger.debug(
            f"[Lineage Stage=IDEAS] project_id={project_id}, original_user_topic='{user_topic}', "
            f"provider={provider.provider_name}, model={getattr(provider, 'default_model', 'unknown')}, source={prov_source}"
        )
        idea_gen = IdeaGenerator(provider=provider, cost_controller=self.cost_ctrl)

        ideas_list = idea_gen.generate_batch(
            count=min(count, 20),
            user_topic=user_topic if user_topic else None,
            topic_intent=topic_intent_obj,
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
            adherence_sc = getattr(idea, "topic_adherence_score", None)
            protag = getattr(idea, "protagonist", "Tuấn")
            if str(protag).strip().lower() in ("nhân vật chính", "protagonist"):
                protag = "Tuấn"
            results.append({
                "idea_id": idea.idea_id,
                "title": title,
                "working_title": title,
                "hook": hook,
                "premise": premise,
                "protagonist": protag,
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
                "original_user_topic": getattr(idea, "original_user_topic", user_topic or None),
                "topic_intent": getattr(idea, "topic_intent", topic_intent_obj.to_dict() if topic_intent_obj else None),
                "topic_adherence_score": adherence_sc if adherence_sc is not None else (100.0 if user_topic else None),
                "generation_source": prov_source,
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
        
        # Helper to clean out internal template prefixes
        def _clean_scaffold(val: str) -> str:
            v = re.sub(r"^(?:Manh mối|Bước ngoặt|Reveal)\s*\d*\s*[-:]?\s*", "", str(val or "")).strip()
            v = re.sub(r"^Chân tướng sự thật về bí mật\s+", "", v).strip()
            return v

        protag = str(sel_idea.get("protagonist") or "").strip()
        if protag.lower() in ("nhân vật chính", "protagonist", ""):
            if any(w in clean_topic.lower() for w in ["cháu", "người cháu"]):
                protag = "Người cháu"
            elif any(w in clean_topic.lower() for w in ["công sở", "văn phòng", "công ty", "đồng nghiệp"]):
                protag = "Hà"
            else:
                protag = "Tuấn"

        rel = sel_idea.get("relationship") or ""
        if not rel:
            if any(w in clean_topic.lower() for w in ["ông nội", "bà nội", "cha", "mẹ", "gia đình", "cháu", "con", "ruột"]):
                rel = "Người thân trong gia đình"
            elif any(w in clean_topic.lower() for w in ["công sở", "văn phòng", "công ty", "đồng nghiệp", "sếp"]):
                rel = "Đồng nghiệp"
            else:
                rel = "Người thân"

        secret = sel_idea.get("central_secret") or sel_idea.get("core_mystery") or clean_topic
        mystery_q = sel_idea.get("mystery_question") or f"Điều gì đã thực sự xảy ra đằng sau uẩn khúc của {protag}?"
        false_lead = sel_idea.get("false_lead") or "Nghi ngờ ban đầu hướng về người ngoài hoặc sự phản bội."

        clues_data = sel_idea.get("clues") or []
        if sel_idea:
            clue1 = _clean_scaffold(sel_idea.get("clue_1") or (clues_data[0] if isinstance(clues_data, list) and len(clues_data) > 0 else f"Dấu vết vật chứng liên quan đến {clean_topic[:60]}."))
            clue2 = _clean_scaffold(sel_idea.get("clue_2") or (clues_data[1] if isinstance(clues_data, list) and len(clues_data) > 1 else f"Lời khai mâu thuẫn của những người liên quan đến {clean_topic[:60]}."))
            clue3 = _clean_scaffold(sel_idea.get("clue_3") or (clues_data[2] if isinstance(clues_data, list) and len(clues_data) > 2 else f"Chứng từ hồ sơ xác thực mốc thời gian liên quan đến {clean_topic[:60]}."))
            rev1 = _clean_scaffold(sel_idea.get("reveal_1") or sel_idea.get("possible_reveal") or f"Hé lộ nhân chứng hoặc góc nhìn mới đảo ngược suy đoán về {clean_topic[:60]}.")
            raw_rev2 = sel_idea.get("reveal_2") or f"Chân tướng sự thật liên quan đến {secret[:80]}."
            rev2 = _clean_scaffold(raw_rev2)
        else:
            clue1 = f"Dấu vết và chứng từ liên quan đến {clean_topic[:60]}."
            clue2 = f"Nhân chứng và mốc thời gian mâu thuẫn xoay quanh {clean_topic[:60]}."
            clue3 = f"Hồ sơ tài liệu xác thực nguồn cơn {clean_topic[:60]}."
            rev1 = f"Bước ngoặt ban đầu làm thay đổi nhận thức về {clean_topic[:60]}."
            rev2 = f"Sự thật cốt lõi về {clean_topic[:60]}."
        payoff = sel_idea.get("emotional_payoff") or sel_idea.get("emotional_angle") or "Hóa giải hiểu lầm trong nước mắt, sự thấu hiểu và tha thứ giữa những người trong cuộc."
        reflection = sel_idea.get("reflection_theme") or "Đằng sau cánh cửa đóng kín, sự thật dù bất ngờ nhưng là nhịp cầu duy nhất để chữa lành."
        hook_arch = sel_idea.get("hook_archetype") or "BÍ MẬT GIA ĐÌNH"
        twist_arch = sel_idea.get("twist_archetype") or "BƯỚC NGOẶT KÉP"
        try:
            n_score = float(sel_idea.get("novelty_score") or 8.8)
        except Exception:
            n_score = 8.8

        orig_topic = sel_idea.get("original_user_topic") or clean_topic or proj_meta.get("original_user_topic") or proj_meta.get("topic")
        top_intent = sel_idea.get("topic_intent")
        top_score = sel_idea.get("topic_adherence_score")
        if top_score is None:
            top_score = 100.0
        else:
            try:
                top_score = float(top_score)
            except Exception:
                top_score = 100.0

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
            novelty_score=n_score,
            original_user_topic=orig_topic,
            topic_intent=top_intent,
            topic_adherence_score=top_score
        )

        provider = self.get_provider()
        prov_source = "MOCK" if isinstance(provider, MockScriptAIProvider) else "REAL_AI"
        logger.debug(
            f"[Lineage Stage=STORY_BIBLE] project_id={project_id}, original_user_topic='{orig_topic}', "
            f"selected_idea_title='{working_title}', premise='{hook}', secret='{secret}', "
            f"reveal_1='{rev1}', reveal_2='{rev2}', provider={provider.provider_name}, "
            f"model={getattr(provider, 'default_model', 'unknown')}, source={prov_source}"
        )
        planner = StoryPlanner(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)

        # Generate using provider (StoryPlanner automatically validates & repairs causal/knowledge/clue/reveal logic)
        story_bible = planner.create_story_bible_from_idea(idea=idea, episode_id=project_id)
        if orig_topic and not story_bible.original_user_topic:
            story_bible.original_user_topic = orig_topic
        if top_intent and not story_bible.topic_intent:
            story_bible.topic_intent = top_intent
        if top_score is not None and story_bible.topic_adherence is None:
            story_bible.topic_adherence = top_score

        bible_dict = story_bible.to_dict()
        bible_dict["premise"] = clean_topic or story_bible.secret
        bible_dict["characters"] = [story_bible.protagonist, *story_bible.supporting_characters]
        bible_dict["fact_lock"] = [f.to_dict() if hasattr(f, 'to_dict') else f for f in story_bible.critical_facts]
        bible_dict["original_user_topic"] = story_bible.original_user_topic
        bible_dict["topic_intent"] = story_bible.topic_intent
        bible_dict["topic_adherence"] = story_bible.topic_adherence
        bible_dict["generation_source"] = prov_source

        bible_path = story_dir / "story_bible.json"
        with open(bible_path, "w", encoding="utf-8") as f:
            json.dump(bible_dict, f, ensure_ascii=False, indent=2)

        bible_root_path = proj_dir / "story_bible.json"
        with open(bible_root_path, "w", encoding="utf-8") as f:
            json.dump(bible_dict, f, ensure_ascii=False, indent=2)

        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    p_curr = json.load(f)
                p_curr["title"] = story_bible.title or working_title
                p_curr["topic"] = clean_topic
                p_curr["original_user_topic"] = orig_topic
                p_curr["topic_intent"] = top_intent
                p_curr["topic_adherence"] = story_bible.topic_adherence
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
            if "STORY_BIBLE_TOPIC_DRIFT" in bible_qc.rule_codes:
                raise ValueError(
                    f"Story Bible trôi dạt chủ đề: {'; '.join(bible_qc.logic_issues)}. "
                    f"Bị chặn bởi Cross-Stage Topic Gate 2! Vui lòng tạo lại hoặc chỉnh sửa Story Bible."
                )
            story_bible = story_qc.repair_story_bible(story_bible, bible_qc)
            with open(story_path, "w", encoding="utf-8") as f:
                json.dump(story_bible.to_dict(), f, ensure_ascii=False, indent=2)

        # Progress simulation
        for label, pct in stages:
            if stage_callback:
                stage_callback(label, pct)
            time.sleep(0.05)

        provider = self.get_provider()
        prov_source = "MOCK" if isinstance(provider, MockScriptAIProvider) else "REAL_AI"
        logger.debug(
            f"[Lineage Stage=SCRIPT] project_id={project_id}, original_user_topic='{story_bible.original_user_topic}', "
            f"title='{story_bible.title}', provider={provider.provider_name}, "
            f"model={getattr(provider, 'default_model', 'unknown')}, source={prov_source}"
        )
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

        # Attach generation_source to script and project metadata
        script_dict = script.to_dict()
        script_dict["generation_source"] = prov_source

        # Save script
        script_dir = proj_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "full_script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)

        qc_dict = asdict(qc_report)
        qc_dict["generation_source"] = prov_source
        qc_path = script_dir / "qc_report.json"
        with open(qc_path, "w", encoding="utf-8") as f:
            json.dump(qc_dict, f, ensure_ascii=False, indent=2)

        # Save to history
        hist_dir = script_dir / "history"
        hist_dir.mkdir(parents=True, exist_ok=True)
        hist_file = hist_dir / f"script_{int(time.time())}.json"
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)

        # Update project.json with generation source
        p_json = proj_dir / "project.json"
        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    p_curr = json.load(f)
                p_curr["generation_source"] = prov_source
                p_curr["qc_status"] = qc_report.status
                with open(p_json, "w", encoding="utf-8") as f:
                    json.dump(p_curr, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        total_words = script.total_words or sum(len(s.text.split()) for s in script.segments)
        return {
            "script": script_dict,
            "qc_report": qc_dict,
            "generation_source": prov_source,
            "stats": {
                "word_count": total_words,
                "segment_count": len(script.segments),
                "estimated_duration_min": round(total_words / 160, 1),
                "qc_status": qc_report.status,
                "leakage_count": sum(1 for e in qc_report.evidence_issues if "LEAKAGE" in e.get("rule", "")),
                "generation_source": prov_source,
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
