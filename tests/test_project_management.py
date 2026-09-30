import json
import sqlite3
from pathlib import Path

import pytest

import studio.backend.project_manager as project_manager_module
from studio.backend.project_manager import ProjectManager


def _create_test_db(path: Path, project_id: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                series_id TEXT NOT NULL,
                episode_number TEXT NOT NULL,
                duration_sec REAL DEFAULT 0.0,
                scene_count INTEGER DEFAULT 45,
                image_count INTEGER DEFAULT 38,
                video_count INTEGER DEFAULT 7,
                stage_statuses TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                is_archived INTEGER DEFAULT 0
            );
            CREATE TABLE jobs (job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL);
            CREATE TABLE approvals (id INTEGER PRIMARY KEY, project_id TEXT NOT NULL);
            CREATE TABLE render_history (render_id TEXT PRIMARY KEY, project_id TEXT NOT NULL);
            """
        )
        conn.execute(
            """
            INSERT INTO projects (
                project_id, title, series_id, episode_number, stage_statuses,
                created_at, updated_at
            ) VALUES (?, 'Tên cũ', 'SAU_CANH_CUA', ?, ?, 1, 1)
            """,
            (
                project_id,
                project_id,
                json.dumps(
                    {
                        "01_idea": "APPROVED",
                        "02_story": "APPROVED",
                        "03_script": "NEEDS_REVIEW",
                    }
                ),
            ),
        )
        conn.execute("INSERT INTO jobs VALUES ('job-1', ?)", (project_id,))
        conn.execute("INSERT INTO approvals VALUES (1, ?)", (project_id,))
        conn.execute("INSERT INTO render_history VALUES ('render-1', ?)", (project_id,))


@pytest.fixture
def isolated_project_manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    project_id = "EP_MANAGEMENT_TEST"
    db_path = tmp_path / "studio_data.db"
    projects_dir = tmp_path / "projects"
    audio_dir = tmp_path / "production_pilot_03"
    visual_dir = tmp_path / "production_pilot_03_visual_v1_0a"
    exports_dir = visual_dir / "exports"

    _create_test_db(db_path, project_id)
    project_dir = projects_dir / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps({"project_id": project_id, "title": "Tên cũ"}, ensure_ascii=False),
        encoding="utf-8",
    )
    for root in (audio_dir, visual_dir):
        artifact_dir = root / project_id
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "artifact.txt").write_text("test", encoding="utf-8")
    exports_dir.mkdir(parents=True)
    (exports_dir / f"{project_id}_google_flow.json").write_text("{}", encoding="utf-8")

    def get_test_connection():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(project_manager_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(project_manager_module, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(project_manager_module, "PILOT_03_AUDIO", audio_dir)
    monkeypatch.setattr(project_manager_module, "PILOT_03_VISUAL", visual_dir)
    monkeypatch.setattr(project_manager_module, "EXPORTS_DIR", exports_dir)
    monkeypatch.setattr(project_manager_module, "get_db_connection", get_test_connection)

    manager = ProjectManager.__new__(ProjectManager)
    return manager, project_id, db_path, project_dir, audio_dir, visual_dir, exports_dir


def test_rename_project_updates_database_and_project_file(isolated_project_manager):
    manager, project_id, db_path, project_dir, *_ = isolated_project_manager

    updated = manager.rename_project(project_id, "  Tên kịch bản   mới  ")

    assert updated.title == "Tên kịch bản mới"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT title FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()[0] == "Tên kịch bản mới"
    stored = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert stored["title"] == "Tên kịch bản mới"
    assert stored["updated_at"] == updated.updated_at


def test_delete_project_removes_database_rows_and_generated_artifacts(
    isolated_project_manager,
):
    manager, project_id, db_path, project_dir, audio_dir, visual_dir, exports_dir = (
        isolated_project_manager
    )

    result = manager.delete_project(project_id)

    assert result["deleted"] is True
    assert not project_dir.exists()
    assert not (audio_dir / project_id).exists()
    assert not (visual_dir / project_id).exists()
    assert not (exports_dir / f"{project_id}_google_flow.json").exists()
    with sqlite3.connect(db_path) as conn:
        for table in ("projects", "jobs", "approvals", "render_history"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE project_id = ?", (project_id,)
            ).fetchone()[0]
            assert count == 0


def test_delete_project_rejects_reference_episodes():
    manager = ProjectManager.__new__(ProjectManager)
    with pytest.raises(ValueError, match="tập tham chiếu"):
        manager.delete_project("EP003")
