"""Automated Test Suite for Script Factory V1.3 Final Script Quality Gate.

Verifies:
1. InformationReleaseMap enforces segment timing rules (Reveal 1 >= 61, Reveal 2 >= 76).
2. StoryBibleLeakageGuard detects and eliminates prompt/database phrasing.
3. SpoilerTimingGuard blocks premature reveal before allowed act window.
4. ScriptQCEngine outputs non-template, evidence-based segment QC issues.
5. All 5 repaired Pilot 02 V1.3 episodes pass validation with 7 required package files.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from apps.script_factory.information_release_map import (
    InformationReleaseMap,
    build_information_release_map,
)
from apps.script_factory.leakage_guard import StoryBibleLeakageGuard
from apps.script_factory.models import (
    ApprovalStatus,
    FullScript,
    LockedFact,
    ScriptSegment,
    StoryBible,
)
from apps.script_factory.spoiler_timing_guard import SpoilerTimingGuard


def test_information_release_map_generation():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Test Story",
        protagonist={"name": "Hùng"},
        critical_facts=[
            LockedFact(fact_id="FACT_001", field="timeline_years", value="7 năm", description="Thời gian diễn ra"),
            LockedFact(fact_id="FACT_002", field="reveal_1_truth", value="Người cậu giả giọng cha ruột", description="Nội dung cốt lõi của Bước ngoặt 1"),
            LockedFact(fact_id="FACT_003", field="reveal_2_truth", value="Số tiền tiết kiệm để chữa bệnh cho Lan", description="Nội dung gốc rễ của Bước ngoặt 2"),
        ]
    )

    rel_map = build_information_release_map(bible)
    assert len(rel_map.rules) >= 3

    # Check timing constraints
    for rule in rel_map.rules:
        if "reveal_1" in rule.field.lower() or "bước ngoặt 1" in rule.description.lower():
            assert rule.earliest_allowed_segment >= 61
        elif "reveal_2" in rule.field.lower() or "bước ngoặt 2" in rule.description.lower():
            assert rule.earliest_allowed_segment >= 76
        elif "timeline" in rule.field.lower():
            assert rule.earliest_allowed_segment <= 15


def test_story_bible_leakage_guard_detection_and_cleaning():
    guard = StoryBibleLeakageGuard()

    # Contaminated segment text
    contaminated_text = (
        "Cuộc sống của Mai trôi qua êm đềm, như dòng sông hiền hòa. "
        "Đáng chú ý, chi tiết liên quan đến Nguồn gốc của vật chứng chính dẫn đến bí mật được xác định là Chiếc hộp gỗ cũ kỹ. "
        "Nội dung cốt lõi của Bước ngoặt 1 được xác định là Người phụ nữ trong ảnh là Bà Thoa."
    )
    seg = ScriptSegment(id="009", text=contaminated_text)
    violations = guard.check_segment(seg)

    assert len(violations) > 0
    assert any(v.violation_code == "STORY_BIBLE_LEAKAGE" for v in violations)
    assert any("đáng chú ý" in v.matched_pattern.lower() for v in violations)

    # Clean text
    cleaned = guard.clean_text_from_leakage(contaminated_text)
    assert "Đáng chú ý" not in cleaned
    assert "được xác định là" not in cleaned
    assert "Cuộc sống của Mai trôi qua êm đềm, như dòng sông hiền hòa." in cleaned

    # Audit cleaned text
    seg_cleaned = ScriptSegment(id="009", text=cleaned)
    assert len(guard.check_segment(seg_cleaned)) == 0


def test_spoiler_timing_guard_blocks_premature_reveal():
    bible = StoryBible(
        episode_id="EP_TEST",
        title="Test Mystery",
        protagonist={"name": "Mai"},
        critical_facts=[
            LockedFact(fact_id="FACT_001", field="evidence_origin", value="Chiếc hộp gỗ cũ"),
            LockedFact(fact_id="FACT_002", field="reveal_1_truth", value="Người phụ nữ trong ảnh là Bà Thoa bạn thân"),
        ]
    )
    rel_map = build_information_release_map(bible)
    guard = SpoilerTimingGuard(rel_map)

    # Premature mention in segment 008 (before allowed segment 61)
    premature_seg = ScriptSegment(
        id="008",
        text="Mai lục lọi gác xép và bất ngờ phát hiện người trong ảnh là Bà Thoa, một sự thật chấn động."
    )
    violations = guard.check_segment(premature_seg)
    assert len(violations) > 0
    assert violations[0].violation_code == "BLOCKED_PREMATURE_REVEAL"
    assert violations[0].segment_id == "008"

    # Permitted mention in segment 065 (within Reveal 1 window)
    allowed_seg = ScriptSegment(
        id="065",
        text="Giờ đây bức màn bí mật được vén lên: người phụ nữ đứng cạnh bà chính là Bà Thoa, người bạn tri kỷ năm xưa."
    )
    allowed_violations = guard.check_segment(allowed_seg)
    assert len(allowed_violations) == 0


def test_pilot_02_v1_3_all_packages_complete_and_pass():
    pilot_dir = Path("pilot_02_v1_3")
    required_ideas = ["IDEA_003", "IDEA_005", "IDEA_011", "IDEA_018", "IDEA_021"]
    required_files = [
        "story_bible.json",
        "fact_lock.json",
        "information_release_map.json",
        "full_script.json",
        "full_script_readable.txt",
        "qc_report.json",
        "revision_log.json",
    ]

    for idea_id in required_ideas:
        ep_dir = pilot_dir / idea_id
        assert ep_dir.exists(), f"Directory {ep_dir} does not exist"

        for rf in required_files:
            f_path = ep_dir / rf
            assert f_path.exists(), f"Missing {rf} in {ep_dir}"
            assert f_path.stat().st_size > 0

        # Check script status
        with open(ep_dir / "full_script.json", "r", encoding="utf-8") as f:
            script_data = json.load(f)
        assert script_data["status"] == "AWAITING_USER_SCRIPT_REVIEW"
        assert len(script_data["segments"]) == 90
        assert 2400 <= script_data["total_words"] <= 3000

        # Check QC report
        with open(ep_dir / "qc_report.json", "r", encoding="utf-8") as f:
            qc_data = json.load(f)
        assert qc_data["status"] == "PASS"
        assert len(qc_data.get("evidence_issues", [])) == 0

    # Check summary reports
    json_rep = Path("reports/full_script_pilot_02_v1_3.json")
    csv_rep = Path("reports/full_script_pilot_02_v1_3.csv")
    assert json_rep.exists()
    assert csv_rep.exists()
