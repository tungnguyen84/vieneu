"""Regression tests for Script QC Hardening (Task B) and Audio Schema Normalization (Task A)."""
from __future__ import annotations

from pathlib import Path
import pytest

from apps.script_factory.auto_revision import AutoRevisionManager
from apps.script_factory.cost_control import CostController
from apps.script_factory.models import FullScript, LockedFact, QCReport, ScriptSegment, StoryBible
from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from apps.script_factory.script_qc import ScriptQCEngine, apply_targeted_repairs
from apps.script_factory.story_logic_v3 import ScriptProseQCV3Engine
from studio.backend.services.audio_service import (
    AudioService,
    normalize_script_segment,
    normalize_voice_id,
)


@pytest.fixture
def qc_env(tmp_path: Path):
    cost_ctrl = CostController(log_file=tmp_path / "usage.jsonl")
    provider = MockScriptAIProvider()
    qc_engine = ScriptQCEngine(provider=provider, cost_controller=cost_ctrl, episodes_root=tmp_path / "episodes")
    rev_mgr = AutoRevisionManager(provider=provider, cost_controller=cost_ctrl, qc_engine=qc_engine)
    return {"qc": qc_engine, "rev": rev_mgr, "provider": provider}


def _base_valid_segments() -> list[ScriptSegment]:
    return [
        ScriptSegment(id="001", speaker="MINH", text="Lá thư của Tuấn gửi về chương trình kể lại biến cố gia đình suốt 10 năm qua.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Mọi chuyện xoay quanh khoản tiền 100.000.000 VND trong chiếc hộp cũ.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Quý vị sẽ làm gì nếu phát hiện bí mật của người thân?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="004", speaker="MINH", text="Quý vị có chọn cách hỏi thẳng hay lặng lẽ tìm hiểu?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="005", speaker="MINH", text="Chúng ta hãy cùng lắng nghe tiếp câu chuyện của hai chị em.", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="006", speaker="MINH", text="Sự thật được xác thực: Bản di chúc hoàn toàn hợp pháp để bảo vệ gia đình.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="007", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe câu chuyện tối nay.", delivery_profile="ENDING"),
    ]


def test_qc_rejects_mid_script_signoff_and_continued_story(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_DOUBLE_ENDING",
        title="Dấu vết kỹ thuật số",
        protagonist={"name": "Nam", "char_id": "NAM"},
    )
    segments = _base_valid_segments()
    segments[4] = ScriptSegment(
        id="005",
        speaker="MINH",
        text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
        delivery_profile="ENDING",
    )
    segments.insert(5, ScriptSegment(
        id="006",
        speaker="MINH",
        text="Sáng hôm sau, Nam tiếp tục kiểm tra hồ sơ và tìm thấy một chứng cứ mới.",
        delivery_profile="MYSTERY",
    ))
    for idx, segment in enumerate(segments, start=1):
        segment.id = f"{idx:03d}"
    script = FullScript(
        episode_id=bible.episode_id,
        title=bible.title,
        host={"id": "MINH", "voice": "Binh"},
        segments=segments,
    )

    report = qc.run_qc(script, bible)
    rules = {issue.get("rule") for issue in report.evidence_issues}

    assert report.status == "FAIL"
    assert {"PREMATURE_SIGNOFF", "DUPLICATE_SIGNOFF", "CONTENT_AFTER_SIGNOFF"} <= rules


def test_qc_accepts_single_signoff_only_at_final_segment():
    bible = StoryBible(
        episode_id="EP_QC_ONE_ENDING",
        title="Một câu chuyện liền mạch",
        protagonist={"name": "Nam", "char_id": "NAM"},
    )

    issues = ScriptProseQCV3Engine().audit_script_prose(
        FullScript(
            episode_id=bible.episode_id,
            title=bible.title,
            host={"id": "MINH", "voice": "Binh"},
            segments=_base_valid_segments(),
        ),
        bible,
    )

    ending_rules = {
        "PREMATURE_SIGNOFF",
        "DUPLICATE_SIGNOFF",
        "CONTENT_AFTER_SIGNOFF",
        "MISSING_FINAL_SIGNOFF",
        "ENDING_PROFILE_PLACEMENT",
    }
    assert not any(issue.get("rule") in ending_rules for issue in issues)


def test_targeted_repair_fixes_slow_hook_and_duplicate_ending_without_new_story_facts():
    bible = StoryBible(
        episode_id="EP_QC_REPAIR_STRUCTURE",
        title="Những ca tăng không có trong lịch",
        protagonist={"name": "Hoàng", "char_id": "HOANG"},
        secret="Linh che giấu một mối quan hệ tình cảm bí mật.",
        mystery_question="Những ca tăng của Linh đang che giấu điều gì?",
        clues=["Một tin nhắn thân mật xuất hiện trên máy tính làm việc của Linh."],
    )
    script = FullScript(
        episode_id=bible.episode_id,
        title=bible.title,
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", speaker="MINH", text="Hoàng bắt đầu nhìn lại mọi chuyện.", delivery_profile="HOOK"),
            ScriptSegment(id="002", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
            ScriptSegment(id="003", speaker="MINH", text="Câu chuyện của Hoàng khép lại trong một khoảng lặng.", delivery_profile="ENDING"),
        ],
    )
    report = QCReport(
        episode_id=bible.episode_id,
        status="FAIL",
        evidence_issues=[
            {"rule": "HOOK_TOO_SLOW", "severity": "HIGH"},
            {"rule": "PREMATURE_SIGNOFF", "severity": "CRITICAL"},
            {"rule": "ENDING_PROFILE_PLACEMENT", "severity": "HIGH"},
        ],
    )

    repaired = apply_targeted_repairs(script, bible, report)

    assert "dấu hiệu bất thường" in repaired.segments[0].text
    assert "tin nhắn thân mật" in repaired.segments[0].text
    assert sum("xin chào và hẹn gặp lại" in s.text.lower() for s in repaired.segments) == 1
    assert [s.delivery_profile for s in repaired.segments].count("ENDING") == 1
    assert repaired.segments[-1].delivery_profile == "ENDING"


def test_qc_matches_locked_numbers_written_naturally_in_vietnamese(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_VI_NUMBERS",
        title="Đối chiếu con số tự nhiên",
        protagonist={"name": "Phương", "char_id": "PHUONG"},
        critical_facts=[
            LockedFact(fact_id="F1", field="timeline_months", value="18 tháng", status="LOCKED"),
            LockedFact(fact_id="F2", field="fraud_amount", value="2.2 tỷ VNĐ", status="LOCKED"),
            LockedFact(fact_id="F3", field="decoy_payment", value="10 triệu VNĐ/tháng", status="LOCKED"),
        ],
    )
    segments = _base_valid_segments()
    segments[1].text = (
        "Sự việc kéo dài mười tám tháng; hồ sơ ghi khoản 2,2 tỷ đồng và "
        "một khoản mười triệu đồng được chuyển đều mỗi tháng."
    )
    script = FullScript(
        episode_id=bible.episode_id,
        title=bible.title,
        host={"id": "MINH", "voice": "Binh"},
        segments=segments,
    )

    report = qc.run_qc(script, bible)

    assert not any(conflict.get("fact_id") in {"F1", "F2", "F3"} for conflict in report.fact_conflicts)


def test_qc_detects_hook_vs_reveal_contradiction(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_HOOK",
        title="Di chúc của cha",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        reveal_1="Bản di chúc hoàn toàn hợp pháp và có hiệu lực.",
    )
    segs = _base_valid_segments()
    segs[0] = ScriptSegment(
        id="001",
        speaker="MINH",
        text="Ngay bên quan tài của cha, bản di chúc giả mạo và vô hiệu đã bị phơi bày trước mặt Tuấn.",
        delivery_profile="HOOK",
    )
    script = FullScript(episode_id="EP_QC_HOOK", title="Di chúc của cha", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c.get("type") == "HOOK_FACT_CONTRADICTION" for c in report.fact_conflicts)
    assert any(iss.get("rule") == "HOOK_FACT_CONTRADICTION" for iss in report.evidence_issues)


def test_qc_detects_character_fact_violation(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_CHAR",
        title="Hai chị em",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        supporting_characters=[{"name": "Lan", "role": "Chị gái"}],
        relationships=[{"char_a": "TUAN", "char_b": "LAN", "relationship": "Một trai một gái, hai chị em ruột"}],
    )
    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Trong gia đình ấy, hai người con trai luôn xảy ra bất đồng về mảnh đất tổ tiên.",
        delivery_profile="NORMAL",
    )
    script = FullScript(episode_id="EP_QC_CHAR", title="Hai chị em", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c.get("type") == "CHARACTER_FACT_VIOLATION" for c in report.fact_conflicts)
    assert any(iss.get("rule") == "CHARACTER_FACT_VIOLATION" for iss in report.evidence_issues)


def test_qc_detects_ungrounded_character_hallucination(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_HALLUC",
        title="Người giấu mặt",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        supporting_characters=[{"name": "Lan", "role": "Chị gái"}],
    )
    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Tuấn bất ngờ nhận được cuộc gọi từ anh Khánh và chị Hương ở tận bên kia thành phố.",
        delivery_profile="NORMAL",
    )
    script = FullScript(episode_id="EP_QC_HALLUC", title="Người giấu mặt", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(c.get("type") == "UNGROUNDED_CHARACTER_HALLUCINATION" for c in report.fact_conflicts)
    assert any(iss.get("rule") == "UNGROUNDED_CHARACTER_HALLUCINATION" for iss in report.evidence_issues)


def test_qc_detects_melodramatic_cliche_density_and_unsafe_legal_claim(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_PROSE",
        title="Sự thật",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
    )
    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Một cuộc chiến ngầm khốc liệt không tiếng súng đã làm chấn động toàn bộ gia tộc nhằm đập tan mọi nghi kỵ.",
        delivery_profile="NORMAL",
    )
    segs[5] = ScriptSegment(
        id="006",
        speaker="MINH",
        text="Tòa án tuyên bố vô hiệu ngay lập tức bản di chúc ngay tại phòng khách gia đình.",
        delivery_profile="REVEAL",
        importance="critical",
    )
    script = FullScript(episode_id="EP_QC_PROSE", title="Sự thật", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "FAIL"  # unsafe legal claims are a hard fail
    rules = {iss.get("rule") for iss in report.evidence_issues}
    assert "MELODRAMATIC_CLICHE_DENSITY" in rules
    assert "LEGAL_CLAIM_SAFETY" in rules


def test_qc_detects_overlong_ending_proportion(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_QC_END",
        title="Tỷ lệ kết",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
    )
    segs = [
        ScriptSegment(id="001", speaker="MINH", text="Lá thư của Tuấn mở ra câu chuyện gia đình.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Quý vị nghĩ sao?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="003", speaker="MINH", text="Quý vị sẽ làm gì?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="004", speaker="MINH", text="Hãy cùng lắng nghe.", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="005", speaker="MINH", text="Sự thật được mở ra.", delivery_profile="REVEAL", importance="critical"),
    ]
    for i in range(6, 17):
        segs.append(ScriptSegment(id=f"{i:03d}", speaker="MINH", text=f"Diễn biến câu chuyện của Tuấn tiếp tục ở đoạn {i}.", delivery_profile="NORMAL"))
    # 5 ending segments out of 21 (~23.8% > 12%)
    for i in range(17, 22):
        segs.append(ScriptSegment(id=f"{i:03d}", speaker="MINH", text=f"Lời kết chiêm nghiệm kéo dài thứ {i}.", delivery_profile="ENDING"))

    script = FullScript(episode_id="EP_QC_END", title="Tỷ lệ kết", host={"id": "MINH", "voice": "Binh"}, segments=segs)
    report = qc.run_qc(script, bible)
    assert report.status == "FAIL"
    assert any(iss.get("rule") == "PREMATURE_SIGNOFF" for iss in report.evidence_issues)
    assert any(iss.get("rule") == "ENDING_PROPORTION_VIOLATION" for iss in report.evidence_issues)


def test_auto_repair_resolves_hardened_qc_violations(qc_env):
    qc: ScriptQCEngine = qc_env["qc"]
    rev: AutoRevisionManager = qc_env["rev"]
    bible = StoryBible(
        episode_id="EP_QC_REPAIR",
        title="Hàn gắn",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        supporting_characters=[{"name": "Lan", "role": "Chị gái"}],
        relationships=[{"char_a": "TUAN", "char_b": "LAN", "relationship": "Một trai một gái"}],
        reveal_1="Bản di chúc hoàn toàn hợp pháp và xác thực.",
    )
    segs = _base_valid_segments()
    segs[0].text = "Bản di chúc giả mạo và vô hiệu bị phát hiện."
    segs[1].text = "Hai người con trai cùng anh Khánh bước vào cuộc chiến ngầm khốc liệt không tiếng súng làm chấn động toàn bộ khu phố."
    segs[5].text = "Tòa án tuyên bố vô hiệu ngay lập tức mọi giấy tờ nhưng sau đó xác nhận bản di chúc hoàn toàn hợp pháp."
    script = FullScript(episode_id="EP_QC_REPAIR", title="Hàn gắn", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    initial_report = qc.run_qc(script, bible)
    assert initial_report.status == "FAIL"  # unsafe legal claim is a hard fail, still repairable

    revised_script, final_report = rev.auto_revise_and_recheck(script, bible, initial_report)
    assert final_report.status == "PASS"
    assert revised_script.revision_round == 1


def test_audio_schema_normalization_and_voice_alias_mapping():
    assert normalize_voice_id("Binh") == "020"
    assert normalize_voice_id("MINH") == "020"
    assert normalize_voice_id("MC Minh") == "020"
    assert normalize_voice_id("Thanh Bình") == "020"
    assert normalize_voice_id("020") == "020"
    assert normalize_voice_id("") == "020"

    legacy_seg = {
        "segment_id": "SEG_007",
        "speaker": "NARRATOR",
        "delivery_profile": "reveal",
        "text": "  Sự thật cuối cùng đã sáng tỏ. ",
    }
    norm = normalize_script_segment(legacy_seg, index=6, voice_id="Binh", contextual_speed=True)
    assert norm["id"] == "007"
    assert norm["segment_id"] == "007"
    assert norm["speaker"] == "MINH"
    assert norm["voice"] == "020"
    assert norm["delivery_profile"] == "REVEAL"
    assert norm["speed"] == 0.92
    assert norm["text"] == "Sự thật cuối cùng đã sáng tỏ."

    srv = AudioService()
    voices_info = srv.list_voices()
    assert voices_info["voices"][0]["voice_id"] == "020"
    assert "MC Minh" in voices_info["voices"][0]["label"]


def test_causal_gap_detection(qc_env):
    """Tests that StoryQCEngine and ScriptQCEngine detect CAUSAL_GAP when a minor request jumps to an extreme lifelong action without causal necessity."""
    from apps.script_factory.story_qc import StoryQCEngine

    story_qc = StoryQCEngine()
    qc: ScriptQCEngine = qc_env["qc"]

    bible = StoryBible(
        episode_id="EP_CAUSAL",
        title="Chiếc thẻ bài cũ",
        protagonist={"name": "Nam", "char_id": "NAM"},
        clues=["Tấm thẻ bài kim loại trong hộp gỗ.", "Bức thư gửi về quê.", "Sổ hộ khẩu cũ."],
        timeline=["52 năm trước: Biến cố xảy ra.", "Hiện tại: Phát hiện hộp gỗ."],
        reveal_1="Người đồng đội đã hy sinh.",
        reveal_2="Trước khi mất, người bạn nhờ mang hộ thẻ bài về quê và chăm sóc mẹ già, nên nhân vật đổi luôn danh tính và sống 52 năm dưới danh tính người đã khuất.",
    )

    bible_report = story_qc.audit_story_bible(bible)
    assert bible_report.status == "FAIL"
    assert "CAUSAL_GAP" in bible_report.rule_codes

    segs = _base_valid_segments()
    segs[5] = ScriptSegment(
        id="006",
        speaker="MINH",
        text="Người bạn chỉ nhờ mang hộ thẻ bài và chăm sóc mẹ già, thế nên ông quyết định đổi luôn danh tính và sống suốt 52 năm dưới danh tính người đã khuất.",
        delivery_profile="REVEAL",
        importance="critical",
    )
    script = FullScript(episode_id="EP_CAUSAL", title="Chiếc thẻ bài cũ", host={"id": "MINH", "voice": "Binh"}, segments=segs)
    script_report = qc.run_qc(script, bible)
    assert script_report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "CAUSAL_GAP" for iss in script_report.evidence_issues)


def test_character_secret_knowledge_consistency(qc_env):
    """Tests that CHARACTER_KNOWLEDGE_CONTRADICTION is caught when a character knows the secret in StoryBible/segment while another segment claims nobody knew / could not tell spouse."""
    from apps.script_factory.story_qc import StoryQCEngine

    story_qc = StoryQCEngine()
    qc: ScriptQCEngine = qc_env["qc"]

    bible = StoryBible(
        episode_id="EP_KNOWLEDGE",
        title="Sự im lặng",
        protagonist={"name": "Nam", "char_id": "NAM"},
        supporting_characters=[
            {
                "name": "Bà Mai",
                "char_id": "MAI",
                "role": "Người vợ",
                "description": "Biết toàn bộ câu chuyện ngay từ đầu nhưng chọn cách câm lặng.",
            }
        ],
        clues=["Manh mối 1", "Manh mối 2"],
        timeline=["Mốc 1", "Mốc 2"],
        secret="Một bí mật cô độc không thể sẻ chia cùng ai kể cả với người vợ gối chăn.",
        reveal_1="Sự thật 1.",
        reveal_2="Sự thật 2.",
    )

    bible_report = story_qc.audit_story_bible(bible)
    assert bible_report.status == "FAIL"
    assert "CHARACTER_KNOWLEDGE_CONTRADICTION" in bible_report.rule_codes

    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Suốt nửa thế kỷ, ông mang theo một bí mật cô độc không thể sẻ chia cùng ai kể cả với người vợ gối chăn.",
        delivery_profile="NORMAL",
    )
    script = FullScript(episode_id="EP_KNOWLEDGE", title="Sự im lặng", host={"id": "MINH", "voice": "Binh"}, segments=segs)
    script_report = qc.run_qc(script, bible)
    assert script_report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "CHARACTER_KNOWLEDGE_CONTRADICTION" for iss in script_report.evidence_issues)


def test_evidence_does_not_prove_claim(qc_env):
    """Tests that EVIDENCE_DOES_NOT_PROVE_CLAIM catches jumping from a single initial clue directly to a final extreme claim without intermediate evidence."""
    from apps.script_factory.story_qc import StoryQCEngine

    story_qc = StoryQCEngine()
    qc: ScriptQCEngine = qc_env["qc"]

    bible = StoryBible(
        episode_id="EP_EVIDENCE",
        title="Bằng chứng",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        clues=["Tấm thẻ bài kim loại."],
        timeline=["10 năm trước"],
        structured_clues=[
            {
                "clue": "Tấm thẻ bài kim loại khắc tên người khác trong hộp gỗ.",
                "what_it_proves": "Chứng minh ông đã đánh tráo danh tính và chính là kẻ giả mạo suốt 50 năm.",
                "what_it_does_NOT_prove": "Chưa chứng minh được ông không phải là ông nội thật.",
                "next_question": "Chiếc thẻ bài này của ai?",
            }
        ],
    )

    bible_report = story_qc.audit_story_bible(bible)
    assert bible_report.status == "FAIL"
    assert "EVIDENCE_DOES_NOT_PROVE_CLAIM" in bible_report.rule_codes

    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Ngay khi nhìn thấy tấm thẻ bài kim loại, vật chứng này đã chứng minh hoàn toàn rằng ông chính là kẻ giả mạo đã đánh tráo danh tính.",
        delivery_profile="MYSTERY",
    )
    script = FullScript(episode_id="EP_EVIDENCE", title="Bằng chứng", host={"id": "MINH", "voice": "Binh"}, segments=segs)
    script_report = qc.run_qc(script, bible)
    assert script_report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "EVIDENCE_DOES_NOT_PROVE_CLAIM" for iss in script_report.evidence_issues)


def test_unsupported_reveal_blocked(tmp_path: Path):
    """Tests that Reveal Justification Gate fails with UNSUPPORTED_REVEAL and blocks ScriptWriter until repaired."""
    from apps.script_factory.script_writer import ScriptWriter
    from apps.script_factory.story_qc import StoryQCEngine

    cost_ctrl = CostController(log_file=tmp_path / "usage.jsonl")
    provider = MockScriptAIProvider()
    writer = ScriptWriter(provider=provider, cost_controller=cost_ctrl, episodes_root=tmp_path / "episodes")
    story_qc = StoryQCEngine()

    unsupported_bible = StoryBible(
        episode_id="EP_UNSUPPORTED",
        title="Bước ngoặt thiếu căn cứ",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        clues=[],
        timeline=[],
        reveal_1="Người hàng xóm thực ra là tỷ phú ẩn danh.",
        reveal_2="Toàn bộ ngôi làng là một phim trường.",
        reveal_justifications={
            "reveal_1": {
                "evidence_support": "",
                "motivation_support": "unsupported",
                "timeline_support": "",
            },
            "reveal_2": {
                "evidence_support": "",
                "motivation_support": "",
                "character_knowledge_support": "none",
            },
        },
    )

    qc_res = story_qc.audit_story_bible(unsupported_bible)
    assert qc_res.status == "FAIL"
    assert "UNSUPPORTED_REVEAL" in qc_res.rule_codes

    with pytest.raises(ValueError, match="UNSUPPORTED_REVEAL"):
        writer.generate_script_from_bible(unsupported_bible)

    # After repair, ScriptWriter succeeds
    repaired_bible = story_qc.repair_story_bible(unsupported_bible, qc_res)
    recheck = story_qc.audit_story_bible(repaired_bible)
    assert recheck.status == "PASS"
    script = writer.generate_script_from_bible(repaired_bible)
    assert len(script.segments) > 0


def test_internal_episode_id_not_spoken(qc_env):
    """Tests that INTERNAL_EPISODE_ID_SPOKEN catches EP1005, EP_TEST_005, 'tập 1005', and 'tập một nghìn không trăm linh năm'."""
    qc: ScriptQCEngine = qc_env["qc"]
    rev: AutoRevisionManager = qc_env["rev"]
    bible = StoryBible(
        episode_id="EP1005",
        title="Sau Vỏ Bọc",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        public_episode_number=None,
    )

    for bad_greeting in [
        "Chào mừng quý vị và các bạn đến với tập một nghìn không trăm linh năm của series Sau Cánh Cửa.",
        "Chào mừng quý vị đến với tập 1005 mang mã số EP1005 của chương trình.",
        "Câu chuyện thuộc dự án EP_TEST_005 xin được bắt đầu.",
    ]:
        segs = _base_valid_segments()
        segs[1] = ScriptSegment(id="002", speaker="MINH", text=bad_greeting, delivery_profile="NORMAL")
        script = FullScript(episode_id="EP1005", title="Sau Vỏ Bọc", host={"id": "MINH", "voice": "Binh"}, segments=segs)

        report = qc.run_qc(script, bible)
        assert report.status == "NEEDS_REVISION"
        assert any(iss.get("rule") == "INTERNAL_EPISODE_ID_SPOKEN" for iss in report.evidence_issues)

        revised, final_rep = rev.auto_revise_and_recheck(script, bible, report)
        assert final_rep.status == "PASS"
        assert "một nghìn không trăm linh năm" not in revised.segments[1].text.lower()
        assert "1005" not in revised.segments[1].text.lower()
        assert "ep_test_005" not in revised.segments[1].text.lower()


def test_fake_serial_break_detection(qc_env):
    """Tests that FAKE_SERIAL_BREAK detects 'phần tiếp theo', 'ở phần sau', 'hãy đón xem', 'chúng ta sẽ quay lại sau', and mid-script 'tập tiếp theo'."""
    qc: ScriptQCEngine = qc_env["qc"]
    rev: AutoRevisionManager = qc_env["rev"]
    bible = StoryBible(
        episode_id="EP_SERIAL",
        title="Mạch truyện liền mạch",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
    )
    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Chuyện gì sẽ xảy ra khi chiếc hộp mở ra, hãy đón xem ở phần tiếp theo sau ít phút nữa.",
        delivery_profile="NORMAL",
    )
    script = FullScript(episode_id="EP_SERIAL", title="Mạch truyện liền mạch", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "FAKE_SERIAL_BREAK" for iss in report.evidence_issues)

    revised, final_rep = rev.auto_revise_and_recheck(script, bible, report)
    assert final_rep.status == "PASS"
    assert "phần tiếp theo" not in revised.segments[1].text.lower()
    assert "hãy đón xem" not in revised.segments[1].text.lower()


def test_melodrama_density_v2(qc_env):
    """Tests that MELODRAMA_DENSITY_V2 catches AI-labeled melodramatic prose ('bí mật động trời', 'đòn chí mạng', 'cuộc gặp gỡ định mệnh', etc.) and repairs it."""
    qc: ScriptQCEngine = qc_env["qc"]
    rev: AutoRevisionManager = qc_env["rev"]
    bible = StoryBible(
        episode_id="EP_MELO_V2",
        title="Tiết chế cảm xúc",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
    )
    segs = _base_valid_segments()
    segs[1] = ScriptSegment(
        id="002",
        speaker="MINH",
        text="Cuộc gặp gỡ định mệnh ấy đã hé lộ một bí mật động trời giáng xuống như một đòn chí mạng khiến anh đau đớn đến tận cùng.",
        delivery_profile="NORMAL",
    )
    script = FullScript(episode_id="EP_MELO_V2", title="Tiết chế cảm xúc", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "MELODRAMA_DENSITY_V2" for iss in report.evidence_issues)
    assert report.scores.get("melodrama_density_v2", 100.0) < 70.0

    revised, final_rep = rev.auto_revise_and_recheck(script, bible, report)
    assert final_rep.status == "PASS"
    assert "bí mật động trời" not in revised.segments[1].text.lower()
    assert "đòn chí mạng" not in revised.segments[1].text.lower()


def test_ending_semantic_repetition(qc_env):
    """Tests that ENDING_SEMANTIC_REPETITION catches consecutive closing segments repeating the same moral lesson in different words and compresses them."""
    qc: ScriptQCEngine = qc_env["qc"]
    rev: AutoRevisionManager = qc_env["rev"]
    bible = StoryBible(
        episode_id="EP_END_REP",
        title="Kết thúc gọn gàng",
        protagonist={"name": "Tuấn", "char_id": "TUAN"},
        reflection_theme="Đằng sau cánh cửa gia đình, sự thấu hiểu bắt đầu từ lòng bao dung.",
    )
    segs = [
        ScriptSegment(id="001", speaker="MINH", text="Lá thư của Tuấn kể về biến cố gia đình suốt 10 năm qua.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Quý vị sẽ làm gì khi đối diện với bí mật?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="003", speaker="MINH", text="Quý vị có chọn cách lắng nghe người thân?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="004", speaker="MINH", text="Hãy cùng theo dõi hành trình của Tuấn.", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="005", speaker="MINH", text="Sự thật được mở ra từ tập hồ sơ lưu trữ.", delivery_profile="REVEAL", importance="critical"),
        # 5 repetitive moralizing segments in the closing window
        ScriptSegment(id="006", speaker="MINH", text="Đằng sau cánh cửa gia đình, sự tha thứ và lòng bao dung sẽ chữa lành mọi vết thương và tháo bỏ chiếc mặt nạ.", delivery_profile="NORMAL"),
        ScriptSegment(id="007", speaker="MINH", text="Bài học lớn nhất đằng sau cánh cửa là tình yêu thương, sự tha thứ và lòng bao dung giúp chữa lành vết thương.", delivery_profile="NORMAL"),
        ScriptSegment(id="008", speaker="MINH", text="Khi chiếc mặt nạ rơi xuống đằng sau cánh cửa, chỉ có sự tha thứ và lòng bao dung mới chữa lành mái ấm.", delivery_profile="COMMENT"),
        ScriptSegment(id="009", speaker="MINH", text="Nhận ra rằng đằng sau cánh cửa ấy, sự tha thứ và bao dung chính là chìa khóa hóa giải và chữa lành.", delivery_profile="COMMENT"),
        ScriptSegment(id="010", speaker="MINH", text="Tôi là Minh. Cảm ơn quý vị đã lắng nghe. Hẹn gặp lại quý vị trong tập tiếp theo.", delivery_profile="ENDING"),
    ]
    script = FullScript(episode_id="EP_END_REP", title="Kết thúc gọn gàng", host={"id": "MINH", "voice": "Binh"}, segments=segs)

    report = qc.run_qc(script, bible)
    assert report.status == "NEEDS_REVISION"
    assert any(iss.get("rule") == "ENDING_SEMANTIC_REPETITION" for iss in report.evidence_issues)

    revised, final_rep = rev.auto_revise_and_recheck(script, bible, report)
    assert final_rep.status == "PASS"

