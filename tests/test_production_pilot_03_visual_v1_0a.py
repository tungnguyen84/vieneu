"""Automated test suite for Production Pilot 03 Visual Planning V1.0a.

Verifies:
1. Real audio timing used as master clock (tolerance <= 0.10s)
2. 100% narration timeline coverage (no gaps, no overlaps, all 90 segments mapped)
3. Content-driven Video Value Scoring (>=7 video, <7 image-only, ratio <= 40%)
4. Strict Fact Grounding (0 UNLOCKED_VISUAL_FACT, 0 UNGROUNDED_OVERLAY_FACT)
5. Overlay Cleanliness (0 forbidden metadata labels, minimal documentary design)
6. Visual spoiler guard (no leaks before Reveal 1 and Reveal 2; dry narration dominance)
7. Character reference approval & cross-generational identity family declarations
8. Prop continuity & prop reference approval flags
9. Prompt QC (Vietnamese ethnic anchor, cinematic terminology, structured video prompts)
10. Google Flow package integrity (9 files per episode)
11. ZERO media generation (0 images, 0 videos, status NOT_GENERATED)
12. Master reports and overall status AWAITING_USER_VISUAL_PLAN_REVIEW
"""
import csv
import json
from pathlib import Path
import pytest
import soundfile as sf

BASE_DIR = Path(__file__).resolve().parent.parent
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"
PILOT_03_VISUAL_V1_0A = BASE_DIR / "production_pilot_03_visual_v1_0a"
REPORTS_DIR = BASE_DIR / "reports"


@pytest.mark.parametrize("ep_id,expected_scenes,expected_video,expected_overlays", [
    ("EP003", 45, 7, 5),
    ("EP011", 45, 8, 6),
])
def test_timeline_and_audio_duration_sync(ep_id, expected_scenes, expected_video, expected_overlays):
    """Criteria 1 & 2: Real audio duration as master clock, 0 gaps, 0 overlaps, 90 segments."""
    wav_path = PILOT_03_AUDIO / ep_id / "audio" / "final_mix.wav"
    assert wav_path.exists(), f"Audio master missing: {wav_path}"
    real_duration = sf.info(str(wav_path)).duration

    plan_path = PILOT_03_VISUAL_V1_0A / ep_id / "visual_plan.json"
    assert plan_path.exists(), f"Visual plan missing: {plan_path}"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan["scenes"]
    assert len(scenes) == expected_scenes

    # Scene 1 start must be 0.0s
    assert scenes[0]["start_time"] == 0.0

    # Final scene end must match audio duration within 0.10s
    last_end = scenes[-1]["end_time"]
    diff = abs(last_end - real_duration)
    assert diff <= 0.10, f"Timeline discrepancy: {diff}s > 0.10s"

    # Continuous non-overlapping check
    for i in range(len(scenes) - 1):
        assert round(scenes[i]["end_time"], 3) == round(scenes[i + 1]["start_time"], 3), (
            f"Gap or overlap at scene {scenes[i]['scene_id']} -> {scenes[i+1]['scene_id']}"
        )

    # 100% segment coverage check (all 90 segments mapped)
    all_mapped_segments = []
    for sc in scenes:
        all_mapped_segments.extend(sc["source_segments"])
    expected_segments = [f"{i:03d}" for i in range(1, 91)]
    assert sorted(all_mapped_segments) == expected_segments, "Not all 90 segments mapped continuously!"


@pytest.mark.parametrize("ep_id,expected_video_count,expected_downgraded_count", [
    ("EP003", 7, 8),
    ("EP011", 8, 7),
])
def test_video_value_scoring_and_budget(ep_id, expected_video_count, expected_downgraded_count):
    """Criteria 3: Content-driven Video Value Scoring & budget hard cap <= 40%."""
    plan_path = PILOT_03_VISUAL_V1_0A / ep_id / "visual_plan.json"
    audit_path = PILOT_03_VISUAL_V1_0A / ep_id / "video_value_audit.json"
    assert audit_path.exists(), f"Video value audit file missing: {audit_path}"

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    with open(audit_path, "r", encoding="utf-8") as f:
        audit = json.load(f)

    video_count = plan["video_recommended_count"]
    ratio_pct = plan["video_ratio_pct"]

    assert video_count == expected_video_count
    assert ratio_pct <= 40.0
    assert audit["downgraded_scenes_count"] == expected_downgraded_count

    # Check each scene's scoring consistency
    for sc in plan["scenes"]:
        scores = sc.get("video_value_scores", {})
        assert "physical_action" in scores
        assert "character_interaction" in scores
        assert "camera_motion_value" in scores
        assert "story_information_from_motion" in scores
        assert "total_score" in scores

        total = scores["total_score"]
        expected_total = (
            scores["physical_action"]
            + scores["character_interaction"]
            + scores["camera_motion_value"]
            + scores["story_information_from_motion"]
        )
        assert total == expected_total, f"Score arithmetic mismatch in {sc['scene_id']}"

        if total >= 7:
            assert sc["visual_mode"] == "VIDEO_RECOMMENDED", f"Scene {sc['scene_id']} score {total} must be video"
            assert sc["video_prompt"] is not None
        else:
            assert sc["visual_mode"] == "IMAGE_ONLY", f"Scene {sc['scene_id']} score {total} must be image only"
            assert sc["video_prompt"] is None


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_fact_grounding_audit(ep_id):
    """Criteria 4: Fact Grounding audit must have 0 ungrounded facts and 0 forbidden labels."""
    fg_path = PILOT_03_VISUAL_V1_0A / ep_id / "visual_fact_grounding.json"
    assert fg_path.exists(), f"Fact grounding file missing: {fg_path}"

    with open(fg_path, "r", encoding="utf-8") as f:
        fg = json.load(f)

    assert fg["status"] == "PASS"
    assert fg["ungrounded_count"] == 0

    ov = fg["overlay_grounding"]
    assert ov["status"] == "PASS"
    assert ov["ungrounded_count"] == 0
    assert ov["forbidden_label_count"] == 0


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_visual_spoiler_guard(ep_id):
    """Criteria 6: Visual spoiler guard (no leaks before Reveal 1 and Reveal 2; dry narration dominance)."""
    plan_path = PILOT_03_VISUAL_V1_0A / ep_id / "visual_plan.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan["scenes"]

    # Reveal 1 (SC_031) must be IMAGE_ONLY to allow dry narration dominance
    assert scenes[30]["scene_id"] == "SC_031"
    assert scenes[30]["visual_mode"] == "IMAGE_ONLY"

    # Reveal 2 (SC_039) must be IMAGE_ONLY
    assert scenes[38]["scene_id"] == "SC_039"
    assert scenes[38]["visual_mode"] == "IMAGE_ONLY"

    # Check that scenes before SC_031 do not reveal truth
    for i in range(30):
        sc = scenes[i]
        text_lower = (sc["image_prompt"] + " " + (sc["video_prompt"] or "")).lower()
        if ep_id == "EP003":
            assert "nhà tình thương" not in text_lower, f"Spoiler in {sc['scene_id']}"
            assert "trẻ mồ côi" not in text_lower, f"Spoiler in {sc['scene_id']}"
        elif ep_id == "EP011":
            assert "nhận nuôi hợp pháp" not in text_lower, f"Spoiler in {sc['scene_id']}"
            assert "gia đình hiếm muộn" not in text_lower, f"Spoiler in {sc['scene_id']}"


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_character_and_prop_continuity(ep_id):
    """Criteria 7 & 8: Character reference approval, identity families, and prop references."""
    char_path = PILOT_03_VISUAL_V1_0A / ep_id / "character_bible.json"
    prop_path = PILOT_03_VISUAL_V1_0A / ep_id / "prop_bible.json"
    loc_path = PILOT_03_VISUAL_V1_0A / ep_id / "location_bible.json"

    assert char_path.exists()
    assert prop_path.exists()
    assert loc_path.exists()

    with open(char_path, "r", encoding="utf-8") as f:
        char_data = json.load(f)

    # Characters must have identity_families
    identity_families = char_data.get("identity_families", [])
    characters = char_data.get("characters", [])
    assert len(identity_families) >= 1, f"Missing identity families in {ep_id}"

    # All characters must require reference approval
    for c in characters:
        assert c.get("requires_approval") is True, f"Character {c['character_id']} must require approval"
        assert len(c.get("reference_prompt", "")) >= 20

    with open(prop_path, "r", encoding="utf-8") as f:
        props = json.load(f)

    # Key props must require reference
    if ep_id == "EP003":
        box_prop = next(p for p in props if p["prop_id"] == "PROP_WOODEN_BOX")
        assert box_prop.get("prop_reference_required") is True
        photo_prop = next(p for p in props if p["prop_id"] == "PROP_VINTAGE_PHOTO_BAO_THOA")
        assert photo_prop.get("prop_reference_required") is True
    elif ep_id == "EP011":
        phone_prop = next(p for p in props if p["prop_id"] == "PROP_OLD_PHONE_01")
        assert phone_prop.get("prop_reference_required") is True
        photo_prop = next(p for p in props if p["prop_id"] == "PROP_HOSPITAL_PHOTO_2012")
        assert photo_prop.get("prop_reference_required") is True
        bracelet_prop = next(p for p in props if p["prop_id"] == "PROP_SILVER_BRACELET")
        assert bracelet_prop.get("prop_reference_required") is True


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_prompt_qc(ep_id):
    """Criteria 9: Image prompts must have Vietnamese anchor; video prompts structured."""
    plan_path = PILOT_03_VISUAL_V1_0A / ep_id / "visual_plan.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    for sc in plan["scenes"]:
        ip = sc["image_prompt"]
        assert len(ip) >= 20, f"Image prompt too short in {sc['scene_id']}"
        assert "Vietnamese" in ip, f"Missing Vietnamese anchor in {sc['scene_id']}"

        if sc["visual_mode"] == "VIDEO_RECOMMENDED":
            vp = sc["video_prompt"]
            assert vp is not None
            for marker in ["Start:", "Action:", "Camera:", "End:"]:
                assert marker in vp, f"Missing marker '{marker}' in video prompt {sc['scene_id']}"


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_flow_package_integrity(ep_id):
    """Criteria 10: Google Flow packages physically exist with all 9 required files."""
    flow_dir = PILOT_03_VISUAL_V1_0A / ep_id / "flow_package"
    assert flow_dir.exists()

    required_files = [
        "scenes.csv",
        "manifest.json",
        "image_prompts.json",
        "video_prompts.json",
        "characters.json",
        "locations.json",
        "props.json",
        "overlays.json",
        "README_IMPORT.txt"
    ]
    for rf in required_files:
        fp = flow_dir / rf
        assert fp.exists(), f"Missing Flow package file: {fp}"
        assert fp.stat().st_size > 0, f"Flow package file empty: {fp}"

    # Verify scenes.csv structure (16 columns, 45 rows)
    with open(flow_dir / "scenes.csv", "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    assert len(reader) == 46  # 1 header + 45 scenes
    assert len(reader[0]) == 16


def test_zero_media_generation():
    """Criteria 11: ZERO newly generated image/video files; status NOT_GENERATED."""
    forbidden_exts = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".avi"}

    for ep_id in ["EP003", "EP011"]:
        ep_dir = PILOT_03_VISUAL_V1_0A / ep_id
        for f in ep_dir.rglob("*"):
            if f.is_file():
                assert f.suffix.lower() not in forbidden_exts, f"Forbidden media generated: {f}"

        plan_path = ep_dir / "visual_plan.json"
        with open(plan_path, "r", encoding="utf-8") as fl:
            plan = json.load(fl)
        for sc in plan["scenes"]:
            assert sc["image_status"] == "NOT_GENERATED"
            assert sc["video_status"] == "NOT_GENERATED"


def test_master_report_and_qc():
    """Criteria 12: Master report status AWAITING_USER_VISUAL_PLAN_REVIEW and QC PASS."""
    json_path = REPORTS_DIR / "production_pilot_03_visual_v1_0a_report.json"
    csv_path = REPORTS_DIR / "production_pilot_03_visual_v1_0a_report.csv"

    assert json_path.exists()
    assert csv_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["status"] == "AWAITING_USER_VISUAL_PLAN_REVIEW"
    assert data["version"] == "V1.0a"

    for ep_id in ["EP003", "EP011"]:
        ep_data = data["episodes"][ep_id]
        assert ep_data["status"] == "AWAITING_USER_VISUAL_PLAN_REVIEW"
        assert ep_data["fact_grounding"] == "PASS"
        assert ep_data["overlay_fact_grounding"] == "PASS"
        assert ep_data["visual_spoiler_guard"] == "PASS"
        assert ep_data["timeline_coverage"] == "PASS"
        assert ep_data["prompt_qc"] == "PASS"
        assert ep_data["video_percentage"] <= 40.0
        assert ep_data["ungrounded_overlay_facts"] == 0
        assert ep_data["forbidden_labels_detected"] == 0
