"""Character & Location Library Manager for VieNeu Visual Engine.

Provides persistent storage, querying, and management for Characters, Locations, and Style Presets.
Ensures characters remain completely consistent across scenes and episodes.
"""
from __future__ import annotations

import json
import logging
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
    id: str
    name: str
    gender: str = "unspecified"
    age_range: str = "30-35"
    appearance: str = ""
    hair: str = ""
    default_clothing: str = ""
    visual_style: str = ""
    references: List[str] = field(default_factory=list)
    flow_media_ids: Dict[str, str] = field(default_factory=dict)  # ref_filename -> Google Flow media_id UUID


@dataclass
class LocationProfile:
    id: str
    name: str
    description: str = ""
    references: List[str] = field(default_factory=list)
    flow_media_ids: Dict[str, str] = field(default_factory=dict)


def load_character_library(base_dir: Path = CHARACTER_LIB_DIR) -> Dict[str, CharacterProfile]:
    """Scan and load all character profiles from character_library/."""
    characters: Dict[str, CharacterProfile] = {}
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)
        return characters

    for char_dir in base_dir.iterdir():
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
                    gender=data.get("gender", "unspecified"),
                    age_range=data.get("age_range", "30-35"),
                    appearance=data.get("appearance", ""),
                    hair=data.get("hair", ""),
                    default_clothing=data.get("default_clothing", ""),
                    visual_style=data.get("visual_style", ""),
                    references=data.get("references", []),
                    flow_media_ids=data.get("flow_media_ids", {})
                )
            except Exception as e:
                logger.error(f"Error loading character {json_file}: {e}")

    return characters


def save_character(profile: CharacterProfile, base_dir: Path = CHARACTER_LIB_DIR) -> Path:
    """Save character profile to persistent JSON file on disk."""
    char_dir = base_dir / profile.id
    char_dir.mkdir(parents=True, exist_ok=True)
    json_path = char_dir / "character.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, ensure_ascii=False, indent=2)
    return json_path


def load_location_library(base_dir: Path = LOCATION_LIB_DIR) -> Dict[str, LocationProfile]:
    """Scan and load all location profiles from location_library/."""
    locations: Dict[str, LocationProfile] = {}
    if not base_dir.exists():
        base_dir.mkdir(parents=True, exist_ok=True)
        return locations

    for loc_dir in base_dir.iterdir():
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
                    references=data.get("references", []),
                    flow_media_ids=data.get("flow_media_ids", {})
                )
            except Exception as e:
                logger.error(f"Error loading location {json_file}: {e}")

    return locations


def load_visual_preset(preset_name: str = "sau_canh_cua", base_dir: Path = PRESETS_DIR) -> Dict[str, Any]:
    """Load visual style preset from visual_presets/<name>.json."""
    preset_file = base_dir / f"{preset_name}.json"
    if not preset_file.exists():
        # Fallback to default
        return {
            "id": "sau_canh_cua",
            "name": "Sau Cánh Cửa - Social Mystery Drama",
            "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
            "video_aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
            "style_prompt": "Vietnamese cinematic social mystery drama, realistic, natural Vietnamese faces, modern Vietnamese environment, subtle cinematic lighting, muted natural colors, 35mm photography, realistic skin texture",
            "negative_prompt": "anime, cartoon, 3d render, fantasy, western faces, exaggerated expressions, watermark, logo, text",
            "resolution": "1920x1080",
            "fps": 30
        }

    with open(preset_file, "r", encoding="utf-8") as f:
        return json.load(f)
