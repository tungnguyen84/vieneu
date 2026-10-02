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
from apps.script_factory.narrative_rules import is_blocking_logic_issue, LOGIC_RULE_CODES, reviewer_checklist
from apps.script_factory.segment_rewriter import clean_segment_id, parse_json_items, parse_json_items_validated

logger = logging.getLogger("VieNeu.SemanticReview")

# call_llm(system_instruction, prompt) -> (raw_text, input_tokens, output_tokens)
LLMCall = Callable[[str, str], Tuple[str, int, int]]
SEMANTIC_REVIEW_VERSION = "semantic-v9-unified-policy"

REVIEW_CALIBRATION = (
    "NGƯỠNG BÁO LỖI: chỉ báo mâu thuẫn hoặc thiếu mắt xích làm người nghe không hiểu được sự kiện, "
    "không biến sở thích văn phong thành lỗi CRITICAL. Đọc cả đoạn trước/sau và toàn bộ Bible trước khi kết luận. "
    "Nhân vật thông minh vẫn có thể bất cẩn: để quên biên lai trong túi áo không tự nó là hành vi phi lý; "
    "chỉ báo IMPLAUSIBLE_BEHAVIOR khi hành động trái với điều kiện cụ thể đã được đặt ra. "
    "UNRESOLVED_SETUP chỉ dành cho nút thắt/chứng cứ/đáp án đã hứa nhưng bỏ lửng; một món quà thể hiện "
    "sự thân mật đã được giải thích bởi quan hệ ngoại tình không cần thêm cảnh giải thích món quà. "
    "TIẾN TRÌNH TRINH THÁM & MANH MỐI: Manh mối phát hiện ở phần đầu (như bức ảnh người lạ, mạng Wi-Fi bí ẩn, khuy măng sét) "
    "được phép là bí ẩn chưa có câu trả lời ngay lúc đó; chúng sẽ được nhân vật đối chiếu, giải mã hoặc xác nhận danh tính "
    "ở các cảnh Reveal/Payoff phía sau. TUYỆT ĐỐI KHÔNG báo UNRESOLVED_SETUP khi chi tiết đã được giải đáp ở phần sau của câu chuyện; "
    "và KHÔNG đòi hỏi nhân vật phải biết hoặc đối chiếu danh tính ngay tại phân đoạn phát hiện ban đầu (điều đó sẽ vi phạm REVEAL_LEAKED_EARLY).\n\n"
    "Nhận định 'thao túng' sau lời đe dọa cụ thể mà nhân vật đã đọc/nghe không phải biết nội tâm bí mật. "
    "Không tự thêm giả định ngoài văn bản để tạo lỗi. Lời thừa nhận của người trong cuộc có thể xác nhận "
    "việc họ ngoại tình; nó không thay được xét nghiệm huyết thống hoặc kết luận của cơ quan pháp luật.\n\n"
    "Phân biệt KHẢ NĂNG với PHÁN QUYẾT: 'có thể gặp rắc rối pháp lý', 'nguy cơ bị truy tố' sau bằng chứng "
    "về gian lận chỉ nêu khả năng, không khẳng định có bản án hay quyết định truy tố. Không đòi thông báo chính thức "
    "cho một nhận định thận trọng như vậy. Vẫn báo lỗi nếu kể việc bắt giữ/phán quyết đã xảy ra mà thiếu căn cứ. "
    "Cảm xúc thể hiện qua cuộc gặp và hành động (kiên cường, đau đớn, giữ kiêu hãnh) không tự nó là biết "
    "một bí mật nội tâm. Chỉ chặn POV khi khẳng định một kế hoạch, sự kiện hoặc ý định kín chưa được tiết lộ.\n\n"
)

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
                "speaker": str(s.get("speaker") or "MINH"),
                "pause_before": float(s.get("pause_before", 0.05) or 0.0),
                "pause_after": float(s.get("pause_after", 0.25) if s.get("pause_after", 0.25) is not None else 0.25),
            })
        elif hasattr(s, "id"):
            core.append({
                "id": str(s.id),
                "text": str(s.text).strip(),
                "speed": float(getattr(s, "speed", 1.0) or 1.0),
                "delivery_profile": str(getattr(s, "delivery_profile", "")).upper(),
                "speaker": str(getattr(s, "speaker", None) or "MINH"),
                "pause_before": float(getattr(s, "pause_before", 0.0) or 0.0),
                "pause_after": float(getattr(s, "pause_after", 0.25) if getattr(s, "pause_after", 0.25) is not None else 0.25),
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


def _retry_review_once(result: Dict[str, Any], retry: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    logger.warning('[SemanticReview] Review output invalid; retrying once without changing the creative artifact')
    repaired = retry()
    repaired['tokens'] = [a + b for a, b in zip(result.get('tokens', [0, 0]), repaired.get('tokens', [0, 0]))]
    repaired['review_retries'] = repaired.get('review_retries', 0) + 1
    return repaired


def build_prompt(script: FullScript, story_bible: StoryBible) -> str:
    protagonist = story_bible.protagonist if isinstance(story_bible.protagonist, dict) else {}
    numbered = "\n".join(f"[{s.id}] {s.text}" for s in script.segments)
    skeleton = story_bible.narrative_skeleton if isinstance(story_bible.narrative_skeleton, dict) else {}
    trigger_text = str(skeleton.get("trigger", "") or "").strip()
    return (
        f"Nhân vật gửi thư (góc nhìn duy nhất): {protagonist.get('name') or story_bible.protagonist}\n\n"
        f"Bộ luật cần kiểm tra:\n{reviewer_checklist()}\n\n"
        f"Tiêu đề kịch bản: {script.title}\n"
        f"Tiêu đề Story Bible: {story_bible.title}\n"
        f"Trigger mở đầu (Narrative Skeleton): {trigger_text}\n"
        "ĐỊNH DẠNG MC: lời chào chương trình, giới thiệu lá thư, bình luận và câu hỏi giao lưu của MC "
        "được phép nằm ngoài góc nhìn Hoa/Tuấn/người gửi thư. Chúng không tự nó là lỗi POV hay analyst narration. "
        "Chỉ đánh giá góc nhìn hạn chế khi kể các SỰ KIỆN trong câu chuyện. Một nhân chứng nói 'có vẻ', 'có thể' "
        "là nhận định có chủ thể, không phải khẳng định biết một kế hoạch kín.\n"
        + REVIEW_CALIBRATION
        +
        f"Story Bible (tài liệu hậu trường, không phải lời kể):\n{json.dumps(story_bible.to_dict(), ensure_ascii=False)}\n\n"
        f"Kịch bản (mỗi dòng là một phân đoạn có id):\n{numbered}\n\n"
        "Cách làm: đọc lần lượt từng phân đoạn và đối chiếu với TỪNG luật:\n"
        "1. POV & Logic: người kể có tự thuật nội tâm/động cơ của nhân vật khác không; có kết luận sớm trước bằng chứng không; vật chứng có phi thực tế không.\n"
        "2. Hook mở đầu & Timeline: đoạn đầu tiên [001] có mở bằng triết lý chung chung không (phải mở bằng nhân vật/hành động/vật cụ thể). "
        "Mốc thời gian và địa điểm phát hiện manh mối ở Hook (ví dụ 'tối hôm ấy' vs 'sáng hôm sau') PHẢI KHỚP với cảnh phát hiện thực tế trong thân truyện (TIMELINE_ORDER_ERROR).\n"
        "3. Tính nhất quán đồ vật & Trạng thái (OBJECT_CONTINUITY_CONTRADICTION): theo dõi AI đang giữ đồ vật, vị trí đồ vật. "
        "Khi một vật đã được lấy ra khỏi túi/xe/ngăn kéo và đặt lên bàn/kệ, các cảnh sau KHÔNG được kể như thể vật đó vẫn đang nằm trong túi/xe nếu không có hành động cất trở lại.\n"
        "4. Giọng kể: có bị mang giọng văn 'báo cáo kiểm tra QC' (như lặp 'chỉ chứng minh... hoàn toàn không chứng minh...') hay câu cú gãy, dị thường không.\n\n"
        "5. Lập tiến trình nội bộ theo từng cảnh: nhân vật ở đâu, đã mở/đọc/gặp gì, biết điều gì từ bằng chứng nào. "
        "Đối chiếu từng câu với trạng thái trước: tìm hành động xảy ra trước điều kiện và trạng thái hiểu biết bị quay lùi. "
        "Không tự đưa suy luận của người đọc thành điều nhân vật đã biết. Nếu có lỗi giữa hai đoạn, ghi related_segment_ids và trích đoạn sai.\n"
        "6. Đọc như người nghe audio: các cảnh phát hiện, đối chất, kết thúc có chi tiết thật hay chỉ tóm tắt? "
        "Không chứng nhận PASS chỉ vì đủ số từ, đủ phân đoạn hoặc có hai REVEAL.\n\n"
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
    _continuity_pass: bool = False,
    _retry_invalid: bool = False,
) -> Dict[str, Any]:
    """Returns {"issues": [...blocking...], "advisories": [...], "script_hash", "tokens"}."""
    prompt = build_prompt(script, story_bible)
    if _retry_invalid:
        prompt += '\nLượt trước có finding không hợp lệ. Chỉ dùng mã luật được cấp, id có trong kịch bản và trích NGUYÊN VĂN tại chính id đó. Không dùng đoạn diễn giải thay trích dẫn. Kiểm tra toàn bộ và trả JSON đúng schema.'
    if _continuity_pass:
        prompt += (
            "\nLƯỢT KIỂM TRA ĐỘC LẬP: không dựa vào verdict của lượt trước. Ưu tiên tìm lỗi hành động "
            "đảo thứ tự, nhân vật quên điều đã biết, cảnh bị thay bằng tóm tắt và chi tiết tiêu đề không được trả. "
            "Đọc toàn bộ từ đầu đến cuối; cần chứng cứ cụ thể ở các ID trước/sau.\n"
        )
    raw, in_tok, out_tok = call_llm(SYSTEM_INSTRUCTION, prompt)
    binding = {"review_version": SEMANTIC_REVIEW_VERSION, "story_hash": story_bible_content_hash(story_bible)}
    items, is_valid, err_msg = parse_json_items_validated(raw, "issues")
    if not is_valid:
        logger.warning(f"[SemanticReview] Model response invalid JSON: {err_msg}. Raw: {raw[:200]}")
        result = {
            **binding,
            "status": "ERROR",
            "error": f"Mô hình không trả về JSON hợp lệ: {err_msg}",
            "dropped_unanchored": 0,
            "script_hash": script_content_hash(script),
            "issues": [],
            "advisories": [],
            "tokens": [in_tok, out_tok],
        }
        return result if _retry_invalid else _retry_review_once(result, lambda: review_script_logic(script, story_bible, call_llm, _continuity_pass, True))

    by_id = {s.id: s for s in script.segments}
    blocking: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []
    dropped = 0
    for item in items:
        rule = str(item.get("rule", "")).strip().upper()
        seg_id = clean_segment_id(item.get("segment_id"), by_id)
        quote = str(item.get("quote", "")).strip()
        segment = by_id.get(seg_id)
        if rule not in LOGIC_RULE_CODES or segment is None or len(quote.split()) < 4:
            logger.warning('[SemanticReview] Invalid Script finding: rule=%s id=%s quote=%r', rule, seg_id, quote)
            dropped += 1
            continue
        if not _quote_in_text(quote, segment.text):
            logger.warning('[SemanticReview] Unanchored Script finding: rule=%s id=%s quote=%r', rule, seg_id, quote)
            dropped += 1
            continue
        if rule == 'GENERIC_PHILOSOPHICAL_HOOK' and seg_id != script.segments[0].id:
            # This rule governs the opening. A concluding audience question is
            # part of the format, not a second hook or a viewpoint violation.
            continue
        if rule == 'UNRESOLVED_SETUP':
            problem_text = str(item.get('problem', '')).lower()
            if any(phrase in problem_text for phrase in [
                "sau đó ở [", "đến phân đoạn [", "mãi đến phân đoạn", "mãi đến [",
                "ở phân đoạn [038]", "ở phân đoạn sau", "phần reveal sau",
                "ở đoạn sau", "ở các đoạn sau", "suy luận gián tiếp ở đoạn sau",
                "trong phần reveal", "phần reveal", "mặc dù đoạn", "mặc dù phân đoạn"
            ]):
                logger.info('[SemanticReview] Skipping UNRESOLVED_SETUP on %s: payoff acknowledged in later segment (%s)', seg_id, item.get('problem'))
                continue
        related = [
            r for r in (clean_segment_id(raw_id, by_id) for raw_id in (item.get("related_segment_ids") or []))
            if r in by_id and r != seg_id
        ]
        confident = str(item.get("confidence", "")).lower() == "high"
        # Objective defects (continuity, state changes, unmotivated confessions)
        # are cheap to fix and costly to air, so they block even when the judge is
        # only fairly sure; quotes are already verified. Taste calls never block.
        objective = is_blocking_logic_issue({"rule": rule})
        if objective:
            issue = {
                "segment_id": seg_id,
                "related_segment_ids": related,
                "excerpt": quote[:160],
                "rule": rule,
                "severity": "CRITICAL",
                "blocking": True,
                "source": "SEMANTIC_REVIEW",
                "message": f"Phân đoạn [{seg_id}] vi phạm {rule}: {str(item.get('problem', '')).strip()}",
                "recommended_action": str(item.get("fix", "")).strip(),
            }
            blocking.append(issue)
        else:
            issue = {
                "segment_id": seg_id,
                "related_segment_ids": related,
                "excerpt": quote[:160],
                "rule": rule,
                "severity": "WARNING",
                "blocking": False,
                "source": "SEMANTIC_REVIEW",
                "message": f"Phân đoạn [{seg_id}] lưu ý về phong cách ({rule}): {str(item.get('problem', '')).strip()}",
                "recommended_action": str(item.get("fix", "")).strip(),
            }
            advisories.append(issue)
    if dropped:
        logger.info(f"[SemanticReview] {script.episode_id}: dropped {dropped} unanchored findings")
    result = {
        **binding,
        # One misquoted finding must not void the review: drop it and keep the
        # anchored ones. Only a review with nothing usable is treated as failed.
        "status": "ERROR" if dropped and not (blocking or advisories) else "RUN",
        "error": (
            f"Có {dropped} finding không có chứng cứ hợp lệ; cần chạy lại review"
            if dropped and not (blocking or advisories) else None
        ),
        "dropped_unanchored": dropped,
        "script_hash": script_content_hash(script),
        "issues": blocking,
        "advisories": advisories,
        "tokens": [in_tok, out_tok],
    }
    if result['status'] == 'ERROR' and not _retry_invalid:
        return _retry_review_once(result, lambda: review_script_logic(script, story_bible, call_llm, _continuity_pass, True))
    # The independent continuity pass runs unless pass 1 already found an
    # objective defect; editor-level findings must not skip it, or the approval
    # gate (which requires both passes) could never open.
    if not _continuity_pass and result["status"] == "RUN" and not any(is_blocking_logic_issue(i) for i in blocking):
        second = review_script_logic(script, story_bible, call_llm, _continuity_pass=True)
        result["status"] = second["status"]
        result["error"] = second.get("error")
        result["issues"].extend(second.get("issues", []))
        result["advisories"].extend(second.get("advisories", []))
        result["dropped_unanchored"] += second.get("dropped_unanchored", 0)
        result["tokens"] = [a + b for a, b in zip(result["tokens"], second.get("tokens", [0, 0]))]
        result["passes"] = 2
        result['review_retries'] = result.get('review_retries', 0) + second.get('review_retries', 0)
    else:
        result["passes"] = 1
    return result


def carry_over_semantic_review(previous_report: Dict[str, Any], script: FullScript, story_bible: Optional[StoryBible] = None) -> Optional[Dict[str, Any]]:
    """Reuses a previous semantic review when the script text has not changed.
    
    Reclassifies all findings under the current policy so that objective defects
    cannot hide in advisories and bypass the QC/lineage gate.
    """
    review = previous_report.get("semantic_review") if isinstance(previous_report, dict) else None
    if (isinstance(review, dict) and review.get("status") == "RUN"
            and review.get("review_version") == SEMANTIC_REVIEW_VERSION
            and review.get("passes") == 2
            and (story_bible is None or review.get("story_hash") == story_bible_content_hash(story_bible))
            and review.get("script_hash") == script_content_hash(script)):
        reclassified = dict(review)
        raw_issues = list(review.get("issues") or [])
        raw_advisories = list(review.get("advisories") or [])
        all_findings = raw_issues + raw_advisories

        clean_blocking: List[Dict[str, Any]] = []
        clean_advisories: List[Dict[str, Any]] = []
        for finding in all_findings:
            if not isinstance(finding, dict):
                continue
            if is_blocking_logic_issue(finding):
                item = dict(finding)
                item["severity"] = "CRITICAL"
                item["blocking"] = True
                clean_blocking.append(item)
            else:
                item = dict(finding)
                item["severity"] = "WARNING"
                item["blocking"] = False
                clean_advisories.append(item)

        reclassified["issues"] = clean_blocking
        reclassified["advisories"] = clean_advisories
        return reclassified
    return None


# ---------------------------------------------------------------------------
# Story Bible review: catch plot designs the script writer cannot tell honestly
# (a reveal only the antagonist's mind could know, an illegal ending, a
# paternity verdict without a test) before any script is written from them.
# ---------------------------------------------------------------------------

STORY_BIBLE_REVIEW_FIELDS = (
    "title", "narrative_skeleton", "topic_intent",
    "secret", "false_lead", "clues", "structured_clues", "reveal_1", "reveal_2",
    "causal_chains", "reveal_justifications", "knowledge_ledger", "emotional_payoff", "ending",
    "protagonist", "supporting_characters", "timeline", "facts", "critical_facts", "relationships", "premise",
    "original_user_topic",
)

STORY_BIBLE_HASH_FIELDS = tuple(dict.fromkeys([
    *STORY_BIBLE_REVIEW_FIELDS,
    "protagonist", "supporting_characters", "timeline", "facts", "critical_facts", "relationships", "premise"
]))

# Rules about how a scene is narrated (order, repetition, wording) only exist
# once there is a script; the Story Bible is judged on design-level logic.
STORY_BIBLE_RULES = (
    "CHARACTER_IDENTITY_CONTRADICTION",
    "TOPIC_TRUTH_DRIFT",
    "POV_KNOWLEDGE_VIOLATION",
    "INFEASIBLE_EVIDENCE",
    "CONCLUSION_BEFORE_PROOF",
    "UNRESOLVED_SETUP",
    "LEGAL_OR_MEDICAL_UNREALISTIC",
    "IMPLAUSIBLE_BEHAVIOR",
    "UNMOTIVATED_DISCLOSURE",
    "REVEAL_LEAKED_EARLY",
)

# Only these rules block Story Bible approval when flagged with high confidence.
STORY_BIBLE_BLOCKING_RULES = {
    "CHARACTER_IDENTITY_CONTRADICTION",
    "TOPIC_TRUTH_DRIFT",
    "INFEASIBLE_EVIDENCE",
    "LEGAL_OR_MEDICAL_UNREALISTIC",
    "POV_KNOWLEDGE_VIOLATION",
    "IMPLAUSIBLE_BEHAVIOR",
    "UNRESOLVED_SETUP",
    "REVEAL_LEAKED_EARLY",
    "CONCLUSION_BEFORE_PROOF",
    "UNMOTIVATED_DISCLOSURE",
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
    plot = {k: data.get(k) for k in STORY_BIBLE_HASH_FIELDS if data.get(k)}
    skeleton = bible.narrative_skeleton if isinstance(bible.narrative_skeleton, dict) else {}
    trigger_text = str(skeleton.get("trigger", "") or "").strip()
    return (
        f"Nhân vật gửi thư (góc nhìn duy nhất): {protagonist.get('name') or bible.protagonist}\n\n"
        f"Tiêu đề Story Bible: {bible.title}\n"
        f"Trigger mở đầu (Narrative Skeleton): {trigger_text}\n\n"
        "Bộ luật logic cần kiểm tra (CHỈ các luật này):\n"
        + reviewer_checklist(STORY_BIBLE_RULES) + "\n\n"
        + REVIEW_CALIBRATION
        +
        "Yêu cầu nhất quán cốt lõi: Tiêu đề và Trigger phải thuộc cùng một câu chuyện logic với manh mối (clues), "
        "bước ngoặt (reveals) và hồi kết. Đạo cụ dẫn dắt nghi ngờ ở tiêu đề/trigger phải được giải thích trung thực, "
        "không được đổi sang một vật chứng khác mà bỏ lửng lời hứa ban đầu.\n\n"
        "Lưu ý: các trường secret, causal_chains, knowledge_ledger, reveal_justifications là SỰ THẬT HẬU TRƯỜNG "
        "cho người viết, không được đọc lên, nên KHÔNG áp dụng POV_KNOWLEDGE_VIOLATION cho chúng và không coi là kết luận sớm. "
        "Chỉ báo POV khi một reveal/ending đưa ra điều nhân vật chính không thể biết và Story Bible không có kênh tiết lộ nào. "
        "Đối chiếu kênh tiết lộ trong TOÀN BỘ Bible, không yêu cầu mỗi câu của tài liệu thiết kế phải lặp lại ai kể/khi nào. "
        "Phân biệt nhận định của nhân vật dựa trên hành động, tin nhắn và lời kể với việc biết bí mật nội tâm không có chứng cứ. "
        "Nhận định đạo đức như ích kỷ/thao túng không tự nó là lỗi POV nếu đã có hành vi, bằng chứng và kênh tiếp cận cụ thể; "
        "chỉ báo khi một SỰ KIỆN hoặc Ý ĐỊNH chưa được tiết lộ bị khẳng định chắc chắn. "
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


def valid_story_semantic_review(bible: StoryBible, review: Any) -> bool:
    return (isinstance(review, dict) and review.get('status') == 'RUN'
            and review.get('review_version') == SEMANTIC_REVIEW_VERSION and review.get('passes') == 2
            and review.get('bible_hash') == story_bible_content_hash(bible)
            and not review.get('dropped_unanchored') and not review.get('issues'))


def review_story_bible_logic(bible: StoryBible, call_llm: LLMCall, _second_pass: bool = False) -> Dict[str, Any]:
    """Returns {"issues": [...high confidence...], "advisories": [...], "bible_hash"}."""
    prompt = build_story_bible_prompt(bible)
    if _second_pass:
        prompt += '\nLƯỢT KIỂM TRA ĐỘC LẬP: đối chiếu danh tính, timeline, bằng chứng và tri thức của nhân vật giữa các trường. Không dựa vào verdict lượt trước.'
    raw, in_tok, out_tok = call_llm(STORY_BIBLE_SYSTEM_INSTRUCTION, prompt)
    items, is_valid, err_msg = parse_json_items_validated(raw, "issues")
    if not is_valid:
        logger.warning(f"[SemanticReview] Story Bible review invalid JSON: {err_msg}")
        return {
            "status": "ERROR",
            "review_version": SEMANTIC_REVIEW_VERSION,
            "passes": 1,
            "error": f"Story Bible review JSON invalid: {err_msg}",
            "bible_hash": story_bible_content_hash(bible),
            "issues": [],
            "advisories": [],
            "tokens": [in_tok, out_tok],
        }

    data = bible.to_dict()
    blocking: List[Dict[str, Any]] = []
    advisories: List[Dict[str, Any]] = []
    dropped = 0
    for item in items:
        rule = str(item.get("rule", "")).strip().upper()
        field_name = str(item.get("field", "")).strip()
        quote = str(item.get("quote", "")).strip()
        # Compare with actual story text, not JSON's escaped representation:
        # a valid quotation containing dialogue quotes is not literally present
        # in json.dumps(...), which inserts backslashes around those quotes.
        def field_text(value):
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                return "\n".join(field_text(v) for v in value.values())
            if isinstance(value, list):
                return "\n".join(field_text(v) for v in value)
            return str(value) if value is not None else ""
        root_field = field_name.split(".")[0]
        if rule == "POV_KNOWLEDGE_VIOLATION" and (root_field in STORY_BIBLE_BACKSTAGE_FIELDS or field_name in STORY_BIBLE_BACKSTAGE_FIELDS):
            continue
        source = ""
        if root_field in STORY_BIBLE_REVIEW_FIELDS:
            source = field_text(data.get(root_field))
        else:
            for k in STORY_BIBLE_REVIEW_FIELDS:
                sub = data.get(k)
                if isinstance(sub, dict) and root_field in sub:
                    source = field_text(sub.get(root_field))
                    break
        if rule not in STORY_BIBLE_RULES or not source or not _quote_in_text(quote, source):
            logger.warning("[SemanticReview] Invalid Story finding: rule=%s field=%s quote=%r", rule, field_name, quote)
            dropped += 1
            continue
        issue = {
            "rule": rule,
            "target": field_name,
            "excerpt": quote[:160],
            "message": f"{str(item.get('problem', '')).strip()} Cách sửa: {str(item.get('fix', '')).strip()}",
            "source": "SEMANTIC_REVIEW",
        }
        confident = str(item.get("confidence", "")).lower() == "high"
        (blocking if confident and rule in STORY_BIBLE_BLOCKING_RULES else advisories).append(issue)
    result = {
        "status": "ERROR" if dropped and not (blocking or advisories) else "RUN",
        "review_version": SEMANTIC_REVIEW_VERSION,
        "passes": 1,
        "error": f"Có {dropped} finding Story Bible không hợp lệ" if dropped and not (blocking or advisories) else None,
        "dropped_unanchored": dropped,
        "bible_hash": story_bible_content_hash(bible),
        "issues": blocking,
        "advisories": advisories,
        "tokens": [in_tok, out_tok],
    }
    if not _second_pass and result['status'] == 'RUN' and not blocking:
        second = review_story_bible_logic(bible, call_llm, _second_pass=True)
        result.update(status=second['status'], error=second.get('error'), passes=2)
        result['issues'].extend(second.get('issues', []))
        result['advisories'].extend(second.get('advisories', []))
        result['dropped_unanchored'] += second.get('dropped_unanchored', 0)
        result['tokens'] = [a + b for a, b in zip(result['tokens'], second.get('tokens', [0, 0]))]
    return result
