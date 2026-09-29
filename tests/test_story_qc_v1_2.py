"""Tests for Script Factory V1.2 Story Quality Hardening (Section 48)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.script_factory.models import ApprovalStatus, IdeaItem
from apps.script_factory.novelty_engine import (
    NoveltyEngine,
    compute_narrative_skeleton_similarity,
    extract_narrative_skeleton,
)
from apps.script_factory.plausibility_qc import PlausibilityEngine
from apps.script_factory.story_qc import StoryQCEngine
from apps.script_factory.idea_rewriter import IdeaRewriter


# 1. test_narrative_skeleton_detects_ep001_variant
def test_narrative_skeleton_detects_ep001_variant():
    ep1_variant = IdeaItem(
        idea_id="IDEA_VAR",
        working_title="5 năm gửi tiền bí mật cho người đàn bà lạ",
        hook="Chồng phát hiện vợ 5 năm nay tháng nào cũng gửi 8 triệu cho một người đàn bà lạ.",
        protagonist="Hoàng",
        relationship="Chồng và vợ",
        central_secret="Người vợ gửi tiền cho người mẹ đã mất 10 năm do người dì giả giọng qua điện thoại.",
        mystery_question="Ai là người ở đầu dây bên kia?",
        false_lead="Người vợ có con riêng hoặc người yêu cũ.",
        clue_1="Sao kê ngân hàng ghi nhận chuyển tiền đều đặn ngày mùng 1 hàng tháng.",
        clue_2="Trích lục khai tử xác nhận mẹ vợ đã qua đời từ 10 năm trước.",
        clue_3="Cuộc gọi thoại với giọng nói của người mẹ nhưng phát ra từ phòng của người dì.",
        reveal_1="Mẹ vợ đã mất 10 năm trước tại quê nhà.",
        reveal_2="Dì ruột đã giả giọng người mẹ đã mất suốt 5 năm để nhận 8 triệu mỗi tháng.",
        emotional_payoff="Hoàng ôm vợ trong nước mắt khi hiểu ra nỗi cô đơn tột cùng của cô.",
        reflection_theme="Sự trống trải khiến con người tự lừa dối chính mình.",
        hook_archetype="MONEY_ANOMALY",
        twist_archetype="DECEPTION",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(ep1_variant)
    assert report.narrative_skeleton_similarity >= 70.0
    assert report.status == ApprovalStatus.BLOCKED_NARRATIVE_DUPLICATE.value


# 2. test_name_changes_do_not_bypass_skeleton_duplicate
def test_name_changes_do_not_bypass_skeleton_duplicate():
    variant_entity_swap = IdeaItem(
        idea_id="IDEA_SWAP",
        working_title="Bí mật chuyển khoản hàng tháng",
        hook="Minh tình cờ phát hiện vợ chuyển tiền định kỳ cho một người họ hàng.",
        protagonist="Minh",
        relationship="Vợ chồng",
        central_secret="Vợ giấu chồng gửi tiền hàng tháng cho cha đã mất do chú ruột giả giọng.",
        mystery_question="Ai thực sự nhận khoản tiền này?",
        false_lead="Nghi ngờ có gia đình riêng bí mật.",
        clue_1="Lịch sử giao dịch biến động số dư tài khoản ngân hàng.",
        clue_2="Giấy báo tử lưu trữ xác nhận cha đã qua đời nhiều năm trước.",
        clue_3="Đoạn ghi âm cuộc gọi mạo danh giọng nói.",
        reveal_1="Người cha đã mất từ nhiều năm trước.",
        reveal_2="Chú ruột giả danh người cha để chiếm đoạt tiền hỗ trợ.",
        emotional_payoff="Tha thứ và thấu hiểu nỗi đau mất người thân.",
        reflection_theme="Tình thương bị lợi dụng bởi người thân thiết.",
        hook_archetype="MONEY_ANOMALY",
        twist_archetype="DECEPTION",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(variant_entity_swap)
    # Masking ensures father->mother, wife->husband, etc. does not lower similarity
    assert report.narrative_skeleton_similarity >= 70.0
    assert report.status == ApprovalStatus.BLOCKED_NARRATIVE_DUPLICATE.value


# 3. test_plausibility_gate
def test_plausibility_gate():
    implausible_idea = IdeaItem(
        idea_id="IDEA_ABS",
        working_title="Người đàn ông hôn mê 20 năm tự đi bộ về nhà",
        hook="Một người đàn ông tỉnh dậy sau 20 năm hôn mê sâu không cần điều trị và tự đi bộ về nhà.",
        protagonist="Tuấn",
        relationship="Cha và con",
        central_secret="Ông sống trong rừng 20 năm mà không ai biết.",
        mystery_question="Làm sao ông sống sót?",
        false_lead="Ông bị bắt cóc.",
        clue_1="Không có hồ sơ bệnh viện nào.",
        clue_2="Không có ai chăm sóc.",
        clue_3="Vô tình xuất hiện.",
        reveal_1="Ông tự chữa lành trong rừng sâu.",
        reveal_2="Ông có năng lượng đặc biệt.",
        emotional_payoff="Cả nhà mừng rỡ.",
        reflection_theme="Kỳ tích cuộc sống.",
        hook_archetype="MISSING_TIME",
        twist_archetype="MEMORY",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(implausible_idea)
    # Highly implausible medical/timeline claims trigger low plausibility or logic rewrite
    assert report.plausibility_score < 70.0
    assert report.status in [ApprovalStatus.NEEDS_LOGIC_REWRITE.value, ApprovalStatus.BLOCKED_IMPLAUSIBLE.value]


# 4. test_medical_timeline_requires_explanation
def test_medical_timeline_requires_explanation():
    medical_idea = IdeaItem(
        idea_id="IDEA_MED",
        working_title="10 Năm Mất Trí Nhớ Của Bố",
        hook="Người con phát hiện người bố được cho là mất trí nhớ 10 năm qua thực chất đã bình phục từ lâu.",
        protagonist="Hà",
        relationship="Bố và con gái",
        central_secret="Bố giả vờ mất trí nhớ suốt 10 năm nằm viện.",
        mystery_question="Ai đã chi trả viện phí suốt 10 năm?",
        false_lead="Bác sĩ chẩn đoán sai.",
        clue_1="Đơn thuốc bệnh viện cũ.",
        clue_2="Biên lai viện phí định kỳ.",
        clue_3="Gặp bố nói chuyện bình thường.",
        reveal_1="Bố không hề mất trí nhớ sau tai nạn.",
        reveal_2="Bố giả mất trí để gánh nợ thay cho con trai.",
        emotional_payoff="Hà bật khóc thương bố.",
        reflection_theme="Sự hy sinh thầm lặng của người cha.",
        hook_archetype="MISSING_TIME",
        twist_archetype="SACRIFICE",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(medical_idea)
    # 10 years medical amnesia requires explanation in skeptical questions
    assert any("viện phí" in q.lower() or "bệnh án" in q.lower() for q in report.skeptical_viewer_questions)


# 5. test_clue_supports_reveal
def test_clue_supports_reveal():
    clue_idea = IdeaItem(
        idea_id="IDEA_CLUES",
        working_title="Lá thư trong ngăn bàn",
        hook="Lan tìm thấy một lá thư cũ trong ngăn bàn khóa kín.",
        protagonist="Lan",
        relationship="Mẹ và con",
        central_secret="Người mẹ gửi gắm tiền cho con gái nuôi.",
        mystery_question="Ai là người nhận tiền?",
        false_lead="Lan nghi mẹ bị tống tiền.",
        clue_1="Bức ảnh chụp chung 20 năm trước tại bệnh viện phụ sản.",
        clue_2="Biên lai thanh toán tiền học phí đại học cho một nữ sinh lạ.",
        clue_3="Cuốn sổ tay ghi lời dặn dò của người mẹ.",
        reveal_1="Nữ sinh lạ chính là con ruột của người bạn đã mất.",
        reveal_2="Người mẹ nuôi dạy giúp bạn vì lời hứa năm xưa.",
        emotional_payoff="Lan xúc động ôm mẹ.",
        reflection_theme="Tình bạn thủy chung.",
        hook_archetype="DOCUMENT",
        twist_archetype="SACRIFICE",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(clue_idea)
    # Every clue must specify support and causal strength
    assert len(report.clues_causality) == 3
    for c in report.clues_causality:
        assert "supports" in c
        assert c["causal_strength"] in ["WEAK", "MEDIUM", "STRONG"]


# 6. test_reveal2_requires_seed
def test_reveal2_requires_seed():
    unseeded_idea = IdeaItem(
        idea_id="IDEA_UNSEEDED",
        working_title="Bức tranh phong cảnh",
        hook="Minh mua bức tranh cũ và phát hiện điều kỳ lạ.",
        protagonist="Minh",
        relationship="Hai vợ chồng",
        central_secret="Bức tranh có giấu kim cương.",
        mystery_question="Ai giấu kim cương?",
        false_lead="Kẻ trộm giấu.",
        clue_1="Vết rách trên góc khung tranh.",
        clue_2="Chữ ký họa sĩ ở góc dưới.",
        clue_3="Lớp sơn dầu bị bong tróc.",
        reveal_1="Bức tranh được vẽ bởi người ông quá cố.",
        reveal_2="Người vợ thực ra là đặc vụ ngầm đang truy lùng kho báu cổ.",
        emotional_payoff="Hai người nhìn nhau.",
        reflection_theme="Bí mật cuộc đời.",
        hook_archetype="OBJECT_DISCOVERY",
        twist_archetype="IDENTITY",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(unseeded_idea)
    # Unseeded out-of-nowhere secret agent twist triggers logic issue
    assert any("gieo mầm" in iss or "seeded" in iss.lower() for iss in report.logic_issues)


# 7. test_reveal2_adds_new_value
def test_reveal2_adds_new_value():
    repetition_idea = IdeaItem(
        idea_id="IDEA_REP",
        working_title="Chiếc nhẫn vàng",
        hook="Tuấn tìm thấy chiếc nhẫn vàng trong hộp gỗ.",
        protagonist="Tuấn",
        relationship="Cha và con",
        central_secret="Chiếc nhẫn là của người mẹ quá cố.",
        mystery_question="Ai là chủ nhân chiếc nhẫn?",
        false_lead="Người yêu cũ của bố.",
        clue_1="Hóa đơn tiệm vàng năm 1995.",
        clue_2="Ký tự khắc tên viết tắt trên thân nhẫn.",
        clue_3="Bức ảnh cưới của bố mẹ.",
        reveal_1="Chiếc nhẫn là kỷ vật của người mẹ đã mất từ năm 1995.",
        reveal_2="Chiếc nhẫn đúng là kỷ vật của người mẹ đã mất từ năm 1995 ở tiệm vàng đó.",
        emotional_payoff="Tuấn trân trọng giữ gìn.",
        reflection_theme="Kỷ vật gia đình.",
        hook_archetype="OBJECT_DISCOVERY",
        twist_archetype="DOCUMENT",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(repetition_idea)
    # Reveal 2 that merely restates Reveal 1 gets low reveal_2_value
    assert report.reveal_qc["reveal_2_value"] <= 6.0


# 8. test_coincidence_budget
def test_coincidence_budget():
    coincidence_heavy_idea = IdeaItem(
        idea_id="IDEA_COIN",
        working_title="Cuộc gặp định mệnh",
        hook="Nam đi dạo trên phố và bất ngờ gặp điều kỳ lạ.",
        protagonist="Nam",
        relationship="Hai anh em",
        central_secret="Người anh mất tích nhiều năm trước.",
        mystery_question="Người anh đang ở đâu?",
        false_lead="Người anh đã ra nước ngoài.",
        clue_1="Nam tình cờ nghe được cuộc trò chuyện của hai người lạ trong quán cà phê kể về anh mình.",
        clue_2="Sau đó một người lạ tự nhiên kể cho Nam địa chỉ nhà trọ.",
        clue_3="Đến nơi thì người chủ trọ đột nhiên thú nhận toàn bộ sự thật.",
        reveal_1="Người anh đang sống ẩn dật gần đó.",
        reveal_2="Người anh làm vậy để chữa bệnh cho em trai.",
        emotional_payoff="Hai anh em ôm nhau khóc.",
        reflection_theme="Tình anh em.",
        hook_archetype="STRANGER",
        twist_archetype="SACRIFICE",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(coincidence_heavy_idea)
    # 3 major coincidences exceed coincidence budget
    assert report.coincidence_count >= 3
    assert report.status == ApprovalStatus.NEEDS_LOGIC_REWRITE.value


# 9. test_genre_guard_horror_drift
def test_genre_guard_horror_drift():
    horror_drift_idea = IdeaItem(
        idea_id="IDEA_HORROR",
        working_title="Căn Nhà Không Cửa Sổ Và Tiếng Đàn Lúc Nửa Đêm",
        hook="Ngôi nhà bỏ hoang phát ra tiếng đàn lúc nửa đêm khiến hàng xóm khiếp sợ vì nghi có hồn ma.",
        protagonist="Phong",
        relationship="Hàng xóm",
        central_secret="Một người phụ nữ bị giam cầm trong căn nhà không cửa sổ.",
        mystery_question="Ai đang gảy đàn trong căn nhà ma?",
        false_lead="Nghi ngờ bóng ma của người đã khuất hiện về báo oán.",
        clue_1="Tiếng đàn dương cầm vang lên đúng 12 giờ đêm.",
        clue_2="Cánh cửa sắt luôn bị khóa xích từ bên ngoài.",
        clue_3="Bóng đen lướt qua cửa sổ tối tăm.",
        reveal_1="Không có ma quỷ nào trong căn nhà bỏ hoang.",
        reveal_2="Một bệnh nhân tâm thần bị giam lỏng bí mật.",
        emotional_payoff="Cứu giúp nạn nhân thoát khỏi cảnh đọa đày.",
        reflection_theme="Nỗi đau tinh thần bị lãng quên.",
        hook_archetype="IMPOSSIBLE_FACT",
        twist_archetype="TIMELINE",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(horror_drift_idea)
    # Genre guard flags horror/captivity drift
    assert report.genre_fit_score < 70.0
    assert report.status == ApprovalStatus.NEEDS_GENRE_REWRITE.value


# 10. test_vietnamese_social_fit
def test_vietnamese_social_fit():
    idea = IdeaItem(
        idea_id="IDEA_VN",
        working_title="Di chúc phân chia mảnh đất ở quê",
        hook="Hai người con tranh chấp mảnh đất hương hỏa ở quê sau khi bố mất.",
        protagonist="Dũng",
        relationship="Hai anh em ruột",
        central_secret="Người bố bí mật sang tên sổ đỏ cho người con út tàn tật.",
        mystery_question="Tại sao sổ đỏ lại mang tên người em?",
        false_lead="Người em đã gian dối làm giả chữ ký công chứng.",
        clue_1="Bản trích lục sổ đỏ lưu trữ tại văn phòng đăng ký đất đai.",
        clue_2="Biên bản họp gia đình tại ủy ban nhân dân xã.",
        clue_3="Bức tâm thư viết tay của người cha gửi gắm người anh trưởng.",
        reveal_1="Chữ ký trên di chúc hoàn toàn do người cha tự nguyện ký trước khi qua đời.",
        reveal_2="Người cha muốn người em tàn tật có nơi nương tựa cả đời.",
        emotional_payoff="Người anh nghẹn ngào từ bỏ tranh chấp, nhận chăm sóc em trai.",
        reflection_theme="Tình anh em ruột thịt và đạo hiếu của người Việt.",
        hook_archetype="DOCUMENT",
        twist_archetype="RELATIONSHIP",
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(idea)
    assert report.vietnamese_social_fit_score >= 85.0


# 11. test_tragedy_saturation
def test_tragedy_saturation():
    idea_death = IdeaItem(
        idea_id="IDEA_D1",
        working_title="T1", hook="H1", protagonist="P1", relationship="R1",
        central_secret="Người cha đã mất trong tai nạn",
        mystery_question="Q1", false_lead="FL1",
        clue_1="C1", clue_2="C2", clue_3="C3",
        reveal_1="Người cha đã mất nhiều năm", reveal_2="R2",
        emotional_payoff="EP", reflection_theme="RT",
        hook_archetype="DOCUMENT", twist_archetype="TIMELINE"
    )
    engine = StoryQCEngine()
    report = engine.audit_idea(idea_death)
    assert report.has_death_or_tragedy is True


# 12. test_no_magic_total_score
def test_no_magic_total_score():
    idea = IdeaItem(
        idea_id="IDEA_DIM",
        working_title="Kỷ vật thời gian",
        hook="H", protagonist="P", relationship="R", central_secret="S",
        mystery_question="Q", false_lead="FL",
        clue_1="C1", clue_2="C2", clue_3="C3",
        reveal_1="R1", reveal_2="R2", emotional_payoff="EP", reflection_theme="RT",
        hook_archetype="OBJECT_DISCOVERY", twist_archetype="SACRIFICE"
    )
    engine = StoryQCEngine()
    rep = engine.audit_idea(idea)
    d = rep.to_dict()
    # Invariant: No single collapsed magic total score like "TOTAL_SCORE = 87"
    assert "total_score" not in d
    assert "overall_magic_score" not in d
    # Exposes dimensions separately
    assert "novelty_score" in d
    assert "plausibility_score" in d
    assert "genre_fit_score" in d
    assert "vietnamese_social_fit_score" in d


# 13. test_ai_cannot_user_approve
def test_ai_cannot_user_approve():
    engine = StoryQCEngine()
    idea = IdeaItem(
        idea_id="IDEA_PERF",
        working_title="Bức ảnh trong chiếc điện thoại cũ",
        hook="Một bức ảnh chụp năm 2005 hé lộ bí mật gia đình.",
        protagonist="An", relationship="Mẹ và con",
        central_secret="Bức ảnh chụp người chị em sinh đôi thất lạc.",
        mystery_question="Người trong ảnh là ai?", false_lead="Người yêu cũ.",
        clue_1="Bức ảnh đen trắng được kẹp trong ví cũ.",
        clue_2="Giấy xác nhận nhận con nuôi tại trạm y tế xã.",
        clue_3="Cuộc gặp mặt trực tiếp với người hộ lý già.",
        reveal_1="Người trong ảnh là chị gái sinh đôi của mẹ.",
        reveal_2="Hai chị em phải xa cách do hoàn cảnh kinh tế năm xưa.",
        emotional_payoff="Gia đình đoàn tụ.", reflection_theme="Tình thân ruột thịt.",
        hook_archetype="FAMILY_PHOTO", twist_archetype="IDENTITY"
    )
    rep = engine.audit_idea(idea)
    # AI can NEVER assign USER_APPROVED
    assert rep.status != ApprovalStatus.USER_APPROVED.value
    assert rep.status == ApprovalStatus.AWAITING_USER_REVIEW.value


# 14. test_rewrite_preserves_locked_fields
def test_rewrite_preserves_locked_fields():
    idea = IdeaItem(
        idea_id="IDEA_LOCK",
        working_title="Tiêu đề gốc",
        hook="Hook gốc",
        protagonist="Thành",
        relationship="Hai cha con",
        central_secret="Bí mật gốc không được sửa",
        mystery_question="Q",
        false_lead="FL",
        clue_1="C1", clue_2="C2", clue_3="C3",
        reveal_1="R1 gốc",
        reveal_2="R2 gốc",
        emotional_payoff="EP gốc",
        reflection_theme="RT",
        hook_archetype="MONEY_ANOMALY",
        twist_archetype="DECEPTION",
    )
    rewriter = IdeaRewriter()
    locked = ["protagonist", "relationship", "central_secret", "reveal_1", "reveal_2"]
    rewritten = rewriter.rewrite_idea(idea, rewrite_goal="Fix Logic", locked_fields=locked)

    assert rewritten.protagonist == "Thành"
    assert rewritten.relationship == "Hai cha con"
    assert rewritten.central_secret == "Bí mật gốc không được sửa"
    assert rewritten.reveal_1 == "R1 gốc"
    assert rewritten.reveal_2 == "R2 gốc"


# 15. test_existing_pilot_not_regenerated
def test_existing_pilot_not_regenerated():
    orig_path = Path("reports/script_factory_pilot_01.json")
    qc_path = Path("reports/script_factory_pilot_01_v1_2_qc.json")
    assert orig_path.exists()
    assert qc_path.exists()

    with open(orig_path, "r", encoding="utf-8") as f:
        orig_data = json.load(f)
    with open(qc_path, "r", encoding="utf-8") as f:
        qc_data = json.load(f)

    # 20 original ideas must have their IDs and titles preserved
    assert len(orig_data["ideas"]) == 20
    assert len(qc_data["ideas"]) == 20
    for o_it, q_it in zip(orig_data["ideas"], qc_data["ideas"]):
        assert o_it["idea_id"] == q_it["idea_id"]
        assert o_it["working_title"] == q_it["working_title"]


# 16. test_pilot02_max_five
def test_pilot02_max_five():
    ideas = [
        IdeaItem(
            idea_id=f"IDEA_{i:03d}",
            working_title=f"Title {i}", hook="H", protagonist="P", relationship="R",
            central_secret="S", mystery_question="Q", false_lead="FL",
            clue_1="C1", clue_2="C2", clue_3="C3",
            reveal_1="R1", reveal_2="R2", emotional_payoff="EP", reflection_theme="RT",
            hook_archetype="DOCUMENT", twist_archetype="TIMELINE"
        )
        for i in range(2, 10)
    ]
    # Simulate user selection with hard cap of 5
    selected = []
    for it in ideas:
        if len(selected) < 5:
            it.selected_for_pilot = True
            selected.append(it.idea_id)
        else:
            it.selected_for_pilot = False

    assert len(selected) == 5
    assert sum(1 for it in ideas if it.selected_for_pilot) == 5
