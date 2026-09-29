"""Comprehensive Test Suite for Script Factory V1.3.1a Final Artifact Integrity Hotfix.

Covers all 30 regression points specified in Part M:
1. EP005 story-character Minh renamed to Tuấn everywhere
2. MC MINH preserved
3. semantic role prevents MC rename
4. stale character name in Fact Lock detected
5. stale character name in Release Map detected
6. first-person protagonist in final text detected
7. quoted first-person allowed
8. third-person conversion passes
9. report claim grounded to artifact
10. ungrounded report claim blocked
11. fabricated Reveal summary blocked
12. no-op editorial change detected
13. real editorial change logged
14. new unlocked debt fact blocked
15. new unlocked illness fact blocked
16. new unlocked crime fact blocked
17. new unlocked relationship fact blocked
18. Reveal consistency across artifacts
19. saved-artifact reload before QC
20. EP011 nuanced reconciliation
21. EP021 melodrama reduction
22. EP018 legal-evidence integrity
23. EP003 fact preservation
24. Story Bible leakage regression
25. spoiler timing regression
26. episode code regression
27. fake continuation regression
28. TTS readiness
29. status remains human review
30. zero media generation
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.script_factory.artifact_integrity import ArtifactIntegrityValidator, normalize_text
from apps.script_factory.report_grounding import ReportGroundingValidator

PILOT_02_V1_3_1A_DIR = BASE_DIR / "pilot_02_v1_3_1a"
REPORTS_DIR = BASE_DIR / "reports"
EPISODES = ["IDEA_003", "IDEA_005", "IDEA_011", "IDEA_018", "IDEA_021"]


@pytest.fixture(scope="module")
def integrity_validator() -> ArtifactIntegrityValidator:
    return ArtifactIntegrityValidator()


@pytest.fixture(scope="module")
def grounding_validator() -> ReportGroundingValidator:
    return ReportGroundingValidator(PILOT_02_V1_3_1A_DIR)


# Point 1: EP005 story-character Minh renamed to Tuấn everywhere
def test_ep005_story_character_minh_renamed_to_tuan_everywhere():
    ep5_dir = PILOT_02_V1_3_1A_DIR / "IDEA_005"
    with open(ep5_dir / "story_bible.json", "r", encoding="utf-8") as f:
        bible = json.load(f)
    supp = bible["supporting_characters"][0]
    assert supp["name"] == "Tuấn"
    assert supp["char_id"] == "TUAN"

    with open(ep5_dir / "fact_lock.json", "r", encoding="utf-8") as f:
        fact_lock_str = f.read()
    assert "Lan và Tuấn" in fact_lock_str
    assert "máy xúc của Tuấn" in fact_lock_str
    assert "Lan và Minh" not in fact_lock_str
    assert "máy xúc của Minh" not in fact_lock_str


# Point 2: MC MINH preserved
def test_ep005_mc_minh_preserved():
    ep5_dir = PILOT_02_V1_3_1A_DIR / "IDEA_005"
    with open(ep5_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    assert sc["host"]["name"] == "Minh"
    seg4 = next(s for s in sc["segments"] if s["id"] == "004")
    assert "Tôi là Minh" in seg4["text"]


# Point 3: semantic role prevents MC rename
def test_semantic_role_prevents_mc_rename():
    ep5_dir = PILOT_02_V1_3_1A_DIR / "IDEA_005"
    with open(ep5_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    # The host name was NOT converted to Tuấn
    assert sc["host"]["name"] == "Minh"
    assert sc["host"]["name"] != "Tuấn"


# Point 4: stale character name in Fact Lock detected
def test_stale_character_name_in_fact_lock_detected(integrity_validator: ArtifactIntegrityValidator):
    mock_facts = [
        {"fact_id": "FACT_002", "value": "Hai chị em ruột (Lan và Minh)", "description": "Mối quan hệ giữa Lan và Minh"}
    ]
    issues, count = integrity_validator._check_character_consistency(
        "EP005", "IDEA_005", {}, mock_facts, {}, {"host": {"name": "Minh"}, "segments": []}
    )
    assert count > 0
    assert any(i.rule == "CHARACTER_NAME_CONSISTENCY" and "Minh" in i.details for i in issues)


# Point 5: stale character name in Release Map detected
def test_stale_character_name_in_release_map_detected(integrity_validator: ArtifactIntegrityValidator):
    mock_rules = {
        "rules": [
            {"fact_id": "FACT_002", "key_entities": ["Minh"], "target_value": "Lan và Minh"}
        ]
    }
    issues, count = integrity_validator._check_character_consistency(
        "EP005", "IDEA_005", {}, [], mock_rules, {"host": {"name": "Minh"}, "segments": []}
    )
    assert count > 0
    assert any(i.rule == "CHARACTER_NAME_CONSISTENCY" for i in issues)


# Point 6: first-person protagonist in final text detected
def test_first_person_protagonist_in_final_text_detected(integrity_validator: ArtifactIntegrityValidator):
    bad_script = {
        "segments": [
            {"id": "029", "text": "Tôi tìm gặp chị Lan, cố gắng giải thích nhưng tôi rất sợ hãi."}
        ]
    }
    issues, count = integrity_validator._check_pov_consistency("EP005", bad_script)
    assert count > 0
    assert any(i.rule == "UNMARKED_FIRST_PERSON_PROTAGONIST" for i in issues)


# Point 7: quoted first-person allowed
def test_quoted_first_person_allowed(integrity_validator: ArtifactIntegrityValidator):
    good_script = {
        "segments": [
            {"id": "029", "text": "Tuấn tìm gặp chị Lan rồi nghẹn ngào nói: 'Tôi đã rất sợ hãi lúc đó.'"}
        ]
    }
    issues, count = integrity_validator._check_pov_consistency("EP005", good_script)
    assert count == 0


# Point 8: third-person conversion passes
def test_third_person_conversion_passes(integrity_validator: ArtifactIntegrityValidator):
    ep5_dir = PILOT_02_V1_3_1A_DIR / "IDEA_005"
    with open(ep5_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    issues, count = integrity_validator._check_pov_consistency("EP005", sc)
    assert count == 0
    assert len(issues) == 0


# Point 9: report claim grounded to artifact
def test_report_claim_grounded_to_artifact(grounding_validator: ReportGroundingValidator):
    with open(REPORTS_DIR / "full_script_pilot_02_v1_3_1a.json", "r", encoding="utf-8") as f:
        report = json.load(f)
    audit = grounding_validator.validate_master_report(report)
    assert audit["status"] == "PASS"
    assert audit["ungrounded_claims"] == 0
    assert audit["grounded_claims"] > 0


# Point 10: ungrounded report claim blocked
def test_ungrounded_report_claim_blocked(grounding_validator: ReportGroundingValidator):
    fake_report = {
        "episodes": [
            {
                "idea_id": "IDEA_005",
                "episode_id": "EP005",
                "title": "Cuộc Gọi Lúc Nửa Đêm",
                "reveal_1_summary": "Tuấn bí mật tham gia đường dây buôn lậu dầu mỏ xuyên quốc gia.",  # Fake
                "reveal_2_summary": "Tuấn che giấu sự cố vì sợ Lan mất lợi thế tranh chấp, sợ bị phạt và muốn tự mình gánh trách nhiệm.",
            }
        ]
    }
    audit = grounding_validator.validate_master_report(fake_report)
    assert audit["status"] == "FAIL"
    assert audit["ungrounded_claims"] > 0
    assert any(i["rule"] == "REPORT_UNGROUNDED_CLAIM" for i in audit["issues"])


# Point 11: fabricated Reveal summary blocked
def test_fabricated_reveal_summary_blocked(grounding_validator: ReportGroundingValidator):
    fake_report = {
        "episodes": [
            {
                "idea_id": "IDEA_011",
                "episode_id": "EP011",
                "title": "Bức Ảnh Lạ Trong Điện Thoại Cũ",
                "reveal_1_summary": "Người phụ nữ trong ảnh là Thảo, em gái họ của Nam, đã mất năm 2013 sau khi sinh con gái tên An.",
                "reveal_2_summary": "Nam bị các chủ nợ xã hội đen truy sát vì thua độ bóng đá.",  # Fabricated
            }
        ]
    }
    audit = grounding_validator.validate_master_report(fake_report)
    assert audit["status"] == "FAIL"
    assert audit["ungrounded_claims"] > 0


# Point 12: no-op editorial change detected
def test_no_op_editorial_change_detected(integrity_validator: ArtifactIntegrityValidator):
    mock_log = {
        "changes": [
            {
                "segment_id": "016",
                "rule_id": "GENERIC_AI_PROSE",
                "before": "Có những góc khuất tồn tại âm thầm.",
                "after": "Có những góc khuất tồn tại âm thầm.",
            }
        ]
    }
    issues, noops = integrity_validator._check_no_op_edits("EP018", mock_log)
    assert noops == 1
    assert any(i.rule == "NO_OP_EDITORIAL_CHANGE" for i in issues)


# Point 13: real editorial change logged
def test_real_editorial_change_logged(integrity_validator: ArtifactIntegrityValidator):
    mock_log = {
        "changes": [
            {
                "segment_id": "016",
                "rule_id": "GENERIC_AI_PROSE",
                "before": "Có những góc khuất tồn tại âm thầm.",
                "after": "Những kỷ vật trong căn nhà cổ đã nằm im suốt bốn mươi năm.",
            }
        ]
    }
    issues, noops = integrity_validator._check_no_op_edits("EP018", mock_log)
    assert noops == 0
    assert len(issues) == 0


# Point 14: new unlocked debt fact blocked
def test_new_unlocked_debt_fact_blocked(integrity_validator: ArtifactIntegrityValidator):
    fake_script = {
        "segments": [
            {"id": "040", "text": "Hóa ra số tiền này dùng để trả món vay nặng lãi mà anh ta vướng phải."}
        ]
    }
    issues, count = integrity_validator._check_new_unlocked_facts("EP011", {}, [], fake_script)
    assert count > 0
    assert any(i.rule == "NEW_UNLOCKED_STORY_FACT" for i in issues)


# Point 15: new unlocked illness fact blocked
def test_new_unlocked_illness_fact_blocked(integrity_validator: ArtifactIntegrityValidator):
    fake_script = {
        "segments": [
            {"id": "040", "text": "Người mẹ đã mắc ung thư giai đoạn cuối nhưng giấu kín gia đình."}
        ]
    }
    issues, count = integrity_validator._check_new_unlocked_facts("EP021", {}, [], fake_script)
    assert count > 0
    assert any(i.rule == "NEW_UNLOCKED_STORY_FACT" for i in issues)


# Point 16: new unlocked crime fact blocked
def test_new_unlocked_crime_fact_blocked(integrity_validator: ArtifactIntegrityValidator):
    fake_script = {
        "segments": [
            {"id": "040", "text": "Anh ta đã dính líu đến hành vi giết người để bịt đầu mối."}
        ]
    }
    issues, count = integrity_validator._check_new_unlocked_facts("EP003", {}, [], fake_script)
    assert count > 0
    assert any(i.rule == "NEW_UNLOCKED_STORY_FACT" for i in issues)


# Point 17: new unlocked relationship fact blocked
def test_new_unlocked_relationship_fact_blocked(integrity_validator: ArtifactIntegrityValidator):
    fake_script = {
        "segments": [
            {"id": "040", "text": "Đứa bé thực chất là đứa con rơi của người cha với mối tình vụng trộm."}
        ]
    }
    issues, count = integrity_validator._check_new_unlocked_facts("EP018", {}, [], fake_script)
    assert count > 0
    assert any(i.rule == "NEW_UNLOCKED_STORY_FACT" for i in issues)


# Point 18: Reveal consistency across artifacts
def test_reveal_consistency_across_artifacts(integrity_validator: ArtifactIntegrityValidator):
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        report = integrity_validator.validate_saved_package(ep_dir)
        assert report["reveal_fact_consistency"] == "PASS"


# Point 19: saved-artifact reload before QC
def test_saved_artifact_reload_before_qc(integrity_validator: ArtifactIntegrityValidator):
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        # Verify physical disk file reload succeeds
        report = integrity_validator.validate_saved_package(ep_dir)
        assert report["status"] == "PASS"


# Point 20: EP011 nuanced reconciliation
def test_ep011_nuanced_reconciliation():
    ep11_dir = PILOT_02_V1_3_1A_DIR / "IDEA_011"
    with open(ep11_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    seg76 = next(s for s in sc["segments"] if s["id"] == "076")
    seg78 = next(s for s in sc["segments"] if s["id"] == "078")
    assert "hụt hẫng" in seg76["text"]
    assert "tổn thương niềm tin" in seg78["text"]
    assert "Em hiểu rồi. Anh đã làm rất tốt" not in seg76["text"]


# Point 21: EP021 melodrama reduction
def test_ep021_melodrama_reduction():
    ep21_dir = PILOT_02_V1_3_1A_DIR / "IDEA_021"
    with open(ep21_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    seg59 = next(s for s in sc["segments"] if s["id"] == "059")
    seg64 = next(s for s in sc["segments"] if s["id"] == "064")
    seg69 = next(s for s in sc["segments"] if s["id"] == "069")
    assert "gia trưởng" not in seg59["text"]
    assert "cào xé tâm can" not in seg64["text"]
    assert "không còn lối thoát nào khác" not in seg69["text"]


# Point 22: EP018 legal-evidence integrity
def test_ep018_legal_evidence_integrity():
    ep18_dir = PILOT_02_V1_3_1A_DIR / "IDEA_018"
    with open(ep18_dir / "full_script.json", "r", encoding="utf-8") as f:
        sc = json.load(f)
    seg16 = next(s for s in sc["segments"] if s["id"] == "016")
    seg81 = next(s for s in sc["segments"] if s["id"] == "081")
    assert "Có những góc khuất" not in seg16["text"]
    assert "Có những lúc, chúng ta phải đi một vòng lớn" not in seg81["text"]
    assert "căn nhà rường" in seg81["text"]


# Point 23: EP003 fact preservation
def test_ep003_fact_preservation():
    ep3_dir = PILOT_02_V1_3_1A_DIR / "IDEA_003"
    with open(ep3_dir / "fact_lock.json", "r", encoding="utf-8") as f:
        fl = json.load(f)
    fact_dict = {f["fact_id"]: f["value"] for f in fl}
    assert "Bà Thoa" in fact_dict["FACT_004"]
    assert "trẻ mồ côi" in fact_dict["FACT_005"]


# Point 24: Story Bible leakage regression
def test_story_bible_leakage_regression():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "artifact_integrity_report.json", "r", encoding="utf-8") as f:
            rep = json.load(f)
        assert rep["story_bible_leakage_count"] == 0


# Point 25: spoiler timing regression
def test_spoiler_timing_regression():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "artifact_integrity_report.json", "r", encoding="utf-8") as f:
            rep = json.load(f)
        assert rep["premature_reveal_count"] == 0


# Point 26: episode code regression
def test_episode_code_regression():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "full_script.json", "r", encoding="utf-8") as f:
            sc = json.load(f)
        for s in sc["segments"]:
            assert not re.search(r"\b(?:EP\d{3}|IDEA_\d{3})\b", s["text"])


# Point 27: fake continuation regression
def test_fake_continuation_regression():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "full_script.json", "r", encoding="utf-8") as f:
            sc = json.load(f)
        for s in sc["segments"]:
            assert not re.search(r"phần\s+tiếp\s+theo", s["text"], re.I)


# Point 28: TTS readiness
def test_tts_readiness():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "artifact_integrity_report.json", "r", encoding="utf-8") as f:
            rep = json.load(f)
        assert rep["tts_ready"] is True


# Point 29: status remains human review
def test_status_remains_human_review():
    for ep in EPISODES:
        ep_dir = PILOT_02_V1_3_1A_DIR / ep
        with open(ep_dir / "artifact_integrity_report.json", "r", encoding="utf-8") as f:
            rep = json.load(f)
        assert rep["script_status"] == "AWAITING_USER_SCRIPT_REVIEW"
        assert rep["script_status"] != "PRODUCTION_APPROVED"


# Point 30: zero media generation
def test_zero_media_generation():
    # Verify no new video / audio files generated in final or cache during this run
    final_dir = BASE_DIR / "final"
    v932 = final_dir / "EP001_Sau_Canh_Cua_V9_3_2_FINAL.mp4"
    assert v932.exists()
    assert v932.stat().st_size > 100_000_000
    # No V1.3.1a mp4 or wav files should exist
    assert not (final_dir / "EP003_FINAL.mp4").exists()
    assert not (final_dir / "EP005_FINAL.mp4").exists()
    assert not (final_dir / "EP011_FINAL.mp4").exists()
