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


@pytest.mark.parametrize('mode', ['FICTION_FROM_THEME','FACTUAL_RETELLING','IMPROVE_OWN_SCRIPT'])
@pytest.mark.parametrize('case', ['matching','wrong','missing','spoken_enum_only'])
def test_locked_source_mode_checks_metadata_without_requiring_internal_spoken_token(qc_env,mode,case):
    context={'brief':{'adaptation_mode':mode,'target_duration_sec':300},'brief_hash':'test','analysis':{},'units':[]}
    bible=StoryBible('EP_MODE','Tập',{'name':'Lan'},adaptation_context=context,
        critical_facts=[LockedFact('MODE','adaptation_mode',mode,'Chế độ nguồn đã chọn.')])
    script_context=context if case=='matching' else (None if case in ('missing','spoken_enum_only') else
        {**context,'brief':{**context['brief'],'adaptation_mode':'FACTUAL_RETELLING' if mode!='FACTUAL_RETELLING' else 'FICTION_FROM_THEME'}})
    text='Đây là câu chuyện hư cấu. Lan đặt sổ thu chi lên bàn.'
    if case=='spoken_enum_only': text+=' '+mode
    script=FullScript('EP_MODE','Tập',{},adaptation_context=script_context,segments=[
        ScriptSegment('001',text=text),ScriptSegment('002',text='Cảm ơn quý vị đã lắng nghe. Hẹn gặp lại.',delivery_profile='ENDING')])
    report=qc_env['qc'].run_qc(script,bible)
    conflicts=[c for c in report.fact_conflicts if c.get('fact_id')=='MODE']
    assert bool(conflicts) is (case!='matching')
    if conflicts: assert 'metadata/lineage' in conflicts[0]['description']
    if case=='matching': assert mode not in ' '.join(s.text for s in script.segments)


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
    rules = {iss.get("rule") for iss in [*report.evidence_issues, *report.warnings]}
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
    assert any(iss.get("rule") == "ENDING_PROPORTION_VIOLATION" for iss in [*report.evidence_issues, *report.warnings])  # style: non-blocking warning


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
    assert any(iss.get("rule") == "MELODRAMA_DENSITY_V2" for iss in [*report.evidence_issues, *report.warnings])  # style: non-blocking warning
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
    assert any(iss.get("rule") == "ENDING_SEMANTIC_REPETITION" for iss in [*report.evidence_issues, *report.warnings])  # style: non-blocking warning

    revised, final_rep = rev.auto_revise_and_recheck(script, bible, report)
    assert final_rep.status == "PASS"



def test_style_findings_are_warnings_and_do_not_block_pass(qc_env):
    """A script whose only findings are judgement/style calls passes, with warnings attached."""
    qc: ScriptQCEngine = qc_env["qc"]
    report = qc.run_qc(FullScript(episode_id="EP_W", title="t", host={"id": "MINH"}, segments=_base_valid_segments()), StoryBible(episode_id="EP_W", title="t", protagonist={"name": "Tuấn"}))
    blocking_rules = {i.get("rule") for i in report.evidence_issues}
    assert all(i.get("blocking") is False for i in report.warnings)
    assert not ({i.get("rule") for i in report.warnings} & blocking_rules)


def test_on_topic_story_with_different_wording_is_not_topic_drift(qc_env):
    """An affair story that says 'quan hệ ngoài hôn nhân' instead of 'ngoại tình' is on topic."""
    qc: ScriptQCEngine = qc_env["qc"]
    segs = _base_valid_segments()
    segs[1].text = "Quân tìm thấy chiếc điện thoại cũ của vợ trong hộp đồ gia đình, với tin nhắn của một đồng nghiệp."
    segs[5].text = "Lan thừa nhận cô đã có mối quan hệ ngoài hôn nhân với Đức, đồng nghiệp cùng công ty, suốt tám tháng."
    bible = StoryBible(
        episode_id="EP_TOPIC", title="Chiếc điện thoại", protagonist={"name": "Quân"},
        original_user_topic="bí mật người vợ ngoại tình",
        clues=["Tin nhắn với đồng nghiệp trong điện thoại cũ", "Lịch làm việc không khớp"],
        reveal_1="Người nhắn tin là Đức, đồng nghiệp của Lan.",
        reveal_2="Lan thừa nhận mối quan hệ ngoài hôn nhân với Đức.",
    )
    report = qc.run_qc(FullScript(episode_id="EP_TOPIC", title="t", host={"id": "MINH"}, segments=segs), bible)
    assert not any(i.get("rule") == "FINAL_SCRIPT_TOPIC_DRIFT" for i in report.evidence_issues)


def test_letter_voice_mixup_is_blocking(qc_env):
    """Only the letter sender 'writes'; another character writing the letter is an objective error."""
    qc: ScriptQCEngine = qc_env["qc"]
    segs = _base_valid_segments()
    segs[6].text = "Lan viết rằng lúc ấy anh vẫn muốn tin mọi chuyện chỉ liên quan đến công việc."
    bible = StoryBible(
        episode_id="EP_VOICE", title="t", protagonist={"name": "Dũng"},
        supporting_characters=[{"name": "Trần Ngọc Lan", "role": "Vợ"}],
    )
    report = qc.run_qc(FullScript(episode_id="EP_VOICE", title="t", host={"id": "MINH"}, segments=segs), bible)
    assert any(i.get("rule") == "LETTER_VOICE_MIXUP" for i in report.evidence_issues)
    assert report.status != "PASS"


def test_story_bible_prop_location_contradiction_blocks():
    """EP2009 audit regression: coat in meeting room (title) vs coat in car (trigger) must block Story Bible."""
    from apps.script_factory.story_qc import StoryQCEngine

    bible = StoryBible(
        episode_id="EP_PROP_LOC",
        title="Chiếc Áo Khoác Trong Phòng Họp Cuối Tầng",
        protagonist={"name": "Ngọc Anh", "age": 30},
        narrative_skeleton={"trigger": "Ngọc Anh tìm thấy áo khoác nữ trong xe Quang."},
        clues=["Hóa đơn sửa xe", "Lịch trình bất thường"],
        reveal_1="Người đi cùng Quang là Thu Hà.",
        reveal_2="Thu Hà thừa nhận mối quan hệ ngoài luồng.",
        secret="Quang ngoại tình với Thu Hà.",
        ending="Ngọc Anh quyết định ly hôn.",
    )
    report = StoryQCEngine().audit_story_bible(bible)
    assert report.status == "FAIL"
    assert "PROP_LOCATION_CONTRADICTION" in report.rule_codes


def test_story_bible_unresolved_core_prop_blocks():
    """EP2009 audit regression: core prop in title/trigger never explained in reveal/ending must block."""
    from apps.script_factory.story_qc import StoryQCEngine

    bible = StoryBible(
        episode_id="EP_UNRESOLVED_PROP",
        title="Chiếc Áo Khoác Trong Phòng Họp Cuối Tầng",
        protagonist={"name": "Ngọc Anh", "age": 30},
        narrative_skeleton={"trigger": "Ngọc Anh tìm thấy áo khoác nữ trong phòng họp cuối tầng."},
        clues=["Kẹp tóc lạ", "Lịch họp bất thường"],  # does not check áo khoác
        reveal_1="Người để quên kẹp tóc là Thu Hà.",  # does not resolve áo khoác
        reveal_2="Thu Hà thừa nhận mối quan hệ ngoài luồng.",
        secret="Quang ngoại tình với Thu Hà.",
        ending="Ngọc Anh quyết định ly hôn.",
    )
    report = StoryQCEngine().audit_story_bible(bible)
    assert report.status == "FAIL"
    assert "UNRESOLVED_CORE_PROP" in report.rule_codes


def test_objective_logic_rules_block_when_critical(qc_env):
    """POV_KNOWLEDGE_VIOLATION, TIMELINE_ORDER_ERROR, REPEATED_DISCOVERY with CRITICAL severity must block."""
    from apps.script_factory.narrative_rules import is_blocking_logic_issue

    for rule in ["POV_KNOWLEDGE_VIOLATION", "TIMELINE_ORDER_ERROR", "REPEATED_DISCOVERY"]:
        issue = {"rule": rule, "severity": "CRITICAL", "message": "Objective logic error"}
        assert is_blocking_logic_issue(issue) is True, f"{rule} should be blocking"


def test_hook_discovery_timeline_contradiction(qc_env):
    """EP2010 regression: Hook says found on 'tối hôm ấy' but body narrates discovery on 'sáng hôm sau'."""
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_HOOK_TIME_BUG",
        title="Chiếc Kẹp Pha Lê Trong Túi Áo Khoác Của Chồng",
        protagonist={"name": "Lan", "char_id": "LAN"},
    )
    segments = [
        ScriptSegment(id="001", speaker="MINH", text="Lan nhớ cảm giác đứng trong phòng giặt đồ tối hôm ấy, chiếc kẹp nhỏ nằm giữa lòng bàn tay.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Mọi chuyện bắt đầu từ những nghi ngờ về cuộc hôn nhân của mình.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Quý vị sẽ phản ứng thế nào khi rơi vào hoàn cảnh ấy?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="004", speaker="MINH", text="Tối hôm đó, Nam về nhà muộn hơn thường lệ và treo áo khoác lên ghế.", delivery_profile="NORMAL"),
        ScriptSegment(id="005", speaker="MINH", text="Sáng hôm sau, Lan lấy chiếc áo khoác ấy để giặt và phát hiện chiếc kẹp tóc pha lê trong túi áo.", delivery_profile="MYSTERY"),
        ScriptSegment(id="006", speaker="MINH", text="Sự thật được phơi bày: Nam đã thú nhận toàn bộ sự thật.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="007", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_HOOK_TIME_BUG",
        title=bible.title,
        host={"id": "MINH", "name": "MC Minh"},
        segments=segments,
    )
    report = qc.run_qc(script, bible)
    assert report.status != "PASS"
    all_issues = [*report.evidence_issues, *report.fact_conflicts]
    assert any(
        i.get("rule") == "TIMELINE_ORDER_ERROR" or i.get("type") == "HOOK_TIMELINE_CONTRADICTION"
        for i in all_issues
    )


def test_prop_location_contradiction(qc_env):
    """EP2010 regression: Prop placed on table in earlier segment is later described as in pocket."""
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_PROP_LOC_BUG",
        title="Chiếc Kẹp Pha Lê Trong Túi Áo Khoác Của Chồng",
        protagonist={"name": "Lan", "char_id": "LAN"},
    )
    segments = [
        ScriptSegment(id="001", speaker="MINH", text="Lan tìm thấy chiếc kẹp tóc pha lê và đặt ra nhiều câu hỏi.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Chào mừng quý vị đến với Sau Cánh Cửa.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Quý vị có từng trải qua cảm giác này?", delivery_profile="COMMENT", audience_address=True),
        ScriptSegment(id="004", speaker="MINH", text="Lan lấy chiếc áo khoác của chồng đi giặt.", delivery_profile="NORMAL"),
        ScriptSegment(id="005", speaker="MINH", text="Cô lấy chiếc kẹp tóc ra khỏi túi áo khoác.", delivery_profile="NORMAL"),
        ScriptSegment(id="006", speaker="MINH", text="Cô đặt chiếc kẹp lên bàn, nhìn nó rất lâu rồi mới gọi tên chồng trong đầu.", delivery_profile="MYSTERY"),
        ScriptSegment(id="007", speaker="MINH", text="Trong túi áo, ngoài chiếc kẹp pha lê, cô tìm thấy một tờ giấy vẽ gấp tư.", delivery_profile="MYSTERY"),
        ScriptSegment(id="008", speaker="MINH", text="Sự thật được xác thực: Đó là sự nhầm lẫn của con trẻ.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="009", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe câu chuyện hôm nay.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_PROP_LOC_BUG",
        title=bible.title,
        host={"id": "MINH", "name": "MC Minh"},
        segments=segments,
    )
    report = qc.run_qc(script, bible)
    assert report.status != "PASS"
    all_issues = [*report.evidence_issues, *report.fact_conflicts]
    assert any(
        i.get("rule") == "PROP_LOCATION_CONTRADICTION" or i.get("type") == "PROP_LOCATION_CONTRADICTION"
        for i in all_issues
    )


def test_legitimate_next_morning_observation_not_blocked(qc_env):
    """Observing an already found and placed prop on the table the next morning is not a timeline conflict."""
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_OBSERVE_OK",
        title="Chiếc Kẹp Pha Lê",
        protagonist={"name": "Lan", "char_id": "LAN"},
    )
    segments = [
        ScriptSegment(id="001", speaker="MINH", text="Tối hôm ấy, Lan tìm thấy chiếc kẹp tóc trong túi áo của Hùng.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Lan lấy chiếc kẹp ra khỏi túi áo và đặt nó lên bàn.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Sáng hôm sau, Lan thấy chiếc kẹp trên bàn, vẫn đúng nơi cô đã đặt tối qua.", delivery_profile="NORMAL"),
        ScriptSegment(id="004", speaker="MINH", text="Sự thật được sáng tỏ: Hùng thú nhận món quà bất ngờ cho mẹ.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="005", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_OBSERVE_OK",
        title=bible.title,
        host={"id": "MINH", "name": "MC Minh"},
        segments=segments,
    )
    report = qc.run_qc(script, bible)
    timeline_issues = [i for i in report.evidence_issues if i.get("rule") == "HOOK_TIMELINE_CONTRADICTION"]
    assert len(timeline_issues) == 0, f"Expected no HOOK_TIMELINE_CONTRADICTION, got {timeline_issues}"


def test_legitimate_explicit_return_to_pocket_not_blocked(qc_env):
    """When a prop is explicitly returned to container, finding other items in container later is valid."""
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_RETURN_OK",
        title="Chiếc Kẹp Pha Lê",
        protagonist={"name": "Lan", "char_id": "LAN"},
    )
    segments = [
        ScriptSegment(id="001", speaker="MINH", text="Lan băn khoăn về chiếc kẹp tóc.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Lan lấy chiếc kẹp tóc ra khỏi túi áo khoác.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Cô đặt chiếc kẹp lên bàn.", delivery_profile="NORMAL"),
        ScriptSegment(id="004", speaker="MINH", text="Lan cất chiếc kẹp trở lại vào túi áo.", delivery_profile="NORMAL"),
        ScriptSegment(id="005", speaker="MINH", text="Trong túi áo, ngoài chiếc kẹp pha lê, Lan tìm thấy một tờ giấy.", delivery_profile="MYSTERY"),
        ScriptSegment(id="006", speaker="MINH", text="Sự thật được sáng tỏ: tờ giấy là hóa đơn mua quà.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="007", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_RETURN_OK",
        title=bible.title,
        host={"id": "MINH", "name": "MC Minh"},
        segments=segments,
    )
    report = qc.run_qc(script, bible)
    prop_issues = [i for i in report.evidence_issues if i.get("rule") == "PROP_LOCATION_CONTRADICTION"]
    assert len(prop_issues) == 0, f"Expected no PROP_LOCATION_CONTRADICTION, got {prop_issues}"


def test_ep2010_split_scene_discovery_timeline_contradiction(qc_env):
    """EP2010 real pattern: Hook says 'tối hôm ấy' in laundry room, body at [014] says 'Sáng hôm sau' touched object and [015] names prop."""
    qc: ScriptQCEngine = qc_env["qc"]
    bible = StoryBible(
        episode_id="EP_SPLIT_BUG",
        title="Chiếc Kẹp Pha Lê Trong Túi Áo Khoác Của Chồng",
        protagonist={"name": "Lan", "char_id": "LAN"},
    )
    segments = [
        ScriptSegment(id="001", speaker="MINH", text="Lan nhớ cảm giác đứng trong phòng giặt đồ tối hôm ấy, chiếc kẹp nhỏ nằm giữa lòng bàn tay.", delivery_profile="HOOK"),
        ScriptSegment(id="002", speaker="MINH", text="Mọi chuyện bắt đầu từ những nghi ngờ về cuộc hôn nhân của mình.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Tối hôm đó, Nam về nhà muộn hơn thường lệ và treo áo khoác lên ghế.", delivery_profile="NORMAL"),
        ScriptSegment(id="004", speaker="MINH", text="Sáng hôm sau, Lan lấy chiếc áo khoác ấy để giặt. Khi đưa tay vào túi áo bên phải, cô chạm phải một vật cứng nhỏ.", delivery_profile="MYSTERY"),
        ScriptSegment(id="005", speaker="MINH", text="Lan kể trong thư rằng cô lấy ra một chiếc kẹp tóc pha lê.", delivery_profile="MYSTERY"),
        ScriptSegment(id="006", speaker="MINH", text="Sự thật được phơi bày: Nam thú nhận toàn bộ.", delivery_profile="REVEAL", importance="critical"),
        ScriptSegment(id="007", speaker="MINH", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_SPLIT_BUG",
        title=bible.title,
        host={"id": "MINH", "name": "MC Minh"},
        segments=segments,
    )
    report = qc.run_qc(script, bible)
    timeline_issues = [i for i in report.evidence_issues if i.get("rule") == "HOOK_TIMELINE_CONTRADICTION"]
    assert len(timeline_issues) >= 1, "Expected HOOK_TIMELINE_CONTRADICTION for split discovery scene"


def test_gate_handles_missing_or_error_semantic_review_safely(tmp_path):
    """validate_full_script must never throw UnboundLocalError when semantic review is missing, NOT_RUN, or ERROR."""
    from studio.backend.services.artifact_lineage import validate_full_script
    import json

    proj_dir = tmp_path / "EPTESTGATE"
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.json").write_text(json.dumps({"stage_statuses": {"03_script": "DRAFT"}}), encoding="utf-8")
    (proj_dir / "story").mkdir()
    (proj_dir / "story" / "story_bible.json").write_text(json.dumps({
        "title": "Bí Mật", "generation_source": "REAL_AI", "generation_request_id": "req-story-12345"
    }), encoding="utf-8")
    (proj_dir / "script").mkdir()
    script_data = {
        "title": "Bí Mật", "generation_source": "REAL_AI", "generation_request_id": "req-script-12345",
        "source_story_generation_request_id": "req-story-12345",
        "segments": [{"id": "001", "text": "Lan mở thư.", "delivery_profile": "NORMAL"},
                     {"id": "002", "text": "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "delivery_profile": "ENDING"}]
    }
    (proj_dir / "script" / "full_script.json").write_text(json.dumps(script_data), encoding="utf-8")

    # 1. Missing review / NOT_RUN with warnings
    qc_not_run = {
        "qc_version": "script-qc-v2.8-melodrama-tiered",
        "status": "PASS",
        "script_content_hash": "dummy",
        "semantic_review": {"status": "NOT_RUN", "issues": [], "advisories": []},
        "warnings": [{"rule": "ENDING_NOT_DELIVERED", "severity": "WARNING", "blocking": False}],
        "evidence_issues": [],
    }
    (proj_dir / "script" / "qc_report.json").write_text(json.dumps(qc_not_run), encoding="utf-8")
    res_not_run = validate_full_script("EPTESTGATE", tmp_path)
    assert res_not_run["audio_gate_allowed"] is False
    assert "QC logic" in str(res_not_run["audio_gate_reason"])

    # 2. ERROR review with critical evidence
    qc_error = {
        "qc_version": "script-qc-v2.8-melodrama-tiered",
        "status": "FAIL",
        "script_content_hash": "dummy",
        "semantic_review": {"status": "ERROR", "error": "Quota exhausted"},
        "evidence_issues": [{"rule": "TIMELINE_ORDER_ERROR", "severity": "CRITICAL"}],
        "warnings": [],
    }
    (proj_dir / "script" / "qc_report.json").write_text(json.dumps(qc_error), encoding="utf-8")
    res_error = validate_full_script("EPTESTGATE", tmp_path)
    assert res_error["audio_gate_allowed"] is False
    assert "QC logic" in str(res_error["audio_gate_reason"]) or "CRITICAL" in str(res_error["audio_gate_reason"])


def test_auto_repair_script_updates_requested_and_actual_model_metadata(tmp_path):
    """auto_repair_script must accurately record the new provider/model that repaired the script."""
    from studio.backend.services.generation_service import GenerationService
    from studio.backend.services import generation_service as gen_module
    from types import SimpleNamespace
    from unittest.mock import patch
    import json
    import copy

    proj_dir = tmp_path / "EPTESTREPAIR"
    proj_dir.mkdir(parents=True)
    from studio.backend.services.artifact_lineage import story_content_hash
    story_dict = {
        "episode_id": "EPTESTREPAIR",
        "title": "Bí mật", "generation_source": "REAL_AI", "generation_request_id": "req-story-12345",
        "protagonist": {"name": "Lan"},
    }
    (proj_dir / "story").mkdir(parents=True, exist_ok=True)
    (proj_dir / "story" / "story_bible.json").write_text(json.dumps(story_dict), encoding="utf-8")
    (proj_dir / "script").mkdir()
    initial_script = {
        "episode_id": "EPTESTREPAIR",
        "title": "Bí mật",
        "host": {"id": "MINH", "name": "MC Minh"},
        "generation_source": "REAL_AI",
        "generation_request_id": "req-script-12345",
        "source_story_generation_request_id": "req-story-12345",
        "source_story_content_hash": story_content_hash(story_dict),
        "provider_name": "initial-provider",
        "model_name": "gemini-2.5-flash",
        "requested_model": "gemini-2.5-flash",
        "actual_model": "gemini-3.5-flash",
        "segments": [{"id": "001", "text": "Lan băn khoăn.", "delivery_profile": "NORMAL"}],
    }
    (proj_dir / "script" / "full_script.json").write_text(json.dumps(initial_script), encoding="utf-8")
    (proj_dir / "script" / "qc_report.json").write_text(json.dumps({"status": "NEEDS_REVISION"}), encoding="utf-8")

    changed_script = FullScript.from_dict(copy.deepcopy(initial_script))
    changed_script.segments[0].text = "Lan băn khoăn về người bạn đời sau khi thấy vết son."
    changed_script.model_name = "repaired-model"
    changed_script.actual_model = "repaired-model"
    changed_script.requested_model = "new-requested-model"
    changed_script.provider_name = "new-repair-provider"

    service = GenerationService.__new__(GenerationService)
    service.cost_ctrl = None
    fake_qc = SimpleNamespace(run_qc=lambda **kw: QCReport(episode_id="EPTESTREPAIR", status="NEEDS_REVISION"))
    new_qc = QCReport(episode_id="EPTESTREPAIR", status="PASS")

    with patch.object(gen_module, "PROJECTS_DIR", tmp_path), \
         patch.object(service, "get_provider", return_value=SimpleNamespace(provider_name="new-repair-provider")), \
         patch.object(gen_module, "ScriptQCEngine", return_value=fake_qc), \
         patch.object(gen_module, "AutoRevisionManager", return_value=SimpleNamespace()), \
         patch.object(gen_module, "_revise_keeping_best", return_value=(changed_script, new_qc)), \
         patch.object(gen_module, "invalidate_script_approval"):
        service.auto_repair_script("EPTESTREPAIR", provider_id="new-repair-provider", model_id="new-requested-model")

    saved = json.loads((proj_dir / "script" / "full_script.json").read_text(encoding="utf-8"))
    assert saved["provider_name"] == "new-repair-provider"
    assert saved["model_name"] == "repaired-model"
    assert saved["requested_model"] == "new-requested-model"
    assert saved["actual_model"] == "repaired-model"
    assert saved["parent_generation_request_id"] == "req-script-12345"
    assert saved["generation_request_id"] != "req-script-12345"


@pytest.mark.parametrize("case,expected_contradiction", [
    ("no_return_then_claim_pocket_invalid_control", True),
    ("return_to_same_pocket_valid", False),
    ("return_to_handbag_then_claim_pocket_invalid", True),
    ("handbag_location_valid", False),
    ("wrong_prop_in_same_sentence", True),
])
def test_prop_location_container_and_action_discrimination(tmp_path, case, expected_contradiction):
    """Codex review 8b50926 regressions:
    1. Túi xách vs túi áo must be normalized as distinct containers.
    2. Multi-prop actions must bind to the specific object, not other props in sentence.
    """
    from apps.script_factory.semantic_review import SEMANTIC_REVIEW_VERSION, script_content_hash, story_bible_content_hash
    engine = ScriptQCEngine(episodes_root=tmp_path)
    start = [
        "Lan băn khoăn về chiếc kẹp tóc.",
        "Lan lấy chiếc kẹp ra khỏi túi áo.",
        "Lan đặt chiếc kẹp lên bàn.",
    ]
    test_cases = {
        "no_return_then_claim_pocket_invalid_control": start + [
            "Trong túi áo, ngoài chiếc kẹp, Lan tìm thấy một tờ giấy."
        ],
        "return_to_same_pocket_valid": start + [
            "Lan cất chiếc kẹp trở lại vào túi áo.",
            "Trong túi áo, ngoài chiếc kẹp, Lan tìm thấy một tờ giấy."
        ],
        "return_to_handbag_then_claim_pocket_invalid": start + [
            "Lan cất chiếc kẹp vào túi xách.",
            "Trong túi áo, ngoài chiếc kẹp, Lan tìm thấy một tờ giấy."
        ],
        "handbag_location_valid": start + [
            "Lan cất chiếc kẹp vào túi xách.",
            "Trong túi xách, ngoài chiếc kẹp, Lan tìm thấy một tờ giấy."
        ],
        "wrong_prop_in_same_sentence": start + [
            "Lan đặt chiếc kẹp trên bàn rồi cất thỏi son vào túi áo.",
            "Trong túi áo, ngoài chiếc kẹp, Lan tìm thấy một tờ giấy."
        ],
    }
    texts = test_cases[case]
    bible = StoryBible(episode_id="EP_PROP_AUDIT", title="Chiếc kẹp", protagonist={"name": "Lan"})
    script = FullScript(
        episode_id="EP_PROP_AUDIT",
        title=bible.title,
        host={"id": "MINH"},
        segments=[
            ScriptSegment(id=f"{i+1:03}", text=t, delivery_profile="HOOK" if i == 0 else "NORMAL")
            for i, t in enumerate(texts)
        ],
    )
    review = dict(
        status="RUN",
        passes=2,
        review_version=SEMANTIC_REVIEW_VERSION,
        script_hash=script_content_hash(script),
        story_hash=story_bible_content_hash(bible),
        issues=[],
        advisories=[],
    )
    qc = engine.run_qc(script, bible, semantic_review=review)
    prop_findings = [i for i in qc.evidence_issues if i.get("rule") == "PROP_LOCATION_CONTRADICTION"]
    if expected_contradiction:
        assert len(prop_findings) > 0, f"Expected PROP_LOCATION_CONTRADICTION for {case}, got none"
    else:
        assert len(prop_findings) == 0, f"Expected valid location for {case}, got {prop_findings}"


def test_real_repair_loop_records_current_requested_model_through_real_manager(tmp_path):
    """Codex review 8b50926 regression:
    auto_repair_script -> _revise_keeping_best -> AutoRevisionManager must record effective requested_model,
    fallback actual_model, and parent_generation_request_id through real manager execution.
    """
    import json
    from studio.backend.services.generation_service import GenerationService
    from studio.backend.services import generation_service as gen_module
    from studio.backend.services.artifact_lineage import story_content_hash
    from types import SimpleNamespace
    from unittest.mock import patch

    proj = tmp_path / "EP_REAL_REPAIR"
    (proj / "story").mkdir(parents=True, exist_ok=True)
    (proj / "script").mkdir(parents=True, exist_ok=True)
    story = {
        "episode_id": "EP_REAL_REPAIR",
        "title": "Bí mật",
        "generation_request_id": "story-req-111",
        "generation_source": "REAL_AI",
        "protagonist": {"name": "Lan"},
    }
    initial = FullScript(
        episode_id="EP_REAL_REPAIR",
        title="Bí mật",
        host={"id": "MINH"},
        segments=[ScriptSegment(id="001", text="Lan mở thư.", delivery_profile="HOOK")],
        generation_request_id="script-req-222",
        generation_source="REAL_AI",
        requested_model="old-model",
        actual_model="old-model",
        model_name="old-model",
    ).to_dict()
    initial.update(
        source_story_generation_request_id=story["generation_request_id"],
        source_story_content_hash=story_content_hash(story),
    )
    (proj / "story" / "story_bible.json").write_text(json.dumps(story), encoding="utf-8")
    (proj / "script" / "full_script.json").write_text(json.dumps(initial), encoding="utf-8")

    class Provider:
        provider_name = "gemini"
        default_model = "selected-new-model"
        last_used_model = "fallback-actual-model"
        last_actual_model = "fallback-actual-model"

        def revise_script(self, script, story_bible, qc_report, model=None):
            self.effective_requested_model = model or self.default_model
            script.segments[0].text += " Cô nhận ra chữ viết của Hùng."
            script.revision_round += 1
            return script, 10, 20

    class QCStub:
        def run_qc(self, script, story_bible, model=None):
            return QCReport(episode_id="EP_REAL_REPAIR", status="PASS" if script.revision_round else "NEEDS_REVISION")

    provider = Provider()
    service = GenerationService.__new__(GenerationService)
    service.cost_ctrl = SimpleNamespace(
        check_budget_pre_flight=lambda **kw: None,
        record_operation=lambda **kw: None,
    )

    with patch.object(gen_module, "PROJECTS_DIR", tmp_path), \
         patch.object(service, "get_provider", return_value=provider), \
         patch.object(gen_module, "ScriptQCEngine", return_value=QCStub()), \
         patch.object(gen_module, "invalidate_script_approval"):
        service.auto_repair_script("EP_REAL_REPAIR", provider_id="gemini", model_id="selected-new-model")

    saved = json.loads((proj / "script" / "full_script.json").read_text(encoding="utf-8"))
    assert provider.effective_requested_model == "selected-new-model"
    assert saved.get("requested_model") == "selected-new-model"
    assert saved.get("actual_model") == "fallback-actual-model"
    assert saved.get("model_name") == "fallback-actual-model"
    assert saved.get("parent_generation_request_id") == "script-req-222"
    assert saved.get("generation_request_id") != "script-req-222"


def _build_unfinished_setup_review(problem):
    import json
    from apps.script_factory.semantic_review import review_script_logic
    script = FullScript(
        episode_id='UNRESOLVED',
        title='Bức thư bị bỏ quên',
        host={'id': 'MINH'},
        segments=[
            ScriptSegment(id='001', text='Lan nhận được phong bì niêm phong, bên trong hứa chứa lời giải thích về khoản tiền mất tích.', delivery_profile='HOOK'),
            ScriptSegment(id='002', text='Lan bước ra khỏi nhà và bắt đầu cuộc sống mới.'),
            ScriptSegment(id='003', text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile='ENDING'),
        ]
    )
    issue = {
        'rule': 'UNRESOLVED_SETUP',
        'segment_id': '001',
        'quote': script.segments[0].text,
        'problem': problem,
        'fix': 'Bổ sung cảnh đọc thư và giải thích khoản tiền.',
        'confidence': 'high'
    }
    calls = []
    def reviewer(system, prompt):
        calls.append(prompt)
        return json.dumps({'issues': [issue]}, ensure_ascii=False), 10, 20
    review = review_script_logic(
        script,
        StoryBible(episode_id=script.episode_id, title=script.title, protagonist={'name': 'Lan'}),
        reviewer
    )
    return review, len(calls)


@pytest.mark.parametrize('problem', [
    'Phong bì đã được hứa là đáp án nhưng bị bỏ quên đến hết truyện.',
    'Phong bì đã được hứa là đáp án nhưng phần reveal vẫn không mở thư và không giải thích khoản tiền.',
    'Mặc dù phân đoạn cuối kể Lan rời đi, không có cảnh mở phong bì và không trả lời khoản tiền mất tích.',
    'Phong bì ở phân đoạn 001 bị lãng quên đến cuối truyện.',
    'Phong bì bị lãng quên; phân đoạn 002 kết thúc câu chuyện thay vì giải đáp nguồn tiền.',
])
def test_anchored_unresolved_setup_must_not_disappear(problem):
    """Deep audit P1: UNRESOLVED_SETUP must never be dropped due to keywords like 'phần reveal' when payoff is missing."""
    review, calls = _build_unfinished_setup_review(problem)
    assert any(i['rule'] == 'UNRESOLVED_SETUP' for i in review['issues']), (
        f"UNRESOLVED_SETUP was dropped for problem: {problem}"
    )


def test_verified_payoff_in_later_segment_skips_false_unresolved_setup():
    """Valid control: when payoff actually exists in segment 002 and is verified, reviewer critique about delayed payoff can be skipped."""
    import json
    from apps.script_factory.semantic_review import review_script_logic
    script = FullScript(
        episode_id='RESOLVED',
        title='Bức thư đã mở',
        host={'id': 'MINH'},
        segments=[
            ScriptSegment(id='001', text='Lan nhận được phong bì niêm phong từ người lạ.', delivery_profile='HOOK'),
            ScriptSegment(id='002', text='Lan mở phong bì niêm phong rồi đọc bức thư: mẹ cô đã giữ khoản tiền để trả viện phí cho cha.'),
            ScriptSegment(id='003', text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile='ENDING'),
        ]
    )
    issue = {
        'rule': 'UNRESOLVED_SETUP',
        'segment_id': '001',
        'quote': script.segments[0].text,
        'problem': 'Chi tiết phong bì niêm phong đã được giải quyết ở phân đoạn [002]',
        'fix': 'Không cần sửa.',
        'confidence': 'low'
    }
    def reviewer(system, prompt):
        return json.dumps({'issues': [issue]}, ensure_ascii=False), 10, 20
    review = review_script_logic(
        script,
        StoryBible(episode_id=script.episode_id, title=script.title, protagonist={'name': 'Lan'}),
        reviewer
    )
    assert not any(i['rule'] == 'UNRESOLVED_SETUP' for i in review['issues'])


@pytest.mark.parametrize('profile', ['NORMAL', 'REVEAL', 'CLIMAX'])
def test_early_truth_cannot_bypass_release_map_by_label(profile):
    """Deep audit P1: delivery_profile REVEAL or CLIMAX must not bypass SpoilerTimingGuard."""
    from apps.script_factory.information_release_map import InformationReleaseMap, InformationReleaseRule
    from apps.script_factory.spoiler_timing_guard import SpoilerTimingGuard
    rule = InformationReleaseRule(
        fact_id='TRUTH',
        fact_type='REVEAL_2',
        field='reveal_2',
        description='Danh tính người giữ tiền',
        target_value='Thu Ngân',
        earliest_allowed_segment=76,
        forbidden_before_segment=76,
        key_entities=['Thu Ngân'],
        sensitivity_level='CRITICAL'
    )
    guard = SpoilerTimingGuard(InformationReleaseMap(episode_id='SPOILER', total_segments=90, rules=[rule]))
    segment = ScriptSegment(id='020', text='Hóa ra Thu Ngân chính là người đã lấy toàn bộ số tiền.', delivery_profile=profile)
    assert guard.check_segment(segment), f'Early truth bypassed with {profile}'


def test_core_truth_fallback_scaling_matches_short_script():
    """Deep audit P2: InformationReleaseMap fallback scaling must scale earliest_allowed_segment and total_segments."""
    from apps.script_factory.information_release_map import build_information_release_map
    bible = StoryBible(episode_id='SHORT', title='Khoản tiền bị mất', protagonist={'name': 'Lan'})
    release_map = build_information_release_map(
        bible,
        fact_locks=[{'fact_id': 'TRUTH', 'field': 'hidden_truth', 'description': 'bí mật cốt lõi', 'value': 'Thu Ngân'}],
        total_segments=56
    )
    rule = next(r for r in release_map.rules if r.fact_id == 'TRUTH')
    assert rule.earliest_allowed_segment <= 56, f'Unreachable reveal threshold: {rule.earliest_allowed_segment}'
    assert release_map.total_segments == 56


def test_script_qc_repairs_full_story_restart():
    """Verify that ScriptQC apply_targeted_repairs handles a full story restart from the beginning,
    pruning duplicate segments cleanly instead of leaving fragmented story pieces."""
    from apps.script_factory.models import ScriptSegment, FullScript, StoryBible, QCReport
    from apps.script_factory.script_qc import apply_targeted_repairs

    first_half = [
        ScriptSegment(id=f"{i+1:03d}", text=f"Lan theo dõi từng bước đi của chồng ở giai đoạn {i} nhằm làm sáng tỏ.", delivery_profile="NORMAL")
        for i in range(50)
    ]
    first_half[0] = ScriptSegment(id="001", text='Lá thư bắt đầu bằng câu chuyện nghi vấn.', delivery_profile="HOOK")
    first_half[1] = ScriptSegment(id="002", text='Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.', delivery_profile="NORMAL")
    first_half[48] = ScriptSegment(id="049", text='Lan đối chất và chồng thừa nhận toàn bộ.', delivery_profile="REVEAL")
    first_half[49] = ScriptSegment(id="050", text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile="ENDING")

    second_half = [
        ScriptSegment(id=f"{i+51:03d}", text=f"Lan theo dõi lại từng bước đi của chồng ở giai đoạn {i} để làm sáng tỏ.", delivery_profile="NORMAL")
        for i in range(55)
    ]
    second_half[0] = ScriptSegment(id="051", text='Lá thư bắt đầu bằng câu chuyện nghi vấn.', delivery_profile="HOOK")
    second_half[1] = ScriptSegment(id="052", text='Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.', delivery_profile="NORMAL")
    second_half[53] = ScriptSegment(id="104", text='Lan đối chất và chồng thừa nhận toàn bộ sự thật.', delivery_profile="REVEAL")
    second_half[54] = ScriptSegment(id="105", text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile="ENDING")

    all_segs = first_half + second_half
    for idx, s in enumerate(all_segs, start=1):
        s.id = f"{idx:03d}"

    bible = StoryBible(episode_id="EP_RESTART", title="Khởi động lại", protagonist={"name": "Lan"})
    script = FullScript(episode_id=bible.episode_id, title=bible.title, host={"id": "MINH"}, segments=all_segs)
    report = QCReport(
        episode_id=bible.episode_id,
        status="FAIL",
        evidence_issues=[{"rule": "REPEATED_NARRATIVE_BLOCK", "severity": "CRITICAL"}],
    )
    repaired = apply_targeted_repairs(script, bible, report)
    assert len(repaired.segments) in (50, 55)
    assert sum(1 for s in repaired.segments if "Chào mừng quý vị" in s.text) == 1
    assert [s.id for s in repaired.segments] == [f"{i+1:03d}" for i in range(len(repaired.segments))]





