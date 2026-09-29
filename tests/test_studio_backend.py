"""Automated tests for Sau Cánh Cửa Studio Desktop Backend & API."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from studio.backend.server import app

client = TestClient(app)


def test_list_projects():
    res = client.get("/api/projects")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 2
    ep_ids = [p["project_id"] for p in data]
    assert "EP003" in ep_ids
    assert "EP011" in ep_ids


def test_project_details_and_next_action():
    res = client.get("/api/projects/EP003")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == "EP003"
    assert data["scene_count"] == 45
    assert data["image_count"] == 38
    assert data["video_count"] == 7
    assert data["series_id"] == "SAU_CANH_CUA"

    # Next Action must exist
    na = data.get("next_action")
    assert na is not None
    assert "stage_id" in na
    assert "title" in na
    assert "button_label" in na


def test_story_bible():
    res = client.get("/api/projects/EP003/story")
    assert res.status_code == 200
    data = res.json()
    assert "premise" in data
    assert "reveal_1" in data
    assert "reveal_2" in data


def test_script_segments():
    res = client.get("/api/projects/EP003/script")
    assert res.status_code == 200
    data = res.json()
    assert len(data) in [45, 90]
    assert data[0]["segment_id"] == "001"
    assert "delivery_profile" in data[0]

    # Full text article view
    res_full = client.get("/api/projects/EP003/script/full")
    assert res_full.status_code == 200
    assert len(res_full.json()["text"]) > 100


def test_audio_info():
    res = client.get("/api/projects/EP003/audio")
    assert res.status_code == 200
    data = res.json()
    assert data["available"] is True
    assert data["duration_sec"] > 200.0
    assert len(data["waveform_peaks"]) > 50
    assert len(data["markers"]) >= 4


def test_visual_plan_scenes():
    res = client.get("/api/projects/EP003/visual/scenes")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 45

    video_scenes = [s for s in data if s["visual_mode"] == "VIDEO_RECOMMENDED"]
    assert len(video_scenes) == 7

    # Characters
    res_chars = client.get("/api/projects/EP003/visual/characters")
    assert res_chars.status_code == 200
    assert len(res_chars.json()) == 6


def test_google_flow_info():
    res = client.get("/api/projects/EP003/flow")
    assert res.status_code == 200
    data = res.json()
    assert data["stats"]["schema_version"] == "SCC_FLOW_V1"
    assert data["stats"]["scenes"] == 45
    assert len(data["instructions"]) >= 5


def test_asset_manifest():
    res = client.get("/api/projects/EP003/assets")
    assert res.status_code == 200
    data = res.json()
    assert len(data["scenes"]) == 45
    assert "stats" in data


def test_timeline_tracks():
    res = client.get("/api/projects/EP003/timeline")
    assert res.status_code == 200
    data = res.json()
    assert len(data["tracks"]) == 4
    track_ids = [t["id"] for t in data["tracks"]]
    assert "V2" in track_ids
    assert "V1" in track_ids
    assert "A2" in track_ids
    assert "A1" in track_ids


def test_final_qc_report():
    res = client.get("/api/projects/EP003/qc")
    assert res.status_code == 200
    data = res.json()
    assert data["overall_status"] == "PASS"
    assert data["resolution"] == "1920x1080"
    assert data["fps"] == 30
    assert len(data["checks_summary"]) == 9


def test_system_status():
    res = client.get("/api/system/status")
    assert res.status_code == 200
    data = res.json()
    assert "free_disk_gb" in data
    assert data["ffmpeg_available"] is True


def test_static_ui_serving():
    res = client.get("/")
    assert res.status_code == 200
    assert "<!doctype html>" in res.text.lower()
