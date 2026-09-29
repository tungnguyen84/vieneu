"""Tests for V9.3.1 Hybrid Visual Production Strategy (Section 49)."""
from __future__ import annotations

import csv
import json
import os
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.script_factory.models import ApprovalStatus, FullScript, ScriptSegment, StoryBible
from apps.script_factory.production_adapter import ProductionAdapter, migrate_ep001_to_v9_3_1


@pytest.fixture
def mock_script_and_bible():
    segs = [
        ScriptSegment(id=f"SEG_{i:03d}", text=f"Câu chuyện bí ẩn số {i}", delivery_profile="NORMAL")
        for i in range(1, 81)
    ]
    # Add reveal segment
    segs[50].delivery_profile = "REVEAL"
    segs[50].text = "Trích lục khai tử xác nhận người cha đã mất 14 năm trước."

    # Add confrontation segment
    segs[20].text = "Hai người đối chất gay gắt về khoản tiền biến mất."
    # Add document segment
    segs[30].text = "Lan mở cuốn sổ tiết kiệm và kiểm tra từng biên lai ngân hàng."

    script = FullScript(
        episode_id="EP999",
        title="Tập Thử Nghiệm Visual",
        host={"id": "MINH", "name": "Minh", "voice": "Binh"},
        segments=segs,
        total_segments=len(segs),
        status=ApprovalStatus.APPROVED,
    )
    bible = StoryBible(
        episode_id="EP999",
        title="Tập Thử Nghiệm Visual",
        protagonist={"name": "Lan", "char_id": "LAN", "age": 30},
        locations=["PHÒNG KHÁCH", "VĂN PHÒNG", "QUÊ"],
        status=ApprovalStatus.APPROVED,
    )
    return script, bible


# 1. test_visual_mode_defaults_to_image_only
def test_visual_mode_defaults_to_image_only():
    adapter = ProductionAdapter()
    scenes = [{"scene_id": "SC_001", "story_beat": "Lan đứng lặng nhìn ra cửa sổ."}]
    classified = adapter.classify_scenes(scenes, video_budget="BALANCED")
    assert classified[0]["visual_mode"] == "IMAGE_ONLY"


# 2. test_all_scenes_require_image
def test_all_scenes_require_image(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    with open(prod_dir / "visual_manifest_v9_3_1.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for sc in data["scenes"]:
        assert sc.get("image_file") is not None
        assert sc.get("image_prompt") is not None
        assert len(sc["image_prompt"]) > 20


# 3. test_image_only_does_not_require_video
def test_image_only_does_not_require_video(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    with open(prod_dir / "visual_manifest_v9_3_1.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    img_only_scenes = [s for s in data["scenes"] if s["visual_mode"] == "IMAGE_ONLY"]
    assert len(img_only_scenes) > 0
    for sc in img_only_scenes:
        assert sc.get("video_file") is None
        assert sc.get("video_prompt") is None


# 4. test_video_recommended_requires_image_first
def test_video_recommended_requires_image_first(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    with open(prod_dir / "visual_manifest_v9_3_1.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    vid_scenes = [s for s in data["scenes"] if s["visual_mode"] == "VIDEO_RECOMMENDED"]
    assert len(vid_scenes) > 0
    for sc in vid_scenes:
        # Must have image first for I2V
        assert sc.get("image_file") is not None
        assert sc.get("image_prompt") is not None
        assert sc.get("video_file") is not None
        assert sc.get("video_prompt") is not None


# 5. test_video_prompt_only_for_video_recommended
def test_video_prompt_only_for_video_recommended(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    with open(prod_dir / "visual_manifest_v9_3_1.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for sc in data["scenes"]:
        if sc["visual_mode"] == "IMAGE_ONLY":
            assert sc.get("video_prompt") is None
        elif sc["visual_mode"] == "VIDEO_RECOMMENDED":
            assert sc.get("video_prompt") is not None


# 6. test_critical_reveal_not_auto_video
def test_critical_reveal_not_auto_video():
    adapter = ProductionAdapter()
    scenes = [{
        "scene_id": "SC_REV",
        "story_beat": "Trích lục khai tử xác nhận người cha đã qua đời 14 năm trước.",
        "is_reveal": True,
        "delivery_profile": "REVEAL",
    }]
    classified = adapter.classify_scenes(scenes)
    # Critical reveal preferred IMAGE_ONLY with slow push & text overlay
    assert classified[0]["visual_mode"] == "IMAGE_ONLY"
    assert classified[0]["image_motion"]["type"] == "SLOW_PUSH"


# 7. test_document_prefers_image
def test_document_prefers_image():
    adapter = ProductionAdapter()
    scenes = [{
        "scene_id": "SC_DOC",
        "story_beat": "Bản sao kê ngân hàng và cuốn sổ ghi chép cũ.",
        "is_reveal": False,
        "delivery_profile": "NORMAL",
    }]
    classified = adapter.classify_scenes(scenes)
    assert classified[0]["visual_mode"] == "IMAGE_ONLY"


# 8. test_character_interaction_prefers_video
def test_character_interaction_prefers_video():
    adapter = ProductionAdapter()
    scenes = [{
        "scene_id": "SC_CONF",
        "story_beat": "Hai nhân vật đối chất gay gắt và ôm chầm lấy nhau khóc nức nở.",
        "is_reveal": False,
        "delivery_profile": "NORMAL",
    }]
    classified = adapter.classify_scenes(scenes, video_budget="BALANCED")
    assert classified[0]["visual_mode"] == "VIDEO_RECOMMENDED"
    assert classified[0]["video_priority"] in ["P1", "P2"]


# 9. test_emotional_climax_prefers_video
def test_emotional_climax_prefers_video():
    adapter = ProductionAdapter()
    scenes = [{
        "scene_id": "SC_CLIMAX",
        "story_beat": "Chồng ôm chặt vợ nghẹn ngào trong sự tha thứ và nước mắt.",
        "is_reveal": False,
        "delivery_profile": "NORMAL",
    }]
    classified = adapter.classify_scenes(scenes)
    assert classified[0]["visual_mode"] == "VIDEO_RECOMMENDED"
    assert classified[0]["video_priority"] == "P1"


# 10. test_video_hard_cap
def test_video_hard_cap():
    adapter = ProductionAdapter()
    # 20 scenes all with confrontation/action
    scenes = [
        {"scene_id": f"SC_{i:03d}", "story_beat": f"Đối chất gay gắt và tranh cãi {i}"}
        for i in range(20)
    ]
    classified = adapter.classify_scenes(scenes, video_budget="RICH")
    summary = adapter.get_production_summary(classified, video_budget="RICH")
    # Video ratio must not exceed 40% hard cap
    assert summary["video_ratio_pct"] <= 40.0


# 11. test_video_priority
def test_video_priority():
    adapter = ProductionAdapter()
    scenes = [
        {"scene_id": "SC_001", "story_beat": "Lá thư của Lan mở đầu bằng đối chất gay gắt"},
        {"scene_id": "SC_002", "story_beat": "Bước đi lần theo dấu vết tìm kiếm manh mối"},
    ]
    classified = adapter.classify_scenes(scenes)
    for sc in classified:
        if sc["visual_mode"] == "VIDEO_RECOMMENDED":
            assert sc["video_priority"] in ["P1", "P2", "P3"]


# 12. test_image_motion_metadata
def test_image_motion_metadata():
    adapter = ProductionAdapter()
    scenes = [{"scene_id": "SC_001", "story_beat": "Góc phố vắng lặng buổi chiều tà."}]
    classified = adapter.classify_scenes(scenes)
    assert "image_motion" in classified[0]
    motion = classified[0]["image_motion"]
    assert motion["type"] in ["SLOW_PUSH", "PAN_LEFT", "PAN_RIGHT", "ZOOM_OUT", "STATIC"]
    assert "speed" in motion


# 13. test_csv_image_only_blank_video_prompt(tmp_path, mock_script_and_bible):
def test_csv_image_only_blank_video_prompt(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    csv_path = prod_dir / "visual_prompts_v9_3_1.csv"
    assert csv_path.exists()

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["visual_mode"] == "IMAGE_ONLY":
                assert row["video_file"] == ""
                assert row["video_prompt"] == ""
            elif row["visual_mode"] == "VIDEO_RECOMMENDED":
                assert row["video_file"] != ""
                assert row["video_prompt"] != ""


# 14. test_visual_override_does_not_mutate_script
def test_visual_override_does_not_mutate_script(mock_script_and_bible):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter()
    scenes = adapter._generate_visual_scenes(script, bible)
    manifest = {"manifest_version": "9.3.1", "scenes": scenes, "video_budget": "BALANCED"}

    orig_script_text = script.segments[0].text
    adapter.override_scene_mode(manifest, "SC_001", "VIDEO_RECOMMENDED")

    # Script text remains 100% identical
    assert script.segments[0].text == orig_script_text


# 15. test_visual_override_does_not_mutate_audio(mock_script_and_bible):
def test_visual_override_does_not_mutate_audio(mock_script_and_bible):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter()
    scenes = adapter._generate_visual_scenes(script, bible)
    manifest = {"manifest_version": "9.3.1", "scenes": scenes, "video_budget": "BALANCED"}

    adapter.override_scene_mode(manifest, "SC_001", "IMAGE_ONLY")
    # Verify no audio engine or segments changed
    assert script.host["voice"] == "Binh"
    assert script.segments[0].speed == 1.0


# 16. test_ep001_images_preserved
def test_ep001_images_preserved():
    rep_file = Path("reports/ep001_v9_3_1_visual_migration.json")
    if not rep_file.exists():
        migrate_ep001_to_v9_3_1(Path("projects/sau_canh_cua_ep01_v9_3_manual_visual"))

    with open(rep_file, "r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["total_scenes"] == 45
    assert rep["existing_images_preserved"] == 45
    assert rep["image_regeneration_count"] == 0


# 17. test_ep001_migration_no_generation
def test_ep001_migration_no_generation():
    rep_file = Path("reports/ep001_v9_3_1_visual_migration.json")
    if not rep_file.exists():
        migrate_ep001_to_v9_3_1(Path("projects/sau_canh_cua_ep01_v9_3_manual_visual"))

    with open(rep_file, "r", encoding="utf-8") as f:
        rep = json.load(f)

    assert rep["video_generation_requests"] == 0
    assert rep["flow_requests"] == 0


# 18. test_adapter_outputs_v9_3_1
def test_adapter_outputs_v9_3_1(mock_script_and_bible, tmp_path):
    script, bible = mock_script_and_bible
    adapter = ProductionAdapter(episodes_root=tmp_path)
    prod_dir = adapter.adapt_to_v9_3_project(script, bible)

    assert (prod_dir / "episode_v9_3_1.json").exists()
    assert (prod_dir / "visual_manifest_v9_3_1.json").exists()
    assert (prod_dir / "visual_prompts_v9_3_1.csv").exists()
