"""Google Flow App JSON Exporter (SCC_FLOW_V1).

Exports complete, standalone visual production plans for EP003 and EP011
into standardized Google Flow App JSON format.

Does NOT generate any media.
Does NOT use FlowKit.
Does NOT invent media IDs.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
VISUAL_DIR = BASE_DIR / "production_pilot_03_visual_v1_0a"
EXPORTS_DIR = VISUAL_DIR / "exports"
SNAPSHOT_BASE = BASE_DIR / "production_pilot_03"

SCHEMA_VERSION = "SCC_FLOW_V1"

GENERATION_SETTINGS = {
    "image_model": "BANANA_PRO",
    "video_model": "OMNI",
    "aspect_ratio": "16:9",
    "image_concurrency": 1,
    "image_delay_seconds": 10,
    "auto_generate_on_import": False,
    "generate_images": True,
    "generate_video_mode": "RECOMMENDED_ONLY",
    "strip_generated_video_audio": True
}


def parse_video_prompt_parts(vp: Optional[str]) -> Optional[Dict[str, str]]:
    """Parses structured video prompt into start_state, action, camera, end_state."""
    if not vp:
        return None

    # Standard format: Start: ... Action: ... Camera: ... End: ...
    m = re.search(r"Start:\s*(.*?)\s*Action:\s*(.*?)\s*Camera:\s*(.*?)\s*End:\s*(.*)", vp, re.DOTALL)
    if m:
        return {
            "start_state": m.group(1).strip(),
            "action": m.group(2).strip(),
            "camera": m.group(3).strip(),
            "end_state": m.group(4).strip(),
            "full_prompt": vp.strip()
        }
    return {
        "start_state": "",
        "action": "",
        "camera": "",
        "end_state": "",
        "full_prompt": vp.strip()
    }


def load_full_script_segments(ep_id: str) -> Dict[str, str]:
    """Loads segment texts from full_script.json snapshot."""
    script_path = SNAPSHOT_BASE / ep_id / "script_snapshot" / "full_script.json"
    if not script_path.exists():
        return {}
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    segments = data.get("segments", [])
    if not segments and isinstance(data, list):
        segments = data
    return {seg.get("id", seg.get("segment_id", f"{i+1:03d}")): seg.get("text", "") for i, seg in enumerate(segments)}


def build_episode_export(ep_id: str) -> Dict[str, Any]:
    """Builds a standardized Google Flow episode object from V1.0a artifacts."""
    ep_dir = VISUAL_DIR / ep_id

    # 1. Load Visual Plan
    with open(ep_dir / "visual_plan.json", "r", encoding="utf-8") as f:
        vplan = json.load(f)

    # 2. Load Character Bible & Identity Families
    with open(ep_dir / "character_bible.json", "r", encoding="utf-8") as f:
        cdata = json.load(f)
    raw_characters = cdata.get("characters", [])
    raw_families = cdata.get("identity_families", [])

    # 3. Load Prop Bible
    with open(ep_dir / "prop_bible.json", "r", encoding="utf-8") as f:
        raw_props = json.load(f)

    # 4. Load Location Bible
    with open(ep_dir / "location_bible.json", "r", encoding="utf-8") as f:
        raw_locations = json.load(f)

    # 5. Load Overlay Plan
    with open(ep_dir / "overlay_plan.json", "r", encoding="utf-8") as f:
        raw_overlays = json.load(f)

    # 6. Load Narration Segments
    seg_texts = load_full_script_segments(ep_id)

    # Build Identity Families
    identity_families = []
    family_anchor_map = {}
    for fam in raw_families:
        fam_id = fam.get("identity_family_id")
        anchor = fam.get("adult_reference") or fam.get("anchor_character")
        variant = fam.get("younger_variant")
        variants = [variant] if variant else fam.get("variants", [])
        gen_order = [anchor] + variants

        family_anchor_map[fam_id] = anchor
        identity_families.append({
            "identity_family_id": fam_id,
            "description": fam.get("description", ""),
            "anchor_character": anchor,
            "variants": variants,
            "generation_order": gen_order
        })

    # Build Characters
    characters = []
    char_bible_map = {}
    for c in raw_characters:
        cid = c["character_id"]
        is_young = (c.get("identity_role") == "YOUNGER_VARIANT")
        fam_id = c.get("identity_family_id")
        dep_ref = family_anchor_map.get(fam_id) if is_young else None

        char_obj = {
            "character_id": cid,
            "name": c["name"],
            "reference_required": c.get("requires_approval", True),
            "reference_status": "NOT_GENERATED",
            "identity_family_id": fam_id,
            "identity_role": c.get("identity_role"),
            "depends_on_reference": dep_ref,
            "use_identity_anchor": bool(dep_ref),
            "reference_prompt": c.get("reference_prompt", ""),
            "appearance": {
                "gender": c.get("gender"),
                "age": c.get("age"),
                "ethnicity": c.get("ethnicity", "Vietnamese"),
                "face_description": c.get("face_description", ""),
                "hair": c.get("hair", ""),
                "body_build": c.get("body_build", ""),
                "emotional_baseline": c.get("emotional_baseline", "")
            },
            "wardrobe": {
                "baseline": c.get("wardrobe_baseline", ""),
                "variants": c.get("wardrobe_variants", {})
            },
            "timeline": c.get("timeline_age", ""),
            "reference_media_id": None
        }
        characters.append(char_obj)
        char_bible_map[cid] = char_obj

    # Build Props with Dependencies
    props = []
    prop_bible_map = {}
    for p in raw_props:
        pid = p["prop_id"]
        ref_req = p.get("prop_reference_required", False)

        # Map character dependencies
        dep_chars = []
        if pid == "PROP_VINTAGE_PHOTO_BAO_THOA":
            dep_chars = ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"]
        elif pid == "PROP_HOSPITAL_PHOTO_2012":
            dep_chars = ["CHAR_NAM_YOUNG_2012", "CHAR_THAO_2012", "CHAR_BE_AN_INFANT_2012"]

        # Build clean reference prompt for props requiring reference
        ref_prompt = None
        if ref_req:
            if pid == "PROP_WOODEN_BOX":
                ref_prompt = (
                    "Studio product documentary photograph of an antique weathered Vietnamese wooden box (PROP_WOODEN_BOX) "
                    "crafted from aged jackfruit wood (gỗ mít), closed lid, 32cm x 22cm x 14cm proportions, rich natural wood grain "
                    "with aged weathered patina, darkened antique brass hinges and front brass latch clasp without padlock, "
                    "fine layer of dust on lid, resting on a clean neutral grey surface, 3/4 angle product view, soft balanced studio lighting, "
                    "crisp focus, 35mm photography, no people, no hands, no text, no watermark."
                )
            elif pid == "PROP_VINTAGE_PHOTO_BAO_THOA":
                ref_prompt = (
                    "Authentic vintage 1980s black-and-white photographic print with delicate scalloped edges: Two young Vietnamese "
                    "factory coworkers (young Bà Hảo, 32, and young Bà Thoa, 28) standing side-by-side outdoors before an old textile mill gate, "
                    "gentle genuine smiles, wearing authentic 1980s Vietnamese cotton factory workwear matching the reference images, "
                    "soft sepia tone, authentic photographic grain, 1980s archival documentary snapshot, no modern styling, no text."
                )
            elif pid == "PROP_OLD_PHONE_01":
                ref_prompt = (
                    "Product documentary photograph of a vintage 2010s candybar feature phone (PROP_OLD_PHONE_01), dark grey matte casing "
                    "with silver trim, physical numeric rubber keypad, small low-resolution color LCD screen, small round charging pin jack, "
                    "faint authentic hairline scratches on plastic casing, resting on a neutral grey studio surface, 3/4 angle product view, "
                    "clean balanced studio lighting, crisp focus, 35mm photography, no hands, no people, no text, no watermark."
                )
            elif pid == "PROP_HOSPITAL_PHOTO_2012":
                ref_prompt = (
                    "Authentic 2012 documentary snapshot: Young Vietnamese man (23, wearing a dark hoodie, matching reference anchor) "
                    "standing beside a young woman (21, resting in a pale green hospital gown, matching reference anchor) who tenderly "
                    "holds a sleeping swaddled newborn baby in a yellow blanket, in a provincial Vietnamese public hospital room with pale "
                    "mint-green walls, authentic 2012 digital camera texture, soft daylight, poignant emotional documentary snapshot, "
                    "no invented timestamp, no text overlays, no watermark."
                )
            elif pid == "PROP_SILVER_BRACELET":
                ref_prompt = (
                    "Product documentary photograph of a traditional Vietnamese baby silver bracelet (PROP_SILVER_BRACELET), solid sterling silver "
                    "with soft polished patina, small 4.5cm open adjustable cuff design, smooth outer surface, resting on a clean neutral white studio "
                    "pedestal, high-angle macro product view, soft studio lighting with gentle silver specular highlights, clean focus, 35mm macro lens, "
                    "no people, no hands, no text, no watermark."
                )

        prop_obj = {
            "prop_id": pid,
            "name": p["name"],
            "reference_required": ref_req,
            "reference_status": "NOT_GENERATED" if ref_req else "NOT_REQUIRED",
            "reference_prompt": ref_prompt,
            "reference_media_id": None,
            "continuity_description": p.get("material", "") or p.get("condition", "") or p.get("dimensions", ""),
            "depends_on_characters": dep_chars
        }
        props.append(prop_obj)
        prop_bible_map[pid] = prop_obj

    # Build Locations
    locations = []
    for loc in raw_locations:
        locations.append({
            "location_id": loc["location_id"],
            "name": loc["name"],
            "city_region": loc.get("city_region", ""),
            "type": loc.get("type", "INTERIOR"),
            "description": loc.get("architecture", "") or loc.get("story_function", ""),
            "visual_prompt": loc.get("reference_prompt", ""),
            "reference_required": False,
            "reference_media_id": None
        })

    # Build Overlays
    overlays = []
    for ov in raw_overlays.get("overlays", []):
        overlays.append({
            "scene_id": ov["scene_id"],
            "required": True,
            "overlay_type": ov.get("overlay_type", "DOCUMENT"),
            "title": ov.get("overlay_title", ""),
            "text": ov.get("overlay_text", ""),
            "start_time": ov["start_time"],
            "end_time": ov["end_time"],
            "duration": ov["duration"],
            "position": ov.get("overlay_position", "LOWER_THIRD"),
            "font_style": ov.get("font_style", "CLEAN_SERIF_DOCUMENTARY"),
            "render_method": "POST_RENDER",
            "generate_inside_image": False,
            "declared_claims": ov.get("declared_claims", [])
        })

    # Build Scenes
    scenes = []
    for sc in vplan["scenes"]:
        sid = sc["scene_id"]
        is_video = (sc["visual_mode"] == "VIDEO_RECOMMENDED")
        vp_obj = parse_video_prompt_parts(sc.get("video_prompt")) if is_video else None

        # Build narration summary from segment texts
        src_segs = sc.get("source_segments", [])
        narr_texts = [seg_texts.get(s, "") for s in src_segs if seg_texts.get(s)]
        narr_summary = " ".join(narr_texts) if narr_texts else sc.get("visual_mode_reason", "")

        # Calculate explicitly required character & prop references
        vis_chars = sc.get("visible_characters", [])
        char_refs_req = [c for c in vis_chars if char_bible_map.get(c, {}).get("reference_required", False)]

        scene_props = sc.get("props", [])
        prop_refs_req = [p for p in scene_props if prop_bible_map.get(p, {}).get("reference_required", False)]

        score = sc.get("video_value_scores", {}).get("total_score", 0)

        scene_obj = {
            "scene_id": sid,
            "order": sc["order"],
            "start_time": sc["start_time"],
            "end_time": sc["end_time"],
            "duration": sc["duration"],
            "source_segments": src_segs,
            "narration_summary": narr_summary,
            "visual_mode": sc["visual_mode"],
            "video_recommended": is_video,
            "video_value_score": score,
            "visible_characters": vis_chars,
            "character_refs_required": char_refs_req,
            "location_id": sc.get("location_id"),
            "props": scene_props,
            "prop_refs_required": prop_refs_req,
            "image_prompt": sc["image_prompt"],
            "video_prompt": vp_obj,
            "image_motion": sc.get("image_motion", {}),
            "generation_dependencies_satisfied": False,
            "image_status": "NOT_GENERATED",
            "image_media_id": None,
            "video_status": "NOT_GENERATED",
            "video_media_id": None
        }
        scenes.append(scene_obj)

    return {
        "episode_id": ep_id,
        "title": vplan["title"],
        "audio_duration": vplan["audio_duration_sec"],
        "generation_settings": GENERATION_SETTINGS,
        "identity_families": identity_families,
        "characters": characters,
        "props": props,
        "locations": locations,
        "overlays": overlays,
        "scenes": scenes
    }


def validate_flow_export(export_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Performs Section 35 strict validation checks."""
    errors = []
    episodes = export_data.get("episodes", [])
    if len(episodes) not in [1, 2]:
        errors.append(f"Expected 1 or 2 episodes in export, got {len(episodes)}")

    for ep in episodes:
        ep_id = ep["episode_id"]
        scenes = ep["scenes"]

        # 1. Scene Count == 45
        if len(scenes) != 45:
            errors.append(f"{ep_id}: Expected 45 scenes, got {len(scenes)}")

        # 2. Video Count
        video_count = sum(1 for s in scenes if s["visual_mode"] == "VIDEO_RECOMMENDED")
        expected_videos = 7 if ep_id == "EP003" else 8
        if video_count != expected_videos:
            errors.append(f"{ep_id}: Expected {expected_videos} video recommended scenes, got {video_count}")

        # 3. Image-Only Count
        image_only_count = sum(1 for s in scenes if s["visual_mode"] == "IMAGE_ONLY")
        expected_images = 38 if ep_id == "EP003" else 37
        if image_only_count != expected_images:
            errors.append(f"{ep_id}: Expected {expected_images} image-only scenes, got {image_only_count}")

        # 4. Character References Complete
        char_refs = [c for c in ep["characters"] if c["reference_required"]]
        expected_char_refs = 6 if ep_id == "EP003" else 7
        if len(char_refs) != expected_char_refs:
            errors.append(f"{ep_id}: Expected {expected_char_refs} character references, got {len(char_refs)}")

        # 5. Prop References Complete
        prop_refs = [p for p in ep["props"] if p["reference_required"]]
        expected_prop_refs = 2 if ep_id == "EP003" else 3
        if len(prop_refs) != expected_prop_refs:
            errors.append(f"{ep_id}: Expected {expected_prop_refs} prop references, got {len(prop_refs)}")

        # 6. Identity dependencies valid
        for c in ep["characters"]:
            if c.get("depends_on_reference"):
                anchor_id = c["depends_on_reference"]
                anchor_exists = any(ch["character_id"] == anchor_id for ch in ep["characters"])
                if not anchor_exists:
                    errors.append(f"{ep_id}: Character {c['character_id']} depends on missing anchor {anchor_id}")

        # 7. No Media IDs Invented (must be null)
        for c in ep["characters"]:
            if c.get("reference_media_id") is not None:
                errors.append(f"{ep_id}: Invented media ID in character {c['character_id']}")
        for p in ep["props"]:
            if p.get("reference_media_id") is not None:
                errors.append(f"{ep_id}: Invented media ID in prop {p['prop_id']}")
        for sc in scenes:
            if sc.get("image_media_id") is not None or sc.get("video_media_id") is not None:
                errors.append(f"{ep_id}: Invented media ID in scene {sc['scene_id']}")
            if sc.get("generation_dependencies_satisfied") is not False:
                errors.append(f"{ep_id}: generation_dependencies_satisfied must be False in scene {sc['scene_id']}")

        # 8. Visual Spoiler Guard
        sc31 = scenes[30]
        if sc31["scene_id"] != "SC_031" or sc31["visual_mode"] != "IMAGE_ONLY":
            errors.append(f"{ep_id}: Reveal 1 (SC_031) must be IMAGE_ONLY")

        sc39 = scenes[38]
        if sc39["scene_id"] != "SC_039" or sc39["visual_mode"] != "IMAGE_ONLY":
            errors.append(f"{ep_id}: Reveal 2 (SC_039) must be IMAGE_ONLY")

        for i in range(30):
            sc = scenes[i]
            text_check = (sc["image_prompt"] + " " + str(sc.get("video_prompt") or "")).lower()
            if ep_id == "EP003":
                if "nhà tình thương" in text_check or "trẻ mồ côi" in text_check:
                    errors.append(f"{ep_id}: Spoiler in scene {sc['scene_id']}")
            elif ep_id == "EP011":
                if "nhận nuôi hợp pháp" in text_check or "gia đình hiếm muộn" in text_check:
                    errors.append(f"{ep_id}: Spoiler in scene {sc['scene_id']}")

        # 9. All Prompts Non-empty
        for sc in scenes:
            if len(sc.get("image_prompt", "")) < 20:
                errors.append(f"{ep_id}: image_prompt too short in scene {sc['scene_id']}")
            if sc["visual_mode"] == "VIDEO_RECOMMENDED":
                vp = sc.get("video_prompt")
                if not vp or not vp.get("full_prompt"):
                    errors.append(f"{ep_id}: video_prompt missing in recommended scene {sc['scene_id']}")

        # 10. Timeline 100% continuous
        if scenes[0]["start_time"] != 0.0:
            errors.append(f"{ep_id}: First scene does not start at 0.0s")
        diff = abs(scenes[-1]["end_time"] - ep["audio_duration"])
        if diff > 0.10:
            errors.append(f"{ep_id}: Timeline end discrepancy {diff}s > 0.10s")
        for i in range(len(scenes) - 1):
            if round(scenes[i]["end_time"], 3) != round(scenes[i+1]["start_time"], 3):
                errors.append(f"{ep_id}: Discontinuity between {scenes[i]['scene_id']} and {scenes[i+1]['scene_id']}")

    return (len(errors) == 0), errors


def export_google_flow_app_json() -> Dict[str, Any]:
    """Generates EP003_google_flow.json, EP011_google_flow.json, and PRODUCTION_PILOT_03_google_flow.json."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    ep003_data = build_episode_export("EP003")
    ep011_data = build_episode_export("EP011")

    # Combined Package
    combined_export = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "series": "Sau Cánh Cửa",
            "production_id": "PRODUCTION_PILOT_03",
            "exported_at": round(time.time(), 3),
            "export_status": "GOOGLE_FLOW_EXPORT_READY"
        },
        "episodes": [ep003_data, ep011_data]
    }

    # Validate Combined
    is_valid, validation_errors = validate_flow_export(combined_export)
    if not is_valid:
        raise ValueError(f"Google Flow Export validation FAILED with errors:\n" + "\n".join(validation_errors))

    # Single EP003 Package
    ep003_export = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "series": "Sau Cánh Cửa",
            "production_id": "PRODUCTION_PILOT_03",
            "exported_at": round(time.time(), 3),
            "export_status": "GOOGLE_FLOW_EXPORT_READY"
        },
        "episodes": [ep003_data]
    }

    # Single EP011 Package
    ep011_export = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "series": "Sau Cánh Cửa",
            "production_id": "PRODUCTION_PILOT_03",
            "exported_at": round(time.time(), 3),
            "export_status": "GOOGLE_FLOW_EXPORT_READY"
        },
        "episodes": [ep011_data]
    }

    # Write files
    combined_path = EXPORTS_DIR / "PRODUCTION_PILOT_03_google_flow.json"
    ep003_path = EXPORTS_DIR / "EP003_google_flow.json"
    ep011_path = EXPORTS_DIR / "EP011_google_flow.json"

    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(combined_export, f, ensure_ascii=False, indent=2)

    with open(ep003_path, "w", encoding="utf-8") as f:
        json.dump(ep003_export, f, ensure_ascii=False, indent=2)

    with open(ep011_path, "w", encoding="utf-8") as f:
        json.dump(ep011_export, f, ensure_ascii=False, indent=2)

    return {
        "status": "PASS",
        "validation_status": "GOOGLE_FLOW_EXPORT_READY",
        "combined_file": str(combined_path.relative_to(BASE_DIR)),
        "ep003_file": str(ep003_path.relative_to(BASE_DIR)),
        "ep011_file": str(ep011_path.relative_to(BASE_DIR)),
        "ep003_stats": {
            "scenes": len(ep003_data["scenes"]),
            "image_only": sum(1 for s in ep003_data["scenes"] if s["visual_mode"] == "IMAGE_ONLY"),
            "video_recommended": sum(1 for s in ep003_data["scenes"] if s["visual_mode"] == "VIDEO_RECOMMENDED"),
            "characters": len([c for c in ep003_data["characters"] if c["reference_required"]]),
            "props": len([p for p in ep003_data["props"] if p["reference_required"]]),
            "locations": len(ep003_data["locations"]),
            "overlays": len(ep003_data["overlays"])
        },
        "ep011_stats": {
            "scenes": len(ep011_data["scenes"]),
            "image_only": sum(1 for s in ep011_data["scenes"] if s["visual_mode"] == "IMAGE_ONLY"),
            "video_recommended": sum(1 for s in ep011_data["scenes"] if s["visual_mode"] == "VIDEO_RECOMMENDED"),
            "characters": len([c for c in ep011_data["characters"] if c["reference_required"]]),
            "props": len([p for p in ep011_data["props"] if p["reference_required"]]),
            "locations": len(ep011_data["locations"]),
            "overlays": len(ep011_data["overlays"])
        }
    }


if __name__ == "__main__":
    res = export_google_flow_app_json()
    print("Export Result:", res)
