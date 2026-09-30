"""Regression tests for Script QC Hardening (Task B) and Audio Schema Normalization (Task A)."""
from __future__ import annotations

from pathlib import Path
import pytest

from apps.script_factory.auto_revision import AutoRevisionManager
from apps.script_factory.cost_control import CostController
from apps.script_factory.models import FullScript, LockedFact, ScriptSegment, StoryBible
from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from apps.script_factory.script_qc import ScriptQCEngine
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
    assert report.status == "NEEDS_REVISION"
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
    assert report.status == "NEEDS_REVISION"
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
    assert initial_report.status == "NEEDS_REVISION"

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
