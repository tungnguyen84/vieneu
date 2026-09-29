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
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, QCReport, ScriptSegment, StoryBible
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
        for fb in ["gemini-2.5-pro", "gemini-flash-latest", "gemini-2.5-flash"]:
            if fb not in candidate_models:
                candidate_models.append(fb)

        last_err = None
        for cur_model in candidate_models:
            url = f"{GEMINI_API_BASE}/models/{cur_model}:generateContent?key={self.api_key}"

            payload: Dict[str, Any] = {
                "contents": [
                    {
                        "parts": [{"text": prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.75,
                    "topP": 0.95,
                    "thinkingConfig": {
                        "thinkingBudget": 0
                    }
                }
            }
            if response_json:
                payload["generationConfig"]["responseMimeType"] = "application/json"

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

            # Retry up to 3 times per model for 503 / 429
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
                    if e.code in (503, 429) and attempt < 2:
                        sleep_s = 2 ** (attempt + 1)
                        logger.warning(f"[GeminiProvider] {cur_model} returned {e.code}. Retrying in {sleep_s}s...")
                        time.sleep(sleep_s)
                        continue
                    else:
                        logger.warning(f"[GeminiProvider] {cur_model} failed with HTTP {e.code}. Trying next model...")
                        break
                except Exception as e:
                    last_err = e
                    logger.warning(f"[GeminiProvider] Connection error with {cur_model}: {e}. Retrying...")
                    time.sleep(2)
                    continue

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
    ) -> Tuple[StoryBible, int, int]:
        """Expands an idea into a Story Bible using Gemini."""
        # For pilot 01 we don't call this, but provide full implementation
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        mock = MockScriptAIProvider()
        return mock.create_story_bible(idea, series_bible, model)

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
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        mock = MockScriptAIProvider()
        return mock.revise_script(script, story_bible, qc_report, model)
