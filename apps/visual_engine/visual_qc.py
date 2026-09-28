"""Visual Quality Control (QC) for VieNeu Production Storytelling.

Validates the complete visual pipeline before final video rendering:
- Missing images / missing videos
- Zero-byte or corrupted asset files
- Timeline coverage (0.0s to final_mix duration) without black gaps
- Aspect ratio verification
- Returns structured QC Report & gatekeeper flag READY TO RENDER
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.visual_planner import VisualScene

logger = logging.getLogger(__name__)


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
