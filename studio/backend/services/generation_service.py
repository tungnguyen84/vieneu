"""Generation Service for AI Ideas, Story Bible, and Full Script from Zero."""
from __future__ import annotations

from dataclasses import asdict
import copy
import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.script_factory.auto_revision import AutoRevisionManager, MAX_REVISION_ROUNDS
from apps.script_factory.cost_control import CostController
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.models import IdeaItem, StoryBible, FullScript, ScriptSegment
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider
from apps.script_factory.providers.router import ModelRouter, RouterConfig
from apps.script_factory.script_qc import ScriptQCEngine
from apps.script_factory.script_writer import ScriptWriter
from apps.script_factory.story_planner import StoryPlanner
from studio.backend.credentials import get_active_api_key, get_active_api_keys, get_public_providers_status
from studio.backend.services.artifact_lineage import (
    mark_full_script_stale,
    require_current_full_script,
    story_content_hash,
    script_content_hash,
    invalidate_script_approval,
)

logger = logging.getLogger("SCCStudio.GenerationService")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"


def _assert_story_snapshot(story_path: Path, expected_hash: str, request_id: str):
    current = json.loads(story_path.read_text(encoding='utf-8'))
    if story_content_hash(current) != expected_hash or current.get('generation_request_id') != request_id:
        raise ValueError("Cốt truyện đã thay đổi trong lúc viết; không lưu Script vào lineage mới. Vui lòng tạo lại kịch bản.")


def _qc_problem_score(report) -> Tuple[int, int, int]:
    """Lower is better; an unavailable reviewer cannot prove improvement."""
    issues = [i for i in [*report.evidence_issues, *report.fact_conflicts] if isinstance(i, dict)]
    critical = sum(1 for i in issues if str(i.get("severity", "")).upper() == "CRITICAL")
    if report.status == "FAIL":
        critical = max(critical, 1)
    total = len(issues) + len(report.logic_issues) + len(report.repetition_issues)
    unavailable = (getattr(report, 'semantic_review', None) or {}).get('status') == 'ERROR'
    return int(unavailable), critical, total


def _revise_keeping_best(rev_manager, script, story_bible, qc_report, round_ceiling: int, model: Optional[str] = None):
    """Runs AI revision rounds up to ``round_ceiling`` and returns the best round.

    Revisions mutate the script in place and a later rewrite can make things
    worse, so each round works on a copy and the version with the fewest QC
    problems wins. The returned script carries the last consumed round number.
    """
    current_script, current_qc = script, qc_report
    best_script, best_qc = copy.deepcopy(script), qc_report
    seen = {script_content_hash(script)}
    stalled_rounds = 0
    def problem_keys(report):
        issues = [*report.evidence_issues, *report.fact_conflicts,
                  *report.logic_issues, *report.repetition_issues]
        return {json.dumps({k: issue.get(k) for k in ('rule', 'target', 'segment_id', 'segment_ids')},
                           sort_keys=True, default=str) if isinstance(issue, dict) else str(issue)
                for issue in issues}
    while current_qc.status != "PASS":
        if (getattr(current_qc, 'semantic_review', None) or {}).get('status') == 'ERROR':
            logger.warning('Auto-repair paused: semantic reviewer failed; retain draft and recheck QC.')
            break
        previous_round = current_script.revision_round
        previous_qc = current_qc
        logger.info(f"Vòng sửa kịch bản {current_script.revision_round + 1}/{round_ceiling}...")
        try:
            try:
                current_script, current_qc = rev_manager.auto_revise_and_recheck(
                    script=copy.deepcopy(current_script),
                    story_bible=story_bible,
                    qc_report=current_qc,
                    max_rounds=round_ceiling,
                    model=model,
                )
            except TypeError as te:
                if "model" in str(te) or "unexpected keyword" in str(te):
                    current_script, current_qc = rev_manager.auto_revise_and_recheck(
                        script=copy.deepcopy(current_script),
                        story_bible=story_bible,
                        qc_report=current_qc,
                        max_rounds=round_ceiling,
                    )
                else:
                    raise
        except Exception:
            logger.exception('Auto-repair failed; retaining the best draft and its failing QC report')
            break
        fingerprint = script_content_hash(current_script)
        repeated = fingerprint in seen
        changed_problems = problem_keys(current_qc) != problem_keys(previous_qc)
        if current_qc.status == "PASS" or (not repeated and (
            _qc_problem_score(current_qc) < _qc_problem_score(best_qc) or (
                _qc_problem_score(current_qc) == _qc_problem_score(best_qc) and changed_problems
            )
        )):
            best_script, best_qc = copy.deepcopy(current_script), current_qc
        if not repeated and (_qc_problem_score(current_qc) < _qc_problem_score(previous_qc) or (
            _qc_problem_score(current_qc) == _qc_problem_score(previous_qc) and changed_problems
        )):
            stalled_rounds = 0
        else:
            stalled_rounds += 1
        seen.add(fingerprint)
        if current_qc.status == "PASS" or current_script.revision_round >= round_ceiling:
            break
        if repeated or stalled_rounds >= 2:
            logger.warning("Auto-repair stopped: no quality improvement; Story/targeted review required")
            break
        # Defensive stop for a provider that returns without consuming a round.
        if current_script.revision_round <= previous_round:
            break
    best_script.revision_round = current_script.revision_round
    return best_script, best_qc


def get_configured_ai_provider(provider_id: Optional[str] = None, model_id: Optional[str] = None):
    """Builds provider from credentials. NEVER silently falls back to Mock in production."""
    status = get_public_providers_status()
    target_p = (provider_id or status.get("default_provider") or "gemini").strip().lower()

    prov_data = status.get("providers", {}).get(target_p, {})
    model = (model_id or prov_data.get("model") or status.get("default_model") or "").strip()

    is_production = os.environ.get("APP_ENV") == "production"
    is_test_env = not is_production and (os.environ.get("APP_ENV") == "test")

    if target_p == "gemini":
        gemini_keys = get_active_api_keys("gemini")
        if gemini_keys:
            return GeminiScriptAIProvider(api_keys=gemini_keys, default_model=model or "gemini-2.5-flash")
        elif is_test_env:
            from tests.mocks.mock_script_provider import MockScriptAIProvider
            return MockScriptAIProvider(default_model=model or "gemini-2.5-flash")
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
            return MockScriptAIProvider(default_model=default_model)
        else:
            raise RuntimeError(
                f"AI GENERATION FAILED: {target_p.upper()} API key is missing or not configured. "
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
        return GeminiScriptAIProvider(api_keys=get_active_api_keys("gemini"), default_model=model or "gemini-2.5-flash")

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
                **idea.to_dict(),
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
                "novelty_status": idea.status,
                "is_duplicate": idea.status == 'BLOCKED_DUPLICATE',
                "original_user_topic": getattr(idea, "original_user_topic", user_topic or None),
                "topic_intent": getattr(idea, "topic_intent", topic_intent_obj.to_dict() if topic_intent_obj else None),
                "topic_adherence_score": adherence_sc if adherence_sc is not None else (100.0 if user_topic else None),
                "generation_source": prov_source,
            })
        project_dir = PROJECTS_DIR / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / 'idea_bank.json').write_text(json.dumps({
            'project_id': project_id, 'direction': user_topic, 'ideas': results,
        }, ensure_ascii=False, indent=2), encoding='utf-8')
        return results

    def generate_source_story(self, project_id, provider_id=None, model_id=None):
        from apps.script_factory.adaptation import create_bible
        from apps.script_factory.story_qc import StoryQCEngine
        from studio.backend.services.source_service import current_context, assert_context, project_lock, write_json
        project = PROJECTS_DIR / project_id
        context = current_context(project)
        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        if not context or not getattr(provider, 'requires_grounded_review', False):
            raise ValueError('Cần brief được chọn và provider AI thật.')
        bible = create_bible(provider, project_id, context)
        qc = StoryQCEngine(provider=provider)
        report = qc.audit_story_bible(bible)
        if report.status != 'PASS' and not all(i.get('rule') == 'SEMANTIC_REVIEW_FAILED' for i in report.issues):
            bible = qc.repair_story_bible(bible, report)
            report = qc.audit_story_bible(bible)
        data = bible.to_dict()
        data.update(premise=context['brief']['direction']['hook'], characters=[bible.protagonist, *bible.supporting_characters],
                    fact_lock=[f.to_dict() for f in bible.critical_facts], story_qc_report=report.to_dict(), artifact_status='CURRENT')
        with project_lock(project):
            assert_context(project, context)
            write_json(project / 'story' / 'story_bible.json', data)
            write_json(project / 'story_bible.json', data)
            mark_full_script_stale(project_id, PROJECTS_DIR, 'Cốt truyện từ nguồn đã tạo lại.')
            invalidate_script_approval(project_id, PROJECTS_DIR)
        return data

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

        if (PROJECTS_DIR / project_id / 'adaptation' / 'brief.json').exists():
            return self.generate_source_story(project_id, provider_id, model_id)
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
        bible_dict["premise"] = hook or story_bible.secret
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
        invalidate_script_approval(project_id, PROJECTS_DIR)

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

    def repair_story_bible(
        self,
        project_id: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs Gemini Auto-Repair on the project's Story Bible to resolve logic and timeline issues."""
        proj_dir = PROJECTS_DIR / project_id
        story_path = proj_dir / "story" / "story_bible.json"
        if not story_path.exists():
            story_path = proj_dir / "story_bible.json"
        if not story_path.exists():
            raise ValueError("Story Bible chưa tồn tại để sửa logic.")

        with open(story_path, "r", encoding="utf-8") as f:
            bible_data = json.load(f)
        story_bible = StoryBible.from_dict(bible_data)

        from studio.backend.services.source_service import assert_context, project_lock
        assert_context(proj_dir, story_bible.adaptation_context)
        original_hash = story_content_hash(bible_data)
        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        from apps.script_factory.story_qc import StoryQCEngine
        from apps.script_factory.semantic_review import story_bible_content_hash
        before_hash = story_bible_content_hash(story_bible)
        story_qc = StoryQCEngine(provider=provider)
        bible_qc = story_qc.audit_story_bible(story_bible)
        repaired_bible = story_qc.repair_story_bible(story_bible, bible_qc)
        recheck_qc = story_qc.audit_story_bible(repaired_bible)

        changed = (before_hash != story_bible_content_hash(repaired_bible)
                   or story_bible.generation_request_id != repaired_bible.generation_request_id)
        repaired_data = {**bible_data, **repaired_bible.to_dict()}
        if changed:
            repaired_data['characters'] = [repaired_bible.protagonist, *repaired_bible.supporting_characters]
            repaired_data['fact_lock'] = [fact.to_dict() for fact in repaired_bible.critical_facts]
        repaired_data["story_qc_report"] = recheck_qc.to_dict()
        repaired_data["artifact_status"] = "CURRENT"

        with project_lock(proj_dir):
            assert_context(proj_dir, story_bible.adaptation_context)
            _assert_story_snapshot(story_path, original_hash, story_bible.generation_request_id)
            # Save to both locations
            for target in (proj_dir / "story" / "story_bible.json", proj_dir / "story_bible.json"):
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(target, "w", encoding="utf-8") as f:
                    json.dump(repaired_data, f, ensure_ascii=False, indent=2)

            if changed:
                mark_full_script_stale(project_id, PROJECTS_DIR, "Story Bible was repaired; Full Script must be regenerated")
            if changed or recheck_qc.status != 'PASS':
                invalidate_script_approval(project_id, PROJECTS_DIR)

        return {
            "story_bible": repaired_data,
            "qc_report": recheck_qc.to_dict(),
            "status": recheck_qc.status,
            "issues": recheck_qc.issues,
            "story_changed": changed,
        }

    def generate_full_script(
        self,
        project_id: str,
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stage_callback: Optional[Callable[[str, int], None]] = None
    ) -> Dict[str, Any]:
        """Writes full script using Script Factory V1.3.1a and runs Script QC + Auto-Repair."""
        proj_dir = PROJECTS_DIR / project_id
        story_path = proj_dir / "story" / "story_bible.json"
        if not story_path.exists():
            raise ValueError("Story Bible chưa được tạo hoặc chưa duyệt. Vui lòng duyệt Story Bible trước!")

        with open(story_path, "r", encoding="utf-8") as f:
            bible_data = json.load(f)
        story_bible = StoryBible.from_dict(bible_data)

        from studio.backend.services.source_service import assert_context, project_lock
        assert_context(proj_dir, story_bible.adaptation_context)
        if story_bible.adaptation_context:
            project_data = json.loads((proj_dir / 'project.json').read_text(encoding='utf-8'))
            if project_data.get('stage_statuses', {}).get('02_story') != 'APPROVED':
                raise ValueError('Duyệt cốt truyện từ nguồn trước khi viết kịch bản.')
        provider = self.get_provider(provider_id=provider_id, model_id=model_id)
        prov_source = "MOCK" if "mock" in provider.provider_name.lower() else "REAL_AI"

        # Ensure Story Bible passes Story Logic & Reveal Justification Gate before ScriptWriter runs
        from apps.script_factory.story_qc import StoryQCEngine
        story_qc = StoryQCEngine(provider=provider)
        logger.info(f"Dùng provider {provider.provider_name} / {getattr(provider, 'default_model', '?')}")
        logger.info("Kiểm tra logic Cốt truyện (Story Bible)...")
        bible_qc = story_qc.audit_story_bible(story_bible)
        logger.info(f"Cốt truyện: {bible_qc.status}" + (f" — {', '.join(bible_qc.rule_codes)}" if bible_qc.rule_codes else ""))
        if story_bible.adaptation_context and bible_qc.status != 'PASS':
            raise ValueError('QC cốt truyện từ nguồn chưa đạt hoặc chưa hiện hành. Mở Cốt truyện để kiểm tra/sửa và duyệt lại; không tự thay cốt truyện đã duyệt trong lúc viết kịch bản.')
        if (
            bible_qc.status != "PASS"
            or (not story_bible.adaptation_context and (not story_bible.causal_chains
            or not story_bible.knowledge_ledger
            or not story_bible.structured_clues
            or not story_bible.reveal_justifications))
        ):
            if "STORY_BIBLE_TOPIC_DRIFT" in bible_qc.rule_codes:
                raise ValueError(
                    f"Story Bible trôi dạt chủ đề: {'; '.join(bible_qc.logic_issues)}. "
                    f"Bị chặn bởi Cross-Stage Topic Gate 2! Vui lòng tạo lại hoặc chỉnh sửa Story Bible."
                )
            logger.info("Cốt truyện chưa đạt, đang để AI tự sửa (tối đa 3 vòng)...")
            story_bible = story_qc.repair_story_bible(story_bible, bible_qc)
            repaired_qc = story_qc.audit_story_bible(story_bible)
            if repaired_qc.status != "PASS":
                remaining_rules = ", ".join(repaired_qc.rule_codes) or "UNKNOWN_STORY_QC"
                remaining_details = "; ".join(repaired_qc.logic_issues[:5])
                raise ValueError(
                    "Story Bible vẫn chưa đạt sau khi tự sửa "
                    f"({remaining_rules}): {remaining_details}. "
                    "Vui lòng tạo lại hoặc sửa Cốt truyện trước khi tạo Kịch bản."
                )
            repaired_story_data = story_bible.to_dict()
            repaired_story_data["artifact_status"] = "CURRENT"
            with project_lock(proj_dir):
                assert_context(proj_dir, story_bible.adaptation_context)
                _assert_story_snapshot(story_path, story_content_hash(bible_data), bible_data.get('generation_request_id'))
                for target in (story_path, proj_dir / "story_bible.json"):
                    with open(target, "w", encoding="utf-8") as f:
                        json.dump(repaired_story_data, f, ensure_ascii=False, indent=2)
            bible_data = repaired_story_data

        source_story_hash = story_content_hash(bible_data)

        logger.debug(
            f"[Lineage Stage=SCRIPT] project_id={project_id}, original_user_topic='{story_bible.original_user_topic}', "
            f"title='{story_bible.title}', provider={provider.provider_name}, "
            f"model={getattr(provider, 'default_model', 'unknown')}, source={prov_source}"
        )
        logger.info("Đang viết kịch bản (viết một lần cả tập; chỉ chia 2 phần nếu bị cắt cụt)...")
        from apps.script_factory.scene_outline import outline_fulfills_contract
        require_contract = bool(getattr(provider, 'requires_grounded_review', False))
        if (not getattr(story_bible, "scene_outline", None)
                or (require_contract and not outline_fulfills_contract(story_bible, story_bible.scene_outline))):
            try:
                from apps.script_factory.scene_outline import build_scene_outline
                if hasattr(provider, "complete_json") and callable(provider.complete_json):
                    m_name = getattr(provider, "default_model", None)
                    story_bible.scene_outline = build_scene_outline(
                        story_bible,
                        lambda system, prompt: provider.complete_json(system, prompt, model=m_name),
                        require_contract=require_contract,
                    )
                    if story_bible.scene_outline:
                        logger.info(f"Đã lập kế hoạch {len(story_bible.scene_outline)} cảnh cho kịch bản.")
            except Exception as e:
                logger.warning(f"Could not pre-build scene outline for Story Bible: {e}")
        if require_contract and not outline_fulfills_contract(story_bible, getattr(story_bible, 'scene_outline', None)):
            raise ValueError('AI chưa lập được dàn cảnh trả lời đủ manh mối và hệ quả. Giữ nguyên cốt truyện, không ghi đè kịch bản hiện tại.')

        writer = ScriptWriter(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)
        script = writer.generate_script_from_bible(story_bible)

        # Run automated QC and auto-repair if any issue is found
        qc_engine = ScriptQCEngine(provider=provider, cost_controller=self.cost_ctrl, episodes_root=PROJECTS_DIR)
        logger.info(f"Đã viết {len(script.segments)} phân đoạn. Đang chạy QC kịch bản...")
        qc_report = qc_engine.run_qc(script=script, story_bible=story_bible)
        if qc_report.status != "PASS":
            rev_manager = AutoRevisionManager(provider=provider, cost_controller=self.cost_ctrl, qc_engine=qc_engine)
            effective_model = model_id or getattr(provider, "requested_model", None) or getattr(provider, "default_model", None)
            script, qc_report = _revise_keeping_best(
                rev_manager, script, story_bible, qc_report, round_ceiling=MAX_REVISION_ROUNDS,
                model=effective_model,
            )

        with project_lock(proj_dir):
            assert_context(proj_dir, story_bible.adaptation_context)
            # Attach generation_source and trace to script and project metadata
            script_dict = script.to_dict()
            script_dict["generation_source"] = prov_source
            script_dict["generation_request_id"] = getattr(script, "generation_request_id", None)
            script_dict["prompt_version"] = getattr(script, "prompt_version", None)
            script_dict["model_name"] = getattr(script, "model_name", None)
            script_dict["provider_name"] = getattr(script, "provider_name", None)
            script_dict["source_story_generation_request_id"] = story_bible.generation_request_id
            _assert_story_snapshot(story_path, source_story_hash, story_bible.generation_request_id)
            script_dict["source_story_content_hash"] = source_story_hash
            script_dict["artifact_status"] = "CURRENT" if qc_report.status == "PASS" else "NEEDS_REVISION"
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
            qc_dict["artifact_status"] = "CURRENT" if qc_report.status == "PASS" else "NEEDS_REVISION"
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
                    p_curr["script_artifact_status"] = script_dict["artifact_status"]
                    p_curr["qc_status"] = qc_report.status
                    with open(p_json, "w", encoding="utf-8") as f:
                        json.dump(p_curr, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            invalidate_script_approval(project_id, PROJECTS_DIR)
            script.total_words = sum(len(s.text.split()) for s in script.segments)
            total_words = script.total_words
            script_dict["total_words"] = total_words
            return {
                "script": script_dict,
                "qc_report": qc_dict,
                "generation_source": prov_source,
                "stats": {
                    "word_count": total_words,
                    "segment_count": len(script.segments),
                    "estimated_duration_min": round(total_words / (2.7 * 60 if story_bible.adaptation_context else 160), 1),
                    "qc_status": qc_report.status,
                    "leakage_count": sum(1 for e in qc_report.evidence_issues if "LEAKAGE" in e.get("rule", "")),
                    "generation_source": prov_source,
                }
            }

    def auto_repair_script(self, project_id: str, provider_id: Optional[str] = None,
                           model_id: Optional[str] = None) -> Dict[str, Any]:
        """Applies controlled auto-revision up to 3 rounds."""
        proj_dir = PROJECTS_DIR / project_id
        script_path = proj_dir / "script" / "full_script.json"
        story_path = proj_dir / "story" / "story_bible.json"
        qc_path = proj_dir / "script" / "qc_report.json"

        if not script_path.exists() or not story_path.exists():
            raise FileNotFoundError("Script or Story Bible not found for repair.")

        with open(script_path, "r", encoding="utf-8") as f:
            original_script_data = json.load(f)
            script = FullScript.from_dict(original_script_data)
        with open(story_path, "r", encoding="utf-8") as f:
            story_data = json.load(f)
            story_bible = StoryBible.from_dict(story_data)
        from studio.backend.services.source_service import assert_context, project_lock
        assert_context(proj_dir, story_bible.adaptation_context)
        source_story_hash = story_content_hash(story_data)
        stale_reasons = list(original_script_data.get('stale_reasons') or [])
        if original_script_data.get('stale_reason'):
            stale_reasons.append(original_script_data['stale_reason'])
        story_mismatch = (
            original_script_data.get('source_story_generation_request_id') != story_bible.generation_request_id
            or original_script_data.get('source_story_content_hash') != source_story_hash
            or any("cốt truyện" in str(r).lower() or "story" in str(r).lower() for r in stale_reasons)
        )
        if original_script_data.get('generation_source') == 'REAL_AI' and story_mismatch:
            raise ValueError("Kịch bản thuộc cốt truyện cũ; cần tạo Full Script mới, không sửa tiếp bản STALE.")

        provider = self.get_provider(provider_id=provider_id, model_id=model_id) if (provider_id or model_id) else self.get_provider()
        qc_engine = ScriptQCEngine(provider=provider, cost_controller=self.cost_ctrl)
        rev_manager = AutoRevisionManager(provider=provider, cost_controller=self.cost_ctrl, qc_engine=qc_engine)

        effective_req_model = (
            model_id
            or getattr(provider, "requested_model", None)
            or getattr(provider, "default_model", None)
            or original_script_data.get("requested_model")
        )
        qc_report = qc_engine.run_qc(script=script, story_bible=story_bible, model=effective_req_model)
        starting_round = script.revision_round
        if qc_report.status == "PASS":
            revised_script, final_qc = script, qc_report
            revised_script.status = "QC_PASS"
        else:
            # Each click gets a fresh budget of AI rounds.
            revised_script, final_qc = _revise_keeping_best(
                rev_manager, script, story_bible, qc_report,
                round_ceiling=starting_round + MAX_REVISION_ROUNDS,
                model=effective_req_model,
            )

        # Auto-repair is allowed only inside the current Story lineage and must
        # preserve all lineage metadata when the dataclass is serialized again.
        revised_data = revised_script.to_dict()
        for key in (
            "generation_source", "generation_request_id", "prompt_version",
            "model_name", "provider_name", "requested_model", "actual_model",
            "writer_strategy", "source_story_generation_request_id",
            "source_story_content_hash",
        ):
            if original_script_data.get(key) is not None:
                revised_data[key] = original_script_data.get(key)
        revised_data["artifact_status"] = "CURRENT" if final_qc.status == "PASS" else "NEEDS_REVISION"
        if final_qc.status == "PASS":
            revised_data.pop("stale_reason", None)
            revised_data.pop("stale_reasons", None)
        if script_content_hash(revised_data) != script_content_hash(original_script_data):
            effective_req = (
                model_id
                or getattr(revised_script, "requested_model", None)
                or getattr(provider, "requested_model", None)
                or getattr(provider, "default_model", None)
                or original_script_data.get("requested_model")
            )
            actual_m = (
                getattr(revised_script, "actual_model", None)
                or getattr(provider, "last_actual_model", None)
                or getattr(provider, "last_used_model", None)
                or getattr(revised_script, "model_name", None)
                or effective_req
            )
            revised_data["parent_generation_request_id"] = original_script_data.get("generation_request_id")
            revised_data["generation_request_id"] = str(uuid.uuid4())
            revised_data["model_name"] = actual_m
            revised_data["provider_name"] = getattr(provider, "provider_name", None) or getattr(revised_script, "provider_name", None)
            revised_data["requested_model"] = effective_req
            revised_data["actual_model"] = actual_m
            revised_data["prompt_version"] = "script-v3.9-calendar-payoff-location-repair"
            revised_data["generated_at"] = time.time()
        with project_lock(proj_dir):
            assert_context(proj_dir, story_bible.adaptation_context)
            _assert_story_snapshot(story_path, source_story_hash, story_bible.generation_request_id)
            current_script_data = json.loads(script_path.read_text(encoding='utf-8'))
            if script_content_hash(current_script_data) != script_content_hash(original_script_data):
                raise ValueError("Kịch bản đã được chỉnh sửa trong lúc AI sửa; giữ bản hiện tại và chạy lại QC.")
            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(revised_data, f, ensure_ascii=False, indent=2)
            with open(qc_path, "w", encoding="utf-8") as f:
                final_qc_data = asdict(final_qc)
                final_qc_data.update({
                    "generation_source": revised_data.get("generation_source"),
                    "generation_request_id": revised_data.get("generation_request_id"),
                    "source_story_generation_request_id": revised_data.get("source_story_generation_request_id"),
                    "source_story_content_hash": revised_data.get("source_story_content_hash"),
                    "artifact_status": revised_data["artifact_status"],
                })
                if final_qc.status == "PASS":
                    final_qc_data.pop("stale_reason", None)
                    final_qc_data.pop("stale_reasons", None)
                json.dump(final_qc_data, f, ensure_ascii=False, indent=2)

            project_path = proj_dir / "project.json"
            if project_path.exists():
                project_data = json.loads(project_path.read_text(encoding="utf-8"))
                project_data["script_artifact_status"] = revised_data["artifact_status"]
                if final_qc.status == "PASS":
                    project_data.pop("script_stale_reason", None)
                    project_data.pop("script_stale_reasons", None)
                project_data["qc_status"] = final_qc.status
                project_data["updated_at"] = time.time()
                project_path.write_text(json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8")

            total_words = revised_script.total_words or sum(len(s.text.split()) for s in revised_script.segments)
            invalidate_script_approval(project_id, PROJECTS_DIR)
        remaining_rules = sorted({
            str(issue.get("rule") or issue.get("type") or "UNKNOWN_QC")
            for issue in [*final_qc.evidence_issues, *final_qc.fact_conflicts]
            if isinstance(issue, dict)
        })
        completed = final_qc.status == "PASS"
        return {
            "rounds": revised_script.revision_round,
            "rounds_attempted": max(0, revised_script.revision_round - starting_round),
            "qc_status": final_qc.status,
            "completed": completed,
            "remaining_rules": remaining_rules,
            "qc_report": final_qc_data,
            "message": (
                "Kịch bản đã vượt qua QC."
                if completed
                else f"Đã giữ bản ít lỗi nhất sau {max(0, revised_script.revision_round - starting_round)} vòng. Kịch bản chưa đạt: {', '.join(remaining_rules)}. Cần xem các đoạn có chứng cứ lỗi hoặc sửa thiết kế Cốt truyện; không nên bấm Viết lại lặp vô hạn."
            ),
            "word_count": total_words,
            "segments": len(revised_script.segments)
        }
