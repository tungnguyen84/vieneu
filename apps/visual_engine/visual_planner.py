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


@dataclass
class VisualScene:
    scene_id: str
    scene_index: int = 0
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    story_beat: str = ""
    story_importance: str = "MEDIUM"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    characters: List[str] = field(default_factory=list)
    location: str = "LAN_HOME"
    visual_type: str = "BANANA_IMAGE"  # "BANANA_IMAGE" or "OMNI_FLASH_I2V"
    motion_value: int = 0  # 0 - 100
    visual_reason: str = ""
    image_prompt: str = ""
    video_prompt: Optional[str] = None
    video_duration_sec: Optional[int] = None  # 4, 6, 8, 10
    motion: str = "slow_push_in"  # "slow_push_in", "slow_pull_out", "pan_left", "pan_right", "static"
    transition: str = "crossfade"  # "crossfade", "cut"
    status: str = "PLANNED"  # "PLANNED", "IMAGE_DONE", "VIDEO_DONE", "FAILED"
    segments_covered: List[str] = field(default_factory=list)
    delivery_profile: str = "NORMAL"
    story_context: str = ""
    image_media_id: Optional[str] = None
    image_url: Optional[str] = None
    video_media_id: Optional[str] = None
    video_url: Optional[str] = None
    reference_required: bool = True


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

        # Location ID check
        if loc_keys is not None:
            if sc.location not in loc_keys:
                issues.append(f"Scene {sc.scene_id} references unknown location ID: '{sc.location}'.")

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

            # Detect characters and location
            chars, loc = self._detect_entities(txt_lower, dominant_profile, character_lib, location_lib, cast)

            # Story beat extraction (first sentence or concise summary)
            first_sentence = combined_text.split(".")[0].strip()
            story_beat = first_sentence[:90] if first_sentence else f"Beat {idx + 1}"

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

            # Auto Video Duration resolution for Omni (Rule 13)
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

            # Camera Motion
            if dominant_profile == "REVEAL":
                motion = "slow_push_in"
                transition = "cut"
            elif dominant_profile in ("TENSION", "HOOK"):
                motion = "slow_push_in"
                transition = "cut"
            elif dominant_profile == "EMOTIONAL":
                motion = "slow_pull_out"
                transition = "crossfade"
            else:
                motion = motion_palette[idx % len(motion_palette)]
                transition = "crossfade"

            # Compose Prompts
            img_prompt, vid_prompt = self._compose_prompts(
                chars=chars,
                location=loc,
                text=combined_text,
                profile=dominant_profile,
                importance=importance,
                is_video=is_video,
                character_lib=character_lib,
                location_lib=location_lib,
                preset=preset
            )

            scene = VisualScene(
                scene_id=f"SC_{idx + 1:03d}",
                scene_index=idx + 1,
                start_sec=st,
                end_sec=en,
                duration_sec=dur,
                story_beat=story_beat,
                story_importance=importance,
                characters=chars,
                location=loc,
                visual_type=visual_type,
                motion_value=motion_value,
                visual_reason=visual_reason,
                image_prompt=img_prompt,
                video_prompt=vid_prompt,
                video_duration_sec=video_dur_sec,
                motion=motion,
                transition=transition,
                status="PLANNED",
                segments_covered=seg_ids,
                delivery_profile=dominant_profile,
                story_context=combined_text[:180] + ("..." if len(combined_text) > 180 else "")
            )
            scenes.append(scene)

        return scenes

    def _detect_entities(
        self,
        txt_lower: str,
        profile: str,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        cast: Optional[Dict[str, Any]]
    ) -> Tuple[List[str], str]:
        """Maps narrative keywords to valid Character and Location Library IDs."""
        chars: List[str] = []
        loc = "LAN_HOME"

        # Character resolution with explicit phrase and context matching
        if any(w in txt_lower for w in ("người cậu", "ông cậu", "chăm cậu", "nuôi cậu", "cậu bị", "cậu nằm", "cậu của", "bác sĩ", "viện phí")):
            chars.append("UNCLE")

        if any(w in txt_lower for w in ("hùng", "chồng tôi", "chồng cô", "người chồng", "anh hùng", "chồng em")):
            chars.append("HUNG")

        if any(w in txt_lower for w in ("lan", "cô", "vợ tôi", "vợ anh", "người phụ nữ")):
            if any(w in txt_lower for w in ("7 năm trước", "bảy năm trước", "lúc trẻ", "thời con gái", "hồi tưởng", "còn học cấp ba", "năm xưa")):
                chars.append("LAN_YOUNG")
            else:
                chars.append("LAN_ADULT")

        # Fallback default character from cast/lib
        if not chars:
            chars = ["LAN_ADULT"]

        # Filter characters against character_lib to ensure 0 invalid character IDs
        valid_chars = [c for c in chars if c in character_lib]
        if not valid_chars:
            valid_chars = ["LAN_ADULT"] if "LAN_ADULT" in character_lib else list(character_lib.keys())[:1]

        # Location resolution
        if any(w in txt_lower for w in ("nghĩa trang", "ngôi mộ", "viếng mộ", "phần mộ", "thắp hương", "nấm mộ", "bia mộ")):
            loc = "CEMETERY"
        elif any(w in txt_lower for w in ("bệnh viện", "phòng cấp cứu", "viện phí", "giường bệnh", "nằm viện")):
            loc = "HOSPITAL_GRAVE" if "HOSPITAL_GRAVE" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("nhà người cậu", "quê", "căn nhà cấp bốn", "về quê")):
            loc = "UNCLE_HOME" if "UNCLE_HOME" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("phòng ngủ", "ngăn kéo", "tủ quần áo", "đầu giường", "lá thư", "dưới đáy ngăn kéo")):
            loc = "LAN_BEDROOM" if "LAN_BEDROOM" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("quán cà phê", "quán nước", "góc phố")):
            loc = "CAFE" if "CAFE" in location_lib else "LAN_HOME"
        elif any(w in txt_lower for w in ("đường phố", "vỉa hè", "bước ra ngoài", "xe cộ")):
            loc = "STREET" if "STREET" in location_lib else "LAN_HOME"
        else:
            loc = "LAN_HOME"

        if loc not in location_lib:
            loc = list(location_lib.keys())[0] if location_lib else "LAN_HOME"

        return valid_chars, loc

    def _compose_prompts(
        self,
        chars: List[str],
        location: str,
        text: str,
        profile: str,
        importance: str,
        is_video: bool,
        character_lib: Dict[str, CharacterProfile],
        location_lib: Dict[str, LocationProfile],
        preset: Dict[str, Any]
    ) -> Tuple[str, Optional[str]]:
        """Composes Series Style + Character Lock + Location Lock + Action prompts."""
        series_style_info = preset.get("series_visual_style", {})
        genre = series_style_info.get("genre", "Vietnamese cinematic social mystery drama")
        look_elements = ", ".join(series_style_info.get("look", ["photorealistic", "natural Vietnamese faces", "cinematic 35mm photography"]))

        # 1. Character Identity Lock block
        char_blocks = []
        for cid in chars:
            c = character_lib.get(cid)
            if c:
                char_blocks.append(
                    f"CHARACTER ID: {c.id} ({c.name}). Appearance: {c.appearance}. "
                    f"Face: {c.face or 'natural authentic Vietnamese features'}. "
                    f"Hair: {c.hair}. "
                    f"Default clothing: {c.default_clothing}. "
                    f"Preserve facial identity, age, hairstyle and body proportions strictly."
                )

        char_text = " | ".join(char_blocks) if char_blocks else "Authentic Vietnamese subject"

        # 2. Location Lock block
        loc_prof = location_lib.get(location)
        if loc_prof:
            loc_text = f"LOCATION: {loc_prof.name}. Environment: {loc_prof.description}. Style: {loc_prof.visual_style}. Lighting: {loc_prof.lighting_default}."
        else:
            loc_text = "LOCATION: Domestic Vietnamese room. Soft natural lighting."

        # 3. Scene Action and Mood
        mood = "Quiet contemplative domestic atmosphere"
        if profile == "REVEAL":
            mood = "Stark emotional stillness, piercing revelation ambiance, restrained dramatic intensity, no melodrama"
        elif profile in ("TENSION", "HOOK"):
            mood = "Subtle domestic suspense, deep shadows, tight emotional focus, nervous searching eyes"
        elif profile == "EMOTIONAL":
            mood = "Tender melancholic sorrow, genuine sorrowful expression, muted nostalgic tones"
        elif profile == "MYSTERY":
            mood = "Subtle cinematic contrast, questioning atmosphere, earnest curiosity"

        # 4. Final Image Prompt
        img_prompt = (
            f"{genre}. {look_elements}. "
            f"{char_text}. "
            f"{loc_text} "
            f"Scene action: {text[:140]}. "
            f"Atmosphere: {mood}. 16:9 ratio, 35mm film still."
        )

        # 5. Video Prompt (Rule 17 & 18: Focused motion, strictly preventing hallucination)
        vid_prompt = None
        if is_video:
            if profile == "REVEAL":
                motion_desc = "Slow cinematic push-in toward the subject. Subject remains utterly still with subtle stunned breathing, eyes widening slightly in shock. No dialogue, no sudden movements."
            elif profile in ("TENSION", "HOOK"):
                motion_desc = "Slow deliberate camera push-in. Subject subtly turns head, glances down with anxious breath, gentle natural motion. High emotional restraint."
            elif profile == "EMOTIONAL":
                motion_desc = "Slow subtle drift or gentle pull-out. Subject looks down, quiet sorrowful breathing, delicate natural emotional reaction."
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
