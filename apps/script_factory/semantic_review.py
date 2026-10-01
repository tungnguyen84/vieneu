"""LLM story-logic and natural storytelling review for scripts.

Regex QC catches wording; it cannot tell that a narrator reports another
character's private motives, or that a DNA test was run without the mother's
sample. This review asks a model to read the whole script against
``NARRATIVE_LOGIC_RULES`` and return only issues it can anchor to an exact quote.
Quotes that do not appear verbatim in the cited segment are discarded, which
keeps hallucinated findings out of the QC verdict.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, StoryBible
from apps.script_factory.narrative_rules import LOGIC_RULE_CODES, reviewer_checklist
from apps.script_factory.segment_rewriter import parse_json_items, parse_json_items_validated

logger = logging.getLogger("VieNeu.SemanticReview")

# call_llm(system_instruction, prompt) -> (raw_text, input_tokens, output_tokens)
LLMCall = Callable[[str, str], Tuple[str, int, int]]

SYSTEM_INSTRUCTION = (
    "Bạn là biên tập viên kiểm định chất lượng kịch bản audio tiếng Việt 'Sau Cánh Cửa' (MC Minh kể chuyện). "
    "Bạn kiểm tra logic cốt truyện, tính tự nhiên của lời kể và sự nhất quán chi tiết theo đúng danh sách quy tắc được cấp. "
    "Mọi lỗi báo cáo phải có trích dẫn NGUYÊN VĂN từ kịch bản. Nếu không chắc, không báo. Chỉ trả về JSON."
)


def script_content_hash(script: Any) -> str:
    """Stable hash of script segments (id, text, speed, delivery_profile)."""
    if hasattr(script, "segments"):
        raw_segs = script.segments
    elif isinstance(script, dict):
        raw_segs = script.get("segments") or []
    else:
        raw_segs = []

    core = []
    for s in raw_segs:
        if isinstance(s, dict):
            core.append({
                "id": str(s.get("id") or s.get("segment_id") or ""),
                "text": str(s.get("text", "")).strip(),
                "speed": float(s.get("speed") or s.get("speed_ratio") or 1.0),
                "delivery_profile": str(s.get("delivery_profile", "")).upper(),
            })
        elif hasattr(s, "id"):
            core.append({
                "id": str(s.id),
                "text": str(s.text).strip(),
                "speed": float(getattr(s, "speed", 1.0) or 1.0),
                "delivery_profile": str(getattr(s, "delivery_profile", "")).upper(),
            })

    encoded = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold().strip(" .,…'\"“”")


def _quote_in_text(quote: str, text: str) -> bool:
    """True when every ellipsis-separated fragment of ``quote`` occurs in ``text``."""
    haystack = _normalize(text)
    fragments = [f for f in re.split(r"\.\.\.|…", quote) if len(f.split()) >= 3]
    return bool(fragments) and all(_normalize(f) in haystack for f in fragments)


def build_prompt(script: FullScript, story_bible: StoryBible) -> str:
    protagonist = story_bible.protagonist if isinstance(story_bible.protagonist, dict) else {}
    numbered = "\n".join(f"[{s.id}] {s.text}" for s in script.segments)
    return (
        f"Nhân vật gửi thư (góc nhìn duy nhất): {protagonist.get('name') or story_bible.protagonist}\n\n"
        f"Bộ luật cần kiểm tra:\n{reviewer_checklist()}\n\n"
        f"Kịch bản (mỗi dòng là một phân đoạn có id):\n{numbered}\n\n"
        "Cách làm: đọc lần lượt từng phân đoạn và đối chiếu với TỪNG luật:\n"
        "1. POV & Logic: người kể có tự thuật nội tâm/động cơ của nhân vật khác không; có kết luận sớm trước bằng chứng không; vật chứng có phi thực tế không.\n"
        "2. Hook mở đầu: đoạn đầu tiên [001] có mở bằng triết lý chung chung sáo rỗng không (phải mở bằng nhân vật/hành động/vật cụ thể).\n"
        "3. Tính nhất quán đồ vật: đạo cụ, hiện vật có bị mâu thuẫn giữa các đoạn không.\n"
        "4. Giọng kể: có bị mang giọng văn 'báo cáo kiểm tra QC' (như lặp 'chỉ chứng minh... hoàn toàn không chứng minh...') hay câu cú gãy, dị thường không.\n\n"
        "Trả về JSON:\n"
        '{"issues": [{"rule": "<mã luật ở trên>", "segment_id": "<id chứa câu sai>", '
        '"related_segment_ids": ["<id liên quan nếu có>"], '
        '"quote": "<trích NGUYÊN VĂN 6-30 từ từ phân đoạn segment_id>", '
        '"problem": "<giải thích ngắn vì sao sai>", '
        '"fix": "<cách sửa cụ thể, giữ nguyên cốt truyện>", "confidence": "high|medium"}]}\n'
        "Chỉ báo tối đa 12 lỗi quan trọng nhất. Nếu kịch bản không có lỗi, trả về {\"issues\": []}."
    )


def review_script_logic(
    script: FullScript,
    story_bible: StoryBible,
    call_llm: LLMCall,
) -> Dict[str, Any]:
    """Returns {"issues": [...blocking...], "advisories": [...], "script_hash", "tokens"}."""
    raw, in_tok, out_tok = call_llm(SYSTEM_INSTRUCTION, build_prompt(script, story_bible))
    items, is_valid, err_msg = parse_json_items_validated(raw, "issues")
    if not is_valid:
        logger.warning(f"[SemanticReview] Model response invalid JSON: {err_msg}. Raw: {raw[:200]}")
        return {
            "status": "ERROR",
            "error": f"Mô hình không trả về JSON hợp lệ: {err_msg}",
            "dropped_unanchored": 0,
            "script_hash": script_content_hash(script),
            "issues": [],
            "advisories": [],
            "tokens": [in_tok, out_tok],
        }

    by_id = {s.id: s for s in script.segments}
    blocking: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []
    dropped = 0
    for item in items:
        rule = str(item.get("rule", "")).strip().upper()
        seg_id = str(item.get("segment_id", "")).strip()
        quote = str(item.get("quote", "")).strip()
        segment = by_id.get(seg_id)
        if rule not in LOGIC_RULE_CODES or segment is None or len(quote.split()) < 4:
            dropped += 1
            continue
        if not _quote_in_text(quote, segment.text):
            dropped += 1
            continue
        related = [
            str(r).strip() for r in (item.get("related_segment_ids") or [])
            if str(r).strip() in by_id and str(r).strip() != seg_id
        ]
        confident = str(item.get("confidence", "")).lower() == "high"
        issue = {
            "segment_id": seg_id,
            "related_segment_ids": related,
            "excerpt": quote[:160],
            "rule": rule,
            "severity": "CRITICAL" if confident else "MEDIUM",
            "source": "SEMANTIC_REVIEW",
            "message": f"Phân đoạn [{seg_id}] vi phạm {rule}: {str(item.get('problem', '')).strip()}",
            "recommended_action": str(item.get("fix", "")).strip(),
        }
        (blocking if confident else advisories).append(issue)
    if dropped:
        logger.info(f"[SemanticReview] {script.episode_id}: dropped {dropped} unanchored findings")
    return {
        "status": "RUN",
        "dropped_unanchored": dropped,
        "script_hash": script_content_hash(script),
        "issues": blocking,
        "advisories": advisories,
        "tokens": [in_tok, out_tok],
    }


def carry_over_semantic_review(previous_report: Dict[str, Any], script: FullScript) -> Optional[Dict[str, Any]]:
    """Reuses a previous semantic review when the script text has not changed."""
    review = previous_report.get("semantic_review") if isinstance(previous_report, dict) else None
    if isinstance(review, dict) and review.get("script_hash") == script_content_hash(script):
        return review
    return None


# ---------------------------------------------------------------------------
# Story Bible review: catch plot designs the script writer cannot tell honestly
# (a reveal only the antagonist's mind could know, an illegal ending, a
# paternity verdict without a test) before any script is written from them.
# ---------------------------------------------------------------------------

STORY_BIBLE_REVIEW_FIELDS = (
    "secret", "false_lead", "clues", "structured_clues", "reveal_1", "reveal_2",
    "causal_chains", "reveal_justifications", "knowledge_ledger", "emotional_payoff", "ending",
)

STORY_BIBLE_HASH_FIELDS = (
    *STORY_BIBLE_REVIEW_FIELDS,
    "protagonist", "supporting_characters", "timeline", "facts", "critical_facts", "relationships", "premise"
)

# Rules about how a scene is narrated (order, repetition, wording) only exist
# once there is a script; the Story Bible is judged on design-level logic.
STORY_BIBLE_RULES = (
    "POV_KNOWLEDGE_VIOLATION",
    "INFEASIBLE_EVIDENCE",
    "CONCLUSION_BEFORE_PROOF",
    "UNRESOLVED_SETUP",
    "LEGAL_OR_MEDICAL_UNREALISTIC",
    "IMPLAUSIBLE_BEHAVIOR",
)

# Only these rules block Story Bible approval when flagged with high confidence.
STORY_BIBLE_BLOCKING_RULES = {
    "INFEASIBLE_EVIDENCE",
    "LEGAL_OR_MEDICAL_UNREALISTIC",
    "POV_KNOWLEDGE_VIOLATION",
}

# In Story Bible, these fields are the writer's reference for the true causal
# chain. A reveal whose motivation is explained in causal_chains is sound, not
# a POV violation. Only report POV if a reveal/ending has no grounded revelation
# channel (e.g. no confession, no document, no witness, no test).
STORY_BIBLE_BACKSTAGE_FIELDS = {
    "secret", "causal_chains", "knowledge_ledger", "reveal_justifications",
}

STORY_BIBLE_SYSTEM_INSTRUCTION = (
    "Bạn là biên tập viên kiểm định logic cốt truyện cho series 'Sau Cánh Cửa'. Câu chuyện sẽ được kể như lá thư "
    "của nhân vật chính gửi về chương trình. Bạn kiểm tra thiết kế Story Bible có kể được một cách trung thực "
    "từ góc nhìn đó hay không. Chỉ báo lỗi thật, có trích dẫn nguyên văn. Chỉ trả về JSON."
)


def story_bible_content_hash(bible: StoryBible) -> str:
    data = bible.to_dict()
    payload = json.dumps({k: data.get(k) for k in STORY_BIBLE_HASH_FIELDS}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_story_bible_prompt(bible: StoryBible) -> str:
    data = bible.to_dict()
    protagonist = bible.protagonist if isinstance(bible.protagonist, dict) else {}
    plot = {k: data.get(k) for k in STORY_BIBLE_REVIEW_FIELDS if data.get(k)}
    return (
        f"Nhân vật gửi thư (góc nhìn duy nhất): {protagonist.get('name') or bible.protagonist}\n\n"
        "Bộ luật logic cần kiểm tra (CHỈ các luật này):\n"
        + reviewer_checklist(STORY_BIBLE_RULES) + "\n\n"
        "Lưu ý: các trường secret, causal_chains, knowledge_ledger, reveal_justifications là SỰ THẬT HẬU TRƯỜNG "
        "cho người viết, không được đọc lên, nên KHÔNG áp dụng POV_KNOWLEDGE_VIOLATION cho chúng và không coi là kết luận sớm. "
        "Chỉ báo POV khi một reveal/ending đưa ra điều nhân vật chính không thể biết và Story Bible không có kênh tiết lộ nào. "
        "Cách sửa phải GIỮ cú lật mạnh và rõ ràng, bằng cách bổ sung kênh tiết lộ cụ thể (lời thú nhận trực tiếp, "
        "xét nghiệm có mẫu hợp lệ, tài liệu nhân vật chính đọc được), TUYỆT ĐỐI không làm mờ reveal thành nghi vấn chung chung.\n\n"
        "Kiểm tra thêm: mỗi reveal phải là điều nhân vật chính có thể BIẾT được qua một kênh cụ thể ghi trong "
        "Story Bible (lời thú nhận, nhân chứng, tài liệu, xét nghiệm). Reveal chỉ là suy nghĩ/động cơ/sự bất cẩn "
        "của nhân vật khác mà không có kênh tiết lộ là lỗi POV_KNOWLEDGE_VIOLATION.\n\n"
        f"Story Bible (các trường cốt truyện):\n{json.dumps(plot, ensure_ascii=False, indent=1)}\n\n"
        "Trả về JSON:\n"
        '{"issues": [{"rule": "<mã luật>", "field": "<tên trường ở trên>", '
        '"quote": "<trích NGUYÊN VĂN 5-30 từ từ trường đó>", "problem": "<vì sao sai>", '
        '"fix": "<cách sửa cụ thể trong Story Bible, giữ nguyên chủ đề>", "confidence": "high|medium"}]}\n'
        "Tối đa 8 lỗi quan trọng nhất. Không có lỗi thì trả về {\"issues\": []}."
    )


def review_story_bible_logic(bible: StoryBible, call_llm: LLMCall) -> Dict[str, Any]:
    """Returns {"issues": [...high confidence...], "advisories": [...], "bible_hash"}."""
    raw, in_tok, out_tok = call_llm(STORY_BIBLE_SYSTEM_INSTRUCTION, build_story_bible_prompt(bible))
    items, is_valid, err_msg = parse_json_items_validated(raw, "issues")
    if not is_valid:
        logger.warning(f"[SemanticReview] Story Bible review invalid JSON: {err_msg}")
        return {
            "status": "ERROR",
            "error": f"Story Bible review JSON invalid: {err_msg}",
            "bible_hash": story_bible_content_hash(bible),
            "issues": [],
            "advisories": [],
            "tokens": [in_tok, out_tok],
        }

    data = bible.to_dict()
    blocking: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []
    for item in items:
        rule = str(item.get("rule", "")).strip().upper()
        field_name = str(item.get("field", "")).strip()
        quote = str(item.get("quote", "")).strip()
        source = json.dumps(data.get(field_name), ensure_ascii=False) if field_name in STORY_BIBLE_REVIEW_FIELDS else ""
        if rule not in STORY_BIBLE_RULES or not source or not _quote_in_text(quote, source):
            continue
        issue = {
            "rule": rule,
            "target": field_name,
            "excerpt": quote[:160],
            "message": f"{str(item.get('problem', '')).strip()} Cách sửa: {str(item.get('fix', '')).strip()}",
            "source": "SEMANTIC_REVIEW",
        }
        if rule == "POV_KNOWLEDGE_VIOLATION" and field_name in STORY_BIBLE_BACKSTAGE_FIELDS:
            continue
        confident = str(item.get("confidence", "")).lower() == "high"
        (blocking if confident and rule in STORY_BIBLE_BLOCKING_RULES else advisories).append(issue)
    return {
        "status": "RUN",
        "bible_hash": story_bible_content_hash(bible),
        "issues": blocking,
        "advisories": advisories,
        "tokens": [in_tok, out_tok],
    }
