"""Phase 3 Test Suite: Character Lock + Pilot Generation Framework.

Validates the 12 core requirements from Section 32:
1. test_character_reference_required: Character references are mandatory for scene generation.
2. test_character_media_cache: Flow media IDs are cached and reused without redundant uploads.
3. test_young_lan_identity_relation: LAN_YOUNG is linked to LAN_ADULT via identity_relation.
4. test_visible_characters_only_sent_to_banana: Only characters in scene.characters have references sent.
5. test_scene_keyframe_dependency: Video generation strictly requires keyframe.
6. test_keyframe_change_marks_video_stale: Keyframe modification marks dependent video STALE_KEYFRAME.
7. test_character_change_marks_scene_stale: Character reference change marks dependent scenes STALE_REFERENCE.
8. test_pilot_generation_scope: Pilot scope targets exactly the 8 specified scenes.
9. test_generation_credit_confirmation: Credit calculation accurately counts Banana and Omni requests.
10. test_omni_uses_approved_keyframe: Omni 1.1 Flash generation enforces approved keyframe status.
11. test_generated_audio_not_used_by_final_renderer: Final video renderer strictly ignores clip audio and muxes final_mix.wav.
12. test_full_generation_locked_before_pilot_approval: Generate All remains locked until 8 keyframes and 5 videos are approved.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.visual_engine.character_manager import (
    CharacterProfile,
    LocationProfile,
    load_character_library,
    load_location_library,
    load_visual_preset,
)
from apps.visual_engine.visual_planner import (
    VisualScene,
    PILOT_SCENE_IDS,
    validate_character_references_ready,
    validate_scene_character_references,
)
from apps.visual_engine.asset_manager import VisualAssetManager, QueueItem
from apps.visual_engine.banana_client import BananaClient
from apps.visual_engine.veo_client import VeoClient
from apps.visual_engine.visual_qc import record_pilot_qc, validate_technical_image
from apps.visual_engine.final_video_renderer import FinalVideoRenderer


@pytest.fixture
def temp_project(tmp_path):
    """Creates a temporary project folder with necessary directories."""
    proj = tmp_path / "test_episode"
    proj.mkdir()
    (proj / "visual/images").mkdir(parents=True)
    (proj / "visual/videos").mkdir(parents=True)
    (proj / "master").mkdir(parents=True)
    (proj / "final").mkdir(parents=True)
    return proj


def test_character_reference_required(temp_project):
    """1. Keyframe generation without character reference fails/rejects."""
    char_lib = {
        "LAN_ADULT": CharacterProfile(
            char_id="LAN_ADULT",
            name="Lan (Trưởng thành)",
            references=[]  # Missing references!
        )
    }
    scene = VisualScene(
        scene_id="SC_001",
        start_sec=0.0,
        end_sec=4.0,
        duration_sec=4.0,
        story_beat="Intro",
        characters=["LAN_ADULT"],
        visible_characters=["LAN_ADULT"],
        location="LAN_HOME",
        visual_type="OMNI_FLASH_I2V"
    )

    ready, missing = validate_scene_character_references([scene], char_lib)
    assert not ready
    assert any("LAN_ADULT" in m for m in missing)

    all_ready, all_missing = validate_character_references_ready(char_lib)
    assert not all_ready
    assert any("LAN_ADULT" in m for m in all_missing)

    mock_adapter = MagicMock()
    asset_mgr = VisualAssetManager(temp_project)
    banana = BananaClient(mock_adapter, asset_mgr, char_lib)
    res = banana.generate_scene_keyframe(scene)
    assert res is None
    q = asset_mgr.load_queue()
    assert q["SC_001"].image_status == "FAILED"
    assert "reference" in q["SC_001"].last_error.lower()


def test_character_media_cache(temp_project):
    """2. Flow media IDs are cached and reused without re-uploading."""
    char_lib = {
        "HUNG": CharacterProfile(
            char_id="HUNG",
            name="Hùng",
            references=["ref_portrait.png"],
            flow_media_ids={"ref_portrait.png": "cached-hung-media-id-12345"}
        )
    }
    mock_adapter = MagicMock()
    asset_mgr = VisualAssetManager(temp_project)
    banana = BananaClient(mock_adapter, asset_mgr, char_lib)

    media_ids = banana.ensure_character_references("HUNG", "proj-123")
    assert media_ids == ["cached-hung-media-id-12345"]
    mock_adapter.upload_image_file.assert_not_called()


def test_young_lan_identity_relation():
    """3. LAN_YOUNG is linked to LAN_ADULT via identity_relation."""
    char_lib = load_character_library()
    assert "LAN_YOUNG" in char_lib
    lan_young = char_lib["LAN_YOUNG"]
    assert lan_young.identity_relation is not None
    assert lan_young.identity_relation.get("type") == "YOUNGER_VERSION_OF"
    assert lan_young.identity_relation.get("character_id") == "LAN_ADULT"


def test_visible_characters_only_sent_to_banana(temp_project):
    """4. Only characters in scene.characters have references sent to Banana."""
    char_lib = {
        "LAN_ADULT": CharacterProfile(
            char_id="LAN_ADULT",
            name="Lan",
            references=["ref_lan.png"],
            flow_media_ids={"ref_lan.png": "media-lan-999"}
        ),
        "HUNG": CharacterProfile(
            char_id="HUNG",
            name="Hùng",
            references=["ref_hung.png"],
            flow_media_ids={"ref_hung.png": "media-hung-888"}
        )
    }
    # Scene has ONLY HUNG
    scene = VisualScene(
        scene_id="SC_011",
        start_sec=20.0,
        end_sec=25.0,
        duration_sec=5.0,
        story_beat="Hung at Archive",
        characters=["HUNG"],
        visible_characters=["HUNG"],
        location="ARCHIVE_OFFICE",
        visual_type="BANANA_IMAGE",
        image_prompt="Hung at archive looking at records"
    )

    mock_adapter = MagicMock()
    mock_asset = MagicMock()
    mock_asset.media_id = "img-out-111"
    mock_asset.url = "http://fake.url/img.jpg"
    mock_adapter.generate_image.return_value = [mock_asset]
    mock_adapter.download_asset.side_effect = lambda url, path: Path(path).write_bytes(b"dummy")

    asset_mgr = VisualAssetManager(temp_project)
    banana = BananaClient(mock_adapter, asset_mgr, char_lib)

    banana.generate_scene_keyframe(scene, project_id="proj-abc", force_regenerate=True)

    # Inspect call to generate_image
    call_kwargs = mock_adapter.generate_image.call_args[1]
    refs = call_kwargs.get("reference_media_ids")
    assert refs == ["media-hung-888"]
    assert "media-lan-999" not in refs


def test_scene_keyframe_dependency(temp_project):
    """5. Video generation strictly requires an existing keyframe."""
    asset_mgr = VisualAssetManager(temp_project)
    mock_adapter = MagicMock()
    veo = VeoClient(mock_adapter, asset_mgr)

    scene = VisualScene(
        scene_id="SC_025",
        start_sec=100.0,
        end_sec=108.0,
        duration_sec=8.0,
        story_beat="Tense discussion",
        characters=["LAN_ADULT", "HUNG"],
        location="LAN_HOME",
        visual_type="OMNI_FLASH_I2V"
    )

    # Keyframe does NOT exist on disk and is not approved
    res = veo.generate_scene_video(scene, project_id="proj-123", allow_fallback=False)
    assert res is None


def test_keyframe_change_marks_video_stale(temp_project):
    """6. Keyframe change marks dependent video as STALE_KEYFRAME."""
    asset_mgr = VisualAssetManager(temp_project)
    # Set up queue with DONE video
    asset_mgr.update_queue_item("SC_025", image_status="DONE", video_status="DONE")
    q = asset_mgr.load_queue()
    assert q["SC_025"].video_status == "DONE"

    # Mark keyframe updated
    asset_mgr.mark_keyframe_updated("SC_025", new_keyframe_hash="newhash123")
    q_after = asset_mgr.load_queue()
    assert q_after["SC_025"].video_status == "STALE_KEYFRAME"
    assert q_after["SC_025"].video_qc_status == "AWAITING_QC"
    assert "newhash123" in q_after["SC_025"].stale_reason


def test_character_change_marks_scene_stale(temp_project):
    """7. Character reference change marks dependent scenes STALE_REFERENCE."""
    asset_mgr = VisualAssetManager(temp_project)
    scenes = [
        VisualScene(scene_id="SC_001", start_sec=0.0, end_sec=4.0, duration_sec=4.0, characters=["LAN_ADULT"]),
        VisualScene(scene_id="SC_002", start_sec=4.0, end_sec=8.0, duration_sec=4.0, characters=["HUNG"]),
        VisualScene(scene_id="SC_003", start_sec=8.0, end_sec=12.0, duration_sec=4.0, characters=["LAN_ADULT", "UNCLE"])
    ]
    # Populate queue with DONE
    for s in scenes:
        asset_mgr.update_queue_item(s.scene_id, image_status="DONE", video_status="DONE")

    stale_scenes = asset_mgr.mark_character_updated("LAN_ADULT", scenes)
    assert len(stale_scenes) == 2
    assert set(stale_scenes) == {"SC_001", "SC_003"}

    q = asset_mgr.load_queue()
    assert q["SC_001"].image_status == "STALE_REFERENCE"
    assert q["SC_003"].image_status == "STALE_REFERENCE"
    assert q["SC_002"].image_status == "DONE"  # HUNG only, not affected!


def test_pilot_generation_scope():
    """8. Pilot scope targets exactly the 8 specified scenes."""
    expected_pilot = ["SC_001", "SC_005", "SC_011", "SC_025", "SC_030", "SC_035", "SC_041", "SC_045"]
    assert PILOT_SCENE_IDS == expected_pilot
    assert len(PILOT_SCENE_IDS) == 8


def test_generation_credit_confirmation(temp_project):
    """9. Credit calculation returns correct counts for Banana and Omni."""
    asset_mgr = VisualAssetManager(temp_project)
    scenes = [
        VisualScene(scene_id="SC_001", start_sec=0.0, end_sec=4.0, duration_sec=4.0, visual_type="OMNI_FLASH_I2V"),
        VisualScene(scene_id="SC_002", start_sec=4.0, end_sec=8.0, duration_sec=4.0, visual_type="BANANA_IMAGE"),
        VisualScene(scene_id="SC_005", start_sec=8.0, end_sec=12.0, duration_sec=4.0, visual_type="BANANA_IMAGE"),
        VisualScene(scene_id="SC_025", start_sec=12.0, end_sec=20.0, duration_sec=8.0, visual_type="OMNI_FLASH_I2V")
    ]
    # Calculate for pilot targets SC_001, SC_005, SC_025
    cost = asset_mgr.calculate_batch_credit_cost(scenes, target_scene_ids=["SC_001", "SC_005", "SC_025"])
    assert cost["banana_requests"] == 3
    assert cost["omni_requests"] == 2
    assert cost["total_requests"] == 5


def test_omni_uses_approved_keyframe(temp_project):
    """10. Omni 1.1 Flash generation enforces approved keyframe status."""
    asset_mgr = VisualAssetManager(temp_project)
    # Create mock keyframe file
    kf_path = asset_mgr.images_dir / "SC_001.jpg"
    kf_path.write_bytes(b"dummy image bytes")

    # Queue item is DONE but NOT APPROVED
    asset_mgr.update_queue_item(
        "SC_001",
        image_status="DONE",
        image_qc_status="AWAITING_QC",
        image_media_id="banana-kf-123"
    )

    mock_adapter = MagicMock()
    veo = VeoClient(mock_adapter, asset_mgr)

    scene = VisualScene(
        scene_id="SC_001",
        start_sec=0.0,
        end_sec=4.0,
        duration_sec=4.0,
        story_beat="Opening",
        characters=["LAN_ADULT"],
        location="LAN_HOME",
        visual_type="OMNI_FLASH_I2V",
        image_media_id="banana-kf-123"
    )

    res_rejected = veo.generate_scene_video(scene, project_id="proj-123", allow_fallback=False)
    assert res_rejected is None
    q_rejected = asset_mgr.load_queue()
    assert q_rejected["SC_001"].video_status == "FAILED"
    assert "not approved" in q_rejected["SC_001"].last_error.lower()

    # Now approve keyframe
    asset_mgr.approve_keyframe("SC_001")
    q_approved = asset_mgr.load_queue()
    assert q_approved["SC_001"].image_qc_status == "APPROVED"

    # Mock adapter generate_video
    mock_adapter.generate_video.return_value = {
        "media": [{"video": {"fifeUrl": "http://flow.google.com/test.mp4"}}]
    }
    mock_adapter.download_asset.side_effect = lambda url, path: Path(path).write_bytes(b"dummy mp4")

    # Generation should proceed now
    with patch("hashlib.md5") as mock_hash:
        mock_hash.return_value.hexdigest.return_value = "dummyhash"
        out_vid = veo.generate_scene_video(scene, project_id="proj-123", allow_fallback=False)
        assert out_vid is not None
        q = asset_mgr.load_queue()
        assert q["SC_001"].video_status in ("DONE", "AWAITING_QC")
        assert q["SC_001"].video_qc_status == "AWAITING_QC"


def test_generated_audio_not_used_by_final_renderer(temp_project):
    """11. Final video renderer strictly ignores clip audio (-an) and muxes final_mix.wav."""
    asset_mgr = VisualAssetManager(temp_project)
    renderer = FinalVideoRenderer(asset_mgr)

    # Check render_banana_motion_clip command line
    img_path = temp_project / "visual/images/SC_001.jpg"
    img_path.write_bytes(b"dummy")

    with patch("subprocess.run") as mock_subproc:
        mock_subproc.return_value.returncode = 0
        renderer.render_banana_motion_clip(img_path, duration_sec=4.0)

        cmd = mock_subproc.call_args[0][0]
        # Must contain -an to discard any audio from video creation
        assert "-an" in cmd

    # Check fit_video_clip command line
    vid_path = temp_project / "visual/videos/SC_001.mp4"
    vid_path.write_bytes(b"dummy")
    with patch("subprocess.run") as mock_subproc, patch.object(renderer, "_get_video_duration", return_value=4.0):
        mock_subproc.return_value.returncode = 0
        renderer.fit_video_clip(vid_path, target_duration_sec=4.0)
        cmd = mock_subproc.call_args[0][0]
        assert "-an" in cmd

    # Check concat & mux in render_final_episode
    scenes = [
        VisualScene(scene_id="SC_001", start_sec=0.0, end_sec=4.0, duration_sec=4.0, visual_type="BANANA_IMAGE")
    ]
    master_wav = temp_project / "master/final_mix.wav"
    master_wav.write_bytes(b"dummy wav data")
    out_mp4 = temp_project / "final/final_episode.mp4"

    with patch("subprocess.run") as mock_subproc, \
         patch.object(renderer, "render_banana_motion_clip", return_value=temp_project / "visual/processed/SC_001.mp4"), \
         patch("soundfile.info") as mock_sf:
        mock_sf.return_value.duration = 4.0
        def fake_run(cmd, *args, **kwargs):
            out_mp4.touch()
            m = MagicMock()
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m
        mock_subproc.side_effect = fake_run
        out = renderer.render_final_episode(scenes, master_wav, out_mp4)

        # Inspect final ffmpeg mux call
        final_call_cmd = mock_subproc.call_args[0][0]
        assert "-map" in final_call_cmd
        assert "0:v:0" in final_call_cmd
        assert "1:a:0" in final_call_cmd
        assert str(master_wav) in final_call_cmd


def test_full_generation_locked_before_pilot_approval(temp_project):
    """12. Strict lock gate for Generate All (Section 30).
    Locked until 8 pilot keyframes and dynamically resolved pilot videos are approved.
    """
    asset_mgr = VisualAssetManager(temp_project)
    # Character profiles with APPROVED status
    char_lib = {
        cid: CharacterProfile(
            char_id=cid,
            name=cid,
            references=["ref_portrait.png"],
            qc_status="APPROVED"
        )
        for cid in ["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"]
    }

    # Create dummy reference files on disk
    from apps.visual_engine.character_manager import CHARACTER_LIB_DIR
    for cid in char_lib:
        cdir = CHARACTER_LIB_DIR / cid
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "ref_portrait.png").write_bytes(b"dummy")

    scenes = [
        VisualScene(scene_id="SC_001", visual_type="OMNI_FLASH_I2V", video_duration_sec=4),
        VisualScene(scene_id="SC_005", visual_type="OMNI_FLASH_I2V", video_duration_sec=8),
        VisualScene(scene_id="SC_011", visual_type="OMNI_FLASH_I2V", video_duration_sec=8),
        VisualScene(scene_id="SC_025", visual_type="BANANA_IMAGE"),
        VisualScene(scene_id="SC_030", visual_type="OMNI_FLASH_I2V", video_duration_sec=6),
        VisualScene(scene_id="SC_035", visual_type="BANANA_IMAGE"),
        VisualScene(scene_id="SC_041", visual_type="BANANA_IMAGE"),
        VisualScene(scene_id="SC_045", visual_type="BANANA_IMAGE"),
    ]

    pilot_ids = ["SC_001", "SC_005", "SC_011", "SC_025", "SC_030", "SC_035", "SC_041", "SC_045"]
    pilot_omni_ids = ["SC_001", "SC_005", "SC_011", "SC_030"]

    # Initially empty queue -> locked!
    unlocked, info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
    assert not unlocked
    assert "Pilot review pending" in info["reason"]
    assert info["pilot_omni_ids"] == pilot_omni_ids

    # Approve 8 keyframes but 0 videos -> still locked
    for pid in pilot_ids:
        asset_mgr.update_queue_item(pid, image_status="DONE", image_qc_status="APPROVED")
    unlocked, info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
    assert not unlocked

    # Approve only 3 of 4 omni videos -> still locked
    for pid in pilot_omni_ids[:-1]:
        asset_mgr.update_queue_item(pid, video_status="DONE", video_qc_status="APPROVED")
    unlocked, info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
    assert not unlocked

    # Approve the 4th omni video -> UNLOCKED!
    asset_mgr.update_queue_item(pilot_omni_ids[-1], video_status="DONE", video_qc_status="APPROVED")
    unlocked, info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
    assert unlocked
    assert info["full_generation_unlocked"] is True
    assert info["reason"] == "Ready"


def test_pilot_metadata_loaded_from_visual_plan():
    """13. Pilot source-of-truth test (Phase 3.1):
    All metadata MUST be loaded directly from visual/visual_plan.json.
    """
    plan_path = REPO_ROOT / "projects/sau_canh_cua_-_episode_01_v9_1_master_reference/visual/visual_plan.json"
    assert plan_path.exists(), f"Missing visual_plan.json at {plan_path}"

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    scenes_by_id = {s["scene_id"]: s for s in plan.get("scenes", [])}

    # Verify all 8 pilot scene IDs are present
    for pid in PILOT_SCENE_IDS:
        assert pid in scenes_by_id, f"Pilot scene {pid} missing from visual_plan.json"
        s = scenes_by_id[pid]
        assert s.get("story_beat"), f"{pid} has empty story_beat"
        assert s.get("location"), f"{pid} has empty location"
        assert s.get("visual_type") in ("BANANA_IMAGE", "OMNI_FLASH_I2V"), f"{pid} invalid visual_type"
        assert s.get("image_prompt"), f"{pid} has empty image_prompt"

    # Dynamic Omni count in pilot must be exactly 4 (SC_001, SC_005, SC_011, SC_030), total 26s
    pilot_omni_scenes = [scenes_by_id[pid] for pid in PILOT_SCENE_IDS if scenes_by_id[pid].get("visual_type") == "OMNI_FLASH_I2V"]
    assert len(pilot_omni_scenes) == 4
    assert [s["scene_id"] for s in pilot_omni_scenes] == ["SC_001", "SC_005", "SC_011", "SC_030"]
    total_omni_sec = sum(s.get("video_duration_sec", 0) for s in pilot_omni_scenes)
    assert total_omni_sec == 26

    # Verify SC_030 Archive Office death record 14 years ago
    sc_030 = scenes_by_id["SC_030"]
    assert sc_030["location"] == "ARCHIVE_OFFICE"
    assert sc_030["visible_characters"] == ["HUNG", "LAN_ADULT"]
    assert sc_030["visual_type"] == "OMNI_FLASH_I2V"
    assert sc_030["video_duration_sec"] == 6
    assert "14 năm trước" in sc_030["text_overlay_content"]

    # Verify SC_041 Climax at Lan Home
    sc_041 = scenes_by_id["SC_041"]
    assert sc_041["location"] == "LAN_HOME"
    assert sc_041["visible_characters"] == ["HUNG", "LAN_ADULT"]
    assert sc_041["visual_type"] == "BANANA_IMAGE"

    # Verify SC_001 Lan Bedroom Bank Transfer overlay
    sc_001 = scenes_by_id["SC_001"]
    assert sc_001["location"] == "LAN_BEDROOM"
    assert sc_001["visible_characters"] == ["LAN_ADULT"]
    assert sc_001["visual_type"] == "OMNI_FLASH_I2V"
    assert sc_001["video_duration_sec"] == 4
    assert "-5.000.000 VND" in sc_001["text_overlay_content"]

    # Verify SC_005 Lan Young flashback at Lan Home
    sc_005 = scenes_by_id["SC_005"]
    assert sc_005["location"] == "LAN_HOME"
    assert sc_005["visible_characters"] == ["LAN_YOUNG"]
    assert sc_005["visual_type"] == "OMNI_FLASH_I2V"
    assert sc_005["video_duration_sec"] == 8


def test_pilot_generation_gate_character_approval(temp_project):
    """14. Pilot generation is locked until all 4 characters are approved."""
    asset_mgr = VisualAssetManager(temp_project)

    # Characters with AWAITING_REVIEW
    char_lib = {
        cid: CharacterProfile(
            char_id=cid,
            name=cid,
            references=["ref_portrait.png"],
            qc_status="AWAITING_REVIEW"
        )
        for cid in ["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"]
    }

    # Initially locked because characters are unapproved
    unlocked, info = asset_mgr.is_pilot_generation_unlocked(char_lib)
    assert not unlocked
    assert info["characters_approved"] is False
    assert len(info["unapproved_characters"]) == 4

    # Approve 3 of 4 -> still locked
    for cid in ["LAN_ADULT", "HUNG", "UNCLE"]:
        char_lib[cid].qc_status = "APPROVED"
    unlocked, info = asset_mgr.is_pilot_generation_unlocked(char_lib)
    assert not unlocked
    assert len(info["unapproved_characters"]) == 1

    # Approve all 4 -> UNLOCKED
    char_lib["LAN_YOUNG"].qc_status = "APPROVED"
    unlocked, info = asset_mgr.is_pilot_generation_unlocked(char_lib)
    assert unlocked
    assert info["pilot_generation_unlocked"] is True
    assert info["reason"] == "Ready for Pilot Generation."


def test_semantic_hash_tamper_protection(temp_project):
    """15. Generation gates are locked if visual_plan.json is modified post-QC."""
    asset_mgr = VisualAssetManager(temp_project)
    from apps.visual_engine.visual_planner import compute_visual_plan_semantic_hash

    char_lib = {
        cid: CharacterProfile(
            char_id=cid,
            name=cid,
            references=["ref_portrait.png"],
            qc_status="APPROVED"
        )
        for cid in ["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"]
    }

    scenes = [
        {"scene_id": "SC_001", "story_beat": "Intro", "visual_type": "BANANA_IMAGE", "location": "LAN_BEDROOM"}
    ]
    correct_hash = compute_visual_plan_semantic_hash(scenes)

    plan_file = temp_project / "visual/visual_plan.json"
    plan_data = {"scenes": scenes, "semantic_hash": correct_hash}
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan_data, f)

    # Valid hash -> unlocked
    unlocked, info = asset_mgr.is_pilot_generation_unlocked(char_lib)
    assert unlocked
    assert info["semantic_hash_valid"] is True

    # Tamper with scene content without recomputing hash
    tampered_scenes = [
        {"scene_id": "SC_001", "story_beat": "Altered beat", "visual_type": "BANANA_IMAGE", "location": "LAN_BEDROOM"}
    ]
    tampered_data = {"scenes": tampered_scenes, "semantic_hash": correct_hash}
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(tampered_data, f)

    # Tampered plan -> gate must immediately lock!
    unlocked, info = asset_mgr.is_pilot_generation_unlocked(char_lib)
    assert not unlocked
    assert info["semantic_hash_valid"] is False
    assert "Semantic hash mismatch" in info["reason"]
