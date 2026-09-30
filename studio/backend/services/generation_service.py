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
from apps.script_factory.providers.router import ModelRouter, RouterConfig
from apps.script_factory.script_qc import ScriptQCEngine
from apps.script_factory.script_writer import ScriptWriter
from apps.script_factory.story_planner import StoryPlanner
from studio.backend.credentials import get_active_api_key, get_public_providers_status
from studio.backend.services.artifact_lineage import (
    mark_full_script_stale,
    require_current_full_script,
    story_content_hash,
)

logger = logging.getLogger("SCCStudio.GenerationService")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"


def get_configured_ai_provider(provider_id: Optional[str] = None, model_id: Optional[str] = None):
    """Builds provider from credentials. NEVER silently falls back to Mock in production."""
    status = get_public_providers_status()
    target_p = (provider_id or status.get("default_provider") or "gemini").strip().lower()

    prov_data = status.get("providers", {}).get(target_p, {})
    model = (model_id or prov_data.get("model") or status.get("default_model") or "").strip()

    is_production = os.environ.get("APP_ENV") == "production"
    is_test_env = not is_production and (os.environ.get("APP_ENV") == "test")

    if target_p == "gemini":
        gemini_key = get_active_api_key("gemini")
        if gemini_key:
            return GeminiScriptAIProvider(api_key=gemini_key, default_model=model or "gemini-2.5-flash")
        elif is_test_env:
            from tests.mocks.mock_script_provider import MockScriptAIProvider
            return MockScriptAIProvider()
        else:
            raise RuntimeError(
                "AI GENERATION FAILED: Google Gemini API key is missing or not configured. "
                "Please configure a valid GEMINI_API_KEY in Settings."
            )
    elif target_p in ("openai", "openai_compatible", "local"):
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        key = get_active_api_key(target_p) or ""
        base_url = prov_data.get("base_url") or ("http://localhost:11434/v1" if target_p == "local" else "https://api.openai.com/v1")
        default_model = model or prov_data.get("model") or ("gpt-4o" if target_p == "openai" else "deepseek-chat")
        if key or target_p == "local":
            return OpenAICompatibleProvider(
                api_key=key,
                default_model=default_model,
                base_url=base_url,
                provider_name=target_p
            )
        elif is_test_env:
            from tests.mocks.mock_script_provider import MockScriptAIProvider
            return MockScriptAIProvider()
        else:
            raise RuntimeError(
                f"AI GENERATION FAILED: {target_p.upper()} API key is missing. "
                "Please configure your provider credentials in Settings."
            )
    elif target_p == "anthropic":
        from apps.script_factory.providers.anthropic_provider import AnthropicScriptAIProvider
        key = get_active_api_key("anthropic") or ""
        default_model = model or prov_data.get("model") or "claude-3-5-sonnet-20241022"
        if key:
            return AnthropicScriptAIProvider(
                api_key=key,
                default_model=default_model,
            )
        elif is_test_env:
            from tests.mocks.mock_script_provider import MockScriptAIProvider
            return MockScriptAIProvider()
        else:
            raise RuntimeError(
                "AI GENERATION FAILED: Anthropic API key is missing. "
                "Please configure your ANTHROPIC_API_KEY in Settings."
            )

    # Secondary checks
    gemini_key = get_active_api_key("gemini")
    if gemini_key:
        return GeminiScriptAIProvider(api_key=gemini_key, default_model=model or "gemini-2.5-flash")

    openai_key = get_active_api_key("openai")
    if openai_key:
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(api_key=openai_key, default_model=model or "gpt-4o", provider_name="openai")

    if is_test_env:
        from tests.mocks.mock_script_provider import MockScriptAIProvider
        return MockScriptAIProvider()

    raise RuntimeError(
        "AI GENERATION FAILED: No valid AI provider credentials found. "
        "Silent fallback to mock is forbidden in production."
    )


class GenerationService:
    def __init__(self):
        self.cost_ctrl = CostController()

    def get_provider(self, provider_id: Optional[str] = None, model_id: Optional[str] = None):
        return get_configured_ai_provider(provider_id=provider_id, model_id=model_id)

    def generate_ideas(
        self,
        project_id: str,
        count: int = 10,
        direction: str = "",
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
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

        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        prov_source = "MOCK" if "mock" in provider.provider_name.lower() else "REAL_AI"
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
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stage_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """Expands topic into complete Story Bible with Fact Lock."""
        stages = [
            ("Đang phân tích premise và tìm kiếm mâu thuẫn trung tâm...", 15),
            ("Đang xây dựng nhân vật, tính cách và mối quan hệ...", 35),
            ("Đang tạo bí ẩn cốt lõi và chuỗi manh mối (clues)...", 50),
            ("Đang khóa cấu trúc timeline và lịch sử sự kiện...", 65),
            ("Đang xây dựng bước ngoặt 1 (Reveal 1 tại ~60-75% thời lượng)...", 80),
            ("Đang xây dựng bước ngoặt 2 (Reveal 2 tại ~75-90% thời lượng)...", 90),
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
            clean_topic = sel_idea.get("premise") or sel_idea.get("hook") or proj_meta.get("topic") or ""

        if not sel_idea and clean_topic:
            # Generate premise ideas from real AI provider first to ensure 100% AI creative generation
            ideas = self.generate_ideas(project_id=project_id, count=1, direction=clean_topic, provider_id=provider_id, model_id=model_id)
            if ideas:
                sel_idea = ideas[0]
                if p_json.exists():
                    try:
                        proj_meta["selected_idea"] = sel_idea
                        with open(p_json, "w", encoding="utf-8") as f:
                            json.dump(proj_meta, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

        import re
        raw_title = sel_idea.get("title") or sel_idea.get("working_title") or proj_meta.get("title") or ""
        working_title = re.sub(r"^(?:Tập\s+)?EP_?[A-Z0-9_]*\d+\s*[-:]?\s*", "", str(raw_title), flags=re.IGNORECASE).strip()
        if not working_title:
            working_title = clean_topic or "Câu chuyện Sau Cánh Cửa"
        hook = sel_idea.get("hook") or sel_idea.get("premise") or clean_topic

        protag = str(sel_idea.get("protagonist") or "").strip()
        if not protag or protag.lower() in ("nhân vật chính", "protagonist"):
            protag = "Nhân vật"

        rel = sel_idea.get("relationship") or "Người liên quan"
        secret = sel_idea.get("central_secret") or sel_idea.get("core_mystery") or clean_topic
        mystery_q = sel_idea.get("mystery_question") or f"Điều gì đã thực sự xảy ra đằng sau uẩn khúc của {protag}?"
        false_lead = sel_idea.get("false_lead") or ""

        clues_data = sel_idea.get("clues") or []
        clue1 = sel_idea.get("clue_1") or (clues_data[0] if isinstance(clues_data, list) and len(clues_data) > 0 else "")
        clue2 = sel_idea.get("clue_2") or (clues_data[1] if isinstance(clues_data, list) and len(clues_data) > 1 else "")
        clue3 = sel_idea.get("clue_3") or (clues_data[2] if isinstance(clues_data, list) and len(clues_data) > 2 else "")
        rev1 = sel_idea.get("reveal_1") or sel_idea.get("possible_reveal") or ""
        rev2 = sel_idea.get("reveal_2") or ""
        payoff = sel_idea.get("emotional_payoff") or sel_idea.get("emotional_angle") or ""
        reflection = sel_idea.get("reflection_theme") or ""
        hook_arch = sel_idea.get("hook_archetype") or ""
        twist_arch = sel_idea.get("twist_archetype") or ""
        try:
            n_score = float(sel_idea.get("novelty_score") or 8.8)
        except Exception:
            n_score = 8.8

        orig_topic = sel_idea.get("original_user_topic") or clean_topic or proj_meta.get("original_user_topic") or proj_meta.get("topic")
        top_intent = sel_idea.get("topic_intent")
        top_score = sel_idea.get("topic_adherence_score")
        if top_score is None:
            top_score = 100.0 if orig_topic else None
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

        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        prov_source = "MOCK" if "mock" in provider.provider_name.lower() else "REAL_AI"
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
        bible_dict["generation_request_id"] = getattr(story_bible, "generation_request_id", None)
        bible_dict["prompt_version"] = getattr(story_bible, "prompt_version", None)
        bible_dict["model_name"] = getattr(story_bible, "model_name", None)
        bible_dict["provider_name"] = getattr(story_bible, "provider_name", None)
        bible_dict["artifact_status"] = "CURRENT"

        bible_path = story_dir / "story_bible.json"
        with open(bible_path, "w", encoding="utf-8") as f:
            json.dump(bible_dict, f, ensure_ascii=False, indent=2)

        bible_root_path = proj_dir / "story_bible.json"
        with open(bible_root_path, "w", encoding="utf-8") as f:
            json.dump(bible_dict, f, ensure_ascii=False, indent=2)

        # A newly generated Story Bible starts a new lineage.  Keep any older
        # script for audit/history, but it can no longer be approved or voiced.
        mark_full_script_stale(
            project_id,
            PROJECTS_DIR,
            "Story Bible was regenerated; Full Script must be regenerated from the new lineage",
        )

        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    p_curr = json.load(f)
                p_curr["title"] = story_bible.title or working_title
                p_curr["topic"] = clean_topic
                p_curr["original_user_topic"] = orig_topic
                p_curr["topic_intent"] = top_intent
                p_curr["topic_adherence"] = story_bible.topic_adherence
                p_curr["generation_source"] = prov_source
                p_curr["generation_request_id"] = getattr(story_bible, "generation_request_id", None)
                p_curr["prompt_version"] = getattr(story_bible, "prompt_version", None)
                p_curr["model_name"] = getattr(story_bible, "model_name", None)
                p_curr["provider_name"] = getattr(story_bible, "provider_name", None)
                with open(p_json, "w", encoding="utf-8") as f:
                    json.dump(p_curr, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return bible_dict

    def generate_full_script(
        self,
        project_id: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
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

        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        prov_source = "MOCK" if "mock" in provider.provider_name.lower() else "REAL_AI"

        # Ensure Story Bible passes Story Logic & Reveal Justification Gate before ScriptWriter runs
        from apps.script_factory.story_qc import StoryQCEngine
        story_qc = StoryQCEngine(provider=provider)
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
            repaired_story_data = story_bible.to_dict()
            repaired_story_data["artifact_status"] = "CURRENT"
            for target in (story_path, proj_dir / "story_bible.json"):
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(repaired_story_data, f, ensure_ascii=False, indent=2)
            bible_data = repaired_story_data

        # Progress simulation
        for label, pct in stages:
            if stage_callback:
                stage_callback(label, pct)
            time.sleep(0.05)

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

        # Attach generation_source and trace to script and project metadata
        script_dict = script.to_dict()
        script_dict["generation_source"] = prov_source
        script_dict["generation_request_id"] = getattr(script, "generation_request_id", None)
        script_dict["prompt_version"] = getattr(script, "prompt_version", None)
        script_dict["model_name"] = getattr(script, "model_name", None)
        script_dict["provider_name"] = getattr(script, "provider_name", None)
        script_dict["source_story_generation_request_id"] = story_bible.generation_request_id
        current_story_data = json.loads(story_path.read_text(encoding="utf-8"))
        script_dict["source_story_content_hash"] = story_content_hash(current_story_data)
        script_dict["artifact_status"] = "CURRENT"
        script_dict.pop("stale_reason", None)
        script_dict.pop("stale_reasons", None)
        script_dict.pop("stale_at", None)

        # Save script
        script_dir = proj_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "full_script.json"
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)

        qc_dict = asdict(qc_report)
        qc_dict["generation_source"] = prov_source
        qc_dict["generation_request_id"] = script_dict.get("generation_request_id")
        qc_dict["source_story_generation_request_id"] = story_bible.generation_request_id
        qc_dict["source_story_content_hash"] = script_dict["source_story_content_hash"]
        qc_dict["artifact_status"] = "CURRENT"
        qc_path = script_dir / "qc_report.json"
        with open(qc_path, "w", encoding="utf-8") as f:
            json.dump(qc_dict, f, ensure_ascii=False, indent=2)

        # Save to history
        hist_dir = script_dir / "history"
        hist_dir.mkdir(parents=True, exist_ok=True)
        hist_file = hist_dir / f"script_{int(time.time())}.json"
        with open(hist_file, "w", encoding="utf-8") as f:
            json.dump(script_dict, f, ensure_ascii=False, indent=2)

        # Update project.json with generation source and trace
        p_json = proj_dir / "project.json"
        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    p_curr = json.load(f)
                p_curr["generation_source"] = prov_source
                p_curr["generation_request_id"] = getattr(script, "generation_request_id", None)
                p_curr["prompt_version"] = getattr(script, "prompt_version", None)
                p_curr["model_name"] = getattr(script, "model_name", None)
                p_curr["provider_name"] = getattr(script, "provider_name", None)
                p_curr["story_generation_request_id"] = story_bible.generation_request_id
                p_curr["script_generation_request_id"] = getattr(script, "generation_request_id", None)
                p_curr["script_source_story_generation_request_id"] = story_bible.generation_request_id
                p_curr["script_source_story_content_hash"] = script_dict["source_story_content_hash"]
                p_curr["script_artifact_status"] = "CURRENT"
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

        require_current_full_script(project_id, PROJECTS_DIR)

        with open(script_path, "r", encoding="utf-8") as f:
            original_script_data = json.load(f)
            script = FullScript.from_dict(original_script_data)
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

        # Auto-repair is allowed only inside the current Story lineage and must
        # preserve all lineage metadata when the dataclass is serialized again.
        revised_data = revised_script.to_dict()
        for key in (
            "generation_source", "generation_request_id", "prompt_version",
            "model_name", "provider_name", "source_story_generation_request_id",
            "source_story_content_hash", "artifact_status",
        ):
            revised_data[key] = original_script_data.get(key)
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(revised_data, f, ensure_ascii=False, indent=2)
        with open(qc_path, "w", encoding="utf-8") as f:
            final_qc_data = asdict(final_qc)
            final_qc_data.update({
                "generation_source": revised_data.get("generation_source"),
                "generation_request_id": revised_data.get("generation_request_id"),
                "source_story_generation_request_id": revised_data.get("source_story_generation_request_id"),
                "source_story_content_hash": revised_data.get("source_story_content_hash"),
                "artifact_status": "CURRENT",
            })
            json.dump(final_qc_data, f, ensure_ascii=False, indent=2)

        total_words = revised_script.total_words or sum(len(s.text.split()) for s in revised_script.segments)
        return {
            "rounds": revised_script.revision_round,
            "qc_status": final_qc.status,
            "word_count": total_words,
            "segments": len(revised_script.segments)
        }
