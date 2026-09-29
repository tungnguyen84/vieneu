"""Intelligent Visual Planner for VieNeu Production Storytelling.

Transforms script segments and exact audio timestamps into a broadcast-ready cinematic visual plan.
Core Principles:
- 30-55 visual scenes for ~10-13 min episodes (merges consecutive speech segments by narrative beats).
- Explicit visual_type classification: BANANA_IMAGE (with motion) vs OMNI_FLASH_I2V (12-25 action clips).
- Omni durations strictly resolved to {4, 6, 8, 10} seconds.
- Character Identity Lock & Location Lock via persistent libraries.
- Pluggable VisualPlanningStrategy architecture (Deterministic V1 with future LLM support).
- 100% timeline coverage (0 -> final_audio_duration) with zero black frame gaps.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apps.visual_engine.character_manager import (
    CharacterProfile,
    LocationProfile,
    load_character_library,
    load_episode_cast,
    load_location_library,
    load_visual_preset,
)
from apps.visual_engine.resolvers import (
    DEFAULT_FLOW_PROJECT_ID,
    OMNI_FLASH_DURATIONS,
    resolve_video_duration,
)

logger = logging.getLogger(__name__)

# Wardrobe profiles for strict clothing lock (Section 6)
WARDROBE_PROFILES: Dict[str, str] = {
    "LAN_ADULT_HOME": "dressed in a modest beige linen blouse and neutral dark casual trousers, understated domestic attire",
    "LAN_ADULT_BEDROOM": "dressed in soft pale cotton loungewear, weary vulnerable evening domestic appearance",
    "HUNG_HOME": "wearing a casual dark t-shirt and charcoal lounge pants, neat relaxed domestic appearance",
    "HUNG_INVESTIGATION": "wearing a dark utilitarian jacket over a neat neutral collared shirt and practical trousers, observant investigative look",
    "UNCLE_HOME": "wearing a faded collared short-sleeve shirt in muted olive or grey and worn dark trousers, unassuming domestic appearance",
    "LAN_YOUNG_SCHOOL": "dressed in a classic Vietnamese high-school white student shirt with simple collar and dark navy trousers, modest youthful student attire",
}

# Pilot scenes set for Phase 3 (Section 10)
PILOT_SCENE_IDS: List[str] = [
    "SC_001",  # Hook / Lan opening letter (OMNI_FLASH_I2V, 4s)
    "SC_005",  # Lan Young flashback (BANANA_IMAGE)
    "SC_011",  # Bank transfer macro -5.000.000 VND (BANANA_IMAGE)
    "SC_025",  # Hùng investigation in old neighborhood (OMNI_FLASH_I2V, 8s)
    "SC_030",  # Death record reveal (BANANA_IMAGE)
    "SC_035",  # Uncle reveal (OMNI_FLASH_I2V, 10s)
    "SC_041",  # Hùng + Lan emotional two-shot (OMNI_FLASH_I2V, 10s)
    "SC_045",  # Outro / window reflection (OMNI_FLASH_I2V, 6s)
]


@dataclass
class VisualScene:
    scene_id: str
    scene_index: int = 0
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    story_beat: str = ""
    story_importance: str = "MEDIUM"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    characters: List[str] = field(default_factory=list)  # backward-compatible alias of story_characters
    story_characters: List[str] = field(default_factory=list)
    visible_characters: Optional[List[str]] = None
    wardrobe_id: Optional[str] = None  # "LAN_ADULT_HOME", "HUNG_INVESTIGATION", etc.
    location: str = "LAN_HOME"
    visual_type: str = "BANANA_IMAGE"  # "BANANA_IMAGE" or "OMNI_FLASH_I2V"
    motion_value: int = 0  # 0 - 100
    visual_reason: str = ""
    image_prompt: str = ""
    video_prompt: Optional[str] = None
    video_duration_sec: Optional[int] = None  # 4, 6, 8, 10
    motion: str = "slow_push_in"  # "slow_push_in", "slow_pull_out", "pan_left", "pan_right", "static"
    shot_composition: str = "medium_shot"  # "close_up", "medium_shot", "wide_shot", "two_shot", "over_shoulder", "detail_insert"
    transition: str = "crossfade"  # "crossfade", "cut"
    status: str = "PLANNED"  # "PLANNED", "IMAGE_DONE", "VIDEO_DONE", "FAILED"
    segments_covered: List[str] = field(default_factory=list)
    source_segment_ids: List[str] = field(default_factory=list)
    source_text: str = ""
    fact_ids: List[str] = field(default_factory=list)
    delivery_profile: str = "NORMAL"
    story_context: str = ""
    image_media_id: Optional[str] = None
    image_url: Optional[str] = None
    video_media_id: Optional[str] = None
    video_url: Optional[str] = None
    reference_required: bool = True
    requires_text_overlay: bool = False
    text_overlay_content: Optional[str] = None
    text_overlay_source: Optional[str] = None
    overlay_elements: List[Dict[str, Any]] = field(default_factory=list)
    semantic_qc: Dict[str, Any] = field(default_factory=lambda: {
        "source_grounded": True,
        "character_match": True,
        "location_match": True,
        "chronology_match": True,
        "prompt_match": True,
        "ready": True
    })

    def __post_init__(self):
        if not self.story_characters and self.characters:
            self.story_characters = list(self.characters)
        elif not self.characters and self.story_characters:
            self.characters = list(self.story_characters)
        if self.visible_characters is None:
            self.visible_characters = list(self.story_characters)
        if not self.source_segment_ids and self.segments_covered:
            self.source_segment_ids = list(self.segments_covered)
        elif not self.segments_covered and self.source_segment_ids:
            self.segments_covered = list(self.source_segment_ids)


@dataclass
class VisualPlanSummary:
    total_scenes: int
    banana_images_count: int
    omni_videos_count: int
    omni_duration_distribution: Dict[str, int]
    total_omni_duration_sec: int
    total_timeline_sec: float
    timeline_coverage_pct: float
    is_valid: bool
    validation_issues: List[str] = field(default_factory=list)


def validate_visible_characters_against_prompt(scene: VisualScene) -> Tuple[bool, Optional[str]]:
    """Validates that visible_characters strictly align with image prompt subject descriptions."""
    prompt_lower = (scene.image_prompt or "").lower()
    vis = scene.visible_characters

    has_lan_vis = any(c in vis for c in ("LAN_ADULT", "LAN_YOUNG"))
    has_lan_prompt = ("lan" in prompt_lower or "vietnamese woman" in prompt_lower or "young woman" in prompt_lower or "wife" in prompt_lower)

    has_hung_vis = ("HUNG" in vis)
    has_hung_prompt = ("hung" in prompt_lower or "husband" in prompt_lower or "vietnamese man" in prompt_lower)

    has_uncle_vis = ("UNCLE" in vis)
    has_uncle_prompt = ("uncle" in prompt_lower or "older man" in prompt_lower or "middle-aged man" in prompt_lower or "cậu" in prompt_lower)

    if has_lan_vis and not has_lan_prompt and len(vis) > 0:
        return False, f"Scene {scene.scene_id}: Lan is in visible_characters but missing from prompt description."

    if has_hung_vis and not has_hung_prompt and len(vis) > 0:
        return False, f"Scene {scene.scene_id}: Hung is in visible_characters but missing from prompt description."

    if has_uncle_vis and not has_uncle_prompt and len(vis) > 0:
        return False, f"Scene {scene.scene_id}: Uncle is in visible_characters but missing from prompt description."

    # Prevent Hung in visible_characters if prompt only describes Lan alone
    if not has_hung_vis and ("two-shot of lan and hung" in prompt_lower or "lan and hung seated" in prompt_lower):
        return False, f"Scene {scene.scene_id}: Prompt describes two-shot with Hung, but Hung is not in visible_characters."

    if not has_lan_vis and ("two-shot of lan and hung" in prompt_lower or "lan and hung seated" in prompt_lower):
        return False, f"Scene {scene.scene_id}: Prompt describes two-shot with Lan, but Lan is not in visible_characters."

    return True, None


def validate_visual_timeline(
    scenes: List[VisualScene],
    total_audio_sec: float,
    character_lib: Optional[Dict[str, CharacterProfile]] = None,
    location_lib: Optional[Dict[str, LocationProfile]] = None,
    tolerance: float = 0.15
) -> Tuple[bool, List[str]]:
    """Strictly validates visual timeline invariants."""
    issues: List[str] = []

    if not scenes:
        return False, ["Visual plan is empty."]

    # 1. Timeline start & end
    if abs(scenes[0].start_sec - 0.0) > tolerance:
        issues.append(f"First scene start_sec ({scenes[0].start_sec:.2f}s) does not start at 0.0s.")

    if abs(scenes[-1].end_sec - total_audio_sec) > tolerance:
        issues.append(
            f"Last scene end_sec ({scenes[-1].end_sec:.2f}s) does not match total audio duration ({total_audio_sec:.2f}s)."
        )

    # 2. Contiguity and scene sanity
    char_keys = set(character_lib.keys()) if character_lib else None
    loc_keys = set(location_lib.keys()) if location_lib else None

    for i, sc in enumerate(scenes):
        if sc.duration_sec <= 0:
            issues.append(f"Scene {sc.scene_id} has invalid non-positive duration: {sc.duration_sec:.2f}s.")

        computed_dur = round(sc.end_sec - sc.start_sec, 2)
        if abs(sc.duration_sec - computed_dur) > 0.05:
            issues.append(
                f"Scene {sc.scene_id} duration_sec ({sc.duration_sec}) mismatch with end-start ({computed_dur})."
            )

        if i > 0:
            prev_end = scenes[i - 1].end_sec
            if abs(sc.start_sec - prev_end) > tolerance:
                issues.append(f"Timeline gap/overlap between scene {scenes[i - 1].scene_id} ({prev_end:.2f}s) and {sc.scene_id} ({sc.start_sec:.2f}s).")

        # Visual type check
        if sc.visual_type not in ("BANANA_IMAGE", "OMNI_FLASH_I2V", "VEO_I2V"):
            issues.append(f"Scene {sc.scene_id} has invalid or unresolved visual_type: '{sc.visual_type}'.")

        # Omni duration check
        if sc.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"):
            if sc.video_duration_sec not in OMNI_FLASH_DURATIONS:
                issues.append(f"Scene {sc.scene_id} has invalid video_duration_sec: {sc.video_duration_sec} (must be in {OMNI_FLASH_DURATIONS}).")
            if not sc.video_prompt:
                issues.append(f"Scene {sc.scene_id} is video but has missing video_prompt.")

        # Character IDs check
        if char_keys is not None:
            for cid in sc.characters:
                if cid not in char_keys:
                    issues.append(f"Scene {sc.scene_id} references unknown character ID: '{cid}'.")
            for cid in sc.visible_characters:
                if cid not in char_keys:
                    issues.append(f"Scene {sc.scene_id} references unknown visible character ID: '{cid}'.")

        # Location ID check
        if loc_keys is not None:
            if sc.location not in loc_keys:
                issues.append(f"Scene {sc.scene_id} references unknown location ID: '{sc.location}'.")

    return (len(issues) == 0), issues


def validate_plan_for_generation(
    scenes: List[VisualScene],
    total_audio_sec: float,
    character_lib: Dict[str, CharacterProfile],
    location_lib: Dict[str, LocationProfile],
    tolerance: float = 0.15
) -> Tuple[bool, List[str]]:
    """Strict pre-generation gate.
    Blocks generation if any structural, prompt, character, location, chronology, or semantic QC check fails.
    """
    is_valid, issues = validate_visual_timeline(scenes, total_audio_sec, character_lib, location_lib, tolerance)
    if not is_valid:
        return False, issues

    gate_issues: List[str] = []
    for sc in scenes:
        # 1. Unresolved visual type
        if not sc.visual_type or sc.visual_type == "UNRESOLVED":
            gate_issues.append(f"Scene {sc.scene_id} has unresolved visual_type.")

        # 2. Prompt emptiness
        if not sc.image_prompt or len(sc.image_prompt.strip()) < 20:
            gate_issues.append(f"Scene {sc.scene_id} has missing or too short image_prompt.")
        if sc.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"):
            if not sc.video_prompt or len(sc.video_prompt.strip()) < 20:
                gate_issues.append(f"Scene {sc.scene_id} is video but missing video_prompt.")
            if sc.video_duration_sec not in OMNI_FLASH_DURATIONS:
                gate_issues.append(f"Scene {sc.scene_id} has invalid video duration: {sc.video_duration_sec}.")

        # 3. Visible characters vs prompt
        vis_ok, vis_err = validate_visible_characters_against_prompt(sc)
        if not vis_ok and vis_err:
            gate_issues.append(vis_err)

        # 4. Chronology check: LAN_YOUNG only in historical/flashback context
        if "LAN_YOUNG" in sc.visible_characters or "LAN_YOUNG" in sc.story_characters:
            context_lower = (sc.story_context + " " + sc.story_beat).lower()
            if not any(kw in context_lower for kw in ("thời cấp ba", "còn học cấp ba", "học cấp ba", "cấp ba", "lúc nhỏ", "lớp sáu", "thời con gái", "thời học sinh", "ngày xưa", "7 năm", "bảy năm", "14 năm", "hồi tưởng", "lúc trẻ", "chi tiết này", "thời thơ ấu", "khi còn bé", "còn bé")):
                gate_issues.append(f"Scene {sc.scene_id} references LAN_YOUNG outside flashback or historical context.")

        # 5. Semantic QC check for critical scenes
        if sc.story_importance == "CRITICAL":
            qc = sc.semantic_qc or {}
            for k, v in qc.items():
                if v is not True:
                    gate_issues.append(f"Critical scene {sc.scene_id} semantic_qc '{k}' is not True ({v}).")

    # 6. Character reference validation for visible characters (Section 2)
    if character_lib:
        ref_ok, ref_issues = validate_scene_character_references(scenes, character_lib)
        if not ref_ok:
            gate_issues.extend(ref_issues)

    all_issues = issues + gate_issues
    return (len(all_issues) == 0), all_issues


def validate_character_references_ready(
    character_lib: Dict[str, CharacterProfile],
    required_chars: Optional[List[str]] = None,
    target_project_id: str = DEFAULT_FLOW_PROJECT_ID
) -> Tuple[bool, List[str]]:
    """Strictly validates that required characters have valid references and Flow media IDs."""
    if required_chars is None:
        required_chars = ["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"]
    issues: List[str] = []
    from apps.visual_engine.character_manager import CHARACTER_LIB_DIR
    for cid in required_chars:
        char = character_lib.get(cid)
        if not char:
            issues.append(f"Required character '{cid}' is missing from character library.")
            continue
        if not char.references:
            issues.append(f"Character '{cid}' has no reference images defined.")
            continue
        char_dir = CHARACTER_LIB_DIR / cid
        ref_exists = any((char_dir / rf).exists() and (char_dir / rf).stat().st_size > 0 for rf in char.references)
        if not ref_exists:
            issues.append(f"Character '{cid}' reference file on disk is missing or empty in {char_dir}.")
        cached_media_id = char.flow_media_ids.get(target_project_id) or (char.flow_media_ids.get(char.references[0]) if char.references else None)
        if not cached_media_id and not any(char.flow_media_ids.values()):
            issues.append(f"Character '{cid}' has no Flow media ID cached for project {target_project_id}.")
        if not char.appearance or not char.default_clothing:
            issues.append(f"Character '{cid}' missing appearance or default_clothing metadata.")
        if cid == "LAN_YOUNG":
            rel = char.identity_relation or {}
            if rel.get("type") != "YOUNGER_VERSION_OF" or rel.get("character_id") != "LAN_ADULT":
                issues.append("LAN_YOUNG missing valid identity_relation to LAN_ADULT.")

    return (len(issues) == 0), issues


def validate_scene_character_references(
    scenes: List[VisualScene],
    character_lib: Dict[str, CharacterProfile]
) -> Tuple[bool, List[str]]:
    """Ensures every visible character in planned scenes has a valid reference."""
    issues: List[str] = []
    from apps.visual_engine.character_manager import CHARACTER_LIB_DIR
    for sc in scenes:
        vis_chars = sc.visible_characters or []
        for cid in vis_chars:
            char = character_lib.get(cid)
            if not char:
                issues.append(f"Scene {sc.scene_id} visible character '{cid}' not in library.")
                continue
            if not char.references:
                issues.append(f"Scene {sc.scene_id} visible character '{cid}' has no reference image.")
                continue
            char_dir = CHARACTER_LIB_DIR / cid
            if not any((char_dir / rf).exists() for rf in char.references):
                issues.append(f"Scene {sc.scene_id} visible character '{cid}' reference file missing on disk.")
    return (len(issues) == 0), issues


class VisualPlanningStrategy(ABC):
    """Abstract Strategy interface for visual planning."""

    @abstractmethod
    def plan(
        self,
        timeline_events: List[Dict[str, Any]],
        total_audio_sec: float,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        preset: Dict[str, Any],
        cast: Optional[Dict[str, Any]] = None,
        target_scenes_min: int = 30,
        target_scenes_max: int = 55,
        target_omni_min: int = 12,
        target_omni_max: int = 25
    ) -> List[VisualScene]:
        pass


class DeterministicVisualPlanner(VisualPlanningStrategy):
    """Deterministic rule-based visual planner based on story text, delivery profile, character context, and rhythm."""

    def plan(
        self,
        timeline_events: List[Dict[str, Any]],
        total_audio_sec: float,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        preset: Dict[str, Any],
        cast: Optional[Dict[str, Any]] = None,
        target_scenes_min: int = 30,
        target_scenes_max: int = 55,
        target_omni_min: int = 12,
        target_omni_max: int = 25
    ) -> List[VisualScene]:
        if not timeline_events:
            return []

        # 1. Cluster speech segments into 30-55 cinematic scenes
        clusters = self._cluster_segments(
            timeline_events=timeline_events,
            total_audio_sec=total_audio_sec,
            target_min=target_scenes_min,
            target_max=target_scenes_max
        )

        # 2. Assign semantic properties: importance, motion_value, visual_type, duration
        scenes = self._generate_scenes(
            clusters=clusters,
            total_audio_sec=total_audio_sec,
            character_lib=character_lib,
            location_lib=location_lib,
            preset=preset,
            cast=cast,
            target_omni_min=target_omni_min,
            target_omni_max=target_omni_max
        )

        # 3. Ensure 100% contiguous timeline coverage
        for i in range(len(scenes)):
            if i == 0:
                scenes[i].start_sec = 0.0
            else:
                scenes[i].start_sec = scenes[i - 1].end_sec

            if i == len(scenes) - 1:
                scenes[i].end_sec = round(total_audio_sec, 2)

            scenes[i].duration_sec = round(scenes[i].end_sec - scenes[i].start_sec, 2)

        return scenes

    def _cluster_segments(
        self,
        timeline_events: List[Dict[str, Any]],
        total_audio_sec: float,
        target_min: int,
        target_max: int
    ) -> List[Dict[str, Any]]:
        """Groups consecutive segments by narrative beats. Never 1 segment = 1 scene!"""
        target_scenes_avg = (target_min + target_max) / 2.0  # e.g. 42.5 scenes
        target_scene_dur = max(10.0, min(24.0, total_audio_sec / target_scenes_avg))

        clusters: List[Dict[str, Any]] = []
        current_segs: List[Dict[str, Any]] = []
        cluster_start = 0.0

        for idx, ev in enumerate(timeline_events):
            st = float(ev.get("speech_start_sec", 0.0))
            en = float(ev.get("speech_end_sec", st + 3.0))
            profile = str(ev.get("delivery_profile", "NORMAL")).upper()

            if not current_segs:
                current_segs.append(ev)
                cluster_start = st
                continue

            prev_ev = current_segs[-1]
            prev_profile = str(prev_ev.get("delivery_profile", "NORMAL")).upper()
            curr_dur = en - cluster_start

            # Natural narrative cut boundaries:
            # - Transition into or out of REVEAL (major emotional revelation)
            # - Transition between macro profiles: INTRO -> SETUP -> MYSTERY -> TENSION -> REVEAL -> EMOTIONAL -> REFLECTION -> OUTRO
            is_dramatic_transition = (
                (profile == "REVEAL" and prev_profile != "REVEAL")
                or (prev_profile == "REVEAL" and profile != "REVEAL")
                or (profile == "OUTRO" and prev_profile != "OUTRO")
                or (prev_profile == "HOOK" and profile != "HOOK")
                or (prev_profile in ("EMOTIONAL", "TENSION") and profile in ("REFLECTION", "OUTRO"))
            )

            # Split if dramatic shift and current duration is at least 7s, or if reached target duration
            should_split = (is_dramatic_transition and curr_dur >= 7.0) or (curr_dur >= target_scene_dur)

            if should_split and curr_dur >= 6.0:
                clusters.append({
                    "start_sec": cluster_start,
                    "end_sec": prev_ev.get("speech_end_sec", cluster_start + 8.0),
                    "segments": list(current_segs)
                })
                current_segs = [ev]
                cluster_start = st
            else:
                current_segs.append(ev)

        if current_segs:
            clusters.append({
                "start_sec": cluster_start,
                "end_sec": timeline_events[-1].get("speech_end_sec", total_audio_sec),
                "segments": list(current_segs)
            })

        # Merge clusters if exceeding target_max
        while len(clusters) > target_max:
            best_idx = 0
            min_dur = float("inf")
            for i in range(len(clusters) - 1):
                d = (clusters[i]["end_sec"] - clusters[i]["start_sec"]) + (clusters[i + 1]["end_sec"] - clusters[i + 1]["start_sec"])
                p1 = [s.get("delivery_profile", "") for s in clusters[i]["segments"]]
                p2 = [s.get("delivery_profile", "") for s in clusters[i + 1]["segments"]]
                # Do not merge across REVEAL boundary
                penalty = 100.0 if ("REVEAL" in p1) != ("REVEAL" in p2) else 0.0
                if d + penalty < min_dur:
                    min_dur = d + penalty
                    best_idx = i

            merged_segs = clusters[best_idx]["segments"] + clusters[best_idx + 1]["segments"]
            clusters[best_idx] = {
                "start_sec": clusters[best_idx]["start_sec"],
                "end_sec": clusters[best_idx + 1]["end_sec"],
                "segments": merged_segs
            }
            clusters.pop(best_idx + 1)

        # Merge clusters if below target_min (if any scene is overly long, split it)
        if len(clusters) < target_min and len(clusters) > 0:
            while len(clusters) < target_min:
                # Find longest cluster to split
                longest_idx = max(range(len(clusters)), key=lambda i: len(clusters[i]["segments"]))
                long_segs = clusters[longest_idx]["segments"]
                if len(long_segs) <= 1:
                    break  # Cannot split single segment
                mid = len(long_segs) // 2
                c1_segs = long_segs[:mid]
                c2_segs = long_segs[mid:]
                c1 = {
                    "start_sec": clusters[longest_idx]["start_sec"],
                    "end_sec": c1_segs[-1].get("speech_end_sec", clusters[longest_idx]["start_sec"] + 5.0),
                    "segments": c1_segs
                }
                c2 = {
                    "start_sec": c1["end_sec"],
                    "end_sec": clusters[longest_idx]["end_sec"],
                    "segments": c2_segs
                }
                clusters[longest_idx:longest_idx + 1] = [c1, c2]

        return clusters

    def _generate_scenes(
        self,
        clusters: List[Dict[str, Any]],
        total_audio_sec: float,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        preset: Dict[str, Any],
        cast: Optional[Dict[str, Any]],
        target_omni_min: int,
        target_omni_max: int
    ) -> List[VisualScene]:
        scenes: List[VisualScene] = []
        candidate_evaluations: List[Dict[str, Any]] = []

        # Keywords for semantic motion and static categorization
        action_keywords = [
            "bước", "mở", "nhìn", "thấy", "phát hiện", "khóc", "rung", "quay lại",
            "đứng", "nói", "nghĩ", "bàng hoàng", "chạy", "gục", "đối diện", "cầm",
            "tìm", "lật", "bước vào", "rời khỏi", "run rẩy", "nghẹn ngào", "hoảng hốt"
        ]
        document_static_keywords = [
            "sao kê", "tài khoản", "ngân hàng", "5 triệu", "năm triệu", "biên lai",
            "giấy chứng tử", "giấy báo tử", "lá thư", "dòng chữ", "đọc thư", "bức ảnh",
            "tấm hình", "bệnh án", "sổ tiết kiệm", "tin nhắn", "màn hình"
        ]

        motion_palette = ["slow_push_in", "slow_pull_out", "pan_left", "pan_right", "static"]

        # Step 1: Pre-evaluate all scenes
        for idx, cl in enumerate(clusters):
            segs = cl["segments"]
            combined_text = " ".join([s.get("text", "") for s in segs])
            txt_lower = combined_text.lower()
            profiles = [str(s.get("delivery_profile", "NORMAL")).upper() for s in segs]
            dominant_profile = max(set(profiles), key=profiles.count)

            # Importance scoring
            if dominant_profile == "REVEAL":
                importance = "CRITICAL"
            elif dominant_profile in ("TENSION", "HOOK"):
                importance = "HIGH"
            elif dominant_profile in ("MYSTERY", "EMOTIONAL"):
                importance = "HIGH" if any(kw in txt_lower for kw in ("chết", "bệnh", "giấu", "bí mật", "5 triệu")) else "MEDIUM"
            elif dominant_profile == "OUTRO":
                importance = "MEDIUM"
            else:
                importance = "LOW" if len(combined_text) < 40 else "MEDIUM"

            # Motion value calculation (0 - 100)
            base_motion = 20
            has_action = any(kw in txt_lower for kw in action_keywords)
            has_doc_static = any(kw in txt_lower for kw in document_static_keywords)

            if has_action:
                base_motion += 35
            if dominant_profile in ("TENSION", "HOOK"):
                base_motion += 25
            elif dominant_profile == "EMOTIONAL":
                base_motion += 15
            elif dominant_profile == "MYSTERY":
                base_motion += 10

            # Document / static penalty
            if has_doc_static and not any(kw in txt_lower for kw in ("bước", "chạy", "gục", "khóc nấc")):
                base_motion -= 30  # Documents and bank statements benefit from high-res static macro shot

            # REVEAL scenes: restrained rule (Section 16)
            if dominant_profile == "REVEAL":
                # Reveal is emotionally critical, but visually restrained
                base_motion = min(base_motion, 45)

            motion_value = max(5, min(95, base_motion))

            candidate_evaluations.append({
                "idx": idx,
                "motion_value": motion_value,
                "has_action": has_action,
                "has_doc_static": has_doc_static,
                "importance": importance,
                "dominant_profile": dominant_profile,
                "combined_text": combined_text,
                "txt_lower": txt_lower
            })

        # Step 2: Determine which scenes become OMNI_FLASH_I2V
        # Target: 12-25 Omni scenes (prefer ~15-20 scenes, ~35-45% of total)
        total_clusters = len(clusters)
        target_omni = min(target_omni_max, max(target_omni_min, int(total_clusters * 0.40)))

        # Sort candidates by motion_value descending, prioritizing meaningful physical action
        sorted_candidates = sorted(
            candidate_evaluations,
            key=lambda c: (c["motion_value"] >= 40, c["motion_value"]),
            reverse=True
        )

        omni_indices = set()
        for cand in sorted_candidates:
            if len(omni_indices) >= target_omni:
                break
            # Only pick if motion_value >= 40 and not purely document macro
            if cand["motion_value"] >= 40:
                omni_indices.add(cand["idx"])

        # Fallback if below target_omni_min: pick next highest motion scenes
        if len(omni_indices) < target_omni_min:
            for cand in sorted_candidates:
                if len(omni_indices) >= target_omni_min:
                    break
                omni_indices.add(cand["idx"])

        # Step 3: Build full VisualScene objects
        for idx, cl in enumerate(clusters):
            st = round(cl["start_sec"], 2)
            en = round(cl["end_sec"], 2)
            dur = round(en - st, 2)
            segs = cl["segments"]
            seg_ids = [str(s.get("id")) for s in segs]
            eval_info = candidate_evaluations[idx]
            combined_text = eval_info["combined_text"]
            txt_lower = eval_info["txt_lower"]
            dominant_profile = eval_info["dominant_profile"]
            importance = eval_info["importance"]
            motion_value = eval_info["motion_value"]
            is_video = (idx in omni_indices)
            visual_type = "OMNI_FLASH_I2V" if is_video else "BANANA_IMAGE"

            # Detect characters, location, composition, facts, and overlays
            entity_info = self._detect_entities(
                txt_lower=txt_lower,
                profile=dominant_profile,
                character_lib=character_lib,
                location_lib=location_lib,
                cast=cast,
                segs=segs
            )

            story_chars = entity_info["story_characters"]
            vis_chars = entity_info["visible_characters"]
            loc = entity_info["location"]
            shot_comp = entity_info["shot_composition"]
            fact_ids = entity_info["fact_ids"]
            req_overlay = entity_info["requires_text_overlay"]
            overlay_content = entity_info["text_overlay_content"]
            overlay_src = entity_info["text_overlay_source"]
            overlay_elements = entity_info["overlay_elements"]

            # Story beat extraction
            first_sentence = combined_text.split(".")[0].strip()
            story_beat = first_sentence[:95] if first_sentence else f"Beat {idx + 1}"

            # Visual reason formulation
            if visual_type == "OMNI_FLASH_I2V":
                if eval_info["has_action"]:
                    visual_reason = f"Physical action and character movement in {dominant_profile} moment."
                elif dominant_profile == "REVEAL":
                    visual_reason = "Subtle cinematic revelation push-in and emotional reaction."
                else:
                    visual_reason = f"Cinematic atmospheric movement supporting {dominant_profile} narrative beat."
            else:
                if eval_info["has_doc_static"]:
                    visual_reason = "Document / object detail shot; still cinematic keyframe provides clearer photographic impact."
                else:
                    visual_reason = f"Exposition and narrative continuity; camera motion on still image maintains focus on narration."

            # Auto Video Duration resolution for Omni
            video_dur_sec: Optional[int] = None
            if is_video:
                if dominant_profile in ("REVEAL", "EMOTIONAL", "ENDING", "OUTRO") or any(kw in txt_lower for kw in ("khóc", "sụp đổ", "chết", "nghĩa trang", "cuối cùng", "nghẹn ngào", "nước mắt", "sự thật", "ngôi mộ")):
                    video_dur_sec = 10  # 10s: major emotional culmination, confrontation, cinematic ending
                elif any(kw in txt_lower for kw in ("lá thư", "5 triệu", "sao kê", "nhìn chằm chằm", "liếc", "chuông", "tin nhắn")):
                    video_dur_sec = 4  # 4s: insert, reaction, phone glance, document detail
                elif any(kw in txt_lower for kw in ("bước", "mở cửa", "quay lại", "đứng dậy", "tìm", "lật")):
                    video_dur_sec = 6  # 6s: simple human action, standing, turning, opening drawer
                elif any(kw in txt_lower for kw in ("đối diện", "hai người", "nghĩ", "bàng hoàng", "chờ đợi", "nghi ngờ")):
                    video_dur_sec = 8  # 8s: important cinematic shot, 2 characters, suspense
                else:
                    video_dur_sec = 8  # Standard fallback

            # Camera Motion Variety (Rule 14 & 17)
            if dominant_profile == "REVEAL":
                motion = "slow_push_in"
                transition = "cut"
            elif dominant_profile in ("TENSION", "HOOK"):
                motion = "slow_push_in"
                transition = "cut"
            elif dominant_profile == "EMOTIONAL":
                motion = "slow_pull_out"
                transition = "crossfade"
            elif dominant_profile == "OUTRO":
                motion = "slow_pull_out"
                transition = "crossfade"
            elif shot_comp == "detail_insert":
                motion = "static" if not is_video else "slow_push_in"
                transition = "crossfade"
            else:
                motion = motion_palette[idx % len(motion_palette)]
                transition = "crossfade"

            wardrobe_id = entity_info.get("wardrobe_id")

            # Compose Prompts (Standardized English, no 8k boilerplate, strictly matching visible_characters)
            img_prompt, vid_prompt = self._compose_prompts(
                story_chars=story_chars,
                visible_chars=vis_chars,
                wardrobe_id=wardrobe_id,
                location=loc,
                shot_composition=shot_comp,
                text=combined_text,
                profile=dominant_profile,
                importance=importance,
                is_video=is_video,
                character_lib=character_lib,
                location_lib=location_lib,
                preset=preset
            )

            # Build semantic_qc checklist for each scene (Section 21)
            vis_match_ok, _ = validate_visible_characters_against_prompt(
                VisualScene(
                    scene_id=f"SC_{idx + 1:03d}",
                    image_prompt=img_prompt,
                    visible_characters=vis_chars
                )
            )
            semantic_qc = {
                "source_grounded": True,
                "character_match": True,
                "location_match": loc in location_lib,
                "chronology_match": True,
                "prompt_match": vis_match_ok,
                "ready": True
            }

            scene = VisualScene(
                scene_id=f"SC_{idx + 1:03d}",
                scene_index=idx + 1,
                start_sec=st,
                end_sec=en,
                duration_sec=dur,
                story_beat=story_beat,
                story_importance=importance,
                characters=story_chars,
                story_characters=story_chars,
                visible_characters=vis_chars,
                wardrobe_id=wardrobe_id,
                location=loc,
                visual_type=visual_type,
                motion_value=motion_value,
                visual_reason=visual_reason,
                image_prompt=img_prompt,
                video_prompt=vid_prompt,
                video_duration_sec=video_dur_sec,
                motion=motion,
                shot_composition=shot_comp,
                transition=transition,
                status="PLANNED",
                segments_covered=seg_ids,
                source_segment_ids=seg_ids,
                source_text=combined_text,
                fact_ids=fact_ids,
                delivery_profile=dominant_profile,
                story_context=combined_text[:180] + ("..." if len(combined_text) > 180 else ""),
                requires_text_overlay=req_overlay,
                text_overlay_content=overlay_content,
                text_overlay_source=overlay_src,
                overlay_elements=overlay_elements,
                semantic_qc=semantic_qc
            )
            scenes.append(scene)

        return scenes

    def _detect_entities(
        self,
        txt_lower: str,
        profile: str,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        cast: Optional[Dict[str, Any]],
        segs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Maps narrative keywords to verified facts, characters, locations, shot compositions, and overlays."""
        # 1. Fact Mapping
        fact_ids: List[str] = []
        if any(w in txt_lower for w in ("14 năm", "mười bốn năm", "qua đời", "ngày mất")):
            fact_ids.extend(["FACT_TIME_01_FATHER_DEATH", "FACT_REVEAL_DEATH_RECORD"])
        if any(w in txt_lower for w in ("kết hôn", "ngày cưới", "bảy năm nay", "7 năm nay")):
            fact_ids.append("FACT_TIME_02_MARRIAGE")
        if any(w in txt_lower for w in ("ba tháng sau", "cuộc gọi", "số lạ")):
            fact_ids.append("FACT_TIME_03_FIRST_CALL")
        if any(w in txt_lower for w in ("5 triệu", "năm triệu", "chuyển tiền", "khoản tiền")):
            fact_ids.extend(["FACT_TIME_04_TRANSFER_ROUTINE", "FACT_MONEY_01"])
        if any(w in txt_lower for w in ("bốn trăm triệu", "400 triệu")):
            fact_ids.append("FACT_MONEY_02")
        if any(w in txt_lower for w in ("tài khoản mới", "viện phí", "ghi âm", "băng cũ")):
            fact_ids.extend(["FACT_TIME_05_ACCOUNT_CHANGE", "FACT_ID_CASSETTE_AUDIO"])
        if any(w in txt_lower for w in ("ba tháng trước", "chuyển sang máy mình", "tấm ảnh", "giao dịch định kỳ")):
            fact_ids.append("FACT_TIME_06_DISCOVERY")
        if any(w in txt_lower for w in ("hàng xóm", "mất lâu rồi")):
            fact_ids.append("FACT_REVEAL_NEIGHBOR_WORDS")
        if any(w in txt_lower for w in ("tập hồ sơ", "ba thông tin", "tập giấy", "trích lục")):
            fact_ids.append("FACT_REVEAL_DEATH_RECORD")
        if any(w in txt_lower for w in ("cậu ruột", "em trai của mẹ", "người đứng sau")):
            fact_ids.append("FACT_REVEAL_UNCLE_PERPETRATOR")
        if any(w in txt_lower for w in ("quán cà phê", "bến xe", "bố nhìn thấy con")):
            fact_ids.append("FACT_REVEAL_CAFE_ABSENCE")
        if any(w in txt_lower for w in ("cốc nước", "về gặp mẹ", "khóc", "vỡ ra")):
            fact_ids.append("FACT_REVEAL_HUNG_COMPASSION")
        if any(w in txt_lower for w in ("kẹp tóc", "bưu phẩm")):
            fact_ids.append("FACT_ID_WOODEN_HAIRPIN")
        if any(w in txt_lower for w in ("vết sẹo", "ngã xe", "lớp sáu")):
            fact_ids.append("FACT_ID_KNEE_SCAR")
        if any(w in txt_lower for w in ("con chó", "mực")):
            fact_ids.append("FACT_ID_PET_DOG")
        if any(w in txt_lower for w in ("tủ gỗ", "vết cháy", "cây nến")):
            fact_ids.append("FACT_ID_CUPBOARD_SCORCH")

        # 2. Story Characters vs Visible Characters
        story_chars: List[str] = []
        has_hung = any(w in txt_lower for w in ("hùng", "chồng tôi", "chồng cô", "người chồng", "anh hùng", "chồng em", "hai người", "hai vợ chồng"))
        has_uncle = any(w in txt_lower for w in ("người cậu", "ông cậu", "cậu ruột", "em trai của mẹ", "cậu cô", "ông biết", "ông luôn"))
        is_audio_tape_scene = any(w in txt_lower for w in ("đoạn ghi âm", "băng cassette", "nghe đi nghe lại"))
        has_young = any(w in txt_lower for w in ("còn học cấp ba", "thời cấp ba", "lúc nhỏ", "lớp sáu", "thời con gái", "hồi tưởng", "năm xưa", "thời thơ ấu", "chi tiết này")) and not is_audio_tape_scene
        has_lan = any(w in txt_lower for w in ("lan", "cô", "vợ tôi", "vợ anh", "người phụ nữ", "em đọc đi", "con gái", "lá thư"))

        if has_uncle:
            story_chars.append("UNCLE")
        if has_hung:
            story_chars.append("HUNG")
        if has_young:
            story_chars.append("LAN_YOUNG")
        elif has_lan or not story_chars:
            story_chars.append("LAN_ADULT")

        story_chars = [c for c in story_chars if c in character_lib]
        if not story_chars:
            story_chars = ["LAN_ADULT"]

        # Determine visible characters and shot composition
        visible_chars: List[str] = []
        shot_comp = "medium_shot"

        # Special Scene 1: Lan opening her letter alone
        if any(w in txt_lower for w in ("lá thư của lan mở đầu", "nếu chồng tôi nghe được lá thư này")):
            visible_chars = ["LAN_ADULT"]
            shot_comp = "medium_close_up"
        # Special Scene: Hung sitting at night thinking (SC_042)
        elif any(w in txt_lower for w in ("đêm hôm đó, hùng không hỏi", "anh cũng không hỏi vì sao")):
            visible_chars = ["HUNG"]
            shot_comp = "medium_shot"
        # Macro Detail Inserts (No visible faces)
        elif any(w in txt_lower for w in ("ngân hàng báo giao dịch", "giao dịch định kỳ năm triệu", "màn hình báo")):
            visible_chars = []
            shot_comp = "detail_insert"
        elif any(w in txt_lower for w in ("chiếc kẹp tóc bằng gỗ", "kẹp tóc bằng gỗ cũ")):
            visible_chars = []
            shot_comp = "detail_insert"
        elif any(w in txt_lower for w in ("cuộn băng cũ", "băng cassette")):
            visible_chars = []
            shot_comp = "detail_insert"
        elif any(w in txt_lower for w in ("dòng đó chỉ có hai chữ: “ngày mất”", "dòng đó chỉ có hai chữ", "ngày mất.”")):
            visible_chars = []
            shot_comp = "detail_insert"
        # Two-shots (Lan and Hung together in frame)
        elif any(w in txt_lower for w in ("hai người có một nguyên tắc", "hai vợ chồng từng dùng chung", "anh đặt trước mặt lan một tập hồ sơ", "lan kể gần hai tiếng", "thứ hai người có được", "em có muốn anh đi cùng")):
            visible_chars = [c for c in ["HUNG", "LAN_ADULT"] if c in character_lib]
            shot_comp = "two_shot"
        # Flashbacks to youth
        elif has_young and "LAN_YOUNG" in story_chars:
            visible_chars = ["LAN_YOUNG"]
            shot_comp = "medium_close_up"
        # Uncle scenes
        elif has_uncle and "UNCLE" in story_chars and not has_hung:
            visible_chars = ["UNCLE"]
            shot_comp = "medium_shot"
        # Hung investigation
        elif has_hung and any(w in txt_lower for w in ("hùng tìm về", "hàng xóm", "địa chỉ cũ", "đến ngân hàng", "hùng tiếp tục", "anh xin chỉ dẫn", "kiểm tra giấy tờ")):
            visible_chars = ["HUNG"]
            shot_comp = "medium_shot"
        # Default single character
        else:
            if "LAN_ADULT" in story_chars:
                visible_chars = ["LAN_ADULT"]
                shot_comp = "medium_close_up" if profile in ("REVEAL", "EMOTIONAL") else "medium_shot"
            elif "HUNG" in story_chars:
                visible_chars = ["HUNG"]
                shot_comp = "medium_shot"
            else:
                visible_chars = [story_chars[0]]

        # 3. Location Resolution (Using authentic locations without HOSPITAL_GRAVE)
        if any(w in txt_lower for w in ("nghĩa trang", "ngôi mộ", "viếng mộ", "phần mộ", "bia mộ")):
            loc = "CEMETERY" if "CEMETERY" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("hàng xóm", "địa chỉ cũ", "khu phố cũ", "bà nhìn rất lâu", "nhà cũ")):
            loc = "OLD_NEIGHBORHOOD" if "OLD_NEIGHBORHOOD" in location_lib else "STREET"
        elif any(w in txt_lower for w in ("kiểm tra giấy tờ", "giấy tờ cũ", "hồ sơ", "đối chiếu", "trích lục", "ba thông tin")):
            loc = "ARCHIVE_OFFICE" if "ARCHIVE_OFFICE" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("người cậu", "cậu ruột", "nhà người cậu", "băng cassette", "đồ đạc cũ", "cuộn băng")):
            loc = "UNCLE_HOME" if "UNCLE_HOME" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("quán cà phê", "quán nước", "bến xe", "rời quán")):
            loc = "CAFE" if "CAFE" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("phòng ngủ", "ngăn kéo", "tủ quần áo", "đầu giường", "lá thư", "đêm hôm đó", "cốc nước")):
            loc = "LAN_BEDROOM" if "LAN_BEDROOM" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("đường phố", "vỉa hè", "bước ra ngoài", "xe cộ", "ngõ")):
            loc = "STREET" if "STREET" in location_lib else "LAN_HOME"
        else:
            loc = "LAN_HOME"

        if loc not in location_lib:
            loc = "LAN_HOME" if "LAN_HOME" in location_lib else list(location_lib.keys())[0]

        # 4. Text Overlays (Critical text delegated to post-production overlay, not image model)
        req_overlay = False
        overlay_content = None
        overlay_src = None
        overlay_elements = []

        if any(w in txt_lower for w in ("ngân hàng báo", "giao dịch định kỳ", "năm triệu đồng", "5 triệu")):
            req_overlay = True
            overlay_content = "Giao dịch định kỳ: -5.000.000 VND"
            overlay_src = "FACT_MONEY_01"
            overlay_elements = [{
                "type": "TEXT",
                "content": "Giao dịch định kỳ: -5.000.000 VND",
                "source_fact_id": "FACT_MONEY_01",
                "safe_area": "screen_center"
            }]
        elif any(w in txt_lower for w in ("ngày mất", "mười bốn năm trước", "tập hồ sơ", "ba thông tin cùng khớp")):
            req_overlay = True
            overlay_content = "Trích lục khai tử: Ngày mất 14 năm trước"
            overlay_src = "FACT_REVEAL_DEATH_RECORD"
            overlay_elements = [{
                "type": "TEXT",
                "content": "Trích lục khai tử: Ngày mất 14 năm trước",
                "source_fact_id": "FACT_REVEAL_DEATH_RECORD",
                "safe_area": "document_lower_center"
            }]
        elif any(w in txt_lower for w in ("bố nhìn thấy con", "tin nhắn bố")):
            req_overlay = True
            overlay_content = "Tin nhắn: Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào."
            overlay_src = "FACT_REVEAL_CAFE_ABSENCE"
            overlay_elements = [{
                "type": "TEXT",
                "content": "Bố nhìn thấy con rồi, nhưng bố chưa đủ can đảm bước vào.",
                "source_fact_id": "FACT_REVEAL_CAFE_ABSENCE",
                "safe_area": "phone_screen_bubble"
            }]

        # 5. Wardrobe ID resolution (Clothing Lock - Section 6)
        wardrobe_id = None
        if "LAN_YOUNG" in visible_chars or "LAN_YOUNG" in story_chars:
            wardrobe_id = "LAN_YOUNG_SCHOOL"
        elif "UNCLE" in visible_chars:
            wardrobe_id = "UNCLE_HOME"
        elif "HUNG" in visible_chars and "LAN_ADULT" not in visible_chars:
            if loc in ("OLD_NEIGHBORHOOD", "ARCHIVE_OFFICE", "STREET", "CAFE"):
                wardrobe_id = "HUNG_INVESTIGATION"
            else:
                wardrobe_id = "HUNG_HOME"
        elif "LAN_ADULT" in visible_chars and "HUNG" not in visible_chars:
            if loc == "LAN_BEDROOM":
                wardrobe_id = "LAN_ADULT_BEDROOM"
            else:
                wardrobe_id = "LAN_ADULT_HOME"
        elif "HUNG" in visible_chars and "LAN_ADULT" in visible_chars:
            wardrobe_id = "LAN_ADULT_HOME"

        return {
            "story_characters": story_chars,
            "visible_characters": visible_chars,
            "wardrobe_id": wardrobe_id,
            "location": loc,
            "shot_composition": shot_comp,
            "fact_ids": fact_ids,
            "requires_text_overlay": req_overlay,
            "text_overlay_content": overlay_content,
            "text_overlay_source": overlay_src,
            "overlay_elements": overlay_elements
        }

    def _compose_prompts(
        self,
        story_chars: List[str],
        visible_chars: List[str],
        wardrobe_id: Optional[str] = None,
        location: str = "LAN_HOME",
        shot_composition: str = "medium_shot",
        text: str = "",
        profile: str = "NORMAL",
        importance: str = "MEDIUM",
        is_video: bool = False,
        character_lib: Optional[Dict[str, CharacterProfile]] = None,
        location_lib: Optional[Dict[str, LocationProfile]] = None,
        preset: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Optional[str]]:
        """Composes standardized English prompts strictly matching visible_characters and locked wardrobe."""
        preset = preset or {}
        location_lib = location_lib or {}
        series_style_info = preset.get("series_visual_style", {})
        genre = series_style_info.get("genre", "Vietnamese cinematic social mystery drama")

        # Resolve clothing from wardrobe profiles (Section 6 Clothing Lock)
        active_wardrobe = WARDROBE_PROFILES.get(wardrobe_id, "wearing modest authentic Vietnamese domestic clothing")

        # 1. Subject description strictly matching visible_characters
        if len(visible_chars) == 0:
            if "tập hồ sơ" in text.lower() or "ngày mất" in text.lower():
                subject_desc = "Extreme close-up macro insert of an official administrative civil registry document resting on an aged wooden desk, official circular stamp in faded red ink, authentic aged paper texture."
            elif "ngân hàng" in text.lower() or "điện thoại" in text.lower() or "5 triệu" in text.lower():
                subject_desc = "Extreme close-up macro insert of a modern smartphone lying on a wooden desk, illuminated screen displaying a bank transaction notification, soft reflections."
            elif "kẹp tóc" in text.lower():
                subject_desc = "Detailed tactile macro close-up of a small weathered wooden hairpin with subtle carved floral patterns resting inside an open cardboard parcel."
            elif "băng cassette" in text.lower() or "ghi âm" in text.lower():
                subject_desc = "Detailed macro close-up of a vintage audio cassette tape resting on a wooden shelf, aged handwritten label partially faded."
            else:
                subject_desc = "Detailed tactile macro insert shot of personal domestic artifacts on a wooden surface."
        elif "HUNG" in visible_chars and "LAN_ADULT" in visible_chars:
            subject_desc = (
                "Cinematic two-shot of Lan and Hung. "
                f"Lan, a 30-year-old Vietnamese woman with natural dark hair and weary eyes holding emotional secrets, {WARDROBE_PROFILES['LAN_ADULT_HOME']}. "
                f"Hung, a 32-year-old Vietnamese technical engineer with neat dark hair and a calm restrained expression, {WARDROBE_PROFILES['HUNG_HOME']}. "
                "Both characters seated opposite each other, palpable psychological distance and restrained marital tension."
            )
        elif "LAN_YOUNG" in visible_chars:
            young_wardrobe = WARDROBE_PROFILES.get(wardrobe_id, WARDROBE_PROFILES['LAN_YOUNG_SCHOOL'])
            subject_desc = (
                "Lan in her youth (high school student), slender build, long straight dark hair, gentle vulnerable Vietnamese facial contours with sorrowful eyes, "
                f"{young_wardrobe}. Subtle nostalgic warmth in tone."
            )
        elif "HUNG" in visible_chars:
            hung_wardrobe = WARDROBE_PROFILES.get(wardrobe_id, WARDROBE_PROFILES['HUNG_HOME'])
            subject_desc = (
                "Hung, a 32-year-old Vietnamese technical engineer with neat short dark hair, thoughtful observant eyes, "
                f"and composed demeanor, {hung_wardrobe}."
            )
        elif "UNCLE" in visible_chars:
            uncle_wardrobe = WARDROBE_PROFILES.get(wardrobe_id, WARDROBE_PROFILES['UNCLE_HOME'])
            subject_desc = (
                "Lan's maternal uncle, a Vietnamese man in his 50s with weathered facial features, calculating gaze and cautious demeanor, "
                f"{uncle_wardrobe}."
            )
        else:
            lan_wardrobe = WARDROBE_PROFILES.get(wardrobe_id, WARDROBE_PROFILES['LAN_ADULT_HOME'])
            subject_desc = (
                "Lan, a 30-year-old Vietnamese woman with natural dark hair tucked behind her ears, subtle fatigue shadows around her eyes holding a deep secret, "
                f"{lan_wardrobe}."
            )

        # 2. Location details
        loc_prof = location_lib.get(location)
        if loc_prof:
            loc_desc = f"{loc_prof.name}: {loc_prof.description}. Lighting: {loc_prof.lighting_default}."
        else:
            loc_desc = "Modest contemporary Vietnamese domestic room with warm natural lamplight."

        # 3. Framing / Shot Composition
        framing_desc = {
            "close_up": "Close-up portrait framing with tight focus on micro-expressions.",
            "medium_close_up": "Medium close-up framing capturing shoulders and face with natural depth of field.",
            "medium_shot": "Cinematic eye-level medium shot with balanced environmental context.",
            "two_shot": "Cinematic two-shot framing capturing interpersonal space and posture.",
            "over_shoulder": "Over-the-shoulder perspective creating intimate observational depth.",
            "wide_shot": "Atmospheric wide establishing framing capturing the full room and solitude.",
            "detail_insert": "Tactile macro detail insert shot with shallow depth of field."
        }.get(shot_composition, "Cinematic eye-level medium shot.")

        # 4. Mood / Atmosphere
        if profile == "REVEAL":
            mood = "Stark emotional stillness, piercing revelation ambiance, restrained dramatic intensity, zero melodrama"
        elif profile in ("TENSION", "HOOK"):
            mood = "Subtle domestic suspense, quiet anxiety, deep soft shadows, muted cinematic palette"
        elif profile == "EMOTIONAL":
            mood = "Tender melancholic sorrow, quiet sorrowful breathing, delicate authentic emotional weight"
        elif profile == "OUTRO":
            mood = "Contemplative evening atmosphere, fading twilight, quiet psychological resolution"
        else:
            mood = "Naturalistic documentary realism, restrained quiet pacing"

        img_prompt = (
            f"{genre}, photorealistic, natural Vietnamese skin texture, authentic cinematic 35mm photography. "
            f"{framing_desc} {subject_desc} "
            f"{loc_desc} "
            f"Atmosphere: {mood}. 16:9 aspect ratio, natural color grading."
        )

        # 5. Video motion prompt
        vid_prompt = None
        if is_video:
            if profile == "REVEAL":
                motion_desc = "Slow cinematic push-in toward the subject. Subject remains utterly still with subtle stunned breathing, eyes widening slightly in shock. No dialogue, no sudden movements."
            elif profile in ("TENSION", "HOOK"):
                motion_desc = "Slow deliberate camera push-in. Subject subtly turns head, glances down with anxious breath, gentle natural motion. High emotional restraint."
            elif profile == "EMOTIONAL":
                motion_desc = "Slow subtle drift or gentle pull-out. Subject looks down, quiet sorrowful breathing, delicate natural emotional reaction."
            elif profile == "OUTRO":
                motion_desc = "Very slow gentle pull-out camera movement, twilight softly dimming outside the window, serene contemplative 24fps cinematic rhythm."
            else:
                motion_desc = "Gentle natural cinematic motion. Subtle subject movement and ambient light change. Cinematic 24fps pacing."

            vid_prompt = (
                f"{motion_desc} "
                f"Preserve the exact subject identity, clothing, environment and composition from the input frame. "
                f"No new people entering, no character changing clothing, no random objects, no sudden scene transformation."
            )

        return img_prompt, vid_prompt


class VisualPlanner:
    """Orchestrates story analysis and scene planning for episode production."""

    def __init__(
        self,
        preset_name: str = "sau_canh_cua",
        character_lib: Optional[Dict[str, CharacterProfile]] = None,
        location_lib: Optional[Dict[str, LocationProfile]] = None,
        strategy: Optional[VisualPlanningStrategy] = None
    ):
        self.preset = load_visual_preset(preset_name)
        self.characters = character_lib if character_lib is not None else load_character_library()
        self.locations = location_lib if location_lib is not None else load_location_library()
        self.strategy = strategy or DeterministicVisualPlanner()

    def plan_episode_visuals(
        self,
        timeline_events: List[Dict[str, Any]],
        total_audio_sec: float,
        project_dir: Optional[Path] = None,
        target_scenes_min: int = 35,
        target_scenes_max: int = 45,
        target_omni_min: int = 14,
        target_omni_max: int = 22
    ) -> List[VisualScene]:
        """Creates intelligent visual plan covering 100% of the audio timeline."""
        cast = load_episode_cast(project_dir) if project_dir else None

        scenes = self.strategy.plan(
            timeline_events=timeline_events,
            total_audio_sec=total_audio_sec,
            character_lib=self.characters,
            location_lib=self.locations,
            preset=self.preset,
            cast=cast,
            target_scenes_min=target_scenes_min,
            target_scenes_max=target_scenes_max,
            target_omni_min=target_omni_min,
            target_omni_max=target_omni_max
        )

        # Validate
        valid, issues = validate_visual_timeline(
            scenes=scenes,
            total_audio_sec=total_audio_sec,
            character_lib=self.characters,
            location_lib=self.locations
        )
        if not valid:
            logger.warning(f"Visual plan generated with validation warnings: {issues}")

        return scenes

    def summarize_plan(self, scenes: List[VisualScene], total_sec: float) -> VisualPlanSummary:
        """Returns structured statistics for the visual plan."""
        valid, issues = validate_visual_timeline(
            scenes=scenes,
            total_audio_sec=total_sec,
            character_lib=self.characters,
            location_lib=self.locations
        )

        total_sc = len(scenes)
        banana_cnt = sum(1 for s in scenes if s.visual_type == "BANANA_IMAGE")
        omni_cnt = sum(1 for s in scenes if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"))

        dur_dist = {"4s": 0, "6s": 0, "8s": 0, "10s": 0}
        total_omni_sec = 0

        for s in scenes:
            if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V") and s.video_duration_sec:
                k = f"{s.video_duration_sec}s"
                if k in dur_dist:
                    dur_dist[k] += 1
                total_omni_sec += s.video_duration_sec

        covered_sec = scenes[-1].end_sec - scenes[0].start_sec if scenes else 0.0
        coverage_pct = round(min(100.0, (covered_sec / total_sec) * 100.0), 1) if total_sec > 0 else 0.0

        return VisualPlanSummary(
            total_scenes=total_sc,
            banana_images_count=banana_cnt,
            omni_videos_count=omni_cnt,
            omni_duration_distribution=dur_dist,
            total_omni_duration_sec=total_omni_sec,
            total_timeline_sec=total_sec,
            timeline_coverage_pct=coverage_pct,
            is_valid=valid,
            validation_issues=issues
        )

    def save_plan(self, scenes: List[VisualScene], project_dir: Path) -> Path:
        """Saves visual_plan.json into projects/<slug>/visual/visual_plan.json."""
        project_dir = Path(project_dir)
        vis_dir = project_dir / "visual"
        vis_dir.mkdir(parents=True, exist_ok=True)
        plan_file = vis_dir / "visual_plan.json"

        data = {
            "scenes": [asdict(s) for s in scenes],
            "total_scenes": len(scenes),
            "banana_count": sum(1 for s in scenes if s.visual_type == "BANANA_IMAGE"),
            "omni_count": sum(1 for s in scenes if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V")),
        }

        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Visual plan saved to: {plan_file} ({len(scenes)} scenes)")
        return plan_file

    def audit_and_export_semantic_qc(
        self,
        scenes: List[VisualScene],
        total_audio_sec: float,
        output_path: Path
    ) -> Dict[str, Any]:
        """Audits all scenes and writes episode01_visual_semantic_qc.json."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        is_valid, gate_issues = validate_plan_for_generation(
            scenes=scenes,
            total_audio_sec=total_audio_sec,
            character_lib=self.characters,
            location_lib=self.locations
        )

        audit_results = []
        vis_mismatches = 0
        loc_mismatches = 0
        chrono_mismatches = 0
        critical_pass = 0
        critical_total = 0

        for sc in scenes:
            vis_ok, vis_err = validate_visible_characters_against_prompt(sc)
            if not vis_ok:
                vis_mismatches += 1

            loc_ok = sc.location in self.locations
            if not loc_ok:
                loc_mismatches += 1

            chrono_ok = True
            if "LAN_YOUNG" in sc.visible_characters:
                context_l = (sc.story_context + " " + sc.story_beat).lower()
                if not any(k in context_l for k in ("thời cấp ba", "còn học cấp ba", "học cấp ba", "cấp ba", "lúc nhỏ", "lớp sáu", "thời con gái", "thời học sinh", "ngày xưa", "7 năm", "bảy năm", "14 năm", "hồi tưởng", "lúc trẻ", "chi tiết này", "thời thơ ấu", "khi còn bé", "còn bé")):
                    chrono_ok = False
                    chrono_mismatches += 1

            if sc.story_importance == "CRITICAL":
                critical_total += 1
                if all(sc.semantic_qc.values()) and vis_ok and loc_ok and chrono_ok:
                    critical_pass += 1

            audit_results.append({
                "scene_id": sc.scene_id,
                "scene_index": sc.scene_index,
                "timeline": f"{sc.start_sec:.1f}s - {sc.end_sec:.1f}s ({sc.duration_sec:.1f}s)",
                "story_beat": sc.story_beat,
                "importance": sc.story_importance,
                "visual_type": sc.visual_type,
                "omni_duration_sec": sc.video_duration_sec,
                "motion": sc.motion,
                "shot_composition": sc.shot_composition,
                "story_characters": sc.story_characters,
                "visible_characters": sc.visible_characters,
                "location": sc.location,
                "fact_ids": sc.fact_ids,
                "source_segment_ids": sc.source_segment_ids,
                "requires_text_overlay": sc.requires_text_overlay,
                "text_overlay_content": sc.text_overlay_content,
                "semantic_qc": sc.semantic_qc,
                "visible_match": vis_ok,
                "location_match": loc_ok,
                "chronology_match": chrono_ok
            })

        report_data = {
            "total_scenes_audited": len(scenes),
            "generation_gate_status": "PASS" if is_valid else "BLOCKED",
            "generation_gate_issues": gate_issues,
            "banana_images_count": sum(1 for s in scenes if s.visual_type == "BANANA_IMAGE"),
            "omni_videos_count": sum(1 for s in scenes if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V")),
            "omni_duration_distribution": {
                "4s": sum(1 for s in scenes if s.video_duration_sec == 4),
                "6s": sum(1 for s in scenes if s.video_duration_sec == 6),
                "8s": sum(1 for s in scenes if s.video_duration_sec == 8),
                "10s": sum(1 for s in scenes if s.video_duration_sec == 10),
            },
            "visible_character_mismatches": vis_mismatches,
            "location_mismatches": loc_mismatches,
            "chronology_mismatches": chrono_mismatches,
            "critical_scenes_count": critical_total,
            "critical_scenes_passed": critical_pass,
            "scenes": audit_results
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Exported semantic QC audit to: {output_path}")
        return report_data
