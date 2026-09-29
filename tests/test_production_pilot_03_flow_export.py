"""Tests for Production Pilot 03 Google Flow App JSON Export.

Verifies:
- Schema compliance with SCC_FLOW_V1
- Presence of all export JSON files
- Exact scene, character, prop, and video budget counts
- Reveal 1 and Reveal 2 are strictly IMAGE_ONLY
- Generational character anchor dependencies
- Prop reference character dependencies
- Zero invented media IDs (all null)
- auto_generate_on_import is False
- Timeline 100% contiguity
"""
import json
from pathlib import Path
import pytest

EXPORTS_DIR = Path(__file__).resolve().parent.parent / "production_pilot_03_visual_v1_0a" / "exports"


@pytest.fixture(scope="module")
def ep003_data():
    path = EXPORTS_DIR / "EP003_google_flow.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def ep011_data():
    path = EXPORTS_DIR / "EP011_google_flow.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def combined_data():
    path = EXPORTS_DIR / "PRODUCTION_PILOT_03_google_flow.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_version_and_settings(ep003_data, ep011_data, combined_data):
    for data in [ep003_data, ep011_data, combined_data]:
        assert data["schema_version"] == "SCC_FLOW_V1"
        assert data["project"]["export_status"] == "GOOGLE_FLOW_EXPORT_READY"
        
        for ep in data["episodes"]:
            settings = ep["generation_settings"]
            assert settings["image_model"] == "BANANA_PRO"
            assert settings["video_model"] == "OMNI"
            assert settings["aspect_ratio"] == "16:9"
            assert settings["auto_generate_on_import"] is False
            assert settings["image_concurrency"] == 1
            assert settings["image_delay_seconds"] == 10


def test_ep003_structure(ep003_data):
    assert len(ep003_data["episodes"]) == 1
    ep = ep003_data["episodes"][0]
    assert ep["episode_id"] == "EP003"

    # Scenes count
    scenes = ep["scenes"]
    assert len(scenes) == 45

    video_scenes = [s for s in scenes if s["visual_mode"] == "VIDEO_RECOMMENDED"]
    image_scenes = [s for s in scenes if s["visual_mode"] == "IMAGE_ONLY"]
    assert len(video_scenes) == 7
    assert len(image_scenes) == 38

    # Reveal 1 (SC_031) and Reveal 2 (SC_039) must be IMAGE_ONLY
    sc_031 = next(s for s in scenes if s["scene_id"] == "SC_031")
    sc_039 = next(s for s in scenes if s["scene_id"] == "SC_039")
    assert sc_031["visual_mode"] == "IMAGE_ONLY"
    assert sc_039["visual_mode"] == "IMAGE_ONLY"

    # Characters
    chars = ep["characters"]
    assert len(chars) == 6
    char_ids = {c["character_id"] for c in chars}
    assert "CHAR_BA_HAO_ELDER" in char_ids
    assert "CHAR_BA_HAO_YOUNG" in char_ids
    assert "CHAR_BA_THOA_ELDER" in char_ids
    assert "CHAR_BA_THOA_YOUNG" in char_ids

    # Young versions must depend on elder anchors
    hao_young = next(c for c in chars if c["character_id"] == "CHAR_BA_HAO_YOUNG")
    assert hao_young["depends_on_reference"] == "CHAR_BA_HAO_ELDER"
    assert hao_young["use_identity_anchor"] is True

    thoa_young = next(c for c in chars if c["character_id"] == "CHAR_BA_THOA_YOUNG")
    assert thoa_young["depends_on_reference"] == "CHAR_BA_THOA_ELDER"
    assert thoa_young["use_identity_anchor"] is True

    # Props
    props = [p for p in ep["props"] if p["reference_required"]]
    assert len(props) == 2
    photo_prop = next(p for p in props if p["prop_id"] == "PROP_VINTAGE_PHOTO_BAO_THOA")
    assert "CHAR_BA_HAO_YOUNG" in photo_prop["depends_on_characters"]
    assert "CHAR_BA_THOA_YOUNG" in photo_prop["depends_on_characters"]


def test_ep011_structure(ep011_data):
    assert len(ep011_data["episodes"]) == 1
    ep = ep011_data["episodes"][0]
    assert ep["episode_id"] == "EP011"

    # Scenes count
    scenes = ep["scenes"]
    assert len(scenes) == 45

    video_scenes = [s for s in scenes if s["visual_mode"] == "VIDEO_RECOMMENDED"]
    image_scenes = [s for s in scenes if s["visual_mode"] == "IMAGE_ONLY"]
    assert len(video_scenes) == 8
    assert len(image_scenes) == 37

    # Reveal 1 (SC_031) and Reveal 2 (SC_039) must be IMAGE_ONLY
    sc_031 = next(s for s in scenes if s["scene_id"] == "SC_031")
    sc_039 = next(s for s in scenes if s["scene_id"] == "SC_039")
    assert sc_031["visual_mode"] == "IMAGE_ONLY"
    assert sc_039["visual_mode"] == "IMAGE_ONLY"

    # Characters
    chars = ep["characters"]
    assert len(chars) == 7
    nam_young = next(c for c in chars if c["character_id"] == "CHAR_NAM_YOUNG_2012")
    assert nam_young["depends_on_reference"] == "CHAR_NAM_PRESENT"
    assert nam_young["use_identity_anchor"] is True

    # Props
    props = [p for p in ep["props"] if p["reference_required"]]
    assert len(props) == 3
    hosp_photo = next(p for p in props if p["prop_id"] == "PROP_HOSPITAL_PHOTO_2012")
    assert "CHAR_NAM_YOUNG_2012" in hosp_photo["depends_on_characters"]
    assert "CHAR_THAO_2012" in hosp_photo["depends_on_characters"]
    assert "CHAR_BE_AN_INFANT_2012" in hosp_photo["depends_on_characters"]


def test_null_media_ids(ep003_data, ep011_data):
    for data in [ep003_data, ep011_data]:
        ep = data["episodes"][0]
        for c in ep["characters"]:
            assert c["reference_media_id"] is None
        for p in ep["props"]:
            assert p["reference_media_id"] is None
        for s in ep["scenes"]:
            assert s["image_media_id"] is None
            assert s["video_media_id"] is None
            assert s["generation_dependencies_satisfied"] is False


def test_timeline_contiguity(ep003_data, ep011_data):
    for data in [ep003_data, ep011_data]:
        ep = data["episodes"][0]
        scenes = sorted(ep["scenes"], key=lambda x: x["order"])
        curr_t = 0.0
        for s in scenes:
            assert abs(s["start_time"] - curr_t) < 0.005, f"Discontinuity at {s['scene_id']}: {s['start_time']} vs {curr_t}"
            assert s["end_time"] > s["start_time"]
            curr_t = s["end_time"]
