import json

from apps.script_factory.cost_control import CostController
from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.script_qc import ScriptQCEngine
from apps.script_factory.semantic_review import carry_over_semantic_review, review_script_logic, script_content_hash, story_bible_content_hash


def _script():
    return FullScript(
        episode_id="EP_SEM",
        title="Chiếc USB",
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", text="Tuấn tìm thấy chiếc USB dán nhãn báo cáo tài chính trên bàn của vợ.", delivery_profile="HOOK"),
            ScriptSegment(id="002", text="Anh đến phòng khám và làm xét nghiệm ADN một mình, không cần mẫu của Mai."),
            ScriptSegment(id="003", text="Mai muốn giữ cả danh phận người vợ lẫn đặc quyền từ cấp trên."),
        ],
    )


def _bible():
    return StoryBible(episode_id="EP_SEM", title="Chiếc USB", protagonist={"name": "Tuấn"})


def _llm(issues):
    return lambda system, prompt: (json.dumps({"issues": issues}, ensure_ascii=False), 5, 7)


def test_review_keeps_only_quote_anchored_findings():
    review = review_script_logic(_script(), _bible(), _llm([
        {"rule": "INFEASIBLE_EVIDENCE", "segment_id": "002", "quote": "làm xét nghiệm ADN một mình", "problem": "thiếu mẫu mẹ", "fix": "x", "confidence": "high"},
        {"rule": "POV_KNOWLEDGE_VIOLATION", "segment_id": "003", "quote": "Mai muốn giữ cả danh phận", "problem": "người kể biết động cơ", "fix": "y", "confidence": "medium"},
        {"rule": "POV_KNOWLEDGE_VIOLATION", "segment_id": "003", "quote": "câu này không có trong kịch bản", "problem": "bịa", "confidence": "high"},
        {"rule": "MADE_UP_RULE", "segment_id": "001", "quote": "Tuấn tìm thấy chiếc USB", "confidence": "high"},
    ]))
    assert [i["rule"] for i in review["issues"]] == ["INFEASIBLE_EVIDENCE"]
    assert review["issues"][0]["severity"] == "CRITICAL"
    assert [i["segment_id"] for i in review["advisories"]] == ["003"]
    assert review["script_hash"] == script_content_hash(_script())


class _ReviewingProvider:
    provider_name = "fake"

    def complete_json(self, system, prompt, model=None):
        return _llm([{"rule": "INFEASIBLE_EVIDENCE", "segment_id": "002", "quote": "không cần mẫu của Mai", "problem": "p", "fix": "f", "confidence": "high"}])(system, prompt)


def test_run_qc_blocks_pass_on_confident_logic_issue(tmp_path):
    engine = ScriptQCEngine(provider=_ReviewingProvider(), cost_controller=CostController(), episodes_root=tmp_path)
    report = engine.run_qc(_script(), _bible())
    assert report.status != "PASS"
    assert report.semantic_review["status"] == "RUN"
    assert any(i["rule"] == "INFEASIBLE_EVIDENCE" for i in report.evidence_issues)


def test_carry_over_only_for_identical_text():
    script = _script()
    previous = {"semantic_review": {"status": "RUN", "script_hash": script_content_hash(script), "issues": []}}
    assert carry_over_semantic_review(previous, script) is not None
    script.segments[0].text += " Thêm."
    assert carry_over_semantic_review(previous, script) is None


class _FailingReviewProvider:
    provider_name = "fake"

    def complete_json(self, system, prompt, model=None):
        raise RuntimeError("No non-lite Gemini model is available (quota exhausted or unavailable).")


def test_unavailable_reviewer_never_yields_pass(tmp_path):
    script = FullScript(
        episode_id="EP_SEM",
        title="Sạch",
        host={"id": "MINH", "voice": "Binh"},
        segments=[ScriptSegment(id="001", text="Tuấn tìm thấy chiếc USB trên bàn của vợ.", delivery_profile="HOOK")],
    )
    engine = ScriptQCEngine(provider=_FailingReviewProvider(), cost_controller=CostController(), episodes_root=tmp_path)
    report = engine.run_qc(script, _bible())
    assert report.status != "PASS"
    assert report.semantic_review["status"] == "ERROR"
    assert any(i["rule"] == "SEMANTIC_REVIEW_FAILED" for i in report.evidence_issues)


def test_gemini_review_excludes_lite_models(monkeypatch):
    from apps.script_factory.providers import gemini_provider as gp

    provider = gp.GeminiScriptAIProvider(api_key="fake")
    blocks = {("*", m): 9e18 for m in gp.GEMINI_FLASH_CHAIN}
    monkeypatch.setattr(gp, "_QUOTA_BLOCKS", blocks)
    import pytest
    with pytest.raises(RuntimeError, match="non-lite"):
        provider._call_generate_content(prompt="x", model="gemini-2.5-flash", allow_lite_models=False)


def test_story_bible_review_blocks_only_objective_defects():
    from apps.script_factory.semantic_review import review_story_bible_logic

    bible = StoryBible(
        episode_id="EP_SB",
        title="t",
        protagonist={"name": "Tuấn"},
        reveal_2="Mai thừa nhận mối quan hệ khi Tuấn đưa ra chiếc USB.",
        ending="Tuấn nộp đơn ly hôn ngay khi vợ đang mang thai tháng thứ bảy.",
        causal_chains=[{"motivation": "Áp lực thăng tiến khiến Mai giấu chuyện."}],
    )
    findings = [
        {"rule": "POV_KNOWLEDGE_VIOLATION", "field": "causal_chains", "quote": "Áp lực thăng tiến khiến Mai giấu chuyện", "confidence": "high"},
        {"rule": "IMPLAUSIBLE_BEHAVIOR", "field": "reveal_2", "quote": "Mai thừa nhận mối quan hệ khi", "confidence": "high"},
        {"rule": "LEGAL_OR_MEDICAL_UNREALISTIC", "field": "ending", "quote": "nộp đơn ly hôn ngay khi vợ đang mang thai", "confidence": "high"},
    ]
    review = review_story_bible_logic(bible, _llm(findings))
    assert [i["rule"] for i in review["issues"]] == ["LEGAL_OR_MEDICAL_UNREALISTIC"]
    assert [i["rule"] for i in review["advisories"]] == ["IMPLAUSIBLE_BEHAVIOR"]


def test_story_bible_patch_applies_every_plot_field_but_keeps_identity():
    from apps.script_factory.models import apply_story_bible_patch

    bible = StoryBible(episode_id="EP_P", title="Gốc", protagonist={"name": "Tuấn"}, ending="cũ", original_user_topic="ngoại tình")
    apply_story_bible_patch(bible, {
        "ending": "Tuấn yêu cầu Tòa án xác định cha, mẹ, con.",
        "emotional_payoff": "mới",
        "episode_id": "HACK",
        "title": "Đổi tên",
        "original_user_topic": "khác",
        "clues": "không phải list",
        "critical_facts": [{"field": "age", "value": 32}],
    })
    assert bible.ending.startswith("Tuấn yêu cầu")
    assert bible.emotional_payoff == "mới"
    assert bible.critical_facts[0].value == "32"


def test_semantic_review_malformed_json_returns_error():
    script = FullScript(
        episode_id="EP_ERR",
        title="t",
        host={"id": "MINH", "voice": "Binh"},
        segments=[ScriptSegment(id="001", text="Tuấn nhìn thấy chiếc hộp cũ trên bàn.", delivery_profile="HOOK")],
    )
    story_bible = StoryBible(episode_id="EP_ERR", title="t", protagonist={"name": "Tuấn"})

    # 1. NOT JSON
    review = review_script_logic(script, story_bible, lambda sys, prompt: ("NOT JSON AT ALL", 10, 10))
    assert review["status"] == "ERROR"
    assert "Mô hình không trả về JSON hợp lệ" in review["error"]

    # 2. Wrong field
    review2 = review_script_logic(script, story_bible, lambda sys, prompt: ('{"wrong_field": []}', 10, 10))
    assert review2["status"] == "ERROR"
    assert "thiếu trường bắt buộc 'issues'" in review2["error"]


def test_story_bible_content_hash_changes_with_characters_and_timeline():
    bible1 = StoryBible(
        episode_id="EP_H1",
        title="t",
        protagonist={"name": "Tuấn", "age": 30},
        timeline="Năm 2020",
    )
    bible2 = StoryBible(
        episode_id="EP_H1",
        title="t",
        protagonist={"name": "Tuấn", "age": 35},  # Age changed
        timeline="Năm 2020",
    )
    bible3 = StoryBible(
        episode_id="EP_H1",
        title="t",
        protagonist={"name": "Tuấn", "age": 30},
        timeline="Năm 2025",  # Timeline changed
    )

    h1 = story_bible_content_hash(bible1)
    h2 = story_bible_content_hash(bible2)
    h3 = story_bible_content_hash(bible3)

    assert h1 != h2, "Hash must change when protagonist attributes change"
    assert h1 != h3, "Hash must change when timeline changes"

