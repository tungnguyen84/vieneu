"""Visual Style Registry and Prompt Presets for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PRESETS_DIR = BASE_DIR / "visual_presets"

DEFAULT_VISUAL_STYLE = "cinematic_documentary"

SUPPORTED_VISUAL_STYLES: Dict[str, Dict[str, Any]] = {
    "cinematic_documentary": {
        "id": "cinematic_documentary",
        "name": "Phim tài liệu điện ảnh",
        "badge": "Ảnh chụp chân thực",
        "description": "Phong cách nhiếp ảnh tài liệu 35mm chân thực, hạt phim tự nhiên, bối cảnh đời thực Việt Nam.",
        "is_photoreal": True,
        "preset_file": "sau_canh_cua.json",
    },
    "manhua_viet": {
        "id": "manhua_viet",
        "name": "Manhua Đô Thị Việt",
        "badge": "Bán thực - Tông trầm",
        "description": "Nét vẽ manhua/donghua hiện đại bán thực, tỷ lệ người lớn, bối cảnh đô thị Việt, ánh sáng cinematic moody, không chữ Hán, không ảnh người thật.",
        "is_photoreal": False,
        "preset_file": "manhua_viet.json",
    },
    "2d_am_viet": {
        "id": "2d_am_viet",
        "name": "Tranh 2D Trầm Ấm Việt",
        "badge": "Minh họa điện ảnh",
        "description": "Phong cách minh họa 2D bán thực, chất liệu tranh vẽ có texture, tỷ lệ người lớn, ánh sáng ấm sâu lắng, bối cảnh Việt Nam, không chữ Hán.",
        "is_photoreal": False,
        "preset_file": "2d_am_viet.json",
    },
}


def normalize_visual_style(style_id: Optional[str]) -> str:
    """Validates and normalizes style identifier; defaults to cinematic_documentary."""
    if not style_id:
        return DEFAULT_VISUAL_STYLE
    clean = str(style_id).strip().lower()
    if clean in SUPPORTED_VISUAL_STYLES:
        return clean
    # Support alias 'sau_canh_cua' mapping to cinematic_documentary
    if clean == "sau_canh_cua":
        return DEFAULT_VISUAL_STYLE
    return DEFAULT_VISUAL_STYLE


def get_available_styles() -> List[Dict[str, Any]]:
    """Returns list of supported visual style definitions for UI and API consumption."""
    items = []
    for sid, info in SUPPORTED_VISUAL_STYLES.items():
        items.append({
            "id": info["id"],
            "name": info["name"],
            "badge": info["badge"],
            "description": info["description"],
            "is_photoreal": info["is_photoreal"],
            "is_default": (sid == DEFAULT_VISUAL_STYLE),
        })
    return items


def load_style_preset_data(style_id: str) -> Dict[str, Any]:
    """Loads raw preset JSON from visual_presets/<name>.json."""
    norm = normalize_visual_style(style_id)
    preset_filename = SUPPORTED_VISUAL_STYLES[norm]["preset_file"]
    preset_file = PRESETS_DIR / preset_filename
    if preset_file.exists():
        try:
            return json.loads(preset_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def compose_character_reference_prompt(
    name: str,
    age: Optional[int],
    gender: Optional[str],
    role: str,
    description: str,
    visual_style: str = DEFAULT_VISUAL_STYLE
) -> str:
    """Builds a visual identity reference prompt matching the chosen visual style."""
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
    style = normalize_visual_style(visual_style)

    if style == "manhua_viet":
        return (
            f"Semi-realistic manhua character concept sheet of Vietnamese character {name}. "
            f"Illustrated Vietnamese {gender_tag}, {age_tag}with authentic Vietnamese facial features, mature adult proportions, "
            "detailed digital line art with subtle shading, composed neutral expression, neat contemporary hairstyle. "
            "Wearing contemporary tasteful Vietnamese smart-casual attire. "
            "Waist-up framing, clean studio background, dramatic cinematic lighting, 16:9, not a real human photo, strictly no Chinese text, no watermark."
        )
    elif style == "2d_am_viet":
        return (
            f"Cinematic 2D digital illustration portrait of Vietnamese character {name}. "
            f"Stylized semi-realistic Vietnamese {gender_tag}, {age_tag}with natural Vietnamese facial anatomy, realistic adult proportions, "
            "painterly brushwork with crisp focal details, composed contemplative expression. "
            "Wearing contemporary tasteful Vietnamese smart-casual attire. "
            "Waist-up framing, warm textured background, soft chiaroscuro lighting, 16:9, not a real human photo, no Chinese text, no text, no watermark."
        )
    else:
        # Default: EXACT byte-for-byte backward compatible with original code
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


def compose_scene_image_prompt(
    scene_idx: int,
    combined_text: str,
    visible_characters: List[str],
    location_name: str,
    dominant_profile: str,
    characters_map: Dict[str, Dict[str, Any]],
    visual_style: str = DEFAULT_VISUAL_STYLE
) -> str:
    """Creates a specific visual moment for the keyframe adhering to the chosen visual style."""
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
    style = normalize_visual_style(visual_style)

    if style == "manhua_viet":
        return (
            f"Modern Vietnamese urban manhua semi-realistic illustration, mature graphic novel art style. Setting: {clean_loc} (authentic Vietnamese urban environment, no Chinese characters or signage). "
            f"Visible cast ONLY: {'; '.join(identities) or 'no identifiable character'}. "
            f"Depict this concrete moment from the source scene: {moment[:450]}. "
            "Do not invent a spouse, visitor, age, gender, object or event absent from the source. "
            "Preserve reference character designs and clothing; semi-realistic manhua art, balanced 16:9 composition, strictly no Chinese text, no captions, no watermark, not a real human photo."
        )
    elif style == "2d_am_viet":
        return (
            f"Contemporary Vietnamese 2D cinematic digital illustration, painterly textured art style, mature adult proportions. Setting: {clean_loc} (authentic Vietnamese domestic environment, no Chinese text). "
            f"Visible cast ONLY: {'; '.join(identities) or 'no identifiable character'}. "
            f"Depict this concrete moment from the source scene: {moment[:450]}. "
            "Do not invent a spouse, visitor, age, gender, object or event absent from the source. "
            "Preserve reference character designs and wardrobe; balanced 16:9 composition, strictly no Chinese characters, no captions, no watermark, not a real human photo."
        )
    else:
        # Default: EXACT byte-for-byte backward compatible with original code
        return (
            f"Vietnamese cinematic documentary realism, 35mm photography, natural film grain. Setting: {clean_loc}. "
            f"Visible cast ONLY: {'; '.join(identities) or 'no identifiable character'}. "
            f"Depict this concrete moment from the source scene: {moment[:450]}. "
            "Do not invent a spouse, visitor, age, gender, object or event absent from the source. "
            "Preserve reference identities and wardrobe; balanced 16:9 composition, no captions, no watermark."
        )


def compose_scene_video_prompt(
    scene_idx: int,
    combined_text: str,
    visible_characters: List[str],
    location_name: str,
    dominant_profile: str,
    visual_style: str = DEFAULT_VISUAL_STYLE
) -> Dict[str, str]:
    """Generates a scene-specific dynamic video prompt adhering strictly to Start/Action/Camera/End."""
    clean_loc = re.sub(r"\(.*?\)", "", location_name).strip()
    start = f"Preserve the exact approved keyframe, character references and setting {clean_loc}. Visible cast: {', '.join(visible_characters)}."
    action = f"Animate only the action already depicted in the keyframe from this source scene: {combined_text[:450]}. Do not add characters or a new event."

    style = normalize_visual_style(visual_style)
    if style == "manhua_viet":
        camera = "Subtle restrained animation camera movement, smooth comic panel pan, stable illustrated character identity, no sudden cuts."
        end = "End on the same established illustrated scene with natural motion settling; no text overlays or audible dialogue."
    elif style == "2d_am_viet":
        camera = "Slow cinematic illustration drift, soft parallax motion, stable character continuity, no sudden cuts."
        end = "End on the same established illustrated scene with natural motion settling; no text overlays or audible dialogue."
    else:
        # Default: EXACT byte-for-byte backward compatible with original code
        camera = "Slow restrained documentary camera movement, stable facial identity, no sudden cuts."
        end = "End on the same established scene with natural motion settling; no text overlays or audible dialogue."

    return {
        "start": start,
        "action": action,
        "camera": camera,
        "end": end,
        "full_prompt": f"START: {start} ACTION: {action} CAMERA: {camera} END: {end}"
    }


def compose_location_reference_prompt(clean_name: str, visual_style: str = DEFAULT_VISUAL_STYLE) -> str:
    """Builds a location reference prompt matching the chosen visual style."""
    style = normalize_visual_style(visual_style)
    if style == "manhua_viet":
        return f"Semi-realistic Vietnamese urban manhua background reference: {clean_name}. Authentic Vietnamese architecture, moody cinematic lighting, 16:9, strictly no Chinese signage or text, no watermark."
    elif style == "2d_am_viet":
        return f"Cinematic Vietnamese 2D illustration environment concept: {clean_name}. Painterly texture, warm atmospheric lighting, 16:9, authentic Vietnamese ambiance, strictly no Chinese characters, no text, no watermark."
    else:
        return f"Cinematic Vietnamese location reference: {clean_name}. Natural light, realistic documentary style, 16:9, no text, no watermark."


def compose_default_location_reference_prompt(visual_style: str = DEFAULT_VISUAL_STYLE) -> str:
    """Builds a default location reference prompt matching the chosen visual style."""
    style = normalize_visual_style(visual_style)
    if style == "manhua_viet":
        return "Contemporary Vietnamese urban apartment living room, semi-realistic manhua background art, moody cinematic lighting, 16:9, strictly no Chinese text, no text, no watermark."
    elif style == "2d_am_viet":
        return "Contemporary Vietnamese family home, cinematic 2D textured digital illustration, warm ambient light, 16:9, strictly no Chinese text, no watermark."
    else:
        return "Contemporary Vietnamese family home, cinematic documentary realism, natural light, 16:9, no text, no watermark."
