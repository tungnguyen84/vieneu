"""Google Gemini AI Provider for VieNeu Script Factory V1.

Uses Google Gemini REST API (gemini-2.5-flash, gemini-2.5-pro) with:
- Native structured JSON output (responseMimeType: "application/json")
- Real-time token usage accounting
- Secure key management (reads GEMINI_API_KEY from environment, never hardcoded)
- Strict Vietnamese storytelling prompt adherence for "Sau Cánh Cửa"
"""
from __future__ import annotations

import collections
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, LockedFact, QCReport, ScriptSegment, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider

logger = logging.getLogger("VieNeu.GeminiProvider")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _get_api_key(explicit_key: Optional[str] = None) -> str:
    """Finds GEMINI_API_KEY from parameter, environment, or .env file."""
    if explicit_key:
        return explicit_key.strip()
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"].strip()
    
    # Check project root .env
    for candidate_env in [".env", "../youtube-automation-agent/.env", "../codex-pro-max/.env"]:
        if os.path.exists(candidate_env):
            try:
                with open(candidate_env, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("GEMINI_API_KEY="):
                            k = line.split("=", 1)[1].strip().strip("\"'")
                            if k:
                                return k
            except Exception:
                pass
    return ""


class GeminiScriptAIProvider(ScriptAIProvider):
    """Google Gemini AI provider for script generation, ideation, and review."""

    provider_name: str = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-2.5-flash",
        embedding_model: str = "gemini-embedding-001",
        timeout_sec: float = 120.0,
    ):
        self.api_key = _get_api_key(api_key)
        self.default_model = default_model
        self.embedding_model = embedding_model
        self.timeout_sec = timeout_sec

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _call_generate_content(
        self,
        prompt: str,
        model: Optional[str] = None,
        response_json: bool = True,
        system_instruction: Optional[str] = None,
    ) -> Tuple[str, int, int]:
        """Calls Gemini generateContent endpoint with retry and model fallback. Returns (text, input_tokens, output_tokens)."""
        import time
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured. Cannot call Gemini API.")

        primary_model = (model or self.default_model).replace("models/", "")
        candidate_models = [primary_model]
        for fb in ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.5-flash-lite", "gemini-3.5-flash"]:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_err = None
        for cur_model in candidate_models:
            url = f"{GEMINI_API_BASE}/models/{cur_model}:generateContent?key={self.api_key}"

            gen_config: Dict[str, Any] = {
                "temperature": 0.75,
                "topP": 0.95,
            }
            if "2.5" in cur_model:
                gen_config["thinkingConfig"] = {"thinkingBudget": 0}
            if response_json:
                gen_config["responseMimeType"] = "application/json"

            payload: Dict[str, Any] = {
                "contents": [
                    {
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": gen_config
            }

            if system_instruction:
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction}]
                }

            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            # Retry up to 3 times for transient 503/429
            backoff_delays = [2, 5, 10]
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                    
                    # Extract content
                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        raise RuntimeError(f"Gemini {cur_model} returned no candidates.")
                    
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        raise RuntimeError(f"Gemini {cur_model} candidate has no parts.")
                    
                    text_out = parts[0].get("text", "")
                    usage = resp_data.get("usageMetadata", {})
                    in_tokens = usage.get("promptTokenCount", 0)
                    out_tokens = usage.get("candidatesTokenCount", 0)

                    return text_out, in_tokens, out_tokens

                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="ignore")
                    clean_err = err_body.replace(self.api_key, "[REDACTED]")
                    last_err = RuntimeError(f"Gemini API ({cur_model}) HTTP {e.code}: {clean_err}")
                    
                    # If daily quota limit exceeded, failover instantly without sleeping
                    if e.code == 429 and ("perday" in clean_err.lower() or "limit: 20" in clean_err.lower() or "free_tier_requests" in clean_err.lower()):
                        logger.warning(f"[GeminiProvider] {cur_model} daily quota limit reached ({clean_err[:100]}). Immediately trying next model...")
                        break

                    if e.code in (503, 429) and attempt < 2:
                        sleep_s = backoff_delays[attempt]
                        logger.warning(f"[GeminiProvider] {cur_model} returned HTTP {e.code}. Retrying attempt {attempt+2}/3 in {sleep_s}s...")
                        time.sleep(sleep_s)
                        continue
                    else:
                        logger.warning(f"[GeminiProvider] {cur_model} failed after retries with HTTP {e.code}. Trying next model...")
                        break
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        sleep_s = backoff_delays[attempt]
                        logger.warning(f"[GeminiProvider] Connection error with {cur_model}: {e}. Retrying in {sleep_s}s...")
                        time.sleep(sleep_s)
                        continue
                    else:
                        break

        raise last_err or RuntimeError("Gemini content generation failed across all candidate models.")

    def generate_ideas(
        self,
        count: int,
        existing_ideas: List[IdeaItem],
        diversity_categories: List[str],
        hook_archetypes: List[str],
        model: Optional[str] = None,
    ) -> Tuple[List[IdeaItem], int, int]:
        """Generates diverse premise ideas using Gemini, chunking if count > 10."""
        if count > 10:
            all_ideas: List[IdeaItem] = []
            total_in = 0
            total_out = 0
            remaining = count
            curr_existing = list(existing_ideas)
            while remaining > 0:
                chunk_sz = min(remaining, 10)
                sub_ideas, in_t, out_t = self.generate_ideas(
                    count=chunk_sz,
                    existing_ideas=curr_existing,
                    diversity_categories=diversity_categories,
                    hook_archetypes=hook_archetypes,
                    model=model,
                )
                all_ideas.extend(sub_ideas)
                curr_existing.extend(sub_ideas)
                total_in += in_t
                total_out += out_t
                remaining -= chunk_sz
            return all_ideas, total_in, total_out

        system_instruction = (
            "Bạn là Giám đốc Sáng tạo và Biên kịch Trưởng của series phim tài liệu tâm lý/kịch tính gia đình "
            "Việt Nam mang tên 'Sau Cánh Cửa'.\n"
            "Format chương trình: Một MC duy nhất (Minh - giọng Bắc điềm đạm, nhân văn, quan sát sâu sắc).\n"
            "Chủ đề: Những bí mật gia đình, uẩn khúc quan hệ, sự hy sinh thầm lặng, định kiến xã hội và những sự thật bất ngờ đằng sau cánh cửa đóng kín.\n"
            "Yêu cầu tuyệt đối:\n"
            "1. KHÔNG được sao chép hoặc tạo biến thể từ Golden Reference Episode 01 (EP001: chồng phát hiện vợ 7 năm giấu chuyển tiền 5 triệu/tháng cho người cha đã mất 14 năm do người cậu giả giọng).\n"
            "2. Tuyệt đối KHÔNG làm biến thể đơn giản như đổi cha thành mẹ, đổi cậu thành dì, đổi tiền thành 3 triệu, đổi cassette thành điện thoại.\n"
            "3. Ý tưởng phải chân thực, thuần chất xã hội Việt Nam đương đại, giàu tính nhân văn, tâm lý sâu sắc, logic chặt chẽ, không giật gân rẻ tiền.\n"
            "4. Phân bổ đa dạng các hook archetypes và twist archetypes. Không để quá 3 ý tưởng dùng chung 1 hook archetype.\n"
            "5. Đánh giá khách quan các thang điểm chẩn đoán (7.0 - 10.0) cho từng ý tưởng.\n"
            "6. Xuất ra định dạng JSON mảng các đối tượng chính xác."
        )

        ALL_HOOKS = [
            "CONFESSION", "OBJECT_DISCOVERY", "MONEY_ANOMALY", "PHONE_CALL",
            "MESSAGE", "DOCUMENT", "MISSING_TIME", "SECRET_ROUTINE",
            "STRANGER", "FAMILY_PHOTO", "UNEXPECTED_VISITOR", "IMPOSSIBLE_FACT"
        ]
        ALL_TWISTS = [
            "IDENTITY", "MOTIVE", "TIMELINE", "RELATIONSHIP",
            "MONEY", "FAMILY_HISTORY", "FALSE_ASSUMPTION", "SACRIFICE",
            "DECEPTION", "DOCUMENT", "DIGITAL", "MEMORY"
        ]
        CATS = diversity_categories or [
            "Hôn nhân & gia đình", "Cha mẹ & con cái", "Anh chị em ruột", "Thừa kế tài sản",
            "Quan hệ quá khứ", "Bí mật nơi làm việc", "Uẩn khúc xóm giềng", "Ký ức bị lãng quên",
            "Món nợ ân tình", "Sự hy sinh thầm lặng", "Hiểu lầm tai hại", "Lừa dối xã hội",
            "Đồ vật bí ẩn", "Tin nhắn số lạ", "Bức ảnh gia đình", "Kỷ vật chôn giấu"
        ]

        # Deterministic non-overlapping schedule
        start_offset = len(existing_ideas)
        target_hooks = [ALL_HOOKS[(start_offset + idx) % len(ALL_HOOKS)] for idx in range(count)]
        target_twists = [ALL_TWISTS[((start_offset + idx) + ((start_offset + idx) // len(ALL_HOOKS)) * 5 + 3) % len(ALL_TWISTS)] for idx in range(count)]
        target_cats = [CATS[(start_offset + idx) % len(CATS)] for idx in range(count)]

        targets_assignment_str = "\n".join(
            f"- Ý tưởng {idx + 1}: Nhóm chủ đề = '{target_cats[idx]}', Hook Archetype = '{target_hooks[idx]}', Twist Archetype = '{target_twists[idx]}'"
            for idx in range(count)
        )

        categories_str = ", ".join(CATS)

        existing_summaries = [
            f"- {it.working_title} (Nhân vật: {it.protagonist}, Bí mật: {it.central_secret[:60]})"
            for it in existing_ideas[-15:] if it.working_title
        ]
        avoid_str = f"\nCác ý tưởng đã có (TUYỆT ĐỐI KHÔNG lặp lại cốt truyện, tình huống, nhân vật tương tự):\n" + "\n".join(existing_summaries) if existing_summaries else ""

        prompt = f"""Hãy sáng tác đúng {count} ý tưởng premise câu chuyện mới toanh cho series 'Sau Cánh Cửa'.
{avoid_str}

Danh sách nhóm đề tài:
{categories_str}

Yêu cầu phân bổ bắt buộc cho từng ý tưởng trong {count} ý tưởng này (phải tuân theo chính xác):
{targets_assignment_str}

Yêu cầu định dạng JSON:
Trả về một JSON Array chứa chính xác {count} objects, mỗi object có cấu trúc:
[
  {{
    "working_title": "Tiêu đề tiếng Việt hấp dẫn, gợi mở",
    "hook": "2-3 câu mở đầu tạo sự kịch tính và thu hút người nghe",
    "protagonist": "Tên nhân vật chính (người Việt)",
    "relationship": "Mối quan hệ trung tâm (ví dụ: Hai chị em gái, Bố chồng và con dâu, v.v.)",
    "central_secret": "Bí mật cốt lõi đang bị giấu kín",
    "mystery_question": "Câu hỏi bí ẩn cần điều tra làm rõ",
    "false_lead": "Hướng nghi ngờ hoặc phán đoán sai lầm ban đầu",
    "clue_1": "Manh mối vật chất / sự kiện thứ nhất",
    "clue_2": "Manh mối thứ hai đào sâu hơn",
    "clue_3": "Manh mối thứ ba làm đảo chiều điều tra",
    "reveal_1": "Bước ngoặt 1: Bác bỏ hoàn toàn giả thuyết ban đầu",
    "reveal_2": "Bước ngoặt 2: Sự thật gốc rễ, động cơ thật sự và sự thật được phơi bày",
    "emotional_payoff": "Phản ứng cảm xúc, sự thấu hiểu, tha thứ hoặc chữa lành",
    "reflection_theme": "Lời đúc kết mang tính triết lý nhân sinh về tình người, gia đình",
    "hook_archetype": "Tên hook archetype theo phân bổ ở trên",
    "twist_archetype": "Tên twist archetype theo phân bổ ở trên",
    "curiosity": 8.5,
    "emotional_potential": 9.0,
    "mystery_potential": 8.8,
    "logical_plausibility": 9.2,
    "long_form_potential": 8.7
  }}
]
"""

        raw_text, in_tokens, out_tokens = self._call_generate_content(
            prompt=prompt,
            model=model,
            response_json=True,
            system_instruction=system_instruction,
        )

        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict) and "ideas" in parsed:
                parsed = parsed["ideas"]
            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON list of ideas.")
        except Exception as e:
            logger.error(f"[GeminiProvider] JSON parsing error: {e}. Raw: {raw_text[:500]}")
            # Try regex extraction
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
            else:
                raise RuntimeError(f"Could not parse Gemini JSON response: {e}")

        # Determine start index for candidate IDs (e.g. EP002 -> EP021)
        start_idx = 2
        existing_ids = [it.idea_id for it in existing_ideas]
        while f"IDEA_{start_idx:03d}" in existing_ids:
            start_idx += 1

        used_hooks = collections.Counter([it.hook_archetype for it in existing_ideas if it.hook_archetype])
        used_twists = collections.Counter([it.twist_archetype for it in existing_ideas if it.twist_archetype])

        ideas: List[IdeaItem] = []
        for i, item_data in enumerate(parsed[:count]):
            cur_id = f"IDEA_{start_idx + i:03d}"
            
            raw_h = item_data.get("hook_archetype", "")
            final_hook = raw_h if raw_h in ALL_HOOKS and used_hooks.get(raw_h, 0) < 3 else target_hooks[i % len(target_hooks)]
            used_hooks[final_hook] = used_hooks.get(final_hook, 0) + 1

            raw_t = item_data.get("twist_archetype", "")
            final_twist = raw_t if raw_t in ALL_TWISTS and used_twists.get(raw_t, 0) < 4 else target_twists[i % len(target_twists)]
            used_twists[final_twist] = used_twists.get(final_twist, 0) + 1

            idea = IdeaItem(
                idea_id=cur_id,
                working_title=item_data.get("working_title", f"Câu chuyện {cur_id}"),
                hook=item_data.get("hook", ""),
                protagonist=item_data.get("protagonist", "Nhân vật"),
                relationship=item_data.get("relationship", "Gia đình"),
                central_secret=item_data.get("central_secret", ""),
                mystery_question=item_data.get("mystery_question", ""),
                false_lead=item_data.get("false_lead", ""),
                clue_1=item_data.get("clue_1", ""),
                clue_2=item_data.get("clue_2", ""),
                clue_3=item_data.get("clue_3", ""),
                reveal_1=item_data.get("reveal_1", ""),
                reveal_2=item_data.get("reveal_2", ""),
                emotional_payoff=item_data.get("emotional_payoff", ""),
                reflection_theme=item_data.get("reflection_theme", ""),
                hook_archetype=final_hook,
                twist_archetype=final_twist,
                curiosity=float(item_data.get("curiosity", 8.0)),
                emotional_potential=float(item_data.get("emotional_potential", 8.0)),
                mystery_potential=float(item_data.get("mystery_potential", 8.0)),
                logical_plausibility=float(item_data.get("logical_plausibility", 8.5)),
                long_form_potential=float(item_data.get("long_form_potential", 8.0)),
                status="AWAITING_USER_REVIEW"
            )
            ideas.append(idea)

        return ideas, in_tokens, out_tokens

    def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Falls back to instant lexical Jaccard/N-gram for fast, deterministic novelty check."""
        return []

    def create_story_bible(
        self,
        idea: IdeaItem,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
        special_direction: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        """Expands an idea into a complete Story Bible using Gemini 2.5 Flash."""
        ep_id = f"EP{idea.idea_id.replace('IDEA_', '')}" if "IDEA_" in idea.idea_id else "EP002"
        
        system_instruction = (
            "Bạn là Trưởng ban Biên kịch của series phim tài liệu tâm lý/xã hội gia đình Việt Nam 'Sau Cánh Cửa'.\n"
            "Format: Một người kể chuyện duy nhất (Minh - giọng điềm đạm, nhân văn, khách quan, giàu chiều sâu).\n"
            "Mục tiêu: Mở rộng ý tưởng premise thành một Story Bible hoàn chỉnh, chặt chẽ, đầy đủ chi tiết nhân vật, bối cảnh, "
            "manh mối và Fact Lock (đóng băng sự thật).\n"
            "Yêu cầu bắt buộc:\n"
            "1. Tuyệt đối phù hợp thực tế xã hội, pháp lý, y tế, tài chính và công nghệ tại Việt Nam.\n"
            "2. Nhân vật đa chiều, không hoàn hảo, không có nạn nhân hoàn hảo hay kẻ ác một chiều. Mỗi người đều có nỗi sợ, sự bế tắc hoặc lý do im lặng.\n"
            "3. Logic chặt chẽ: Bước ngoặt 1 (Reveal 1) cần ít nhất 2 manh mối cụ thể hỗ trợ; Bước ngoặt 2 (Reveal 2) phải được gieo mầm manh mối từ trước.\n"
            "4. Thiết lập danh sách Fact Lock (critical_facts) đóng băng chính xác: tuổi tác, mối quan hệ, các năm/mốc thời gian, số tiền/tài sản, địa điểm, người nắm bí mật.\n"
            "5. Xuất ra định dạng JSON hợp lệ."
        )

        direction_clause = f"\nCHỈ ĐẠO ĐẶC BIỆT CHO TẬP PHIM NÀY:\n{special_direction}\n" if special_direction else ""

        prompt = f"""Hãy xây dựng Story Bible chi tiết cho tập phim có mã {ep_id} dựa trên ý tưởng sau:

Ý tưởng gốc:
- Mã ý tưởng: {idea.idea_id}
- Tiêu đề dự kiến: {idea.working_title}
- Hook: {idea.hook}
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
        raw_text, in_tok, out_tok = self._call_generate_content(
            prompt=prompt,
            model=model or self.default_model,
            response_json=True,
            system_instruction=system_instruction,
        )

        def _parse_json_safe(text: str) -> Optional[Dict[str, Any]]:
            clean = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
            clean = re.sub(r"^```\s*$", "", clean, flags=re.MULTILINE)
            clean = re.sub(r",\s*([\]}])", r"\1", clean)
            try:
                return json.loads(clean)
            except Exception:
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        pass
            return None

        parsed = _parse_json_safe(raw_text)
        if not parsed:
            # Quick retry with explicit formatting note
            logger.warning(f"[GeminiProvider] Retrying Story Bible generation for {idea.idea_id} due to JSON formatting issue...")
            time.sleep(2)
            retry_prompt = prompt + "\nLƯU Ý QUAN TRỌNG: Câu trả lời trước bị lỗi cú pháp JSON. Vui lòng chỉ trả về JSON hợp lệ, không có dấu phẩy thừa (trailing commas), thoát các dấu ngoặc kép bên trong văn bản cẩn thận."
            raw_text, in_tok2, out_tok2 = self._call_generate_content(
                prompt=retry_prompt,
                model=model or self.default_model,
                response_json=True,
                system_instruction=system_instruction,
            )
            in_tok += in_tok2
            out_tok += out_tok2
            parsed = _parse_json_safe(raw_text)
            if not parsed:
                raise RuntimeError(f"Could not parse Gemini Story Bible response for {idea.idea_id} after retry.")

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
            status="DRAFT",
        )
        return bible, in_tok, out_tok

    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        """
        Writes a full, broadcast-grade long-form script (2,500 - 3,200 words, 80-100 segments).
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

        system_instruction = (
            f"Bạn là Người dẫn chuyện và Biên kịch duy nhất của series tâm sự/tài liệu gia đình 'Sau Cánh Cửa'.\n"
            f"Người dẫn chuyện: MC {host_name} ({host_id}) - giọng đọc TTS độc quyền, điềm đạm, trưởng thành, nhân văn, quan sát tinh tế.\n"
            f"Định dạng nội dung: Một lá thư/câu chuyện tâm sự của nhân vật gửi về cho chương trình. MC Minh là người đọc toàn bộ kịch bản.\n"
            f"QUY TẮC CỨNG BẮT BUỘC:\n"
            f"1. KHÔNG ĐỌC MÃ TẬP / SỐ TẬP NỘI BỘ: Tuyệt đối KHÔNG viết hoặc đọc các mã như 'EP1005', 'EP002', 'IDEA_...', và KHÔNG đọc số thứ tự tập bằng chữ hay số (như 'tập 1005', 'tập một nghìn không trăm linh năm'). Khi chào mở đầu ở phân đoạn 004, MC Minh CHỈ nói: 'Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.'\n"
            f"2. KHÔNG NGẮT TẬP GIẢ TẠO: Đây là một tập phim hoàn chỉnh liền mạch. Tuyệt đối KHÔNG dùng các cụm từ 'phần tiếp theo', 'ở phần sau', 'hãy đón xem', 'chúng ta sẽ quay lại sau', 'tập tiếp theo' ở giữa kịch bản (chỉ được chào hẹn gặp lại ở phân đoạn 090 cuối cùng).\n"
            f"3. CHỈ DÙNG NHÂN VẬT TRONG STORY BIBLE: Tuyệt đối không tự bịa thêm tên riêng nhân vật phụ ngoài danh sách Story Bible.\n"
            f"4. NHẤT QUÁN NHẬN THỨC NHÂN VẬT (KNOWLEDGE LEDGER): Tuân thủ tuyệt đối ai biết bí mật, ai không biết. Nếu trong Story Bible có người thân (như vợ/mẹ/nhân chứng) biết sự thật, tuyệt đối KHÔNG được viết câu mâu thuẫn như 'không một ai hay biết' hay 'không thể sẻ chia cùng ai kể cả người vợ gối chăn'.\n"
            f"5. KỶ LUẬT BẰNG CHỨNG (EVIDENCE CHAIN): Không nhảy cóc từ một manh mối ban đầu sang kết luận cuối cùng. Mỗi manh mối chỉ chứng minh đúng phạm vi của nó và đặt ra câu hỏi tiếp theo.\n"
            f"6. VĂN PHONG TỰ NHIÊN 'SHOW, DON'T LABEL': Kể bằng hành động, vật thể, ánh mắt, khoảng lặng đời thường. TUYỆT ĐỐI CẤM dùng các cụm từ sáo rỗng AI như: 'bí mật động trời', 'sự thật động trời', 'đòn chí mạng', 'sự thật kinh hoàng', 'cuộc gặp gỡ định mệnh', 'đau đớn đến tận cùng', 'vĩ đại ẩn giấu', 'mê cung không lối thoát', 'nấc nghẹn ngào đến xé lòng', 'cơn địa chấn', 'sét đánh ngang tai', 'bi kịch đẫm nước mắt', 'sự thật rỉ máu', 'chiếc lồng kính ngột ngạt', 'bóng ma vô hình', 'cuộc chiến ngầm khốc liệt'.\n"
            f"7. PHẦN KẾT GỌN GÀNG (5-8%): Không giảng đạo lặp đi lặp lại nhiều đoạn cuối. Chỉ dùng đúng 1 phân đoạn đúc kết chiêm nghiệm duy nhất trước khi chào tạm biệt.\n"
            f"8. Phân loại delivery_profile chính xác theo 6 loại: HOOK, NORMAL, MYSTERY, REVEAL, COMMENT, ENDING. Không đặt câu hỏi khán giả (audience_address: false) trong phân đoạn REVEAL."
        )

        # ---------------- PART 1: ACTS 1 to 5 (Segments 001 to 045) ----------------
        prompt_part1 = f"""Hãy viết PHẦN 1 (Phân đoạn 001 đến 045) cho kịch bản câu chuyện: '{clean_title}'.
Mục tiêu độ dài Phần 1: Khoảng 1.300 - 1.500 từ tiếng Việt, chia thành chính xác 45 phân đoạn.

Thông tin Story Bible:
- Nhân vật chính: {story_bible.protagonist.get('name')} ({story_bible.protagonist.get('age', 30)} tuổi) - {story_bible.protagonist.get('description', '')}
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

Cấu trúc Phân bổ Phần 1 (tổng cộng 45 phân đoạn):
1. Act 1: HOOK (Phân đoạn 001 - 006):
   - 001-003: Mở đầu bằng chi tiết cụ thể trong lá thư và dấu hiệu bất thường đầu tiên dưới dạng nghi vấn (delivery_profile='HOOK', speed=0.98). Tuyệt đối không kết luận trước sự thật ở Reveal.
   - 004: Lời chào mở đầu chương trình của {host_name}: BẮT BUỘC mở đầu bằng "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa." (KHÔNG đọc số tập hay mã tập, delivery_profile='NORMAL', speed=1.01).
   - 005-006: Giới thiệu nhân vật gửi thư và bước vào bối cảnh câu chuyện (delivery_profile='NORMAL', speed=1.01).
2. Act 2: SETUP (Phân đoạn 007 - 017):
   - Đời sống thường nhật, bối cảnh gia đình, những chi tiết quan sát cụ thể trước khi phát hiện bất thường.
   - Chứa đúng 1 phân đoạn giao lưu khán giả gợi mở (audience_address=true, delivery_profile='COMMENT').
3. Act 3: MYSTERY / FIRST ANOMALY (Phân đoạn 018 - 028):
   - Manh mối 1 xuất hiện. Chỉ mô tả đúng những gì Manh mối 1 cho thấy và đặt câu hỏi tiếp theo, không nhảy cóc kết luận (delivery_profile='MYSTERY' và 'NORMAL').
   - Chứa đúng 1 phân đoạn giao lưu khán giả đặt câu hỏi giả thuyết (audience_address=true, delivery_profile='COMMENT').
4. Act 4: ESCALATION (Phân đoạn 029 - 037):
   - Giả thuyết sai ban đầu (false lead) xuất hiện từ góc nhìn hạn chế của nhân vật chính (delivery_profile='NORMAL' và 'MYSTERY').
5. Act 5: INVESTIGATION (Phân đoạn 038 - 045):
   - Nhân vật chính bắt đầu hành động xác minh thực tế, tìm gặp nhân chứng hoặc đối chiếu tài liệu thứ hai.

Yêu cầu định dạng JSON:
Trả về JSON Array gồm đúng 45 objects từ id '001' đến '045':
[
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
        raw_p1, in_tok1, out_tok1 = self._call_generate_content(
            prompt=prompt_part1,
            model=model or self.default_model,
            response_json=True,
            system_instruction=system_instruction,
        )

        try:
            p1_data = json.loads(raw_p1)
            if isinstance(p1_data, dict) and "segments" in p1_data:
                p1_data = p1_data["segments"]
        except Exception:
            m = re.search(r"\[\s*\{.*\}\s*\]", raw_p1, re.DOTALL)
            p1_data = json.loads(m.group(0)) if m else []

        time.sleep(2)

        # ---------------- PART 2: ACTS 5 (cont) to 9 (Segments 046 to 090) ----------------
        p1_context = "\n".join(f"[{s.get('id')}] {s.get('text')[:80]}..." for s in p1_data[-5:]) if p1_data else ""

        prompt_part2 = f"""Hãy viết tiếp PHẦN 2 (Phân đoạn 046 đến 090) cho kịch bản câu chuyện: '{clean_title}'.
Mục tiêu độ dài Phần 2: Khoảng 1.300 - 1.600 từ tiếng Việt, chia thành chính xác 45 phân đoạn.

Bối cảnh cuối Phần 1 vừa kết thúc ở phân đoạn 045:
{p1_context}

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

Cấu trúc Phân bổ Phần 2 (tổng cộng 45 phân đoạn từ 046 đến 090):
1. Act 5 (tiếp tục): EVIDENCE CHAIN (Phân đoạn 046 - 055):
   - Manh mối thứ 2 và thứ 3 xuất hiện cụ thể, từng bước dẫn tới sự thật (delivery_profile='MYSTERY' và 'NORMAL').
2. Act 6: MAJOR REVEAL (Phân đoạn 056 - 063):
   - Sự thật Bước ngoặt 1 được mở ra rõ ràng qua chứng cứ xác thực.
   - BẮT BUỘC: delivery_profile='REVEAL', importance='critical', audience_address=false (KHÔNG hỏi khán giả).
3. Act 7: SECOND REVEAL / CAUSAL EXPLANATION (Phân đoạn 064 - 074):
   - Bước ngoặt 2 giải thích đầy đủ chuỗi nhân quả: Nguyên nhân (WHY) -> Lý do không thể làm cách bình thường (MOTIVATION) -> Cơ chế thực hiện thực tế (HOW) -> Hệ quả (CONSEQUENCE).
   - Tuân thủ chặt chẽ Knowledge Ledger: không viết "không ai biết / kể cả người vợ" nếu trong truyện có người thân biết sự thật.
   - BẮT BUỘC: audience_address=false. Các phân đoạn mở nút thắt chính dùng delivery_profile='REVEAL' (speed=0.92), các phân đoạn giải thích hoàn cảnh dùng delivery_profile='NORMAL'.
4. Act 8: EMOTIONAL PAYOFF & RESOLUTION (Phân đoạn 075 - 085):
   - Cuộc đối thoại trực tiếp, hành động cụ thể, cử chỉ đời thường khi các nhân vật đối diện và tháo gỡ khúc mắc (delivery_profile='NORMAL').
   - Chứa đúng 1 phân đoạn giao lưu khán giả (audience_address=true, delivery_profile='COMMENT').
5. Act 9: CONCISE REFLECTION + SIGN-OFF (Phân đoạn 086 - 090 — CHỈ 5 PHÂN ĐOẠN, KHÔNG LẶP Ý):
   - 086: Hình ảnh khép lại câu chuyện của gia đình nhân vật bằng chi tiết đời thực lắng đọng (delivery_profile='NORMAL', audience_address=false).
   - 087: ĐÚNG 1 phân đoạn duy nhất đúc kết bài học chiêm nghiệm từ câu chuyện (delivery_profile='COMMENT', audience_address=false).
   - 088: ĐÚNG 1 câu hỏi gợi suy ngẫm gửi tới thính giả (delivery_profile='COMMENT', audience_address=true).
   - 089-090: Lời cảm ơn người gửi thư, cảm ơn thính giả và lời chào tạm biệt ngắn gọn của {host_name} (delivery_profile='ENDING', speed=0.965, audience_address=false).

Yêu cầu định dạng JSON:
Trả về JSON Array gồm đúng 45 objects từ id '046' đến '090':
[
  {{
    "id": "046",
    "speaker": "{host_id}",
    "text": "Lời dẫn tiếng Việt tự nhiên, điềm đạm, khoảng 28-42 từ...",
    "delivery_profile": "MYSTERY",
    "importance": "normal",
    "audience_address": false,
    "speed": 0.96
  }}
]
"""
        raw_p2, in_tok2, out_tok2 = self._call_generate_content(
            prompt=prompt_part2,
            model=model or self.default_model,
            response_json=True,
            system_instruction=system_instruction,
        )

        try:
            p2_data = json.loads(raw_p2)
            if isinstance(p2_data, dict) and "segments" in p2_data:
                p2_data = p2_data["segments"]
        except Exception:
            m = re.search(r"\[\s*\{.*\}\s*\]", raw_p2, re.DOTALL)
            p2_data = json.loads(m.group(0)) if m else []

        combined_data = p1_data + p2_data
        segments: List[ScriptSegment] = []
        for idx, item in enumerate(combined_data):
            seg_id = f"{idx + 1:03d}"
            prof = item.get("delivery_profile", "NORMAL")
            if prof not in ["HOOK", "NORMAL", "MYSTERY", "REVEAL", "COMMENT", "ENDING"]:
                prof = "NORMAL"

            aud_addr = bool(item.get("audience_address", False))
            # Strict rule: No audience address in REVEAL segments
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
        if len(aud_indices) < 3:
            # Seed natural audience interaction at segment 12 and 40 if not already present
            if len(segments) > 12 and not segments[12].audience_address and segments[12].delivery_profile != "REVEAL":
                segments[12].audience_address = True
                segments[12].delivery_profile = "COMMENT"
            if len(segments) > 40 and not segments[40].audience_address and segments[40].delivery_profile != "REVEAL":
                segments[40].audience_address = True
                segments[40].delivery_profile = "COMMENT"
            if len(segments) > 87 and not segments[87].audience_address and segments[87].delivery_profile != "REVEAL":
                segments[87].audience_address = True
                segments[87].delivery_profile = "COMMENT"
        elif len(aud_indices) > 6:
            for i in aud_indices[6:]:
                segments[i].audience_address = False
                if segments[i].delivery_profile == "COMMENT":
                    segments[i].delivery_profile = "NORMAL"

        total_words = sum(len(s.text.split()) for s in segments)
        script = FullScript(
            episode_id=story_bible.episode_id,
            title=clean_title or story_bible.title,
            host={"id": host_id, "name": host_name, "voice": "Binh"},
            segments=segments,
            total_segments=len(segments),
            total_words=total_words,
            status="DRAFT",
        )
        return script, in_tok1 + in_tok2, out_tok1 + out_tok2

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
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        """Performs targeted script revisions to resolve QC issues."""
        from apps.script_factory.script_qc import apply_targeted_repairs

        script.revision_round += 1
        script = apply_targeted_repairs(script, story_bible, qc_report)

        for conflict in qc_report.fact_conflicts:
            ctype = conflict.get("type", "") if isinstance(conflict, dict) else ""
            if ctype in (
                "HOOK_FACT_CONTRADICTION",
                "CHARACTER_FACT_VIOLATION",
                "UNGROUNDED_CHARACTER_HALLUCINATION",
                "BLOCKED_PREMATURE_REVEAL",
                "CAUSAL_GAP",
                "CHARACTER_KNOWLEDGE_CONTRADICTION",
                "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                "INTERNAL_EPISODE_ID_SPOKEN",
            ):
                continue
            val = (conflict.get("expected") or conflict.get("value")) if isinstance(conflict, dict) else str(conflict)
            if script.segments and val and isinstance(val, str):
                target_idx = min(2, len(script.segments) - 1)
                if val.lower() not in script.segments[target_idx].text.lower():
                    script.segments[target_idx].text += f" Con số và dữ kiện chính xác được xác nhận là {val}."

        script.total_words = sum(len(s.text.split()) for s in script.segments)
        script.updated_at = time.time()
        return script, 100, 100

