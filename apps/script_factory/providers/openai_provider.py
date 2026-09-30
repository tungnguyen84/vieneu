"""OpenAI and OpenAI-Compatible Provider for Script Factory V1.3.1a.

Supports OpenAI (GPT-4o, GPT-5, o3-mini), Anthropic (via proxy/compatible format),
OpenAI-Compatible (DeepSeek, Groq, OpenRouter), and Local LLM (Ollama, LM Studio, vLLM).
"""
from __future__ import annotations

import collections
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, LockedFact, QCReport, ScriptSegment, StoryBible
from apps.script_factory.narrative_continuity import has_repeated_narrative_block
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

logger = logging.getLogger("VieNeu.OpenAIProvider")


def _parse_json_safe(text: str) -> Optional[Any]:
    """Robust JSON parser that strips markdown code fences and cleans trailing commas."""
    clean = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"^```\s*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r",\s*([\]}])", r"\1", clean)
    try:
        return json.loads(clean)
    except Exception:
        # Match outermost object
        m_obj = re.search(r"\{.*\}", clean, re.DOTALL)
        if m_obj:
            try:
                return json.loads(m_obj.group(0))
            except Exception:
                pass
        # Match outermost array
        m_arr = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
        if m_arr:
            try:
                return json.loads(m_arr.group(0))
            except Exception:
                pass
    return None


_SCRIPT_SIGNOFF_RE = re.compile(
    r"(?:cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|"
    r"xin\s+chào\s+và\s+hẹn\s+gặp\s+lại|"
    r"tôi\s+là\s+minh[^.]{0,80}hẹn\s+gặp\s+lại)",
    re.IGNORECASE,
)
_MIN_SCRIPT_PART_SEGMENTS = 30
_MIN_COMPLETE_SCRIPT_SEGMENTS = 70


def _extract_script_segments(raw_text: str) -> List[Dict[str, Any]]:
    parsed = _parse_json_safe(raw_text)
    if isinstance(parsed, dict):
        parsed = parsed.get("segments", [])
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _part_has_closure(segments: List[Dict[str, Any]]) -> bool:
    return any(
        str(segment.get("delivery_profile", "")).upper() == "ENDING"
        or bool(_SCRIPT_SIGNOFF_RE.search(str(segment.get("text", ""))))
        for segment in segments
    )


def _part_has_premature_reveal(segments: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(segment, dict)
        and str(segment.get("delivery_profile", "")).upper() == "REVEAL"
        for segment in segments
    )


def _normalize_final_closure(segments: List[Dict[str, Any]]) -> None:
    """Correct harmless profile mistakes without hiding an actual early sign-off."""
    if not segments:
        return
    for segment in segments[:-1]:
        if (
            str(segment.get("delivery_profile", "")).upper() == "ENDING"
            and not _SCRIPT_SIGNOFF_RE.search(str(segment.get("text", "")))
        ):
            segment["delivery_profile"] = "COMMENT"
    if _SCRIPT_SIGNOFF_RE.search(str(segments[-1].get("text", ""))):
        segments[-1]["delivery_profile"] = "ENDING"


def _has_valid_final_closure(segments: List[Dict[str, Any]]) -> bool:
    if not segments:
        return False
    final_index = len(segments) - 1
    signoff_indices = [
        index for index, segment in enumerate(segments)
        if _SCRIPT_SIGNOFF_RE.search(str(segment.get("text", "")))
    ]
    ending_indices = [
        index for index, segment in enumerate(segments)
        if str(segment.get("delivery_profile", "")).upper() == "ENDING"
    ]
    return signoff_indices == [final_index] and ending_indices == [final_index]


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
        self.last_used_model = default_model
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
        """Calls /chat/completions endpoint with resilient fallback if response_format is unsupported."""
        chosen_model = (model or self.default_model).strip()
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SCC-Studio/1.1",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        def _do_post(include_json_format: bool) -> Tuple[str, int, int]:
            payload: Dict[str, Any] = {
                "model": chosen_model,
                "messages": messages,
                "temperature": temperature,
            }
            if include_json_format:
                payload["response_format"] = {"type": "json_object"}
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))

            choices = resp_data.get("choices", [])
            if not choices:
                raise RuntimeError(f"OpenAI-Compatible API ({chosen_model}) returned no choices.")

            content = choices[0].get("message", {}).get("content", "")
            usage = resp_data.get("usage", {})
            in_tokens = usage.get("prompt_tokens", len(json.dumps(messages)) // 4)
            out_tokens = usage.get("completion_tokens", len(content) // 4)
            self.last_used_model = chosen_model
            return content, in_tokens, out_tokens

        try:
            return _do_post(include_json_format=response_json)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            # If 400 or 422, response_format might not be supported by this proxy/local endpoint
            if response_json and (e.code in (400, 422) or "response_format" in err_body.lower()):
                logger.warning(
                    f"OpenAI-Compatible endpoint failed with response_format, retrying without response_format... (HTTP {e.code})"
                )
                try:
                    return _do_post(include_json_format=False)
                except Exception as inner_e:
                    clean_err = str(inner_e).replace(self.api_key or "NOKEY", "[REDACTED]") if self.api_key else str(inner_e)
                    raise RuntimeError(f"OpenAI-Compatible ({chosen_model}) HTTP {e.code}: {clean_err}")

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
    "twist_archetype": "IDENTITY",
    "curiosity": 8.5,
    "emotional_potential": 9.0,
    "mystery_potential": 8.8,
    "logical_plausibility": 9.2,
    "long_form_potential": 8.7
  }}
]
"""
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        content, in_t, out_t = self._call_chat_completion(messages, model=model, response_json=True)
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
            idea_obj.prompt_version = "ideas-v2.1"
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
        """Expands idea into complete Story Bible using OpenAI-compatible LLM."""
        ep_id = f"EP{idea.idea_id.replace('IDEA_', '')}" if "IDEA_" in idea.idea_id else "EP002"

        topic_instruction = ""
        topic_clause = ""
        if idea.original_user_topic:
            topic_instruction = f"\nCHỦ ĐỀ BẮT BUỘC: '{idea.original_user_topic}'. Story Bible PHẢI bám sát đề tài này, không được thay thế bằng đề tài gia đình chung chung.\n"
            topic_clause = f"- Chủ đề bắt buộc: {idea.original_user_topic}\n"

        system_instruction = (
            "Bạn là Trưởng ban Biên kịch của series phim tài liệu tâm lý/xã hội gia đình Việt Nam 'Sau Cánh Cửa'.\n"
            "Format: Một người kể chuyện duy nhất (Minh - giọng điềm đạm, nhân văn, khách quan, giàu chiều sâu).\n"
            + topic_instruction +
            "Mục tiêu: Mở rộng ý tưởng premise thành một Story Bible hoàn chỉnh, chặt chẽ, đầy đủ chi tiết nhân vật, bối cảnh, "
            "manh mối và Fact Lock (đóng băng sự thật).\n"
            "Yêu cầu bắt buộc:\n"
            "1. Tuyệt đối phù hợp thực tế xã hội, pháp lý, y tế, tài chính và công nghệ tại Việt Nam.\n"
            "2. Nhân vật đa chiều, không hoàn hảo, không có nạn nhân hoàn hảo hay kẻ ác một chiều. Mỗi người đều có nỗi sợ, sự bế tắc hoặc lý do im lặng.\n"
            "3. Logic chặt chẽ: Bước ngoặt 1 (Reveal 1) cần ít nhất 2 manh mối cụ thể hỗ trợ; Bước ngoặt 2 (Reveal 2) phải được gieo mầm manh mối từ trước.\n"
            "4. Thiết lập danh sách Fact Lock (critical_facts) đóng băng chính xác: tuổi tác, mối quan hệ, các năm/mốc thời gian, số tiền/tài sản, địa điểm, người nắm bí mật.\n"
            "5. Tên Minh và mã MINH chỉ dành riêng cho MC, tuyệt đối không đặt cho nhân vật trong Story Bible.\n"
            "6. Với cáo buộc nghiêm trọng, tin nhắn/lịch sử cuộc gọi/lời đồn/lời thú nhận đơn độc chỉ là dấu hiệu; reveal phải có ít nhất một chi tiết độc lập có thể kiểm chứng.\n"
            "7. Bối cảnh hôn nhân có thể giải thích hoàn cảnh nhưng không được đổ trách nhiệm lựa chọn nói dối/ngoại tình lên người bị phản bội.\n"
            "8. Xuất ra định dạng JSON hợp lệ."
        )

        direction_clause = f"\nCHỈ ĐẠO ĐẶC BIỆT CHO TẬP PHIM NÀY:\n{special_direction}\n" if special_direction else ""

        prompt = f"""Hãy xây dựng Story Bible chi tiết cho tập phim có mã {ep_id} dựa trên ý tưởng sau:

Ý tưởng gốc:
- Mã ý tưởng: {idea.idea_id}
- Tiêu đề dự kiến: {idea.working_title}
{topic_clause}- Hook: {idea.hook}
- Nhân vật chính: {idea.protagonist}
- Quan hệ trung tâm: {idea.relationship}
- Bí mật cốt lõi: {idea.central_secret}
- Câu hỏi bí ẩn: {idea.mystery_question}
- Giả thuyết sai ban đầu (False Lead): {idea.false_lead}
- Manh mối 1: {idea.clue_1}
- Manh mối 2: {idea.clue_2}
- Manh mối 3: {idea.clue_3}
- Bước ngoặt 1 (Reveal 1): {idea.reveal_1}
- Bước ngoặt 2 (Reveal 2): {idea.reveal_2}
- Cao trào cảm xúc: {idea.emotional_payoff}
- Chủ đề đúc kết: {idea.reflection_theme}
{direction_clause}

Yêu cầu cấu trúc JSON trả về (chính xác định dạng sau):
{{
  "episode_id": "{ep_id}",
  "source_idea_id": "{idea.idea_id}",
  "title": "{idea.working_title}",
  "protagonist": {{
    "name": "{idea.protagonist}",
    "char_id": "{idea.protagonist.upper()}",
    "age": 32,
    "role": "Nhân vật chính",
    "description": "Mô tả ngoại hình, tính cách, công việc và bối cảnh sống",
    "want": "Mục tiêu trực tiếp",
    "fear": "Nỗi sợ sâu kín",
    "misbelief": "Định kiến hoặc suy nghĩ sai lầm ban đầu"
  }},
  "supporting_characters": [
    {{
      "name": "Tên nhân vật phụ",
      "char_id": "CHAR_ID",
      "role": "Người nắm giữ bí mật / Người thân",
      "age": 55,
      "description": "Mô tả tính cách và hoàn cảnh",
      "want": "Mong muốn cá nhân",
      "fear": "Nỗi sợ",
      "reason_for_silence": "Lý do vì sao phải giữ im lặng hoặc che giấu"
    }}
  ],
  "relationships": [
    {{
      "char_a": "{idea.protagonist.upper()}",
      "char_b": "CHAR_ID",
      "relationship": "{idea.relationship}"
    }}
  ],
  "time_period": "Bối cảnh thời gian cụ thể (ví dụ: Hiện tại 2024, các mốc quá khứ 1995-2015)",
  "locations": ["PHÒNG KHÁCH", "VĂN PHÒNG", "QUÊ NHÀ"],
  "central_secret": "{idea.central_secret}",
  "mystery_question": "{idea.mystery_question}",
  "false_lead": "{idea.false_lead}",
  "timeline": [
    "Mốc thời gian 1: Sự kiện quá khứ khởi đầu",
    "Mốc thời gian 2: Biến cố tiếp theo",
    "Mốc thời gian 3: Thời điểm hiện tại khi phát hiện manh mối"
  ],
  "clues": [
    "Manh mối 1 cụ thể (vật thể, giấy tờ, cuộc gọi)",
    "Manh mối 2 cụ thể đào sâu hơn",
    "Manh mối 3 cụ thể đảo chiều điều tra"
  ],
  "reveal_1": "{idea.reveal_1}",
  "reveal_2": "{idea.reveal_2}",
  "emotional_payoff": "{idea.emotional_payoff}",
  "reflection_theme": "{idea.reflection_theme}",
  "ending": "Cách câu chuyện kết thúc (sự thấu hiểu, trách nhiệm, hàn gắn hoặc chấp nhận ranh giới)",
  "critical_facts": [
    {{
      "fact_id": "FACT_001",
      "field": "timeline_years",
      "value": "10 năm",
      "description": "Khoảng thời gian bí mật kéo dài",
      "status": "LOCKED"
    }},
    {{
      "fact_id": "FACT_002",
      "field": "relationship_nature",
      "value": "{idea.relationship}",
      "description": "Mối quan hệ chính xác giữa các nhân vật",
      "status": "LOCKED"
    }},
    {{
      "fact_id": "FACT_003",
      "field": "evidence_origin",
      "value": "Mô tả nguồn gốc vật chứng/giấy tờ",
      "description": "Nguồn gốc xác thực của vật chứng",
      "status": "LOCKED"
    }},
    {{
      "fact_id": "FACT_004",
      "field": "reveal_1_truth",
      "value": "{idea.reveal_1[:80]}",
      "description": "Nội dung cốt lõi của Bước ngoặt 1",
      "status": "LOCKED"
    }},
    {{
      "fact_id": "FACT_005",
      "field": "reveal_2_truth",
      "value": "{idea.reveal_2[:80]}",
      "description": "Nội dung gốc rễ của Bước ngoặt 2",
      "status": "LOCKED"
    }}
  ],
  "narrative_skeleton": {{
    "trigger": "Tình huống kích hoạt mở đầu",
    "initial_suspicion": "Sự nghi ngờ ban đầu",
    "investigation_method": "Phương pháp tiếp cận và xác minh",
    "evidence_chain": ["Manh mối 1", "Manh mối 2", "Manh mối 3"],
    "reveal_mechanism": "Cơ chế đưa Bước ngoặt 1 ra ánh sáng",
    "second_reveal_mechanism": "Cơ chế hé lộ Bước ngoặt 2",
    "emotional_resolution": "Cách hóa giải cảm xúc cuối cùng"
  }},
  "causal_chains": [
    {{
      "target": "reveal_1",
      "cause": "Nguyên nhân thực tế khởi phát biến cố",
      "decision": "Quyết định cụ thể của nhân vật tại thời điểm đó",
      "action": "Hành động thực hiện",
      "consequence": "Hệ quả kéo dài đến hiện tại",
      "why": "Lý do bắt buộc phải hành động như vậy",
      "motivation": "Tại sao giải pháp thông thường/đơn giản hơn là bất khả thi trong hoàn cảnh đó",
      "how": "Cơ chế thực tế để duy trì việc này suốt khoảng thời gian đã nêu"
    }},
    {{
      "target": "reveal_2",
      "cause": "Nguyên nhân gốc rễ sâu xa của Bước ngoặt 2",
      "decision": "Quyết định giữ im lặng hoặc hy sinh",
      "action": "Hành động cụ thể",
      "consequence": "Ai bị ảnh hưởng và vì sao họ giữ im lặng",
      "why": "Động lực nhân văn sâu nhất",
      "motivation": "Tại sao không thể nói thật hoặc giải quyết bằng cách bình thường",
      "how": "Cách thức thực hiện nhất quán trong đời thực"
    }}
  ],
  "knowledge_ledger": [
    {{
      "character": "{idea.protagonist}",
      "who_knows_what": "Ban đầu hoàn toàn chưa biết bí mật, chỉ phát hiện dấu hiệu bất thường",
      "when_they_learned_it": "Chỉ biết sự thật ở Hồi 6 - Hồi 7 khi mở hồ sơ/nghe nhân chứng",
      "how_they_learned_it": "Qua chuỗi 3 manh mối và cuộc đối thoại trực tiếp",
      "knowledge_scope": "none"
    }},
    {{
      "character": "Tên nhân vật phụ nắm bí mật",
      "who_knows_what": "Nắm rõ toàn bộ nguyên nhân và quá trình che giấu",
      "when_they_learned_it": "Từ thời điểm biến cố xảy ra trong quá khứ",
      "how_they_learned_it": "Trực tiếp trải qua và thực hiện thỏa thuận",
      "knowledge_scope": "full"
    }}
  ],
  "structured_clues": [
    {{
      "clue": "Manh mối 1 cụ thể",
      "what_it_proves": "Điều thực tế mà manh mối 1 chứng minh được ngay lúc đó",
      "what_it_does_NOT_prove": "Điều manh mối 1 CHƯA đủ căn cứ để kết luận (tránh nhảy cóc)",
      "next_question": "Câu hỏi điều tra tiếp theo nảy sinh từ manh mối 1"
    }},
    {{
      "clue": "Manh mối 2 cụ thể",
      "what_it_proves": "Điều manh mối 2 chứng minh sâu hơn về mốc thời gian/con người",
      "what_it_does_NOT_prove": "Điều vẫn còn thiếu cần manh mối 3 làm rõ",
      "next_question": "Câu hỏi dẫn tới cuộc xác minh cuối cùng"
    }},
    {{
      "clue": "Manh mối 3 cụ thể",
      "what_it_proves": "Chứng cứ đầy đủ xác nhận Bước ngoặt 1 và bác bỏ giả thuyết sai",
      "what_it_does_NOT_prove": "Không phải sự phản bội như nghi ngờ ban đầu",
      "next_question": "Tại sao người trong cuộc phải âm thầm chịu đựng suốt ngần ấy năm?"
    }}
  ],
  "reveal_justifications": {{
    "reveal_1": {{
      "evidence_support": "Manh mối 1, 2, 3 kết hợp chứng minh Bước ngoặt 1 như thế nào",
      "motivation_support": "Động cơ tâm lý và hoàn cảnh thực tế hỗ trợ Bước ngoặt 1",
      "timeline_support": "Sự khớp nối chính xác với các mốc năm/thời gian trong timeline"
    }},
    "reveal_2": {{
      "evidence_support": "Vật chứng/lời kể nhân chứng chứng minh Bước ngoặt 2",
      "motivation_support": "Lý do bất khả kháng khiến nhân vật không thể chọn cách đơn giản hơn",
      "character_knowledge_support": "Sự nhất quán với knowledge_ledger (ai biết, ai không biết)"
    }}
  }}
}}
"""
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        raw_text, in_tok, out_tok = self._call_chat_completion(messages, model=model, response_json=True)
        parsed = _parse_json_safe(raw_text)

        if not parsed:
            logger.warning(f"Retrying Story Bible generation for {idea.idea_id} due to JSON parsing issue...")
            time.sleep(1)
            retry_messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt + "\nLƯU Ý: Chỉ xuất ra đúng một JSON object hợp lệ, không có văn bản giải thích ngoài JSON."},
            ]
            raw_text, in_tok2, out_tok2 = self._call_chat_completion(retry_messages, model=model, response_json=True)
            in_tok += in_tok2
            out_tok += out_tok2
            parsed = _parse_json_safe(raw_text)
            if not parsed:
                raise RuntimeError(f"Could not parse OpenAI-Compatible Story Bible response for {idea.idea_id}.")

        critical_facts: List[LockedFact] = []
        for f_data in parsed.get("critical_facts", []):
            critical_facts.append(LockedFact(
                fact_id=f_data.get("fact_id", f"FACT_{len(critical_facts)+1:03d}"),
                field=f_data.get("field", "fact"),
                value=str(f_data.get("value", "")),
                description=f_data.get("description", ""),
                status="LOCKED",
            ))

        clean_title = re.sub(r"^(?:Tập\s+)?EP_?[A-Z0-9_]*\d+\s*[-:]?\s*", "", str(parsed.get("title", idea.working_title)), flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = idea.working_title

        orig_topic = idea.original_user_topic or (idea.topic_intent.get("original_topic") if idea.topic_intent else None)
        adherence_val = idea.topic_adherence_score if idea.topic_adherence_score is not None else 100.0
        chosen_model_name = self.last_used_model or model or self.default_model

        bible = StoryBible(
            episode_id=ep_id,
            title=clean_title,
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
            original_user_topic=orig_topic,
            topic_intent=idea.topic_intent,
            topic_adherence=adherence_val,
            status="DRAFT",
            generation_request_id=str(uuid.uuid4()),
            prompt_version="story-v3.0",
            generation_source="REAL_AI",
            model_name=chosen_model_name,
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
        """Repairs Story Bible QC issues without template injection using OpenAI-compatible LLM."""
        issues_summary = "\n".join(
            f"- [{it.get('rule', 'LOGIC')}] {it.get('message', '')} (Target: {it.get('target', 'general')})"
            for it in issues if isinstance(it, dict)
        )
        if not issues_summary:
            issues_summary = "Cần bổ sung và chuẩn hóa cấu trúc: causal_chains, knowledge_ledger, structured_clues, reveal_justifications."

        orig_topic_clause = f"\nCHỦ ĐỀ BẮT BUỘC: '{story_bible.original_user_topic}'. Tuyệt đối KHÔNG thay đổi đề tài gốc!\n" if story_bible.original_user_topic else ""

        system_instruction = (
            "Bạn là Trưởng ban Biên kịch của series 'Sau Cánh Cửa'. Nhiệm vụ của bạn là sửa chữa các lỗi logic, thiếu sót nhân quả "
            "hoặc mâu thuẫn nhận thức trong Story Bible hiện tại mà KHÔNG làm thay đổi cốt truyện hay danh tính nhân vật đã có.\n"
            + orig_topic_clause +
            "Yêu cầu:\n"
            "1. Tuyệt đối KHÔNG đưa vào các khuôn mẫu template hay tên nhân vật ngoài kịch bản.\n"
            "2. Khắc phục triệt để các vấn đề QC được chỉ rõ.\n"
            "3. Trả về toàn bộ Story Bible đã sửa đổi dưới dạng JSON hợp lệ."
        )

        prompt = f"""Dưới đây là Story Bible hiện tại và danh sách các lỗi QC cần khắc phục:

STORY BIBLE HIỆN TẠI:
{json.dumps(story_bible.to_dict(), ensure_ascii=False, indent=2)}

DANH SÁCH LỖI QC CẦN SỬA:
{issues_summary}

Hãy sửa đổi và hoàn thiện Story Bible, đảm bảo bổ sung đầy đủ và chặt chẽ:
1. causal_chains (nguyên nhân, quyết định, hành động, hệ quả, lý do giải pháp thông thường bất khả thi)
2. knowledge_ledger (ai biết gì, khi nào biết, biết bằng cách nào, scope)
3. structured_clues (clue, what_it_proves, what_it_does_NOT_prove, next_question)
4. reveal_justifications (reveal_1 và reveal_2 có evidence_support, motivation_support, v.v.)
5. critical_facts (các sự thật cốt lõi đóng băng)

Xuất ra toàn bộ Story Bible dưới dạng một JSON Object duy nhất, đúng định dạng schema chuẩn."""

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        raw_text, in_tok, out_tok = self._call_chat_completion(messages, model=model, response_json=True)
        parsed = _parse_json_safe(raw_text)

        if parsed and isinstance(parsed, dict):
            if parsed.get("causal_chains"):
                story_bible.causal_chains = parsed.get("causal_chains")
            if parsed.get("knowledge_ledger"):
                story_bible.knowledge_ledger = parsed.get("knowledge_ledger")
            if parsed.get("structured_clues"):
                story_bible.structured_clues = parsed.get("structured_clues")
            if parsed.get("reveal_justifications"):
                story_bible.reveal_justifications = parsed.get("reveal_justifications")
            if parsed.get("critical_facts"):
                new_cf = []
                for f_data in parsed.get("critical_facts", []):
                    new_cf.append(LockedFact(
                        fact_id=f_data.get("fact_id", f"FACT_{len(new_cf)+1:03d}"),
                        field=f_data.get("field", "fact"),
                        value=str(f_data.get("value", "")),
                        description=f_data.get("description", ""),
                        status="LOCKED",
                    ))
                story_bible.critical_facts = new_cf
            if parsed.get("reveal_1"):
                story_bible.reveal_1 = parsed.get("reveal_1")
            if parsed.get("reveal_2"):
                story_bible.reveal_2 = parsed.get("reveal_2")
            if parsed.get("secret"):
                story_bible.secret = parsed.get("secret")
            if parsed.get("clues"):
                story_bible.clues = parsed.get("clues")

        story_bible.generation_request_id = str(uuid.uuid4())
        story_bible.generation_source = "REAL_AI"
        story_bible.model_name = self.last_used_model or model or self.default_model
        story_bible.provider_name = self.provider_name
        story_bible.last_modified_at = time.time()
        return story_bible, in_tok, out_tok

    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        """
        Writes a full, broadcast-grade long-form script (80-100 segments).
        Generates in two coherent parts (Acts 1-5 and Acts 6-9) to guarantee narrative density,
        exact delivery profiles, and prevent output truncation.
        """
        host_id = series_bible.get("host", {}).get("id", "MINH")
        host_name = series_bible.get("host", {}).get("display_name", "Minh")

        facts_summary = "\n".join(
            f"- {f.field}: {f.value} ({f.description})" for f in story_bible.critical_facts
        )
        supporting_summary = "\n".join(
            f"- {sc.get('name', 'Nhân vật phụ')} ({sc.get('role', 'Người thân')}, {sc.get('age', '')} tuổi): {sc.get('description', '')} | Lý do im lặng: {sc.get('reason_for_silence', '')}"
            for sc in (story_bible.supporting_characters or []) if isinstance(sc, dict)
        )
        knowledge_summary = json.dumps(story_bible.knowledge_ledger or [], ensure_ascii=False)
        clues_summary = json.dumps(story_bible.structured_clues or story_bible.clues or [], ensure_ascii=False)
        causal_summary = json.dumps(story_bible.causal_chains or [], ensure_ascii=False)

        clean_title = re.sub(r"^(?:Tập\s+)?EP_?[A-Z0-9_]*\d+\s*[-:]?\s*", "", str(story_bible.title or ""), flags=re.IGNORECASE).strip()
        protag_name = story_bible.protagonist.get("name", "Tuấn") if isinstance(story_bible.protagonist, dict) else str(story_bible.protagonist or "Tuấn")
        if protag_name.lower() in ("nhân vật chính", "protagonist"):
            protag_name = "Tuấn"

        user_topic_constraint = ""
        if getattr(story_bible, "original_user_topic", ""):
            user_topic_constraint = (
                f"\n=== CHỦ ĐỀ BẮT BUỘC TỪ NGƯỜI DÙNG (AUTHORITATIVE TOPIC) ===\n"
                f"Đề tài cốt lõi: \"{story_bible.original_user_topic}\"\n"
                f"Toàn bộ diễn biến, xung đột, manh mối và bước ngoặt BẮT BUỘC phải xoay quanh và đào sâu đề tài này.\n"
                f"Tuyệt đối KHÔNG làm biến tướng câu chuyện sang các bi kịch gia đình/y tế/phẫu thuật/bán đất không liên quan!\n"
            )

        system_instruction = (
            f"Bạn là Người dẫn chuyện và Biên kịch duy nhất của series tâm sự/tài liệu gia đình 'Sau Cánh Cửa'.\n"
            f"Người dẫn chuyện: MC {host_name} ({host_id}) - giọng đọc TTS độc quyền, điềm đạm, trưởng thành, nhân văn, quan sát tinh tế.\n"
            f"Định dạng nội dung: Một lá thư/câu chuyện tâm sự của nhân vật gửi về cho chương trình. MC Minh là người đọc toàn bộ kịch bản.\n"
            f"QUY TẮC CỨNG BẮT BUỘC:\n"
            f"1. KHÔNG ĐỌC MÃ TẬP / SỐ TẬP NỘI BỘ: Tuyệt đối KHÔNG viết hoặc đọc các mã như 'EP1005', 'EP002', 'IDEA_...', và KHÔNG đọc số thứ tự tập bằng chữ hay số. Khi chào mở đầu ở phân đoạn 004, MC Minh CHỈ nói: 'Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.'\n"
            f"2. KHÔNG NGẮT TẬP GIẢ TẠO: Đây là một tập phim hoàn chỉnh liền mạch. Tuyệt đối KHÔNG dùng các cụm từ 'phần tiếp theo', 'ở phần sau', 'hãy đón xem', 'chúng ta sẽ quay lại sau', 'tập tiếp theo' ở bất kỳ đâu trong kịch bản. Lời chào kết chuẩn chỉ được xuất hiện ĐÚNG MỘT LẦN trong object cuối cùng của PHẦN 2: 'Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.' PHẦN 1 tuyệt đối không được khép lại câu chuyện, cảm ơn thính giả, chào tạm biệt hoặc dùng delivery_profile='ENDING'.\n"
            f"3. CHỈ DÙNG NHÂN VẬT TRONG STORY BIBLE: Tuyệt đối không tự bịa thêm tên riêng nhân vật phụ ngoài danh sách Story Bible.\n"
            f"4. NHẤT QUÁN NHẬN THỨC NHÂN VẬT (KNOWLEDGE LEDGER): Tuân thủ tuyệt đối ai biết bí mật, ai không biết. Nếu trong Story Bible có người thân biết sự thật, tuyệt đối KHÔNG được viết câu mâu thuẫn như 'không một ai hay biết' hay 'không thể sẻ chia cùng ai kể cả người vợ gối chăn'.\n"
            f"5. KỶ LUẬT BẰNG CHỨNG (EVIDENCE CHAIN): Không nhảy cóc từ một manh mối ban đầu sang kết luận cuối cùng. Mỗi manh mối chỉ chứng minh đúng phạm vi của nó và đặt ra câu hỏi tiếp theo.\n"
            f"6. VĂN PHONG TỰ NHIÊN 'SHOW, DON'T LABEL': Kể bằng hành động, vật thể, ánh mắt, khoảng lặng đời thường. TUYỆT ĐỐI CẤM dùng các cụm từ sáo rỗng AI như: 'bí mật động trời', 'sự thật động trời', 'đòn chí mạng', 'sự thật kinh hoàng', 'cuộc gặp gỡ định mệnh', 'đau đớn đến tận cùng', 'vĩ đại ẩn giấu', 'mê cung không lối thoát', 'nấc nghẹn ngào đến xé lòng', 'cơn địa chấn', 'sét đánh ngang tai', 'bi kịch đẫm nước mắt', 'sự thật rỉ máu', 'chiếc lồng kính ngột ngạt', 'bóng ma vô hình', 'cuộc chiến ngầm khốc liệt', 'mặt nạ hoàn hảo', 'bức tường phòng thủ cuối cùng sụp đổ', 'đứng lặng như tượng đá', 'tiếng khóc xé lòng', 'vết thương sâu hoắm'.\n"
            f"7. PHẦN KẾT GỌN GÀNG (5-8%): Không giảng đạo lặp đi lặp lại nhiều đoạn cuối. Chỉ dùng đúng 1 phân đoạn đúc kết chiêm nghiệm duy nhất trước khi chào tạm biệt.\n"
            f"8. Phân loại delivery_profile chính xác theo 6 loại: HOOK, NORMAL, MYSTERY, REVEAL, COMMENT, ENDING. Không đặt câu hỏi khán giả (audience_address: false) trong phân đoạn REVEAL.\n"
            f"9. TUYỆT ĐỐI KHÔNG DÙNG NHÃN TEMPLATE / DATABASE NỘI BỘ (INTERNAL LABELS): Lời đọc của MC là văn xuôi tự nhiên, TUYỆT ĐỐI KHÔNG chứa các nhãn kỹ thuật như: 'Nhân vật chính', 'Manh mối 1', 'Manh mối 2', 'Manh mối 3', 'Bước ngoặt 1', 'Bước ngoặt 2', 'Reveal 1', 'Reveal 2', 'Fact Lock', 'Story Bible', 'central_conflict', 'topic_intent'. Luôn dùng tên riêng cụ thể của nhân vật (ví dụ: {protag_name}) thay cho cụm danh xưng 'Nhân vật chính'.\n"
            f"10. TÊN MINH CHỈ DÀNH CHO MC: Không đặt tên hoặc mã MINH cho nhân vật trong truyện.\n"
            f"11. KHÔNG KỂ LẠI: Mỗi hành động điều tra, cuộc gọi, cuộc gặp và phát hiện chỉ được kể một lần. Phần 2 nối thẳng hành động cuối Phần 1.\n"
            f"12. KỶ LUẬT KẾT LUẬN: Tin nhắn, lịch sử cuộc gọi, lời đồn hoặc lời thú nhận đơn độc chỉ là dấu hiệu; không gọi chúng là chứng cứ không thể chối cãi nếu thiếu chi tiết độc lập có thể kiểm chứng.\n"
            f"13. TRÁCH NHIỆM NHÂN VẬT: Bối cảnh hôn nhân không biến sự xa cách của người bị phản bội thành lỗi cho lựa chọn nói dối/ngoại tình của người kia."
        )

        # ---------------- PART 1: ACTS 1 to 5 (~40 to 50 Segments) ----------------
        prompt_part1 = f"""Hãy viết PHẦN 1 cho kịch bản câu chuyện: '{clean_title}'.
Mục tiêu độ dài Phần 1: Khoảng 1.200 - 1.500 từ tiếng Việt, triển khai tự nhiên khoảng 40 - 50 phân đoạn.
{user_topic_constraint}
Thông tin Story Bible:
- Nhân vật chính: {protag_name} ({story_bible.protagonist.get('age', 30) if isinstance(story_bible.protagonist, dict) else 30} tuổi) - {story_bible.protagonist.get('description', '') if isinstance(story_bible.protagonist, dict) else ''}
- Nhân vật phụ (CHỈ ĐƯỢC DÙNG CÁC TÊN NÀY):
{supporting_summary}
- Quan hệ: {story_bible.relationships}
- Bí mật cốt lõi: {story_bible.secret}
- Câu hỏi bí ẩn: {story_bible.mystery_question}
- Giả thuyết sai ban đầu: {story_bible.false_lead}
- Chuỗi manh mối có cấu trúc (CHỈ chứng minh trong giới hạn what_it_proves, KHÔNG nhảy cóc sang kết luận cuối):
{clues_summary}
- Sổ cái nhận thức nhân vật (Knowledge Ledger):
{knowledge_summary}
- Các sự thật đóng băng (Fact Lock - TUYỆT ĐỐI TUÂN THỦ, KHÔNG SỬA ĐỔI):
{facts_summary}

Cấu trúc Phân bổ Phần 1 (khoảng 40-50 phân đoạn):
1. Act 1: HOOK (khoảng 5-6 phân đoạn đầu):
   - Hai phân đoạn đầu phải mở ngay bằng một vật thể, tin nhắn, thời điểm hoặc hành động bất thường cụ thể trong lá thư; phải có từ "bất thường", "dấu hiệu", "nghi vấn", "bí mật", "lá thư" hoặc một câu hỏi trực tiếp (delivery_profile='HOOK', speed=0.98). Tuyệt đối không kết luận trước sự thật ở Reveal.
   - Lời chào mở đầu chương trình của {host_name}: BẮT BUỘC mở đầu bằng "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa." (KHÔNG đọc số tập hay mã tập, delivery_profile='NORMAL', speed=1.01).
   - Giới thiệu nhân vật gửi thư và bước vào bối cảnh câu chuyện (delivery_profile='NORMAL', speed=1.01).
2. Act 2: SETUP (khoảng 10-12 phân đoạn):
   - Đời sống thường nhật, bối cảnh gia đình/công việc, những chi tiết quan sát cụ thể trước khi phát hiện bất thường.
   - Chứa đúng 1 phân đoạn giao lưu khán giả gợi mở (audience_address=true, delivery_profile='COMMENT').
3. Act 3: MYSTERY / FIRST ANOMALY (khoảng 10-12 phân đoạn):
   - Manh mối 1 xuất hiện. Chỉ mô tả đúng những gì Manh mối 1 cho thấy và đặt câu hỏi tiếp theo, không nhảy cóc kết luận (delivery_profile='MYSTERY' và 'NORMAL').
   - Chứa đúng 1 phân đoạn giao lưu khán giả đặt câu hỏi giả thuyết (audience_address=true, delivery_profile='COMMENT').
4. Act 4: ESCALATION (khoảng 8-10 phân đoạn):
   - Giả thuyết sai ban đầu (false lead) xuất hiện từ góc nhìn hạn chế của nhân vật chính (delivery_profile='NORMAL' và 'MYSTERY').
5. Act 5: INVESTIGATION (khoảng 8-10 phân đoạn):
   - Nhân vật chính chỉ bắt đầu chuẩn bị hành động xác minh; dừng trước khi nhân chứng trả lời hoặc tài liệu thứ hai được đọc.
   - Tuyệt đối không dùng REVEAL trong PHẦN 1 và không hoàn tất cuộc gặp/đối thoại sẽ mở đầu PHẦN 2.

ĐIỂM DỪNG BẮT BUỘC CỦA PHẦN 1:
- Dừng ở một hành động xác minh đang diễn ra hoặc một câu hỏi còn mở để PHẦN 2 tiếp tục trực tiếp.
- KHÔNG tiết lộ đáp án cuối, KHÔNG giải quyết xung đột, KHÔNG đúc kết bài học, KHÔNG cảm ơn và KHÔNG chào tạm biệt.
- Không object nào trong PHẦN 1 được dùng delivery_profile='ENDING'.

Yêu cầu định dạng JSON:
Trả về JSON Object có khóa "segments": [
  {{
    "id": "001",
    "speaker": "{host_id}",
    "text": "Lời dẫn tiếng Việt tự nhiên, điềm đạm, cụ thể, khoảng 28-42 từ...",
    "delivery_profile": "HOOK",
    "importance": "high",
    "audience_address": false,
    "speed": 0.98
  }}
]
"""
        messages_p1 = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt_part1},
        ]
        raw_p1, in_tok1, out_tok1 = self._call_chat_completion(messages_p1, model=model, response_json=True)
        p1_data = _extract_script_segments(raw_p1)
        if len(p1_data) < _MIN_SCRIPT_PART_SEGMENTS or _part_has_closure(p1_data) or _part_has_premature_reveal(p1_data):
            retry_messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_part1 + """

YÊU CẦU SỬA BẮT BUỘC: Kết quả trước bị thiếu phân đoạn hoặc đã khép lại câu chuyện quá sớm.
Viết lại TOÀN BỘ PHẦN 1 với ít nhất 30 phân đoạn. Không ENDING hoặc REVEAL, không lời cảm ơn/chào tạm biệt, không giải quyết bí mật.
Phân đoạn cuối phải để một hành động xác minh đang tiếp diễn cho PHẦN 2 nối trực tiếp.
"""},
            ]
            raw_retry, retry_in, retry_out = self._call_chat_completion(
                retry_messages, model=model, response_json=True
            )
            in_tok1 += retry_in
            out_tok1 += retry_out
            p1_data = _extract_script_segments(raw_retry)
        if len(p1_data) < _MIN_SCRIPT_PART_SEGMENTS:
            raise RuntimeError(
                f"OpenAI-compatible provider returned only {len(p1_data)} valid Part 1 segments after retry; at least {_MIN_SCRIPT_PART_SEGMENTS} are required."
            )
        if _part_has_closure(p1_data) or _part_has_premature_reveal(p1_data):
            raise RuntimeError("OpenAI-compatible Part 1 still reveals/closes the story after retry; script was rejected.")

        time.sleep(1)

        # ---------------- PART 2: ACTS 5 (cont) to 9 (~40 to 50 Segments) ----------------
        p1_context = "\n".join(
            f"[{s.get('id')}] {str(s.get('text', ''))[:180]}"
            for s in p1_data
        )
        p1_count = len(p1_data)
        next_start_id = p1_count + 1

        prompt_part2 = f"""Hãy viết tiếp PHẦN 2 cho kịch bản câu chuyện: '{clean_title}'.
Mục tiêu độ dài Phần 2: Khoảng 1.200 - 1.600 từ tiếng Việt, triển khai tự nhiên khoảng 40 - 50 phân đoạn tiếp theo.

BẢN ĐỒ TOÀN BỘ NỘI DUNG ĐÃ KỂ Ở PHẦN 1 (tổng cộng {p1_count} phân đoạn):
{p1_context}

KỶ LUẬT NỐI MẠCH:
- Tiếp tục trực tiếp từ hành động cuối PHẦN 1. Không mở đầu lại, không giới thiệu lại nhân vật và không kể lại các dấu hiệu đã có.
- Mỗi chứng cứ cũ chỉ được nhắc rất ngắn khi dẫn thẳng đến một phát hiện mới.
- Chỉ khép lại câu chuyện ở Act 8 và chỉ chào kết đúng một lần trong object cuối cùng của PHẦN 2.

Nội dung Bước ngoặt, Chuỗi Nhân Quả & Hóa giải cảm xúc của Story Bible:
- Bước ngoặt 1 (Reveal 1): {story_bible.reveal_1}
- Bước ngoặt 2 (Reveal 2): {story_bible.reveal_2}
- Chuỗi nhân quả bắt buộc (CAUSE -> DECISION -> ACTION -> CONSEQUENCE - giải thích rõ tại sao giải pháp thông thường là bất khả thi):
{causal_summary}
- Sổ cái nhận thức nhân vật (Knowledge Ledger - TUYỆT ĐỐI KHÔNG MÂU THUẪN):
{knowledge_summary}
- Cao trào cảm xúc: {story_bible.emotional_payoff}
- Đúc kết nhân sinh: {story_bible.reflection_theme}
- Kết thúc: {story_bible.ending}
- Các sự thật đóng băng (Fact Lock - TUYỆT ĐỐI TUÂN THỦ):
{facts_summary}

Cấu trúc Phân bổ Phần 2 (khoảng 40-50 phân đoạn, bắt đầu từ id '{next_start_id:03d}'):
1. Act 5 (tiếp tục): EVIDENCE CHAIN (khoảng 8-10 phân đoạn):
   - Manh mối thứ 2 và thứ 3 xuất hiện cụ thể, từng bước dẫn tới sự thật (delivery_profile='MYSTERY' và 'NORMAL').
2. Act 6: MAJOR REVEAL (khoảng 7-9 phân đoạn, rơi vào vị trí khoảng 60-75% toàn bộ câu chuyện):
   - Sự thật Bước ngoặt 1 được mở ra rõ ràng qua chứng cứ xác thực.
   - BẮT BUỘC: delivery_profile='REVEAL', importance='critical', audience_address=false (KHÔNG hỏi khán giả).
3. Act 7: SECOND REVEAL / CAUSAL EXPLANATION (khoảng 10-12 phân đoạn, rơi vào vị trí khoảng 75-90% toàn bộ câu chuyện):
   - Bước ngoặt 2 giải thích đầy đủ chuỗi nhân quả: Nguyên nhân (WHY) -> Lý do không thể làm cách bình thường (MOTIVATION) -> Cơ chế thực hiện thực tế (HOW) -> Hệ quả (CONSEQUENCE).
   - Tuân thủ chặt chẽ Knowledge Ledger: không viết "không ai biết / kể cả người vợ" nếu trong truyện có người thân biết sự thật.
   - BẮT BUỘC: audience_address=false. Các phân đoạn mở nút thắt chính dùng delivery_profile='REVEAL' (speed=0.92), các phân đoạn giải thích hoàn cảnh dùng delivery_profile='NORMAL'.
4. Act 8: EMOTIONAL PAYOFF & RESOLUTION (khoảng 10-12 phân đoạn):
   - Cuộc đối thoại trực tiếp, hành động cụ thể, cử chỉ đời thường khi các nhân vật đối diện và tháo gỡ khúc mắc (delivery_profile='NORMAL').
   - Chứa đúng 1 phân đoạn giao lưu khán giả (audience_address=true, delivery_profile='COMMENT').
5. Act 9: CONCISE REFLECTION + SIGN-OFF (khoảng 4-6 phân đoạn cuối, KHÔNG LẶP Ý):
   - Hình ảnh khép lại câu chuyện của gia đình nhân vật bằng chi tiết đời thực lắng đọng (delivery_profile='NORMAL', audience_address=false).
   - ĐÚNG 1 phân đoạn duy nhất đúc kết bài học chiêm nghiệm từ câu chuyện (delivery_profile='COMMENT', audience_address=false).
   - ĐÚNG 1 câu hỏi gợi suy ngẫm gửi tới thính giả (delivery_profile='COMMENT', audience_address=true).
   - Lời cảm ơn người gửi thư, cảm ơn thính giả và lời chào tạm biệt ngắn gọn của {host_name}: 'Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.' (delivery_profile='ENDING', speed=0.965, audience_address=false).

Yêu cầu định dạng JSON:
Trả về JSON Object có khóa "segments": [
  {{
    "id": "{next_start_id:03d}",
    "speaker": "{host_id}",
    "text": "Lời dẫn tiếng Việt tự nhiên, điềm đạm, khoảng 28-42 từ...",
    "delivery_profile": "MYSTERY",
    "importance": "normal",
    "audience_address": false,
    "speed": 0.96
  }}
]
"""
        messages_p2 = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt_part2},
        ]
        raw_p2, in_tok2, out_tok2 = self._call_chat_completion(messages_p2, model=model, response_json=True)
        p2_data = _extract_script_segments(raw_p2)
        _normalize_final_closure(p2_data)
        combined_candidate = p1_data + p2_data
        if (
            len(p2_data) < _MIN_SCRIPT_PART_SEGMENTS
            or len(combined_candidate) < _MIN_COMPLETE_SCRIPT_SEGMENTS
            or not _has_valid_final_closure(combined_candidate)
            or has_repeated_narrative_block(combined_candidate)
        ):
            retry_messages = [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_part2 + """

YÊU CẦU SỬA BẮT BUỘC: Kết quả trước bị thiếu phân đoạn, đặt ENDING sai vị trí hoặc kể lại sự kiện đã có trong PHẦN 1.
Viết lại TOÀN BỘ PHẦN 2 với ít nhất 30 phân đoạn. Chỉ object cuối cùng được dùng delivery_profile='ENDING'
và chứa đúng lời chào chuẩn. Nối trực tiếp hành động cuối PHẦN 1; không lặp cuộc gọi, cuộc gặp, manh mối hay phát hiện cũ.
"""},
            ]
            raw_retry, retry_in, retry_out = self._call_chat_completion(
                retry_messages, model=model, response_json=True
            )
            in_tok2 += retry_in
            out_tok2 += retry_out
            p2_data = _extract_script_segments(raw_retry)
            _normalize_final_closure(p2_data)
            combined_candidate = p1_data + p2_data
        if len(p2_data) < _MIN_SCRIPT_PART_SEGMENTS:
            raise RuntimeError(
                f"OpenAI-compatible provider returned only {len(p2_data)} valid Part 2 segments after retry; at least {_MIN_SCRIPT_PART_SEGMENTS} are required."
            )
        if len(combined_candidate) < _MIN_COMPLETE_SCRIPT_SEGMENTS:
            raise RuntimeError(
                f"OpenAI-compatible provider returned only {len(combined_candidate)} total script segments after retry; at least {_MIN_COMPLETE_SCRIPT_SEGMENTS} are required."
            )
        if not _has_valid_final_closure(combined_candidate):
            raise RuntimeError("OpenAI-compatible script does not contain exactly one final sign-off after retry; script was rejected.")
        if has_repeated_narrative_block(combined_candidate):
            raise RuntimeError("OpenAI-compatible Part 2 still repeats a narrative block from Part 1 after retry; script was rejected.")

        combined_data = combined_candidate
        segments: List[ScriptSegment] = []
        for idx, item in enumerate(combined_data):
            seg_id = f"{idx + 1:03d}"
            prof = item.get("delivery_profile", "NORMAL")
            if prof not in ["HOOK", "NORMAL", "MYSTERY", "REVEAL", "COMMENT", "ENDING"]:
                prof = "NORMAL"

            aud_addr = bool(item.get("audience_address", False))
            if prof == "REVEAL":
                aud_addr = False

            imp = item.get("importance", "normal")
            if prof == "REVEAL":
                imp = "critical"
            elif prof == "HOOK":
                imp = "high"

            speed = float(item.get("speed", 1.0))
            if prof == "REVEAL":
                speed = 0.92
            elif prof == "HOOK":
                speed = 0.98
            elif prof == "ENDING":
                speed = 0.965
            elif prof == "COMMENT":
                speed = 1.025
            elif prof == "MYSTERY":
                speed = 0.96
            else:
                speed = 1.01

            seg = ScriptSegment(
                id=seg_id,
                speaker=host_id,
                text=item.get("text", "").strip(),
                delivery_profile=prof,
                importance=imp,
                audience_address=aud_addr,
                speed=speed,
                pause_before=0.1 if prof == "REVEAL" else 0.05,
                pause_after=0.6 if prof == "REVEAL" else 0.25,
            )
            segments.append(seg)

        # Rebalance audience interactions if needed (must be 3 to 6)
        aud_indices = [i for i, s in enumerate(segments) if s.audience_address and s.delivery_profile != "REVEAL"]
        if len(aud_indices) < 3 and len(segments) >= 30:
            step = len(segments) // 4
            for target_idx in [step, 2 * step, len(segments) - 3]:
                if target_idx < len(segments) and not segments[target_idx].audience_address and segments[target_idx].delivery_profile != "REVEAL":
                    segments[target_idx].audience_address = True
                    segments[target_idx].delivery_profile = "COMMENT"
                    aud_indices.append(target_idx)
                    if len(aud_indices) >= 3:
                        break
        elif len(aud_indices) > 6:
            for i in aud_indices[6:]:
                segments[i].audience_address = False
                if segments[i].delivery_profile == "COMMENT":
                    segments[i].delivery_profile = "NORMAL"

        total_words = sum(len(s.text.split()) for s in segments)
        chosen_model_name = self.last_used_model or model or self.default_model

        script = FullScript(
            episode_id=story_bible.episode_id,
            title=clean_title or story_bible.title,
            host={"id": host_id, "name": host_name, "voice": "Binh"},
            segments=segments,
            total_segments=len(segments),
            total_words=total_words,
            status="DRAFT",
            generation_request_id=str(uuid.uuid4()),
            prompt_version="script-v3.1",
            generation_source="REAL_AI",
            model_name=chosen_model_name,
            provider_name=self.provider_name,
            created_at=time.time(),
            updated_at=time.time(),
        )
        return script, in_tok1 + in_tok2, out_tok1 + out_tok2

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
        report = ScriptQCEngine.audit_script(script, story_bible, story_formula, series_bible)
        return report, 100, 100

    def revise_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        from apps.script_factory.script_qc import apply_targeted_repairs
        script.revision_round += 1
        repaired = apply_targeted_repairs(script, story_bible, qc_report)
        repaired.total_words = sum(len(s.text.split()) for s in repaired.segments)
        repaired.updated_at = time.time()
        return repaired, 100, 100
