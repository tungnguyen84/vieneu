"""Character & Location Library Manager for VieNeu Visual Engine.

Provides persistent storage, querying, and management for Characters, Locations, and Style Presets.
Ensures characters remain completely consistent across scenes and episodes.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHARACTER_LIB_DIR = REPO_ROOT / "character_library"
LOCATION_LIB_DIR = REPO_ROOT / "location_library"
PRESETS_DIR = REPO_ROOT / "visual_presets"


@dataclass
class CharacterProfile:
    id: str = ""
    name: str = ""
    role: str = "main"  # "main", "supporting", "flashback", "guest"
    gender: str = "unspecified"
    age_range: str = "30-35"
    appearance: str = ""
    face: str = ""
    hair: str = ""
    body: str = ""
    default_clothing: str = ""
    visual_notes: str = ""
    visual_style: str = ""
    references: List[str] = field(default_factory=list)
    flow_media_ids: Dict[str, str] = field(default_factory=dict)  # ref_filename or project_id -> Google Flow media_id UUID
    identity_relation: Optional[Dict[str, Any]] = None  # e.g. {"type": "YOUNGER_VERSION_OF", "character_id": "LAN_ADULT"}
    wardrobes: Dict[str, str] = field(default_factory=dict)  # wardrobe_id -> description
    char_id: str = ""

    def __post_init__(self):
        if not self.id and self.char_id:
            self.id = self.char_id
        elif not self.char_id and self.id:
            self.char_id = self.id


@dataclass
class LocationProfile:
    id: str = ""
    name: str = ""
    description: str = ""
    visual_style: str = ""
    lighting_default: str = ""
    is_recurring: bool = False
    references: List[str] = field(default_factory=list)
    flow_media_ids: Dict[str, str] = field(default_factory=dict)
    location_id: str = ""

    def __post_init__(self):
        if not self.id and self.location_id:
            self.id = self.location_id
        elif not self.location_id and self.id:
            self.location_id = self.id


def load_character_library(base_dir: Path = CHARACTER_LIB_DIR) -> Dict[str, CharacterProfile]:
    """Scan and load all character profiles from character_library/."""
    characters: Dict[str, CharacterProfile] = {}
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)
        return characters

    for char_dir in sorted(base_dir.iterdir()):
        if not char_dir.is_dir():
            continue
        json_file = char_dir / "character.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                char_id = data.get("id") or char_dir.name
                characters[char_id] = CharacterProfile(
                    id=char_id,
                    name=data.get("name", char_id),
                    role=data.get("role", "main"),
                    gender=data.get("gender", "unspecified"),
                    age_range=data.get("age_range", "30-35"),
                    appearance=data.get("appearance", ""),
                    face=data.get("face", ""),
                    hair=data.get("hair", ""),
                    body=data.get("body", ""),
                    default_clothing=data.get("default_clothing", ""),
                    visual_notes=data.get("visual_notes", ""),
                    visual_style=data.get("visual_style", ""),
                    references=data.get("references", []),
                    flow_media_ids=data.get("flow_media_ids", {}),
                    identity_relation=data.get("identity_relation"),
                    wardrobes=data.get("wardrobes", {})
                )
            except Exception as e:
                logger.error(f"Error loading character {json_file}: {e}")

    return characters


def save_character(profile: CharacterProfile, base_dir: Path = CHARACTER_LIB_DIR) -> Path:
    """Save character profile to persistent JSON file on disk."""
    char_dir = base_dir / profile.id
    char_dir.mkdir(parents=True, exist_ok=True)
    json_path = char_dir / "character.json"
    data = asdict(profile)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return json_path


def delete_character(char_id: str, base_dir: Path = CHARACTER_LIB_DIR) -> bool:
    """Deletes a character directory from character_library/."""
    char_dir = base_dir / char_id
    if char_dir.exists() and char_dir.is_dir():
        shutil.rmtree(char_dir, ignore_errors=True)
        return True
    return False


def load_location_library(base_dir: Path = LOCATION_LIB_DIR) -> Dict[str, LocationProfile]:
    """Scan and load all location profiles from location_library/."""
    locations: Dict[str, LocationProfile] = {}
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)
        return locations

    for loc_dir in sorted(base_dir.iterdir()):
        if not loc_dir.is_dir():
            continue
        json_file = loc_dir / "location.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loc_id = data.get("id") or loc_dir.name
                locations[loc_id] = LocationProfile(
                    id=loc_id,
                    name=data.get("name", loc_id),
                    description=data.get("description", ""),
                    visual_style=data.get("visual_style", ""),
                    lighting_default=data.get("lighting_default", ""),
                    is_recurring=data.get("is_recurring", False),
                    references=data.get("references", []),
                    flow_media_ids=data.get("flow_media_ids", {})
                )
            except Exception as e:
                logger.error(f"Error loading location {json_file}: {e}")

    return locations


def save_location(profile: LocationProfile, base_dir: Path = LOCATION_LIB_DIR) -> Path:
    """Save location profile to persistent JSON file on disk."""
    loc_dir = base_dir / profile.id
    loc_dir.mkdir(parents=True, exist_ok=True)
    json_path = loc_dir / "location.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, ensure_ascii=False, indent=2)
    return json_path


def delete_location(loc_id: str, base_dir: Path = LOCATION_LIB_DIR) -> bool:
    """Deletes a location directory from location_library/."""
    loc_dir = base_dir / loc_id
    if loc_dir.exists() and loc_dir.is_dir():
        shutil.rmtree(loc_dir, ignore_errors=True)
        return True
    return False


def load_episode_cast(project_dir: Optional[Path]) -> Optional[Dict[str, Dict[str, Any]]]:
    """Loads episode_cast.json for a project.
    
    Returns a dict mapping cast role/alias to character library id:
    {
      "LAN_ADULT": {"character_library_id": "LAN_ADULT"},
      "HUNG": {"character_library_id": "HUNG"}, ...
    }
    """
    if project_dir is None:
        return None
    cast_file = Path(project_dir) / "episode_cast.json"
    if not cast_file.exists():
        # Default fallback cast for Sau Cánh Cửa
        default_cast = {
            "LAN_ADULT": {"character_library_id": "LAN_ADULT", "notes": "Lan (trưởng thành)"},
            "HUNG": {"character_library_id": "HUNG", "notes": "Hùng (chồng Lan)"},
            "UNCLE": {"character_library_id": "UNCLE", "notes": "Cậu của Lan"},
            "LAN_YOUNG": {"character_library_id": "LAN_YOUNG", "notes": "Lan lúc trẻ (hồi tưởng)"}
        }
        try:
            save_episode_cast(default_cast, project_dir)
        except Exception:
            pass
        return default_cast

    with open(cast_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_episode_cast(cast: Dict[str, Any], project_dir: Path) -> Path:
    """Saves episode_cast.json into project directory."""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    cast_file = project_dir / "episode_cast.json"
    with open(cast_file, "w", encoding="utf-8") as f:
        json.dump(cast, f, ensure_ascii=False, indent=2)
    return cast_file


def load_visual_preset(preset_name: str = "sau_canh_cua", base_dir: Path = PRESETS_DIR) -> Dict[str, Any]:
    """Load visual style preset from visual_presets/<name>.json."""
    preset_file = base_dir / f"{preset_name}.json"
    if not preset_file.exists():
        return {
            "id": "sau_canh_cua",
            "name": "Sau Cánh Cửa - Social Mystery Drama",
            "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "video_aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "flow_project_id": "b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e",
            "image_model": "NANO_BANANA_PRO",
            "video_model": "omni_flash",
            "video_duration_default": 8,
            "video_duration_allowed": [4, 6, 8, 10],
            "series_visual_style": {
                "genre": "Vietnamese cinematic social mystery drama",
                "look": [
                    "photorealistic",
                    "natural Vietnamese faces",
                    "realistic skin texture",
                    "cinematic 35mm photography",
                    "restrained acting",
                    "natural modern Vietnamese environment",
                    "subtle dramatic lighting",
                    "muted natural colors"
                ],
                "avoid": [
                    "anime",
                    "fantasy",
                    "overacting",
                    "fashion editorial",
                    "beauty glamour",
                    "plastic skin",
                    "exaggerated facial expression",
                    "text",
                    "logo",
                    "watermark"
                ],
                "aspect_ratio": "16:9"
            }
        }

    with open(preset_file, "r", encoding="utf-8") as f:
        return json.load(f)
