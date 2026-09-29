"""Timeline Service for multi-track visual, overlay, and audio alignment."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
VISUAL_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"


class TimelineService:
    def __init__(self):
        pass

    def get_timeline_tracks(self, project_id: str) -> Dict[str, Any]:
        plan_path = VISUAL_DIR / project_id / "visual_plan.json"
        overlay_path = VISUAL_DIR / project_id / "overlay_plan.json"

        if not plan_path.exists():
            return {
                "total_duration_sec": 0.0,
                "tracks": [],
                "markers": []
            }

        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)

        total_duration = plan_data.get("audio_duration_sec", 288.75)

        # Track V1: Visual Scenes
        v1_blocks = []
        for s in plan_data.get("scenes", []):
            is_vid = (s.get("visual_mode") == "VIDEO_RECOMMENDED")
            v1_blocks.append({
                "id": s["scene_id"],
                "start": s["start_time"],
                "end": s["end_time"],
                "duration": s["duration"],
                "label": s["scene_id"],
                "type": "VIDEO" if is_vid else "IMAGE",
                "motion": "Ken Burns" if not is_vid else "Omni 5s Motion",
                "score": s.get("video_value_scores", {}).get("total_score", 0)
            })

        # Track V2: Overlays
        v2_blocks = []
        if overlay_path.exists():
            with open(overlay_path, "r", encoding="utf-8") as f:
                ov_data = json.load(f)
            for ov in ov_data.get("overlays", []):
                v2_blocks.append({
                    "id": f"ov_{ov['scene_id']}",
                    "start": ov["start_time"],
                    "end": ov["end_time"],
                    "duration": ov["duration"],
                    "label": ov.get("overlay_title", "Tài liệu"),
                    "text": ov.get("overlay_text", ""),
                    "type": "OVERLAY"
                })

        # Track A1: Narration Master
        a1_blocks = [{
            "id": "narration_master",
            "start": 0.0,
            "end": total_duration,
            "duration": total_duration,
            "label": f"Master Narration ({project_id})",
            "type": "AUDIO_MASTER"
        }]

        # Track A2: Music Bed
        a2_blocks = [
            {"id": "bgm_act1", "start": 0.0, "end": round(total_duration * 0.65, 2), "label": "BGM: Suspense Cold", "type": "MUSIC"},
            {"id": "bgm_act2", "start": round(total_duration * 0.65, 2), "end": total_duration, "label": "BGM: Dramatic Reveal", "type": "MUSIC"}
        ]

        markers = [
            {"name": "Hook", "time": 0.0, "color": "#3B82F6"},
            {"name": "Phát Hiện", "time": round(total_duration * 0.25, 2), "color": "#10B981"},
            {"name": "Reveal 1 (SC_031)", "time": round(total_duration * 0.65, 2), "color": "#F59E0B"},
            {"name": "Reveal 2 (SC_039)", "time": round(total_duration * 0.85, 2), "color": "#E11D48"},
            {"name": "Ending", "time": round(total_duration * 0.95, 2), "color": "#8B5CF6"}
        ]

        return {
            "project_id": project_id,
            "total_duration_sec": total_duration,
            "tracks": [
                {"id": "V2", "name": "V2 Overlays", "type": "OVERLAY", "blocks": v2_blocks},
                {"id": "V1", "name": "V1 Visuals", "type": "VISUAL", "blocks": v1_blocks},
                {"id": "A2", "name": "A2 Music", "type": "AUDIO", "blocks": a2_blocks},
                {"id": "A1", "name": "A1 Narration", "type": "AUDIO", "blocks": a1_blocks},
            ],
            "markers": markers
        }
