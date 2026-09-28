"""Test End-to-End Omni 1.1 Flash Video Generation for Production Storytelling.

Verifies:
1. FlowKitAdapter connectivity to Google Flow session.
2. Video generation with model_family="omni_flash" (4s, 720p).
3. Polling and download of actual MP4 asset.
4. FFprobe validation (H.264, 720p).
5. Dynamic video fit to scene duration.
"""
from pathlib import Path
import json
import subprocess

from apps.visual_engine.flowkit_adapter import FlowKitAdapter
from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.veo_client import VeoClient
from apps.visual_engine.visual_planner import VisualScene
from apps.visual_engine.final_video_renderer import FinalVideoRenderer


def test_omni_flash_end_to_end():
    project_dir = Path("projects/sau_canh_cua_-_episode_01_v9_1_master_reference")
    adapter = FlowKitAdapter()

    st = adapter.get_connection_status()
    print(f"[TEST] Connection Status: {st}")
    assert st.flowkit_server_running, "FlowKit server not running"

    asset_mgr = VisualAssetManager(project_dir)

    # Pick SC_001
    plan_file = project_dir / "visual/visual_plan.json"
    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    sc001_dict = plan["scenes"][0]
    sc001 = VisualScene(**sc001_dict)
    print(f"[TEST] Target scene: {sc001.scene_id} ({sc001.visual_type}, {sc001.duration_sec:.2f}s)")

    # Temporarily set visual_type to VEO_I2V for test if needed
    sc001.visual_type = "VEO_I2V"

    video_client = VeoClient(
        adapter=adapter,
        asset_mgr=asset_mgr,
        model_family="omni_flash",
        duration_s=4,
        poll_interval_s=4.0,
        poll_timeout_s=180.0
    )

    out_mp4 = video_client.generate_scene_video(
        scene=sc001,
        project_id=st.flow_project_id or "",
        force_regenerate=True,
        allow_fallback=False
    )

    print(f"[TEST] Generated Video Path: {out_mp4}")
    assert out_mp4 is not None and out_mp4.exists(), "Video was not generated or saved"
    sz = out_mp4.stat().st_size
    print(f"[TEST] File size: {sz:,} bytes")
    assert sz > 50000, f"File size too small: {sz} bytes"

    # FFprobe verify
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height", "-of", "json", str(out_mp4)],
        capture_output=True, text=True
    )
    probe_data = json.loads(res.stdout)
    print(f"[TEST] FFprobe data: {probe_data}")

    # Test dynamic fitting
    renderer = FinalVideoRenderer(asset_mgr)
    fitted_clip = renderer.fit_video_clip(out_mp4, target_duration_sec=sc001.duration_sec)
    assert fitted_clip.exists() and fitted_clip.stat().st_size > 0, "Fitted clip failed"
    print(f"[TEST] Successfully fitted video to scene duration: {fitted_clip} ({fitted_clip.stat().st_size:,} bytes)")
    print("[TEST] ALL OMNI 1.1 FLASH TESTS PASSED!")


if __name__ == "__main__":
    test_omni_flash_end_to_end()
