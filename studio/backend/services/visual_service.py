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
from apps.visual_engine.character_continuity_resolver import CharacterContinuityResolver
from studio.backend.services.artifact_files import file_sha256

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
VISUAL_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a"
PROJECTS_DIR = BASE_DIR / "projects"


def _normalize_gender(char_dict: Dict[str, Any], all_chars: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    """Extracts and normalizes character gender strictly without guessing solely from name."""
    g = char_dict.get("gender")
    if g:
        g_str = str(g).strip().upper()
        if g_str in ("FEMALE", "F", "NỮ", "NU", "WOMAN"):
            return "FEMALE"
        if g_str in ("MALE", "M", "NAM", "MAN"):
            return "MALE"

    desc = str(char_dict.get("description") or "")
    role = str(char_dict.get("role") or "")
    combined = (desc + " " + role).lower()

    # Check contextual relationships from other characters (e.g. 'vợ của Hùng' -> Hùng is male)
    cname = str(char_dict.get("name") or "").strip().lower()
    if cname and all_chars:
        for oc in all_chars:
            orole = (str(oc.get("role") or "") + " " + str(oc.get("description") or "")).lower()
            if f"vợ của {cname}" in orole or f"vợ {cname}" in orole:
                return "MALE"
            if f"chồng của {cname}" in orole or f"chồng {cname}" in orole:
                return "FEMALE"

    female_indicators = ["người phụ nữ", "phụ nữ", "cô ấy", "cô ta", "vợ anh", "vợ của", "người vợ", "nữ sinh", "người mẹ"]
    male_indicators = ["người đàn ông", "đàn ông", "anh ấy", "anh ta", "chồng cô", "chồng của", "người chồng", "nam sinh", "người bố", "người cha"]

    has_female = any(re.search(r"\b" + re.escape(w) + r"\b", combined) for w in female_indicators)
    has_male = any(re.search(r"\b" + re.escape(w) + r"\b", combined) for w in male_indicators)

    if re.search(r"\bcô\s+(?:có|là|thường|yêu|muốn|biết|nghĩ|đang|đã)\b", combined):
        has_female = True
    if re.search(r"\banh\s+(?:có|là|thường|yêu|muốn|biết|nghĩ|đang|đã)\b", combined):
        has_male = True

    if has_female and not has_male:
        return "FEMALE"
    if has_male and not has_female:
        return "MALE"
    return None


def _clean_character_reference_prompt(name: str, age: Optional[int], gender: Optional[str], role: str, description: str) -> str:
    """Builds a clean visual identity reference prompt without narrative spoilers."""
    spoiler_patterns = [
        r"người tình[^.,;]*",
        r"ngoại tình[^.,;]*",
        r"phản bội[^.,;]*",
        r"theo dõi[^.,;]*",
        r"quan hệ ngoài luồng[^.,;]*",
        r"hôn nhân tẻ nhạt[^.,;]*",
        r"thao túng[^.,;]*",
        r"ích kỷ[^.,;]*",
        r"thủ đoạn[^.,;]*",
        r"trả thù[^.,;]*",
        r"hậu quả[^.,;]*",
        r"bị bắt quả tang[^.,;]*",
        r"bị lộ tẩy[^.,;]*",
        r"lừa dối[^.,;]*",
        r"tội lỗi[^.,;]*",
        r"ảo tưởng[^.,;]*",
        r"ảo mộng[^.,;]*",
        r"đối mặt sự thật[^.,;]*",
        r"níu giữ gia đình[^.,;]*",
        r"con cái bị tổn thương[^.,;]*",
        r"lợi dụng sự cả tin[^.,;]*",
        r"hy vọng có thể làm lại[^.,;]*",
        r"hứa hẹn[^.,;]*",
        r"giải quyết nội bộ[^.,;]*",
        r"không muốn đối mặt với sự thật[^.,;]*",
    ]
    clean_desc = description
    for pat in spoiler_patterns:
        clean_desc = re.sub(pat, "", clean_desc, flags=re.IGNORECASE)
    clean_desc = re.sub(r"\s+", " ", clean_desc).strip(" .,;")

    gender_tag = "woman" if gender == "FEMALE" else "man" if gender == "MALE" else "person"
    age_tag = f"{age}-year-old " if age else ""

    identity_summary = (
        f"Realistic Vietnamese {gender_tag}, {age_tag}with authentic Vietnamese facial features, "
        "natural skin texture, composed neutral expression, neat contemporary hairstyle."
    )
    wardrobe = "Wearing contemporary tasteful Vietnamese smart-casual attire appropriate for daily life."

    return (
        f"Cinematic identity reference portrait of Vietnamese character {name}. "
        f"{identity_summary} {wardrobe} "
        "Waist-up framing, neutral soft studio background, natural lighting, sharp focus, 16:9, no text, no watermark."
    )


class LocationContinuityEngine:
    """Tracks location continuity state and infers locations purely from story semantics.
    Never uses scene index, round-robin, or blind character occupation.
    """
    def __init__(self, locations: List[Dict[str, Any]]):
        self.locations = locations
        self.loc_by_id = {loc["location_id"]: loc for loc in locations}
        self.primary_loc = locations[0] if locations else None

        self.classified = []
        for loc in locations:
            blob = (loc["name"] + " " + loc.get("architecture", "") + " " + loc.get("story_function", "") + " " + loc["location_id"]).lower()
            cat = "OTHER"
            if any(k in blob for k in ("căn hộ", "nhà", "chung cư", "phòng khách", "phòng ngủ", "phòng tắm", "gia đình")):
                cat = "HOME"
            elif any(k in blob for k in ("resort", "khách sạn", "vũng tàu", "hotel")):
                cat = "HOTEL_RESORT"
            elif any(k in blob for k in ("cà phê", "cafe", "quán nước")):
                cat = "CAFE"
            elif "kiến trúc" in blob or ("văn phòng" in blob and "hùng" in blob):
                cat = "OFFICE_PROTAGONIST"
            elif "nội thất" in blob or ("công ty" in blob and "mai" in blob):
                cat = "OFFICE_SUPPORTING"
            elif "văn phòng" in blob or "công ty" in blob or "office" in blob:
                cat = "OFFICE"
            self.classified.append({
                "loc": loc,
                "cat": cat,
                "id": loc["location_id"],
                "name": loc["name"],
                "blob": blob
            })

    def find_by_category(self, cat: str) -> Optional[Dict[str, Any]]:
        for c in self.classified:
            if c["cat"] == cat:
                return c["loc"]
        return None

    def resolve(
        self,
        scene_index: int,
        combined_text: str,
        dominant_profile: str,
        previous_loc_id: Optional[str]
    ) -> Tuple[Optional[str], str, str, str]:
        """
        Returns (location_id, location_source, location_evidence, location_confidence).
        Priority:
        1. EXPLICIT: Physical setting directly mentioned in narration
        2. TRANSITION: Explicit transition phrases in narration
        3. CONTINUITY: Preserved setting from previous scene
        4. STORY_BIBLE: Primary story setting anchor
        5. UNKNOWN: Fallback
        """
        t_low = combined_text.lower()

        # 1. EXPLICIT PHYSICAL SIGNALS
        home_presence = [
            "ngưỡng cửa nhà", "trước cửa nhà", "chuông cửa", "mở chốt", "cánh cửa vừa hé",
            "bước vào trong", "phòng khách", "ghế sofa", "phòng ngủ", "phòng tắm",
            "về nhà", "trở về nhà", "trong nhà", "ở nhà", "căn hộ", "ngôi nhà", "mái ấm",
            "tổ ấm", "nằm trên giường", "ngủ say", "điện thoại của cô bỗng rung",
            "bước ra khỏi căn nhà", "khép lại an toàn"
        ]
        matched_home = next((kw for kw in home_presence if kw in t_low), None)
        if matched_home:
            home_loc = self.find_by_category("HOME") or self.primary_loc
            if home_loc:
                return (
                    home_loc["location_id"],
                    "EXPLICIT",
                    f"Explicit domestic setting in narration: '{matched_home}'",
                    "HIGH"
                )

        cafe_presence = ["ngồi trong quán cà phê", "tại quán cà phê", "bước vào quán cà phê", "ở quán cà phê", "hai người gặp nhau ở quán cà phê"]
        matched_cafe = next((kw for kw in cafe_presence if kw in t_low), None)
        if matched_cafe:
            cafe_loc = self.find_by_category("CAFE")
            if cafe_loc:
                return (
                    cafe_loc["location_id"],
                    "EXPLICIT",
                    f"Explicit cafe setting in narration: '{matched_cafe}'",
                    "HIGH"
                )

        office_protagonist_presence = ["đến văn phòng kiến trúc", "tại văn phòng kiến trúc", "ngồi tại bàn làm việc ở văn phòng kiến trúc"]
        matched_off_pro = next((kw for kw in office_protagonist_presence if kw in t_low), None)
        if matched_off_pro:
            off_loc = self.find_by_category("OFFICE_PROTAGONIST") or self.find_by_category("OFFICE")
            if off_loc:
                return (
                    off_loc["location_id"],
                    "EXPLICIT",
                    f"Explicit architect office presence: '{matched_off_pro}'",
                    "HIGH"
                )

        office_supporting_presence = ["đến công ty thiết kế", "tại công ty thiết kế", "ở công ty nội thất"]
        matched_off_sup = next((kw for kw in office_supporting_presence if kw in t_low), None)
        if matched_off_sup:
            off_sup = self.find_by_category("OFFICE_SUPPORTING") or self.find_by_category("OFFICE")
            if off_sup:
                return (
                    off_sup["location_id"],
                    "EXPLICIT",
                    f"Explicit design office presence: '{matched_off_sup}'",
                    "HIGH"
                )

        resort_presence = ["đến resort", "trong phòng khách sạn tại vũng tàu", "ở tại resort", "bước vào khách sạn ở vũng tàu"]
        matched_resort = next((kw for kw in resort_presence if kw in t_low), None)
        if matched_resort:
            resort_loc = self.find_by_category("HOTEL_RESORT")
            if resort_loc:
                return (
                    resort_loc["location_id"],
                    "EXPLICIT",
                    f"Explicit resort presence in narration: '{matched_resort}'",
                    "HIGH"
                )

        # 2. CONTINUITY: If previous location was established, preserve it!
        if previous_loc_id and previous_loc_id in self.loc_by_id:
            return (
                previous_loc_id,
                "CONTINUITY",
                "Continued setting from previous scene without location transition",
                "HIGH"
            )

        # 3. STORY BIBLE / PRIMARY ANCHOR: For opening scenes or default grounding
        if self.primary_loc:
            return (
                self.primary_loc["location_id"],
                "STORY_BIBLE",
                f"Primary story setting established from Story Bible ({self.primary_loc['name']})",
                "HIGH"
            )

        # 4. UNKNOWN Fallback
        return (
            None,
            "UNKNOWN",
            "Location could not be established from narration or continuity",
            "LOW"
        )


def _compose_scene_image_prompt(
    scene_idx: int,
    combined_text: str,
    visible_characters: List[str],
    location_name: str,
    dominant_profile: str,
    characters_map: Dict[str, Dict[str, Any]]
) -> str:
    """Creates a specific cinematic visual moment for the keyframe rather than dumping raw narration."""
    clean_loc = re.sub(r"\(.*?\)", "", location_name).strip()
    identities = []
    for cid in visible_characters:
        char = characters_map.get(cid, {})
        gender = char.get("gender")
        noun = "woman" if gender == "FEMALE" else "man" if gender == "MALE" else "person"
        identities.append(f"{char.get('name') or cid}, Vietnamese {noun}; preserve this character reference")
    sentences = re.split(r"(?<=[.!?])\s+", combined_text.strip())
    action_words = ("bước", "mở", "nhìn", "cầm", "đọc", "ngồi", "đứng", "rời", "đặt", "khóc", "gặp")
    moment = next((line for line in sentences if any(word in line.lower() for word in action_words)),
                  "A restrained quiet moment; show only the listed characters in the established setting.")
    return (
        f"Vietnamese cinematic documentary realism, 35mm photography, natural film grain. Setting: {clean_loc}. "
        f"Visible cast ONLY: {'; '.join(identities) or 'no identifiable character'}. "
        f"Depict this concrete moment from the source scene: {moment[:450]}. "
        "Do not invent a spouse, visitor, age, gender, object or event absent from the source. "
        "Preserve reference identities and wardrobe; balanced 16:9 composition, no captions, no watermark."
    )


def _compose_scene_video_prompt(
    scene_idx: int,
    combined_text: str,
    visible_characters: List[str],
    location_name: str,
    dominant_profile: str
) -> Dict[str, str]:
    """Generates a scene-specific dynamic video prompt adhering strictly to Start/Action/Camera/End."""
    clean_loc = re.sub(r"\(.*?\)", "", location_name).strip()
    start = f"Preserve the exact approved keyframe, character references and setting {clean_loc}. Visible cast: {', '.join(visible_characters)}."
    action = f"Animate only the action already depicted in the keyframe from this source scene: {combined_text[:450]}. Do not add characters or a new event."
    camera = "Slow restrained documentary camera movement, stable facial identity, no sudden cuts."
    end = "End on the same established scene with natural motion settling; no text overlays or audible dialogue."
    return {"start": start, "action": action, "camera": camera, "end": end,
            "full_prompt": f"START: {start} ACTION: {action} CAMERA: {camera} END: {end}"}


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

        # Check lineage if project.json or qc_report.json exists
        if (project_dir / "project.json").exists() or (project_dir / "script" / "qc_report.json").exists():
            from studio.backend.services.artifact_lineage import require_current_full_script
            require_current_full_script(
                project_id,
                PROJECTS_DIR,
                require_approved=True,
                require_clean_qc=True,
            )

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

        # 1. Characters Normalization
        raw_characters = []
        char_bible_path = project_dir / "character_bible.json"
        if char_bible_path.exists():
            try:
                cb_data = json.loads(char_bible_path.read_text(encoding="utf-8"))
                if isinstance(cb_data, dict):
                    if "characters" in cb_data and isinstance(cb_data["characters"], list):
                        raw_characters = cb_data["characters"]
                    else:
                        raw_characters = list(cb_data.values())
                elif isinstance(cb_data, list):
                    raw_characters = cb_data
            except Exception:
                raw_characters = []

        if not raw_characters:
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
            age = char.get("age")
            gender = _normalize_gender(char, raw_characters)
            role = str(char.get("role") or "")
            ref_prompt = _clean_character_reference_prompt(name, age, gender, role, description)
            characters.append({
                "character_id": char_id,
                "name": name,
                "age": age,
                "gender": gender,
                "ethnicity": "Vietnamese",
                "identity_family_id": None,
                "identity_role": "ANCHOR",
                "requires_approval": True,
                "face_description": description,
                "hair": "",
                "body_build": "",
                "emotional_baseline": role,
                "wardrobe_baseline": "Contemporary Vietnamese clothing appropriate to the story",
                "wardrobe_variants": {},
                "reference_prompt": ref_prompt,
            })

        # 2. Locations Grounding
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
            clean_name = re.sub(r"\(.*?\)", "", name).strip()
            locations.append({
                "location_id": self._slug(name, "LOC"),
                "name": name,
                "city_region": "Vietnam",
                "type": "INTERIOR",
                "architecture": description,
                "story_function": description,
                "reference_prompt": f"Cinematic Vietnamese location reference: {clean_name}. Natural light, realistic documentary style, 16:9, no text, no watermark.",
            })
        if not locations:
            locations.append({
                "location_id": "LOC_VIETNAM_HOME",
                "name": "Không gian gia đình Việt Nam",
                "city_region": "Vietnam",
                "type": "INTERIOR",
                "architecture": "Contemporary Vietnamese family home",
                "story_function": "Primary story setting",
                "reference_prompt": "Contemporary Vietnamese family home, cinematic documentary realism, natural light, 16:9, no text, no watermark.",
            })

        loc_engine = LocationContinuityEngine(locations)

        # Use the same measured, content-bound timeline as the music mixer.
        timing_data = AudioService().get_measured_timing(project_id)
        audio_binding = AudioService().require_current_audio(project_id)
        segment_times = []
        for idx, (seg, timing) in enumerate(zip(segments, timing_data)):
            s_start = 0.0 if idx == 0 else float(timing["speech_start_sec"])
            s_end = audio_duration if idx == len(segments) - 1 else float(timing_data[idx + 1]["speech_start_sec"])
            if s_end <= s_start or s_start < 0 or s_end > audio_duration + 0.001:
                raise ValueError("Measured timing không hợp lệ cho Visual Plan")
            segment_times.append((s_start, s_end, seg))

        scene_count = min(45, len(segments))
        boundaries = [round(index * len(segments) / scene_count) for index in range(scene_count + 1)]
        scene_groups = [segment_times[boundaries[index]:boundaries[index + 1]] for index in range(scene_count)]
        action_words = ("bước", "mở", "nhìn", "phát hiện", "khóc", "chạy", "đối diện", "cầm", "lật", "rời", "rung", "chuông", "gục")
        scored = []
        for index, group in enumerate(scene_groups):
            text = " ".join(str(item[2].get("text") or "") for item in group)
            profiles = [str(item[2].get("delivery_profile") or "NORMAL").upper() for item in group]
            score = 30 + (25 if any(word in text.lower() for word in action_words) else 0)
            score += 20 if any(profile in {"HOOK", "MYSTERY", "ENDING", "REVEAL", "TENSION"} for profile in profiles) else 0
            scored.append((score, index))
        video_target = min(8, max(1, round(scene_count * 0.18)))
        video_indexes = {index for _, index in sorted(scored, reverse=True)[:video_target]}

        # 4. Scenes Planning with Continuity State Machine
        plan_scenes = []
        previous_loc_id = None
        characters_map = {c["character_id"]: c for c in characters}
        char_resolver = CharacterContinuityResolver(characters)

        for scene_index, group in enumerate(scene_groups):
            start_time = round(group[0][0], 3)
            end_time = round(audio_duration, 3) if scene_index == len(scene_groups) - 1 else round(group[-1][1], 3)
            texts = [str(item[2].get("text") or "") for item in group]
            combined = " ".join(texts).strip()
            lower = combined.lower()
            profiles = [str(item[2].get("delivery_profile") or "NORMAL").upper() for item in group]
            dominant_profile = max(set(profiles), key=profiles.count)

            visible = char_resolver.match_characters_in_text(combined)

            # Semantic location inference with continuity tracking
            loc_id, loc_source, loc_evidence, loc_confidence = loc_engine.resolve(
                scene_index=scene_index,
                combined_text=combined,
                dominant_profile=dominant_profile,
                previous_loc_id=previous_loc_id
            )
            previous_loc_id = loc_id
            assigned_loc = loc_engine.loc_by_id.get(loc_id) or locations[0]

            is_video = scene_index in video_indexes
            image_prompt = _compose_scene_image_prompt(
                scene_idx=scene_index,
                combined_text=combined,
                visible_characters=visible,
                location_name=assigned_loc["name"],
                dominant_profile=dominant_profile,
                characters_map=characters_map
            )
            video_prompt = None
            if is_video:
                video_prompt_obj = _compose_scene_video_prompt(
                    scene_idx=scene_index,
                    combined_text=combined,
                    visible_characters=visible,
                    location_name=assigned_loc["name"],
                    dominant_profile=dominant_profile
                )
                video_prompt = video_prompt_obj["full_prompt"]

            plan_scenes.append({
                "scene_id": f"SC_{scene_index + 1:03d}",
                "order": scene_index + 1,
                "start_time": start_time,
                "end_time": end_time,
                "duration": round(end_time - start_time, 3),
                "source_segments": [str(item[2].get("id") or item[2].get("segment_id") or "") for item in group],
                "visual_mode": "VIDEO_RECOMMENDED" if is_video else "IMAGE_ONLY",
                "visual_mode_reason": combined[:220],
                "video_value_scores": {"total_score": scored[scene_index][0]},
                "image_prompt": image_prompt,
                "video_prompt": video_prompt,
                "visible_characters": visible,
                "location_id": loc_id,
                "location_confidence": loc_confidence,
                "location_evidence": loc_evidence,
                "location_source": loc_source,
                "props": [],
                "image_motion": {"type": "SLOW_PUSH_IN" if is_video else "KEN_BURNS_SLOW_PAN"},
            })

        # Run Character Continuity Resolver post-scene generation pass
        plan_scenes = char_resolver.resolve_scenes(plan_scenes)
        # The resolver may carry characters into a pronoun-only scene. Compose
        # prompts AFTER that decision so the prompt and exported references agree.
        for scene in plan_scenes:
            group = scene_groups[scene["order"] - 1]
            text = " ".join(str(item[2].get("text") or "") for item in group)
            loc = loc_engine.loc_by_id.get(scene["location_id"]) or locations[0]
            profile = str(group[0][2].get("delivery_profile") or "NORMAL").upper()
            scene["image_prompt"] = _compose_scene_image_prompt(scene["order"] - 1, text,
                scene["visible_characters"], loc["name"], profile, characters_map)
            if scene["video_prompt"]:
                scene["video_prompt"] = _compose_scene_video_prompt(scene["order"] - 1, text,
                    scene["visible_characters"], loc["name"], profile)["full_prompt"]


        target_dir = VISUAL_DIR / project_id
        target_dir.mkdir(parents=True, exist_ok=True)
        plan = {
            "audio_sha256": file_sha256(audio_path),
            "source_script_content_hash": audio_binding["script_content_hash"],
            "source_story_content_hash": audio_binding["story_content_hash"],
            "episode_id": project_id,
            "title": project_meta.get("title") or script_data.get("title") or project_id,
            "audio_duration_sec": round(audio_duration, 3),
            "scenes": plan_scenes,
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
                character_refs_required=s.get("character_refs_required", []),
                character_dependencies=s.get("character_dependencies", []),
                generation_dependencies_satisfied=s.get("generation_dependencies_satisfied", False),
                location_id=s.get("location_id"),
                location_confidence=s.get("location_confidence"),
                location_evidence=s.get("location_evidence"),
                location_source=s.get("location_source"),
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
                gender=c.get("gender"),
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
