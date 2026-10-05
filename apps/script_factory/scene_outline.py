"""Scene outline that both halves of a two-call script are written against.

A full episode is written in two model calls to avoid output truncation. Part 2
used to receive only a summary of Part 1 and regularly "restarted" the
investigation, retelling a visit or a phone call with new wording (EP2007 told
the same shop visit twice). Planning every scene up front, each with its own new
information, and telling Part 2 exactly which scenes are already written removes
that seam. Production requires the outline to cover each writing obligation;
test/import callers may explicitly retain the legacy optional outline.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.script_factory.models import StoryBible
from apps.script_factory.narrative_design import DESIGN_INSTRUCTION, outline_design_errors

logger = logging.getLogger("VieNeu.SceneOutline")

LLMCall = Callable[[str, str], Tuple[str, int, int]]

SYSTEM_INSTRUCTION = (
    "Bạn là biên kịch trưởng của 'Sau Cánh Cửa'. Lập DÀN CẢNH cho một tập audio dài khoảng 80 phân đoạn. "
    "Mỗi cảnh xảy ra một lần duy nhất và mang một thông tin MỚI. Chỉ trả về JSON."
)


def _prompt(bible: StoryBible) -> str:
    from apps.script_factory.story_contract import contract_block
    if bible.adaptation_context:
        from apps.script_factory.adaptation import writer_context
        from apps.script_factory.prompt_context import story_prompt_data
        target = bible.adaptation_context['brief']['target_duration_sec']
        scene_target = max(8, min(18, round(target * 2.7 / 300)))
        return (f'Lập dàn cảnh cho {target} giây, khoảng {round(target*2.7)} từ; không ép 80 đoạn hoặc hai reveals. '
            'Mỗi cảnh có action, new_information, consequence; ghi payoff_ids và payoff_action trả lời hợp đồng. '
            'Factual: cảnh là đơn vị trình bày thông tin có nguồn, không bịa hành động/thoại. '
            'Hư cấu/own: gọi tên công việc, vật hoặc thao tác thực tế trong cảnh; không chỉ ghi "cải thiện quy trình", "hiểu nhu cầu", "giải quyết vấn đề". '
            'Nếu fiction Bible chỉ mô tả khái quát, cụ thể hóa trong phạm vi hướng đã chọn bằng một nghiệp vụ quan sát được; không đổi các facts đã khóa. '
            'Own chỉ thêm chi tiết trong phần được thay, giữ nguyên nguyên nhân/kết thúc/locks. '
            'Writer triển khai các cụm cảnh liên tiếp, giữ ngữ cảnh toàn tập; xếp tối thiểu 8 cảnh, không cần chia part 1/2. '
            f'Mục tiêu khoảng {scene_target} cảnh có diễn biến thực, tùy số sự kiện được phép trong Bible. '
            'Không chia một lần xem giấy/sửa đồ thành nhiều cảnh cùng kết luận để đủ thời lượng. '
            'Ở fiction, nếu canon chỉ ghi "thay linh kiện", action cần chọn một bộ phận cụ thể phù hợp sự cố '
            'và ghi rõ lần thử sai khác lần sửa đúng ở điểm nào; giữ tên bộ phận và nơi sửa ở các cảnh sau. '
            'Không thêm chẩn đoán/thao tác ngoài nguồn ở factual hoặc ngoài allowed_changes ở own. '
            'Ở fiction, triển khai các lần thử, trở ngại và lựa chọn cụ thể trong phạm vi canon; '
            'ở factual/own không bịa sự kiện để đạt số cảnh. Vật được giao cho ai/ở đâu phải liên tục qua các cảnh, có hành động nhận lại trước khi mang đi. '
            + DESIGN_INSTRUCTION +
            'JSON {scenes:[{no,part,title,role,state_before,state_after,listener_question,action,new_information,consequence,payoff_ids:[],payoff_action,segments}]}.\n'
            + writer_context(bible.adaptation_context) + contract_block(bible)
            # QC reports contain all reviewer responses, quotes and request
            # records. They are diagnostics, not story canon, and can dwarf
            # the actual source and trigger the proxy's request-size limit.
            + '\nStory: ' + json.dumps(story_prompt_data(bible, include_outline=False),ensure_ascii=False))
    data = {k: v for k, v in bible.to_dict().items() if k not in {"story_qc_report", "status", "approved_at", "approved_by"}}
    return (
        f"STORY BIBLE:\n{json.dumps(data, ensure_ascii=False)}\n\n"
        + contract_block(bible) +
        DESIGN_INSTRUCTION +
        "Lập 14-18 cảnh theo thứ tự thời gian. Yêu cầu:\n"
        "- Mỗi cảnh: một hành động/địa điểm/cuộc trò chuyện cụ thể và đúng MỘT thông tin mới người nghe chưa biết.\n"
        "- KHÔNG có hai cảnh cùng một việc (hai lần đến cùng một nơi hỏi cùng một người, hai lần tra cùng một manh mối).\n"
        "- Mỗi bằng chứng có được bằng cách tự nhiên đời thường (nhìn thấy, nghe được, nhận ra người quen), không qua thủ tục "
        "giấy tờ phi thực tế (người lạ được cấp hợp đồng thuê nhà, camera, sao kê của người khác).\n"
        "- NGUYÊN TẮC BẰNG CHỨNG VÀ TÊN NHÂN VẬT: Mọi bằng chứng phải được TÌM THẤY hoặc ĐỌC NỘI DUNG ở cảnh trước mới được mang ra suy luận "
        "hoặc đối chất ở cảnh sau. Tên nhân vật phụ (ví dụ: nhân tình, con riêng, đồng phạm) phải được xác định danh tính cụ thể trong một cảnh trước khi gọi tên.\n"
        "- NGUYÊN TẮC SETUP & PAYOFF: Chi tiết/vật chứng mở đầu (trong trigger/hook) phải có cảnh kiểm chứng và giải quyết trọn vẹn (payoff) trước cảnh kết thúc.\n"
        "- Mỗi cảnh ghi trạng thái trước/sau: nhân vật vừa biết gì, phải quyết định hoặc mất gì vì thông tin mới. Không lập cảnh chỉ 'cần hỏi', 'xếp giấy', 'chưa kết luận' mà không thay đổi tình thế.\n"
        "- Gắn payoff_ids của hợp đồng vào cảnh trả lời thật sự, kèm payoff_action diễn tả đáp án cụ thể và nguồn xác nhận. Một dấu hiệu chỉ tạo nghi ngờ vẫn phải được giải thích nguồn gốc, không suy ra tội/ngoại tình từ dấu hiệu.\n"
        "- Cú lật phải thay đổi cách hiểu manh mối cũ bằng một thông tin trong Bible chưa xác nhận trước đó. Nếu đã biết danh tính, hãy dùng sự kiện/động cơ/hậu quả mới có sẵn trong Bible; không thêm bí mật tùy tiện.\n"
        "- Cảnh 1-3: hook và giới thiệu đời sống. Cảnh 4-10: manh mối đầu tiên, giả thuyết sai và điều tra thực địa. Cảnh 11-13: Bước ngoặt 1 (lật tẩy giả thuyết sai). "
        "Cảnh 14-15: Cú lật chính (sự thật cốt lõi). Cảnh 15-16: Đối chất/thú nhận bằng lời thoại trực tiếp. Cảnh 17-18: Giải quyết bằng hành động dứt khoát và chiêm nghiệm.\n"
        "- Đánh dấu 'part': 1 cho khoảng 45% cảnh đầu (kết thúc ở cuối một cảnh trọn vẹn), 2 cho phần còn lại.\n"
        'Trả về JSON: {"scenes": [{"no": 1, "part": 1, "title": "<tên cảnh ngắn>", '
        '"role": "<vai trò cảnh>", "state_before": "<tình thế trước>", "state_after": "<tình thế sau>", "listener_question": "<câu hỏi muốn biết tiếp>", "action": "<hành động cụ thể>", "new_information": "<thông tin mới duy nhất>", "consequence": "<thay đổi tình thế/quyết định>", "payoff_ids": ["<id hợp đồng được trả lời>"], "payoff_action": "<đáp án và nguồn>", "segments": <3-8>}]}'
    )


def _normalize(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    for i, scene in enumerate(scenes, start=1):
        title = str(scene.get("title", "")).strip()
        action = str(scene.get("action", "")).strip()
        if not title or not action:
            continue
        part = 2 if str(scene.get("part", "1")).strip() == "2" else 1
        try:
            segments = max(2, min(10, int(scene.get("segments", 5))))
        except (TypeError, ValueError):
            segments = 5
        clean.append({
            "no": len(clean) + 1,
            "part": part,
            "title": title,
            "action": action,
            "new_information": str(scene.get("new_information", "")).strip(),
            "consequence": str(scene.get("consequence", "")).strip(),
            "payoff_ids": scene.get("payoff_ids", []) if isinstance(scene.get("payoff_ids", []), list) else [],
            "payoff_action": str(scene.get("payoff_action", "")).strip(),
            "segments": segments,
            **{key: str(scene.get(key, '')).strip() for key in ('role', 'state_before', 'state_after', 'listener_question')},
        })
    # Parts must be contiguous: everything before the first Part-2 scene is Part 1.
    first_two = next((i for i, s in enumerate(clean) if s["part"] == 2), None)
    if first_two is not None:
        for i, scene in enumerate(clean):
            scene["part"] = 1 if i < first_two else 2
    return clean


def outline_fulfills_contract(bible: StoryBible, scenes) -> bool:
    from apps.script_factory.story_contract import payoff_obligations
    if not scenes or any(not s.get('new_information') or not s.get('consequence') for s in scenes):
        return False
    if outline_design_errors(scenes):
        return False
    mapped = {key for s in scenes if s.get('payoff_action') for key in s.get('payoff_ids', [])}
    return {o['id'] for o in payoff_obligations(bible)} <= mapped


def build_scene_outline(bible: StoryBible, call_llm: LLMCall, require_contract: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Returns the planned scenes, or None when the outline could not be produced."""
    from apps.script_factory.segment_rewriter import parse_json_items
    system = SYSTEM_INSTRUCTION
    if bible.adaptation_context:
        from apps.script_factory.adaptation import SYSTEM
        system = SYSTEM + ' Lập dàn cảnh VĂN BẢN theo thời lượng và mode trong brief; mỗi cảnh có thông tin mới, không ép 80 phân đoạn. Chỉ trả JSON văn bản, không tạo ảnh/video hay gọi công cụ.'

    try:
        raw, _, _ = call_llm(system, _prompt(bible))
    except Exception as exc:
        if require_contract:
            logger.warning('[SceneOutline] Required outline provider call failed: %s', exc)
            raise RuntimeError(f'Dịch vụ AI lỗi khi lập dàn cảnh: {exc}') from exc
        logger.warning(f"[SceneOutline] Outline call failed, writing without outline: {exc}")
        return None
    scenes = _normalize(parse_json_items(raw, "scenes"))
    if require_contract and not outline_fulfills_contract(bible, scenes):
        from apps.script_factory.story_contract import payoff_obligations
        def failure_details():
            mapped = {key for s in scenes if s.get('payoff_action') for key in s.get('payoff_ids', [])}
            missing = sorted({o['id'] for o in payoff_obligations(bible)} - mapped)
            errors = outline_design_errors(scenes)
            if not scenes or any(not s.get('new_information') or not s.get('consequence') for s in scenes):
                errors.append('Thiếu new_information/consequence trong dàn cảnh.')
            if missing:
                errors.append('Chưa có payoff_action cho các ID: ' + ', '.join(missing))
            return '; '.join(errors)
        logger.warning('[SceneOutline] Outline rejected: %s; retrying once before writing', failure_details())
        try:
            raw, _, _ = call_llm(system, _prompt(bible) + '\nDàn cảnh trước chưa hợp lệ: ' + failure_details() + '\nKiểm tra đủ TỪNG payoff id, ghi cảnh trả lời và đáp án rõ nguồn. Mỗi cảnh phải có new_information và consequence. Trả lại toàn bộ dàn cảnh JSON.')
            scenes = _normalize(parse_json_items(raw, 'scenes'))
        except Exception as exc:
            logger.warning('[SceneOutline] Contract retry failed: %s', exc)
            raise RuntimeError(f'Dịch vụ AI lỗi khi sửa dàn cảnh: {exc}') from exc
        if not outline_fulfills_contract(bible, scenes):
            logger.warning('[SceneOutline] Outline still rejected after bounded retry: %s', failure_details())
            return None
    parts = {s["part"] for s in scenes}
    if len(scenes) < 8 or (not bible.adaptation_context and parts != {1, 2}):
        logger.warning(f"[SceneOutline] Outline unusable ({len(scenes)} scenes, parts={sorted(parts)}); writing without outline")
        return None
    logger.info(f"[SceneOutline] Planned {len(scenes)} scenes ({sum(s['part'] == 1 for s in scenes)} in part 1)")
    return scenes


def outline_block(scenes: Optional[List[Dict[str, Any]]], part: int) -> str:
    """Prompt section telling a part which scenes to write and which are already written."""
    if not scenes:
        return ""
    lines = ["", "DÀN CẢNH BẮT BUỘC CỦA CẢ TẬP (viết đúng thứ tự, mỗi cảnh một lần):"]
    for s in scenes:
        if s["part"] == part:
            tag = "VIẾT TRONG PHẦN NÀY"
        elif s["part"] < part:
            tag = "ĐÃ VIẾT Ở PHẦN 1 — KHÔNG kể lại"
        else:
            tag = "để PHẦN 2 viết — KHÔNG viết bây giờ"
        lines.append(
            f"Cảnh {s['no']} [{tag}] {s['title']}: {s['action']} | Thông tin mới: {s['new_information']} | Hệ quả: {s.get('consequence', '')} | Trả lời {s.get('payoff_ids', [])}: {s.get('payoff_action', '')} | ~{s['segments']} phân đoạn"
        )
    if part == 1:
        lines.append("PHẦN 1 kết thúc đúng ở cuối cảnh cuối cùng được đánh dấu VIẾT TRONG PHẦN NÀY.")
    else:
        lines.append("PHẦN 2 bắt đầu NGAY bằng cảnh đầu tiên được đánh dấu VIẾT TRONG PHẦN NÀY; không viết lại cảnh ĐÃ VIẾT.")
    return "\n".join(lines) + "\n"


def single_pass_outline_block(scenes: Optional[List[Dict[str, Any]]]) -> str:
    """Prompt section telling the single-pass writer the planned scene order."""
    if not scenes:
        return ""
    lines = ["", "DÀN CẢNH BẮT BUỘC CỦA CẢ TẬP (viết đúng thứ tự thời gian, mỗi cảnh xảy ra đúng MỘT lần):"]
    for s in scenes:
        lines.append(
            f"Cảnh {s['no']} [{s.get('role', '')}]: {s['title']} — Hành động: {s['action']} | Thông tin mới: {s['new_information']} | Hệ quả: {s.get('consequence', '')} | Trạng thái {s.get('state_before', '')} → {s.get('state_after', '')} | Câu hỏi: {s.get('listener_question', '')} | Trả lời {s.get('payoff_ids', [])}: {s.get('payoff_action', '')} | ~{s['segments']} phân đoạn"
        )
    lines.append("Triển khai tuần tự theo từng cảnh trên; không nhảy cóc và không kể lại cảnh đã qua.\n")
    return "\n".join(lines)


_QUOTE_RE = re.compile(r"[\"“]([^\"”]{8,})[\"”]")

_VN_FUNCTION_WORDS = {
    "và", "hoặc", "thì", "mà", "là", "của", "cho", "với", "trong", "ngoài", "trên", "dưới",
    "đó", "này", "kia", "ấy", "người", "những", "các", "một", "có", "sẽ", "đã", "đang",
    "được", "bị", "ra", "vào", "lại", "đi", "đến", "ở", "vì", "do", "tại", "về", "như",
    "để", "anh", "tôi", "em", "chị", "ông", "bà", "nó", "họ", "mình", "cô", "chú", "bác",
    "cái", "con", "chiếc", "thì", "gì", "sao", "thế", "nào", "đâu", "nữa", "rồi", "rất",
    "quá", "lắm", "vẫn", "cứ", "chỉ", "cũng", "đều", "phải", "rằng", "muốn", "cần", "nên",
    "hãy", "xin", "không", "chưa", "chẳng", "chứ",
}

_CALLBACK_MARKERS = re.compile(
    r"(?:nhớ\s+lại|nghĩ\s+lại|văng\s+vẳng|từng\s+nói|từng\s+bảo|từng\s+dặn|nhắc\s+lại|lời\s+thú\s+nhận|nghĩ\s+về\s+câu)",
    re.IGNORECASE,
)

_QUESTION_PATTERNS = re.compile(
    r"(?:\?|\b(?:sao|nào|gì|đâu|ai|mấy\s+giờ|lúc\s+nào|bao\s+giờ|phải\s+không|chưa)\b)",
    re.IGNORECASE,
)

_NEGATION_PATTERNS = re.compile(
    r"\b(?:không|chưa|chẳng|đâu\s+có)\b",
    re.IGNORECASE,
)

_PROPER_NAME_RE = re.compile(
    r"\b[A-ZÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬĐÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ][a-zàáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]+\b"
)


def repeated_dialogue_pairs(segments: List[Any], min_gap: int = 4, threshold: float = 0.6) -> List[Tuple[str, str]]:
    """(first_id, later_id) pairs where a line of dialogue is essentially said twice in separate scenes.
    
    Distinguishes genuine scene repetition from:
    - Shared function words / pronouns (người, đó, là, tôi...)
    - Disproportionate length (short confession vs long premise monologue)
    - Identity revelation / entity change (Linh Chi vs Thu Hà)
    - Question vs Answer polarity
    - Negation differences (tôi không ký vs tôi đã ký)
    - Valid callbacks and memories (nhớ lại lời anh nói...)
    """
    quotes: List[Tuple[int, str, List[str], List[str], bool, bool, bool, set]] = []

    for index, seg in enumerate(segments):
        text = str(seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", ""))
        seg_id = str(seg.get("id", "") if isinstance(seg, dict) else getattr(seg, "id", ""))
        is_callback = bool(_CALLBACK_MARKERS.search(text))

        for quote in _QUOTE_RE.findall(text):
            q_clean = quote.strip()
            all_words = [w for w in re.findall(r"\w+", q_clean.casefold()) if len(w) > 1]
            content_words = [w for w in all_words if w not in _VN_FUNCTION_WORDS]
            # Require at least 4 content words to avoid false-matching short common phrases
            if len(content_words) < 4:
                continue

            is_question = bool(_QUESTION_PATTERNS.search(q_clean))
            has_negation = bool(_NEGATION_PATTERNS.search(q_clean))
            # Proper names (excluding the sentence-initial capitalized word)
            names = set(_PROPER_NAME_RE.findall(q_clean[1:]))

            quotes.append((
                index, seg_id, all_words, content_words, is_callback, is_question, has_negation, names
            ))

    pairs: List[Tuple[str, str]] = []
    for i, (idx_a, id_a, wa, cwa, cb_a, q_a, neg_a, names_a) in enumerate(quotes):
        for idx_b, id_b, wb, cwb, cb_b, q_b, neg_b, names_b in quotes[i + 1:]:
            if idx_b - idx_a < min_gap:
                continue
            # A valid callback or memory is not a retold scene
            if cb_a or cb_b:
                continue
            # Length ratio between sentences must be balanced (cannot compare a 26-word clause to a 5-word sentence)
            len_ratio = min(len(wa), len(wb)) / max(len(wa), len(wb))
            if len_ratio < 0.45:
                continue
            # Question vs answer/statement is not repeated dialogue
            if q_a != q_b:
                continue
            # Negation polarity mismatch means opposite meaning
            if neg_a != neg_b:
                continue
            # Naming different entities indicates revelation/refutation, not duplication
            if names_a and names_b and not (names_a & names_b):
                continue

            set_a, set_b = set(cwa), set(cwb)
            shared_content = set_a & set_b
            if len(shared_content) < 3:
                continue

            # Containment made a short question about a project match any
            # longer witness question mentioning the same project. Compare
            # both lines' information, not only the smaller vocabulary.
            overlap = len(shared_content) / len(set_a | set_b)
            trigrams_a = {tuple(cwa[k:k+3]) for k in range(len(cwa)-2)}
            trigrams_b = {tuple(cwb[k:k+3]) for k in range(len(cwb)-2)}
            # Retain paraphrased repetition of a substantial ordered event
            # (e.g. My / nói / kiểm / kê / muộn) even when time-question words
            # differ. A generic shared project topic is insufficient.
            retold_event = len(shared_content) >= 5 and bool(trigrams_a & trigrams_b)
            if overlap < threshold and not retold_event:
                continue

            # Check for at least one ordered content bigram OR a 4-gram of words containing >= 2 content words
            bigrams_a = {(cwa[k], cwa[k + 1]) for k in range(len(cwa) - 1)}
            bigrams_b = {(cwb[k], cwb[k + 1]) for k in range(len(cwb) - 1)}
            shared_bigrams = bigrams_a & bigrams_b

            fourgrams_wa = {tuple(wa[k:k + 4]) for k in range(len(wa) - 3)}
            fourgrams_wb = {tuple(wb[k:k + 4]) for k in range(len(wb) - 3)}
            shared_fourgrams = fourgrams_wa & fourgrams_wb
            has_content_fourgram = any(sum(w in set_a for w in fg) >= 2 for fg in shared_fourgrams)

            if shared_bigrams or has_content_fourgram:
                pairs.append((id_a, id_b))

    return pairs
