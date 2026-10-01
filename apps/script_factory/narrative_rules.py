"""Story-logic rules shared by the script writer prompts and the semantic QC review.

The writer is told these rules up front and the reviewer checks the same list,
so a script is judged against exactly what it was asked to do.
"""
from __future__ import annotations

from typing import Iterable, Optional

# (rule code, what the writer must do / what the reviewer flags)
NARRATIVE_LOGIC_RULES = [
    (
        "POV_KNOWLEDGE_VIOLATION",
        "Câu chuyện là lá thư của nhân vật chính gửi về chương trình. Người kể chỉ biết điều nhân vật chính "
        "tận mắt thấy, tận tai nghe, đọc được trong tài liệu, hoặc được nhân vật khác TỰ NÓI RA trong đối thoại. "
        "Suy nghĩ, động cơ, cảm xúc bên trong, sự bất cẩn hay toan tính của nhân vật khác chỉ được kể khi chính "
        "họ thú nhận bằng lời thoại hoặc có tài liệu ghi lại.",
    ),
    (
        "INFEASIBLE_EVIDENCE",
        "Mọi bằng chứng phải khả thi ngoài đời thực. Xét nghiệm ADN thai nhi cần mẫu máu người mẹ (có sự đồng ý); "
        "xét nghiệm cha con sau sinh cần mẫu của đứa trẻ. Không có thư mục/phân vùng 'ẩn' xuất hiện thần kỳ, "
        "không có tài liệu tự giải thích toàn bộ âm mưu.",
    ),
    (
        "CONCLUSION_BEFORE_PROOF",
        "Không khẳng định sự thật (huyết thống, ngoại tình, gian lận) trước thời điểm bằng chứng quyết định "
        "được kể ra trong truyện. Trước đó chỉ là nghi ngờ của nhân vật.",
    ),
    (
        "UNRESOLVED_SETUP",
        "Mọi thứ đã được gài phải được trả: nếu có kết quả xét nghiệm, phong bì, tin nhắn chưa đọc… thì nhân vật "
        "phải đọc nó và người nghe phải biết nội dung. Không dùng một vật chứng mà chính nhân vật chính chưa xem.",
    ),
    (
        "TIMELINE_ORDER_ERROR",
        "Kể theo đúng trình tự thời gian; không kể 'ba ngày trôi qua' rồi quay lại tối hôm đó; không kể cùng một "
        "khoảng thời gian hai lần. Cảnh HOOK mở đầu phải trùng khớp chi tiết với cảnh tương ứng ở thân truyện.",
    ),
    (
        "REPEATED_DISCOVERY",
        "Mỗi lần lục soát, mỗi cuộc gọi, mỗi phát hiện chỉ kể một lần. Không để nhân vật mở lại cùng một vật "
        "nhiều lần để 'tìm thêm' bằng chứng mới xuất hiện tiện lợi.",
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
        "('Trong cuộc sống...', 'Có những bí mật...', 'Đằng sau cánh cửa cuộc đời...', 'Mỗi gia đình đều có...').",
    ),
    (
        "OBJECT_CONTINUITY_CONTRADICTION",
        "Đạo cụ, hiện vật và bằng chứng phải nhất quán xuyên suốt câu chuyện: không đổi từ hộp các-tông thành hộp gỗ, "
        "không để bưu thiếp vừa rơi khỏi sổ vừa nằm trong phong bì niêm phong cùng biên lai; chuyển cảnh phải liền mạch, logic.",
    ),
    (
        "QC_REPORT_TONE_LEAKAGE",
        "Lời dẫn của MC Minh phải tự nhiên, mang tính kể chuyện đời thường, không mang giọng văn báo cáo phân tích QC "
        "hay lập luận máy móc (ví dụ lặp cấu trúc 'chỉ chứng minh... hoàn toàn không chứng minh...', 'vật chứng này chứng thực...').",
    ),
]

LOGIC_RULE_CODES = {code for code, _ in NARRATIVE_LOGIC_RULES}


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
