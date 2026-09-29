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
    flow_media_ids: Dict[str, str] = field(default_factory=dict)  # ref_filename or project_id -> Google Flow media_id UUID (only verified Flow IDs)
    identity_relation: Optional[Dict[str, Any]] = None  # e.g. {"type": "YOUNGER_VERSION_OF", "character_id": "LAN_ADULT"}
    wardrobes: Dict[str, str] = field(default_factory=dict)  # wardrobe_id -> description
    char_id: str = ""
    local_reference_id: str = ""
    flow: Dict[str, Any] = field(default_factory=dict)
    qc_status: str = "AWAITING_REVIEW"  # "AWAITING_REVIEW" | "APPROVED" | "REJECTED"
    reference_source: Optional[str] = None  # "BANANA_PRO", "CUSTOM_UPLOAD", etc.

    def __post_init__(self):
        if not self.id and self.char_id:
            self.id = self.char_id
        elif not self.char_id and self.id:
            self.char_id = self.id
        if not self.local_reference_id and self.id:
            self.local_reference_id = f"{self.id}_REF_V1"
        if not self.flow:
            self.flow = {
                "project_id": "b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e",
                "media_id": None,
                "upload_status": "LOCAL_ONLY"
            }


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
                flow_data = data.get("flow") or {
                    "project_id": "b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e",
                    "media_id": None,
                    "upload_status": "LOCAL_ONLY"
                }
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
                    wardrobes=data.get("wardrobes", {}),
                    local_reference_id=data.get("local_reference_id", f"{char_id}_REF_V1"),
                    flow=flow_data,
                    qc_status=data.get("qc_status", "AWAITING_REVIEW"),
                    reference_source=data.get("reference_source")
                )
            except Exception as e:
                logger.error(f"Error loading character {json_file}: {e}")

    return characters


def is_valid_image_file(path: Path | str) -> bool:
    """Verifies that the file exists and is a valid readable image (> 1KB)."""
    if not path:
        return False
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1000:
        return False
    try:
        from PIL import Image
        with Image.open(p) as img:
            img.verify()
        return True
    except Exception:
        return False


def get_character_preview_path(char_id: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    """Resolves the best available image path for previewing character reference in UI.

    Priority:
    1. If character is AWAITING_REVIEW, returns the newest valid candidate (ref_portrait_v*.png).
    2. If ref_portrait.png is valid, returns ref_portrait.png.
    3. Falls back to newest valid candidate version.
    4. None if no valid image exists on disk.
    """
    effective_dir = base_dir or CHARACTER_LIB_DIR
    char_dir = effective_dir / char_id
    if not char_dir.exists():
        return None

    chars = load_character_library(effective_dir)
    profile = chars.get(char_id)

    # Collect versioned candidates sorted by version number descending
    versioned_candidates = []
    for p in char_dir.glob("ref_portrait_v*.png"):
        parts = p.stem.split("_v")
        if len(parts) == 2 and parts[1].isdigit():
            versioned_candidates.append((int(parts[1]), p))
    versioned_candidates.sort(key=lambda x: x[0], reverse=True)

    main_ref = char_dir / "ref_portrait.png"
    main_is_valid = is_valid_image_file(main_ref)

    # When awaiting review, prioritize showing the newest generated candidate
    if profile and profile.qc_status != "APPROVED":
        for _, v_path in versioned_candidates:
            if is_valid_image_file(v_path):
                return v_path

    if main_is_valid:
        return main_ref

    for _, v_path in versioned_candidates:
        if is_valid_image_file(v_path):
            return v_path

    return None


def build_character_reference_prompt(
    character: CharacterProfile | dict,
    reference_type: str = "CHARACTER_BIBLE"
) -> str:
    """Builds a standardized cinematic reference prompt from character.json.

    Supports:
    - 'CHARACTER_BIBLE': Multi-angle character design turnaround model sheet (16:9 Landscape)
      displaying full-body front view, three-quarter view, side profile view, and close-up facial crop.
    - 'PORTRAIT': Single-view waist-up 3:4 portrait.
    """
    identity_rel = getattr(character, "identity_relation", None) if hasattr(character, "identity_relation") else (character.get("identity_relation") if isinstance(character, dict) else None)
    char_id = getattr(character, "id", None) or getattr(character, "char_id", None) or (character.get("id") or character.get("char_id") if isinstance(character, dict) else "")
    is_young_version = bool((identity_rel and identity_rel.get("type") == "YOUNGER_VERSION_OF") or char_id == "LAN_YOUNG")

    # Helper to extract fields
    def _g(key: str) -> str:
        if hasattr(character, key):
            val = getattr(character, key)
            return str(val) if val else ""
        if isinstance(character, dict):
            val = character.get(key)
            return str(val) if val else ""
        return ""

    gender = _g("gender").strip()
    age = _g("age_range").strip()
    face = _g("face").strip()
    hair = _g("hair").strip()
    body = _g("body").strip()
    appearance = _g("appearance").strip()
    clothing = _g("default_clothing").strip()

    if gender.lower() == "female":
        gender_desc = "Vietnamese woman."
    elif gender.lower() == "male":
        gender_desc = "Vietnamese man."
    else:
        gender_desc = "Vietnamese person."

    age_desc = f"Age approximately {age}." if age else ""

    # CHARACTER BIBLE (Turnaround Model Sheet - 16:9 Landscape)
    if reference_type == "CHARACTER_BIBLE":
        if is_young_version:
            return (
                "Photorealistic cinematic character bible model sheet for a Vietnamese social mystery drama.\n\n"
                "A complete multi-view character design reference turnaround sheet of a young Vietnamese female student aged 17–18, "
                "who is the younger version of the adult anchor character.\n\n"
                "Turnaround layout displaying multiple views of the same young woman side-by-side in one wide image:\n"
                "1. Full-body front view: Standing youthful posture, wearing classic Vietnamese high-school white student shirt and dark trousers, showing natural body proportions.\n"
                "2. Three-quarter angle upper body view: Clear jawline contours, natural dark straight ponytail hair, delicate posture.\n"
                "3. Side profile view: Natural facial silhouette, delicate nose bridge, clean neckline.\n"
                "4. Detailed close-up facial crop: Soft youthful Vietnamese facial features, natural unblemished skin, innocent earnest eyes, subtle emotional depth.\n\n"
                "Identity Continuity Rules:\n"
                "- Must preserve the exact facial bone structure, eye shape, nose structure, and mouth contours of the adult reference character, portrayed 12–14 years younger.\n"
                "- Classic Vietnamese high-school white student uniform blouse.\n"
                "- Soft even diffuse studio lighting on solid neutral grey background.\n"
                "- No glamour retouching, no editorial makeup, no dramatic cinematic shadows.\n"
                "- No text, no typography, no labels, no watermark, no color swatches.\n"
                "- Wide 16:9 landscape cinematic character model sheet composition.\n\n"
                "This is a character bible model sheet, not an isolated single scene."
            )

        return (
            "Photorealistic cinematic character bible model sheet for a Vietnamese social mystery drama.\n\n"
            f"A complete multi-view character design reference turnaround sheet of the same {gender_desc.lower()} on a neutral studio background.\n\n"
            "Turnaround layout displaying multiple views of the same character side-by-side in one composite image:\n"
            "1. Full-body front view: Standing natural pose, head-to-toe view clearly displaying overall physical proportions and clothing style.\n"
            "2. Three-quarter angle upper body view: Showing facial depth, jawline contours, and hair volume.\n"
            "3. Side profile view: Showing silhouette, nose bridge, ear placement, and upright posture.\n"
            "4. Detailed close-up facial crop: Focused on authentic Vietnamese facial features, natural skin texture, calm thoughtful expression.\n\n"
            "Character Identity Specifications:\n"
            f"- Identity: {gender_desc} {age_desc}\n"
            f"- Facial Features: {face}\n"
            f"- Hairstyle: {hair}\n"
            f"- Body Build: {body}\n"
            f"- General Appearance: {appearance}\n"
            f"- Wardrobe / Attire: {clothing}\n\n"
            "Aesthetic & Technical Rules:\n"
            "- Absolute identity continuity: The exact same individual must appear across all views.\n"
            "- Soft, even, diffuse neutral studio lighting with balanced fill.\n"
            "- Clean solid neutral grey studio background.\n"
            "- Realistic Vietnamese facial anatomy, natural pore skin texture, realistic lighting reflections.\n"
            "- No glamour retouching, no editorial makeup, no exaggerated styling.\n"
            "- No dramatic high-contrast film shadows, no cinematic background distractions, no props covering the face.\n"
            "- No text, no typography, no labels, no watermark, no color swatches.\n"
            "- Wide 16:9 landscape cinematic character model sheet composition.\n\n"
            "This is a character bible model sheet, not an isolated single scene."
        )

    # PORTRAIT (Single-view 3:4)
    if is_young_version:
        return (
            "Create a believable younger version of the SAME Vietnamese woman shown in the identity reference.\n\n"
            "Age approximately 17–18.\n\n"
            "Preserve recognizable:\n"
            "facial bone structure,\n"
            "eye shape,\n"
            "nose structure,\n"
            "mouth shape,\n"
            "facial proportions,\n"
            "overall identity.\n\n"
            "Make her naturally younger rather than changing her into another person.\n\n"
            "Vietnamese high-school-age appearance.\n"
            "Natural black hair.\n"
            "Simple modest Vietnamese student appearance.\n"
            "White school blouse where appropriate.\n\n"
            "Neutral character reference portrait.\n"
            "Soft even lighting.\n"
            "Simple neutral background.\n"
            "Photorealistic realistic skin.\n"
            "No glamour.\n"
            "No heavy makeup.\n"
            "No text.\n"
            "No watermark.\n"
            "3:4 portrait."
        )

    sections = [
        "Photorealistic character reference portrait for a Vietnamese cinematic social mystery drama.\n",
        "Vietnamese person.",
        gender_desc,
        age_desc,
        face,
        hair,
        body,
        appearance,
        clothing,
        "\nNeutral natural expression.",
        "Front-facing or slight three-quarter angle.",
        "Clearly visible facial features.",
        "Relaxed natural standing pose.",
        "Waist-up or three-quarter body character reference.",
        "Soft even studio-like natural lighting.",
        "Simple neutral background.",
        "Realistic Vietnamese facial anatomy.",
        "Realistic skin texture.",
        "No glamour retouching.",
        "No fashion editorial styling.",
        "No exaggerated makeup.",
        "No dramatic cinematic shadows.",
        "No props covering the face.",
        "No text.",
        "No watermark.",
        "3:4 portrait composition.\n",
        "This is an identity reference image, not a cinematic scene."
    ]
    return "\n".join(s for s in sections if s.strip() or s == "\n")


def save_character(profile: CharacterProfile, base_dir: Optional[Path] = None) -> Path:
    """Save character profile to persistent JSON file on disk."""
    effective_dir = base_dir or CHARACTER_LIB_DIR
    char_dir = effective_dir / profile.id
    char_dir.mkdir(parents=True, exist_ok=True)
    json_path = char_dir / "character.json"
    data = asdict(profile)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return json_path


def approve_character_reference(
    char_id: str,
    version_filename: Optional[str] = None,
    base_dir: Optional[Path] = None
) -> CharacterProfile:
    """Approves the character reference, promoting candidate version to ref_portrait.png (active reference)."""
    effective_dir = base_dir or CHARACTER_LIB_DIR
    chars = load_character_library(effective_dir)
    profile = chars.get(char_id)
    if not profile:
        raise ValueError(f"Character '{char_id}' not found.")

    char_dir = effective_dir / char_id

    # Auto-resolve latest valid candidate version if none provided
    if not version_filename:
        versioned_candidates = []
        for p in char_dir.glob("ref_portrait_v*.png"):
            parts = p.stem.split("_v")
            if len(parts) == 2 and parts[1].isdigit():
                versioned_candidates.append((int(parts[1]), p))
        versioned_candidates.sort(key=lambda x: x[0], reverse=True)
        for _, v_path in versioned_candidates:
            if is_valid_image_file(v_path):
                version_filename = v_path.name
                break

    if version_filename:
        v_path = char_dir / version_filename
        if v_path.exists():
            shutil.copy2(v_path, char_dir / "ref_portrait.png")
            # Promote flow media id if present
            if version_filename in profile.flow_media_ids:
                media_id = profile.flow_media_ids[version_filename]
                profile.flow["media_id"] = media_id
                profile.flow_media_ids["ref_portrait.png"] = media_id

    profile.qc_status = "APPROVED"
    profile.flow["upload_status"] = "UPLOADED" if profile.flow.get("media_id") else "LOCAL_ONLY"
    if "ref_portrait.png" not in profile.references:
        profile.references.insert(0, "ref_portrait.png")

    save_character(profile, effective_dir)
    logger.info(f"[CharacterManager] Approved character reference for {char_id} (active: ref_portrait.png, source: {version_filename or 'existing'}).")
    return profile


def reject_character_reference(char_id: str, base_dir: Optional[Path] = None) -> CharacterProfile:
    """Rejects the character reference candidate without modifying existing approved reference."""
    effective_dir = base_dir or CHARACTER_LIB_DIR
    chars = load_character_library(effective_dir)
    profile = chars.get(char_id)
    if not profile:
        raise ValueError(f"Character '{char_id}' not found.")

    profile.qc_status = "REJECTED"
    save_character(profile, effective_dir)
    logger.info(f"[CharacterManager] Rejected character reference for {char_id}.")
    return profile


def upload_custom_character_reference(
    char_id: str,
    file_path_or_bytes: Path | str | bytes,
    base_dir: Optional[Path] = None
) -> Path:
    """Saves a user-uploaded image as a new reference version for the character."""
    effective_dir = base_dir or CHARACTER_LIB_DIR
    chars = load_character_library(effective_dir)
    profile = chars.get(char_id)
    if not profile:
        raise ValueError(f"Character '{char_id}' not found.")

    char_dir = effective_dir / char_id
    char_dir.mkdir(parents=True, exist_ok=True)

    # Archive existing ref_portrait.png to ref_portrait_v1.png if needed
    main_ref = char_dir / "ref_portrait.png"
    existing_versions = list(char_dir.glob("ref_portrait_v*.png"))
    v_nums = []
    for p in existing_versions:
        stem = p.stem
        parts = stem.split("_v")
        if len(parts) == 2 and parts[1].isdigit():
            v_nums.append(int(parts[1]))

    if main_ref.exists() and not existing_versions:
        v1_path = char_dir / "ref_portrait_v1.png"
        shutil.copy2(main_ref, v1_path)
        v_nums.append(1)

    next_v = (max(v_nums) + 1) if v_nums else 1
    new_version_filename = f"ref_portrait_v{next_v}.png"
    target_path = char_dir / new_version_filename

    if isinstance(file_path_or_bytes, (str, Path)):
        shutil.copy2(file_path_or_bytes, target_path)
    else:
        target_path.write_bytes(file_path_or_bytes)

    # If no main reference existed yet, initialize it
    if not main_ref.exists():
        shutil.copy2(target_path, main_ref)

    profile.references = ["ref_portrait.png", new_version_filename]
    profile.reference_source = "CUSTOM_UPLOAD"
    profile.qc_status = "AWAITING_REVIEW"
    profile.flow["upload_status"] = "LOCAL_ONLY"
    profile.flow["media_id"] = None
    save_character(profile, base_dir)
    logger.info(f"[CharacterManager] Custom reference uploaded for {char_id} ({new_version_filename}).")
    return target_path


def set_character_qc_status(char_id: str, status: str, base_dir: Path = CHARACTER_LIB_DIR) -> Optional[CharacterProfile]:
    """Sets QC/approval status for a character profile ("APPROVED", "REJECTED", "AWAITING_REVIEW")."""
    chars = load_character_library(base_dir)
    profile = chars.get(char_id)
    if profile:
        profile.qc_status = status
        save_character(profile, base_dir)
        return profile
    return None


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
