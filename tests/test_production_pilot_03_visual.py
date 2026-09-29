"""Automated test suite for Production Pilot 03 Visual Planning.

Verifies all 11 acceptance criteria from Section 40:
1. Real audio timing used as master clock (tolerance <= 0.10s)
2. 100% narration timeline coverage (no gaps, no overlaps, all 90 segments mapped)
3. Visual spoiler guard (no leaks before Reveal 1 and Reveal 2)
4. Character continuity & primary character approval flags
5. Location & prop continuity
6. Video recommendation ratio <= 40% (target 30-35%)
7. Image prompts production-ready (Vietnamese anchor, cinematic terminology, length >= 20)
8. Video prompts structured as Start | Action | Camera | End
9. Google Flow packages physically exist with all required files
10. Zero newly generated image/video media files
11. Master report and QC validation status PASS
"""
import csv
import json
from pathlib import Path
import pytest
import soundfile as sf

BASE_DIR = Path(__file__).resolve().parent.parent
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"
PILOT_03_VISUAL = BASE_DIR / "production_pilot_03_visual"
REPORTS_DIR = BASE_DIR / "reports"


@pytest.mark.parametrize("ep_id,expected_scenes,expected_video,expected_overlays", [
    ("EP003", 45, 15, 5),
    ("EP011", 45, 15, 6),
])
def test_timeline_and_audio_duration_sync(ep_id, expected_scenes, expected_video, expected_overlays):
    """Criteria 1 & 2: Real audio duration as master clock, 0 gaps, 0 overlaps."""
    wav_path = PILOT_03_AUDIO / ep_id / "audio" / "final_mix.wav"
    assert wav_path.exists(), f"Audio master missing: {wav_path}"
    real_duration = sf.info(str(wav_path)).duration

    plan_path = PILOT_03_VISUAL / ep_id / "visual_plan.json"
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


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_hybrid_video_budget(ep_id):
    """Criteria 6: Video recommendation ratio <= 40% (strictly 30-35%)."""
    plan_path = PILOT_03_VISUAL / ep_id / "visual_plan.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    video_count = plan["video_recommended_count"]
    total_scenes = plan["total_scenes"]
    ratio_pct = plan["video_ratio_pct"]

    assert video_count == 15
    assert total_scenes == 45
    assert ratio_pct == 33.33
    assert ratio_pct <= 40.0


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_visual_spoiler_guard(ep_id):
    """Criteria 3: No visual spoilers before Reveal 1 (SC_031) and Reveal 2 (SC_039)."""
    plan_path = PILOT_03_VISUAL / ep_id / "visual_plan.json"
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
def test_character_and_prop_bibles(ep_id):
    """Criteria 4 & 5: Character continuity, flashback control, prop bibles."""
    char_path = PILOT_03_VISUAL / ep_id / "character_bible.json"
    prop_path = PILOT_03_VISUAL / ep_id / "prop_bible.json"
    loc_path = PILOT_03_VISUAL / ep_id / "location_bible.json"

    assert char_path.exists()
    assert prop_path.exists()
    assert loc_path.exists()

    with open(char_path, "r", encoding="utf-8") as f:
        characters = json.load(f)
    with open(prop_path, "r", encoding="utf-8") as f:
        props = json.load(f)
    with open(loc_path, "r", encoding="utf-8") as f:
        locations = json.load(f)

    # Primary characters require reference approval
    primary_chars = [c for c in characters if c["priority"] == "PRIMARY"]
    assert len(primary_chars) >= 1
    for c in primary_chars:
        assert c["requires_approval"] is True
        assert len(c["reference_prompt"]) >= 50
        assert "Vietnamese" in c["reference_prompt"]

    # Props must have continuity notes
    for p in props:
        assert len(p["continuity_notes"]) > 10

    # Locations must specify architecture and lighting
    for loc in locations:
        assert len(loc["architecture"]) > 20
        assert len(loc["lighting"]) > 10


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_prompt_qc_and_video_prompt_structure(ep_id):
    """Criteria 7 & 8: Image prompts production-ready, video prompts structured."""
    plan_path = PILOT_03_VISUAL / ep_id / "visual_plan.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes = plan["scenes"]
    for sc in scenes:
        ip = sc["image_prompt"]
        assert len(ip) >= 50, f"Prompt too short in {sc['scene_id']}"
        assert "Vietnamese" in ip, f"Missing Vietnamese anchor in {sc['scene_id']}"
        assert "35mm" in ip or "documentary" in ip or "photography" in ip or "lens" in ip

        if sc["visual_mode"] == "VIDEO_RECOMMENDED":
            vp = sc["video_prompt"]
            assert vp is not None
            assert "Start:" in vp
            assert "Action:" in vp
            assert "Camera:" in vp
            assert "End:" in vp
        else:
            assert sc["video_prompt"] is None


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_flow_package_completeness(ep_id):
    """Criteria 9: Flow package physically exists with all required files."""
    flow_dir = PILOT_03_VISUAL / ep_id / "flow_package"
    assert flow_dir.exists()

    required_files = [
        "manifest.json",
        "scenes.csv",
        "image_prompts.json",
        "video_prompts.json",
        "characters.json",
        "locations.json",
        "props.json",
        "overlays.json",
        "README_IMPORT.txt"
    ]
    for rf in required_files:
        p = flow_dir / rf
        assert p.exists(), f"Flow package missing {rf}"
        assert p.stat().st_size > 0, f"File {rf} is empty"

    # Validate scenes.csv has exactly 15 columns and 45 rows (+ 1 header)
    with open(flow_dir / "scenes.csv", "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
    assert len(reader) == 46  # 1 header + 45 scenes
    assert len(reader[0]) == 15  # exactly 15 columns
    assert reader[0][0] == "episode_id"
    assert reader[0][14] == "prompt_hash"


def test_zero_new_media_generated():
    """Criteria 10: 0 new image/video files generated in visual directory."""
    new_images = list(PILOT_03_VISUAL.rglob("*.png")) + list(PILOT_03_VISUAL.rglob("*.jpg"))
    new_videos = list(PILOT_03_VISUAL.rglob("*.mp4"))
    assert len(new_images) == 0, f"Found unexpected generated images: {new_images}"
    assert len(new_videos) == 0, f"Found unexpected generated videos: {new_videos}"


def test_master_report():
    """Criteria 11: Master report exists and both episodes have status PASS."""
    report_json_path = REPORTS_DIR / "production_pilot_03_visual_report.json"
    report_csv_path = REPORTS_DIR / "production_pilot_03_visual_report.csv"

    assert report_json_path.exists()
    assert report_csv_path.exists()

    with open(report_json_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    assert report["status"] == "AWAITING_USER_VISUAL_PLAN_REVIEW"
    for ep_id in ["EP003", "EP011"]:
        ep_rep = report["episodes"][ep_id]
        assert ep_rep["timeline_coverage"] == "PASS"
        assert ep_rep["visual_spoiler_guard"] == "PASS"
        assert ep_rep["prompt_qc"] == "PASS"
        assert ep_rep["character_continuity"] == "PASS"
        assert ep_rep["location_continuity"] == "PASS"
        assert ep_rep["prop_continuity"] == "PASS"
        assert ep_rep["video_percentage"] <= 40.0
