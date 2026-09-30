import json
import tempfile
import unittest
from pathlib import Path

from studio.backend.services import audio_service as audio_module
from studio.backend.services.artifact_lineage import (
    STALE_LABEL,
    mark_full_script_stale,
    story_content_hash,
    validate_full_script,
)
from studio.backend.services.audio_service import AudioService


STORY_REQUEST = "11111111-1111-4111-8111-111111111111"
SCRIPT_REQUEST = "22222222-2222-4222-8222-222222222222"


def _write_current_artifacts(root: Path, project_id: str = "EP3001") -> Path:
    project = root / project_id
    (project / "story").mkdir(parents=True)
    (project / "script").mkdir(parents=True)
    story = {
        "episode_id": project_id,
        "title": "Bí mật ngoại tình công sở",
        "generation_source": "REAL_AI",
        "generation_request_id": STORY_REQUEST,
        "prompt_version": "story-v3.0",
        "model_name": "gemini-2.5-flash",
        "source_idea_id": "IDEA_3001",
        "secret": "Một bí mật trong phòng kế toán.",
    }
    script = {
        "episode_id": project_id,
        "title": story["title"],
        "generation_source": "REAL_AI",
        "generation_request_id": SCRIPT_REQUEST,
        "prompt_version": "script-v3.0",
        "model_name": "gemini-2.5-flash",
        "provider_name": "GeminiScriptAIProvider",
        "source_story_generation_request_id": STORY_REQUEST,
        "source_story_content_hash": story_content_hash(story),
        "artifact_status": "CURRENT",
        "segments": [
            {"id": "001", "speaker": "MINH", "text": "Một lá thư mới vừa được gửi tới.", "delivery_profile": "HOOK"}
        ],
    }
    (project / "story" / "story_bible.json").write_text(json.dumps(story), encoding="utf-8")
    (project / "script" / "full_script.json").write_text(json.dumps(script), encoding="utf-8")
    (project / "project.json").write_text(json.dumps({
        "project_id": project_id,
        "selected_idea": {"idea_id": "IDEA_3001", "title": story["title"]},
    }), encoding="utf-8")
    return project


class StudioLineageGuardTests(unittest.TestCase):
    def test_current_script_requires_matching_real_ai_story_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_current_artifacts(root)
            status = validate_full_script("EP3001", root)
            self.assertTrue(status["is_current"])
            self.assertEqual(status["leakage_count"], 0)
            self.assertEqual(status["generation_request_id"], SCRIPT_REQUEST)

    def test_story_regeneration_marks_previously_approved_script_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _write_current_artifacts(root)
            mark_full_script_stale("EP3001", root, "Story Bible was regenerated")
            status = validate_full_script("EP3001", root)
            saved = json.loads((project / "script" / "full_script.json").read_text())
            self.assertEqual(status["status_label"], STALE_LABEL)
            self.assertFalse(status["is_current"])
            self.assertEqual(saved["artifact_status"], "STALE")

    def test_audio_fails_fast_for_invalid_script(self):
        for mutation in ("lineage", "idea_lineage", "source", "leakage", "empty"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = _write_current_artifacts(root)
                script_path = project / "script" / "full_script.json"
                script = json.loads(script_path.read_text())
                if mutation == "lineage":
                    script["source_story_generation_request_id"] = "33333333-3333-4333-8333-333333333333"
                elif mutation == "idea_lineage":
                    project_data = json.loads((project / "project.json").read_text())
                    project_data["selected_idea"]["idea_id"] = "IDEA_3002"
                    (project / "project.json").write_text(json.dumps(project_data), encoding="utf-8")
                elif mutation == "source":
                    script["generation_source"] = "MOCK"
                elif mutation == "leakage":
                    script["segments"][0]["text"] = "Nhân vật chính tìm Manh mối 2 và Bước ngoặt 1 trị giá 100.000.000 VND."
                else:
                    script["segments"] = []
                script_path.write_text(json.dumps(script), encoding="utf-8")
                original_projects_dir = audio_module.PROJECTS_DIR
                audio_module.PROJECTS_DIR = root
                try:
                    with self.assertRaisesRegex(ValueError, "STALE"):
                        AudioService().generate_narration("EP3001", "020")
                finally:
                    audio_module.PROJECTS_DIR = original_projects_dir


if __name__ == "__main__":
    unittest.main()
