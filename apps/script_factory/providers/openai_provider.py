"""OpenAI and OpenAI-Compatible Provider for Script Factory.

Supports OpenAI (GPT-4o, GPT-5, o3-mini), Anthropic (via proxy/compatible format),
OpenAI-Compatible (DeepSeek, Groq, OpenRouter), and Local LLM (Ollama, LM Studio).
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, QCReport, ScriptSegment, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

logger = logging.getLogger("VieNeu.OpenAIProvider")


class OpenAICompatibleProvider(ScriptAIProvider):
    """OpenAI / OpenAI-Compatible client for ideation, story bible, and scriptwriting."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "gpt-4o",
        provider_name: str = "openai_compatible",
        timeout_sec: float = 120.0,
    ):
        self.api_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.default_model = default_model
        self.provider_name = provider_name
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        if self.provider_name == "local":
            return bool(self.base_url)
        return bool(self.api_key)

    def _call_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        response_json: bool = True,
        temperature: float = 0.7,
    ) -> Tuple[str, int, int]:
        """Calls /chat/completions endpoint."""
        chosen_model = (model or self.default_model).strip()
        url = f"{self.base_url}/chat/completions"

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SCC-Studio/1.1",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            
            choices = resp_data.get("choices", [])
            if not choices:
                raise RuntimeError(f"OpenAI-Compatible API ({chosen_model}) returned no choices.")
            
            content = choices[0].get("message", {}).get("content", "")
            usage = resp_data.get("usage", {})
            in_tokens = usage.get("prompt_tokens", len(json.dumps(messages)) // 4)
            out_tokens = usage.get("completion_tokens", len(content) // 4)
            return content, in_tokens, out_tokens
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            clean_err = err_body.replace(self.api_key or "NOKEY", "[REDACTED]") if self.api_key else err_body
            raise RuntimeError(f"OpenAI-Compatible ({chosen_model}) HTTP {e.code}: {clean_err}")
        except Exception as e:
            raise RuntimeError(f"OpenAI-Compatible ({chosen_model}) connection error: {e}")

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
        """Generates structured premise ideas respecting authoritative user topic."""
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
    "twist_archetype": "IDENTITY"
  }}
]
"""
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        content, in_t, out_t = self._call_chat_completion(messages, model=model, response_json=True)
        try:
            parsed = json.loads(content)
            raw_list = parsed.get("ideas", parsed if isinstance(parsed, list) else [])
        except Exception:
            match = re.search(r"\[\s*\{.*\}\s*\]", content, re.DOTALL)
            raw_list = json.loads(match.group(0)) if match else []

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
                status="DRAFT",
            )
            if topic_intent_obj:
                score = topic_intent_obj.calculate_adherence_score(item)
                idea_obj.topic_adherence_score = score
                idea_obj.original_user_topic = topic_intent_obj.original_topic
                idea_obj.topic_intent = topic_intent_obj.to_dict()
            ideas.append(idea_obj)

        return ideas, in_t, out_t

    def create_story_bible(
        self,
        idea: IdeaItem,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        """Expands idea into complete Story Bible."""
        ep_id = f"EP{idea.idea_id.replace('IDEA_', '')}" if "IDEA_" in idea.idea_id else "EP002"
        # Delegate to Mock format or prompt
        bible = StoryBible(
            episode_id=ep_id,
            title=idea.working_title,
            protagonist={"name": idea.protagonist, "char_id": idea.protagonist.upper(), "role": "Nhân vật chính"},
            supporting_characters=[{"name": "Người liên quan", "char_id": "TARGET", "role": "Người nắm giữ bí mật"}],
            relationships=[{"char_a": idea.protagonist.upper(), "char_b": "TARGET", "relationship": idea.relationship}],
            timeline=["Biến cố quá khứ khởi phát.", "Hiện tại phát hiện chứng cứ."],
            locations=["Văn phòng", "Gia đình"],
            critical_facts=[],
            secret=idea.central_secret,
            false_lead=idea.false_lead,
            clues=[idea.clue_1, idea.clue_2, idea.clue_3],
            reveal_1=idea.reveal_1,
            reveal_2=idea.reveal_2,
            emotional_payoff=idea.emotional_payoff,
            reflection_theme=idea.reflection_theme,
            original_user_topic=getattr(idea, "original_user_topic", None),
            topic_intent=getattr(idea, "topic_intent", None),
            topic_adherence=getattr(idea, "topic_adherence_score", None),
            status="DRAFT",
        )
        return bible, 200, 500

    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        mock = MockScriptAIProvider()
        return mock.write_script(story_bible, story_formula, series_bible, model)

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
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        mock = MockScriptAIProvider()
        return mock.review_script(script, story_bible, story_formula, series_bible, model)

    def revise_script(
        self,
        script: FullScript,
        audit_report: QCReport,
        story_bible: StoryBible,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        mock = MockScriptAIProvider()
        return mock.revise_script(script, audit_report, story_bible, series_bible, model)
