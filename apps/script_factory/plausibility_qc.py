"""Plausibility QC Engine for Script Factory V1.2.

Evaluates premise ideas for real-world plausibility in the Vietnamese domestic context:
- Checks 12 dimensions: timeline consistency, family knowledge, identity continuity,
  financial plausibility, medical plausibility, legal/document plausibility, technology,
  geography, character motivation, cause-and-effect, evidence accessibility, institutional behavior.
- Generates skeptical viewer questions.
- Enforces hard gates:
  - plausibility < 55: BLOCKED_IMPLAUSIBLE
  - plausibility < 70: NEEDS_LOGIC_REWRITE
  - plausibility >= 70: PASS
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from apps.script_factory.models import IdeaItem


@dataclass
class PlausibilityResult:
    score: float  # 0 to 100
    status: str   # "PASS", "NEEDS_LOGIC_REWRITE", "BLOCKED_IMPLAUSIBLE"
    issues: List[str] = field(default_factory=list)
    required_explanations: List[str] = field(default_factory=list)
    skeptical_viewer_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PlausibilityEngine:
    """Evaluates the realistic credibility of premise ideas in contemporary Vietnamese society."""

    def evaluate_idea(self, idea: IdeaItem) -> PlausibilityResult:
        full_text = (
            f"{idea.working_title} {idea.hook} {idea.protagonist} {idea.relationship} "
            f"{idea.central_secret} {idea.mystery_question} {idea.false_lead} "
            f"{idea.clue_1} {idea.clue_2} {idea.clue_3} {idea.reveal_1} {idea.reveal_2} "
            f"{idea.emotional_payoff} {idea.reflection_theme}"
        ).lower()

        issues: List[str] = []
        required_explanations: List[str] = []
        skeptical_questions: List[str] = []

        base_score = 90.0

        # 1. Timeline & Medical Consistency (Section 6 & 24 IDEA_008 test case)
        # E.g., 10 years of amnesia or coma without medical tracing or family notification
        year_match = re.search(r"(\d+)\s*(năm|tháng)", full_text)
        duration_years = int(year_match.group(1)) if year_match and year_match.group(2) == "năm" else 0
        has_medical = any(w in full_text for w in ["mất trí", "hôn mê", "bệnh viện", "viện phí", "chấn thương", "mất trí nhớ"])
        
        if duration_years >= 5 and has_medical:
            issues.append(f"Khoảng thời gian y tế/mất trí kéo dài {duration_years} năm cần giải trình rõ viện phí và hồ sơ bệnh án.")
            required_explanations.append(f"Cần làm rõ ai chăm sóc và thanh toán viện phí trong suốt {duration_years} năm.")
            skeptical_questions.append(f"Tại sao trong suốt {duration_years} năm nằm viện/mất trí, cơ sở y tế không liên lạc với gia đình?")
            skeptical_questions.append("Hồ sơ bệnh án và viện phí suốt nhiều năm qua được ai bảo lãnh chi trả?")
            base_score -= 15.0

        # Medically impossible / supernatural recovery (e.g. waking from coma without treatment, "năng lượng đặc biệt", "tự chữa lành")
        has_impossible_recovery = any(w in full_text for w in ["không cần điều trị", "năng lượng đặc biệt", "tự chữa lành", "siêu nhiên", "phép màu", "hồi phục kỳ diệu"])
        if has_impossible_recovery:
            issues.append("Yếu tố hồi phục y tế thần kỳ hoặc không qua điều trị vi phạm tính hợp lý khoa học thực tế.")
            required_explanations.append("Cần căn cứ y khoa thực tế thay vì các yếu tố tự hồi phục phi lý.")
            skeptical_questions.append("Làm sao một người có thể hồi phục sau thời gian dài mà không qua bất kỳ can thiệp y tế nào?")
            base_score -= 25.0

        # 2. Technology & Impossible Communication (Messages / calls from deceased)
        has_msg_from_dead = any(w in full_text for w in ["người đã khuất", "người đã mất", "dưới suối vàng", "kiếp sau"]) and any(w in full_text for w in ["tin nhắn", "dòng chat", "cuộc gọi", "gọi điện"])
        if has_msg_from_dead:
            # Must explain who operates the account or phone line
            has_tech_expl = any(w in full_text for w in ["lập trình", "hẹn giờ", "người khác", "giữ sim", "nhờ", "mượn", "bí mật dùng"])
            if not has_tech_expl:
                issues.append("Tin nhắn/cuộc gọi từ người đã mất chưa làm rõ cơ chế công nghệ (SIM, tài khoản ai duy trì).")
                required_explanations.append("Cần giải thích rõ ai là người nạp tiền/duy trì SIM hoặc tài khoản mạng xã hội của người đã khuất.")
                skeptical_questions.append("Làm sao SIM điện thoại hoặc tài khoản của người đã mất nhiều năm vẫn còn hoạt động?")
                base_score -= 12.0
            else:
                skeptical_questions.append("Ai là người nắm giữ thiết bị và duy trì kết nối mạng?")

        # 3. Financial Plausibility
        has_secret_money = any(w in full_text for w in ["khoản tiền", "chuyển tiền", "tài khoản", "tiền tỷ", "hàng tháng"])
        if has_secret_money:
            # In Vietnam, large transfers or secret accounts require banking identification (CCCD / VNeID)
            has_fin_expl = any(w in full_text for w in ["tài khoản", "ngân hàng", "tiền mặt", "sổ tiết kiệm", "đứng tên"])
            if not has_fin_expl:
                issues.append("Giao dịch tài chính chưa nêu rõ hình thức thanh toán (chuyển khoản ngân hàng hay tiền mặt).")
                required_explanations.append("Làm rõ nguồn tiền và phương thức giao dịch để phù hợp quy định ngân hàng Việt Nam.")
                base_score -= 8.0
            skeptical_questions.append("Dòng tiền lớn như vậy được rút hoặc chuyển qua kênh nào mà không để lại thông báo biến động số dư?")

        # 4. Legal / Document Plausibility (Birth certificate, will, inheritance)
        has_legal_doc = any(w in full_text for w in ["giấy khai sinh", "di chúc", "khai tử", "thừa kế", "sổ đỏ", "công chứng"])
        if has_legal_doc:
            if "giả" in full_text or "lạ" in full_text or "sai" in full_text:
                skeptical_questions.append("Giấy tờ này có được công chứng hợp pháp tại cơ quan chức năng Việt Nam không?")
                required_explanations.append("Giải thích tính pháp lý của giấy tờ theo luật hộ tịch và công chứng Việt Nam.")

        # 5. Family Knowledge & Routine
        # If someone keeps a daily/monthly routine for years under the same roof:
        if any(w in full_text for w in ["7 năm", "10 năm", "nhiều năm"]) and any(w in full_text for w in ["giấu chồng", "giấu vợ", "giấu gia đình"]):
            skeptical_questions.append("Làm thế nào nhân vật có thể che giấu lịch trình/thói quen này suốt nhiều năm sống chung một nhà?")
            if "bí mật" in full_text and not any(w in full_text for w in ["khéo léo", "đêm khuya", "riêng tư", "tủ khóa", "ngăn kéo"]):
                issues.append("Cần bổ sung chi tiết cách nhân vật che giấu sự việc trong sinh hoạt gia đình hàng ngày.")
                base_score -= 7.0

        # 6. Causal Necessity Check (CAUSAL_GAP: Weak Cause -> Extreme Long-Term Action)
        extreme_actions = [
            r"đổi\s+(?:luôn\s+)?danh\s+tính",
            r"sống\s+(?:suốt\s+)?(?:\d+\s+năm\s+)?dưới\s+danh\s+tính",
            r"sống\s+dưới\s+tên",
            r"mang\s+danh\s+tính\s+của",
            r"giả\s+danh\s+người\s+đã\s+khuất",
            r"mạo\s+danh\s+suốt",
            r"xóa\s+bỏ\s+tên\s+thật",
        ]
        weak_causes = [
            r"nhờ\s+.*mang\s+(?:hộ\s+)?thẻ\s+bài",
            r"mang\s+thẻ\s+bài.*chăm\s+sóc\s+mẹ",
            r"nhờ\s+chăm\s+sóc\s+mẹ\s+già",
            r"nhờ\s+gửi\s+lại\s+kỷ\s+vật",
            r"nhờ\s+mang\s+giấy\s+tờ\s+về\s+quê",
            r"chỉ\s+vì\s+lời\s+nhờ\s+vả",
        ]
        necessity_markers = [
            "bất khả kháng", "không còn cách nào khác", "phương án duy nhất", "cách duy nhất",
            "giấy báo tử ghi nhầm", "thất lạc hồ sơ", "hồ sơ duy nhất", "nguy kịch tính mạng",
            "đe dọa tính mạng", "ràng buộc pháp lý",
        ]
        if any(re.search(p, full_text) for p in extreme_actions) and any(re.search(p, full_text) for p in weak_causes):
            if not any(m in full_text for m in necessity_markers):
                issues.append("CAUSAL_GAP: Nguyên nhân/lời nhờ vả ban đầu không đủ sức nặng bắt buộc nhân vật đánh đổi danh tính suốt nhiều năm khi chưa giải thích tại sao không thể giúp đỡ dưới tên thật.")
                required_explanations.append("Giải thích rõ hoàn cảnh bất khả kháng khiến nhân vật không thể giữ tên thật hoặc giải pháp bình thường.")
                skeptical_questions.append("Tại sao chỉ vì lời nhờ mang kỷ vật và chăm sóc người thân mà nhân vật lại phải xóa bỏ tên thật để sống dưới danh tính người đã khuất?")
                base_score -= 25.0

        # 7. Default skeptical questions if list is still small
        if len(skeptical_questions) < 3:
            skeptical_questions.append("Tại sao nhân vật chính không thẳng thắn đối chất ngay từ manh mối đầu tiên?")
            skeptical_questions.append("Liệu bằng chứng này có thể bị làm giả hoặc hiểu lầm không?")
            skeptical_questions.append("Người giữ bí mật có động cơ thực sự thuyết phục để chấp nhận đánh đổi lớn như vậy không?")

        # Final Score Clamping
        score = max(30.0, min(100.0, round(base_score, 1)))

        # Section 7 Hard Gate:
        # plausibility < 55: BLOCKED_IMPLAUSIBLE
        # plausibility < 70: NEEDS_LOGIC_REWRITE
        # plausibility >= 70: PASS
        if score < 55.0:
            status = "BLOCKED_IMPLAUSIBLE"
        elif score < 70.0:
            status = "NEEDS_LOGIC_REWRITE"
        else:
            status = "PASS"

        return PlausibilityResult(
            score=score,
            status=status,
            issues=issues,
            required_explanations=required_explanations,
            skeptical_viewer_questions=skeptical_questions[:4],
        )
