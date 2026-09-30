"""Topic Hardening V2, Template Leakage Eradication & Production Verification Tests.

Covers:
1. test_real_script_topic_adherence_not_metadata
2. test_keyword_presence_does_not_equal_topic_centrality
3. test_story_bible_topic_drift_blocks_script_generation
4. test_full_script_topic_drift_blocks_human_pass
5. test_internal_template_labels_block_tts
6. test_production_never_silently_uses_mock_provider
7. test_gemini_failure_surfaces_error
8. test_topic_score_recalculated_per_stage
9. test_fake_serial_break_actual_phrase
10. test_broken_medical_story_fails_workplace_affair_topic
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock

from apps.script_factory.models import (
    FullScript,
    IdeaItem,
    LockedFact,
    ScriptSegment,
    StoryBible,
)
from apps.script_factory.leakage_guard import (
    clean_text_from_leakage,
    detect_internal_template_leakage,
    validate_script_segments_for_leakage,
)
from apps.script_factory.script_qc import ScriptQCEngine, apply_targeted_repairs
from apps.script_factory.story_qc import StoryQCEngine
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent
from studio.backend.services.generation_service import GenerationService


def make_mock_script(segments_text, title="Test Episode"):
    segments = [
        ScriptSegment(id=f"{i+1:03d}", speaker="MINH", text=txt, delivery_profile="NORMAL")
        for i, txt in enumerate(segments_text)
    ]
    return FullScript(
        episode_id="EP_TEST",
        title=title,
        host={"id": "MINH", "display_name": "Minh", "voice": "Binh"},
        segments=segments,
        total_segments=len(segments),
        total_words=sum(len(s.text.split()) for s in segments),
        status="DRAFT"
    )


def test_infidelity_topic_accepts_natural_relationship_wording():
    intent = extract_topic_intent(
        "Linh đã ngoại tình với một đồng nghiệp cùng cơ quan và che giấu mối quan hệ vụng trộm bằng lý do tăng ca."
    )
    segments = [
        {"text": f"Hoàng đối chiếu lịch tăng ca và tin nhắn công việc bất thường thứ {index}."}
        for index in range(40)
    ]
    segments[4]["text"] = "Linh thừa nhận đã có một mối quan hệ tình cảm bí mật với đồng nghiệp."
    segments[18]["text"] = "Quan hệ tình cảm bí mật ấy bắt đầu từ những lần cùng làm dự án muộn."
    segments[30]["text"] = "Linh nói họ đã vượt qua ranh giới đồng nghiệp và che giấu mối quan hệ."

    result = intent.evaluate_content_adherence({"segments": segments}, stage="script")

    assert result["status"] == "PASS"
    assert result["topic_centrality_score"] >= 80.0


def test_real_script_topic_adherence_not_metadata():
    """1. Topic QC evaluates actual narration text, NOT metadata."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    # Script has metadata topic claiming adherence, but narration is about family surgery & hospital
    medical_narration = [
        "Sau Cánh Cửa xin chào quý vị.",
        "Câu chuyện hôm nay xảy ra khi người con dọn dẹp căn phòng cũ của mẹ.",
        "Một hồ sơ bệnh án và viện phí phẫu thuật 100.000.000 VND xuất hiện.",
        "Người cha đã âm thầm bán mảnh đất hương hỏa ở quê để lo chi phí ca phẫu thuật cứu con.",
        "Bệnh viện xác nhận mẹ đã hoãn lại ca phẫu thuật của chính mình để dồn tiền cho con.",
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."
    ]
    script = make_mock_script(medical_narration, title="Bí mật ngoại tình công sở")

    eval_result = ti.evaluate_content_adherence(script, stage="script")
    # Must fail because actual narration content has 0 workplace affair centrality
    assert eval_result["status"] == "FAIL"
    assert eval_result["score"] < 50.0
    assert eval_result["topic_centrality_score"] == 0.0
    assert eval_result["drift_detected"] is True


def test_keyword_presence_does_not_equal_topic_centrality():
    """2. Mere mention of a single keyword does not give a pass if narrative is foreign."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    # Narrator throws in 'công sở' once casually, but story is entirely about 100M VND surgery & land sale
    derailed_narration = [
        "Mỗi ngày sau giờ tan làm tại công sở, anh lại đến bệnh viện thăm mẹ.",
        "Khoản viện phí phẫu thuật 100.000.000 VND là gánh nặng lớn của cả nhà.",
        "Gia đình phải bán mảnh đất hương hỏa để chữa bệnh.",
        "Bác sĩ xác nhận cha đã hy sinh toàn bộ chi phí điều trị cá nhân.",
        "Sự thật về ca phẫu thuật khiến người con rơi nước mắt.",
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."
    ]
    script = make_mock_script(derailed_narration)

    eval_result = ti.evaluate_content_adherence(script, stage="script")
    assert eval_result["status"] == "FAIL"
    assert eval_result["topic_centrality_score"] < 40.0
    # Severe foreign tropes must trigger penalties
    assert any("phẫu thuật" in t or "100.000.000" in t for t in eval_result["drift_terms"])


def test_story_bible_topic_drift_blocks_script_generation():
    """3. Story Bible topic drift flags critical issue and blocks script generation."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    # Create Story Bible that drifted into ancestral land & hospital surgery
    drifted_bible = StoryBible(
        episode_id="EP999",
        title="Bí Mật Mảnh Đất",
        protagonist={"name": "Tuấn"},
        supporting_characters=[{"name": "Cha ruột"}],
        relationships=[{"char_a": "TUẤN", "char_b": "CHA", "relationship": "Cha con"}],
        timeline=["10 năm trước bán đất", "Hiện tại phẫu thuật"],
        locations=["Bệnh viện", "Vùng quê"],
        critical_facts=[LockedFact(fact_id="F1", field="viện phí", value="100.000.000 VND", description="Viện phí", status="LOCKED")],
        secret="Cha bán đất chữa bệnh nhưng giấu con",
        false_lead="Nghi ngờ cha lấy tiền cho người ngoài",
        clues=["Hồ sơ bệnh án", "Chứng từ chuyển tiền 100.000.000 VND", "Giấy bán đất"],
        reveal_1="Cha hy sinh tiền phẫu thuật của mình",
        reveal_2="Bệnh tình cha đã ở giai đoạn cuối",
        emotional_payoff="Hai cha con ôm nhau khóc",
        reflection_theme="Tình phụ tử bao la",
        original_user_topic=topic,
        topic_intent=ti.to_dict(),
        status="DRAFT"
    )

    qc_engine = StoryQCEngine()
    report = qc_engine.audit_story_bible(drifted_bible)

    # Must be marked as FAIL due to STORY_BIBLE_TOPIC_DRIFT
    assert report.status == "FAIL"
    rule_codes = [issue["rule"] for issue in report.issues]
    assert "STORY_BIBLE_TOPIC_DRIFT" in rule_codes
    assert drifted_bible.topic_adherence < 75.0


def test_full_script_topic_drift_blocks_human_pass():
    """4. Script topic drift marks status as FAIL and sets tts_readability to 40.0."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    story_bible = StoryBible(
        episode_id="EP_DRIFT",
        title="Ngoại tình công sở",
        protagonist={"name": "Hà"},
        secret="Quan hệ ngoài luồng giữa giám đốc và trợ lý",
        clues=["Lịch hẹn khách sạn", "Tin nhắn lén lút", "Hóa đơn thanh toán"],
        reveal_1="Hai người lén lút qua lại",
        reveal_2="Kế hoạch thâu tóm dự án",
        emotional_payoff="Hóa giải",
        reflection_theme="Lòng tin",
        original_user_topic=topic,
        topic_intent=ti.to_dict(),
    )

    # Generate a script that drifted into medical surgery & ancestral land
    segs = [
        "Sau Cánh Cửa nhận được tâm thư của Hà.",
        "Mẹ của Hà phải nhập viện cấp cứu vì bệnh nặng.",
        "Số tiền 100.000.000 VND viện phí khiến gia đình phải bán mảnh đất hương hỏa.",
        "Ca phẫu thuật thành công nhưng người cha đã qua đời vì kiệt sức.",
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."
    ]
    script = make_mock_script(segs, title="Ngoại tình công sở")

    qc_report = ScriptQCEngine.audit_script(script, story_bible, {}, {})
    assert qc_report.status == "FAIL"
    assert qc_report.scores["tts_readability"] == 40.0
    ev_rules = [e["rule"] for e in qc_report.evidence_issues]
    assert "FINAL_SCRIPT_TOPIC_DRIFT" in ev_rules


def test_internal_template_labels_block_tts():
    """5. Leaked internal scaffold/template labels trigger CRITICAL violation and block TTS."""
    leaked_texts = [
        "Nhân vật chính lúc này bàng hoàng không nói nên lời.",
        "Bước ngoặt 2: Chân tướng sự thật về bí mật tại văn phòng công ty.",
        "Manh mối 1: Dấu vết chữ viết tay và con dấu đã mờ trên phong bì.",
    ]

    for leaked in leaked_texts:
        violations = detect_internal_template_leakage(leaked)
        assert len(violations) >= 1
        assert violations[0]["severity"] == "CRITICAL"
        assert violations[0]["code"] == "INTERNAL_TEMPLATE_LEAKAGE"

    # Cleaning helper properly removes the template tags
    cleaned = clean_text_from_leakage("Bước ngoặt 2: Chân tướng sự thật về bí mật tại văn phòng: Họ đã ly hôn.", protagonist_name="Hà")
    assert "Bước ngoặt 2" not in cleaned
    assert "Chân tướng sự thật về bí mật" not in cleaned

    cleaned_protag = clean_text_from_leakage("Nhân vật chính cảm thấy hoang mang.", protagonist_name="Minh Tuấn")
    assert "Nhân vật chính" not in cleaned_protag
    assert "Minh Tuấn" in cleaned_protag


def test_production_never_silently_uses_mock_provider():
    """6. In production mode (APP_ENV != 'test'), missing credentials raise explicit error."""
    with patch.dict(os.environ, {"APP_ENV": "production", "PYTEST_CURRENT_TEST": ""}):
        with patch("studio.backend.services.generation_service.get_active_api_key", return_value=""):
            srv = GenerationService()
            with pytest.raises(RuntimeError) as exc_info:
                srv.get_provider()
            assert "AI GENERATION FAILED" in str(exc_info.value)
            assert "missing or not configured" in str(exc_info.value) or "silent mock fallback" in str(exc_info.value)


def test_gemini_failure_surfaces_error():
    """7. Gemini API failure surfaces clean descriptive error without silent mock fallback."""
    from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider

    with patch.dict(os.environ, {"APP_ENV": "production", "PYTEST_CURRENT_TEST": ""}):
        prov = GeminiScriptAIProvider(api_key="TEST_INVALID_KEY")
        with patch.object(prov, "_call_generate_content", side_effect=RuntimeError("Google Gemini API HTTP 403: API_KEY_INVALID")):
            with pytest.raises(RuntimeError) as exc_info:
                prov.generate_ideas(count=3, existing_ideas=[], diversity_categories=[], hook_archetypes=[], user_topic="Bí mật ngoại tình công sở")
            assert "Google Gemini API HTTP 403" in str(exc_info.value)


def test_topic_score_recalculated_per_stage():
    """8. Topic adherence score is recalculated independently per stage."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    # Stage 1: Idea is compliant
    good_idea = IdeaItem(
        idea_id="IDEA_001",
        working_title="Thẻ phòng khách sạn",
        hook="Phát hiện dấu hiệu ngoại tình công sở giữa trưởng phòng và nhân viên.",
        protagonist="Hà",
        relationship="Đồng nghiệp",
        central_secret="Mối quan hệ vụng trộm tại công sở",
        mystery_question="Ai là người gửi ảnh?",
        false_lead="Nghi ngờ bảo vệ",
        clue_1="Hóa đơn khách sạn trong cặp tài liệu",
        clue_2="Lịch họp ngoài giờ bất thường",
        clue_3="Tin nhắn hẹn hò lén lút",
        reveal_1="Hai người có quan hệ tình cảm vụng trộm",
        reveal_2="Mối quan hệ này dùng để thao túng hợp đồng",
        emotional_payoff="Giải tỏa áp lực",
        reflection_theme="Lòng tin nơi công sở",
        hook_archetype="OBJECT_DISCOVERY",
        twist_archetype="Workplace",
        original_user_topic=topic,
    )
    res_idea = ti.evaluate_content_adherence(good_idea, stage="idea")
    assert res_idea["score"] >= 80.0
    assert res_idea["status"] == "PASS"

    # Stage 2: StoryBible drifts into generic hospital/land story
    drifted_bible = StoryBible(
        episode_id="EP_DRIFT_BIBLE",
        title="Bí Mật Đất Vườn",
        protagonist={"name": "Hà"},
        secret="Cha bán đất chữa bệnh cho con 100.000.000 VND",
        clues=["Bệnh án", "Viện phí", "Giấy bán đất"],
        reveal_1="Phẫu thuật cứu sống con",
        reveal_2="Cha hy sinh bí mật",
        original_user_topic=topic,
        topic_adherence=res_idea["score"]  # Copied score
    )
    res_bible = ti.evaluate_content_adherence(drifted_bible, stage="story_bible")
    # Score MUST drop dramatically despite previous stage score
    assert res_bible["score"] < 50.0
    assert res_bible["status"] == "FAIL"


def test_fake_serial_break_actual_phrase():
    """9. The exact phrase 'Hẹn gặp lại quý vị trong tập tiếp theo của Sau Cánh Cửa.' is flagged and repaired."""
    segs = [
        ScriptSegment(id="001", speaker="MINH", text="Chào mừng quý vị đến với Sau Cánh Cửa.", delivery_profile="NORMAL"),
        ScriptSegment(id="002", speaker="MINH", text="Câu chuyện ngày hôm nay về gia đình.", delivery_profile="NORMAL"),
        ScriptSegment(id="003", speaker="MINH", text="Tôi là Minh. Xin kính chúc quý vị an lành. Hẹn gặp lại quý vị trong tập tiếp theo của Sau Cánh Cửa.", delivery_profile="ENDING"),
    ]
    script = FullScript(
        episode_id="EP_SERIAL",
        title="Test",
        host={"id": "MINH", "display_name": "Minh"},
        segments=segs,
        total_segments=len(segs),
        total_words=30,
        status="DRAFT"
    )
    bible = StoryBible(episode_id="EP_SERIAL", title="Test", protagonist={"name": "Nam"}, secret="Bí mật")

    qc_report = ScriptQCEngine.audit_script(script, bible, {}, {})
    ev_rules = [e["rule"] for e in qc_report.evidence_issues]
    assert "FAKE_SERIAL_BREAK" in ev_rules

    # Targeted repair must replace with standard channel sign-off
    repaired = apply_targeted_repairs(script, bible, qc_report)
    assert "tập tiếp theo" not in repaired.segments[-1].text
    assert "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại." in repaired.segments[-1].text


def test_broken_medical_story_fails_workplace_affair_topic():
    """10. Broken medical story (surgery/100M VND/land sale) evaluated against workplace affair fails with score 0.0."""
    topic = "Bí mật ngoại tình công sở"
    ti = extract_topic_intent(topic)

    # Narrative with the exact tropes from broken EP1005
    broken_segments = [
        "Hòm thư Sau Cánh Cửa nhận được tâm thư của nhân vật.",
        "Mọi thứ bắt đầu khi chạm vào tài liệu liên quan đến 100.000.000 VND và 10 năm.",
        "Xuất hiện chứng từ giao dịch ghi rõ khoản tiền 100.000.000 VND tại cơ quan lưu trữ địa phương.",
        "Biến cố tai nạn nguy kịch 10 năm trước đòi hỏi chi phí phẫu thuật khẩn cấp.",
        "Người thân đã quyết định bán mảnh đất hương hỏa để lấy 100.000.000 VND cho ca phẫu thuật.",
        "Người thân đồng thời phát hiện bệnh nặng tại bệnh viện nhưng dồn tiền chữa bệnh cho con.",
        "Khóa kín hồ sơ bệnh án trong chiếc hộp gỗ.",
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."
    ]
    broken_script = make_mock_script(broken_segments, title="Bí mật ngoại tình công sở")

    res = ti.evaluate_content_adherence(broken_script, stage="script")
    assert res["score"] == 0.0
    assert res["status"] == "FAIL"
    assert res["topic_centrality_score"] == 0.0
    assert res["topic_reveal_alignment"] == 0.0
    assert res["drift_detected"] is True
    # Verify foreign tropes identified
    assert any("phẫu thuật" in d for d in res["drift_terms"])
    assert any("100.000.000" in d for d in res["drift_terms"])
    assert any("bán mảnh đất" in d for d in res["drift_terms"])
