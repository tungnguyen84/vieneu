"""Automated unit and integration tests for Sau Cánh Cửa Studio V1.1.

Covers:
- AI Provider Credentials Management (Fernet encryption, masked keys, connection test)
- Project Manager V1.1 (next episode ID suggestion, clean directory scaffolding)
- Option A: Idea Generation & Selection
- Option B: Story Planner -> Story Bible + Fact Lock + Approval Gate
- Option C: Script Factory V1.3.1a -> Full Script + QC + Auto-Repair + Approval Gate
- Regression verification for EP003 and EP011
- Zero quota consumption (all LLM calls mocked)
"""
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from studio.backend.credentials import (
    delete_provider_credentials,
    get_public_providers_status,
    save_provider_credentials,
    test_provider_connection as check_provider_connection,
)
from studio.backend.server import app
from studio.backend.project_manager import ProjectManager
from studio.backend.services.generation_service import GenerationService

client = TestClient(app)
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
TEST_EP_ID = "EP999"


@pytest.fixture(autouse=True)
def cleanup_test_project():
    """Ensure test project directory is cleaned up before and after testing."""
    test_proj = PROJECTS_DIR / TEST_EP_ID
    test_ep = BASE_DIR / "episodes" / TEST_EP_ID
    if test_proj.exists():
        shutil.rmtree(test_proj, ignore_errors=True)
    if test_ep.exists():
        shutil.rmtree(test_ep, ignore_errors=True)
    yield
    if test_proj.exists():
        shutil.rmtree(test_proj, ignore_errors=True)
    if test_ep.exists():
        shutil.rmtree(test_ep, ignore_errors=True)


# ============================================================================
# 1. AI PROVIDER CREDENTIALS & SECURITY TESTS
# ============================================================================

def test_credentials_lifecycle():
    """Tests saving, masking, testing, and deleting provider credentials."""
    # 1. Save Gemini Key
    save_res = save_provider_credentials(
        provider="gemini",
        api_key="AIzaSyDummyKeyForTestingStudioV1_1_2026",
        model="gemini-2.5-flash",
    )
    assert save_res["status"] == "saved"
    assert save_res["configured"] is True

    # 2. Public status should NOT reveal plaintext key
    status = get_public_providers_status()
    gemini_info = status["providers"]["gemini"]
    assert gemini_info["configured"] is True
    assert gemini_info["has_key"] is True
    assert "AIza" in gemini_info["masked_key"]
    assert "TestingStudioV1" not in gemini_info["masked_key"]
    assert gemini_info["masked_key"].count("•") >= 6

    # 3. Test connection (mocked network call)
    with patch("urllib.request.urlopen") as mock_url:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"models": []}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_response

        test_res = check_provider_connection("gemini", model="gemini-2.5-flash")
        assert test_res["success"] is True


    # 4. Save and verify OpenAI Compatible with custom Base URL
    save_compat = save_provider_credentials(
        provider="openai_compatible",
        api_key="sk-dummy-deepseek-key",
        model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
    )
    assert save_compat["configured"] is True
    status = get_public_providers_status()
    compat_info = status["providers"]["openai_compatible"]
    assert compat_info["base_url"] == "https://api.deepseek.com/v1"
    assert compat_info["masked_key"].startswith("sk-d")

    # 5. Delete and verify removal
    del_res = delete_provider_credentials("gemini")
    assert del_res["status"] == "deleted"
    status_after = get_public_providers_status()
    assert status_after["providers"]["gemini"]["configured"] is False
    assert status_after["providers"]["gemini"]["has_key"] is False


def test_api_endpoints_ai_providers():
    """Tests the HTTP endpoints for AI providers."""
    # GET providers status
    res = client.get("/api/ai/providers")
    assert res.status_code == 200
    data = res.json()
    assert "providers" in data
    assert "gemini" in data["providers"]
    assert "openai" in data["providers"]
    assert "anthropic" in data["providers"]
    assert "openai_compatible" in data["providers"]
    assert "local" in data["providers"]

    # POST test provider with invalid key
    res_test = client.post(
        "/api/ai/test",
        json={"provider": "gemini", "api_key": ""},
    )
    assert res_test.status_code == 200
    assert res_test.json()["success"] is False


# ============================================================================
# 2. PROJECT CREATION & NEXT ID SUGGESTION
# ============================================================================

def test_next_available_episode_id():
    """Verify next episode ID scanner correctly suggests the next available ID."""
    res = client.get("/api/projects/next-id")
    assert res.status_code == 200
    data = res.json()
    ep_id = data["episode_id"]
    assert ep_id.startswith("EP")
    # Should be greater than EP011 since EP001, EP003, EP011 exist
    num = int(ep_id.replace("EP", ""))
    assert num >= 12


def test_create_new_project_scaffolding():
    """Verify that creating a new episode initializes complete directory scaffolding."""
    res = client.post(
        "/api/projects/create",
        json={
            "episode_id": TEST_EP_ID,
            "title": "Bức Di Thư Dưới Nền Nhà",
            "premise": "Người con trai tìm thấy bức di thư bí ẩn từ năm 1995.",
            "target_duration": 1200,
            "category": "Gia đình / Bí ẩn",
        },
    )
    assert res.status_code == 200
    proj_meta = res.json()
    assert proj_meta["project_id"] == TEST_EP_ID
    assert proj_meta["title"] == "Bức Di Thư Dưới Nền Nhà"

    # Verify physical directories created
    p_dir = PROJECTS_DIR / TEST_EP_ID
    assert p_dir.exists()
    assert (p_dir / "project.json").exists()
    for sub in ["story", "script", "audio", "visual", "flow", "assets", "timeline", "render", "reports"]:
        assert (p_dir / sub).is_dir()

    # Next action for new project must point to 01_idea or 02_story
    assert proj_meta["next_action"]["stage_id"] in ["01_idea", "02_story"]


# ============================================================================
# 3. OPTION A: IDEA GENERATION & SELECTION
# ============================================================================

def test_idea_generation_and_selection():
    """Tests generating 5 ideas using Mock provider (zero quota) and selecting one."""
    pm = ProjectManager()
    pm.create_project(
        episode_id=TEST_EP_ID,
        title="Test Idea Workflow",
        premise="",
    )

    with patch.object(GenerationService, "get_provider", return_value=MockScriptAIProvider()):
        # 1. Generate 5 ideas
        res = client.post(
            f"/api/projects/{TEST_EP_ID}/ideas/generate",
            json={"direction": "BÍ MẬT GIA ĐÌNH", "count": 5},
        )
        assert res.status_code == 200
        ideas = res.json()["ideas"]
        assert len(ideas) >= 1
        chosen_idea = ideas[0]
        assert "title" in chosen_idea
        assert "premise" in chosen_idea
        assert "novelty_score" in chosen_idea

        # 2. Select idea
        res_sel = client.post(
            f"/api/projects/{TEST_EP_ID}/ideas/select",
            json={"idea": chosen_idea},
        )
        assert res_sel.status_code == 200
        updated_proj = res_sel.json()
        assert updated_proj["stage_statuses"]["01_idea"] == "APPROVED"
        assert updated_proj["next_action"]["stage_id"] == "02_story"
        assert updated_proj["title"] == chosen_idea["title"]

        # Verify premise.txt saved
        premise_file = PROJECTS_DIR / TEST_EP_ID / "story" / "premise.txt"
        assert premise_file.exists()
        content = premise_file.read_text(encoding="utf-8")
        assert chosen_idea["title"] in content

        story_res = client.get(f"/api/projects/{TEST_EP_ID}/story")
        assert story_res.status_code == 200
        assert story_res.json()["premise"] == chosen_idea["premise"]

        project_json = json.loads((PROJECTS_DIR / TEST_EP_ID / "project.json").read_text(encoding="utf-8"))
        assert project_json["topic"] == chosen_idea["premise"]
        assert project_json["selected_idea"]["idea_id"] == chosen_idea["idea_id"]

        refreshed = client.get(f"/api/projects/{TEST_EP_ID}")
        assert refreshed.status_code == 200
        assert refreshed.json()["title"] == chosen_idea["title"]
        assert refreshed.json()["next_action"]["stage_id"] == "02_story"


# ============================================================================
# 4. OPTION B: STORY BIBLE GENERATION & APPROVAL GATE
# ============================================================================

def test_story_bible_generation_and_approval():
    """Tests generating Story Bible from topic and enforcing approval gate."""
    pm = ProjectManager()
    pm.create_project(
        episode_id=TEST_EP_ID,
        title="Tập Phim Thử Nghiệm",
        premise="Người cháu phát hiện lá thư tống tiền năm 1990 gửi cho ông nội.",
    )

    with patch.object(GenerationService, "get_provider", return_value=MockScriptAIProvider()):
        # 1. Generate Story Bible
        res_gen = client.post(
            f"/api/projects/{TEST_EP_ID}/story/generate",
            json={"topic": "Lá thư tống tiền năm 1990 gửi cho ông nội quá cố"},
        )
        assert res_gen.status_code == 200
        bible = res_gen.json()
        assert "premise" in bible
        assert "characters" in bible
        assert "reveal_1" in bible
        assert "reveal_2" in bible
        assert "fact_lock" in bible

        # Verify story_bible.json exists
        bible_file = PROJECTS_DIR / TEST_EP_ID / "story" / "story_bible.json"
        assert bible_file.exists()

        story_reload = client.get(f"/api/projects/{TEST_EP_ID}/story")
        assert story_reload.status_code == 200
        assert story_reload.json()["premise"]
        assert story_reload.json()["fact_lock_items"]

        # Check stage status updated to REVIEW_REQUIRED / NEEDS_REVIEW
        proj = pm.get_project(TEST_EP_ID)
        assert proj.stage_statuses["02_story"] in ["NEEDS_REVIEW", "IN_PROGRESS"]

        # 2. Approve Story Bible
        res_app = client.post(f"/api/projects/{TEST_EP_ID}/story/approve")
        assert res_app.status_code == 200
        proj_approved = pm.get_project(TEST_EP_ID)
        assert proj_approved.stage_statuses["02_story"] == "APPROVED"


def test_story_endpoint_accepts_list_fact_lock():
    """AI output may serialize fact_lock as a list; Story must still load."""
    pm = ProjectManager()
    pm.create_project(episode_id=TEST_EP_ID, title="List Fact Lock")
    bible_file = PROJECTS_DIR / TEST_EP_ID / "story" / "story_bible.json"
    bible_file.write_text(
        json.dumps({"premise": "Một bí mật gia đình.", "fact_lock": ["Thư viết năm 1990", "Người cha đã mất"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    response = client.get(f"/api/projects/{TEST_EP_ID}/story")
    assert response.status_code == 200
    assert response.json()["fact_lock_items"] == ["Thư viết năm 1990", "Người cha đã mất"]


# ============================================================================
# 5. SCRIPT GENERATION, QC, AUTO-REPAIR & APPROVAL GATE
# ============================================================================

def test_script_generation_enforces_story_bible():
    """Verify that script generation cannot proceed if Story Bible is missing."""
    pm = ProjectManager()
    pm.create_project(episode_id=TEST_EP_ID, title="No Bible Ep")

    # Attempting to generate script without Story Bible should fail with 400
    res = client.post(
        f"/api/projects/{TEST_EP_ID}/script/generate",
        json={"force": False},
    )
    assert res.status_code == 400
    assert "Story Bible" in res.json()["detail"]


def test_script_generation_and_auto_repair_flow():
    """Tests writing full script with Script Factory V1.3.1a, running QC, and auto-repair."""
    pm = ProjectManager()
    pm.create_project(episode_id=TEST_EP_ID, title="Full Script Test")

    with patch.object(GenerationService, "get_provider", return_value=MockScriptAIProvider()):
        # 1. Generate and approve Story Bible first
        client.post(
            f"/api/projects/{TEST_EP_ID}/story/generate",
            json={"topic": "Bí mật chiếc hộp đồng cổ"},
        )
        client.post(f"/api/projects/{TEST_EP_ID}/story/approve")

        # 2. Generate Full Script
        res_script = client.post(
            f"/api/projects/{TEST_EP_ID}/script/generate",
            json={"force": False},
        )
        assert res_script.status_code == 200
        script_data = res_script.json()
        assert "script" in script_data
        assert "qc_report" in script_data
        assert "stats" in script_data

        segments = script_data["script"]["segments"]
        assert len(segments) >= 40
        # Check delivery profiles include diverse archetypes
        profiles = {s.get("delivery_profile") for s in segments}
        assert len(profiles) >= 3

        # Verify files created on disk
        script_file = PROJECTS_DIR / TEST_EP_ID / "script" / "full_script.json"
        qc_file = PROJECTS_DIR / TEST_EP_ID / "script" / "qc_report.json"
        assert script_file.exists()
        assert qc_file.exists()

        # 3. Test Auto Repair
        res_repair = client.post(f"/api/projects/{TEST_EP_ID}/script/repair")
        assert res_repair.status_code == 200
        repair_res = res_repair.json()
        assert "qc_status" in repair_res
        assert "rounds" in repair_res

        # 4. Mock lineage must not be approved as a production/current script.
        res_app = client.post(f"/api/projects/{TEST_EP_ID}/script/approve")
        assert res_app.status_code == 400
        assert "STALE" in res_app.json()["detail"]
        proj = pm.get_project(TEST_EP_ID)
        assert proj.stage_statuses["03_script"] == "NEEDS_REVIEW"


def test_import_existing_script_text():
    """Tests Option C: importing raw text as an existing script."""
    pm = ProjectManager()
    pm.create_project(episode_id=TEST_EP_ID, title="Import Script Ep")

    raw_text = (
        "Đêm hôm đó, tiếng gõ cửa vang lên dồn dập giữa cơn mưa lớn.\n\n"
        "Bà Năm run rẩy bước ra mở cửa và thấy một chiếc túi xách đen bị bỏ lại trước thềm.\n\n"
        "Hóa ra, bên trong chiếc túi là toàn bộ sự thật về vụ mất tích 20 năm trước.\n\n"
        "Gia đình cuối cùng cũng tìm lại được sự bình yên sau bao năm dằn vặt."
    )

    res = client.post(
        f"/api/projects/{TEST_EP_ID}/script/import-text",
        json={"text": raw_text},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 4
    assert len(data["segments"]) == 4
    # First segment should be HOOK
    assert data["segments"][0]["delivery_profile"] == "HOOK"
    # Third segment mentions 'sự thật' -> REVEAL
    assert data["segments"][2]["delivery_profile"] == "REVEAL"


# ============================================================================
# 6. REGRESSION VERIFICATION FOR EP003 AND EP011
# ============================================================================

def test_regression_ep003_and_ep011_intact():
    """Ensures EP003 and EP011 remain completely intact and unaffected by V1.1 changes."""
    for ep_id in ["EP003", "EP011"]:
        # 1. Project details
        p_res = client.get(f"/api/projects/{ep_id}")
        assert p_res.status_code == 200
        p_data = p_res.json()
        assert p_data["project_id"] == ep_id
        assert p_data["scene_count"] == 45

        # 2. Story Bible
        s_res = client.get(f"/api/projects/{ep_id}/story")
        assert s_res.status_code == 200
        s_data = s_res.json()
        assert len(s_data["premise"]) > 20
        assert len(s_data["reveal_1"]) > 10
        assert len(s_data["reveal_2"]) > 10

        # 3. Script
        sc_res = client.get(f"/api/projects/{ep_id}/script")
        assert sc_res.status_code == 200
        assert len(sc_res.json()) in [45, 90]

        # 4. Audio
        a_res = client.get(f"/api/projects/{ep_id}/audio")
        assert a_res.status_code == 200
        assert a_res.json()["available"] is True
