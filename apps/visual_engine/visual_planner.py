"""Visual Planner for VieNeu Production Storytelling.

Transforms TTS speech timeline events and script context into a cohesive cinematic visual plan.
Ensures:
- 30-55 visual scenes for ~10-13 min episodes (merging consecutive speech segments).
- Hybrid generation: BANANA_IMAGE (with motion) + VEO_I2V (15-30 cinematic action clips).
- Character consistency via Character Library appearance anchoring.
- Zero black frame gaps across the entire timeline.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_engine.character_manager import (
    CharacterProfile,
    LocationProfile,
    load_character_library,
    load_location_library,
    load_visual_preset,
)

logger = logging.getLogger(__name__)


@dataclass
class VisualScene:
    scene_id: str
    scene_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    visual_type: str  # "BANANA_IMAGE" or "VEO_I2V"
    characters: List[str] = field(default_factory=list)
    location: str = "LAN_HOME"
    story_context: str = ""
    image_prompt: str = ""
    video_prompt: Optional[str] = None
    motion: str = "slow_push_in"  # "slow_push_in", "slow_pull_out", "pan_left", "pan_right", "static"
    transition: str = "crossfade"  # "crossfade", "hard_cut"
    video_duration: int = 8
    reference_required: bool = True
    status: str = "PLANNED"  # "PLANNED", "IMAGE_DONE", "VIDEO_DONE", "FAILED"
    segments_covered: List[str] = field(default_factory=list)
    delivery_profile: str = "NORMAL"
    image_media_id: Optional[str] = None
    image_url: Optional[str] = None
    video_media_id: Optional[str] = None
    video_url: Optional[str] = None


@dataclass
class VisualPlanSummary:
    total_scenes: int
    banana_images_count: int
    veo_clips_count: int
    total_veo_duration_sec: int
    total_timeline_sec: float
    estimated_banana_cost: str
    estimated_veo_cost: str


class VisualPlanner:
    """Orchestrates story analysis and scene planning for episode production."""

    def __init__(
        self,
        preset_name: str = "sau_canh_cua",
        character_lib: Optional[Dict[str, CharacterProfile]] = None,
        location_lib: Optional[Dict[str, LocationProfile]] = None
    ):
        self.preset = load_visual_preset(preset_name)
        self.characters = character_lib or load_character_library()
        self.locations = location_lib or load_location_library()

    def plan_episode_visuals(
        self,
        timeline_events: List[Dict[str, Any]],
        total_audio_sec: float,
        target_scenes_min: int = 30,
        target_scenes_max: int = 55,
        target_veo_min: int = 15,
        target_veo_max: int = 30
    ) -> List[VisualScene]:
        """
        Groups speech segments into 30-55 cinematic visual scenes.
        Classifies each scene as BANANA_IMAGE or VEO_I2V based on emotional beat,
        delivery profile, action cues, and rhythm.
        """
        if not timeline_events:
            return []

        # 1. Cluster contiguous segments into scenes
        raw_clusters = self._cluster_segments(
            timeline_events,
            total_audio_sec,
            target_scenes_min=target_scenes_min,
            target_scenes_max=target_scenes_max
        )

        # 2. Assign visual types (BANANA_IMAGE vs VEO_I2V)
        scenes = self._assign_visual_types_and_prompts(
            raw_clusters,
            total_audio_sec,
            target_veo_min=target_veo_min,
            target_veo_max=target_veo_max
        )

        return scenes

    def _cluster_segments(
        self,
        events: List[Dict[str, Any]],
        total_audio_sec: float,
        target_scenes_min: int,
        target_scenes_max: int
    ) -> List[Dict[str, Any]]:
        """Groups contiguous segments into cohesive scene clusters averaging 14-25 seconds."""
        clusters: List[Dict[str, Any]] = []
        current_cluster_segs: List[Dict[str, Any]] = []
        cluster_start = 0.0

        target_scene_dur = max(12.0, min(24.0, total_audio_sec / ((target_scenes_min + target_scenes_max) / 2)))

        for idx, ev in enumerate(events):
            st = float(ev.get("speech_start_sec", 0.0))
            en = float(ev.get("speech_end_sec", st + ev.get("duration_sec", 3.0)))
            profile = str(ev.get("delivery_profile", "NORMAL")).upper()

            if not current_cluster_segs:
                current_cluster_segs.append(ev)
                cluster_start = st
                continue

            prev_ev = current_cluster_segs[-1]
            prev_profile = str(prev_ev.get("delivery_profile", "NORMAL")).upper()
            curr_dur = en - cluster_start

            # Conditions to cut to a new scene:
            # - Profile dramatic shift (e.g. into REVEAL, INTRO -> MYSTERY, EMOTIONAL -> REFLECTION)
            # - Or duration reaches threshold
            is_critical_cut = (
                (profile == "REVEAL" and prev_profile != "REVEAL")
                or (prev_profile == "REVEAL" and profile != "REVEAL")
                or (profile in ("INTRO", "OUTRO") and prev_profile != profile)
            )

            should_split = is_critical_cut or (curr_dur >= target_scene_dur)

            if should_split and curr_dur >= 8.0:
                clusters.append({
                    "start_sec": cluster_start,
                    "end_sec": prev_ev.get("speech_end_sec", cluster_start + 10.0),
                    "segments": list(current_cluster_segs)
                })
                current_cluster_segs = [ev]
                cluster_start = st
            else:
                current_cluster_segs.append(ev)

        if current_cluster_segs:
            clusters.append({
                "start_sec": cluster_start,
                "end_sec": events[-1].get("speech_end_sec", total_audio_sec),
                "segments": list(current_cluster_segs)
            })

        # Enforce target_scenes_max by merging the shortest compatible adjacent clusters
        while len(clusters) > target_scenes_max:
            best_idx = 0
            min_comb_dur = float("inf")
            for i in range(len(clusters) - 1):
                d1 = clusters[i]["end_sec"] - clusters[i]["start_sec"]
                d2 = clusters[i + 1]["end_sec"] - clusters[i + 1]["start_sec"]
                comb = d1 + d2
                p1 = [s.get("delivery_profile", "") for s in clusters[i]["segments"]]
                p2 = [s.get("delivery_profile", "") for s in clusters[i + 1]["segments"]]
                penalty = 100.0 if ("REVEAL" in p1) != ("REVEAL" in p2) else 0.0
                if comb + penalty < min_comb_dur:
                    min_comb_dur = comb + penalty
                    best_idx = i

            merged_segs = clusters[best_idx]["segments"] + clusters[best_idx + 1]["segments"]
            clusters[best_idx] = {
                "start_sec": clusters[best_idx]["start_sec"],
                "end_sec": clusters[best_idx + 1]["end_sec"],
                "segments": merged_segs
            }
            clusters.pop(best_idx + 1)

        # Ensure complete coverage without gaps
        for i in range(len(clusters)):
            if i == 0:
                clusters[i]["start_sec"] = 0.0
            else:
                clusters[i]["start_sec"] = clusters[i - 1]["end_sec"]

            if i == len(clusters) - 1:
                clusters[i]["end_sec"] = total_audio_sec

        return clusters

    def _assign_visual_types_and_prompts(
        self,
        clusters: List[Dict[str, Any]],
        total_audio_sec: float,
        target_veo_min: int,
        target_veo_max: int
    ) -> List[VisualScene]:
        """Classify each scene and construct identity-anchored cinematic prompts."""
        scenes: List[VisualScene] = []
        veo_candidate_scores: List[tuple[int, float]] = []

        # Motion rotation patterns for Banana Images
        motion_palette = ["slow_push_in", "slow_pull_out", "pan_left", "pan_right", "subtle_drift"]

        for idx, cl in enumerate(clusters):
            st = round(cl["start_sec"], 2)
            en = round(cl["end_sec"], 2)
            dur = round(en - st, 2)
            segs = cl["segments"]
            seg_ids = [str(s.get("id")) for s in segs]
            combined_text = " ".join([s.get("text", "") for s in segs])

            # Dominant delivery profile
            profiles = [str(s.get("delivery_profile", "NORMAL")).upper() for s in segs]
            dominant_profile = max(set(profiles), key=profiles.count)

            # Heuristics for Veo action score:
            # Action keywords: chuyển tiền, nhìn, bước, mở, phát hiện, khóc, rung, đứng, quay lại, bàng hoàng
            action_keywords = [
                "bước", "mở", "nhìn", "thấy", "phát hiện", "khóc", "rung", "chuyển tiền",
                "điện thoại", "quay lại", "đứng", "nói", "nghĩ", "bàng hoàng", "chết", "mất",
                "bệnh viện", "lá thư", "gục", "đối diện"
            ]
            action_score = sum(1.5 for kw in action_keywords if kw in combined_text.lower())

            if dominant_profile in ("TENSION", "REVEAL", "EMOTIONAL"):
                action_score += 4.0
            elif dominant_profile == "MYSTERY":
                action_score += 2.0
            elif dominant_profile in ("INTRO", "OUTRO"):
                action_score += 1.0

            # Favor Veo every 2nd or 3rd scene to keep visual pacing alive
            if idx % 2 == 1:
                action_score += 1.5

            veo_candidate_scores.append((idx, action_score))

        # Select Top Veo candidates within [target_veo_min, target_veo_max]
        desired_veo_count = min(target_veo_max, max(target_veo_min, int(len(clusters) * 0.45)))
        veo_indices = set(
            idx for idx, _ in sorted(veo_candidate_scores, key=lambda x: x[1], reverse=True)[:desired_veo_count]
        )

        for idx, cl in enumerate(clusters):
            st = round(cl["start_sec"], 2)
            en = round(cl["end_sec"], 2)
            dur = round(en - st, 2)
            segs = cl["segments"]
            seg_ids = [str(s.get("id")) for s in segs]
            combined_text = " ".join([s.get("text", "") for s in segs])
            profiles = [str(s.get("delivery_profile", "NORMAL")).upper() for s in segs]
            dominant_profile = max(set(profiles), key=profiles.count)

            is_veo = (idx in veo_indices)
            visual_type = "VEO_I2V" if is_veo else "BANANA_IMAGE"

            # Detect character & location
            chars, loc = self._detect_context(combined_text, dominant_profile)

            # Build prompts
            img_prompt, vid_prompt = self._compose_prompts(
                chars=chars,
                location=loc,
                text=combined_text,
                profile=dominant_profile,
                is_veo=is_veo
            )

            motion = motion_palette[idx % len(motion_palette)]
            transition = "hard_cut" if dominant_profile in ("TENSION", "REVEAL") else "crossfade"

            scene = VisualScene(
                scene_id=f"SC_{idx + 1:03d}",
                scene_index=idx + 1,
                start_sec=st,
                end_sec=en,
                duration_sec=dur,
                visual_type=visual_type,
                characters=chars,
                location=loc,
                story_context=combined_text[:160] + "...",
                image_prompt=img_prompt,
                video_prompt=vid_prompt if is_veo else None,
                motion=motion,
                transition=transition,
                video_duration=8,
                status="PLANNED",
                segments_covered=seg_ids,
                delivery_profile=dominant_profile
            )
            scenes.append(scene)

        return scenes

    def _detect_context(self, text: str, profile: str) -> tuple[List[str], str]:
        """Detects characters and locations from text semantics."""
        txt_l = text.lower()
        chars: List[str] = []
        loc = "LAN_HOME"

        if "cậu" in txt_l or "bệnh" in txt_l or "viện" in txt_l:
            chars.append("UNCLE")
            loc = "HOSPITAL_GRAVE"

        if "hùng" in txt_l or "chồng" in txt_l:
            chars.append("HUNG")

        if "lan" in txt_l or "cô" in txt_l or "vợ" in txt_l or "người phụ nữ" in txt_l:
            if "năm xưa" in txt_l or "trẻ" in txt_l or "quá khứ" in txt_l or "hồi tưởng" in txt_l:
                chars.append("LAN_YOUNG")
            else:
                chars.append("LAN_ADULT")

        if "chuyển tiền" in txt_l or "5 triệu" in txt_l or "năm triệu" in txt_l or "tài khoản" in txt_l:
            loc = "BANK_PHONE"

        if "mộ" in txt_l or "ngày mất" in txt_l or "nghĩa trang" in txt_l:
            loc = "HOSPITAL_GRAVE"

        # Default fallback character
        if not chars:
            chars = ["LAN_ADULT"]

        return list(dict.fromkeys(chars)), loc

    def _compose_prompts(
        self,
        chars: List[str],
        location: str,
        text: str,
        profile: str,
        is_veo: bool
    ) -> tuple[str, Optional[str]]:
        """
        Constructs style-consistent prompt.
        Anchors character appearance to character library to prevent AI face drift.
        """
        preset_style = self.preset.get("style_prompt", "")

        # 1. Character descriptions
        char_descriptions = []
        for c_id in chars:
            c_profile = self.characters.get(c_id)
            if c_profile:
                char_descriptions.append(
                    f"{c_profile.name}: {c_profile.appearance}, wearing {c_profile.default_clothing}"
                )

        char_block = "; ".join(char_descriptions) if char_descriptions else "Vietnamese character"

        # 2. Location description
        loc_profile = self.locations.get(location)
        loc_desc = loc_profile.description if loc_profile else "modern Vietnamese domestic room"

        # 3. Emotion / lighting based on profile
        mood_lighting = "soft warm domestic lighting, quiet contemplative atmosphere"
        if profile in ("TENSION", "MYSTERY"):
            mood_lighting = "dramatic contrast shadows, moody cinematic atmosphere, shallow depth of field"
        elif profile == "REVEAL":
            mood_lighting = "stark cold light, emotionally piercing revelation ambiance, heightened reality"
        elif profile == "EMOTIONAL":
            mood_lighting = "tender melancholic rim lighting, deep emotional sorrow, authentic tearful expression"

        # 4. Image Prompt
        img_prompt = (
            f"Cinematic 35mm film still. {char_block}. "
            f"Location: {loc_desc}. "
            f"Scene context: {text[:120]}. "
            f"{mood_lighting}. {preset_style}, 16:9 ratio."
        )

        # 5. Video Prompt (for Veo Image-to-Video)
        vid_prompt = None
        if is_veo:
            vid_prompt = (
                f"Cinematic slow subject motion, subtle emotional breathing, realistic Vietnamese facial expressions, "
                f"restrained natural movement, gentle camera push in, cinematic documentary pacing, 24fps"
            )

        return img_prompt, vid_prompt

    def summarize_plan(self, scenes: List[VisualScene], total_sec: float) -> VisualPlanSummary:
        """Returns structured statistics for the visual plan."""
        total_sc = len(scenes)
        banana_cnt = sum(1 for s in scenes if s.visual_type == "BANANA_IMAGE")
        veo_cnt = sum(1 for s in scenes if s.visual_type == "VEO_I2V")
        total_veo_sec = veo_cnt * 8

        return VisualPlanSummary(
            total_scenes=total_sc,
            banana_images_count=banana_cnt,
            veo_clips_count=veo_cnt,
            total_veo_duration_sec=total_veo_sec,
            total_timeline_sec=total_sec,
            estimated_banana_cost="Google Flow Standard Tier (Included)",
            estimated_veo_cost="Google Flow Standard Tier (Included)"
        )

    def save_plan(self, scenes: List[VisualScene], project_dir: Path) -> Path:
        """Saves visual_plan.json into projects/<slug>/visual/visual_plan.json."""
        vis_dir = project_dir / "visual"
        vis_dir.mkdir(parents=True, exist_ok=True)
        plan_file = vis_dir / "visual_plan.json"

        data = {
            "scenes": [asdict(s) for s in scenes],
            "total_scenes": len(scenes),
            "banana_count": sum(1 for s in scenes if s.visual_type == "BANANA_IMAGE"),
            "veo_count": sum(1 for s in scenes if s.visual_type == "VEO_I2V"),
        }

        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Visual plan saved to: {plan_file} ({len(scenes)} scenes)")
        return plan_file
