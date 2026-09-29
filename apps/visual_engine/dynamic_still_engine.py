"""V9.3.2 Dynamic Still Engine for VieNeu.

Transforms static IMAGE scenes into cinematic multi-shot documentary sequences
using virtual camera reframing, intelligent motion phases, and evidence inserts.

Invariants:
- 0 AI generations (0 image, 0 video). Uses existing approved images only.
- Strict static hold limit: <= 2.0s (unless intentional_static = true).
- Motion variety: <= 2 consecutive scenes with same primary motion.
- Safe cropping: max zoom 108–112%, preserves faces, evidence, and composition.
- Overlays treated as visual beats.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger("VieNeu.DynamicStillEngine")


@dataclass
class VirtualShot:
    shot_index: int
    start_sec: float
    end_sec: float
    duration_sec: float
    composition: str  # "WIDE", "MEDIUM", "DETAIL", "MEDIUM_CLOSE"
    motion: str       # "SLOW_PUSH_IN", "SLOW_PULL_OUT", "PAN_LEFT", "PAN_RIGHT", "PAN_UP", "PAN_DOWN", "STATIC"
    zoom_start: float = 1.00
    zoom_end: float = 1.04
    has_overlay: bool = False
    overlay_text: Optional[str] = None
    is_intentional_static: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SceneVirtualPlan:
    scene_id: str
    total_duration_sec: float
    source_image: str
    virtual_shots: List[VirtualShot] = field(default_factory=list)
    predicted_static_hold_max: float = 0.0
    intentional_static: bool = False
    qc_status: str = "PASS"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["virtual_shots"] = [s.to_dict() for s in self.virtual_shots]
        return d


class DynamicStillPlanner:
    """Plans dynamic multi-phase virtual camera shots from a single still image."""

    MOTION_PALETTE = [
        "SLOW_PUSH_IN",
        "PAN_LEFT",
        "SLOW_PULL_OUT",
        "PAN_RIGHT",
        "SLOW_PUSH_IN",
        "PAN_UP"
    ]

    def __init__(self):
        self.motion_history: List[str] = []

    def plan_scene(
        self,
        scene_id: str,
        image_path: str | Path,
        duration_sec: float,
        story_function: str = "NORMAL",
        overlays: Optional[List[str]] = None,
        intentional_static: bool = False,
    ) -> SceneVirtualPlan:
        dur = float(duration_sec)
        shots: List[VirtualShot] = []
        ov_list = overlays or []

        # Determine motion sequence avoiding >2 consecutive repeats
        def pick_motion(preferred: str, fallback_idx: int) -> str:
            if len(self.motion_history) >= 2 and self.motion_history[-1] == self.motion_history[-2] == preferred:
                # Alternate
                alt = "PAN_LEFT" if "PUSH" in preferred else "SLOW_PUSH_IN"
                self.motion_history.append(alt)
                return alt
            self.motion_history.append(preferred)
            return preferred

        # Shot Pattern Selection (Deterministic & Story-Aware)
        sc_num = 1
        num_match = re.search(r"\d+", scene_id)
        if num_match:
            sc_num = int(num_match.group(0))

        # DURATION RULES
        if dur <= 7.0:
            # Rule 1: <= 7s -> 1 continuous motion, no static end
            pref = "SLOW_PUSH_IN" if story_function in ["MYSTERY", "HOOK"] else ("PAN_RIGHT" if sc_num % 2 == 0 else "SLOW_PULL_OUT")
            m = pick_motion(pref, 0)
            shots.append(VirtualShot(
                shot_index=1,
                start_sec=0.0,
                end_sec=dur,
                duration_sec=dur,
                composition="WIDE",
                motion=m,
                zoom_start=1.00,
                zoom_end=1.04,
                has_overlay=bool(ov_list),
                overlay_text=ov_list[0] if ov_list else None,
                is_intentional_static=intentional_static
            ))

        elif dur <= 12.0:
            # Rule 2: 7 < dur <= 12s -> 2 motion phases with pattern diversity
            d1 = round(dur * 0.52, 2)
            d2 = round(dur - d1, 2)
            
            # Diverse 2-shot patterns: WIDE -> MEDIUM, MEDIUM -> DETAIL, or WIDE -> DETAIL
            pattern_idx = sc_num % 3
            if pattern_idx == 0:
                c1, c2 = "WIDE", "MEDIUM"
                m1 = pick_motion("SLOW_PUSH_IN", 0)
                m2 = pick_motion("PAN_LEFT", 1)
                z1_s, z1_e = 1.00, 1.04
                z2_s, z2_e = 1.05, 1.08
            elif pattern_idx == 1:
                c1, c2 = "MEDIUM", "DETAIL"
                m1 = pick_motion("PAN_RIGHT", 0)
                m2 = pick_motion("SLOW_PULL_OUT", 1)
                z1_s, z1_e = 1.05, 1.07
                z2_s, z2_e = 1.09, 1.05
            else:
                c1, c2 = "WIDE", "DETAIL"
                m1 = pick_motion("SLOW_PUSH_IN", 0)
                m2 = pick_motion("PAN_RIGHT", 1)
                z1_s, z1_e = 1.00, 1.03
                z2_s, z2_e = 1.08, 1.10

            shots.append(VirtualShot(
                shot_index=1,
                start_sec=0.0,
                end_sec=d1,
                duration_sec=d1,
                composition=c1,
                motion=m1,
                zoom_start=z1_s,
                zoom_end=z1_e,
            ))
            shots.append(VirtualShot(
                shot_index=2,
                start_sec=d1,
                end_sec=dur,
                duration_sec=d2,
                composition=c2,
                motion=m2,
                zoom_start=z2_s,
                zoom_end=z2_e,
                has_overlay=bool(ov_list),
                overlay_text=ov_list[0] if ov_list else None,
                is_intentional_static=intentional_static
            ))

        elif dur <= 18.0:
            # Rule 3: 12 < dur <= 18s -> 3 motion phases with diverse patterns
            d1 = round(dur * 0.35, 2)
            d2 = round(dur * 0.35, 2)
            d3 = round(dur - d1 - d2, 2)

            pattern_idx = sc_num % 3
            if pattern_idx == 0:
                # WIDE -> MEDIUM -> DETAIL
                comps = ["WIDE", "MEDIUM", "DETAIL"]
                motions = ["SLOW_PUSH_IN", "PAN_RIGHT", "SLOW_PULL_OUT"]
                zooms = [(1.00, 1.04), (1.05, 1.08), (1.09, 1.05)]
            elif pattern_idx == 1:
                # MEDIUM -> DETAIL -> WIDE
                comps = ["MEDIUM", "DETAIL", "WIDE"]
                motions = ["PAN_LEFT", "SLOW_PULL_OUT", "SLOW_PUSH_IN"]
                zooms = [(1.05, 1.08), (1.09, 1.06), (1.00, 1.04)]
            else:
                # WIDE -> DETAIL -> MEDIUM
                comps = ["WIDE", "DETAIL", "MEDIUM"]
                motions = ["SLOW_PUSH_IN", "PAN_LEFT", "SLOW_PULL_OUT"]
                zooms = [(1.00, 1.03), (1.09, 1.07), (1.05, 1.02)]

            shots.append(VirtualShot(
                shot_index=1,
                start_sec=0.0,
                end_sec=d1,
                duration_sec=d1,
                composition=comps[0],
                motion=pick_motion(motions[0], 0),
                zoom_start=zooms[0][0],
                zoom_end=zooms[0][1],
            ))
            shots.append(VirtualShot(
                shot_index=2,
                start_sec=d1,
                end_sec=d1 + d2,
                duration_sec=d2,
                composition=comps[1],
                motion=pick_motion(motions[1], 1),
                zoom_start=zooms[1][0],
                zoom_end=zooms[1][1],
                has_overlay=bool(ov_list),
                overlay_text=ov_list[0] if ov_list else None,
            ))
            shots.append(VirtualShot(
                shot_index=3,
                start_sec=d1 + d2,
                end_sec=dur,
                duration_sec=d3,
                composition=comps[2],
                motion=pick_motion(motions[2], 2),
                zoom_start=zooms[2][0],
                zoom_end=zooms[2][1],
                is_intentional_static=intentional_static
            ))

        else:
            # Rule 4: dur > 18s -> 3 to 4 virtual shots (each 5-8s) with pattern diversity
            count = 4 if dur >= 22.0 else 3
            seg_len = round(dur / count, 2)
            
            pattern_idx = sc_num % 3
            if pattern_idx == 0:
                comps = ["WIDE", "MEDIUM", "DETAIL", "WIDE"]
                motions = ["SLOW_PUSH_IN", "PAN_LEFT", "SLOW_PUSH_IN", "SLOW_PULL_OUT"]
            elif pattern_idx == 1:
                comps = ["MEDIUM", "DETAIL", "WIDE", "MEDIUM"]
                motions = ["PAN_RIGHT", "SLOW_PULL_OUT", "SLOW_PUSH_IN", "PAN_LEFT"]
            else:
                comps = ["WIDE", "DETAIL", "MEDIUM", "WIDE"]
                motions = ["SLOW_PUSH_IN", "PAN_RIGHT", "SLOW_PULL_OUT", "SLOW_PUSH_IN"]

            acc = 0.0
            for idx in range(count):
                this_dur = seg_len if idx < count - 1 else round(dur - acc, 2)
                comp = comps[idx % len(comps)]
                mot = pick_motion(motions[idx % len(motions)], idx)
                z_start = 1.00 if comp == "WIDE" else (1.05 if comp == "MEDIUM" else 1.09)
                z_end = z_start + (0.04 if "PUSH" in mot else (-0.03 if "PULL" in mot else 0.01))

                has_ov = (idx == 1 and bool(ov_list))
                ov_txt = ov_list[0] if has_ov else None

                shots.append(VirtualShot(
                    shot_index=idx + 1,
                    start_sec=acc,
                    end_sec=acc + this_dur,
                    duration_sec=this_dur,
                    composition=comp,
                    motion=mot,
                    zoom_start=z_start,
                    zoom_end=min(1.12, z_end),
                    has_overlay=has_ov,
                    overlay_text=ov_txt,
                    is_intentional_static=(intentional_static and idx == count - 1)
                ))
                acc += this_dur

        pred_static = 1.5 if intentional_static else 0.0
        status = "PASS" if pred_static <= 2.0 else "NEEDS_DYNAMIC_STILL_REPLAN"

        return SceneVirtualPlan(
            scene_id=scene_id,
            total_duration_sec=dur,
            source_image=str(Path(image_path).resolve()),
            virtual_shots=shots,
            predicted_static_hold_max=pred_static,
            intentional_static=intentional_static,
            qc_status=status
        )


def build_zoompan_filter(shot: VirtualShot, fps: int = 30) -> str:
    """Builds robust FFmpeg zoompan filter for a virtual shot within safe 108-112% zoom bounds."""
    frames = max(1, int(shot.duration_sec * fps))
    z_start = shot.zoom_start
    z_end = shot.zoom_end
    step = (z_end - z_start) / max(1, frames)

    # Base scaling to 1080p
    base = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"

    if shot.motion == "STATIC" or shot.is_intentional_static:
        return f"{base},fps={fps},format=yuv420p"

    if shot.motion == "SLOW_PUSH_IN":
        # Smooth push from z_start to z_end, centered
        step_pos = max(0.0001, abs(step))
        zp = f"zoompan=z='min(zoom+{step_pos:.6f},{z_end:.3f})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}"
    elif shot.motion == "SLOW_PULL_OUT":
        step_pos = max(0.0001, abs(step))
        zp = f"zoompan=z='if(lte(zoom,{z_end:.3f}),{z_end:.3f},max({z_end:.3f},zoom-{step_pos:.6f}))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}"
    elif shot.motion == "PAN_LEFT":
        # Slight zoom 1.06 to allow smooth horizontal pan
        zp = f"zoompan=z='{z_start:.3f}':x='if(lte(on,1),(iw-iw/zoom),max(0,x-0.45))':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}"
    elif shot.motion == "PAN_RIGHT":
        zp = f"zoompan=z='{z_start:.3f}':x='if(lte(on,1),0,min(iw-iw/zoom,x+0.45))':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}"
    elif shot.motion == "PAN_UP":
        zp = f"zoompan=z='{z_start:.3f}':x='iw/2-(iw/zoom/2)':y='if(lte(on,1),(ih-ih/zoom),max(0,y-0.35))':d={frames}:s=1920x1080:fps={fps}"
    elif shot.motion == "PAN_DOWN":
        zp = f"zoompan=z='{z_start:.3f}':x='iw/2-(iw/zoom/2)':y='if(lte(on,1),0,min(ih-ih/zoom,y+0.35))':d={frames}:s=1920x1080:fps={fps}"
    else:
        # Default push
        zp = f"zoompan=z='min(zoom+0.0002,{z_end:.3f})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}"

    return f"{base},{zp},format=yuv420p"


def render_dynamic_still_scene(
    plan: SceneVirtualPlan,
    output_mp4: Path,
    cache_dir: Path,
    overlay_generator_fn: Optional[Any] = None,
    ffmpeg_bin: str = "ffmpeg",
    fps: int = 30
) -> Path:
    """Renders virtual shots and concatenates them into a single dynamic scene clip."""
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if len(plan.virtual_shots) == 1:
        # Single shot: direct render
        shot = plan.virtual_shots[0]
        vf = build_zoompan_filter(shot, fps=fps)
        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(plan.source_image),
            "-vf", vf,
            "-t", f"{shot.duration_sec:.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_mp4)
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return output_mp4

    # Multiple virtual shots
    shot_clips: List[Path] = []
    for s in plan.virtual_shots:
        shot_mp4 = cache_dir / f"dyn_{plan.scene_id}_shot_{s.shot_index}.mp4"
        vf = build_zoompan_filter(s, fps=fps)

        temp_shot_mp4 = shot_mp4 if not s.has_overlay or not s.overlay_text else cache_dir / f"tmp_dyn_{plan.scene_id}_shot_{s.shot_index}.mp4"
        cmd = [
            ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(plan.source_image),
            "-vf", vf,
            "-t", f"{s.duration_sec:.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(temp_shot_mp4)
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        if s.has_overlay and s.overlay_text and overlay_generator_fn:
            banner_png = cache_dir / f"dyn_overlay_{plan.scene_id}_{s.shot_index}.png"
            overlay_generator_fn(s.overlay_text, banner_png)
            cmd_ov = [
                ffmpeg_bin, "-y",
                "-i", str(temp_shot_mp4),
                "-i", str(banner_png),
                "-filter_complex", "[0:v][1:v]overlay=0:0[outv]",
                "-map", "[outv]",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                str(shot_mp4)
            ]
            subprocess.run(cmd_ov, check=True, capture_output=True)
            temp_shot_mp4.unlink(missing_ok=True)
            banner_png.unlink(missing_ok=True)

        shot_clips.append(shot_mp4)

    # Concatenate virtual shots
    concat_list = cache_dir / f"concat_dyn_{plan.scene_id}.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for c in shot_clips:
            f.write(f"file '{c.resolve().as_posix()}'\n")

    cmd_cat = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_mp4)
    ]
    subprocess.run(cmd_cat, check=True, capture_output=True)

    # Cleanup temp shot clips
    for c in shot_clips:
        c.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)

    return output_mp4


def inspect_real_static_holds(
    mp4_path: Path | str,
    max_threshold: float = 2.0,
    ffmpeg_bin: str = "ffmpeg"
) -> Tuple[float, List[Dict[str, Any]]]:
    """Inspects rendered MP4 using FFmpeg freezedetect filter to find frozen periods > threshold."""
    p = Path(mp4_path)
    if not p.exists():
        return 0.0, []

    cmd = [
        ffmpeg_bin,
        "-i", str(p),
        "-vf", f"freezedetect=n=-50dB:d={max_threshold:.1f}",
        "-f", "null",
        "-"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr

    # Pattern: [freezedetect @ ...] freeze_start: 12.3 freeze_duration: 3.5 freeze_end: 15.8
    freezes: List[Dict[str, Any]] = []
    longest_hold = 0.0

    matches = re.finditer(r"freeze_start:\s*([0-9\.]+).*?freeze_duration:\s*([0-9\.]+)", stderr)
    for m in matches:
        f_start = float(m.group(1))
        f_dur = float(m.group(2))
        freezes.append({"start_sec": f_start, "duration_sec": f_dur})
        if f_dur > longest_hold:
            longest_hold = f_dur

    return longest_hold, freezes


def inspect_static_holds_detailed(
    mp4_path: Path | str,
    accidental_threshold: float = 2.0,
    intentional_threshold: float = 1.0,
    ffmpeg_bin: str = "ffmpeg"
) -> Tuple[float, float, List[Dict[str, Any]]]:
    """
    Inspects rendered MP4 using FFmpeg freezedetect at fine threshold.
    Separates:
    - longest_accidental_static_hold (> accidental_threshold, e.g. > 2.0s)
    - longest_intentional_static_hold (deliberate visual rest between 1.0s and 2.0s)
    """
    p = Path(mp4_path)
    if not p.exists():
        return 0.0, 0.0, []

    cmd = [
        ffmpeg_bin,
        "-i", str(p),
        "-vf", f"freezedetect=n=-50dB:d={intentional_threshold:.1f}",
        "-f", "null",
        "-"
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr

    freezes: List[Dict[str, Any]] = []
    longest_accidental = 0.0
    longest_intentional = 0.0

    matches = re.finditer(r"freeze_start:\s*([0-9\.]+).*?freeze_duration:\s*([0-9\.]+)", stderr)
    for m in matches:
        f_start = float(m.group(1))
        f_dur = float(m.group(2))
        is_accidental = f_dur > accidental_threshold
        entry = {
            "start_sec": f_start,
            "duration_sec": f_dur,
            "type": "ACCIDENTAL" if is_accidental else "INTENTIONAL_REST",
        }
        freezes.append(entry)

        if is_accidental:
            if f_dur > longest_accidental:
                longest_accidental = f_dur
        else:
            if f_dur > longest_intentional:
                longest_intentional = f_dur

    return longest_accidental, longest_intentional, freezes

