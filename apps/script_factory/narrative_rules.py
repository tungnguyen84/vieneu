"""Story-logic rules shared by the script writer prompts and the semantic QC review.

The writer is told these rules up front and the reviewer checks the same list,
so a script is judged against exactly what it was asked to do.
"""
from __future__ import annotations

from typing import Iterable, Optional

# (rule code, what the writer must do / what the reviewer flags)
NARRATIVE_LOGIC_RULES = [
    (
        "CHARACTER_IDENTITY_CONTRADICTION",
        "Tên, quan hệ gia đình, tuổi và vai trò nhân vật phải nhất quán giữa danh sách nhân vật, timeline, "
        "manh mối và reveal. Không biến mẹ vợ thành mẹ chồng, nhân vật đã mất thành người còn sống, "
        "hoặc người đã tốt nghiệp thành thực tập sinh nhiều năm sau mà không giải thích.",
    ),
    (
        "TOPIC_TRUTH_DRIFT",
        "Giữ sự thật trung tâm đúng chủ đề người dùng yêu cầu. Nếu đề tài là bí mật ngoại tình công sở, "
        "không thay ngoại tình bằng hiểu lầm về anh em ruột, con riêng hoặc một bí mật không có quan hệ ngoài luồng. "
        "Chỉ được dùng cú lật minh oan khi đề tài gốc yêu cầu nghi ngờ hoặc hiểu lầm.",
    ),
    (
        "ACTION_SEQUENCE_INVERSION",
        "Hành động phải đủ điều kiện trước khi xảy ra: cửa được mở trước khi khách bước vào; "
        "tài liệu được tiếp cận trước khi đọc; lời mời có trước cuộc gặp. Kiểm tra cả hai câu liền nhau, "
        "không chỉ mốc ngày tháng. Không báo lỗi cho hồi tưởng đã được dẫn rõ.",
    ),
    (
        "KNOWLEDGE_STATE_REGRESSION",
        "Theo dõi điều nhân vật đã biết sau mỗi bằng chứng. Sau khi đã đọc chứng cứ về gian lận, "
        "không được kể nhân vật vẫn tưởng chỉ có ngoại tình nếu không có lý do phủ nhận chứng cứ. "
        "Cú lật sau phải bổ sung sự thật mới, không xóa phát hiện trước. Trích cả đoạn phát hiện và đoạn mâu thuẫn. "
        "Không coi khăn tay hoặc chuyển tiền đơn lẻ là bằng chứng chắc chắn của ngoại tình; nhân vật vẫn được "
        "nghi ngờ và hỏi thêm trước khi có lời thừa nhận hoặc bằng chứng rõ ràng.",
    ),
    (
        "SUMMARY_INSTEAD_OF_SCENE",
        "Hook và các cảnh then chốt cần hành động, chi tiết và phản ứng cụ thể. Không thay cuộc đối chất "
        "hoặc khám phá bằng tóm tắt phân tích, kết luận trừu tượng hay hàng loạt ẩn dụ sáo rỗng. "
        "Chỉ báo lỗi khi việc tóm tắt làm mất nội dung/bằng chứng cần để hiểu cảnh, không cấm mọi câu chuyển đoạn.",
    ),
    (
        "POV_KNOWLEDGE_VIOLATION",
        "Câu chuyện là lá thư của nhân vật chính gửi về chương trình. Người kể chỉ biết điều nhân vật chính "
        "tận mắt thấy, tận tai nghe, đọc được trong tài liệu, hoặc được nhân vật khác TỰ NÓI RA trong đối thoại. "
        "Kế hoạch, động cơ kín hay toan tính của nhân vật khác chỉ được xác nhận khi chính "
        "họ thú nhận bằng lời thoại hoặc có tài liệu ghi lại. Khi bằng chứng chỉ cho phép suy luận, được kể nhận định "
        "của nhân vật chính bằng những cách như 'cô nghĩ', 'qua những tin nhắn, cô hiểu rằng'; phải gắn với hành vi "
        "cụ thể đã được kể và không biến suy luận ấy thành sự xác nhận về một ý định bí mật chưa được tiết lộ. "
        "Cảm xúc bộc lộ trong cuộc gặp hoặc hành động đã kể có thể được mô tả tự nhiên; không bắt mỗi câu "
        "lặp lại 'cô nghĩ' hay 'cô cảm nhận' khi góc nhìn và nguồn quan sát đã rõ.",
    ),
    (
        "INFEASIBLE_EVIDENCE",
        "Mọi bằng chứng phải khả thi ngoài đời thực. Xét nghiệm ADN thai nhi cần mẫu máu người mẹ (có sự đồng ý); "
        "xét nghiệm cha con sau sinh cần mẫu của đứa trẻ. Không có thư mục/phân vùng 'ẩn' xuất hiện thần kỳ, "
        "không có tài liệu tự giải thích toàn bộ âm mưu. "
        "Bằng chứng phải là thứ NGƯỜI THƯỜNG có được: đồ vật trong nhà, máy/tài khoản dùng chung của gia đình, điều tận mắt thấy hoặc nghe được, lời người quen kể, ảnh trên mạng xã hội, vật để quên. KHÔNG dùng camera của khách sạn/quán/tòa nhà/công ty, lịch sử thanh toán hay sao kê của người khác, hợp đồng thuê nhà, dữ liệu do công ty/khách sạn/ngân hàng cung cấp cho người hỏi; ngoài đời họ không cung cấp, và viết 'theo quy trình' không làm nó thật hơn.",
    ),
    (
        "CONCLUSION_BEFORE_PROOF",
        "Không khẳng định sự thật (huyết thống, ngoại tình, gian lận) trước thời điểm bằng chứng quyết định "
        "được kể ra trong truyện. Trước đó chỉ là nghi ngờ của nhân vật.",
    ),
    (
        "UNRESOLVED_SETUP",
        "Mọi thứ đã được gài, kể cả vật/chi tiết được hứa trong tiêu đề, phải được trả: nếu có kết quả xét nghiệm, phong bì, tin nhắn chưa đọc… thì nhân vật "
        "phải đọc nó và người nghe phải biết nội dung. Không dùng một vật chứng mà chính nhân vật chính chưa xem. "
        "Người thân đã xuất hiện (con cái, cha mẹ) phải được nhắc tới khi hoàn cảnh gia đình thay đổi (ly thân, dọn đi). "
        "Mỗi vật chứng đã dẫn dắt nghi ngờ (kẹp tóc, áo khoác, tin nhắn…) phải được giải thích là của ai, từ đâu ra khi sự thật "
        "lộ diện; vật chứng gài cho hướng nghi sai cũng phải được trả lời, không bị bỏ lửng. "
        "CHỈ BÁO LỖI KHI CHI TIẾT BỊ BỎ QUÊN HOÀN TOÀN ĐẾN HẾT TRUYỆN; KHÔNG BÁO LỖI KHI CHI TIẾT ĐƯỢC GIẢI MÃ HOẶC ĐỐI CHIẾU Ở CẢNH REVEAL/PAYOFF PHÍA SAU.",
    ),
    (
        "REVEAL_LEAKED_EARLY",
        "Danh tính hay sự thật của cú lật chính không được ai nói ra hoặc gợi thẳng trước cảnh lật. Nhân chứng xuất hiện "
        "trước cú lật chỉ được cung cấp chi tiết khớp với hướng nghi sai hoặc chi tiết mơ hồ; không có người quen nào nói "
        "'tôi thấy anh ấy và <người thật> khá thân' ở giữa truyện, vì người nghe sẽ đoán ra trước. Không báo lỗi cho "
        "manh mối nhỏ chỉ được hiểu lại SAU cú lật.",
    ),
    (
        "UNMOTIVATED_DISCLOSURE",
        "Người đang che giấu (người thứ ba, người phản bội, kẻ lừa đảo) chỉ thú nhận khi bị đặt trước bằng chứng cụ thể "
        "không thể chối hoặc có lý do rõ ràng (muốn chấm dứt, bị lộ trước người khác). Không để họ tự khai ngay khi vừa "
        "bị hỏi. Khi bị dọa bằng một cái tên SAI ('em biết chuyện anh với X rồi'), người che giấu sẽ chối hoặc hỏi lại, "
        "không tự nhắc tên người thật hay chi tiết chưa ai biết; tự lộ kiểu đó là lỗi, không phải cú lật.",
    ),
    (
        "TIMELINE_ORDER_ERROR",
        "Kể theo đúng trình tự thời gian; không kể 'ba ngày trôi qua' rồi quay lại tối hôm đó; không kể cùng một "
        "khoảng thời gian hai lần. Cảnh HOOK mở đầu phải trùng khớp chi tiết với cảnh tương ứng ở thân truyện.",
    ),
    (
        "REPEATED_DISCOVERY",
        "Mỗi lần lục soát, mỗi cuộc gọi, mỗi phát hiện chỉ kể một lần. Không để nhân vật mở lại cùng một vật "
        "nhiều lần để 'tìm thêm' bằng chứng mới xuất hiện tiện lợi. Nhân vật được kể ngắn gọn phát hiện "
        "đã biết cho người khác để xin xác minh; không gọi việc chia sẻ thông tin là khám phá lại. "
        "Một cuộc gặp sau bổ sung lý do sa thải chưa biết là diễn biến mới, không phải kể lại việc bị sa thải.",
    ),
    (
        "LEGAL_OR_MEDICAL_UNREALISTIC",
        "Thủ tục pháp lý và y tế phải đúng thực tế Việt Nam: con sinh ra trong thời kỳ hôn nhân mặc nhiên là con "
        "chung, muốn xác định không phải cha con phải yêu cầu Tòa án; không có thủ tục 'từ bỏ quyền làm cha'. "
        "Người chồng không được yêu cầu ly hôn khi vợ đang mang thai, sinh con hoặc nuôi con dưới 12 tháng tuổi "
        "(Điều 51 Luật Hôn nhân và Gia đình); giới hạn này KHÔNG áp dụng cho yêu cầu Tòa án xác định cha, mẹ, con "
        "(gọi đúng là 'yêu cầu xác định con', không phải 'khởi kiện không nhận con'). "
        "Không có phán quyết, bắt giữ hay vô hiệu hóa tức thời.",
    ),
    (
        "ANALYST_NARRATION",
        "Người kể là MC kể chuyện, không phải người lập biên bản. Không viết 'Manh mối thứ ba này chứng minh…', "
        "'điều này chưa chứng minh được…'. Thể hiện giới hạn của bằng chứng qua suy nghĩ, do dự và câu hỏi của nhân vật.",
    ),
    (
        "GARBLED_VIETNAMESE",
        "Không có từ sai chính tả hay thành ngữ bị viết méo (ví dụ 'đầu ối tay kề' thay cho 'đầu ấp tay gối', "
        "'nặng nhề', 'nấp ló'); TTS sẽ đọc nguyên văn nên mỗi lỗi đều lộ ra trong audio.",
    ),
    (
        "IMPLAUSIBLE_BEHAVIOR",
        "Hành động của nhân vật phải có lý do hợp lý trong hoàn cảnh: người che giấu bí mật không tự để lộ một "
        "cách vô lý mà không có giải thích; nhân vật không biết điều mình không thể biết.",
    ),
    (
        "GENERIC_PHILOSOPHICAL_HOOK",
        "Phân đoạn mở đầu (Hook) phải mở ngay bằng nhân vật cụ thể, hành động hoặc chi tiết hữu hình của lá thư gửi về. "
        "Tuyệt đối không mở bằng triết lý chung chung, châm ngôn sáo rỗng về cuộc đời, thời gian hay hôn nhân "
        "('Trong cuộc sống...', 'Có những bí mật...', 'Đằng sau cánh cửa cuộc đời...', 'Mỗi gia đình đều có...'). "
        "Không mở bằng mô tả chung về nét chữ, trang giấy của lá thư gửi chương trình nếu lá thư không phải vật chứng "
        "trong cốt truyện. Mở ngay bằng nhân vật gặp dấu hiệu bất thường, rồi mới chào và giới thiệu.",
    ),
    (
        "OBJECT_CONTINUITY_CONTRADICTION",
        "Đạo cụ, hiện vật và bằng chứng phải nhất quán xuyên suốt câu chuyện: không đổi từ hộp các-tông thành hộp gỗ, "
        "không để bưu thiếp vừa rơi khỏi sổ vừa nằm trong phong bì niêm phong cùng biên lai; chuyển cảnh phải liền mạch, logic. "
        "Theo dõi AI đang giữ đồ vật ở từng cảnh, và mỗi thay đổi trạng thái (đóng tài khoản, dọn ra ở riêng, trả lại đồ) "
        "chỉ xảy ra MỘT lần.",
    ),
    (
        "QC_REPORT_TONE_LEAKAGE",
        "Lời dẫn của MC Minh phải tự nhiên, mang tính kể chuyện đời thường, không mang giọng văn báo cáo phân tích QC "
        "hay lập luận máy móc (ví dụ lặp cấu trúc 'chỉ chứng minh... hoàn toàn không chứng minh...', 'vật chứng này chứng thực...').",
    ),
]

LOGIC_RULE_CODES = {code for code, _ in NARRATIVE_LOGIC_RULES}

# Judgement calls / subjective style critiques from LLM reviewers that are reported
# as editor warnings. Objective plot logic rules (POV violations, timeline order inversions,
# repeated discoveries, infeasible evidence, legal issues) are objective defects that BLOCK
# approval and trigger repair when verified with grounded quotes.
JUDGEMENT_RULES = {
    "IMPLAUSIBLE_BEHAVIOR",
    "ANALYST_NARRATION",
    "GENERIC_PHILOSOPHICAL_HOOK",
    "SUMMARY_INSTEAD_OF_SCENE",
    "QC_REPORT_TONE_LEAKAGE",
}


def is_blocking_logic_issue(issue: dict) -> bool:
    rule = str(issue.get("rule", "") or issue.get("type", "")).strip().upper()
    if not rule or rule in JUDGEMENT_RULES:
        return False
    return rule in LOGIC_RULE_CODES or rule in {
        "PROP_LOCATION_CONTRADICTION", "HOOK_TIMELINE_CONTRADICTION",
        "REPEATED_SCENE_DIALOGUE", "UNRESOLVED_CORE_PROP",
    }


def writer_rules_block(start_index: int) -> str:
    """Numbered rules appended to a writer system instruction."""
    lines = []
    for offset, (code, text) in enumerate(NARRATIVE_LOGIC_RULES):
        lines.append(f"{start_index + offset}. LOGIC – {code}: {text}")
    return "\n".join(lines)


def reviewer_checklist(only: Optional[Iterable[str]] = None) -> str:
    allowed = set(only) if only is not None else LOGIC_RULE_CODES
    return "\n".join(f"- {code}: {text}" for code, text in NARRATIVE_LOGIC_RULES if code in allowed)


# Replaces the old Act 7 instruction that asked the narrator to explain the
# antagonist's WHY/MOTIVATION/HOW directly, which forced POV violations.
ACT7_CAUSAL_INSTRUCTION = (
    "   - Bước ngoặt 2 làm rõ chuỗi nhân quả (nguyên nhân -> lý do không làm cách thông thường -> cách thực hiện -> hệ quả), "
    "NHƯNG chỉ qua kênh mà nhân vật chính tiếp cận được: lời thú nhận trực tiếp trong đối thoại, lời kể của nhân chứng, "
    "hoặc tài liệu cụ thể nhân vật chính đọc thấy. Người kể KHÔNG tự thuật lại suy nghĩ hay động cơ bên trong của nhân vật khác.\n"
    "   - Dữ liệu chuỗi nhân quả trong Story Bible chỉ để hiểu câu chuyện, không được đọc lại thành câu văn."
)
