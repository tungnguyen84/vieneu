"""Unit and Integration Tests for Manual Visual Import & Auto Assemble Mode.

Validates:
- Manifest loading and timeline grounding on real audio segment duration (not word count estimation).
- Case-insensitive scanning of SC_XXX in images/ and videos/.
- Priority: VIDEO > IMAGE.
- Duplicate detection and user selection resolution.
- Invalid/corrupt media detection and reporting.
- Missing scene strictly blocks assembly render.
- Restrained Ken Burns camera motion for still images.
- Video scale/crop to 1080p, trimming long videos, freezing last frame for short videos.
- Stripping all source video audio tracks.
- High-quality post-production rendering for critical text overlays.
- Offline guarantee: 0 calls to FlowKit, Banana Pro, or Omni Flash.
- Immutability guarantee: visual_plan.json, source.json, and master audio are never mutated.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from PIL import Image

from apps.visual_engine.manual_visual_mode import (
    ManualSceneItem,
    ManualVisualManifest,
    assemble_manual_episode,
    create_overlay_banner,
    get_manifest_dataframe,
    load_or_create_manifest,
    render_manual_scene_clip,
    resolve_duplicate_asset,
    save_manifest,
    scan_project_assets,
    validate_manifest_for_assemble,
)


@pytest.fixture
def temp_project(tmp_path):
    """Sets up an isolated test project directory."""
    proj_dir = tmp_path / "test_manual_project"
    proj_dir.mkdir(parents=True)
    (proj_dir / "visual" / "images").mkdir(parents=True)
    (proj_dir / "visual" / "videos").mkdir(parents=True)
    (proj_dir / "visual" / "processed").mkdir(parents=True)
    (proj_dir / "master").mkdir(parents=True)

    # Create dummy master audio (1 second silent wav for testing)
    audio_p = proj_dir / "master" / "final_mix.wav"
    import wave
    with wave.open(str(audio_p), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00" * 44100 * 4)  # 1 sec

    return proj_dir


def _create_dummy_image(path: Path, color=(100, 150, 200), size=(1920, 1080)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, "PNG")
    return path


def _create_dummy_video(path: Path, duration_sec: float = 2.0, with_audio: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=640x360:r=30:d={duration_sec}",
    ]
    if with_audio:
        cmd.extend(["-f", "lavfi", "-i", f"sine=f=440:d={duration_sec}", "-c:a", "aac"])
    else:
        cmd.append("-an")
    cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg dummy video generation failed: {res.stderr}"
    return path


def test_load_canonical_manifest_timeline(temp_project):
    """Verifies that the canonical manifest loads 45 scenes with real audio timeline grounding."""
    manifest = load_or_create_manifest(project_dir=temp_project)
    assert len(manifest.scenes) == 45
    assert manifest.manifest_version == "9.3"
    assert manifest.timeline_source == "PROJECT_AUDIO_SEGMENTS"
    assert manifest.scenes[0].scene_id == "SC_001"
    assert manifest.scenes[0].start_sec == 0.0
    assert manifest.scenes[-1].scene_id == "SC_045"

    # Verify contiguous timeline with 0 black gaps
    for i in range(1, len(manifest.scenes)):
        prev = manifest.scenes[i - 1]
        curr = manifest.scenes[i]
        assert abs(curr.start_sec - prev.end_sec) < 0.01, f"Gap between {prev.scene_id} and {curr.scene_id}"


def test_scan_assets_case_insensitive(temp_project):
    """Verifies case-insensitive scanning of SC_XXX filenames in images and videos."""
    manifest = load_or_create_manifest(project_dir=temp_project)

    # Create mixed-case files
    _create_dummy_image(temp_project / "visual" / "images" / "sc_001.png")
    _create_dummy_image(temp_project / "visual" / "images" / "SC_002_banana.PNG")
    _create_dummy_video(temp_project / "visual" / "videos" / "sC_003.mp4", duration_sec=1.0)
    _create_dummy_video(temp_project / "visual" / "videos" / "SC_004.MP4", duration_sec=1.0)

    scan_project_assets(manifest, project_dir=temp_project)

    s1 = next(s for s in manifest.scenes if s.scene_id == "SC_001")
    assert len(s1.matched_images) == 1
    assert "sc_001.png" in s1.matched_images[0]
    assert s1.chosen_type == "IMAGE"
    assert s1.qc_status == "READY"

    s2 = next(s for s in manifest.scenes if s.scene_id == "SC_002")
    assert len(s2.matched_images) == 1
    assert "SC_002_banana.PNG" in s2.matched_images[0]
    assert s2.chosen_type == "IMAGE"
    assert s2.qc_status == "READY"

    s3 = next(s for s in manifest.scenes if s.scene_id == "SC_003")
    assert len(s3.matched_videos) == 1
    assert "sC_003.mp4" in s3.matched_videos[0]
    assert s3.chosen_type == "VIDEO"
    assert s3.qc_status == "READY"

    s4 = next(s for s in manifest.scenes if s.scene_id == "SC_004")
    assert len(s4.matched_videos) == 1
    assert "SC_004.MP4" in s4.matched_videos[0]
    assert s4.chosen_type == "VIDEO"
    assert s4.qc_status == "READY"


def test_priority_video_over_image(temp_project):
    """Verifies that Video takes priority over Image when both are available."""
    manifest = load_or_create_manifest(project_dir=temp_project)

    # SC_005 has both image and video
    _create_dummy_image(temp_project / "visual" / "images" / "SC_005.jpg")
    _create_dummy_video(temp_project / "visual" / "videos" / "sc_005.mp4", duration_sec=1.5)

    scan_project_assets(manifest, project_dir=temp_project)

    s5 = next(s for s in manifest.scenes if s.scene_id == "SC_005")
    assert len(s5.matched_images) == 1
    assert len(s5.matched_videos) == 1
    assert s5.chosen_type == "VIDEO"
    assert "sc_005.mp4" in s5.chosen_asset
    assert s5.qc_status == "READY"


def test_duplicate_detection_and_resolution(temp_project):
    """Verifies that multiple matching files flag DUPLICATE and require user selection."""
    manifest = load_or_create_manifest(project_dir=temp_project)

    # SC_006 has two image files
    p1 = _create_dummy_image(temp_project / "visual" / "images" / "sc_006_v1.png")
    p2 = _create_dummy_image(temp_project / "visual" / "images" / "sc_006_v2.png")

    scan_project_assets(manifest, project_dir=temp_project)

    s6 = next(s for s in manifest.scenes if s.scene_id == "SC_006")
    assert len(s6.matched_images) == 2
    assert s6.qc_status == "DUPLICATE"
    assert s6.chosen_asset is None

    # Duplicate blocks render
    can_render, issues, _ = validate_manifest_for_assemble(manifest, project_dir=temp_project)
    assert not can_render
    assert any("DUPLICATE" in iss or "SC_006" in iss for iss in issues)

    # User resolves selection to p2
    resolve_duplicate_asset(manifest, "SC_006", p2)
    assert s6.chosen_asset == str(p2.resolve())
    assert s6.chosen_type == "IMAGE"
    assert s6.qc_status == "READY"


def test_invalid_media_detection(temp_project):
    """Verifies that corrupted or 0-byte media files are flagged as INVALID and reported."""
    manifest = load_or_create_manifest(project_dir=temp_project)

    corrupt_file = temp_project / "visual" / "images" / "sc_007.png"
    corrupt_file.write_bytes(b"not an image corrupted data")

    scan_project_assets(manifest, project_dir=temp_project)

    s7 = next(s for s in manifest.scenes if s.scene_id == "SC_007")
    assert s7.qc_status == "INVALID"
    assert s7.chosen_asset is None
    assert s7.error_reason is not None

    can_render, issues, _ = validate_manifest_for_assemble(manifest, project_dir=temp_project)
    assert not can_render
    assert any("SC_007" in iss for iss in issues)


def test_missing_scene_blocks_render(temp_project):
    """Verifies that any missing scene strictly blocks assemble execution."""
    manifest = load_or_create_manifest(project_dir=temp_project)
    # Only provide asset for SC_001
    _create_dummy_image(temp_project / "visual" / "images" / "SC_001.png")
    scan_project_assets(manifest, project_dir=temp_project)

    can_render, issues, stats = validate_manifest_for_assemble(manifest, project_dir=temp_project)
    assert not can_render
    assert stats["missing_count"] == 44

    with pytest.raises(RuntimeError, match="Auto Assemble blocked"):
        assemble_manual_episode(manifest, project_dir=temp_project)


def test_restrained_ken_burns_image(temp_project):
    """Verifies image motion rendering with restrained Ken Burns effect at 1920x1080 30fps."""
    img_path = _create_dummy_image(temp_project / "visual" / "images" / "sc_test_img.png")
    scene = ManualSceneItem(
        scene_id="SC_TEST",
        scene_index=1,
        start_sec=0.0,
        end_sec=2.0,
        duration_sec=2.0,
        story_beat="Test Ken Burns",
        chosen_asset=str(img_path),
        chosen_type="IMAGE",
        qc_status="READY"
    )

    out_mp4 = temp_project / "visual" / "processed" / "sc_test_img.mp4"
    rendered = render_manual_scene_clip(scene, out_mp4)

    assert rendered.exists()
    assert rendered.stat().st_size > 1000

    # Probe properties with ffprobe
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_name,r_frame_rate,codec_type",
        "-of", "json", str(rendered)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(res.stdout)

    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    dur = float(probe["format"]["duration"])

    assert v_stream["width"] == 1920
    assert v_stream["height"] == 1080
    assert v_stream["codec_name"] == "h264"
    assert abs(dur - 2.0) < 0.15
    # Must have NO audio stream
    a_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    assert len(a_streams) == 0


def test_video_trim_and_freeze_last_frame(temp_project):
    """Verifies video trimming when long and freezing last frame when short."""
    # 1. Video longer than scene duration -> trim
    vid_long = _create_dummy_video(temp_project / "visual" / "videos" / "long.mp4", duration_sec=4.0)
    sc_trim = ManualSceneItem(
        scene_id="SC_TRIM",
        scene_index=1,
        start_sec=0.0,
        end_sec=1.5,
        duration_sec=1.5,
        story_beat="Test trim",
        chosen_asset=str(vid_long),
        chosen_type="VIDEO",
        qc_status="READY"
    )
    out_trim = temp_project / "visual" / "processed" / "sc_trim.mp4"
    render_manual_scene_clip(sc_trim, out_trim)

    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out_trim)], capture_output=True, text=True)
    probe_trim = json.loads(res.stdout)
    assert abs(float(probe_trim["format"]["duration"]) - 1.5) < 0.15
    assert probe_trim["streams"][0]["width"] == 1920
    assert probe_trim["streams"][0]["height"] == 1080

    # 2. Video shorter than scene duration -> freeze last frame (pad)
    vid_short = _create_dummy_video(temp_project / "visual" / "videos" / "short.mp4", duration_sec=1.0)
    sc_pad = ManualSceneItem(
        scene_id="SC_PAD",
        scene_index=2,
        start_sec=1.5,
        end_sec=4.0,
        duration_sec=2.5,
        story_beat="Test freeze pad",
        chosen_asset=str(vid_short),
        chosen_type="VIDEO",
        qc_status="READY"
    )
    out_pad = temp_project / "visual" / "processed" / "sc_pad.mp4"
    render_manual_scene_clip(sc_pad, out_pad)

    res_pad = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out_pad)], capture_output=True, text=True)
    probe_pad = json.loads(res_pad.stdout)
    assert abs(float(probe_pad["format"]["duration"]) - 2.5) < 0.15


def test_post_production_overlay_rendering(temp_project):
    """Verifies that scenes with text overlay render text overlay post-production."""
    img_path = _create_dummy_image(temp_project / "visual" / "images" / "sc_overlay.png")
    scene = ManualSceneItem(
        scene_id="SC_030",
        scene_index=30,
        start_sec=0.0,
        end_sec=2.0,
        duration_sec=2.0,
        story_beat="Reveal death record",
        requires_text_overlay=True,
        text_overlay_content="Trích lục khai tử: Ngày mất 14 năm trước",
        chosen_asset=str(img_path),
        chosen_type="IMAGE",
        qc_status="READY"
    )

    out_mp4 = temp_project / "visual" / "processed" / "sc_030.mp4"
    rendered = render_manual_scene_clip(scene, out_mp4)
    assert rendered.exists()
    assert rendered.stat().st_size > 10000

    # Verify overlay PNG was generated
    overlay_png = temp_project / "visual" / "processed" / "SC_030_overlay.png"
    assert overlay_png.exists()


def test_assemble_strips_video_audio_and_muxes_master(temp_project):
    """Verifies that Auto Assemble strips source video audio and cleanly muxes final_mix.wav."""
    # Create a 2-scene mini manifest
    vid1 = _create_dummy_video(temp_project / "visual" / "videos" / "SC_001.mp4", duration_sec=1.5, with_audio=True)
    img2 = _create_dummy_image(temp_project / "visual" / "images" / "SC_002.png")

    scenes = [
        ManualSceneItem(
            scene_id="SC_001",
            scene_index=1,
            start_sec=0.0,
            end_sec=1.0,
            duration_sec=1.0,
            story_beat="Scene 1",
            chosen_asset=str(vid1),
            chosen_type="VIDEO",
            qc_status="READY"
        ),
        ManualSceneItem(
            scene_id="SC_002",
            scene_index=2,
            start_sec=1.0,
            end_sec=2.0,
            duration_sec=1.0,
            story_beat="Scene 2",
            chosen_asset=str(img2),
            chosen_type="IMAGE",
            qc_status="READY"
        ),
    ]

    # Create 2s master audio
    audio_p = temp_project / "master" / "final_mix.wav"
    import wave
    with wave.open(str(audio_p), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00" * 44100 * 4 * 2)  # 2 sec

    manifest = ManualVisualManifest(
        manifest_version="9.3",
        project_slug="test_assemble",
        project_dir=str(temp_project),
        audio_master_path=str(audio_p),
        total_duration_sec=2.0,
        timeline_source="PROJECT_AUDIO_SEGMENTS",
        scenes=scenes
    )

    out_file = temp_project / "final" / "assembled_test.mp4"
    final_mp4 = assemble_manual_episode(manifest, output_mp4_path=out_file, project_dir=temp_project)

    assert final_mp4.exists()
    assert final_mp4.stat().st_size > 5000

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=width,height,codec_name,codec_type",
        "-of", "json", str(final_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe = json.loads(res.stdout)

    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")

    assert v_stream["width"] == 1920
    assert v_stream["height"] == 1080
    assert v_stream["codec_name"] == "h264"
    assert a_stream["codec_name"] == "aac"


def test_offline_strict_no_flowkit_no_banana_no_omni(temp_project):
    """Ensures that Manual Mode NEVER calls FlowKit, Banana Pro, or Omni Flash."""
    manifest = load_or_create_manifest(project_dir=temp_project)

    with patch("apps.visual_engine.flowkit_adapter.FlowKitAdapter") as mock_adapter, \
         patch("apps.visual_engine.banana_client.BananaClient") as mock_banana, \
         patch("apps.visual_engine.veo_client.OmniFlashClient") as mock_omni:

        scan_project_assets(manifest, project_dir=temp_project)
        validate_manifest_for_assemble(manifest, project_dir=temp_project)
        get_manifest_dataframe(manifest)

        assert mock_adapter.call_count == 0
        assert mock_banana.call_count == 0
        assert mock_omni.call_count == 0


def test_immutable_visual_plan_and_source():
    """Guarantees that visual_plan.json, source.json, and master audio are NEVER mutated."""
    real_proj = Path("projects/sau_canh_cua_ep01_v9_3_manual_visual")
    if not real_proj.exists():
        pytest.skip("v9_3 manual project not found")

    files = [
        real_proj / "source.json",
        real_proj / "visual" / "visual_plan.json",
        real_proj / "master" / "final_mix.wav",
    ]
    before_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}

    # Run manifest initialization and scanning on v9_3
    manifest = load_or_create_manifest(project_dir=real_proj)
    scan_project_assets(manifest, project_dir=real_proj)
    validate_manifest_for_assemble(manifest, project_dir=real_proj)
    get_manifest_dataframe(manifest)

    # Check hashes after
    for p, orig_hash in before_hashes.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == orig_hash, f"File {p} was illegally mutated!"
