"""Google Gemini AI Provider for VieNeu Script Factory V1.

Uses Google Gemini REST API (gemini-2.5-flash, gemini-2.5-pro) with:
- Native structured JSON output (responseMimeType: "application/json")
- Real-time token usage accounting
- Secure key management (reads GEMINI_API_KEY from environment, never hardcoded)
- Strict Vietnamese storytelling prompt adherence for "Sau Cánh Cửa"
"""
from __future__ import annotations

import collections
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, LockedFact, QCReport, ScriptSegment, StoryBible, apply_story_bible_patch, story_bible_repair_targets_clause
from apps.script_factory.narrative_continuity import has_repeated_narrative_block
from apps.script_factory.json_response import parse_json_response
from apps.script_factory.scene_outline import build_scene_outline, outline_block
from apps.script_factory.single_pass_writer import build_prompt as build_single_pass_prompt, write_single_pass
from apps.script_factory.script_craft import STORY_DESIGN_PRINCIPLES, voice_reference_block
from apps.script_factory.narrative_rules import ACT7_CAUSAL_INSTRUCTION, writer_rules_block
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent

logger = logging.getLogger("VieNeu.GeminiProvider")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

_SCRIPT_SIGNOFF_RE = re.compile(
    r"(?:cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|"
    r"xin\s+chào\s+và\s+hẹn\s+gặp\s+lại|"
    r"tôi\s+là\s+minh[^.]{0,80}hẹn\s+gặp\s+lại)",
    re.IGNORECASE,
)


def _parse_script_segment_array(raw: str) -> List[Dict[str, Any]]:
    """Parse a Gemini JSON response into a segment list."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "segments" in data:
            data = data["segments"]
        return data if isinstance(data, list) else []
    except Exception:
        match = re.search(r"\[\s*\{.*\}\s*\]", raw, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else []


def _part_has_closure(segments: List[Dict[str, Any]]) -> bool:
    """Return True when a non-final generation part prematurely closes the show."""
    return any(
        str(segment.get("delivery_profile", "")).upper() == "ENDING"
        or bool(_SCRIPT_SIGNOFF_RE.search(str(segment.get("text", ""))))
        for segment in segments
        if isinstance(segment, dict)
    )


def _part_has_premature_reveal(segments: List[Dict[str, Any]]) -> bool:
    return any(
        isinstance(segment, dict)
        and str(segment.get("delivery_profile", "")).upper() == "REVEAL"
        for segment in segments
    )


_CANONICAL_SIGNOFF = "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."


def _normalize_final_signoff(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Moves the broadcast close to exactly one final segment.

    A misplaced or missing sign-off is a formatting slip, not a story defect, so
    it is repaired here instead of discarding an otherwise usable 80-segment script.
    """
    body: List[Dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", ""))
        if _SCRIPT_SIGNOFF_RE.search(text):
            # Keep any story content that shares a segment with a stray sign-off.
            kept = " ".join(
                s for s in re.split(r"(?<=[.!?])\s+", text)
                if s and not _SCRIPT_SIGNOFF_RE.search(s) and not re.match(r"tôi\s+là\s+minh", s, re.IGNORECASE)
            ).strip()
            if not kept:
                continue
            segment = {**segment, "text": kept}
        if str(segment.get("delivery_profile", "")).upper() == "ENDING":
            segment = {**segment, "delivery_profile": "COMMENT"}
        body.append(segment)
    if not body:
        return body
    template = body[-1]
    body.append({
        "speaker": template.get("speaker", "MINH"),
        "text": _CANONICAL_SIGNOFF,
        "delivery_profile": "ENDING",
        "importance": "normal",
        "audience_address": False,
        "speed": 0.965,
    })
    return body


def _has_one_final_signoff(segments: List[Dict[str, Any]]) -> bool:
    """The completed episode must have one sign-off, in its final segment only."""
    if not segments:
        return False
    signoff_indices = [
        idx for idx, segment in enumerate(segments)
        if isinstance(segment, dict) and _SCRIPT_SIGNOFF_RE.search(str(segment.get("text", "")))
    ]
    ending_indices = [
        idx for idx, segment in enumerate(segments)
        if isinstance(segment, dict) and str(segment.get("delivery_profile", "")).upper() == "ENDING"
    ]
    final_idx = len(segments) - 1
    return signoff_indices == [final_idx] and ending_indices == [final_idx]


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


# Gemini free-tier quotas are counted per Google Cloud project *and per model*:
# each model has its own requests-per-day bucket, while every key created in the
# same project shares that project's buckets. So capacity grows by falling back
# across models and by rotating keys that belong to different projects.
GEMINI_FLASH_CHAIN = [
    "gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
    "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-flash-latest",
]
# Lite models write passable prose but cannot be trusted as reviewers.
GEMINI_LITE_CHAIN = [
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-flash-lite-latest",
]
_FALLBACK_ELIGIBLE = set(GEMINI_FLASH_CHAIN) | set(GEMINI_LITE_CHAIN) | {
    "gemini-2.5-pro", "gemini-pro-latest", "gemini-3.1-pro-preview",
}

# (key fingerprint or "*", model or "*") -> epoch seconds when the block lifts.
_QUOTA_BLOCKS: Dict[Tuple[str, str], float] = {}
_MODEL_LAST_SUCCESS: Dict[Tuple[Tuple[str, ...], str], float] = {}


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _next_quota_reset(now: Optional[float] = None) -> float:
    """Daily Gemini quotas reset at midnight Pacific time."""
    import datetime
    now = time.time() if now is None else now
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
    except Exception:
        tz = datetime.timezone(datetime.timedelta(hours=-8))
    local = datetime.datetime.fromtimestamp(now, tz)
    tomorrow = (local + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return tomorrow.timestamp()


def _is_blocked(key: str, model: str, now: Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    fp = _key_fingerprint(key)
    return any(_QUOTA_BLOCKS.get(slot, 0) > now for slot in ((fp, model), (fp, "*"), ("*", model)))


def _block(key: Optional[str], model: str, until: float) -> None:
    slot = (_key_fingerprint(key) if key else "*", model)
    _QUOTA_BLOCKS[slot] = max(_QUOTA_BLOCKS.get(slot, 0), until)


def _quota_block_until(error_body: str, now: Optional[float] = None) -> float:
    """How long a 429 should take this key+model out of rotation."""
    now = time.time() if now is None else now
    lower = error_body.lower()
    if "perday" in lower or "per_day" in lower or "requests_per_day" in lower:
        return _next_quota_reset(now)
    retry = re.search(r'"retrydelay":\s*"(\d+)(?:\.\d+)?s"', lower)
    if retry:
        return now + int(retry.group(1)) + 1
    if "perminute" in lower or "per_minute" in lower:
        return now + 60
    return now + 600


class GeminiScriptAIProvider(ScriptAIProvider):
    """Google Gemini AI provider for script generation, ideation, and review."""

    provider_name: str = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = "gemini-2.5-flash",
        embedding_model: str = "gemini-embedding-001",
        timeout_sec: float = 120.0,
        api_keys: Optional[List[str]] = None,
    ):
        keys: List[str] = []
        for raw in [*(api_keys or []), *re.split(r"[\s,;]+", _get_api_key(api_key) or "")]:
            raw = raw.strip()
            if raw and raw not in keys:
                keys.append(raw)
        self.api_keys = keys
        self.api_key = keys[0] if keys else ""
        self.last_used_key_index = 0
        self._sticky_review_model: Optional[str] = None
        self.default_model = default_model
        self.last_used_model = default_model
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
        allow_fallback: bool = True,
        temperature: float = 0.75,
        thinking_budget: int = 4096,
        allow_lite_models: bool = True,
    ) -> Tuple[str, int, int]:
        """Calls Gemini generateContent with model fallback and API-key rotation.

        Returns (text, input_tokens, output_tokens).
        """
        backoff_delays = [2, 5, 10]
        if not self.api_keys:
            raise RuntimeError("GEMINI_API_KEY is not configured. Cannot call Gemini API.")

        primary_model = (model or self.default_model).replace("models/", "")
        candidate_models = [primary_model]
        if allow_fallback and primary_model in _FALLBACK_ELIGIBLE:
            for fb in [*GEMINI_FLASH_CHAIN, *GEMINI_LITE_CHAIN]:
                if fb not in candidate_models:
                    candidate_models.append(fb)
        if not allow_lite_models:
            # Lite models answer review prompts with an empty list without reading
            # the script, which would turn "could not check" into a false PASS.
            candidate_models = [m for m in candidate_models if "lite" not in m]
        # A new UI operation creates a new provider. Prefer a recently working
        # fallback for these same credentials over several unavailable models,
        # while still trying the user's selected primary first.
        credential_scope = tuple(sorted(_key_fingerprint(k) for k in self.api_keys))
        now = time.time()
        if allow_fallback and candidate_models:
            primary, rest = candidate_models[0], candidate_models[1:]
            rest.sort(key=lambda m: _MODEL_LAST_SUCCESS.get((credential_scope, m), 0)
                      if now - _MODEL_LAST_SUCCESS.get((credential_scope, m), 0) < 600 else 0, reverse=True)
            candidate_models = [primary, *rest]
        # Keep the healthy model within one generation/repair operation. The
        # second script part must not retry an overloaded primary after a long
        # first part merely because its short cooldown expired.
        healthy = getattr(self, '_successful_generation_model', None)
        if allow_fallback and primary_model == self.default_model.replace('models/', '') and healthy in candidate_models:
            candidate_models.remove(healthy)
            candidate_models.insert(0, healthy)
        if not any(not _is_blocked(k, m) for m in candidate_models for k in self.api_keys):
            raise RuntimeError(
                "No usable Gemini model/key is available right now (quota exhausted for every "
                f"{'non-lite ' if not allow_lite_models else ''}model on all {len(self.api_keys)} key(s))."
            )

        def _redact(text: str) -> str:
            for k in self.api_keys:
                text = text.replace(k, "[REDACTED]")
            return text

        gen_config: Dict[str, Any] = {"temperature": temperature, "topP": 0.95}
        if response_json:
            gen_config["responseMimeType"] = "application/json"
        last_err: Optional[Exception] = None

        # Best model first across every key, then degrade to the next model.
        for cur_model in candidate_models:
            model_config = dict(gen_config)
            if "2.5" in cur_model:
                model_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}
            payload: Dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": model_config,
            }
            if system_instruction:
                payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
            data_bytes = json.dumps(payload).encode("utf-8")

            for key_index, key in enumerate(self.api_keys):
                if _is_blocked(key, cur_model):
                    continue
                key_label = f"key#{key_index + 1}"
                req = urllib.request.Request(
                    f"{GEMINI_API_BASE}/models/{cur_model}:generateContent?key={key}",
                    data=data_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                model_unusable = False
                for attempt in range(3):
                    call_started = time.time()
                    logger.info(f"→ Gọi {cur_model} ({key_label}/{len(self.api_keys)})...")
                    try:
                        with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                        candidates = resp_data.get("candidates", [])
                        if not candidates:
                            raise RuntimeError(f"Gemini {cur_model} returned no candidates.")
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if not parts:
                            raise RuntimeError(f"Gemini {cur_model} candidate has no parts.")
                        usage = resp_data.get("usageMetadata", {})
                        logger.info(
                            f"✓ {cur_model} ({key_label}) trả lời sau {time.time() - call_started:.0f}s, "
                            f"{usage.get('candidatesTokenCount', 0)} token"
                        )
                        self.last_used_model = cur_model
                        _MODEL_LAST_SUCCESS[(credential_scope, cur_model)] = time.time()
                        self._successful_generation_model = cur_model
                        self.last_used_key_index = key_index
                        return (
                            "".join(part.get("text", "") for part in parts if not part.get("thought")),
                            usage.get("promptTokenCount", 0),
                            usage.get("candidatesTokenCount", 0),
                        )
                    except urllib.error.HTTPError as e:
                        clean_err = _redact(e.read().decode("utf-8", errors="ignore"))
                        last_err = RuntimeError(f"Gemini API ({cur_model}, {key_label}) HTTP {e.code}: {clean_err}")
                        lower = clean_err.lower()
                        if e.code == 429:
                            until = _quota_block_until(clean_err)
                            _block(key, cur_model, until)
                            logger.warning(
                                f"[GeminiProvider] {cur_model} {key_label} rate-limited until "
                                f"{time.strftime('%H:%M', time.localtime(until))}; rotating to next key/model."
                            )
                            break
                        if e.code == 400 and ("api_key_invalid" in lower or "api key not valid" in lower):
                            _block(key, "*", time.time() + 86400)
                            logger.warning(f"[GeminiProvider] {key_label} is invalid; removed from rotation.")
                            break
                        if e.code in (403, 404):
                            # 404: model does not exist; 403: not enabled for this key's project.
                            _block(key if e.code == 403 else None, cur_model, time.time() + 86400)
                            model_unusable = e.code == 404
                            logger.warning(f"[GeminiProvider] {cur_model} unavailable for {key_label} (HTTP {e.code}).")
                            break
                        if e.code in (500, 503):
                            # Overload is model-wide on Google's side: other keys
                            # will not help, waiting rarely does. Park the model
                            # briefly for every key and move down the chain.
                            _block(None, cur_model, time.time() + 120)
                            model_unusable = True
                            logger.warning(f"[GeminiProvider] {cur_model} quá tải (HTTP {e.code}); tạm bỏ qua 2 phút, chuyển model kế tiếp.")
                            break
                        # Overloaded or rejected request: the model is the problem, not the key.
                        model_unusable = True
                        logger.warning(f"[GeminiProvider] {cur_model} failed with HTTP {e.code}. Trying next model...")
                        break
                    except Exception as e:
                        last_err = e
                        if isinstance(e, TimeoutError) or "timed out" in str(e).lower():
                            # A model that hangs for the full timeout usually hangs
                            # again; retrying it cost minutes per call.
                            _block(None, cur_model, time.time() + 300)
                            model_unusable = True
                            logger.warning(
                                f"[GeminiProvider] {cur_model} không phản hồi sau {self.timeout_sec:.0f}s; "
                                "tạm bỏ qua 5 phút, chuyển model kế tiếp."
                            )
                            break
                        if attempt < 1:
                            sleep_s = backoff_delays[attempt]
                            logger.warning(f"[GeminiProvider] Connection error with {cur_model}: {e}. Retrying in {sleep_s}s...")
                            time.sleep(sleep_s)
                            continue
                        model_unusable = True
                        break
                if model_unusable:
                    break

        raise last_err or RuntimeError("Gemini content generation failed across all candidate models and keys.")

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
        """Generates diverse premise ideas using Gemini, chunking if count > 10."""
        topic_intent_obj: Optional[TopicIntent] = None
        if topic_intent and isinstance(topic_intent, TopicIntent):
            topic_intent_obj = topic_intent
        elif topic_intent and isinstance(topic_intent, dict):
            topic_intent_obj = TopicIntent.from_dict(topic_intent)
        elif user_topic:
            topic_intent_obj = extract_topic_intent(user_topic, self)

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
                    user_topic=user_topic,
                    topic_intent=topic_intent_obj,
                )
                all_ideas.extend(sub_ideas)
                curr_existing.extend(sub_ideas)
                total_in += in_t
                total_out += out_t
                remaining -= chunk_sz
            return all_ideas, total_in, total_out

        topic_prompt_block = topic_intent_obj.to_prompt_constraint() if topic_intent_obj else ""

        system_instruction = (
            "Bạn là Giám đốc Sáng tạo và Biên kịch Trưởng của series phim tài liệu tâm lý/kịch tính Việt Nam mang tên 'Sau Cánh Cửa'.\n"
            "Format chương trình: Một MC duy nhất (Minh - giọng Bắc điềm đạm, nhân văn, quan sát sâu sắc).\n"
            + (
                f"CHỦ ĐỀ BẮT BUỘC TỪ NGƯỜI DÙNG: '{topic_intent_obj.original_topic}'.\n"
                f"USER TOPIC IS AUTHORITATIVE. Toàn bộ các ý tưởng PHẢI bám sát chủ đề '{topic_intent_obj.original_topic}' "
                f"({topic_intent_obj.primary_theme} trong bối cảnh {topic_intent_obj.context}).\n"
                f"Tuyệt đối KHÔNG thay thế bằng các chủ đề mặc định của Series Bible (như bí mật thừa kế gia tộc, tìm cha thất lạc, con nuôi...) "
                f"trừ khi chính chủ đề người dùng yêu cầu.\n"
                if topic_intent_obj else
                "Chủ đề: Những bí mật gia đình, uẩn khúc quan hệ, sự hy sinh thầm lặng, định kiến xã hội và những sự thật bất ngờ đằng sau cánh cửa đóng kín.\n"
            )
            + "Yêu cầu tuyệt đối:\n"
            "1. KHÔNG được sao chép hoặc tạo biến thể từ Golden Reference Episode 01.\n"
            "2. Ý tưởng phải chân thực, thuần chất xã hội Việt Nam đương đại, giàu tính nhân văn, tâm lý sâu sắc, logic chặt chẽ, không giật gân rẻ tiền.\n"
            "3. Đa dạng hóa các ý tưởng mà KHÔNG làm trôi chủ đề: Mỗi ý tưởng khai thác các góc nhìn nhân vật khác nhau, chứng cứ khác nhau, nhận định sai lầm khác nhau, ngã rẽ sự thật khác nhau nhưng CÙNG PHỤC VỤ chủ đề bắt buộc.\n"
            "4. Phân bổ đa dạng các hook archetypes và twist archetypes.\n"
            "5. Đánh giá khách quan các thang điểm chẩn đoán (7.0 - 10.0) cho từng ý tưởng.\n"
            "6. Xuất ra định dạng JSON mảng các đối tượng chính xác.\n"
            + STORY_DESIGN_PRINCIPLES
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

        if topic_intent_obj:
            targets_assignment_str = "\n".join(
                f"- Ý tưởng {idx + 1}: Bám sát chủ đề '{topic_intent_obj.original_topic}' | Hook Archetype = '{target_hooks[idx]}', Twist Archetype = '{target_twists[idx]}'"
                for idx in range(count)
            )
        else:
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
{topic_prompt_block}
{avoid_str}

Yêu cầu phân bổ bắt buộc cho từng ý tưởng trong {count} ý tưởng này (phải tuân theo chính xác):
{targets_assignment_str}

Yêu cầu định dạng JSON:
Trả về một JSON Array chứa chính xác {count} objects, mỗi object có cấu trúc:
[
  {{
    "working_title": "Tiêu đề tiếng Việt hấp dẫn, gợi mở",
    "hook": "2-3 câu mở đầu tạo sự kịch tính và thu hút người nghe",
    "protagonist": "Tên nhân vật chính (người Việt)",
    "relationship": "Mối quan hệ trung tâm (ví dụ: Đồng nghiệp và cấp dưới, Vợ và đối tác công việc của chồng, v.v.)",
    "central_secret": "Bí mật cốt lõi đang bị giấu kín",
    "mystery_question": "Câu hỏi bí ẩn cần điều tra làm rõ",
    "false_lead": "Hướng nghi ngờ hoặc phán đoán sai lầm ban đầu",
    "clue_1": "Manh mối vật chất / sự kiện thứ nhất",
    "clue_2": "Manh mối thứ hai đào sâu hơn",
    "clue_3": "Manh mối thứ ba làm đảo chiều điều tra",
    "reveal_1": "Bước ngoặt 1: Làm rõ sự thật từ bằng chứng, chỉ bác bỏ phần giả thuyết sai, giữ chủ đề người dùng",
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

            # Topic Adherence Evaluation without artificial string prepending
            if topic_intent_obj:
                adherence = topic_intent_obj.calculate_adherence_score(item_data)
                idea.topic_adherence_score = adherence
                idea.original_user_topic = topic_intent_obj.original_topic
                idea.topic_intent = topic_intent_obj.to_dict()
            elif user_topic:
                idea.original_user_topic = user_topic

            idea.generation_request_id = str(uuid.uuid4())
            idea.prompt_version = "ideas-v2.2-topic-truth"
            idea.generation_source = "REAL_AI"
            idea.model_name = self.last_used_model or model or self.default_model
            idea.provider_name = "GeminiScriptAIProvider"

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
            "5. VÒNG ĐỜI QUAN HỆ & THỜI ĐIỂM (RELATIONSHIP LIFECYCLE & TIMELINE): Timeline phải theo trình tự thời gian tăng dần hợp lý. Nếu câu chuyện có nhiều người con cùng mang huyết thống của người ngoài hôn nhân, dòng thời gian và mối quan hệ BẮT BUỘC phải khớp hoàn toàn: giải thích việc tiếp tục duy trì gặp gỡ/liên lạc bí mật kéo dài đến năm nào bao trùm các lần thụ thai, tuyệt đối KHÔNG tuyên bố cắt đứt liên lạc từ trước mà sau đó vẫn sinh thêm con sinh học của người đó.\n"
            "6. Tên Minh và mã MINH chỉ dành riêng cho MC, tuyệt đối không đặt cho nhân vật trong Story Bible.\n"
            "7. Với cáo buộc nghiêm trọng, lời đồn và dấu hiệu mơ hồ chỉ tạo nghi ngờ. Lời thừa nhận trực tiếp có thể xác nhận hành vi ngoại tình của chính người nói; huyết thống hoặc tội phạm cần bằng chứng phù hợp. Không bịa thêm văn bản tự tố cáo chỉ để đủ vật chứng.\n"
            "8. Bối cảnh hôn nhân có thể giải thích hoàn cảnh nhưng không được đổ trách nhiệm lựa chọn nói dối/ngoại tình lên người bị phản bội.\n"
            "9. Xuất ra định dạng JSON hợp lệ.\n"
            + STORY_DESIGN_PRINCIPLES + "\n"
            "Câu chuyện sẽ được kể như lá thư của nhân vật chính, nên mọi reveal phải có kênh để nhân vật chính biết được "
            "(lời thú nhận, nhân chứng, tài liệu, xét nghiệm) và kết thúc phải hợp pháp. Tuân thủ các luật logic sau:\n"
            + writer_rules_block(10)
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
      "decision": "Quyết định cụ thể dẫn đến sự thật thứ hai",
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
      "what_it_does_NOT_prove": "Giới hạn kết luận của manh mối này theo bằng chứng thực tế",
      "next_question": "Câu hỏi mới nảy sinh từ chi tiết cụ thể của tập này"
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

        orig_topic = idea.original_user_topic or (idea.topic_intent.get("original_topic") if idea.topic_intent else None)
        adherence_val = idea.topic_adherence_score if idea.topic_adherence_score is not None else 100.0

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
            prompt_version="story-v3.2-grounded-proof",
            generation_source="REAL_AI",
            model_name=self.last_used_model or model or self.default_model,
            provider_name="GeminiScriptAIProvider",
            generated_at=time.time(),
        )
        return bible, in_tok, out_tok

    def repair_story_bible(
        self,
        story_bible: StoryBible,
        issues: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        """
        Asks Gemini to repair Story Bible QC issues (causal gaps, knowledge contradictions, clue jumps)
        strictly preserving the authoritative user topic and character identities without injecting hardcoded templates.
        """
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
            "2. Khắc phục triệt để các vấn đề QC được chỉ rõ. Với lỗi logic cốt truyện, hãy BỔ SUNG kênh tiết lộ hoặc bằng chứng "
            "cụ thể (lời thú nhận trực tiếp, xét nghiệm có mẫu hợp lệ, tài liệu nhân vật chính đọc được); KHÔNG làm mờ reveal "
            "hay kết thúc thành nghi vấn chung chung. Câu chuyện phải giữ cú lật rõ ràng và kết thúc dứt khoát, hợp pháp.\n"
            "3. Chỉ trả về JSON hợp lệ gồm các trường đã sửa hoặc bổ sung."
        )

        prompt = f"""Dưới đây là Story Bible hiện tại và danh sách các lỗi QC cần khắc phục:

STORY BIBLE HIỆN TẠI:
{json.dumps(story_bible.to_dict(), ensure_ascii=False, indent=2)}

DANH SÁCH LỖI QC CẦN SỬA:
{issues_summary}

HƯỚNG DẪN SỬA CHỮA CỤ THỂ THEO TỪNG LOẠI LỖI:
1. Nếu có lỗi RELATIONSHIP_TIMELINE_CONTRADICTION:
   - Kiểm tra và sửa đổi timeline, relationships, secret, reveal_1, reveal_2 hoặc causal_chains.
   - Nếu nhiều người con sinh ở các năm khác nhau cùng mang huyết thống của người ngoài hôn nhân, BẮT BUỘC phải làm rõ mối quan hệ/gặp gỡ bí mật kéo dài đến năm nào bao trùm các lần thụ thai, thay vì tuyên bố cắt đứt liên lạc từ trước khi các con sau được thụ thai; hoặc điều chỉnh lại chi tiết số lượng con/huyết thống cho logic và nhất quán tuyệt đối.
2. Nếu có lỗi TIMELINE_FACT_CONTRADICTION:
   - Sắp xếp timeline theo thứ tự năm tăng dần, đảm bảo không có sự kiện mâu thuẫn sinh học hoặc hành động sau khi qua đời.
3. Nếu có lỗi CAUSAL_GAP:
   - Hoàn thiện đầy đủ chuỗi CAUSE -> DECISION -> ACTION -> CONSEQUENCE cho cả reveal_1 và reveal_2, nêu rõ WHY, HOW và MOTIVATION (vì sao giải pháp thông thường là bất khả thi trong hoàn cảnh đó).
4. Nếu có lỗi CHARACTER_KNOWLEDGE_CONTRADICTION:
   - Chỉnh sửa câu chữ trong secret, reveal_1, reveal_2 để không mâu thuẫn với knowledge_ledger (không viết 'không ai hay biết' nếu có người thân biết).
5. Chỉ bổ sung hoặc sửa các cấu trúc sau khi chúng thiếu/sai hoặc phụ thuộc trực tiếp vào lỗi QC; giữ nguyên các cấu trúc đang hợp lệ:
   - causal_chains (nguyên nhân, quyết định, hành động, hệ quả, lý do giải pháp thông thường bất khả thi)
   - knowledge_ledger (ai biết gì, khi nào biết, biết bằng cách nào, scope)
   - structured_clues (clue, what_it_proves, what_it_does_NOT_prove, next_question)
   - reveal_justifications (reveal_1 và reveal_2 có evidence_support, motivation_support, timeline_support, v.v.)
   - critical_facts (các sự thật cốt lõi đóng băng)

Chỉ xuất các trường đã sửa/bổ sung dưới dạng một JSON Object duy nhất, đúng tên trường của schema."""
        prompt += story_bible_repair_targets_clause(issues)

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
        if parsed is None:
            parsed = parse_json_response(raw_text)
        if parsed and isinstance(parsed, dict):
            apply_story_bible_patch(story_bible, parsed)
        else:
            logger.warning(f"Story Bible repair response was not JSON; nothing applied: start={raw_text[:160]!r}, end={raw_text[-200:]!r}")
            try:
                json.JSONDecoder(strict=False).raw_decode(raw_text, raw_text.find("{"))
            except json.JSONDecodeError as exc:
                logger.warning("Story patch JSON syntax error: %s; near=%r", exc, raw_text[max(0, exc.pos - 70):exc.pos + 90])
            raise ValueError('Story Bible repair returned invalid JSON; original draft was retained')

        story_bible.generation_request_id = str(uuid.uuid4())
        story_bible.generation_source = "REAL_AI"
        story_bible.model_name = self.last_used_model or model or self.default_model
        story_bible.provider_name = "GeminiScriptAIProvider"
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
        reveal_proof_summary = json.dumps(story_bible.reveal_justifications or {}, ensure_ascii=False)
        canonical_story = json.dumps({k: v for k, v in story_bible.to_dict().items()
                                     if k not in {'story_qc_report', 'status', 'approved_at', 'approved_by'}}, ensure_ascii=False)

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
            f"1. KHÔNG ĐỌC MÃ TẬP / SỐ TẬP NỘI BỘ: Tuyệt đối KHÔNG viết hoặc đọc các mã như 'EP1005', 'EP002', 'IDEA_...', và KHÔNG đọc số thứ tự tập bằng chữ hay số (như 'tập 1005', 'tập một nghìn không trăm linh năm'). Khi chào mở đầu ở phân đoạn 004, MC Minh CHỈ nói: 'Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.'\n"
            f"2. KHÔNG NGẮT TẬP GIẢ TẠO: Đây là một tập phim hoàn chỉnh liền mạch. Tuyệt đối KHÔNG dùng các cụm từ 'phần tiếp theo', 'ở phần sau', 'hãy đón xem', 'chúng ta sẽ quay lại sau', 'tập tiếp theo' ở bất kỳ đâu trong kịch bản. Lời chào kết thúc chuẩn chỉ được xuất hiện ĐÚNG MỘT LẦN trong phân đoạn CUỐI CÙNG của PHẦN 2: 'Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.' PHẦN 1 tuyệt đối không được khép lại câu chuyện, không được có delivery_profile='ENDING' và không được dùng bất kỳ lời cảm ơn hay lời chào tạm biệt nào.\n"
            f"3. CHỈ DÙNG NHÂN VẬT TRONG STORY BIBLE: Tuyệt đối không tự bịa thêm tên riêng nhân vật phụ ngoài danh sách Story Bible.\n"
            f"4. NHẤT QUÁN NHẬN THỨC NHÂN VẬT (KNOWLEDGE LEDGER): Tuân thủ tuyệt đối ai biết bí mật, ai không biết. Nếu trong Story Bible có người thân (như vợ/mẹ/nhân chứng) biết sự thật, tuyệt đối KHÔNG được viết câu mâu thuẫn như 'không một ai hay biết' hay 'không thể sẻ chia cùng ai kể cả người vợ gối chăn'.\n"
            f"5. KỶ LUẬT BẰNG CHỨNG (EVIDENCE CHAIN): Không nhảy cóc từ manh mối đầu sang kết luận cuối. Giới hạn của mỗi manh mối thể hiện bằng HÀNH ĐỘNG kiểm chứng tiếp theo của nhân vật, KHÔNG bằng câu rào đón của người kể ('chưa đủ để kết luận', 'mới chỉ là dấu hiệu').\n"
            f"6. VĂN PHONG TỰ NHIÊN 'SHOW, DON'T LABEL': Kể bằng hành động, vật thể, ánh mắt, khoảng lặng đời thường. TUYỆT ĐỐI CẤM dùng các cụm từ sáo rỗng AI như: 'bí mật động trời', 'sự thật động trời', 'đòn chí mạng', 'sự thật kinh hoàng', 'cuộc gặp gỡ định mệnh', 'đau đớn đến tận cùng', 'vĩ đại ẩn giấu', 'mê cung không lối thoát', 'nấc nghẹn ngào đến xé lòng', 'cơn địa chấn', 'sét đánh ngang tai', 'bi kịch đẫm nước mắt', 'sự thật rỉ máu', 'chiếc lồng kính ngột ngạt', 'bóng ma vô hình', 'cuộc chiến ngầm khốc liệt', 'mặt nạ hoàn hảo', 'bức tường phòng thủ cuối cùng sụp đổ', 'đứng lặng như tượng đá', 'tiếng khóc xé lòng', 'vết thương sâu hoắm'.\n"
            f"7. PHẦN KẾT GỌN GÀNG (5-8%): Không giảng đạo lặp đi lặp lại nhiều đoạn cuối. Chỉ dùng đúng 1 phân đoạn đúc kết chiêm nghiệm duy nhất trước khi chào tạm biệt.\n"
            f"8. Phân loại delivery_profile chính xác theo 6 loại: HOOK, NORMAL, MYSTERY, REVEAL, COMMENT, ENDING. Không đặt câu hỏi khán giả (audience_address: false) trong phân đoạn REVEAL.\n"
            f"9. TUYỆT ĐỐI KHÔNG DÙNG NHÃN TEMPLATE / DATABASE NỘI BỘ (INTERNAL LABELS): Lời đọc của MC là văn xuôi tự nhiên, TUYỆT ĐỐI KHÔNG chứa các nhãn kỹ thuật như: 'Nhân vật chính', 'Manh mối 1', 'Manh mối 2', 'Manh mối 3', 'Bước ngoặt 1', 'Bước ngoặt 2', 'Reveal 1', 'Reveal 2', 'Fact Lock', 'Story Bible', 'central_conflict', 'topic_intent'. Luôn dùng tên riêng cụ thể của nhân vật (ví dụ: {protag_name}) thay cho cụm danh xưng 'Nhân vật chính'.\n"
            f"10. TRÁNH VĂN PHONG 'BÁO CÁO KIỂM ĐỊNH': Tuyệt đối không lặp đi lặp lại các câu rào đón như 'chưa đủ căn cứ để kết luận', 'chưa thể khẳng định', 'cần xác minh thêm', 'chưa phải câu trả lời'. Hãy thể hiện sự cẩn trọng qua hành động, suy nghĩ và phản ứng tự nhiên của nhân vật thay vì đọc đi đọc lại câu rào đón.\n"
            f"11. GỌI TÊN NHÂN VẬT TỰ NHIÊN: Không lặp lại họ tên đầy đủ trong mọi câu. Sau khi giới thiệu ban đầu, hãy dùng đại từ nhân xưng tự nhiên ('anh', 'chị', 'ông', 'bà', 'cô', 'chú' hoặc gọi bằng tên riêng) để tạo sự gần gũi, ấm áp.\n"
            f"12. PHẦN KẾT CÔ ĐỌNG (5-10%): Không kéo dài bài học luân lý hay lặp lại thông điệp đạo lý nhiều lần. Khép lại câu chuyện bằng hình ảnh đời thường xúc động và lời chào ngắn gọn của MC Minh.\n"
            f"13. TÊN MINH CHỈ DÀNH CHO MC: Không được đặt tên hoặc mã MINH cho bất kỳ nhân vật nào trong câu chuyện.\n"
            f"14. KHÔNG KỂ LẠI: Mỗi hành động điều tra, cuộc gọi, cuộc gặp và phát hiện chỉ được kể một lần. Phần 2 phải nối đúng hành động cuối Phần 1, không khởi động lại một vòng điều tra.\n"
            f"15. KỶ LUẬT KẾT LUẬN: Lời đồn và dấu hiệu mơ hồ chỉ tạo nghi ngờ. Lời thừa nhận trực tiếp có thể xác nhận hành vi ngoại tình của chính người nói; không dùng nó để kết luận huyết thống hay tội phạm. Không bịa thêm giấy tờ tự tố cáo.\n"
            f"16. TRÁCH NHIỆM NHÂN VẬT: Bối cảnh hôn nhân giải thích hoàn cảnh nhưng không biến sự xa cách của người bị phản bội thành nguyên nhân hoặc lỗi cho lựa chọn nói dối/ngoại tình của người kia.\n"
            f"17. CÂU TIẾNG VIỆT HOÀN CHỈNH: Mỗi phân đoạn phải đúng chủ-vị, đúng người đang cảm xúc; cấm câu gãy như 'còn Mai thì.' hoặc ghép sai kiểu 'đau lòng vào tim Tuấn'.\n"
            f"18. KHÔNG CHÉP STORY BIBLE: Không nối nguyên văn các trường cause/decision/action/consequence/why/motivation/how thành lời đọc. Hãy chuyển chúng thành cảnh, hành động hoặc đối thoại tự nhiên.\n"
            f"19. HUYẾT THỐNG: Không kết luận đứa trẻ không phải con của chồng nếu chưa kể rõ xét nghiệm ADN hoặc mốc tuổi thai/thụ thai được đối chiếu. Lời thú nhận đơn độc chỉ tạo nghi vấn.\n"
            f"20. PHÁP LÝ GIA ĐÌNH: Không viết 'văn bản từ bỏ quyền làm cha' hay thủ tục tức thời tự chế. Nếu cần, nhân vật chỉ nói sẽ nhờ luật sư/tòa án giải quyết việc ly hôn và xác định cha con."
            + "\n\n" + voice_reference_block() + "\n\n"
            + writer_rules_block(21)
        )

        # ---------------- PART 1: ACTS 1 to 5 (~40 to 50 Segments) ----------------
        # Use pre-attached scene outline if present; otherwise fallback writer will build it.
        scene_outline = getattr(story_bible, "scene_outline", None)

        # One call writes the whole episode as tagged lines: no Part 1 / Part 2
        # seam to retell scenes across. Falls back to the two-call writer below
        # when the reply is truncated or malformed.
        actual_strategy = "single_pass"
        combined_data, in_tok1, out_tok1 = write_single_pass(
            lambda system, prompt: self._call_generate_content(
                prompt=prompt, model=model, response_json=False, system_instruction=system,
                temperature=0.8, thinking_budget=2048,
            ),
            system_instruction,
            build_single_pass_prompt(
                clean_title or story_bible.title, canonical_story, user_topic_constraint, host_name, scenes=scene_outline
            ),
            ending=story_bible.ending,
        )
        in_tok2 = out_tok2 = 0
        if combined_data is None:
            actual_strategy = "two_pass_seamed"
            if not scene_outline:
                scene_outline = build_scene_outline(
                    story_bible, lambda system, prompt: self.complete_json(system, prompt, model=model)
                )
            prompt_part1 = f"""Hãy viết PHẦN 1 cho kịch bản câu chuyện: '{clean_title}'.
    Mục tiêu độ dài Phần 1: Khoảng 1.200 - 1.500 từ tiếng Việt, triển khai tự nhiên khoảng 40 - 50 phân đoạn.
    STORY BIBLE ĐẦY ĐỦ (nguồn chuẩn cho danh tính, thời gian, nguồn bằng chứng và kết thúc; chỉ kể những gì nhân vật biết tại từng thời điểm):
    {canonical_story}
    {user_topic_constraint}
    Thông tin Story Bible:
    - Nhân vật chính: {protag_name} ({story_bible.protagonist.get('age', 30) if isinstance(story_bible.protagonist, dict) else 30} tuổi) - {story_bible.protagonist.get('description', '') if isinstance(story_bible.protagonist, dict) else ''}
    - Nhân vật phụ (CHỈ ĐƯỢC DÙNG CÁC TÊN NÀY):
    {supporting_summary}
    - Quan hệ: {story_bible.relationships}
    - Bí mật cốt lõi: {story_bible.secret}
    - Câu hỏi bí ẩn: {story_bible.mystery_question}
    - Giả thuyết sai ban đầu: {story_bible.false_lead}
    - Chuỗi manh mối có cấu trúc (mỗi manh mối chỉ chứng minh trong giới hạn what_it_proves, KHÔNG nhảy cóc sang kết luận cuối; thể hiện giới hạn đó qua hành động kiểm chứng của nhân vật, KHÔNG viết câu rào đón hay câu phân tích kiểu 'manh mối này chứng minh…'):
    {clues_summary}
    - Sổ cái nhận thức nhân vật (Knowledge Ledger):
    {knowledge_summary}
    - Các sự thật đóng băng (Fact Lock - TUYỆT ĐỐI TUÂN THỦ, KHÔNG SỬA ĐỔI):
    {facts_summary}

    Cấu trúc Phân bổ Phần 1 (khoảng 40-50 phân đoạn):
    1. Act 1: HOOK (khoảng 5-6 phân đoạn đầu):
       - Phân đoạn 001-002: mở bằng một câu TRÍCH NGUYÊN VĂN từ lá thư trong ngoặc kép, hoặc một hành động/vật cụ thể; MC có thể nói phản ứng của mình và dẫn người nghe đoán theo hướng dễ đoán nhất; câu ngắn có nhịp như MẪU GIỌNG KỂ (delivery_profile='HOOK', speed=0.98). Không mở bằng câu triết lý. Tuyệt đối không kết luận trước sự thật ở Reveal.
       - Lời chào mở đầu chương trình của {host_name}: BẮT BUỘC mở đầu bằng "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa." (KHÔNG đọc số tập hay mã tập, delivery_profile='NORMAL', speed=1.01).
       - Giới thiệu nhân vật gửi thư và bước vào bối cảnh câu chuyện (delivery_profile='NORMAL', speed=1.01).
    2. Act 2: SETUP (khoảng 10-12 phân đoạn):
       - Đời sống thường nhật, bối cảnh gia đình/công việc, những chi tiết quan sát cụ thể trước khi phát hiện bất thường.
       - Chứa đúng 1 phân đoạn giao lưu khán giả gợi mở (audience_address=true, delivery_profile='COMMENT').
    3. Act 3: MYSTERY / FIRST ANOMALY (khoảng 10-12 phân đoạn):
       - Manh mối đầu tiên xuất hiện qua một CẢNH cụ thể (vật, câu nói, thời điểm). Nhân vật phản ứng rồi tự kiểm chứng bằng hành động (hỏi thử, đối chiếu, hẹn gặp); kết quả hành động đó vừa trấn an vừa để lại điểm lạ. Không kết luận sự thật cuối (delivery_profile='MYSTERY' và 'NORMAL').
       - Chứa đúng 1 phân đoạn giao lưu khán giả đặt câu hỏi giả thuyết (audience_address=true, delivery_profile='COMMENT').
    4. Act 4: ESCALATION (khoảng 8-10 phân đoạn):
       - Giả thuyết sai ban đầu (false lead) xuất hiện từ góc nhìn hạn chế của nhân vật chính (delivery_profile='NORMAL' và 'MYSTERY').
    5. Act 5: INVESTIGATION (khoảng 8-10 phân đoạn):
       - Nhân vật chính bắt đầu hành động xác minh. Mọi cảnh (cuộc gọi, cuộc gặp, lần đọc tài liệu) bắt đầu trong PHẦN 1 phải KẾT THÚC trong PHẦN 1.
       - Tuyệt đối không dùng REVEAL trong PHẦN 1 và không hoàn tất cuộc gặp/đối thoại sẽ mở đầu PHẦN 2.

    ĐIỂM DỪNG BẮT BUỘC CỦA PHẦN 1:
    - Dừng ở CUỐI một cảnh trọn vẹn và để lại một câu hỏi mở cho PHẦN 2. KHÔNG dừng giữa một cuộc trò chuyện, vì PHẦN 2 sẽ phải kể lại nó.
    - KHÔNG tiết lộ đáp án cuối, KHÔNG giải quyết xung đột, KHÔNG đúc kết bài học, KHÔNG cảm ơn thính giả và KHÔNG chào tạm biệt.
    - Không một object nào trong PHẦN 1 được dùng delivery_profile='ENDING'.

    Yêu cầu định dạng JSON:
    Trả về JSON Array gồm các objects từ id '001' trở đi (khoảng 40-50 phân đoạn tự nhiên):
    [
      {{
        "id": "001",
        "speaker": "{host_id}",
        "text": "Lời dẫn tiếng Việt tự nhiên, điềm đạm, cụ thể, 1-3 câu, khoảng 15-40 từ, câu ngắn có nhịp...",
        "delivery_profile": "HOOK",
        "importance": "high",
        "audience_address": false,
        "speed": 0.98
      }}
    ]
    """
            prompt_part1 += outline_block(scene_outline, 1)
            raw_p1, in_tok1, out_tok1 = self._call_generate_content(
                prompt=prompt_part1,
                model=model or self.default_model,
                response_json=True,
                system_instruction=system_instruction,
            )

            p1_data = _parse_script_segment_array(raw_p1)
            if not p1_data or _part_has_closure(p1_data) or _part_has_premature_reveal(p1_data):
                retry_prompt = prompt_part1 + """

    YÊU CẦU SỬA BẮT BUỘC: Kết quả trước đã khép lại câu chuyện quá sớm hoặc sai định dạng.
    Hãy viết lại TOÀN BỘ PHẦN 1. Không dùng ENDING hoặc REVEAL, không có lời cảm ơn/lời chào, không giải quyết bí mật.
    Phân đoạn cuối phải là một hành động xác minh đang tiếp diễn để PHẦN 2 nối tiếp ngay.
    """
                raw_retry, retry_in, retry_out = self._call_generate_content(
                    prompt=retry_prompt,
                    model=model or self.default_model,
                    response_json=True,
                    system_instruction=system_instruction,
                )
                in_tok1 += retry_in
                out_tok1 += retry_out
                p1_data = _parse_script_segment_array(raw_retry)
            if not p1_data:
                raise RuntimeError("Gemini returned an empty or invalid Part 1 script.")
            if _part_has_closure(p1_data) or _part_has_premature_reveal(p1_data):
                raise RuntimeError("Gemini Part 1 still contains a premature reveal/ending after retry; script rejected.")

            time.sleep(2)

            # ---------------- PART 2: ACTS 5 (cont) to 9 (~40 to 50 Segments) ----------------
            p1_context = "\n".join(
                f"[{s.get('id')}] {str(s.get('text', ''))}"
                for s in p1_data
                if isinstance(s, dict)
            )
            p1_count = len(p1_data)
            next_start_id = p1_count + 1

            prompt_part2 = f"""Hãy viết tiếp PHẦN 2 cho kịch bản câu chuyện: '{clean_title}'.
    Mục tiêu độ dài Phần 2: Khoảng 1.200 - 1.600 từ tiếng Việt, triển khai tự nhiên khoảng 40 - 50 phân đoạn tiếp theo.
    STORY BIBLE ĐẦY ĐỦ (nguồn chuẩn cho danh tính, thời gian, nguồn bằng chứng và kết thúc; chỉ kể những gì nhân vật biết tại từng thời điểm):
    {canonical_story}

    BẢN ĐỒ TOÀN BỘ NỘI DUNG ĐÃ KỂ Ở PHẦN 1 (tổng cộng {p1_count} phân đoạn):
    {p1_context}

    KỶ LUẬT NỐI MẠCH:
    - Phân đoạn đầu PHẦN 2 phải là hành động/cảnh MỚI. Không nhắc lại vật, địa điểm hay quyết định đã có trong 3 phân đoạn cuối PHẦN 1.
    - Tiếp tục trực tiếp từ hành động cuối của PHẦN 1. Không mở đầu lại câu chuyện, không giới thiệu lại nhân vật và không kể lại dấu hiệu/manh mối đã có trong bản đồ trên.
    - Mỗi chứng cứ cũ chỉ được nhắc lại rất ngắn khi nó dẫn thẳng tới một phát hiện mới; tuyệt đối không dựng lại một vòng điều tra thứ hai.
    - Chỉ giải quyết câu chuyện ở Act 8 và chỉ chào kết đúng một lần ở object cuối cùng của PHẦN 2.

    Nội dung Bước ngoặt, Chuỗi Nhân Quả & Hóa giải cảm xúc của Story Bible:
    - Bước ngoặt 1 (Reveal 1): {story_bible.reveal_1}
    - Bước ngoặt 2 (Reveal 2): {story_bible.reveal_2}
    - Chuỗi nhân quả (CHỈ ĐỂ BẠN HIỂU, KHÔNG ĐỌC LẠI; chỉ thể hiện qua lời thú nhận, nhân chứng hoặc tài liệu nhân vật chính thấy):
    {causal_summary}
    - Căn cứ bắt buộc cho các Reveal (phải kể thành diễn biến tự nhiên, không chép nguyên trường dữ liệu):
    {reveal_proof_summary}
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
    {ACT7_CAUSAL_INSTRUCTION}
       - Tuân thủ chặt chẽ Knowledge Ledger: không viết "không ai biết / kể cả người vợ" nếu trong truyện có người thân biết sự thật.
       - BẮT BUỘC: audience_address=false. Các phân đoạn mở nút thắt chính dùng delivery_profile='REVEAL' (speed=0.92), các phân đoạn giải thích hoàn cảnh dùng delivery_profile='NORMAL'.
    4. Act 8: EMOTIONAL PAYOFF & RESOLUTION (6-8 phân đoạn, giải quyết bằng hành động và lời thoại, không kể lể hậu quả dài dòng; giữ nhất quán nơi ở/hoàn cảnh sau quyết định):
       - Cuộc đối thoại trực tiếp, hành động cụ thể, cử chỉ đời thường khi các nhân vật đối diện và tháo gỡ khúc mắc (delivery_profile='NORMAL').
       - Chứa đúng 1 phân đoạn giao lưu khán giả (audience_address=true, delivery_profile='COMMENT').
    5. Act 9: CONCISE REFLECTION + SIGN-OFF (khoảng 4-6 phân đoạn cuối, KHÔNG LẶP Ý):
       - GIỚI HẠN CỨNG: sau cảnh giải quyết cuối cùng, phần kết TỐI ĐA 5 phân đoạn (gồm cả lời chào). Không cảm ơn nhiều lần, không chuỗi phân đoạn giảng đạo.
       - Hình ảnh khép lại câu chuyện của gia đình nhân vật bằng chi tiết đời thực lắng đọng (delivery_profile='NORMAL', audience_address=false).
       - ĐÚNG 1 phân đoạn duy nhất đúc kết bài học chiêm nghiệm từ câu chuyện (delivery_profile='COMMENT', audience_address=false).
       - ĐÚNG 1 câu hỏi gợi suy ngẫm gửi tới thính giả (delivery_profile='COMMENT', audience_address=true).
       - Lời cảm ơn người gửi thư, cảm ơn thính giả và lời chào tạm biệt ngắn gọn của {host_name}: 'Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.' (delivery_profile='ENDING', speed=0.965, audience_address=false).

    Yêu cầu định dạng JSON:
    Trả về JSON Array gồm các objects từ id '{next_start_id:03d}' trở đi:
    [
      {{
        "id": "{next_start_id:03d}",
        "speaker": "{host_id}",
        "text": "Lời dẫn tiếng Việt tự nhiên, điềm đạm, 1-3 câu, khoảng 15-40 từ, câu ngắn có nhịp...",
        "delivery_profile": "MYSTERY",
        "importance": "normal",
        "audience_address": false,
        "speed": 0.96
      }}
    ]
    """
            prompt_part2 += outline_block(scene_outline, 2)
            raw_p2, in_tok2, out_tok2 = self._call_generate_content(
                prompt=prompt_part2,
                model=model or self.default_model,
                response_json=True,
                system_instruction=system_instruction,
            )

            p2_data = _parse_script_segment_array(raw_p2)
            if not _has_one_final_signoff(p1_data + p2_data) or has_repeated_narrative_block(p1_data + p2_data):
                retry_prompt = prompt_part2 + """

    YÊU CẦU SỬA BẮT BUỘC: Kết quả trước có lời chào sai vị trí hoặc kể lại một chuỗi sự kiện đã có trong PHẦN 1.
    Hãy viết lại TOÀN BỘ PHẦN 2. Chỉ object cuối cùng được dùng delivery_profile='ENDING' và chứa đúng một lời chào chuẩn.
    Mọi object trước đó không được cảm ơn thính giả hoặc chào tạm biệt. Nối trực tiếp hành động cuối PHẦN 1 và không lặp cuộc gọi, cuộc gặp, manh mối hay phát hiện cũ.
    """
                raw_retry, retry_in, retry_out = self._call_generate_content(
                    prompt=retry_prompt,
                    model=model or self.default_model,
                    response_json=True,
                    system_instruction=system_instruction,
                )
                in_tok2 += retry_in
                out_tok2 += retry_out
                p2_data = _parse_script_segment_array(raw_retry) or p2_data
            if not p2_data:
                raise RuntimeError("Gemini returned an empty or invalid Part 2 script.")
            if not _has_one_final_signoff(p1_data + p2_data):
                logger.warning("[Gemini] Part 2 sign-off misplaced after retry; normalizing the closing segment.")
                p2_data = _normalize_final_signoff(p2_data)
            if has_repeated_narrative_block(p1_data + p2_data):
                # Script QC flags REPEATED_NARRATIVE_BLOCK and auto-repair cuts the
                # duplicate, so keep the script instead of discarding the whole run.
                logger.warning("[Gemini] Part 2 still repeats a Part 1 block after retry; leaving it to QC auto-repair.")

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
            prompt_version="script-v3.6-scene-outline-grounded",
            generation_source="REAL_AI",
            model_name=chosen_model_name,
            requested_model=model or self.default_model,
            actual_model=chosen_model_name,
            writer_strategy=actual_strategy,
            scene_outline=scene_outline,
            provider_name="GeminiScriptAIProvider",
            created_at=time.time(),
            updated_at=time.time(),
        )
        return script, in_tok1 + in_tok2, out_tok1 + out_tok2

    def complete_json(self, system_instruction: str, prompt: str, model: Optional[str] = None) -> Tuple[str, int, int]:
        """Single JSON completion used by QC review and segment rewriting."""
        # Review and targeted rewrites need careful reading more than variety.
        # Stick to the model that last judged this job: different models grade
        # differently, so switching judges between repair rounds stops QC from
        # converging. The chain still falls back if that model becomes unusable.
        result = self._call_generate_content(
            prompt=prompt, model=model or self._sticky_review_model or None, response_json=True,
            system_instruction=system_instruction, temperature=0.2, thinking_budget=4096, allow_lite_models=False,
        )
        self._sticky_review_model = self.last_used_model
        return result

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
        """Performs targeted script revisions to resolve QC issues without hardcoded sentence injection."""
        from apps.script_factory.segment_rewriter import revise_with_ai

        return revise_with_ai(
            script, story_bible, qc_report,
            lambda system, prompt: self.complete_json(system, prompt, model=model),
        )
