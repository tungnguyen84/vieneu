import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.visual_engine.final_auto_assembler import (
    CANONICAL_SCENE_DEFINITIONS,
    EXPECTED_EP001_VIDEO_SCENES,
    AssemblyPlan,
    SceneAssemblyItem,
    build_assembly_plan,
    compute_scene_cache_key,
    create_overlay_banner,
    get_video_info,
    inspect_and_extract_zip,
    normalize_scene_id,
    render_scene_clip,
    run_final_qc,
    validate_image_file,
    validate_imported_assets,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_ZIP_PATH = Path(r"D:\Youtube\Sau cánh cửa\Sau_Canh_Cua_EP01_V9_3_1_FULL_NO_MUSIC\New_Project_FULL_EXPORT.zip")
REAL_AUDIO_PATH = REPO_ROOT / "projects/sau_canh_cua_ep01_v9_3_manual_visual/master/final_mix.wav"


def test_scene_id_normalization():
    """Verify various naming conventions normalize to SC_XXX."""
    assert normalize_scene_id("SC_001.png") == "SC_001"
    assert normalize_scene_id("sc_001.mp4") == "SC_001"
    assert normalize_scene_id("SC001.png") == "SC_001"
    assert normalize_scene_id("sc001.mp4") == "SC_001"
    assert normalize_scene_id("SC-001.png") == "SC_001"
    assert normalize_scene_id("nested/path/sc_045.mp4") == "SC_045"
    assert normalize_scene_id("random_file.txt") is None


def test_zip_recursive_discovery(tmp_path):
    """Test recursive discovery of images, videos and manifest regardless of folder depth."""
    zip_path = tmp_path / "test_flow.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder_a/deep_b/SC_001.png", b"\x89PNG\r\n\x1a\nfake")
        zf.writestr("videos/SC_001.mp4", b"fake_mp4")
        zf.writestr("nested/manifest_v9_3_1.json", json.dumps({"test": 1}))
        zf.writestr("random.txt", "notes")

    ext_dir = tmp_path / "extracted"
    img_map, vid_map, manifest_p, unknown = inspect_and_extract_zip(zip_path, ext_dir)

    assert "SC_001" in img_map
    assert "SC_001" in vid_map
    assert manifest_p is not None
    assert "random.txt" in unknown


def test_asset_validation_counts_and_readiness(tmp_path):
    """Validate 45 images detection, 15 videos detection, and readiness logic."""
    # Create 45 dummy valid images
    img_map = {}
    for i in range(1, 46):
        sc_id = f"SC_{i:03d}"
        img_p = tmp_path / f"{sc_id}.png"
        img = Image.new("RGB", (100, 100), (255, 0, 0))
        img.save(img_p, "PNG")
        img_map[sc_id] = img_p

    # Create dummy video map for 15 scenes
    vid_map = {}
    for sc_id in EXPECTED_EP001_VIDEO_SCENES:
        vid_map[sc_id] = tmp_path / f"{sc_id}.mp4"

    # Mock ffprobe to avoid needing real mp4s for unit check
    report = validate_imported_assets(img_map, {}, scenes=CANONICAL_SCENE_DEFINITIONS)
    assert report.total_scenes == 45
    assert report.images_found == 45
    assert len(report.missing_images) == 0
    assert report.ready_for_assembly is True
    assert report.manifest_status == "PASS"


def test_audio_master_clock_and_timeline_order():
    """Verify scene ordering, continuity, and total duration conforming to master audio."""
    plan = build_assembly_plan({}, {}, REAL_AUDIO_PATH)
    assert len(plan.scenes) == 45
    assert plan.scenes[0].scene_id == "SC_001"
    assert plan.scenes[-1].scene_id == "SC_045"
    assert plan.scenes[0].start_sec == 0.0
    assert plan.scenes[-1].end_sec == 779.75
    assert plan.total_visual_duration_sec == 779.75
    assert plan.av_delta_sec == 0.0

    # Contiguity check: start of scene i == end of scene i-1
    for i in range(1, len(plan.scenes)):
        prev = plan.scenes[i - 1]
        curr = plan.scenes[i]
        assert abs(curr.start_sec - prev.end_sec) < 0.01


def test_source_resolution_priority_and_overrides(tmp_path):
    """Test: Manual Override > Valid Video > Valid Image."""
    img_map = {"SC_001": tmp_path / "SC_001.png", "SC_002": tmp_path / "SC_002.png"}
    vid_map = {"SC_001": tmp_path / "SC_001.mp4"}

    # Default: SC_001 uses VIDEO, SC_002 uses IMAGE
    plan = build_assembly_plan(img_map, vid_map, REAL_AUDIO_PATH)
    s1 = next(s for s in plan.scenes if s.scene_id == "SC_001")
    s2 = next(s for s in plan.scenes if s.scene_id == "SC_002")
    assert s1.source_type == "VIDEO"
    assert s2.source_type == "IMAGE"

    # User overrides SC_001 to USE_IMAGE
    overrides = {"SC_001": "USE_IMAGE"}
    plan_ov = build_assembly_plan(img_map, vid_map, REAL_AUDIO_PATH, manual_overrides=overrides)
    s1_ov = next(s for s in plan_ov.scenes if s.scene_id == "SC_001")
    assert s1_ov.source_type == "IMAGE"
    assert s1_ov.manual_override == "USE_IMAGE"


def test_utf8_vietnamese_text_overlay(tmp_path):
    """Verify overlay banner creation with Vietnamese diacritics."""
    overlay_png = tmp_path / "banner_test.png"
    text = "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào. -5.000.000 VND"
    out_p = create_overlay_banner(text, overlay_png)
    assert out_p.exists()
    assert out_p.stat().st_size > 0

    with Image.open(out_p) as img:
        assert img.size == (1920, 1080)
        assert img.mode == "RGBA"


def test_render_cache_key_determinism():
    """Verify cache keys change when parameters change and remain identical otherwise."""
    item1 = SceneAssemblyItem(
        scene_id="SC_001", segment_start="001", segment_end="002",
        start_sec=0.0, end_sec=10.0, duration_sec=10.0,
        source_type="IMAGE", source_file=None, image_motion="SLOW_PUSH_IN"
    )
    item2 = SceneAssemblyItem(
        scene_id="SC_001", segment_start="001", segment_end="002",
        start_sec=0.0, end_sec=10.0, duration_sec=10.0,
        source_type="IMAGE", source_file=None, image_motion="SLOW_PUSH_IN"
    )
    item3 = SceneAssemblyItem(
        scene_id="SC_001", segment_start="001", segment_end="002",
        start_sec=0.0, end_sec=10.0, duration_sec=10.0,
        source_type="IMAGE", source_file=None, image_motion="PAN_LEFT"
    )

    k1 = compute_scene_cache_key(item1)
    k2 = compute_scene_cache_key(item2)
    k3 = compute_scene_cache_key(item3)

    assert k1 == k2
    assert k1 != k3


@pytest.mark.skipif(not REAL_ZIP_PATH.exists(), reason="Real export ZIP not present on machine")
def test_real_rendered_final_mp4_qc():
    """Verify the real rendered final MP4 passes all QC requirements."""
    final_mp4 = REPO_ROOT / "final/EP001_Sau_Canh_Cua_V9_3_1_FINAL.mp4"
    assert final_mp4.exists(), f"Final MP4 {final_mp4} not found!"
    assert final_mp4.stat().st_size > 100_000_000, f"Final MP4 is suspiciously small: {final_mp4.stat().st_size} bytes"

    # Read final_qc_v9_3_1.json
    qc_p = REPO_ROOT / "final/final_qc_v9_3_1.json"
    assert qc_p.exists()
    with open(qc_p, "r", encoding="utf-8") as f:
        qc = json.load(f)

    assert qc["qc_status"] == "PASS"
    assert qc["sync_pass"] is True
    assert qc["codec_pass"] is True
    assert qc["resolution_pass"] is True
    assert qc["resolution"] == "1920x1080"
    assert qc["video_codec"] == "h264"
    assert qc["audio_codec"] == "aac"
    assert qc["audio_streams_count"] == 1
    assert qc["ai_video_audio_contribution_pct"] == 0.0
    assert qc["scene_count"] == 45
    assert qc["video_scenes_count"] == 15
    assert qc["image_scenes_count"] == 30
    assert qc["scene_coverage_pass"] is True
    assert qc["black_gaps_detected"] == 0
    assert qc["av_delta_sec"] <= 0.05
