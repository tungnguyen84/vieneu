from __future__ import annotations

import json
from pathlib import Path

from apps.script_factory.models import FullScript, QCReport, ScriptSegment, StoryBible
from apps.script_factory.narrative_continuity import find_repeated_narrative_block
from apps.script_factory.script_qc import apply_targeted_repairs
from apps.script_factory.story_qc import StoryQCEngine
from studio.backend.services import generation_service as generation_module


def _segment(index: int, text: str, profile: str = "NORMAL") -> ScriptSegment:
    return ScriptSegment(id=f"{index:03d}", speaker="MINH", text=text, delivery_profile=profile)


def test_detects_and_removes_distant_restarted_investigation() -> None:
    first = [
        "Hoàng gọi cho Thảo để hỏi về chuyến công tác cuối tuần và lịch làm việc tại công ty.",
        "Thảo kiểm tra hồ sơ rồi xác nhận hôm đó không có dự án khẩn hay cuộc họp nào vào buổi tối.",
        "Cô cho biết người đi cùng Lan là cấp trên trực tiếp, thường gặp riêng sau giờ làm việc.",
        "Hoàng ngồi im bên bàn, chờ Lan về để hỏi thẳng về những lần vắng nhà không rõ lý do.",
    ]
    repeated = [
        "Hoàng gọi lại cho Thảo, hỏi về chuyến công tác cuối tuần cùng lịch làm việc ở công ty.",
        "Sau khi xem hồ sơ, Thảo nói hôm ấy không hề có dự án khẩn hoặc cuộc họp buổi tối.",
        "Người thường đi riêng với Lan sau giờ làm chính là cấp trên trực tiếp của cô ở công ty.",
        "Hoàng ngồi chờ bên bàn cho đến khi Lan về nhà để hỏi về các lần cô vắng mặt không rõ lý do.",
    ]
    segments = [_segment(1, "Lá thư mở đầu bằng một dấu hiệu bất thường trong gia đình.", "HOOK")]
    segments += [_segment(i + 2, text) for i, text in enumerate(first)]
    segments += [_segment(i + 6, f"Chi tiết riêng biệt số {i} dẫn câu chuyện tiến thêm một bước mới.") for i in range(8)]
    segments += [_segment(i + 14, text) for i, text in enumerate(repeated)]
    segments += [_segment(18, "Lan đưa ra tài liệu gốc và giải thích sự việc trước mọi người.", "REVEAL")]
    segments += [_segment(19, "Gia đình trao đổi bình tĩnh về hậu quả và trách nhiệm của từng người.")]
    segments += [_segment(20, "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING")]

    match = find_repeated_narrative_block(segments)
    assert match is not None

    bible = StoryBible(episode_id="EP_REPEAT", title="Vòng kể lại", protagonist={"name": "Hoàng"})
    script = FullScript(episode_id=bible.episode_id, title=bible.title, host={"id": "MINH"}, segments=segments)
    report = QCReport(
        episode_id=bible.episode_id,
        status="FAIL",
        evidence_issues=[{"rule": "REPEATED_NARRATIVE_BLOCK", "severity": "CRITICAL"}],
    )
    repaired = apply_targeted_repairs(script, bible, report)

    assert find_repeated_narrative_block(repaired.segments) is None
    assert any(segment.delivery_profile == "REVEAL" for segment in repaired.segments)
    assert [segment.id for segment in repaired.segments] == [
        f"{index:03d}" for index in range(1, len(repaired.segments) + 1)
    ]


def test_story_qc_reserves_minh_for_host_and_repairs_all_references() -> None:
    bible = StoryBible(
        episode_id="EP_HOST_NAME",
        title="Tên trùng MC",
        protagonist={"name": "Lan", "char_id": "LAN"},
        supporting_characters=[{"name": "Minh", "char_id": "MINH", "role": "Trưởng phòng"}],
        secret="Lan phát hiện Minh đã che giấu một cuộc gặp.",
        reveal_1="Minh thừa nhận đã có mặt.",
    )
    engine = StoryQCEngine()
    report = engine.audit_story_bible(bible)
    assert "HOST_CHARACTER_NAME_COLLISION" in report.rule_codes

    repaired = engine.repair_story_bible(bible, report)
    serialized = str(repaired.to_dict())
    assert repaired.supporting_characters[0]["name"] != "Minh"
    assert repaired.supporting_characters[0]["char_id"] != "MINH"
    assert "'Minh'" not in serialized


def test_story_qc_rejects_indirect_evidence_as_conclusive_proof() -> None:
    bible = StoryBible(
        episode_id="EP_PROOF",
        title="Dấu hiệu chưa phải kết luận",
        protagonist={"name": "Hoàng", "char_id": "HOANG"},
        secret="Lan ngoại tình với đồng nghiệp.",
        reveal_1="Mối quan hệ ngoại tình bị phát hiện.",
        reveal_2="Lan thừa nhận đã phản bội chồng.",
        reveal_justifications={
            "reveal_1": {
                "evidence_support": "Tin nhắn, lịch sử cuộc gọi và lời đồn cho thấy mọi chuyện không thể chối cãi.",
                "motivation_support": "Lan muốn che giấu lựa chọn của mình.",
                "timeline_support": "Các dấu hiệu xuất hiện trong cùng ba tháng.",
            },
            "reveal_2": {
                "evidence_support": "Lời thú nhận của Lan là căn cứ duy nhất.",
                "motivation_support": "Lan nhận trách nhiệm về lựa chọn của mình.",
                "character_knowledge_support": "Hoàng biết sau cuộc đối thoại.",
            },
        },
    )
    report = StoryQCEngine().audit_story_bible(bible)
    proof_issues = [issue for issue in report.issues if issue["rule"] == "REVEAL_PROOF_OVERCLAIM"]
    assert len(proof_issues) == 2


def _run_auto_repair_service(tmp_path: Path, monkeypatch, pass_on_round: int, starting_round: int = 0) -> dict:
    project = tmp_path / "EP_AUTO"
    (project / "script").mkdir(parents=True)
    (project / "story").mkdir(parents=True)
    script = FullScript(
        episode_id="EP_AUTO",
        title="Tự sửa một lần bấm",
        host={"id": "MINH"},
        segments=[_segment(1, "Một chi tiết cần được sửa lại.", "HOOK")],
        revision_round=starting_round,
    )
    bible = StoryBible(episode_id="EP_AUTO", title=script.title, protagonist={"name": "Lan"})
    (project / "script" / "full_script.json").write_text(
        json.dumps(script.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    (project / "story" / "story_bible.json").write_text(
        json.dumps(bible.to_dict(), ensure_ascii=False), encoding="utf-8"
    )

    class FakeQC:
        def __init__(self, **_kwargs):
            pass

        def run_qc(self, script, story_bible, **_kwargs):
            status = "PASS" if script.revision_round >= pass_on_round else "FAIL"
            return QCReport(
                episode_id=story_bible.episode_id,
                status=status,
                evidence_issues=[] if status == "PASS" else [{"rule": "TEST_REMAINING"}],
            )

    class FakeRevisionManager:
        def __init__(self, **_kwargs):
            pass

        def auto_revise_and_recheck(self, script, story_bible, qc_report, max_rounds=3):
            script.revision_round += 1
            return script, FakeQC().run_qc(script, story_bible)

    monkeypatch.setattr(generation_module, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(generation_module, "ScriptQCEngine", FakeQC)
    monkeypatch.setattr(generation_module, "AutoRevisionManager", FakeRevisionManager)
    service = object.__new__(generation_module.GenerationService)
    service.cost_ctrl = object()
    service.get_provider = lambda: object()
    return service.auto_repair_script("EP_AUTO")


def test_auto_repair_one_click_runs_until_qc_pass(tmp_path: Path, monkeypatch) -> None:
    result = _run_auto_repair_service(tmp_path, monkeypatch, pass_on_round=2)
    assert result["completed"] is True
    assert result["rounds_attempted"] == 2
    assert result["qc_status"] == "PASS"


def test_auto_repair_one_click_stops_at_three_rounds_with_reason(tmp_path: Path, monkeypatch) -> None:
    result = _run_auto_repair_service(tmp_path, monkeypatch, pass_on_round=99)
    assert result["completed"] is False
    assert result["rounds_attempted"] == 3
    assert result["remaining_rules"] == ["TEST_REMAINING"]


def test_auto_repair_click_after_round_limit_gets_fresh_rounds(tmp_path: Path, monkeypatch) -> None:
    result = _run_auto_repair_service(tmp_path, monkeypatch, pass_on_round=5, starting_round=3)
    assert result["completed"] is True
    assert result["rounds_attempted"] == 2
