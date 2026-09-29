"""Project Manager and Migration Engine for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from studio.backend.db import get_db_connection
from studio.backend.models import NextAction, ProjectMetadata, StageId, StageStatus

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"
PILOT_03_VISUAL = BASE_DIR / "production_pilot_03_visual_v1_0a"
PILOT_02_SCRIPTS = BASE_DIR / "pilot_02_v1_3_1a"
EXPORTS_DIR = PILOT_03_VISUAL / "exports"


def compute_next_action(statuses: Dict[str, StageStatus], ep_id: str) -> NextAction:
    """Calculates the single most important next action for the creator."""
    if statuses.get(StageId.SCRIPT) != StageStatus.APPROVED:
        return NextAction(
            stage_id=StageId.SCRIPT,
            title="Duyệt kịch bản",
            description="Kiểm tra thông số QC kịch bản và nhấn Duyệt để chuyển sang Audio.",
            action_type="NAVIGATE",
            button_label="MỞ KỊCH BẢN",
            target_route="/script"
        )
    if statuses.get(StageId.AUDIO) not in [StageStatus.COMPLETE, StageStatus.APPROVED]:
        return NextAction(
            stage_id=StageId.AUDIO,
            title="Chuẩn bị Audio Narration",
            description="Tạo TTS với Audio Formula V1 hoặc Import file âm thanh bản thu.",
            action_type="NAVIGATE",
            button_label="MỞ AUDIO",
            target_route="/audio"
        )
    if statuses.get(StageId.VISUAL) != StageStatus.APPROVED:
        return NextAction(
            stage_id=StageId.VISUAL,
            title="Duyệt Visual Storyboard",
            description="Kiểm tra 45 scenes và danh sách nhân vật/bối cảnh trước khi xuất.",
            action_type="NAVIGATE",
            button_label="DUYỆT VISUAL PLAN",
            target_route="/visual"
        )
    if statuses.get(StageId.FLOW) not in [StageStatus.COMPLETE, StageStatus.APPROVED]:
        return NextAction(
            stage_id=StageId.FLOW,
            title="Xuất JSON cho Google Flow",
            description="Visual Plan đã duyệt. Xuất file SCC_FLOW_V1 JSON để tạo ảnh và video bên ngoài.",
            action_type="EXPORT_FLOW",
            button_label="XUẤT GOOGLE FLOW JSON",
            target_route="/flow"
        )
    if statuses.get(StageId.ASSETS) not in [StageStatus.COMPLETE, StageStatus.APPROVED]:
        return NextAction(
            stage_id=StageId.ASSETS,
            title="Import Production ZIP từ Google Flow",
            description="Kéo thả file ZIP chứa 45 ảnh và video đã tạo vào studio để kiểm định.",
            action_type="IMPORT_ZIP",
            button_label="IMPORT PRODUCTION ZIP",
            target_route="/assets"
        )
    if statuses.get(StageId.RENDER) != StageStatus.COMPLETE:
        return NextAction(
            stage_id=StageId.RENDER,
            title="Render Final Video",
            description="Tài nguyên đã sẵn sàng. Chạy Auto Assembler V9.3.2 và Dynamic Still.",
            action_type="RENDER",
            button_label="RENDER FINAL VIDEO",
            target_route="/render"
        )
    return NextAction(
        stage_id=StageId.QC,
        title="Kiểm định Final QC & Xuất bản",
        description="Video đã hoàn tất. Xem báo cáo độ lệch A/V delta, loudness LUFS và lưu trữ.",
        action_type="NAVIGATE",
        button_label="XEM BÁO CÁO QC",
        target_route="/qc"
    )


class ProjectManager:
    def __init__(self):
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        self.auto_migrate_pilots()

    def auto_migrate_pilots(self) -> None:
        """Discovers and migrates existing EP003 and EP011 into the Studio DB."""
        pilots = [
            {
                "id": "EP003",
                "idea_id": "IDEA_003",
                "title": "Chiếc Hộp Gỗ Của Người Bà Quá Cố",
                "duration": 288.75,
                "scenes": 45,
                "images": 38,
                "videos": 7
            },
            {
                "id": "EP011",
                "idea_id": "IDEA_011",
                "title": "Bức Ảnh Lạ Trong Điện Thoại Cũ",
                "duration": 285.34,
                "scenes": 45,
                "images": 37,
                "videos": 8
            }
        ]

        with get_db_connection() as conn:
            cursor = conn.cursor()
            for p in pilots:
                pid = p["id"]
                cursor.execute("SELECT project_id FROM projects WHERE project_id = ?", (pid,))
                row = cursor.fetchone()
                
                # Check real file artifacts to determine stage
                flow_json_exists = (EXPORTS_DIR / f"{pid}_google_flow.json").exists()
                visual_exists = (PILOT_03_VISUAL / pid / "visual_plan.json").exists()
                audio_exists = (PILOT_03_AUDIO / pid / "audio_master").exists() or (PILOT_03_AUDIO / pid).exists()
                script_exists = (PILOT_02_SCRIPTS / p["idea_id"]).exists()

                statuses = {
                    StageId.IDEA.value: StageStatus.APPROVED.value,
                    StageId.STORY.value: StageStatus.APPROVED.value,
                    StageId.SCRIPT.value: StageStatus.APPROVED.value if script_exists else StageStatus.NOT_STARTED.value,
                    StageId.AUDIO.value: StageStatus.COMPLETE.value if audio_exists else StageStatus.NOT_STARTED.value,
                    StageId.VISUAL.value: StageStatus.APPROVED.value if visual_exists else StageStatus.NOT_STARTED.value,
                    StageId.FLOW.value: StageStatus.APPROVED.value if flow_json_exists else StageStatus.NOT_STARTED.value,
                    StageId.ASSETS.value: StageStatus.NEEDS_REVIEW.value,
                    StageId.TIMELINE.value: StageStatus.APPROVED.value if visual_exists else StageStatus.NOT_STARTED.value,
                    StageId.RENDER.value: StageStatus.NOT_STARTED.value,
                    StageId.QC.value: StageStatus.NOT_STARTED.value,
                }

                now = time.time()
                if not row:
                    cursor.execute("""
                        INSERT INTO projects (
                            project_id, title, series_id, episode_number,
                            duration_sec, scene_count, image_count, video_count,
                            stage_statuses, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        pid, p["title"], "SAU_CANH_CUA", pid,
                        p["duration"], p["scenes"], p["images"], p["videos"],
                        json.dumps(statuses), now, now
                    ))
            conn.commit()

    def list_projects(self) -> List[ProjectMetadata]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE is_archived = 0 ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            projects = []
            for r in rows:
                raw_statuses = json.loads(r["stage_statuses"])
                statuses = {k: StageStatus(v) for k, v in raw_statuses.items()}
                next_act = compute_next_action(statuses, r["project_id"])
                projects.append(ProjectMetadata(
                    project_id=r["project_id"],
                    title=r["title"],
                    series_id=r["series_id"],
                    episode_number=r["episode_number"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    duration_sec=r["duration_sec"],
                    scene_count=r["scene_count"],
                    image_count=r["image_count"],
                    video_count=r["video_count"],
                    stage_statuses=statuses,
                    next_action=next_act,
                    is_archived=bool(r["is_archived"])
                ))
            return projects

    def get_project(self, project_id: str) -> Optional[ProjectMetadata]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE project_id = ?", (project_id,))
            r = cursor.fetchone()
            if not r:
                return None
            raw_statuses = json.loads(r["stage_statuses"])
            statuses = {k: StageStatus(v) for k, v in raw_statuses.items()}
            next_act = compute_next_action(statuses, project_id)
            return ProjectMetadata(
                project_id=r["project_id"],
                title=r["title"],
                series_id=r["series_id"],
                episode_number=r["episode_number"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                duration_sec=r["duration_sec"],
                scene_count=r["scene_count"],
                image_count=r["image_count"],
                video_count=r["video_count"],
                stage_statuses=statuses,
                next_action=next_act,
                is_archived=bool(r["is_archived"])
            )

    def update_stage_status(self, project_id: str, stage: StageId, status: StageStatus) -> ProjectMetadata:
        """Updates stage status and applies dependency cascade."""
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        statuses = proj.stage_statuses
        statuses[stage.value] = status

        # Cascade Rule:
        if stage == StageId.SCRIPT and status != StageStatus.APPROVED:
            statuses[StageId.AUDIO.value] = StageStatus.STALE
            statuses[StageId.VISUAL.value] = StageStatus.STALE
            statuses[StageId.FLOW.value] = StageStatus.STALE
            statuses[StageId.TIMELINE.value] = StageStatus.STALE
            statuses[StageId.RENDER.value] = StageStatus.STALE
        elif stage == StageId.AUDIO and status != StageStatus.COMPLETE:
            statuses[StageId.TIMELINE.value] = StageStatus.STALE
            statuses[StageId.RENDER.value] = StageStatus.STALE
        elif stage == StageId.VISUAL and status != StageStatus.APPROVED:
            statuses[StageId.FLOW.value] = StageStatus.STALE
            statuses[StageId.TIMELINE.value] = StageStatus.STALE

        serialized = json.dumps({k: v.value for k, v in statuses.items()})
        now = time.time()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE projects SET stage_statuses = ?, updated_at = ? WHERE project_id = ?",
                (serialized, now, project_id)
            )
            cursor.execute(
                "INSERT INTO approvals (project_id, stage_id, status, timestamp) VALUES (?, ?, ?, ?)",
                (project_id, stage.value, status.value, now)
            )
            conn.commit()

        return self.get_project(project_id)  # type: ignore

    def export_archive(self, project_id: str, full: bool = False) -> Path:
        """Exports .sccproject portable zip package."""
        proj = self.get_project(project_id)
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        archive_dir = BASE_DIR / "reports" / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        suffix = "full" if full else "light"
        out_zip = archive_dir / f"{project_id}_{suffix}_{int(time.time())}.sccproject"

        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            # Metadata
            zf.writestr("project.json", proj.model_dump_json(indent=2))

            # Visual plan artifacts
            vis_dir = PILOT_03_VISUAL / project_id
            if vis_dir.exists():
                for f in vis_dir.glob("*.json"):
                    zf.write(f, arcname=f"visual/{f.name}")

            # Flow export JSON
            flow_json = EXPORTS_DIR / f"{project_id}_google_flow.json"
            if flow_json.exists():
                zf.write(flow_json, arcname=f"flow/{flow_json.name}")

            # Include media if full
            if full:
                # Include audio master
                aud_dir = PILOT_03_AUDIO / project_id
                if aud_dir.exists():
                    for f in aud_dir.glob("*.*"):
                        zf.write(f, arcname=f"audio/{f.name}")

        return out_zip
