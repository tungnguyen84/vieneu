"""Project-aware SCC_FLOW_V1 export service."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from apps.visual_pilot_03_v1_0a.google_flow_exporter import (
    SCHEMA_VERSION,
    build_episode_export,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
VISUAL_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a"
EXPORTS_DIR = VISUAL_DIR / "exports"


class FlowService:
    def export_path(self, project_id: str) -> Path:
        return EXPORTS_DIR / f"{project_id}_google_flow.json"

    def _plan_stats(self, project_id: str) -> Dict[str, int]:
        export_file = self.export_path(project_id)
        if export_file.exists():
            data = json.loads(export_file.read_text(encoding="utf-8"))
            episodes = data.get("episodes") or []
            episode = episodes[0] if episodes else {}
            scenes = episode.get("scenes") or []
            characters = episode.get("characters") or []
            props = episode.get("props") or []
            return {
                "scenes": len(scenes),
                "images": sum(1 for scene in scenes if scene.get("visual_mode") == "IMAGE_ONLY"),
                "videos": sum(1 for scene in scenes if scene.get("visual_mode") == "VIDEO_RECOMMENDED"),
                "characters": sum(1 for item in characters if item.get("reference_required")),
                "props": sum(1 for item in props if item.get("reference_required")),
            }
        plan_path = VISUAL_DIR / project_id / "visual_plan.json"
        if not plan_path.exists():
            return {"scenes": 0, "images": 0, "videos": 0, "characters": 0, "props": 0}
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        scenes = plan.get("scenes") or []
        return {
            "scenes": len(scenes),
            "images": sum(1 for scene in scenes if scene.get("visual_mode") == "IMAGE_ONLY"),
            "videos": sum(1 for scene in scenes if scene.get("visual_mode") == "VIDEO_RECOMMENDED"),
            "characters": 0,
            "props": 0,
        }

    def get_export_info(self, project_id: str) -> Dict[str, Any]:
        export_file = self.export_path(project_id)
        plan_ready = (VISUAL_DIR / project_id / "visual_plan.json").exists()
        stats = {
            **self._plan_stats(project_id),
            "schema_version": SCHEMA_VERSION,
            "export_status": (
                "GOOGLE_FLOW_EXPORT_READY" if export_file.exists()
                else "READY_FOR_EXPORT" if plan_ready
                else "WAITING_FOR_VISUAL_PLAN"
            ),
            "export_file_path": str(export_file) if export_file.exists() else None,
        }
        scene_count = stats["scenes"] or "các"
        instructions = [
            "Mở Google Flow App trên trình duyệt.",
            "Nhấn Import JSON và chọn đúng file của tập này.",
            "Tạo và duyệt Character References theo thứ tự anchor rồi tới biến thể.",
            f"Tạo và duyệt nội dung cho {scene_count} phân cảnh.",
            "Xuất Production ZIP từ Google Flow App.",
            "Quay lại Studio và nhập ZIP tại tab Assets.",
        ]
        return {
            "project_id": project_id,
            "stats": stats,
            "instructions": instructions,
            "is_exported": export_file.exists(),
            "is_ready": plan_ready,
        }

    def _validate(self, package: Dict[str, Any], project_id: str) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if package.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"schema_version phải là {SCHEMA_VERSION}")
        episodes = package.get("episodes") or []
        if len(episodes) != 1:
            errors.append("Gói xuất từng tập phải có đúng một episode")
            return False, errors
        episode = episodes[0]
        if episode.get("episode_id") != project_id:
            errors.append("episode_id không khớp với dự án đang xuất")
        scenes = episode.get("scenes") or []
        if not scenes:
            errors.append("Visual Plan chưa có phân cảnh")
            return False, errors
        seen_ids = set()
        character_ids = {item.get("character_id") for item in episode.get("characters") or []}
        for index, scene in enumerate(scenes):
            scene_id = scene.get("scene_id")
            if not scene_id or scene_id in seen_ids:
                errors.append(f"scene_id thiếu hoặc trùng tại vị trí {index + 1}")
            seen_ids.add(scene_id)
            if len(str(scene.get("image_prompt") or "").strip()) < 20:
                errors.append(f"{scene_id}: image_prompt quá ngắn")
            if scene.get("visual_mode") == "VIDEO_RECOMMENDED":
                video_prompt = scene.get("video_prompt") or {}
                if not str(video_prompt.get("full_prompt") or "").strip():
                    errors.append(f"{scene_id}: thiếu video_prompt")
            if scene.get("image_media_id") is not None or scene.get("video_media_id") is not None:
                errors.append(f"{scene_id}: media ID phải để trống trước khi import")
            if scene.get("generation_dependencies_satisfied") is not False:
                errors.append(f"{scene_id}: trạng thái dependency ban đầu phải là false")
            if index and round(float(scenes[index - 1].get("end_time", 0)), 3) != round(float(scene.get("start_time", 0)), 3):
                errors.append(f"Timeline bị hở trước {scene_id}")
        for character in episode.get("characters") or []:
            dependency = character.get("depends_on_reference")
            if dependency and dependency not in character_ids:
                errors.append(f"{character.get('character_id')}: thiếu anchor {dependency}")
            if character.get("reference_media_id") is not None:
                errors.append(f"{character.get('character_id')}: reference_media_id phải để trống")
        for prop in episode.get("props") or []:
            if prop.get("reference_media_id") is not None:
                errors.append(f"{prop.get('prop_id')}: reference_media_id phải để trống")
        audio_duration = float(episode.get("audio_duration") or 0)
        if audio_duration and abs(float(scenes[-1].get("end_time", 0)) - audio_duration) > 0.1:
            errors.append("Mốc kết thúc timeline không khớp thời lượng audio")
        return not errors, errors

    def run_export(self, project_id: str) -> Dict[str, Any]:
        plan_dir = VISUAL_DIR / project_id
        required = ["visual_plan.json", "character_bible.json", "prop_bible.json", "location_bible.json", "overlay_plan.json"]
        missing = [name for name in required if not (plan_dir / name).exists()]
        if missing:
            raise FileNotFoundError(
                "Chưa thể xuất Google Flow: Visual Plan của tập chưa hoàn chỉnh (thiếu " + ", ".join(missing) + ")"
            )
        episode = build_episode_export(project_id)
        package = {
            "schema_version": SCHEMA_VERSION,
            "project": {
                "series": "Sau Cánh Cửa",
                "production_id": project_id,
                "exported_at": round(time.time(), 3),
                "export_status": "GOOGLE_FLOW_EXPORT_READY",
            },
            "episodes": [episode],
        }
        valid, errors = self._validate(package, project_id)
        if not valid:
            raise ValueError("Google Flow JSON không đạt kiểm định:\n" + "\n".join(errors))
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.export_path(project_id).write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**self.get_export_info(project_id), "validation": {"status": "PASS", "errors": []}}
