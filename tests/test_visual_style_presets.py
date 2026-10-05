"""Comprehensive test suite for Visual Style Presets (manhua_viet, 2d_am_viet, cinematic_documentary)."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from studio.backend.services.visual_styles import (
    DEFAULT_VISUAL_STYLE,
    SUPPORTED_VISUAL_STYLES,
    compose_character_reference_prompt,
    compose_default_location_reference_prompt,
    compose_location_reference_prompt,
    compose_scene_image_prompt,
    compose_scene_video_prompt,
    get_available_styles,
    load_style_preset_data,
    normalize_visual_style,
)
from studio.backend.services.visual_service import VisualService
from apps.visual_pilot_03_v1_0a.google_flow_exporter import build_episode_export


def test_preset_json_files_exist_and_valid():
    """Validates that all visual preset JSON files exist and have required schema keys."""
    presets_dir = Path(__file__).resolve().parent.parent / "visual_presets"
    for style_id, info in SUPPORTED_VISUAL_STYLES.items():
        preset_file = presets_dir / info["preset_file"]
        assert preset_file.exists(), f"Missing preset file: {preset_file}"
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        assert "id" in data
        assert "name" in data
        assert "style_prompt" in data
        assert "negative_prompt" in data
        assert "series_visual_style" in data

    # Non-photoreal presets must forbid Chinese characters and real human photos
    for non_photo in ["manhua_viet", "2d_am_viet"]:
        data = load_style_preset_data(non_photo)
        avoid = " ".join(data.get("series_visual_style", {}).get("avoid", [])).lower()
        neg = data.get("negative_prompt", "").lower()
        assert "chinese" in avoid or "chinese" in neg, f"{non_photo} must forbid Chinese text/signage"
        assert "real human" in avoid or "photo" in neg, f"{non_photo} must forbid real human photos"


def test_default_style_prompts_match_original_behavior():
    """Default style (cinematic_documentary) must preserve exact original prompt text for backward compatibility."""
    # Character reference prompt
    char_prompt = compose_character_reference_prompt(
        name="Hùng",
        age=32,
        gender="MALE",
        role="Kỹ sư",
        description="Người đàn ông điềm đạm",
        visual_style=DEFAULT_VISUAL_STYLE,
    )
    assert "Realistic Vietnamese man, 32-year-old with authentic Vietnamese facial features" in char_prompt
    assert "natural skin texture" in char_prompt
    assert "35mm" not in char_prompt or "photography" not in char_prompt # Waist-up studio portrait
    assert "16:9, no text, no watermark" in char_prompt

    # Scene image prompt
    scene_image = compose_scene_image_prompt(
        scene_idx=0,
        combined_text="Lan mở cửa bước vào phòng khách và nhìn thấy hộp quà.",
        visible_characters=["CHAR_LAN"],
        location_name="Phòng khách căn hộ (LOC_LIVING)",
        dominant_profile="NORMAL",
        characters_map={"CHAR_LAN": {"name": "Lan", "gender": "FEMALE"}},
        visual_style=DEFAULT_VISUAL_STYLE,
    )
    assert scene_image.startswith("Vietnamese cinematic documentary realism, 35mm photography, natural film grain. Setting: Phòng khách căn hộ.")
    assert "Visible cast ONLY: Lan, Vietnamese woman; preserve this character reference" in scene_image
    assert "balanced 16:9 composition, no captions, no watermark." in scene_image

    # Scene video prompt
    scene_video = compose_scene_video_prompt(
        scene_idx=0,
        combined_text="Lan mở cửa bước vào phòng khách.",
        visible_characters=["CHAR_LAN"],
        location_name="Phòng khách căn hộ",
        dominant_profile="NORMAL",
        visual_style=DEFAULT_VISUAL_STYLE,
    )
    assert scene_video["camera"] == "Slow restrained documentary camera movement, stable facial identity, no sudden cuts."

    # Location reference prompt
    loc_ref = compose_location_reference_prompt("Phòng khách", visual_style=DEFAULT_VISUAL_STYLE)
    assert loc_ref == "Cinematic Vietnamese location reference: Phòng khách. Natural light, realistic documentary style, 16:9, no text, no watermark."

    default_loc = compose_default_location_reference_prompt(visual_style=DEFAULT_VISUAL_STYLE)
    assert default_loc == "Contemporary Vietnamese family home, cinematic documentary realism, natural light, 16:9, no text, no watermark."


def test_manhua_viet_style_prompts():
    """Manhua style must produce semi-realistic graphic novel prompts with Vietnamese setting and no Chinese text."""
    # Character reference prompt
    char_prompt = compose_character_reference_prompt(
        name="Thảo",
        age=28,
        gender="FEMALE",
        role="Trưởng phòng",
        description="Người phụ nữ sắc sảo",
        visual_style="manhua_viet",
    )
    assert "Semi-realistic manhua character concept sheet of Vietnamese character Thảo" in char_prompt
    assert "mature adult proportions" in char_prompt
    assert "strictly no Chinese text" in char_prompt
    assert "not a real human photo" in char_prompt
    assert "natural skin texture" not in char_prompt
    assert "Realistic Vietnamese" not in char_prompt

    # Scene image prompt
    scene_image = compose_scene_image_prompt(
        scene_idx=1,
        combined_text="Hùng bước vào quán cà phê và đặt chiếc kẹp tóc tím lên bàn.",
        visible_characters=["CHAR_HUNG"],
        location_name="Quán cà phê góc phố",
        dominant_profile="NORMAL",
        characters_map={"CHAR_HUNG": {"name": "Hùng", "gender": "MALE"}},
        visual_style="manhua_viet",
    )
    assert "Modern Vietnamese urban manhua semi-realistic illustration" in scene_image
    assert "no Chinese characters or signage" in scene_image
    assert "strictly no Chinese text" in scene_image
    assert "not a real human photo" in scene_image
    assert "35mm photography" not in scene_image
    assert "natural film grain" not in scene_image

    # Scene video prompt
    scene_video = compose_scene_video_prompt(
        scene_idx=1,
        combined_text="Hùng đặt chiếc kẹp tóc tím lên bàn.",
        visible_characters=["CHAR_HUNG"],
        location_name="Quán cà phê góc phố",
        dominant_profile="NORMAL",
        visual_style="manhua_viet",
    )
    assert "animation camera movement" in scene_video["camera"]
    assert "comic panel pan" in scene_video["camera"]

    # Location reference prompt
    loc_ref = compose_location_reference_prompt("Văn phòng công ty", visual_style="manhua_viet")
    assert "Semi-realistic Vietnamese urban manhua background reference: Văn phòng công ty" in loc_ref
    assert "strictly no Chinese signage" in loc_ref


def test_2d_am_viet_style_prompts():
    """2D warm illustration style must produce painterly textured prompts with Vietnamese ambiance."""
    # Character reference prompt
    char_prompt = compose_character_reference_prompt(
        name="Minh",
        age=35,
        gender="MALE",
        role="Giám đốc",
        description="Người đàn ông chững chạc",
        visual_style="2d_am_viet",
    )
    assert "Cinematic 2D digital illustration portrait of Vietnamese character Minh" in char_prompt
    assert "painterly brushwork with crisp focal details" in char_prompt
    assert "not a real human photo" in char_prompt
    assert "no Chinese text" in char_prompt
    assert "Realistic Vietnamese" not in char_prompt

    # Scene image prompt
    scene_image = compose_scene_image_prompt(
        scene_idx=2,
        combined_text="Minh ngồi bên cửa sổ nhìn ra ban công mưa rơi.",
        visible_characters=["CHAR_MINH"],
        location_name="Ban công chung cư",
        dominant_profile="TENSION",
        characters_map={"CHAR_MINH": {"name": "Minh", "gender": "MALE"}},
        visual_style="2d_am_viet",
    )
    assert "Contemporary Vietnamese 2D cinematic digital illustration, painterly textured art style" in scene_image
    assert "authentic Vietnamese domestic environment" in scene_image
    assert "strictly no Chinese characters" in scene_image
    assert "not a real human photo" in scene_image
    assert "35mm photography" not in scene_image

    # Location reference prompt
    loc_ref = compose_location_reference_prompt("Phòng làm việc", visual_style="2d_am_viet")
    assert "Cinematic Vietnamese 2D illustration environment concept: Phòng làm việc" in loc_ref
    assert "Painterly texture" in loc_ref
    assert "strictly no Chinese characters" in loc_ref


def test_style_normalization_and_fallback():
    """Invalid or empty style strings must safely normalize to default."""
    assert normalize_visual_style(None) == DEFAULT_VISUAL_STYLE
    assert normalize_visual_style("") == DEFAULT_VISUAL_STYLE
    assert normalize_visual_style("random_non_existent_style") == DEFAULT_VISUAL_STYLE
    assert normalize_visual_style("sau_canh_cua") == DEFAULT_VISUAL_STYLE
    assert normalize_visual_style("manhua_viet") == "manhua_viet"
    assert normalize_visual_style("2d_am_viet") == "2d_am_viet"
    assert normalize_visual_style("  MANHUA_VIET  ") == "manhua_viet"


def test_get_available_styles():
    """Available styles endpoint must list id, name, badge and photoreal flag."""
    styles = get_available_styles()
    assert len(styles) == 3
    ids = [s["id"] for s in styles]
    assert "cinematic_documentary" in ids
    assert "manhua_viet" in ids
    assert "2d_am_viet" in ids
    for s in styles:
        assert "name" in s and len(s["name"]) > 0
        assert "badge" in s and len(s["badge"]) > 0
        assert "description" in s and len(s["description"]) > 0
        assert "is_photoreal" in s


def test_visual_service_style_persistence_and_staleness(tmp_path, monkeypatch):
    """Setting style updates project.json and detects staleness against existing visual_plan.json."""
    from studio.backend.services import visual_service as vs_mod

    # Setup isolated directories
    proj_dir = tmp_path / "projects" / "EP_TEST"
    proj_dir.mkdir(parents=True)
    vis_dir = tmp_path / "visual" / "EP_TEST"
    vis_dir.mkdir(parents=True)

    monkeypatch.setattr(vs_mod, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(vs_mod, "VISUAL_DIR", tmp_path / "visual")

    srv = VisualService()

    # 1. Project has no project.json -> defaults to cinematic_documentary
    assert srv.get_project_visual_style("EP_TEST") == DEFAULT_VISUAL_STYLE
    status_0 = srv.get_visual_status("EP_TEST")
    assert status_0["has_plan"] is False
    assert status_0["is_stale"] is False

    # 2. Write project.json with manhua_viet
    res = srv.set_project_visual_style("EP_TEST", "manhua_viet")
    assert res["visual_style"] == "manhua_viet"
    assert srv.get_project_visual_style("EP_TEST") == "manhua_viet"

    # 3. Create visual_plan.json with manhua_viet -> not stale
    plan_file = vis_dir / "visual_plan.json"
    plan_file.write_text(json.dumps({
        "episode_id": "EP_TEST",
        "visual_style": "manhua_viet",
        "scenes": [{"scene_id": "SC_001", "visual_mode": "IMAGE_ONLY"}]
    }), encoding="utf-8")

    status_1 = srv.get_visual_status("EP_TEST")
    assert status_1["has_plan"] is True
    assert status_1["visual_style"] == "manhua_viet"
    assert status_1["plan_visual_style"] == "manhua_viet"
    assert status_1["is_stale"] is False

    # 4. Switch project style to 2d_am_viet -> now plan is stale!
    res2 = srv.set_project_visual_style("EP_TEST", "2d_am_viet")
    assert res2["plan_is_stale"] is True
    status_2 = srv.get_visual_status("EP_TEST")
    assert status_2["visual_style"] == "2d_am_viet"
    assert status_2["plan_visual_style"] == "manhua_viet"
    assert status_2["is_stale"] is True


def test_google_flow_export_with_manhua_style(tmp_path, monkeypatch):
    """Google Flow export retains visual_style and removes 35mm photography references for props."""
    from apps.visual_pilot_03_v1_0a import google_flow_exporter as gfe_mod

    vis_dir = tmp_path / "visual" / "EP_STYLE_TEST"
    vis_dir.mkdir(parents=True)
    monkeypatch.setattr(gfe_mod, "VISUAL_DIR", tmp_path / "visual")

    # Mock visual plan with manhua_viet
    (vis_dir / "visual_plan.json").write_text(json.dumps({
        "episode_id": "EP_STYLE_TEST",
        "title": "Bí mật công sở",
        "visual_style": "manhua_viet",
        "audio_duration_sec": 120.0,
        "scenes": [
            {
                "scene_id": "SC_001",
                "order": 1,
                "start_time": 0.0,
                "end_time": 4.0,
                "duration": 4.0,
                "source_segments": ["001"],
                "narration_summary": "Lan mở cửa bước vào.",
                "visual_mode": "IMAGE_ONLY",
                "video_recommended": False,
                "video_value_scores": {"total_score": 30},
                "visible_characters": ["CHAR_LAN"],
                "character_refs_required": ["CHAR_LAN"],
                "location_id": "LOC_HOME",
                "location_confidence": "HIGH",
                "location_evidence": "nhà",
                "location_source": "EXPLICIT",
                "props": ["PROP_WOODEN_BOX"],
                "prop_refs_required": ["PROP_WOODEN_BOX"],
                "image_prompt": "Modern Vietnamese urban manhua illustration of Lan.",
                "video_prompt": None,
                "image_motion": {"type": "KEN_BURNS_SLOW_PAN"},
            }
        ]
    }), encoding="utf-8")

    (vis_dir / "character_bible.json").write_text(json.dumps({
        "visual_style": "manhua_viet",
        "identity_families": [],
        "characters": [
            {
                "character_id": "CHAR_LAN",
                "name": "Lan",
                "requires_approval": True,
                "reference_prompt": "Semi-realistic manhua character concept sheet of Vietnamese character Lan."
            }
        ]
    }), encoding="utf-8")

    (vis_dir / "prop_bible.json").write_text(json.dumps([
        {
            "prop_id": "PROP_WOODEN_BOX",
            "name": "Hộp gỗ cổ",
            "prop_reference_required": True,
            "material": "gỗ mít",
        }
    ]), encoding="utf-8")

    (vis_dir / "location_bible.json").write_text(json.dumps([
        {
            "location_id": "LOC_HOME",
            "name": "Phòng khách căn hộ",
            "reference_prompt": "Semi-realistic Vietnamese urban manhua background: Phòng khách"
        }
    ]), encoding="utf-8")

    (vis_dir / "overlay_plan.json").write_text(json.dumps({"overlays": []}), encoding="utf-8")

    export_obj = build_episode_export("EP_STYLE_TEST")

    assert export_obj["visual_style"] == "manhua_viet"
    assert export_obj["generation_settings"]["visual_style"] == "manhua_viet"

    prop_obj = next(p for p in export_obj["props"] if p["prop_id"] == "PROP_WOODEN_BOX")
    assert prop_obj["reference_prompt"] is not None
    assert "35mm photography" not in prop_obj["reference_prompt"]
    assert "manhua" in prop_obj["reference_prompt"]
    assert "no Chinese characters" in prop_obj["reference_prompt"]
