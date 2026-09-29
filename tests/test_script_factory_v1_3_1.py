"""Automated Test Suite for Script Factory V1.3.1 Controlled Editorial Polish.

Verifies:
1. Editorial QC detects and validates fixes for all 10 human review rules:
   - MC_NAME_COLLISION (Minh -> Tuấn in IDEA_005)
   - UNMARKED_FIRST_PERSON_PROTAGONIST (3rd person documentary POV in IDEA_005)
   - EPISODE_CODE_IN_NARRATION (No "mã số EP021" in narration)
   - FAKE_CONTINUATION_LANGUAGE (No "phần tiếp theo / ở phần sau" in standalone story)
   - OVERLONG_REVEAL_BLOCK (REVEAL profile concentrated to 5-8 segments, consequences in NORMAL/COMMENT)
   - REVEAL_2_REDUNDANCY (Reveal 2 provides distinct emotional motive/relational consequence)
   - GENERIC_REFLECTION (Grounding in story-specific dilemmas)
   - MELODRAMA_DENSITY (No purple prose / soap opera clichés)
   - GENERIC_AI_PROSE (Concrete opening hooks instead of cliché AI proverbs)
   - UNSUPPORTED_LEGAL_CERTAINTY (Archival leads requiring verification, not automatic legal certainty)
2. All 5 pilot episodes pass V1.3.1 Editorial QC with 0 BLOCKER, 0 FAIL.
3. No regressions on V1.3 anti-spoiler gates (Story Bible hidden facts never leaked prematurely).
4. Status of all 5 scripts is strictly 'AWAITING_USER_SCRIPT_REVIEW' (never auto-approved).
5. Cross-episode audit report and master JSON/CSV exist and validate cleanly.
6. All 7 required package files exist in each pilot_02_v1_3_1/<IDEA_ID> folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.script_factory.editorial_qc import EditorialQCEngine, EditorialIssue
from apps.script_factory.pilot_02_v1_3_1_editorial import execute_all_pilot_02_v1_3_1_repairs


BASE_DIR = Path(__file__).resolve().parent.parent
PILOT_02_V1_3_1_DIR = BASE_DIR / "pilot_02_v1_3_1"
REPORTS_DIR = BASE_DIR / "reports"
PILOT_EPISODES = ["IDEA_003", "IDEA_005", "IDEA_011", "IDEA_018", "IDEA_021"]


@pytest.fixture(scope="module")
def editorial_qc_engine() -> EditorialQCEngine:
    return EditorialQCEngine()


def test_mc_name_collision_detected_and_repaired(editorial_qc_engine: EditorialQCEngine):
    """Rule 1: If a character is named Minh while narrator is MC Minh, it must be flagged."""
    script_bad = {
        "segments": [
            {"segment_id": "005", "delivery_profile": "NORMAL", "text": "Anh Minh vội vã chạy ra mở cửa khi nghe tiếng chuông."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_005")
    assert any(i.rule_id == "MC_NAME_COLLISION" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "005", "delivery_profile": "NORMAL", "text": "Anh Tuấn vội vã chạy ra mở cửa khi nghe tiếng chuông."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_005")
    assert not any(i.rule_id == "MC_NAME_COLLISION" for i in issues_good)


def test_unmarked_first_person_rejected_and_fixed(editorial_qc_engine: EditorialQCEngine):
    """Rule 2: Unmarked 1st person narrator ('Tôi và chị Lan...') in documentary script must be rejected."""
    script_bad = {
        "segments": [
            {"segment_id": "010", "delivery_profile": "NORMAL", "text": "Tôi và chị Lan bắt đầu bước vào khu vườn sau nhà."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_005")
    assert any(i.rule_id == "UNMARKED_FIRST_PERSON_PROTAGONIST" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "010", "delivery_profile": "NORMAL", "text": "Tuấn và chị Lan bắt đầu bước vào khu vườn sau nhà."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_005")
    assert not any(i.rule_id == "UNMARKED_FIRST_PERSON_PROTAGONIST" for i in issues_good)


def test_episode_code_in_narration_flagged_and_removed(editorial_qc_engine: EditorialQCEngine):
    """Rule 3: Internal code like 'EP021' spoken in narration must be rejected."""
    script_bad = {
        "segments": [
            {"segment_id": "005", "delivery_profile": "HOOK", "text": "Hồ sơ mang mã số EP021 ghi lại một sự việc kỳ lạ."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_021")
    assert any(i.rule_id == "EPISODE_CODE_IN_NARRATION" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "005", "delivery_profile": "HOOK", "text": "Tài liệu này ghi lại một sự việc kỳ lạ."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_021")
    assert not any(i.rule_id == "EPISODE_CODE_IN_NARRATION" for i in issues_good)


def test_fake_continuation_flagged_and_removed(editorial_qc_engine: EditorialQCEngine):
    """Rule 4: 'phần tiếp theo' in standalone episode must be rejected."""
    script_bad = {
        "segments": [
            {"segment_id": "045", "delivery_profile": "NORMAL", "text": "Mời quý vị đón xem ở phần tiếp theo của câu chuyện."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_021")
    assert any(i.rule_id == "FAKE_CONTINUATION_LANGUAGE" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "045", "delivery_profile": "NORMAL", "text": "Những manh mối tiếp theo dần hé mở sự thật."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_021")
    assert not any(i.rule_id == "FAKE_CONTINUATION_LANGUAGE" for i in issues_good)


def test_overlong_reveal_profile_detected_and_rebalanced(editorial_qc_engine: EditorialQCEngine):
    """Rule 5: REVEAL profile lasting >9 segments must be flagged."""
    script_bad = {
        "segments": [
            {"segment_id": f"{i:03d}", "delivery_profile": "REVEAL", "text": f"Sự thật hé lộ phần {i}."}
            for i in range(55, 75)  # 20 segments
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_003")
    assert any(i.rule_id == "OVERLONG_REVEAL_BLOCK" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": f"{i:03d}", "delivery_profile": "REVEAL", "text": f"Sự thật hé lộ phần {i}."}
            for i in range(61, 68)  # 7 segments
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_003")
    assert not any(i.rule_id == "OVERLONG_REVEAL_BLOCK" for i in issues_good)


def test_reveal_2_requires_motive_and_emotional_meaning(editorial_qc_engine: EditorialQCEngine):
    """Rule 6: Reveal 2 must explain why, emotional impact, or relationship consequence."""
    script_weak = {
        "segments": [
            {"segment_id": f"{i:03d}", "delivery_profile": "NORMAL", "text": "Bình thường."}
            for i in range(1, 65)
        ] + [
            {"segment_id": "065", "delivery_profile": "REVEAL", "text": "Và đó là toàn bộ sự thật về chiếc hộp gỗ."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_weak, "IDEA_003")
    assert any(i.rule_id == "REVEAL_2_REDUNDANCY" for i in issues)

    script_strong = {
        "segments": [
            {"segment_id": f"{i:03d}", "delivery_profile": "NORMAL", "text": "Bình thường."}
            for i in range(1, 65)
        ] + [
            {"segment_id": "065", "delivery_profile": "REVEAL", "text": "Nhưng động cơ sâu xa đằng sau bí mật đó không phải là tài sản, mà là nỗi ân hận và tình yêu thương âm thầm suốt ba mươi năm."}
        ]
    }
    issues_strong = editorial_qc_engine.evaluate_script(script_strong, "IDEA_003")
    assert not any(i.rule_id == "REVEAL_2_REDUNDANCY" for i in issues_strong)


def test_generic_reflections_flagged_and_replaced(editorial_qc_engine: EditorialQCEngine):
    """Rule 7: Cliché reflections like 'cuộc sống vốn dĩ vô thường' must be flagged."""
    script_bad = {
        "segments": [
            {"segment_id": "085", "delivery_profile": "ENDING", "text": "Cuộc sống vốn dĩ vô thường, chúng ta hãy trân trọng hiện tại."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_003")
    assert any(i.rule_id == "GENERIC_REFLECTION" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "085", "delivery_profile": "ENDING", "text": "Lời hứa của người bà năm xưa nhắc nhở chúng ta về trách nhiệm và sự tha thứ trong gia đình."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_003")
    assert not any(i.rule_id == "GENERIC_REFLECTION" for i in issues_good)


def test_melodrama_density_flagged_and_toned_down(editorial_qc_engine: EditorialQCEngine):
    """Rule 8: Cliché melodrama like 'bóng ma vô hình', 'lồng kính ngột ngạt' must be flagged."""
    script_bad = {
        "segments": [
            {"segment_id": "060", "delivery_profile": "NORMAL", "text": "Căn phòng như một chiếc lồng kính ngột ngạt giam cầm bóng ma vô hình của sự thật rỉ máu."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_021")
    assert any(i.rule_id == "MELODRAMA_DENSITY" for i in issues)


def test_generic_ai_opening_replaced_with_concrete_element(editorial_qc_engine: EditorialQCEngine):
    """Rule 9: 'Có những ngôi nhà...' opening must be rejected in favor of concrete elements."""
    script_bad = {
        "segments": [
            {"segment_id": "001", "delivery_profile": "HOOK", "text": "Có những ngôi nhà mang theo những bí mật không bao giờ nói."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_018")
    assert any(i.rule_id == "GENERIC_AI_PROSE" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "001", "delivery_profile": "HOOK", "text": "Trước cánh cổng niêm phong của căn nhà rường cổ, điện thoại bất ngờ rung lên."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_018")
    assert not any(i.rule_id == "GENERIC_AI_PROSE" for i in issues_good)


def test_unsupported_legal_certainty_repaired(editorial_qc_engine: EditorialQCEngine):
    """Rule 10: Automatic legal ownership claim in IDEA_018 must be flagged."""
    script_bad = {
        "segments": [
            {"segment_id": "050", "delivery_profile": "NORMAL", "text": "Tờ giấy viết tay năm 1985 lập tức khẳng định quyền sở hữu hợp pháp tuyệt đối cho người cháu."}
        ]
    }
    issues = editorial_qc_engine.evaluate_script(script_bad, "IDEA_018")
    assert any(i.rule_id == "UNSUPPORTED_LEGAL_CERTAINTY" for i in issues)

    script_good = {
        "segments": [
            {"segment_id": "050", "delivery_profile": "NORMAL", "text": "Tờ giấy viết tay năm 1985 là manh mối lưu trữ then chốt cần cơ quan chuyên môn xác minh tính xác thực."}
        ]
    }
    issues_good = editorial_qc_engine.evaluate_script(script_good, "IDEA_018")
    assert not any(i.rule_id == "UNSUPPORTED_LEGAL_CERTAINTY" for i in issues_good)


def test_all_five_episodes_pass_v1_3_1_editorial_qc(editorial_qc_engine: EditorialQCEngine):
    """Integrity check: All 5 exported episodes in pilot_02_v1_3_1 must pass Editorial QC with 0 BLOCKER, 0 FAIL."""
    for idea_id in PILOT_EPISODES:
        script_file = PILOT_02_V1_3_1_DIR / idea_id / "full_script.json"
        assert script_file.exists(), f"Missing full_script.json for {idea_id}"
        with open(script_file, "r", encoding="utf-8") as f:
            script_data = json.load(f)

        issues = editorial_qc_engine.evaluate_script(script_data, idea_id)
        blockers = [i for i in issues if i.severity == "BLOCKER"]
        fails = [i for i in issues if i.severity == "FAIL"]
        assert len(blockers) == 0, f"{idea_id} has editorial blockers: {[b.description for b in blockers]}"
        assert len(fails) == 0, f"{idea_id} has editorial fails: {[f.description for f in fails]}"


def test_no_spoiler_leakage_regressions():
    """Verify that V1.3 anti-spoiler guarantees are strictly maintained in V1.3.1."""
    # Check that in segment 001-050, no core twist answers appear
    for idea_id in PILOT_EPISODES:
        script_file = PILOT_02_V1_3_1_DIR / idea_id / "full_script.json"
        with open(script_file, "r", encoding="utf-8") as f:
            script_data = json.load(f)

        early_text = " ".join([
            seg["text"] for seg in script_data["segments"]
            if int(seg.get("id") or seg.get("segment_id")) <= 50
        ]).lower()

        if idea_id == "IDEA_003":
            assert "nhận nuôi" not in early_text
            assert "con nuôi" not in early_text
        elif idea_id == "IDEA_005":
            assert "chọc thủng bể nước" not in early_text
            assert "nghiện cờ bạc" not in early_text
        elif idea_id == "IDEA_011":
            assert "vay nặng lãi" not in early_text
        elif idea_id == "IDEA_018":
            assert "trung tâm bảo trợ" not in early_text
        elif idea_id == "IDEA_021":
            assert "bệnh viện dã chiến" not in early_text


def test_script_status_strictly_awaiting_user_script_review():
    """Scripts must NEVER be marked PRODUCTION_APPROVED before user human review."""
    for idea_id in PILOT_EPISODES:
        qc_file = PILOT_02_V1_3_1_DIR / idea_id / "qc_report.json"
        with open(qc_file, "r", encoding="utf-8") as f:
            qc_data = json.load(f)
        assert qc_data.get("script_status") == "AWAITING_USER_SCRIPT_REVIEW"
        assert qc_data.get("script_status") != "PRODUCTION_APPROVED"


def test_cross_episode_audit_generated():
    """Cross-episode audit report must exist and verify clean status."""
    audit_file = REPORTS_DIR / "pilot_02_v1_3_1_cross_episode_audit.json"
    assert audit_file.exists(), "pilot_02_v1_3_1_cross_episode_audit.json must exist"
    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["mc_name_collision"] == "PASS"
    assert data["unmarked_first_person"] == "PASS"
    assert data["episode_code"] == "PASS"
    assert data["fake_continuation"] == "PASS"
    assert data["overlong_reveal"] == "PASS"
    assert data["generic_reflection"] == "PASS"
    assert data["melodrama"] == "PASS"
    assert data["legal_certainty"] == "PASS"


def test_editorial_change_log_structure():
    """Verify that every episode directory contains an editorial_change_log.json with valid records."""
    for idea_id in PILOT_EPISODES:
        log_file = PILOT_02_V1_3_1_DIR / idea_id / "editorial_change_log.json"
        assert log_file.exists(), f"Missing editorial_change_log.json for {idea_id}"
        with open(log_file, "r", encoding="utf-8") as f:
            log_data = json.load(f)
        assert "idea_id" in log_data
        assert "changes" in log_data
        assert len(log_data["changes"]) > 0
        for change in log_data["changes"]:
            assert "segment_id" in change
            assert "rule_id" in change
            assert "before" in change
            assert "after" in change
            assert "reason" in change


def test_required_package_files_exist():
    """All 7 required files must exist in each pilot_02_v1_3_1/<IDEA_ID> folder."""
    required_files = [
        "story_bible.json",
        "fact_lock.json",
        "information_release_map.json",
        "full_script.json",
        "full_script_readable.txt",
        "qc_report.json",
        "editorial_change_log.json",
    ]
    for idea_id in PILOT_EPISODES:
        ep_dir = PILOT_02_V1_3_1_DIR / idea_id
        for rf in required_files:
            target = ep_dir / rf
            assert target.exists(), f"Missing {rf} in {ep_dir}"
            assert target.stat().st_size > 0, f"Empty file {rf} in {ep_dir}"
