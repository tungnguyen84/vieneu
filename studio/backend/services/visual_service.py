"""Visual Plan Service for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
import re
import unicodedata
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
PROJECTS_DIR = BASE_DIR / "projects"


class VisualService:
    def __init__(self):
        pass

    @staticmethod
    def _slug(value: str, prefix: str) -> str:
        ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        clean = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value).strip("_").upper()
        return f"{prefix}_{clean or 'UNKNOWN'}"

    def generate_visual_plan(self, project_id: str) -> Dict[str, Any]:
        """Build a project-specific visual plan from approved script and real audio timing."""
        project_dir = PROJECTS_DIR / project_id
        script_path = project_dir / "script" / "full_script.json"
        if not script_path.exists():
            raise FileNotFoundError("Chưa có kịch bản để lập Visual Plan")

        from studio.backend.services.audio_service import AudioService
        audio_path = AudioService().get_audio_master_path(project_id)
        if not audio_path:
            raise FileNotFoundError("Chưa có Audio Master. Hãy tạo hoặc import audio trước khi lập Visual Plan")
        try:
            import soundfile as sf
            audio_duration = float(sf.info(str(audio_path)).duration)
        except Exception as exc:
            raise ValueError(f"Không đọc được thời lượng Audio Master: {exc}")
        if audio_duration <= 0:
            raise ValueError("Audio Master có thời lượng không hợp lệ")

        script_data = json.loads(script_path.read_text(encoding="utf-8"))
        segments = script_data.get("segments", script_data if isinstance(script_data, list) else [])
        if not segments:
            raise ValueError("Kịch bản không có phân đoạn")

        project_meta_path = project_dir / "project.json"
        project_meta = json.loads(project_meta_path.read_text(encoding="utf-8")) if project_meta_path.exists() else {}
        story_path = project_dir / "story_bible.json"
        if not story_path.exists():
            story_path = project_dir / "story" / "story_bible.json"
        story = json.loads(story_path.read_text(encoding="utf-8")) if story_path.exists() else {}

        raw_characters = []
        if isinstance(story.get("protagonist"), dict):
            raw_characters.append(story["protagonist"])
        raw_characters.extend(item for item in story.get("supporting_characters", []) if isinstance(item, dict))
        if not raw_characters and isinstance(story.get("characters"), list):
            raw_characters = story["characters"]
        characters = []
        for index, char in enumerate(raw_characters):
            name = str(char.get("name") or f"Nhân vật {index + 1}")
            char_id = str(char.get("char_id") or char.get("character_id") or self._slug(name, "CHAR"))
            description = str(char.get("description") or char.get("appearance") or char.get("role") or "")
            characters.append({
                "character_id": char_id,
                "name": name,
                "age": char.get("age"),
                "gender": char.get("gender"),
                "ethnicity": "Vietnamese",
                "identity_family_id": None,
                "identity_role": "ANCHOR",
                "requires_approval": True,
                "face_description": description,
                "hair": "",
                "body_build": "",
                "emotional_baseline": str(char.get("role") or ""),
                "wardrobe_baseline": "Contemporary Vietnamese clothing appropriate to the story",
                "wardrobe_variants": {},
                "reference_prompt": (
                    f"Cinematic identity reference portrait of Vietnamese character {name}. {description}. "
                    "Neutral background, natural skin texture, consistent facial identity, no text, 16:9."
                ),
            })

        location_path = project_dir / "location_bible.json"
        location_data = json.loads(location_path.read_text(encoding="utf-8")) if location_path.exists() else {}
        raw_locations = location_data.get("locations", []) if isinstance(location_data, dict) else location_data
        locations = []
        for index, item in enumerate(raw_locations or []):
            if isinstance(item, str):
                name, description = item, item
            else:
                name = str(item.get("name") or f"Bối cảnh {index + 1}")
                description = str(item.get("description") or item.get("architecture") or item.get("story_function") or name)
            locations.append({
                "location_id": self._slug(name, "LOC"), "name": name, "city_region": "Vietnam",
                "type": "INTERIOR", "architecture": description, "story_function": description,
                "reference_prompt": f"Cinematic Vietnamese location reference: {description}. Natural light, realistic documentary style, no text.",
            })
        if not locations:
            locations.append({
                "location_id": "LOC_VIETNAM_HOME", "name": "Không gian gia đình Việt Nam", "city_region": "Vietnam",
                "type": "INTERIOR", "architecture": "Contemporary Vietnamese family home",
                "story_function": "Primary story setting",
                "reference_prompt": "Contemporary Vietnamese family home, cinematic documentary realism, natural light, no text.",
            })

        weights = []
        for segment in segments:
            words = max(1, len(str(segment.get("text") or "").split()))
            speed = max(0.88, min(1.05, float(segment.get("speed") or 1.0)))
            weights.append(words / (2.7 * speed) + float(segment.get("pause_after") or 0.25))
        weight_total = sum(weights)
        segment_times = []
        cursor = 0.0
        for index, (segment, weight) in enumerate(zip(segments, weights)):
            end = audio_duration if index == len(segments) - 1 else cursor + audio_duration * weight / weight_total
            segment_times.append((cursor, end, segment))
            cursor = end

        scene_count = min(45, len(segments))
        boundaries = [round(index * len(segments) / scene_count) for index in range(scene_count + 1)]
        scene_groups = [segment_times[boundaries[index]:boundaries[index + 1]] for index in range(scene_count)]
        action_words = ("bước", "mở", "nhìn", "phát hiện", "khóc", "chạy", "đối diện", "cầm", "lật", "rời")
        scored = []
        for index, group in enumerate(scene_groups):
            text = " ".join(str(item[2].get("text") or "") for item in group)
            profiles = [str(item[2].get("delivery_profile") or "NORMAL").upper() for item in group]
            score = 30 + (25 if any(word in text.lower() for word in action_words) else 0)
            score += 20 if any(profile in {"HOOK", "MYSTERY", "ENDING"} for profile in profiles) else 0
            scored.append((score, index))
        video_target = min(8, max(1, round(scene_count * 0.18)))
        video_indexes = {index for _, index in sorted(scored, reverse=True)[:video_target]}

        plan_scenes = []
        for scene_index, group in enumerate(scene_groups):
            start_time = round(group[0][0], 3)
            end_time = round(group[-1][1], 3)
            texts = [str(item[2].get("text") or "") for item in group]
            combined = " ".join(texts).strip()
            lower = combined.lower()
            visible = [char["character_id"] for char in characters if char["name"].lower() in lower]
            location = next((loc for loc in locations if loc["name"].lower() in lower), locations[scene_index % len(locations)])
            is_video = scene_index in video_indexes
            image_prompt = (
                "Vietnamese cinematic documentary scene, photorealistic 35mm photography, natural skin texture, "
                f"authentic setting: {location['name']}. Story beat: {combined[:500]}. "
                "Restrained emotion, coherent character identity, 16:9 composition, no captions, no watermark."
            )
            video_prompt = None
            if is_video:
                video_prompt = (
                    "Start: preserve the exact subjects, clothing and environment from the approved keyframe. "
                    "Action: subtle natural movement matching the story beat with restrained Vietnamese drama acting. "
                    "Camera: slow cinematic push-in or gentle lateral drift, stable 24fps. "
                    "End: hold the same composition and identity, no new people or objects."
                )
            plan_scenes.append({
                "scene_id": f"SC_{scene_index + 1:03d}", "order": scene_index + 1,
                "start_time": start_time, "end_time": end_time, "duration": round(end_time - start_time, 3),
                "source_segments": [str(item[2].get("id") or item[2].get("segment_id") or "") for item in group],
                "visual_mode": "VIDEO_RECOMMENDED" if is_video else "IMAGE_ONLY",
                "visual_mode_reason": combined[:220], "video_value_scores": {"total_score": scored[scene_index][0]},
                "image_prompt": image_prompt, "video_prompt": video_prompt,
                "visible_characters": visible, "location_id": location["location_id"], "props": [],
                "image_motion": {"type": "SLOW_PUSH_IN" if is_video else "KEN_BURNS_SLOW_PAN"},
            })

        target_dir = VISUAL_DIR / project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "episode_id": project_id, "title": project_meta.get("title") or script_data.get("title") or project_id,
            "audio_duration_sec": round(audio_duration, 3), "scenes": plan_scenes,
        }
        (target_dir / "visual_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        (target_dir / "character_bible.json").write_text(
            json.dumps({"identity_families": [], "characters": characters}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (target_dir / "location_bible.json").write_text(json.dumps(locations, ensure_ascii=False, indent=2), encoding="utf-8")
        (target_dir / "prop_bible.json").write_text("[]", encoding="utf-8")
        (target_dir / "overlay_plan.json").write_text(json.dumps({"overlays": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "project_id": project_id, "scenes": len(plan_scenes),
            "images": scene_count - len(video_indexes), "videos": len(video_indexes),
            "audio_duration_sec": round(audio_duration, 3),
        }

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
