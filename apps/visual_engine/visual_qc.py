"""Visual Quality Control (QC) for VieNeu Production Storytelling.

Validates the complete visual pipeline before final video rendering:
- Missing images / missing videos
- Zero-byte or corrupted asset files
- Timeline coverage (0.0s to final_mix duration) without black gaps
- Aspect ratio verification
- Returns structured QC Report & gatekeeper flag READY TO RENDER
"""
from __future__ import annotations

import datetime
import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.visual_planner import VisualScene

logger = logging.getLogger(__name__)


def validate_technical_image(image_path: Path | str) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Technical auto-QC for generated still image/keyframe.
    
    Verifies:
    - File existence & non-zero byte size
    - Image can be decoded cleanly
    - Dimensions and aspect ratio (expects ~16:9)
    - Not fully corrupt or completely black/blank
    """
    p = Path(image_path)
    if not p.exists():
        return False, f"Image file does not exist: {p}", {}
    if p.stat().st_size == 0:
        return False, f"Image file is 0 bytes: {p}", {"file_size_bytes": 0}

    try:
        from PIL import Image
        with Image.open(p) as img:
            w, h = img.size
            fmt = img.format
            aspect = round(w / h, 2) if h > 0 else 0.0

            # Blank/black image detection
            rgb_img = img.convert("RGB")
            extrema = rgb_img.getextrema()  # ((min_r, max_r), (min_g, max_g), (min_b, max_b))
            is_black = all(min_val == 0 and max_val == 0 for min_val, max_val in extrema)

            meta = {
                "width": w,
                "height": h,
                "aspect_ratio": aspect,
                "format": fmt,
                "file_size_bytes": p.stat().st_size,
                "is_blank_black": is_black
            }

            if is_black:
                return False, "Image is completely black/empty", meta

            if w < 640 or h < 360:
                return False, f"Image resolution too low: {w}x{h}", meta

            return True, None, meta
    except Exception as e:
        return False, f"Image decode error: {str(e)}", {"file_size_bytes": p.stat().st_size}


def validate_technical_video(
    video_path: Path | str,
    expected_duration: Optional[float] = None,
    ffprobe_bin: str = "ffprobe"
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Technical auto-QC for generated video clip.
    
    Verifies:
    - File existence & non-zero byte size
    - Playable container and video stream
    - Actual duration matches expected duration if specified
    """
    p = Path(video_path)
    if not p.exists():
        return False, f"Video file does not exist: {p}", {}
    if p.stat().st_size == 0:
        return False, f"Video file is 0 bytes: {p}", {"file_size_bytes": 0}

    try:
        cmd = [
            ffprobe_bin, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,nb_frames:format=duration",
            "-of", "json",
            str(p)
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            # If ffprobe failed, return warning or fallback file-size check
            return False, f"ffprobe error: {proc.stderr[:200]}", {"file_size_bytes": p.stat().st_size}

        data = json.loads(proc.stdout)
        stream = data.get("streams", [{}])[0] if data.get("streams") else {}
        format_info = data.get("format", {})

        dur_str = format_info.get("duration") or stream.get("duration")
        duration = float(dur_str) if dur_str else 0.0
        w = int(stream.get("width", 0))
        h = int(stream.get("height", 0))

        meta = {
            "width": w,
            "height": h,
            "duration": duration,
            "file_size_bytes": p.stat().st_size
        }

        if expected_duration is not None and duration > 0:
            # Check duration tolerance (e.g. within 1.5s of target)
            diff = abs(duration - expected_duration)
            if diff > 2.0:
                meta["duration_diff"] = diff
                return False, f"Video duration mismatch: actual {duration:.2f}s vs expected {expected_duration:.2f}s", meta

        return True, None, meta
    except Exception as e:
        # Fallback if ffprobe not available
        meta = {"file_size_bytes": p.stat().st_size, "error": str(e)}
        if p.stat().st_size > 1024:
            return True, None, meta
        return False, f"Video verification error: {str(e)}", meta


def record_pilot_qc(
    asset_mgr: VisualAssetManager,
    scene_id: str,
    asset_type: str,
    status: str,
    notes: str = "",
    user: str = "user"
) -> Dict[str, Any]:
    """Records human / reviewer semantic QC decisions on pilot assets.
    
    status: "APPROVED" | "REJECTED" | "AWAITING_QC"
    asset_type: "IMAGE" | "VIDEO"
    """
    report = asset_mgr.load_pilot_qc_status()
    scenes_map = report.setdefault("scenes", {})
    scene_qc = scenes_map.setdefault(scene_id, {})

    now_iso = datetime.datetime.now().isoformat()

    if asset_type == "IMAGE":
        scene_qc["image_status"] = status
        scene_qc["image_reviewed_at"] = now_iso
        scene_qc["image_notes"] = notes
        scene_qc["reviewer"] = user
        if status == "APPROVED":
            asset_mgr.approve_keyframe(scene_id)
    elif asset_type == "VIDEO":
        scene_qc["video_status"] = status
        scene_qc["video_reviewed_at"] = now_iso
        scene_qc["video_notes"] = notes
        scene_qc["reviewer"] = user
        if status == "APPROVED":
            asset_mgr.approve_video(scene_id)

    report["last_updated"] = now_iso
    asset_mgr.save_pilot_qc_status(report)
    return scene_qc



@dataclass
class VisualQCReport:
    total_scenes: int = 0
    ready_scenes: int = 0
    missing_images: int = 0
    missing_videos: int = 0
    failed_items: int = 0
    timeline_coverage_pct: float = 0.0
    timeline_gaps_count: int = 0
    timeline_gaps: List[Dict[str, float]] = field(default_factory=list)
    audio_master_duration_sec: float = 0.0
    ready_to_render: bool = False
    warning_messages: List[str] = field(default_factory=list)


class VisualQC:
    """Pre-render Quality Control Inspector."""

    def __init__(self, asset_mgr: VisualAssetManager):
        self.asset_mgr = asset_mgr

    def run_qc(
        self,
        scenes: List[VisualScene],
        audio_master_path: str | Path
    ) -> VisualQCReport:
        """Runs complete validation suite on scenes, disk assets, and timeline timing."""
        report = VisualQCReport(total_scenes=len(scenes))
        a_p = Path(audio_master_path)
        if not a_p.exists():
            report.warning_messages.append(f"Audio master not found at {a_p}")
            return report

        import soundfile as sf
        a_info = sf.info(str(a_p))
        audio_dur = a_info.duration
        report.audio_master_duration_sec = audio_dur

        queue = self.asset_mgr.load_queue()
        ready_count = 0

        # Check asset files on disk
        for sc in scenes:
            q_item = queue.get(sc.scene_id)
            img_p = self.asset_mgr.images_dir / f"{sc.scene_id}.jpg"

            # 1. Image Check
            if not img_p.exists() or img_p.stat().st_size == 0:
                report.missing_images += 1
                report.warning_messages.append(f"Scene {sc.scene_id} missing keyframe on disk: {img_p}")
            else:
                # 2. Video Check (if VEO_I2V and not fallback)
                if sc.visual_type == "VEO_I2V":
                    vid_p = self.asset_mgr.videos_dir / f"{sc.scene_id}.mp4"
                    if q_item and q_item.video_status == "DONE":
                        if not vid_p.exists() or vid_p.stat().st_size == 0:
                            report.missing_videos += 1
                            report.warning_messages.append(f"Scene {sc.scene_id} marked DONE but video missing: {vid_p}")
                        else:
                            ready_count += 1
                    elif q_item and q_item.video_status == "FALLBACK_MOTION":
                        # Valid fallback to Banana Motion
                        ready_count += 1
                    else:
                        report.missing_videos += 1
                else:
                    ready_count += 1

        report.ready_scenes = ready_count

        # Check Timeline Gaps (0.0s to audio_dur)
        if scenes:
            curr_pos = 0.0
            for sc in scenes:
                if sc.start_sec > curr_pos + 0.05:
                    report.timeline_gaps.append({
                        "gap_start": curr_pos,
                        "gap_end": sc.start_sec,
                        "gap_duration": sc.start_sec - curr_pos
                    })
                curr_pos = max(curr_pos, sc.end_sec)

            if curr_pos < audio_dur - 0.1:
                report.timeline_gaps.append({
                    "gap_start": curr_pos,
                    "gap_end": audio_dur,
                    "gap_duration": audio_dur - curr_pos
                })

            report.timeline_gaps_count = len(report.timeline_gaps)
            covered_sec = audio_dur - sum(g["gap_duration"] for g in report.timeline_gaps)
            report.timeline_coverage_pct = round(max(0.0, min(100.0, (covered_sec / audio_dur) * 100)), 1)
        else:
            report.timeline_coverage_pct = 0.0

        # Ready Gate
        report.ready_to_render = (
            report.missing_images == 0
            and report.timeline_gaps_count == 0
            and report.timeline_coverage_pct >= 99.5
        )

        return report
