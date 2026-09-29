"""Visual Plan Service for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from studio.backend.models import (
    CharacterItem,
    LocationItem,
    PropItem,
    SceneItem,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
VISUAL_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a"


class VisualService:
    def __init__(self):
        pass

    def get_scenes(self, project_id: str) -> List[SceneItem]:
        plan_path = VISUAL_DIR / project_id / "visual_plan.json"
        if not plan_path.exists():
            return []

        with open(plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenes = []
        for s in data.get("scenes", []):
            is_video = (s.get("visual_mode") == "VIDEO_RECOMMENDED")
            vp = s.get("video_prompt")
            vp_text = vp if isinstance(vp, str) else (vp.get("full_prompt") if isinstance(vp, dict) else None)
            score = s.get("video_value_scores", {}).get("total_score", 0)

            scenes.append(SceneItem(
                scene_id=s["scene_id"],
                order=s["order"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                duration=s["duration"],
                visual_mode=s.get("visual_mode", "IMAGE_ONLY"),
                video_recommended=is_video,
                video_value_score=score,
                narration_summary=s.get("visual_mode_reason", ""),
                image_prompt=s.get("image_prompt", ""),
                video_prompt=vp_text,
                visible_characters=s.get("visible_characters", []),
                location_id=s.get("location_id"),
                props=s.get("props", []),
                overlay_text=None,
                motion_type="KEN_BURNS_SLOW_PAN"
            ))
        return scenes

    def get_characters(self, project_id: str) -> List[CharacterItem]:
        bible_path = VISUAL_DIR / project_id / "character_bible.json"
        if not bible_path.exists():
            return []

        with open(bible_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chars = []
        for c in data.get("characters", []):
            cid = c["character_id"]
            chars.append(CharacterItem(
                character_id=cid,
                name=c["name"],
                identity_family_id=c.get("identity_family_id"),
                identity_role=c.get("identity_role"),
                depends_on_reference=c.get("depends_on_reference"),
                use_identity_anchor=bool(c.get("depends_on_reference")),
                age=c.get("age"),
                appearance_description=c.get("face_description", "") + " " + c.get("hair", ""),
                reference_required=c.get("requires_approval", True),
                reference_status="NOT_GENERATED",
                scene_appearances_count=c.get("scenes_count", 0)
            ))
        return chars

    def get_identity_families(self, project_id: str) -> List[Dict[str, Any]]:
        bible_path = VISUAL_DIR / project_id / "character_bible.json"
        if not bible_path.exists():
            return []
        with open(bible_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("identity_families", [])

    def get_props(self, project_id: str) -> List[PropItem]:
        bible_path = VISUAL_DIR / project_id / "prop_bible.json"
        if not bible_path.exists():
            return []
        with open(bible_path, "r", encoding="utf-8") as f:
            props_raw = json.load(f)

        props = []
        for p in props_raw:
            pid = p["prop_id"]
            dep_chars = []
            if pid == "PROP_VINTAGE_PHOTO_BAO_THOA":
                dep_chars = ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"]
            elif pid == "PROP_HOSPITAL_PHOTO_2012":
                dep_chars = ["CHAR_NAM_YOUNG_2012", "CHAR_THAO_2012", "CHAR_BE_AN_INFANT_2012"]

            props.append(PropItem(
                prop_id=pid,
                name=p["name"],
                continuity_critical=p.get("prop_reference_required", False),
                reference_required=p.get("prop_reference_required", False),
                reference_status="NOT_GENERATED" if p.get("prop_reference_required") else "NOT_REQUIRED",
                depends_on_characters=dep_chars
            ))
        return props

    def get_locations(self, project_id: str) -> List[LocationItem]:
        bible_path = VISUAL_DIR / project_id / "location_bible.json"
        if not bible_path.exists():
            return []
        with open(bible_path, "r", encoding="utf-8") as f:
            locs_raw = json.load(f)

        locs = []
        for l in locs_raw:
            locs.append(LocationItem(
                location_id=l["location_id"],
                name=l["name"],
                city_region=l.get("city_region", ""),
                description=l.get("architecture", "") or l.get("story_function", ""),
                scenes_count=l.get("scenes_count", 0)
            ))
        return locs

    def toggle_scene_mode(self, project_id: str, scene_id: str, mode: str) -> SceneItem:
        """Toggles a scene between IMAGE_ONLY and VIDEO_RECOMMENDED."""
        plan_path = VISUAL_DIR / project_id / "visual_plan.json"
        with open(plan_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        target = None
        for s in data["scenes"]:
            if s["scene_id"] == scene_id:
                s["visual_mode"] = mode
                target = s
                break

        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return SceneItem(
            scene_id=target["scene_id"],
            order=target["order"],
            start_time=target["start_time"],
            end_time=target["end_time"],
            duration=target["duration"],
            visual_mode=target["visual_mode"],
            video_recommended=(target["visual_mode"] == "VIDEO_RECOMMENDED"),
            video_value_score=target.get("video_value_scores", {}).get("total_score", 0),
            image_prompt=target.get("image_prompt", "")
        )
