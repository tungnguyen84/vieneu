"""End-to-End Test for AI Idea -> Auto Story Bible -> Full MC Script Workflow."""
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from studio.backend.server import app
from studio.backend.models import StageStatus
from studio.backend.services.generation_service import GenerationService

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE_DIR / "projects"


@pytest.fixture(autouse=True)
def cleanup_test_project():
    pid = "EPTESTIDEAFLOW"
    pdir = PROJECTS_DIR / pid
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)
    yield
    if pdir.exists():
        shutil.rmtree(pdir, ignore_errors=True)


def test_ai_idea_to_story_to_script_e2e():
    pid = "EPTESTIDEAFLOW"

    with patch.object(GenerationService, "get_provider", return_value=MockScriptAIProvider()):
        # 1. Create project
        create_resp = client.post("/api/projects/create", json={
            "episode_id": pid,
            "title": "Bí Ẩn Test Idea Flow",
            "premise": "Khởi tạo từ AI Idea",
            "target_duration": 1200,
            "category": "Gia đình / Bí ẩn"
        })
        assert create_resp.status_code == 200, create_resp.text
        data = create_resp.json()
        assert data["project_id"] == pid

        # 2. Generate ideas
        ideas_resp = client.post(f"/api/projects/{pid}/ideas/generate", json={"direction": "BÍ MẬT GIA ĐÌNH", "count": 5})
        assert ideas_resp.status_code == 200, ideas_resp.text
        ideas = ideas_resp.json().get("ideas", [])
        assert len(ideas) >= 1
        chosen_idea = ideas[0]

        # 3. Select AI Idea - transitions to Story stage
        sel_resp = client.post(f"/api/projects/{pid}/ideas/select", json={"idea": chosen_idea})
        assert sel_resp.status_code == 200, sel_resp.text

        # Verify project.json stores selected_idea
        p_json = PROJECTS_DIR / pid / "project.json"
        assert p_json.exists()
        with open(p_json, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta.get("selected_idea") is not None
        assert (meta["selected_idea"].get("title") or meta["selected_idea"].get("working_title")) == (chosen_idea.get("title") or chosen_idea.get("working_title"))

        # 4. Check Story Bible Section endpoint before generating
        story_pre = client.get(f"/api/projects/{pid}/story")
        assert story_pre.status_code == 200
        pre_data = story_pre.json()
        assert pre_data["has_story_bible"] is False
        assert pre_data["selected_idea"] is not None

        # 5. Generate Story Bible WITHOUT entering any manual topic (empty topic)
        gen_story_resp = client.post(f"/api/projects/{pid}/story/generate", json={"topic": ""})
        assert gen_story_resp.status_code == 200, gen_story_resp.text
        bible_data = gen_story_resp.json()
        assert "premise" in bible_data
        assert "characters" in bible_data
        assert "critical_facts" in bible_data

        # Check story endpoint after generation
        story_post = client.get(f"/api/projects/{pid}/story")
        assert story_post.status_code == 200
        post_data = story_post.json()
        assert post_data["has_story_bible"] is True
        assert len(post_data["fact_lock_items"]) > 0
        assert post_data["reveal_1"] != ""
        assert post_data["reveal_2"] != ""
        assert post_data["emotional_payoff"] != ""

        # 6. Approve Story Bible
        app_story = client.post(f"/api/projects/{pid}/story/approve")
        assert app_story.status_code == 200

        # 7. Generate Full Script (host-led letter format for MC Minh)
        gen_script_resp = client.post(f"/api/projects/{pid}/script/generate", json={"force": False})
        assert gen_script_resp.status_code == 200, gen_script_resp.text
        script_data = gen_script_resp.json()

        stats = script_data.get("stats", {})
        seg_count = stats.get("segment_count", 0)
        word_count = stats.get("word_count", 0)
        qc_status = stats.get("qc_status", "")

        # Assert standard requirements: 80-100 segments, 2500-3200 words, QC PASS
        assert 80 <= seg_count <= 100, f"Expected 80-100 segments, got {seg_count}"
        assert 2500 <= word_count <= 3200, f"Expected 2500-3200 words, got {word_count}"
        assert qc_status == "PASS"

        # 8. Check segments details
        segs_resp = client.get(f"/api/projects/{pid}/script")
        assert segs_resp.status_code == 200
        segments = segs_resp.json()
        assert len(segments) == seg_count
        # All segments read by MC Minh
        assert all(s["speaker"] == "MINH" for s in segments)

        # Verify delivery profiles
        profiles = {s["delivery_profile"] for s in segments}
        assert "HOOK" in profiles
        assert "NORMAL" in profiles
        assert "MYSTERY" in profiles
        assert "REVEAL" in profiles
        assert "COMMENT" in profiles
        assert "ENDING" in profiles

        # Verify letter opening style
        first_text = segments[0]["text"]
        assert any(term in first_text for term in ["Sau Cánh Cửa", "lá thư", "tâm thư", "hòm thư", "bức tâm thư"])

        # 9. Check Full Script Text endpoint (Normal mode continuous transcript)
        full_resp = client.get(f"/api/projects/{pid}/script/full")
        assert full_resp.status_code == 200
        full_text = full_resp.json().get("text", "")
        assert len(full_text.split()) == word_count
        assert "Minh" in full_text

        # 10. Mock lineage can be rendered for test inspection but must never be
        # approved as a production/current Full Script.
        app_script = client.post(f"/api/projects/{pid}/script/approve")
        assert app_script.status_code == 400
        assert "STALE" in app_script.json()["detail"]

        # Verify final project status
        proj_resp = client.get(f"/api/projects/{pid}")
        assert proj_resp.status_code == 200
        proj = proj_resp.json()
        assert proj["stage_statuses"]["01_idea"] == StageStatus.APPROVED.value
        assert proj["stage_statuses"]["02_story"] == StageStatus.APPROVED.value
        assert proj["stage_statuses"]["03_script"] == StageStatus.NEEDS_REVIEW.value
