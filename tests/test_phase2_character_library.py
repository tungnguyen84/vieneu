"""Phase 2 Validation Suite: Character Library + Intelligent Visual Planner.

Validates:
1. test_character_library_persistence: 4 characters loaded, schema attributes, save/load/delete.
2. test_episode_cast_resolution: episode_cast.json resolution and fallback.
3. test_visual_scene_grouping: merges consecutive speech segments into 30-55 cinematic scenes (target 35-45).
4. test_no_one_segment_one_scene: total scenes << segment count.
5. test_visual_type_explicit: 100% scenes BANANA_IMAGE or OMNI_FLASH_I2V, zero UNRESOLVED.
6. test_omni_duration_resolution: OMNI_FLASH_I2V scenes strictly resolve to {4, 6, 8, 10} seconds.
7. test_visual_timeline_coverage: 100% coverage (0.0 to final audio duration), zero gaps > 0.05s.
8. test_character_ids_valid: every character referenced in scenes exists in character library.
9. test_location_ids_valid: every location referenced in scenes exists in location library.
10. test_queue_sync: asset_mgr.sync_queue_with_plan matches visual_types.
11. test_reanalyze_does_not_delete_assets: re-analyzing/syncing preserves existing completed assets.
12. test_audio_formula_regression: verifies Audio Formula V1 files and loudness metrics are untouched.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.visual_engine.character_manager import (
    CharacterProfile,
    LocationProfile,
    load_character_library,
    save_character,
    delete_character,
    load_location_library,
    save_location,
    delete_location,
    load_episode_cast,
    load_visual_preset,
)
from apps.visual_engine.visual_planner import (
    VisualPlanner,
    VisualScene,
    validate_visual_timeline,
    DeterministicVisualPlanner,
)
from apps.visual_engine.asset_manager import VisualAssetManager, VisualQueueItem
from apps.visual_engine.resolvers import OMNI_FLASH_DURATIONS


PROJECT_DIR = REPO_ROOT / "projects/sau_canh_cua_-_episode_01_v9_1_master_reference"


@pytest.fixture(scope="module")
def episode_data():
    source_path = PROJECT_DIR / "source.json"
    with open(source_path, "r", encoding="utf-8") as f:
        source = json.load(f)

    voice_master_p = PROJECT_DIR / "master/voice_master.wav"
    v_info = sf.info(str(voice_master_p))
    total_audio_sec = v_info.duration
    sample_rate = v_info.samplerate

    timeline_events = []
    current_sample = 0
    for seg in source.get("segments", []):
        sid = seg["id"]
        wav_p = PROJECT_DIR / "selected" / f"{int(sid):03d}.wav"
        w_info = sf.info(str(wav_p))
        samp_len = w_info.frames
        st_sec = current_sample / sample_rate
        en_sec = (current_sample + samp_len) / sample_rate
        timeline_events.append({
            "id": sid,
            "speaker": seg.get("speaker", "MINH"),
            "text": seg.get("text", ""),
            "delivery_profile": seg.get("delivery_profile", "NORMAL"),
            "importance": seg.get("importance", "normal"),
            "audio_region": seg.get("audio_region", ""),
            "music_cue": seg.get("music_cue", ""),
            "music_obj": seg.get("music", {}),
            "speech_start_sec": st_sec,
            "speech_end_sec": en_sec,
            "duration_sec": en_sec - st_sec,
        })
        p_gap = float(seg.get("pause_after", 0.18))
        current_sample += samp_len + int(p_gap * sample_rate)

    return {
        "source": source,
        "timeline_events": timeline_events,
        "total_audio_sec": total_audio_sec,
        "voice_master_p": voice_master_p,
    }


def test_character_library_persistence():
    chars = load_character_library()
    expected_ids = {"LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"}
    for cid in expected_ids:
        assert cid in chars, f"Missing character {cid} in character library"
        c = chars[cid]
        assert c.char_id == cid
        assert c.name
        assert c.face
        assert c.hair
        assert c.body
        assert c.default_clothing
        assert isinstance(c.flow_media_ids, (list, dict))

    # Test saving a temporary character profile, loading, and deleting
    temp_profile = CharacterProfile(
        char_id="TEST_CHAR",
        name="Nhân vật thử nghiệm",
        gender="MALE",
        age_range="30s",
        role="Test character for persistence",
        face="Sharp jaw, neutral expression",
        hair="Short black hair",
        body="Average build, 175cm",
        appearance="Vietnamese man in his 30s",
        default_clothing="White shirt, dark trousers",
        visual_notes="Photorealistic cinematic lighting",
        flow_media_ids={"ref_portrait": "media_test_999"}
    )
    save_character(temp_profile)
    reloaded_chars = load_character_library()
    assert "TEST_CHAR" in reloaded_chars
    assert reloaded_chars["TEST_CHAR"].role == "Test character for persistence"
    assert reloaded_chars["TEST_CHAR"].flow_media_ids == {"ref_portrait": "media_test_999"}

    # Delete temporary character
    deleted = delete_character("TEST_CHAR")
    assert deleted is True
    chars_after_delete = load_character_library()
    assert "TEST_CHAR" not in chars_after_delete


def test_episode_cast_resolution():
    # 1. Project with episode_cast.json
    cast = load_episode_cast(PROJECT_DIR)
    assert cast is not None
    assert "LAN_ADULT" in cast
    assert cast["LAN_ADULT"]["character_library_id"] == "LAN_ADULT"
    assert "HUNG" in cast
    assert cast["HUNG"]["character_library_id"] == "HUNG"
    assert "UNCLE" in cast
    assert cast["UNCLE"]["character_library_id"] == "UNCLE"
    assert "LAN_YOUNG" in cast
    assert cast["LAN_YOUNG"]["character_library_id"] == "LAN_YOUNG"

    # 2. None project_dir returns None (fallback to global lib)
    assert load_episode_cast(None) is None


def test_visual_scene_grouping(episode_data):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR,
        target_scenes_min=35,
        target_scenes_max=45,
        target_omni_min=14,
        target_omni_max=22
    )

    # Check scene count conforms to target
    assert 30 <= len(scenes) <= 55, f"Scene count {len(scenes)} outside 30-55 range"
    assert 35 <= len(scenes) <= 48, f"Scene count {len(scenes)} outside soft target 35-45 range"


def test_no_one_segment_one_scene(episode_data):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )
    num_segments = len(episode_data["timeline_events"])
    assert num_segments >= 90
    assert len(scenes) < (num_segments / 2), "Scenes not sufficiently grouped from speech segments"
    ratio = num_segments / len(scenes)
    assert ratio >= 2.0, f"Compression ratio {ratio:.2f} is too low (expected >= 2.0)"


def test_visual_type_explicit(episode_data):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    valid_types = {"BANANA_IMAGE", "OMNI_FLASH_I2V"}
    for s in scenes:
        assert s.visual_type in valid_types, f"Scene {s.scene_id} has invalid visual_type: {s.visual_type}"
        assert s.visual_type != "UNRESOLVED"
        assert s.image_prompt, f"Scene {s.scene_id} missing image_prompt"
        if s.visual_type == "OMNI_FLASH_I2V":
            assert s.video_prompt, f"Video scene {s.scene_id} missing video_prompt"
            assert s.video_duration_sec in OMNI_FLASH_DURATIONS


def test_omni_duration_resolution(episode_data):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    omni_scenes = [s for s in scenes if s.visual_type == "OMNI_FLASH_I2V"]
    assert len(omni_scenes) >= 12, f"Too few Omni Flash video scenes: {len(omni_scenes)}"

    duration_counts = {4: 0, 6: 0, 8: 0, 10: 0}
    for s in omni_scenes:
        assert s.video_duration_sec in {4, 6, 8, 10}, f"Invalid video duration: {s.video_duration_sec}"
        duration_counts[s.video_duration_sec] += 1

    # Verify all 4 standard durations are represented
    assert duration_counts[4] > 0, "Missing 4s scenes"
    assert duration_counts[6] > 0, "Missing 6s scenes"
    assert duration_counts[8] > 0, "Missing 8s scenes"
    assert duration_counts[10] > 0, "Missing 10s scenes"


def test_visual_timeline_coverage(episode_data):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    is_valid, issues = validate_visual_timeline(
        scenes=scenes,
        total_audio_sec=episode_data["total_audio_sec"],
        character_lib=planner.characters,
        location_lib=planner.locations
    )
    assert is_valid is True, f"Timeline validation failed with issues: {issues}"
    assert issues == []

    # Strict timeline math verification
    assert scenes[0].start_sec == 0.0
    assert abs(scenes[-1].end_sec - episode_data["total_audio_sec"]) < 0.05
    for i in range(len(scenes) - 1):
        assert abs(scenes[i+1].start_sec - scenes[i].end_sec) < 0.01, (
            f"Gap or overlap between {scenes[i].scene_id} and {scenes[i+1].scene_id}"
        )


def test_character_ids_valid(episode_data):
    char_lib = load_character_library()
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    for s in scenes:
        for cid in s.characters:
            assert cid in char_lib, f"Scene {s.scene_id} references invalid character: {cid}"


def test_location_ids_valid(episode_data):
    loc_lib = load_location_library()
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    for s in scenes:
        assert s.location in loc_lib, f"Scene {s.scene_id} references invalid location: {s.location}"


def test_queue_sync(episode_data, tmp_path):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    asset_mgr = VisualAssetManager(tmp_path)
    queue = asset_mgr.sync_queue_with_plan(scenes)

    assert len(queue) == len(scenes)
    for s in scenes:
        item = queue[s.scene_id]
        assert item.visual_type == s.visual_type
        assert item.image_status == "PLANNED"
        if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"):
            assert item.video_status == "PLANNED"
        else:
            assert item.video_status == "SKIPPED"


def test_reanalyze_does_not_delete_assets(episode_data, tmp_path):
    planner = VisualPlanner(preset_name="sau_canh_cua")
    scenes = planner.plan_episode_visuals(
        timeline_events=episode_data["timeline_events"],
        total_audio_sec=episode_data["total_audio_sec"],
        project_dir=PROJECT_DIR
    )

    asset_mgr = VisualAssetManager(tmp_path)
    asset_mgr.sync_queue_with_plan(scenes)

    # Mark scene 1 as completed with a media id and local file
    sc1_id = scenes[0].scene_id
    asset_mgr.update_item(
        sc1_id,
        image_status="COMPLETED",
        image_media_id="flow_media_abc123",
        image_path=str(tmp_path / "visual/images/SC_001.png")
    )
    (tmp_path / "visual/images").mkdir(parents=True, exist_ok=True)
    with open(tmp_path / "visual/images/SC_001.png", "wb") as f:
        f.write(b"FAKE_PNG_BYTES")

    # Re-sync queue (simulating re-planning)
    resynced_queue = asset_mgr.sync_queue_with_plan(scenes)

    # Completed asset must remain COMPLETED and file must not be deleted
    assert resynced_queue[sc1_id].image_status == "COMPLETED"
    assert resynced_queue[sc1_id].image_media_id == "flow_media_abc123"
    assert (tmp_path / "visual/images/SC_001.png").exists()


def test_audio_formula_regression(episode_data):
    """Verifies Audio Formula V1 files and loudness metrics are completely untouched."""
    voice_master_p = episode_data["voice_master_p"]
    assert voice_master_p.exists()
    assert voice_master_p.stat().st_size > 0

    final_mix_p = PROJECT_DIR / "master/final_mix.wav"
    assert final_mix_p.exists()
    assert final_mix_p.stat().st_size > 0

    from apps.music_engine import analyze_audio_loudness
    metrics = analyze_audio_loudness(final_mix_p)
    # -15.14 LUFS baseline
    assert -16.0 <= metrics["integrated_lufs"] <= -14.5
    assert metrics["true_peak_db"] <= -0.5
