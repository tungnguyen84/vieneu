import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.script_factory.models import QCReport
from studio.backend.services import audio_service as audio_module
from studio.backend.services import generation_service as generation_module
from studio.backend.services.artifact_lineage import (
    STALE_LABEL,
    mark_full_script_stale,
    story_content_hash,
    validate_full_script,
)
from studio.backend.services.audio_service import AudioService
from studio.backend.services.generation_service import GenerationService
from tests.mocks.mock_script_provider import MockScriptAIProvider


STORY_REQUEST = "11111111-1111-4111-8111-111111111111"
SCRIPT_REQUEST = "22222222-2222-4222-8222-222222222222"


def _write_current_artifacts(root: Path, project_id: str = "EP3001") -> Path:
    project = root / project_id
    (project / "story").mkdir(parents=True)
    (project / "script").mkdir(parents=True)
    story = {
        "episode_id": project_id,
        "title": "Bí mật ngoại tình công sở",
        "protagonist": {"name": "Nam", "char_id": "NAM"},
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
        "host": {"id": "MINH", "name": "Minh", "voice": "Binh"},
        "segments": [
            {"id": "001", "speaker": "MINH", "text": "Một lá thư mới vừa được gửi tới.", "delivery_profile": "HOOK"},
            {"id": "002", "speaker": "MINH", "text": "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "delivery_profile": "ENDING"},
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
        for mutation in ("lineage", "idea_lineage", "source", "leakage", "premature_signoff", "empty"):
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
                elif mutation == "premature_signoff":
                    script["segments"].insert(1, {
                        "id": "002",
                        "speaker": "MINH",
                        "text": "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
                        "delivery_profile": "ENDING",
                    })
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

    def test_recheck_promotes_a_qc_passed_script_back_to_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = _write_current_artifacts(root)
            script_path = project / "script" / "full_script.json"
            script = json.loads(script_path.read_text())
            script.update({"artifact_status": "NEEDS_REVISION", "revision_round": 3})
            script["segments"] = [
                {"id": "001", "speaker": "MINH", "text": "Một lá thư cụ thể mở ra nghi vấn về gia đình Nam.", "delivery_profile": "HOOK"},
                {"id": "002", "speaker": "MINH", "text": "Quý vị sẽ chọn cách nào để tìm hiểu?", "delivery_profile": "COMMENT", "audience_address": True},
                {"id": "003", "speaker": "MINH", "text": "Quý vị có từng gặp một dấu hiệu như vậy?", "delivery_profile": "COMMENT", "audience_address": True},
                {"id": "004", "speaker": "MINH", "text": "Chúng ta cùng theo dõi câu chuyện.", "delivery_profile": "COMMENT", "audience_address": True},
                {"id": "005", "speaker": "MINH", "text": "Một chứng cứ xác thực đã làm rõ sự thật.", "delivery_profile": "REVEAL", "importance": "critical"},
                {"id": "006", "speaker": "MINH", "text": "Gia đình ngồi lại và bình tĩnh giải quyết biến cố.", "delivery_profile": "NORMAL"},
                {"id": "007", "speaker": "MINH", "text": "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "delivery_profile": "ENDING"},
            ]
            script_path.write_text(json.dumps(script), encoding="utf-8")
            (project / "project.json").write_text(json.dumps({
                "project_id": "EP3001",
                "selected_idea": {"idea_id": "IDEA_3001"},
                "script_artifact_status": "NEEDS_REVISION",
                "qc_status": "NEEDS_REVISION",
            }), encoding="utf-8")

            original_projects_dir = generation_module.PROJECTS_DIR
            generation_module.PROJECTS_DIR = root
            service = GenerationService()
            service.get_provider = lambda provider_id=None, model_id=None: MockScriptAIProvider()
            try:
                pass_report = QCReport(episode_id="EP3001", status="PASS")
                with patch.object(generation_module.ScriptQCEngine, "run_qc", return_value=pass_report):
                    result = service.auto_repair_script("EP3001")
            finally:
                generation_module.PROJECTS_DIR = original_projects_dir

            saved_script = json.loads(script_path.read_text(encoding="utf-8"))
            saved_project = json.loads((project / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(result["qc_status"], "PASS")
            self.assertEqual(saved_script["artifact_status"], "CURRENT")
            self.assertEqual(saved_project["script_artifact_status"], "CURRENT")
            self.assertEqual(saved_project["qc_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
