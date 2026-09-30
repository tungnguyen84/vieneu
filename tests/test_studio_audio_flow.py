import json
from pathlib import Path

import pytest

from studio.backend.services import audio_service as audio_module
from studio.backend.services import flow_service as flow_module
from studio.backend.services import script_service as script_module
from studio.backend.services import visual_service as visual_module
from studio.backend.services.audio_service import AudioService
from studio.backend.services.flow_service import FlowService
from studio.backend.services.script_service import ScriptService
from studio.backend.services.visual_service import VisualService
from studio.backend.services.artifact_lineage import story_content_hash


def _add_real_lineage(project: Path, script: dict) -> dict:
    story = {
        "episode_id": project.name,
        "title": "Tập kiểm thử",
        "generation_source": "REAL_AI",
        "generation_request_id": "11111111-1111-4111-8111-111111111111",
        "prompt_version": "story-test",
        "model_name": "gemini-test",
    }
    story_dir = project / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "story_bible.json").write_text(json.dumps(story), encoding="utf-8")
    script.update({
        "generation_source": "REAL_AI",
        "generation_request_id": "22222222-2222-4222-8222-222222222222",
        "source_story_generation_request_id": story["generation_request_id"],
        "source_story_content_hash": story_content_hash(story),
        "prompt_version": "script-test",
        "model_name": "gemini-test",
        "provider_name": "GeminiScriptAIProvider",
        "artifact_status": "CURRENT",
    })
    return script


def test_script_api_preserves_contextual_speed(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    script_dir = projects / "EP900" / "script"
    script_dir.mkdir(parents=True)
    (script_dir / "full_script.json").write_text(
        json.dumps({"segments": [{"id": "001", "text": "Một câu mở đầu.", "delivery_profile": "HOOK", "speed": 0.98}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(script_module, "PROJECTS_DIR", projects)

    segment = ScriptService().get_script_segments("EP900")[0]

    assert segment.delivery_profile == "HOOK"
    assert segment.speed == 0.98


def test_audio_generation_uses_segment_speeds_and_selected_voice(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    script_dir = projects / "EP900" / "script"
    script_dir.mkdir(parents=True)
    script = _add_real_lineage(projects / "EP900", {"segments": [
            {"id": "001", "speaker": "MINH", "text": "Mở đầu", "delivery_profile": "HOOK", "speed": 0.98},
            {"id": "002", "speaker": "MINH", "text": "Hé lộ", "delivery_profile": "REVEAL", "speed": 0.92},
        ]})
    (script_dir / "full_script.json").write_text(json.dumps(script), encoding="utf-8")
    monkeypatch.setattr(audio_module, "PROJECTS_DIR", projects)
    seen = []

    def fake_generate(engine, work_dir, segment, character):
        seen.append((segment["speed"], character["voice"]))
        selected = work_dir / "selected"
        selected.mkdir(parents=True, exist_ok=True)
        (selected / f"{segment['id']}.wav").write_bytes(b"wav")
        return True, "ok", {"selected_file": f"selected/{segment['id']}.wav", "status": "COMPLETED"}

    def fake_master(**kwargs):
        output = kwargs["project_dir"] / "episode_master.wav"
        output.write_bytes(b"master")
        return True, "ok", str(output), None

    service = AudioService()
    monkeypatch.setattr(service, "list_voices", lambda: {"voices": [{"voice_id": "020", "label": "020", "cloned": True}], "profile_speeds": {}})
    monkeypatch.setattr(service, "_get_engine", lambda: type("Engine", (), {"sample_rate": 48000})())
    monkeypatch.setattr(audio_module, "generate_single_segment_takes", fake_generate)
    monkeypatch.setattr(audio_module, "build_master_audio", fake_master)

    result = service.generate_narration("EP900", "020", contextual_speed=True)

    assert seen == [(0.98, "020"), (0.92, "020")]
    assert result["generation"]["segments"] == 2
    assert (projects / "EP900" / "audio" / "narration.wav").exists()


def _episode(project_id: str):
    return {
        "episode_id": project_id,
        "title": "Tập kiểm thử",
        "audio_duration": 10.0,
        "generation_settings": {},
        "identity_families": [],
        "characters": [{"character_id": "CHAR_A", "reference_required": True, "reference_media_id": None}],
        "props": [],
        "locations": [],
        "overlays": [],
        "scenes": [{
            "scene_id": "SC_001", "order": 1, "start_time": 0.0, "end_time": 10.0, "duration": 10.0,
            "visual_mode": "IMAGE_ONLY", "image_prompt": "Vietnamese cinematic documentary scene with soft natural light",
            "video_prompt": None, "image_media_id": None, "video_media_id": None,
            "generation_dependencies_satisfied": False,
        }],
    }


def test_flow_export_is_project_specific_and_validated(tmp_path, monkeypatch):
    visual_dir = tmp_path / "visual"
    project_dir = visual_dir / "EP900"
    project_dir.mkdir(parents=True)
    for name in ("visual_plan.json", "character_bible.json", "prop_bible.json", "location_bible.json", "overlay_plan.json"):
        (project_dir / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(flow_module, "VISUAL_DIR", visual_dir)
    monkeypatch.setattr(flow_module, "EXPORTS_DIR", visual_dir / "exports")
    monkeypatch.setattr(flow_module, "build_episode_export", _episode)

    result = FlowService().run_export("EP900")
    package = json.loads((visual_dir / "exports" / "EP900_google_flow.json").read_text(encoding="utf-8"))

    assert result["validation"]["status"] == "PASS"
    assert package["schema_version"] == "SCC_FLOW_V1"
    assert package["project"]["production_id"] == "EP900"
    assert package["episodes"][0]["episode_id"] == "EP900"


def test_flow_export_refuses_missing_visual_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_module, "VISUAL_DIR", tmp_path / "visual")
    monkeypatch.setattr(flow_module, "EXPORTS_DIR", tmp_path / "exports")

    with pytest.raises(FileNotFoundError, match="Visual Plan"):
        FlowService().run_export("EP999")


def test_visual_plan_is_built_from_current_project(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    visual = tmp_path / "visual"
    project = projects / "EP903"
    (project / "script").mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({"title": "Tập riêng"}), encoding="utf-8")
    (project / "story_bible.json").write_text(json.dumps({
        "protagonist": {"char_id": "THANH", "name": "Thanh", "age": 32, "description": "Người vợ đi tìm sự thật"},
        "supporting_characters": [{"char_id": "KHOA", "name": "Khoa", "age": 34, "description": "Người chồng giữ bí mật"}],
    }), encoding="utf-8")
    (project / "location_bible.json").write_text(json.dumps({"locations": ["Căn hộ của Thanh và Khoa", "Tiệm bánh của Hương"]}), encoding="utf-8")
    (project / "script" / "full_script.json").write_text(json.dumps({"segments": [
        {"id": f"{index:03d}", "text": f"Thanh phát hiện bí mật số {index} trong căn hộ.", "delivery_profile": "MYSTERY", "speed": 0.96}
        for index in range(1, 11)
    ]}), encoding="utf-8")
    audio = project / "audio" / "narration.wav"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio")
    monkeypatch.setattr(visual_module, "PROJECTS_DIR", projects)
    monkeypatch.setattr(visual_module, "VISUAL_DIR", visual)
    monkeypatch.setattr("studio.backend.services.audio_service.AudioService.get_audio_master_path", lambda self, project_id: audio)
    monkeypatch.setattr("soundfile.info", lambda path: type("Info", (), {"duration": 120.0})())

    result = VisualService().generate_visual_plan("EP903")
    plan = json.loads((visual / "EP903" / "visual_plan.json").read_text(encoding="utf-8"))

    assert result["scenes"] == 10
    assert plan["episode_id"] == "EP903"
    assert plan["audio_duration_sec"] == 120.0
    assert plan["scenes"][0]["image_prompt"]
    assert plan["scenes"][-1]["end_time"] == 120.0
    assert (visual / "EP903" / "character_bible.json").exists()


def test_auto_mix_bgm_creates_stems_and_cue_sheet(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    project = projects / "EP904"
    audio_dir = project / "audio"
    script_dir = project / "script"
    audio_dir.mkdir(parents=True)
    script_dir.mkdir(parents=True)

    # Mock voice wav (15 seconds)
    import numpy as np
    import soundfile as sf
    sr = 48000
    voice = (np.sin(2 * np.pi * 440 * np.linspace(0, 15, 15 * sr, endpoint=False)) * 0.1).astype(np.float32)
    voice_file = audio_dir / "narration.wav"
    sf.write(str(voice_file), voice, sr)

    # Script
    script = _add_real_lineage(project, {
        "episode_id": "EP904",
        "segments": [
            {"id": "001", "delivery_profile": "HOOK", "text": "Mở đầu kịch tính", "pause_after": 0.5},
            {"id": "002", "delivery_profile": "MYSTERY", "text": "Khám phá bí mật", "pause_after": 0.5},
            {"id": "003", "delivery_profile": "ENDING", "text": "Chiêm nghiệm kết thúc", "pause_after": 0.5},
        ]
    })
    (script_dir / "full_script.json").write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(audio_module, "PROJECTS_DIR", projects)
    srv = AudioService()

    info_before = srv.get_audio_info("EP904")
    assert info_before["available"] is True
    assert info_before["has_bgm"] is False

    result = srv.auto_mix_background_music("EP904", enable_ducking=True, target_lufs=-14.0)

    assert result["available"] is True
    assert result["has_bgm"] is True
    assert result["stems"]["final"] is True
    assert result["stems"]["dry"] is True
    assert result["stems"]["music"] is True
    assert (audio_dir / "final_mix.wav").exists()
    assert (audio_dir / "final_mix.mp3").exists()
    assert (audio_dir / "music_mix.wav").exists()
    assert (audio_dir / "music_cue_sheet.json").exists()
    assert (audio_dir / "narration_dry.wav").exists()

