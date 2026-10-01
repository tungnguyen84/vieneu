"""Anthropic Claude Provider for Script Factory V1.3.1a.

Supports Claude 3.5 Sonnet, Claude 3.7 Sonnet, Claude 3.5 Haiku, and Claude Opus.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, LockedFact, QCReport, ScriptSegment, StoryBible, apply_story_bible_patch, story_bible_repair_targets_clause
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.json_response import parse_json_response
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

logger = logging.getLogger("VieNeu.AnthropicProvider")


def _parse_json_safe(text: str) -> Optional[Any]:
    decoded = parse_json_response(text)
    if decoded is not None:
        return decoded
    clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"^```\s*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    try:
        return json.loads(clean)
    except Exception:
        m_obj = re.search(r"\{.*\}", clean, re.DOTALL)
        if m_obj:
            try:
                return json.loads(m_obj.group(0))
            except Exception:
                pass
        m_arr = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
        if m_arr:
            try:
                return json.loads(m_arr.group(0))
            except Exception:
                pass
    return None


class AnthropicScriptAIProvider(ScriptAIProvider):
    """Anthropic Claude client for ideation, story bible, and scriptwriting."""

    provider_name: str = "anthropic"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "claude-3-5-sonnet-20241022",
        timeout_sec: float = 120.0,
    ):
        self.api_key = (api_key or os.getenv("ANTHROPIC_API_KEY", "")).strip()
        self.default_model = default_model
        self.last_used_model = default_model
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _call_messages(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Tuple[str, int, int]:
        """Calls /v1/messages Anthropic endpoint."""
        chosen_model = (model or self.default_model).strip()
        url = "https://api.anthropic.com/v1/messages"

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "SCC-Studio/1.1",
        }

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            payload["system"] = system_instruction

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))

            content_blocks = resp_data.get("content", [])
            text_out = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
            usage = resp_data.get("usage", {})
            in_tokens = usage.get("input_tokens", len(prompt) // 4)
            out_tokens = usage.get("output_tokens", len(text_out) // 4)
            self.last_used_model = chosen_model
            return text_out, in_tokens, out_tokens
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            clean_err = err_body.replace(self.api_key or "NOKEY", "[REDACTED]") if self.api_key else err_body
            raise RuntimeError(f"Anthropic ({chosen_model}) HTTP {e.code}: {clean_err}")
        except Exception as e:
            raise RuntimeError(f"Anthropic ({chosen_model}) connection error: {e}")

    def generate_ideas(
        self,
        count: int,
        existing_ideas: List[IdeaItem],
        diversity_categories: List[str],
        hook_archetypes: List[str],
        model: Optional[str] = None,
        user_topic: Optional[str] = None,
        topic_intent: Optional[Any] = None,
    ) -> Tuple[List[IdeaItem], int, int]:
        topic_intent_obj: Optional[TopicIntent] = None
        if topic_intent and isinstance(topic_intent, TopicIntent):
            topic_intent_obj = topic_intent
        elif topic_intent and isinstance(topic_intent, dict):
            topic_intent_obj = TopicIntent.from_dict(topic_intent)
        elif user_topic:
            topic_intent_obj = extract_topic_intent(user_topic)

        topic_block = topic_intent_obj.to_prompt_constraint() if topic_intent_obj else ""

        system_msg = (
            "Bạn là Giám đốc Sáng tạo series phim tài liệu tâm lý/kịch tính gia đình Việt Nam 'Sau Cánh Cửa'.\n"
            "Format: MC Minh dẫn chuyện điềm đạm, nhân văn. Trả về đúng định dạng JSON có khóa 'ideas' chứa danh sách ý tưởng."
        )

        user_msg = f"""Hãy sáng tác đúng {count} ý tưởng premise câu chuyện mới toanh cho 'Sau Cánh Cửa'.
{topic_block}

Yêu cầu cấu trúc JSON:
Trả về JSON object có khóa "ideas": [
  {{
    "working_title": "Tiêu đề tiếng Việt",
    "hook": "2-3 câu mở đầu",
    "protagonist": "Tên nhân vật chính",
    "relationship": "Quan hệ trung tâm",
    "central_secret": "Bí mật cốt lõi",
    "mystery_question": "Câu hỏi bí ẩn",
    "false_lead": "Hướng nghi ngờ sai ban đầu",
    "clue_1": "Manh mối 1",
    "clue_2": "Manh mối 2",
    "clue_3": "Manh mối 3",
    "reveal_1": "Bước ngoặt 1",
    "reveal_2": "Bước ngoặt 2",
    "emotional_payoff": "Cao trào cảm xúc",
    "reflection_theme": "Đúc kết triết lý",
    "hook_archetype": "OBJECT_DISCOVERY",
    "twist_archetype": "IDENTITY",
    "curiosity": 8.5,
    "emotional_potential": 9.0,
    "mystery_potential": 8.8,
    "logical_plausibility": 9.2,
    "long_form_potential": 8.7
  }}
]
"""
        content, in_t, out_t = self._call_messages(user_msg, system_instruction=system_msg, model=model)
        parsed = _parse_json_safe(content)
        raw_list = []
        if isinstance(parsed, dict):
            raw_list = parsed.get("ideas", [])
        elif isinstance(parsed, list):
            raw_list = parsed

        chosen_model_name = self.last_used_model or model or self.default_model
        ideas: List[IdeaItem] = []
        for idx, item in enumerate(raw_list[:count]):
            w_title = item.get("working_title") or item.get("title") or f"Ý tưởng #{idx + 1}"
            idea_id = f"IDEA_{idx + 1:03d}"
            idea_obj = IdeaItem(
                idea_id=idea_id,
                working_title=w_title,
                hook=item.get("hook", ""),
                protagonist=item.get("protagonist", "Nhân vật"),
                relationship=item.get("relationship", "Đồng nghiệp / Người thân"),
                central_secret=item.get("central_secret", ""),
                mystery_question=item.get("mystery_question", ""),
                false_lead=item.get("false_lead", ""),
                clue_1=item.get("clue_1", ""),
                clue_2=item.get("clue_2", ""),
                clue_3=item.get("clue_3", ""),
                reveal_1=item.get("reveal_1", ""),
                reveal_2=item.get("reveal_2", ""),
                emotional_payoff=item.get("emotional_payoff", ""),
                reflection_theme=item.get("reflection_theme", ""),
                hook_archetype=item.get("hook_archetype", "OBJECT_DISCOVERY"),
                twist_archetype=item.get("twist_archetype", "IDENTITY"),
                curiosity=float(item.get("curiosity", 8.5)),
                emotional_potential=float(item.get("emotional_potential", 8.8)),
                mystery_potential=float(item.get("mystery_potential", 8.6)),
                logical_plausibility=float(item.get("logical_plausibility", 9.0)),
                long_form_potential=float(item.get("long_form_potential", 8.7)),
                status="AWAITING_USER_REVIEW",
            )
            if topic_intent_obj:
                score = topic_intent_obj.calculate_adherence_score(item)
                idea_obj.topic_adherence_score = score
                idea_obj.original_user_topic = topic_intent_obj.original_topic
                idea_obj.topic_intent = topic_intent_obj.to_dict()
            elif user_topic:
                idea_obj.original_user_topic = user_topic

            idea_obj.generation_request_id = str(uuid.uuid4())
            idea_obj.prompt_version = "ideas-v2.2-topic-truth"
            idea_obj.generation_source = "REAL_AI"
            idea_obj.model_name = chosen_model_name
            idea_obj.provider_name = self.provider_name
            ideas.append(idea_obj)

        return ideas, in_t, out_t

    def create_story_bible(
        self,
        idea: IdeaItem,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
        special_direction: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        # Re-use standard prompt from OpenAICompatibleProvider
        dummy_helper = OpenAICompatibleProvider(provider_name="anthropic", default_model=self.default_model)
        system_instruction = (
            "Bạn là Trưởng ban Biên kịch của series phim tài liệu tâm lý/xã hội gia đình Việt Nam 'Sau Cánh Cửa'.\n"
            "Format: Một người kể chuyện duy nhất (Minh - giọng điềm đạm, nhân văn, khách quan, giàu chiều sâu).\n"
            + (f"\nCHỦ ĐỀ BẮT BUỘC: '{idea.original_user_topic}'. Story Bible PHẢI bám sát đề tài này.\n" if idea.original_user_topic else "")
            + "Mục tiêu: Mở rộng ý tưởng premise thành một Story Bible hoàn chỉnh dạng JSON hợp lệ."
        )
        ep_id = f"EP{idea.idea_id.replace('IDEA_', '')}" if "IDEA_" in idea.idea_id else "EP002"
        prompt = f"""Hãy xây dựng Story Bible chi tiết cho tập {ep_id}:
Ý tưởng: {idea.working_title} - {idea.hook}
Nhân vật chính: {idea.protagonist}
Bí mật: {idea.central_secret}
Manh mối: 1. {idea.clue_1}, 2. {idea.clue_2}, 3. {idea.clue_3}
Reveal 1: {idea.reveal_1}
Reveal 2: {idea.reveal_2}

Trả về JSON Object theo cấu trúc chuẩn có keys: episode_id, title, protagonist, supporting_characters, relationships, timeline, locations, central_secret, mystery_question, false_lead, clues, reveal_1, reveal_2, emotional_payoff, reflection_theme, ending, critical_facts, narrative_skeleton, causal_chains, knowledge_ledger, structured_clues, reveal_justifications."""

        raw_text, in_tok, out_tok = self._call_messages(prompt, system_instruction=system_instruction, model=model)
        parsed = _parse_json_safe(raw_text)
        if not parsed or not isinstance(parsed, dict):
            raise RuntimeError(f"Could not parse Anthropic Story Bible response for {idea.idea_id}.")

        critical_facts: List[LockedFact] = []
        for f_data in parsed.get("critical_facts", []):
            critical_facts.append(LockedFact(
                fact_id=f_data.get("fact_id", f"FACT_{len(critical_facts)+1:03d}"),
                field=f_data.get("field", "fact"),
                value=str(f_data.get("value", "")),
                description=f_data.get("description", ""),
                status="LOCKED",
            ))

        bible = StoryBible(
            episode_id=ep_id,
            title=str(parsed.get("title", idea.working_title)),
            protagonist=parsed.get("protagonist", {"name": idea.protagonist, "age": 30}),
            supporting_characters=parsed.get("supporting_characters", []),
            relationships=parsed.get("relationships", []),
            timeline=parsed.get("timeline", []),
            locations=parsed.get("locations", ["PHÒNG KHÁCH", "QUÊ NHÀ"]),
            money_facts=parsed.get("money_facts", []),
            critical_facts=critical_facts,
            secret=parsed.get("central_secret", idea.central_secret),
            false_lead=parsed.get("false_lead", idea.false_lead),
            clues=parsed.get("clues", [idea.clue_1, idea.clue_2, idea.clue_3]),
            reveal_1=parsed.get("reveal_1", idea.reveal_1),
            reveal_2=parsed.get("reveal_2", idea.reveal_2),
            emotional_payoff=parsed.get("emotional_payoff", idea.emotional_payoff),
            reflection_theme=parsed.get("reflection_theme", idea.reflection_theme),
            ending=parsed.get("ending", "Câu chuyện khép lại với sự thấu hiểu sâu sắc."),
            source_idea_id=idea.idea_id,
            time_period=parsed.get("time_period", "Hiện tại"),
            mystery_question=parsed.get("mystery_question", idea.mystery_question),
            narrative_skeleton=parsed.get("narrative_skeleton", {}),
            causal_chains=parsed.get("causal_chains", []),
            knowledge_ledger=parsed.get("knowledge_ledger", []),
            structured_clues=parsed.get("structured_clues", []),
            reveal_justifications=parsed.get("reveal_justifications", {}),
            original_user_topic=idea.original_user_topic,
            topic_intent=idea.topic_intent,
            topic_adherence=idea.topic_adherence_score or 100.0,
            status="DRAFT",
            generation_request_id=str(uuid.uuid4()),
            prompt_version="story-v3.2-grounded-proof",
            generation_source="REAL_AI",
            model_name=self.last_used_model or model or self.default_model,
            provider_name=self.provider_name,
            generated_at=time.time(),
        )
        return bible, in_tok, out_tok

    def repair_story_bible(
        self,
        story_bible: StoryBible,
        issues: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        issues_summary = "\n".join(
            f"- [{it.get('rule', 'LOGIC')}] {it.get('message', '')}"
            for it in issues if isinstance(it, dict)
        )
        system_instruction = "Bạn là Trưởng ban Biên kịch của 'Sau Cánh Cửa'. Hãy sửa chữa Story Bible theo danh sách lỗi QC và trả về JSON hợp lệ."
        prompt = f"""STORY BIBLE HIỆN TẠI:\n{json.dumps(story_bible.to_dict(), ensure_ascii=False)}\n\nLỖI QC CẦN SỬA:\n{issues_summary}\n\nHãy sửa chữa và chỉ trả về JSON object gồm các trường đã sửa hoặc bổ sung."""
        prompt += story_bible_repair_targets_clause(issues)
        raw_text, in_tok, out_tok = self._call_messages(prompt, system_instruction=system_instruction, model=model)
        parsed = _parse_json_safe(raw_text)
        if parsed and isinstance(parsed, dict):
            apply_story_bible_patch(story_bible, parsed)
        else:
            logger.warning(f"Story Bible repair response was not JSON; nothing applied: {raw_text[:160]!r}")
            raise ValueError('Story Bible repair returned invalid JSON; original draft was retained')

        story_bible.generation_request_id = str(uuid.uuid4())
        story_bible.generation_source = "REAL_AI"
        story_bible.model_name = self.last_used_model or model or self.default_model
        story_bible.provider_name = self.provider_name
        return story_bible, in_tok, out_tok

    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
        helper = OpenAICompatibleProvider(provider_name="anthropic", default_model=self.default_model)
        # We can leverage OpenAICompatibleProvider prompt formatting
        host_id = series_bible.get("host", {}).get("id", "MINH")
        host_name = series_bible.get("host", {}).get("display_name", "Minh")

        system_instruction = (
            f"Bạn là Người dẫn chuyện MC {host_name} ({host_id}) của series 'Sau Cánh Cửa'.\n"
            f"Hãy viết toàn bộ kịch bản tự nhiên, không ngắt tập, không mã nội bộ, chia phân đoạn JSON chuẩn."
        )

        prompt = f"""Hãy viết kịch bản hoàn chỉnh cho tập phim: '{story_bible.title}'.
STORY BIBLE ĐẦY ĐỦ (nguồn chuẩn cho danh tính, thời gian, nguồn bằng chứng và kết thúc):
{json.dumps(story_bible.to_dict(), ensure_ascii=False)}
Bí mật: {story_bible.secret}
Reveal 1: {story_bible.reveal_1}
Reveal 2: {story_bible.reveal_2}

Trả về JSON Object có khóa "segments": [
  {{"id": "001", "speaker": "{host_id}", "text": "...", "delivery_profile": "HOOK", "importance": "high", "audience_address": false, "speed": 0.98}}
]"""
        raw_text, in_tok, out_tok = self._call_messages(prompt, system_instruction=system_instruction, model=model)
        parsed = _parse_json_safe(raw_text)
        raw_segs = parsed.get("segments", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])

        segments: List[ScriptSegment] = []
        for idx, item in enumerate(raw_segs):
            seg_id = f"{idx + 1:03d}"
            prof = item.get("delivery_profile", "NORMAL")
            segments.append(ScriptSegment(
                id=seg_id,
                speaker=host_id,
                text=item.get("text", "").strip(),
                delivery_profile=prof,
                importance=item.get("importance", "normal"),
                audience_address=bool(item.get("audience_address", False)),
                speed=float(item.get("speed", 1.0)),
            ))

        total_words = sum(len(s.text.split()) for s in segments)
        script = FullScript(
            episode_id=story_bible.episode_id,
            title=story_bible.title,
            host={"id": host_id, "name": host_name, "voice": "Binh"},
            segments=segments,
            total_segments=len(segments),
            total_words=total_words,
            status="DRAFT",
            generation_request_id=str(uuid.uuid4()),
            prompt_version="script-v3.5-complete-story-context",
            generation_source="REAL_AI",
            model_name=self.last_used_model or model or self.default_model,
            provider_name=self.provider_name,
            created_at=time.time(),
            updated_at=time.time(),
        )
        return script, in_tok, out_tok

    def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        return []

    def review_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[QCReport, int, int]:
        from apps.script_factory.script_qc import ScriptQCEngine
        return ScriptQCEngine.audit_script(script, story_bible, story_formula, series_bible), 100, 100

    def complete_json(self, system_instruction: str, prompt: str, model: Optional[str] = None) -> Tuple[str, int, int]:
        """Single JSON completion used by QC review and segment rewriting."""
        return self._call_messages(
            prompt=prompt, system_instruction=system_instruction, model=model, temperature=0.3,
        )

    def revise_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.segment_rewriter import revise_with_ai

        return revise_with_ai(
            script, story_bible, qc_report,
            lambda system, prompt: self.complete_json(system, prompt, model=model),
        )
