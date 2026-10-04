"""Write the whole episode in one model call, as plain tagged lines.

The two-call writer (Part 1 / Part 2) existed because older models capped output
around 8k tokens. Current models produce a 2,500-word episode easily, and almost
every repetition defect came from the seam between the two calls (Part 2
restarting a scene Part 1 had told). Writing in one pass removes the seam, and
plain lines instead of JSON objects cost fewer tokens and read like the chat-
written EP01. If the reply is truncated or malformed the caller falls back to
the two-call writer.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("VieNeu.SinglePassWriter")

# call_text(system_instruction, prompt) -> (raw_text, input_tokens, output_tokens)
TextCall = Callable[[str, str], Tuple[str, int, int]]

MIN_SEGMENTS = 70
MIN_WORDS = 2200
# Only a complete episode far shorter than this goes to the two-part writer. A
# coherent 1,800-word episode beats a longer one that stalls and retells at the
# Part 1 / Part 2 seam (EP2009: 1,879 words discarded for a seamed 2,494).
ACCEPT_SEGMENTS = 50
ACCEPT_WORDS = 1500
_SIGNOFF_RE = re.compile(r"hẹn\s+gặp\s+lại", re.IGNORECASE)
_TAGS = ("HOOK", "NORMAL", "MYSTERY", "REVEAL", "COMMENT", "QUESTION", "ENDING")
_LINE_RE = re.compile(r"^\s*(?:[-*•]\s*)?\[(" + "|".join(_TAGS) + r")\]\s*(.+?)\s*$", re.IGNORECASE)


def build_prompt(
    title: str,
    canonical_story: str,
    user_topic_constraint: str,
    host_name: str,
    scenes: Optional[List[Dict[str, Any]]] = None,
) -> str:
    from apps.script_factory.scene_outline import single_pass_outline_block
    from apps.script_factory.narrative_design import DESIGN_INSTRUCTION, scene_word_budgets
    outline_text = single_pass_outline_block(scenes) if scenes else ""
    outline_text += '\n' + DESIGN_INSTRUCTION
    if scenes:
        outline_text += '\nNgân sách mục tiêu theo cảnh: ' + str(scene_word_budgets(scenes, 2450)) + ' từ. Không kéo dài phần kết để đạt tổng từ.\n'
    if scenes:
        outline_instruction = (
            "1. Viết tuần tự theo đúng DÀN CẢNH BẮT BUỘC ở trên: mỗi cảnh chỉ xảy ra MỘT lần, "
            "chuyển tải đúng thông tin mới được giao, không lặp lại cảnh cũ."
        )
    else:
        outline_instruction = (
            "1. Bố cục 14-18 cảnh theo thời gian; mỗi cảnh xảy ra MỘT lần và mang một thông tin mới. KHÔNG in dàn ý."
        )

    return f"""Hãy viết TRỌN VẸN kịch bản tập '{title}' trong MỘT lần trả lời.
(Các quy tắc có nhắc tới PHẦN 1 / PHẦN 2 hoặc "object cuối cùng" áp dụng cho cả tập viết một lần: lời chào kết chỉ ở dòng cuối cùng.)

STORY BIBLE ĐẦY ĐỦ (nguồn chuẩn cho nhân vật, thời gian, bằng chứng và kết thúc; chỉ kể điều nhân vật biết tại từng thời điểm):
{canonical_story}
{user_topic_constraint}
{outline_text}
CÁCH LÀM:
{outline_instruction}
2. Viết liền một mạch như kể cho người nghe. Không quay lại kể lại một cảnh, cuộc gọi hay lần lục tìm đã kể.
3. NGUYÊN TẮC GIỚI THIỆU THÔNG TIN (INFORMATION GROUNDING):
   - Mọi tên nhân vật mới (người thứ ba, đồng phạm, con riêng) và đạo cụ/tài liệu quan trọng (hợp đồng, hóa đơn, sao kê, chìa khóa) PHẢI được giới thiệu bối cảnh phát hiện (nhìn thấy, nghe gọi tên, đọc trên biển tên/giấy tờ) TRƯỚC KHI được người kể chuyện hay nhân vật gọi tên như điều đã biết. Tuyệt đối không đột ngột gọi tên một nhân vật khi chưa có cảnh xác định danh tính.
   - Nghe tên không có nghĩa đã biết mặt. Muốn nhận ra người trong ảnh phải có cảnh từng gặp, chú thích ảnh rõ tên hoặc nguồn xác nhận độc lập. Trước khi nghe thú nhận về quan hệ quá khứ, nhân vật chỉ được hỏi điều đã biết, không hỏi như thể đã biết người yêu cũ. Thông tin tương lai trong Bible không phải kiến thức hiện tại của nhân vật.
   - Bằng chứng phải được tìm thấy rồi ĐỌC NỘI DUNG cụ thể trước khi dùng để kết luận hoặc đối chất. Nêu thông tin nào trong chứng cứ hỗ trợ kết luận nào; một suy đoán vẫn phải được kể là suy đoán cho đến khi có xác nhận độc lập hoặc lời thú nhận có cơ sở. Không suy ra danh tính từ dấu công cụ, ảnh chụp, tên lưu trong điện thoại hoặc chữ viết giống nhau; không coi giấy khám sức khỏe hay lịch tái khám là hồ sơ xác nhận người hiến tạng.
   - Giữ đúng từng nhân vật, sự kiện và năm trong Bible, kể cả năm viết bằng chữ và khoảng thời gian tương đối. Phân biệt lúc bắt đầu mắc bệnh với lúc thực hiện phẫu thuật. Nếu Bible tự mâu thuẫn, không tự chọn một dữ kiện rồi bịa chi tiết để hòa giải.
   - Khi nhắc lại bằng chứng ở cảnh sau, phải giữ tính nhất quán về nguồn gốc và tên gọi (nếu tìm thấy "ghi chú trong cặp tài liệu" thì không đột ngột đổi thành "tập hợp đồng kinh tế" mà không có hành động xem hợp đồng).
4. NGUYÊN TẮC SETUP & PAYOFF:
   - Bất kỳ chi tiết, vật phẩm hay câu hỏi nào được gieo ở phần Hook/Setup (chiếc hộp, phong bì niêm phong, máy tính bảng, tờ hóa đơn...) BẮT BUỘC phải có đáp án cụ thể ở phần thân truyện hoặc hồi kết. Mở phong bì, nhìn ảnh hay nói "đối chiếu sự thật" chưa phải đáp án: phải kể nội dung đã đọc, nguồn xác nhận và ý nghĩa của nó. Kết thúc giữ đúng hành động và số phận vật phẩm trong Bible; không tự đổi giữ thành trả lại hoặc tiêu hủy.
5. DỰNG CẢNH SỐNG ĐỘNG BẰNG HÀNH ĐỘNG VÀ ĐỐI THOẠI:
   - Các cảnh then chốt (phát hiện manh mối, đối chất, chia tay) PHẢI được viết bằng hành động cụ thể, biểu cảm và lời thoại trực tiếp đặt trong dấu ngoặc kép "...". Không tóm tắt cảnh bằng "anh kể rằng…", "anh viết rằng…", "sau một hồi đối chất thì anh thú nhận...".
   - Mỗi cảnh làm thay đổi điều nhân vật biết, lựa chọn tiếp theo hoặc cái giá phải trả. Một lần hỏi người chồng và một lần hỏi nhân chứng có thể kiểm chứng cùng sự kiện nhưng phải đem lại thông tin khác nhau và tác động khác nhau. Không kéo dài bằng nhiều đoạn xếp giấy, định hỏi, nhắc nghi ngờ hoặc 'chưa đủ để kết luận'.
   - Kể rõ chuyển địa điểm trước hành động vật lý: đang trên đường chỉ suy nghĩ/gọi điện; về đến nhà rồi mới đặt sổ/ảnh trên bàn. Lời người khác nói là thông tin nhớ lại, không phải đồ vật có thể đặt cạnh một cuốn sổ. Mỗi nhân chứng/cuộc gọi phải có nguồn liên hệ tự nhiên trong Bible, không để số điện thoại hoặc địa chỉ tự xuất hiện.
   - Thận trọng thể hiện qua câu hỏi, hành động và lời thoại; không để MC liên tục giảng giới hạn chứng cứ. Khi mở nút thắt, cho người nghe biết thêm điều đã có trong Bible làm thay đổi cách hiểu dấu hiệu ban đầu, không chỉ lặp lại danh tính đã đoán rõ từ giữa tập.
6. KỂ ĐÚNG MỘT LẦN DUY NHẤT:
   - Kể toàn bộ câu chuyện một lần từ đầu đến cuối, kết thúc bằng dòng [ENDING] chào tạm biệt.
   - TUYỆT ĐỐI KHÔNG bắt đầu lại câu chuyện, KHÔNG lặp lại câu chào mừng "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa" ở giữa hoặc cuối, KHÔNG viết phiên bản thứ hai ở nửa sau.

ĐỘ DÀI: 70-85 dòng, 2.200-2.700 từ (phù hợp thời lượng nghe 18-22 phút của podcast Sau Cánh Cửa).

CẤU TRÚC VÀ SỐ DÒNG (ĐÚNG HỢP ĐỒNG NHỊP KỂ):
- Mở đầu & Hook (4 dòng): 2-3 dòng [HOOK] mở bằng câu trích lá thư gắn với vật phẩm/dấu hiệu cụ thể; dòng tiếp theo đúng nguyên văn: "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa."
- Đời sống thường ngày & Vết nứt (8-10 dòng): nhân vật, chi tiết riêng tư của gia đình, nhịp sinh hoạt sẽ bị phá vỡ.
- Dấu hiệu lạ và giả thuyết sai (10-12 dòng): dấu hiệu đầu tiên; giả thuyết sai mà người nghe cũng tin.
- Kiểm chứng thực địa (16-20 dòng): nhân vật chủ động tìm hiểu; bằng chứng tăng dần, mỗi lần một thông tin mới.
- Bước ngoặt 1 (Reveal 1, khoảng 65-72% tập, ~dòng 48-56): manh mối giả bị lật tẩy, hé lộ sự thật tầng thứ nhất.
- Cú lật chính (Reveal 2, khoảng 76-85% tập, ~dòng 58-68): bí mật cốt lõi và động cơ thật được phơi bày trọn vẹn qua bằng chứng không thể chối cãi, các dòng mở nút thắt dùng [REVEAL], không hỏi người nghe trong [REVEAL].
- Đối chất/thú nhận (10-12 dòng, khoảng 80-88% tập): cuộc gặp trực tiếp hai phía, đối chất bằng chứng thực tế, có lời thoại trực tiếp trong ngoặc kép.
- Giải quyết bằng hành động (6-8 dòng, khoảng 86-93% tập): hành động dứt khoát về pháp lý hoặc chia tay thanh thản, bảo vệ con cái, không đánh ghen ầm ĩ.
- Kết (3 dòng): 1 dòng chiêm nghiệm [COMMENT], 1 câu hỏi người nghe [QUESTION], rồi dòng cuối cùng [ENDING] đúng nguyên văn: "Cảm ơn quý vị đã lắng nghe. Tôi là {host_name}. Xin chào và hẹn gặp lại."
- Rải 3-5 dòng [QUESTION] hỏi người nghe trong cả tập (không đặt trong cảnh REVEAL).

ĐỊNH DẠNG TRẢ VỀ (chỉ các dòng sau, không tiêu đề, không giải thích, không JSON):
Mỗi dòng = một phân đoạn đọc, 1-3 câu, bắt đầu bằng một nhãn:
[HOOK] ...  [NORMAL] ...  [MYSTERY] ...  [REVEAL] ...  [COMMENT] ...  [QUESTION] ...  [ENDING] ...
Ví dụ:
[HOOK] "Câu trích lá thư." Dòng mở đầu của người gửi thư.
[NORMAL] Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.
"""


def parse_tagged_lines(raw: str) -> List[Dict[str, Any]]:
    """Turns '[TAG] text' lines into segment dicts; untagged lines continue the previous one."""
    segments: List[Dict[str, Any]] = []
    for line in raw.replace("\r", "").split("\n"):
        stripped = line.strip().strip("`")
        if not stripped:
            continue
        match = _LINE_RE.match(stripped)
        if match:
            tag, text = match.group(1).upper(), match.group(2).strip()
            if not text:
                continue
            segments.append({
                "text": text,
                "delivery_profile": "COMMENT" if tag == "QUESTION" else tag,
                "audience_address": tag == "QUESTION",
            })
        elif segments and not stripped.startswith("#"):
            # A wrapped line belongs to the segment above it.
            segments[-1]["text"] = f"{segments[-1]['text']} {stripped}"
    from apps.script_factory.vietnamese_cleaner import clean_garbled_vietnamese
    for seg in segments:
        seg["text"] = clean_garbled_vietnamese(seg["text"])
    return segments


def build_expand_prompt(prompt: str, draft: List[Dict[str, Any]]) -> str:
    words = _word_count(draft)
    draft_text = "\n".join(f"[{_tag(seg)}] {seg['text']}" for seg in draft)
    return f"""{prompt}

BẢN NHÁP TRƯỚC (đúng cốt truyện nhưng QUÁ NGẮN: {len(draft)} dòng, {words} từ):
{draft_text}

YÊU CẦU: Viết lại TOÀN BỘ tập thành một bản hoàn chỉnh duy nhất 70-85 dòng, 2.200-2.700 từ, cùng định dạng dòng có nhãn.
- CHỈ TRẢ VỀ DUY NHẤT BẢN MỚI ĐÃ MỞ RỘNG (từ [HOOK] mở đầu đến [ENDING] chào kết). Tuyệt đối KHÔNG in lại bản nháp cũ rồi mới viết bản mới!
- Giữ nguyên cốt truyện, thứ tự cảnh, tên người, mốc thời gian và kết thúc của bản nháp.
- Dài ra bằng cách DỰNG CẢNH: ở các cảnh phát hiện, kiểm chứng, cú lật và đối chất, viết hành động cụ thể, lời thoại trực tiếp và cảm giác của người gửi thư ngay lúc đó; thay các câu tóm tắt "anh kể rằng…" bằng chính cảnh ấy.
- Không thêm sự kiện hay bằng chứng ngoài story bible; không kể lại một cảnh hai lần.
"""


def build_resolution_prompt(prompt: str, segments: List[Dict[str, Any]], insert_at: int, ending: str) -> str:
    before = "\n".join(f"[{_tag(seg)}] {seg['text']}" for seg in segments[max(0, insert_at - 12):insert_at])
    return f"""{prompt}

BẢN KỊCH BẢN ĐÃ VIẾT BỎ QUA PHẦN GIẢI QUYẾT: sau cảnh đối chất, nó nhảy thẳng tới lời chiêm nghiệm và lời chào, nên người nghe không biết chuyện gì xảy ra tiếp theo.
KẾT THÚC TRONG STORY BIBLE (phải được kể ra):
{ending}

CÁC DÒNG NGAY TRƯỚC CHỖ CẦN CHÈN:
{before}

YÊU CẦU: Chỉ viết 5-7 dòng [NORMAL] kể phần giải quyết bằng HÀNH ĐỘNG theo đúng kết thúc trên, nối tiếp ngay sau các dòng trên.
- Không lặp lại lời thú nhận hay cuộc đối chất đã kể; không chiêm nghiệm; không hỏi người nghe; không lời chào.
- Có con cái/người thân trong nhà thì cho thấy họ trong lúc gia đình thay đổi.
"""


def _tag(seg: Dict[str, Any]) -> str:
    return "QUESTION" if seg.get("audience_address") else seg["delivery_profile"]


def _word_count(segments: List[Dict[str, Any]]) -> int:
    return sum(len(seg["text"].split()) for seg in segments)


def _is_complete(segments: List[Dict[str, Any]]) -> bool:
    """A reply cut off by the output limit never reaches the sign-off line."""
    return any(seg["delivery_profile"] == "ENDING" or _SIGNOFF_RE.search(seg["text"]) for seg in segments[-3:])


def _is_long_enough(segments: List[Dict[str, Any]]) -> bool:
    # A draft with >= 65 segments and >= 2000 words is well-paced and complete;
    # forcing an expand pass tends to introduce repetitive narrative padding.
    if len(segments) >= 65 and _word_count(segments) >= 2000:
        return True
    return len(segments) >= MIN_SEGMENTS and _word_count(segments) >= MIN_WORDS


def _ensure_resolution(
    call_text: TextCall, system_instruction: str, prompt: str, segments: List[Dict[str, Any]], ending: str
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Inserts resolution lines before the closing block when the ending never airs."""
    from apps.script_factory.script_craft import ENDING_COVERAGE_MIN, closing_block_start, ending_coverage

    coverage = ending_coverage([seg["text"] for seg in segments], ending)
    if coverage is None or coverage >= ENDING_COVERAGE_MIN:
        return segments, 0, 0
    insert_at = closing_block_start(segments)
    logger.info(f"[SinglePassWriter] Bản viết bỏ qua phần giải quyết (độ phủ kết thúc {coverage:.2f}); viết bổ sung.")
    try:
        raw, in_tok, out_tok = call_text(system_instruction, build_resolution_prompt(prompt, segments, insert_at, ending))
    except Exception as exc:
        logger.warning(f"[SinglePassWriter] Viết bổ sung phần giải quyết thất bại: {exc}")
        return segments, 0, 0
    lines = [
        seg for seg in parse_tagged_lines(raw)
        if seg["delivery_profile"] in ("NORMAL", "MYSTERY") and not seg["audience_address"] and not _SIGNOFF_RE.search(seg["text"])
    ][:9]
    if len(lines) < 3:
        return segments, in_tok, out_tok
    for seg in lines:
        seg["delivery_profile"] = "NORMAL"
    return segments[:insert_at] + lines + segments[insert_at:], in_tok, out_tok


def write_single_pass(
    call_text: TextCall, system_instruction: str, prompt: str, ending: str = ""
) -> Tuple[Optional[List[Dict[str, Any]]], int, int]:
    """Returns (segment dicts or None to fall back, input_tokens, output_tokens)."""
    from apps.script_factory.narrative_continuity import find_repeated_narrative_block, has_repeated_narrative_block
    from apps.script_factory.providers.gemini_provider import _has_one_final_signoff, _normalize_final_signoff

    in_total = out_total = 0
    try:
        raw, in_tok, out_tok = call_text(system_instruction, prompt)
    except Exception as exc:
        logger.warning(f"[SinglePassWriter] Một lần gọi thất bại, chuyển sang viết 2 phần: {exc}")
        return None, 0, 0
    in_total, out_total = in_tok, out_tok
    segments = parse_tagged_lines(raw)
    if not _is_complete(segments):
        logger.warning(
            f"[SinglePassWriter] Bản viết một lần dừng giữa chừng ({len(segments)} đoạn, chưa tới lời chào kết); "
            "chuyển sang viết 2 phần."
        )
        return None, in_total, out_total

    if not _is_long_enough(segments):
        logger.info(
            f"[SinglePassWriter] Bản viết một lần đủ truyện nhưng ngắn ({len(segments)} đoạn, {_word_count(segments)} từ); "
            "viết lại toàn bộ cho dài hơn."
        )
        try:
            raw2, in_tok, out_tok = call_text(system_instruction, build_expand_prompt(prompt, segments))
            in_total, out_total = in_total + in_tok, out_total + out_tok
            expanded = parse_tagged_lines(raw2)
            if _is_complete(expanded) and _word_count(expanded) > _word_count(segments):
                # If expanded echoed both drafts, extract the second complete draft
                rep_exp = find_repeated_narrative_block(expanded)
                if rep_exp and rep_exp.get("first_start", 0) <= 4 and rep_exp.get("second_start", 0) >= ACCEPT_SEGMENTS:
                    second_half = expanded[rep_exp["second_start"]:]
                    if _is_complete(second_half) and len(second_half) >= ACCEPT_SEGMENTS:
                        logger.info(
                            f"[SinglePassWriter] Bản mở rộng chứa 2 phiên bản; chọn phần sau "
                            f"({len(second_half)} đoạn, {_word_count(second_half)} từ)."
                        )
                        expanded = second_half
                segments = expanded
        except Exception as exc:
            logger.warning(f"[SinglePassWriter] Lần viết dài hơn thất bại: {exc}")

    if len(segments) < ACCEPT_SEGMENTS or _word_count(segments) < ACCEPT_WORDS:
        logger.warning(
            f"[SinglePassWriter] Vẫn quá ngắn ({len(segments)} đoạn, {_word_count(segments)} từ); chuyển sang viết 2 phần."
        )
        return None, in_total, out_total
    segments, in_tok, out_tok = _ensure_resolution(call_text, system_instruction, prompt, segments, ending)
    in_total, out_total = in_total + in_tok, out_total + out_tok
    if not _has_one_final_signoff(segments):
        segments = _normalize_final_signoff(segments)

    # If the episode itself contains a distant restart from the beginning, prune it
    rep = find_repeated_narrative_block(segments)
    if rep and rep.get("first_start", 0) <= 4 and rep.get("second_start", 0) >= ACCEPT_SEGMENTS:
        second_half = segments[rep["second_start"]:]
        prefix = segments[:rep["second_start"]]
        if _is_complete(second_half) and len(second_half) >= ACCEPT_SEGMENTS and not has_repeated_narrative_block(second_half):
            logger.warning(
                f"[SinglePassWriter] Phát hiện khởi động lại toàn bộ tập từ đoạn {rep['second_start']}; "
                f"chọn phần sau ({len(second_half)} đoạn)."
            )
            segments = second_half
        elif len(prefix) >= ACCEPT_SEGMENTS and any(s.get("delivery_profile") == "REVEAL" for s in prefix):
            logger.warning(
                f"[SinglePassWriter] Phát hiện khởi động lại toàn bộ tập từ đoạn {rep['second_start']}; "
                f"cắt bỏ phần lặp sau ({len(segments)} -> {len(prefix)} đoạn)."
            )
            segments = prefix
            if not _has_one_final_signoff(segments):
                segments = _normalize_final_signoff(segments)

    if has_repeated_narrative_block(segments):
        logger.warning("[SinglePassWriter] Bản viết một lần vẫn có khối kể lặp; để QC xử lý.")
    logger.info(f"[SinglePassWriter] Viết một lần: {len(segments)} đoạn, {_word_count(segments)} từ")
    return segments, in_total, out_total
