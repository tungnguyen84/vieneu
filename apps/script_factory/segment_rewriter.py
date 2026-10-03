"""AI rewrite of only the script segments that QC flagged.

Regenerating a whole script to fix a handful of bad sentences trades known
defects for new random ones. This module sends just the flagged segments, with
their neighbours as read-only context, and splices the rewritten text back.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, QCReport, StoryBible

logger = logging.getLogger("VieNeu.SegmentRewriter")

# call_llm(system_instruction, prompt) -> (raw_text, input_tokens, output_tokens)
LLMCall = Callable[[str, str], Tuple[str, int, int]]

MAX_SEGMENTS_PER_CALL = 24

# Rules the deterministic repair already fixes without changing meaning.
_DETERMINISTIC_ONLY_RULES = {
    "PREMATURE_SIGNOFF", "DUPLICATE_SIGNOFF", "CONTENT_AFTER_SIGNOFF", "MISSING_FINAL_SIGNOFF",
    "REVEAL_AUDIENCE_RESTRAINT", "ENDING_PROPORTION_VIOLATION",
}

REPETITION_RULES = {
    "REPEATED_DISCOVERY",
    "REPEATED_NARRATIVE_BLOCK",
    "ADJACENT_SEGMENT_ECHO",
    "REPEATED_SCENE_DIALOGUE",
}

_SIGNOFF_RE = re.compile(r"cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|xin\s+chào\s+và\s+hẹn\s+gặp\s+lại", re.IGNORECASE)

SYSTEM_INSTRUCTION = (
    "Bạn là biên tập viên kịch bản audio tiếng Việt cho chương trình kể chuyện 'Sau Cánh Cửa' do MC Minh dẫn. "
    "Nhiệm vụ: viết lại DUY NHẤT các phân đoạn được yêu cầu để sửa lỗi QC, giữ nguyên sự kiện, nhân vật, "
    "thứ tự thông tin và giọng kể. Văn nói tự nhiên, câu hoàn chỉnh đúng chủ-vị, không sáo rỗng, "
    "không triết lý chung chung, không thêm nhân vật hay tình tiết mới, không tiết lộ sớm hơn bản gốc. "
    "Câu chuyện là lời người trong cuộc gửi về chương trình nên người kể không biết suy nghĩ bên trong của "
    "nhân vật khác trừ khi họ tự nói ra. Không kết luận huyết thống khi chưa có xét nghiệm ADN; không bịa "
    "thủ tục pháp lý. Chỉ trả về JSON."
)


def _issue_phrases(issue: Dict[str, Any]) -> List[str]:
    return [p for p in re.findall(r"'([^']{4,60})'", str(issue.get("message", ""))) if p]


def collect_flagged_segments(script: FullScript, qc_report: QCReport) -> Dict[str, List[str]]:
    """Maps segment id -> list of problems to fix in that segment."""
    by_id = {s.id: s for s in script.segments}
    flagged: Dict[str, List[str]] = {}

    def add(seg_id: Optional[str], problem: str) -> None:
        if seg_id in by_id and problem not in flagged.setdefault(seg_id, []):
            flagged[seg_id].append(problem)

    # Only blocking findings are rewritten. Rewriting segments for advisories or
    # style warnings churned the script and introduced fresh defects each round.
    for issue in [*qc_report.evidence_issues, *qc_report.fact_conflicts]:
        if not isinstance(issue, dict):
            continue
        rule = str(issue.get("rule") or issue.get("type") or "")
        if rule in _DETERMINISTIC_ONLY_RULES:
            continue
        message = str(issue.get("message") or issue.get("description") or rule)
        action = str(issue.get("recommended_action") or "")
        problem = f"[{rule}] {message}" + (f" Cách sửa: {action}" if action else "")

        phrases = _issue_phrases(issue)
        if "CLICHE" in rule or "MELODRAMA" in rule:
            # Density rules anchor on one segment but the phrases are spread out.
            for seg in script.segments:
                hits = [p for p in phrases if p.casefold() in seg.text.casefold()]
                if hits:
                    add(seg.id, f"[{rule}] Thay cụm từ sáo rỗng {hits} bằng mô tả cụ thể, giản dị.")
            continue
        if rule == "REPEATED_NARRATIVE_BLOCK" and isinstance(issue.get("first_start"), int):
            earlier = " / ".join(
                s.text for s in script.segments[issue["first_start"]:issue.get("first_end", issue["first_start"] + 4)]
            )[:900]
            block_problem = (
                f"[{rule}] Cụm phân đoạn này kể lại chuỗi sự kiện ĐÃ KỂ trước đó. Viết lại cả cụm thành diễn biến MỚI "
                f"nối tiếp câu chuyện (hoặc rút gọn thành 1-2 câu chuyển cảnh), tuyệt đối không kể lại: \"{earlier}\""
            )
            add(issue.get("segment_id"), block_problem)
            for related_id in issue.get("related_segment_ids") or []:
                add(related_id, block_problem)
            continue
        if rule == "UNSUPPORTED_PATERNITY_CLAIM":
            for seg in script.segments:
                if re.search(r"không\s+(?:phải|thể\s+là)\s+con\s+của|không\s+phải\s+máu\s+mủ", seg.text, re.IGNORECASE):
                    add(seg.id, problem)
            continue
        add(issue.get("segment_id"), problem)
        # Semantic findings name the other segments that must change with it
        # (e.g. the scene that sets up an infeasible test and its payoff).
        for related_id in issue.get("related_segment_ids") or []:
            add(related_id, f"(Liên quan tới lỗi ở [{issue.get('segment_id')}]) {problem}")
    return flagged


def _story_context(story_bible: StoryBible) -> Dict[str, Any]:
    # Repairs need the same canonical plot as the writer. Truncating clues to
    # four or omitting the timeline/ending makes a later evidence channel look
    # optional, so a rewrite reintroduces exactly the inconsistency QC flagged.
    return {k: v for k, v in story_bible.to_dict().items()
            if k not in {'story_qc_report', 'status', 'approved_at', 'approved_by'}}


def build_prompt(script: FullScript, story_bible: StoryBible, flagged: Dict[str, List[str]]) -> str:
    from apps.script_factory.story_contract import contract_block
    index = {s.id: i for i, s in enumerate(script.segments)}
    targets = []
    for seg_id in sorted(flagged, key=index.__getitem__):
        problems = flagged[seg_id]
        i = index[seg_id]
        targets.append({
            "id": seg_id,
            "delivery_profile": script.segments[i].delivery_profile,
            "previous_text": script.segments[i - 1].text if i > 0 else "",
            "text": script.segments[i].text,
            "next_text": script.segments[i + 1].text if i + 1 < len(script.segments) else "",
            "problems": problems,
        })
    return (
        "Bối cảnh câu chuyện:\n"
        f"{json.dumps(_story_context(story_bible), ensure_ascii=False)}\n\n"
        + contract_block(story_bible) +
        "Toàn bộ mạch kịch bản hiện tại (chỉ đọc để biết nhân vật đã biết gì và sự kiện đã xảy ra):\n"
        + '\n'.join(f'[{s.id}] {s.text}' for s in script.segments) + '\n\n'
        +
        "Các phân đoạn cần viết lại (previous_text/next_text chỉ để nối mạch, KHÔNG viết lại chúng; "
        "không lặp lại hành động đã kể ở previous_text):\n"
        f"{json.dumps(targets, ensure_ascii=False, indent=1)}\n\n"
        "Yêu cầu:\n"
        "- Sửa cả nhóm theo trình tự thời gian, mỗi id giữ một diễn biến riêng. Không sao chép câu của "
        "phân đoạn liền kề vào nhiều id. Nếu previous_text/next_text cũng có id trong nhóm yêu cầu, "
        "đồng bộ bản sửa của cả nhóm thay vì coi bản cũ của chúng là bất biến.\n"
        "- Thường giữ độ dài tương đương bản gốc (±30%). Riêng đoạn lặp khám phá/sự kiện/câu văn, "
        "được rút ngắn thành câu nối mạch; không kéo dài hoặc dựng phát hiện mới chỉ để đủ số từ.\n"
        "- Phân đoạn đầu tiên của kịch bản phải mở bằng nhân vật/vật cụ thể, không mở bằng câu triết lý.\n"
        "- Không thêm lời chào kết hay lời cảm ơn khán giả.\n"
        "- Khi sửa lỗi người kể biết nội tâm nhân vật khác, hãy chuyển thành câu thoại nhân vật đó tự nói ra "
        "hoặc thành phỏng đoán có chủ thể ('Tuấn đoán…'); KHÔNG thêm cảnh mở lại, lục lại vật chứng đã xem.\n"
        "- TÍNH LIÊN TỤC VÀ BẰNG CHỨNG (CONTINUITY): Khi sửa một phân đoạn liên quan đến bằng chứng, tên nhân vật hoặc đạo cụ, "
        "BẮT BUỘC phải đảm bảo tính nhất quán với toàn bộ mạch kịch bản. Nếu một đạo cụ/bằng chứng mới được thiết lập (hoặc thay thế), "
        "không để các phân đoạn sau nhắc tới như thể vẫn còn vật cũ hoặc ngược lại. Tên người lạ hoặc vật phẩm phải được giới thiệu "
        "trước khi nhân vật gọi tên.\n"
        "- NGUỒN NHẬN THỨC: nghe tên chưa đủ để nhận ra mặt người trong ảnh; cần cảnh từng gặp hoặc chú thích ảnh xác nhận rõ tên. "
        "Không cho nhân vật hỏi về người yêu cũ trước khi nguồn thông tin ấy được tiết lộ. Nguồn chỉ nằm trong Bible hoặc ở cảnh sau chưa cấp kiến thức cho cảnh trước.\n"
        "- SETUP & PAYOFF: Nếu phân đoạn được sửa liên quan đến một manh mối/vật phẩm gieo từ đầu truyện (setup), phải bảo đảm "
        "có đáp án cụ thể: nội dung được đọc và điều nội dung ấy xác nhận. Chỉ mở vật chứa hoặc nói 'đối chiếu sự thật' chưa trả được câu hỏi. "
        "Không suy ra danh tính từ ảnh, dấu công cụ hay tên trong danh bạ; không dùng giấy khám sức khỏe thay hồ sơ hiến tạng. "
        "Giữ đúng năm và thời lượng của từng sự kiện/nhân vật, phân biệt mắc bệnh với phẫu thuật, giữ hành động kết thúc trong Bible.\n"
        "- DỰNG CẢNH SỐNG ĐỘNG: Cảnh đối chất, phát hiện manh mối hoặc chia tay phải có hành động cụ thể và lời thoại trực tiếp "
        "trong ngoặc kép thay vì chỉ tóm tắt diễn biến.\n"
        'Trả về JSON: {"segments": [{"id": "<id>", "text": "<văn bản mới>"}]}'
    )


def parse_json_items_validated(raw: str, key: str) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """Extracts a list of objects from {key: [...]} or a bare [...], with validation info.

    Returns:
        (items, is_valid_json, error_message)
    """
    if not raw or not raw.strip():
        return [], False, "Phản hồi từ AI rỗng"

    # Extract markdown code fence block if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    text = fence_match.group(1).strip() if fence_match else raw.strip()

    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return [], False, "Không tìm thấy cấu trúc JSON (thiếu '{' hoặc '[')"

    start = min(starts)
    data = None
    decode_err = None

    # First attempt: standard raw_decode from first opening brace (ignores trailing text)
    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text[start:])
    except Exception as exc:
        decode_err = exc

    # Fallback attempt: find matching outermost brace
    if data is None:
        is_obj = text[start] == "{"
        end = text.rfind("}" if is_obj else "]")
        if end < start:
            return [], False, "Cấu trúc JSON bị cắt cụt (dấu ngoặc đóng không khớp)"
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            return [], False, f"Lỗi cú pháp JSON: {decode_err or exc}"

    if isinstance(data, dict):
        if key not in data:
            return [], False, f"JSON thiếu trường bắt buộc '{key}'"
        items = data.get(key)
    elif isinstance(data, list):
        items = data
    else:
        return [], False, "Dữ liệu JSON không phải object hay array"

    if not isinstance(items, list):
        return [], False, f"Trường '{key}' phải là danh sách (array)"

    if any(not isinstance(item, dict) for item in items):
        return [], False, f"Mọi phần tử trong '{key}' phải là object; không được bỏ lỗi để coi như danh sách rỗng"
    return items, True, None


def clean_segment_id(raw: Any, known_ids: Any) -> str:
    """Maps a model-written id ("[059]", "#59", "59") onto a real segment id.

    Prompts list segments as "[059] text", and models echo that form back;
    matching only the bare id silently discarded valid findings and repairs.
    """
    seg_id = re.sub(r"^\s*(?:segment|id)?\s*[\[#(]*\s*|\s*[\])]*\s*$", "", str(raw or ""), flags=re.IGNORECASE)
    if seg_id in known_ids or not seg_id.isdigit():
        return seg_id
    width = max((len(k) for k in known_ids if str(k).isdigit()), default=len(seg_id))
    padded = seg_id.zfill(width)
    return padded if padded in known_ids else seg_id


def parse_json_items(raw: str, key: str) -> List[Dict[str, Any]]:
    """Extracts a list of objects from ``{key: [...]}`` or a bare ``[...]``.

    Models asked for an object frequently answer with the bare array instead.
    """
    items, _, _ = parse_json_items_validated(raw, key)
    return items


def rewrite_flagged_segments(
    script: FullScript,
    story_bible: StoryBible,
    qc_report: QCReport,
    call_llm: LLMCall,
) -> Tuple[FullScript, int, int, set]:
    """Rewrites flagged segments in place.

    Returns (script, input_tokens, output_tokens, ids of segments actually rewritten).
    """
    flagged = collect_flagged_segments(script, qc_report)
    rewritten: set = set()
    if not flagged:
        return script, 0, 0, rewritten

    by_id = {s.id: s for s in script.segments}
    last_id = script.segments[-1].id
    ids = [s.id for s in script.segments if s.id in flagged]
    total_in = total_out = 0
    for start in range(0, len(ids), MAX_SEGMENTS_PER_CALL):
        batch = {seg_id: flagged[seg_id] for seg_id in ids[start:start + MAX_SEGMENTS_PER_CALL]}
        raw, in_tok, out_tok = call_llm(SYSTEM_INSTRUCTION, build_prompt(script, story_bible, batch))
        total_in += in_tok
        total_out += out_tok
        applied = 0
        for item in parse_json_items(raw, "segments"):
            seg_id = clean_segment_id(item.get("id"), batch)
            new_text = re.sub(r"\s+", " ", str(item.get("text", ""))).strip()
            if seg_id not in batch or not new_text:
                continue
            original = by_id[seg_id].text
            if seg_id != last_id and _SIGNOFF_RE.search(new_text):
                continue
            # A repeated discovery often needs a short transition. Requiring
            # its old length silently rejects that repair and preserves the loop.
            repetition = any(rule in problem for problem in batch[seg_id] for rule in REPETITION_RULES)
            minimum_ratio = 0.1 if repetition else 0.4
            ratio = len(new_text) / max(1, len(original))
            if not (minimum_ratio <= ratio <= 2.0):
                logger.warning(
                    f"[SegmentRewriter] Bỏ qua sửa đoạn [{seg_id}]: tỷ lệ độ dài {ratio:.2f} "
                    f"ngoài giới hạn [{minimum_ratio}, 2.0] (gốc: {len(original)}, mới: {len(new_text)})"
                )
                continue
            by_id[seg_id].text = new_text
            rewritten.add(seg_id)
            applied += 1

        unapplied = set(batch.keys()) - rewritten
        if unapplied:
            logger.warning(f"[SegmentRewriter] Các đoạn chưa áp dụng sửa trong batch: {sorted(unapplied)}")
        logger.info(f"[SegmentRewriter] {script.episode_id}: rewrote {applied}/{len(batch)} flagged segments")
    return script, total_in, total_out, rewritten


def revise_with_ai(
    script: FullScript,
    story_bible: StoryBible,
    qc_report: QCReport,
    call_llm: LLMCall,
) -> Tuple[FullScript, int, int]:
    """One revision round shared by every provider: AI segment rewrite, then
    deterministic repairs that leave the freshly rewritten segments alone.

    A failed AI call preserves the draft; production never invents replacement prose.
    """
    from apps.script_factory.script_qc import apply_targeted_repairs

    script.revision_round += 1
    in_tok = out_tok = 0
    rewritten: set = set()
    try:
        script, in_tok, out_tok, rewritten = rewrite_flagged_segments(script, story_bible, qc_report, call_llm)
    except Exception:
        logger.exception('[SegmentRewriter] AI rewrite failed; retaining draft without template replacements')
        raise
    script = apply_targeted_repairs(script, story_bible, qc_report, preserve_segment_ids=rewritten,
                                    allow_prose_templates=False)
    from apps.script_factory.vietnamese_cleaner import clean_garbled_vietnamese
    for s in script.segments:
        s.text = clean_garbled_vietnamese(s.text)
    script.total_words = sum(len(s.text.split()) for s in script.segments)
    script.updated_at = time.time()
    return script, in_tok, out_tok
