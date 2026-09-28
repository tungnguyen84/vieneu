"""Final Video Renderer for VieNeu Production Storytelling.

Orchestrates FFmpeg to compose a broadcast-ready 1080p MP4 episode:
- Converts Banana Pro images to animated clips (slow push in, pull out, pan)
- Fits Veo 3 video clips to scene duration
- Concatenates visual timeline with zero black frames
- Multiplexes VieNeu Audio Formula V1 final_mix.wav as the sole authoritative audio track
- Output: 1920x1080, 16:9, 30fps, H.264, AAC 320kbps
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.visual_planner import VisualScene

logger = logging.getLogger(__name__)


class FinalVideoRenderer:
    """Renders composite MP4 episodes from images, clips, and master audio."""

    def __init__(self, asset_mgr: VisualAssetManager, ffmpeg_bin: str = "ffmpeg"):
        self.asset_mgr = asset_mgr
        self.ffmpeg = ffmpeg_bin
        self.final_dir = self.asset_mgr.project_dir / "final"
        self.final_dir.mkdir(parents=True, exist_ok=True)

    def render_banana_motion_clip(
        self,
        image_path: Path,
        duration_sec: float,
        motion: str = "slow_push_in",
        output_clip_path: Optional[Path] = None,
        fps: int = 30
    ) -> Path:
        """Converts a still 16:9 image into a smooth camera-motion MP4 clip."""
        if output_clip_path is None:
            output_clip_path = self.asset_mgr.processed_dir / f"{image_path.stem}.mp4"

        frames = max(1, int(duration_sec * fps))

        # Camera motion expressions
        if motion == "slow_pull_out":
            zoom_expr = "z='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0006))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif motion == "pan_left":
            zoom_expr = f"z='1.12':x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)'"
        elif motion == "pan_right":
            zoom_expr = f"z='1.12':x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'"
        else:  # default slow_push_in
            zoom_expr = "z='min(zoom+0.0006,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        vf = (
            f"scale=1920:1080:force_original_aspect_ratio=increase,"
            f"crop=1920:1080,"
            f"zoompan={zoom_expr}:d={frames}:s=1920x1080:fps={fps},"
            f"format=yuv420p"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            "-t", f"{duration_sec:.3f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_clip_path)
        ]

        logger.info(f"[VideoRenderer] Rendering motion clip ({motion}, {duration_sec:.2f}s): {output_clip_path.name}")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            logger.error(f"[VideoRenderer] FFmpeg motion render failed: {proc.stderr}")
            raise RuntimeError(f"FFmpeg motion clip failed: {proc.stderr[:300]}")

        return output_clip_path

    def fit_veo_clip(
        self,
        video_path: Path,
        target_duration_sec: float,
        output_clip_path: Optional[Path] = None,
        fps: int = 30
    ) -> Path:
        """Fits an 8s Veo video clip into the target scene duration by holding last frame or looping."""
        if output_clip_path is None:
            output_clip_path = self.asset_mgr.processed_dir / f"{video_path.stem}.mp4"

        # If target duration <= 8s, trim it
        if target_duration_sec <= 8.0:
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(video_path),
                "-t", f"{target_duration_sec:.3f}",
                "-vf", f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-an",
                str(output_clip_path)
            ]
        else:
            # Hold last frame
            extra_hold = target_duration_sec - 8.0
            cmd = [
                self.ffmpeg, "-y",
                "-i", str(video_path),
                "-vf", f"tpad=stop_mode=clone:stop_duration={extra_hold:.3f},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={fps},format=yuv420p",
                "-t", f"{target_duration_sec:.3f}",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "18",
                "-an",
                str(output_clip_path)
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg fit video clip failed: {proc.stderr[:300]}")

        return output_clip_path

    def render_scene_clip(self, scene: VisualScene) -> Path:
        """Renders processed clip for a single scene (Banana motion or Veo video)."""
        queue = self.asset_mgr.load_queue()
        q_item = queue.get(scene.scene_id)
        out_clip_p = self.asset_mgr.processed_dir / f"{scene.scene_id}.mp4"

        # Check if Veo video is available and ready
        vid_p = self.asset_mgr.videos_dir / f"{scene.scene_id}.mp4"
        if q_item and q_item.video_status == "DONE" and vid_p.exists() and vid_p.stat().st_size > 0:
            return self.fit_veo_clip(vid_p, scene.duration_sec, out_clip_p)

        # Fallback or BANANA_IMAGE
        img_p = self.asset_mgr.images_dir / f"{scene.scene_id}.jpg"
        if not img_p.exists() or img_p.stat().st_size == 0:
            # Fallback: search for previous scene image to prevent black screen (Section 27)
            logger.warning(f"[VideoRenderer] Scene {scene.scene_id} missing image, searching fallback...")
            available_images = sorted(list(self.asset_mgr.images_dir.glob("*.jpg")))
            if available_images:
                img_p = available_images[0]
            else:
                raise FileNotFoundError(f"Zero visual assets available for scene {scene.scene_id}!")

        return self.render_banana_motion_clip(
            image_path=img_p,
            duration_sec=scene.duration_sec,
            motion=scene.motion,
            output_clip_path=out_clip_p
        )

    def render_final_episode(
        self,
        scenes: List[VisualScene],
        audio_master_path: str | Path,
        output_mp4_path: Optional[str | Path] = None,
        max_scenes: Optional[int] = None
    ) -> Path:
        """
        Renders complete episode video:
        1. Renders processed clips for each scene
        2. Concatenates all visual clips
        3. Muxes with audio master final_mix.wav (discarding generated Veo audio)
        4. Outputs final_episode.mp4
        """
        if output_mp4_path is None:
            output_mp4 = self.final_dir / "final_episode.mp4"
        else:
            output_mp4 = Path(output_mp4_path)

        target_scenes = scenes[:max_scenes] if max_scenes else scenes
        clip_paths: List[Path] = []

        logger.info(f"[VideoRenderer] Rendering {len(target_scenes)} scene visual clips...")
        for sc in target_scenes:
            clip = self.render_scene_clip(sc)
            clip_paths.append(clip)

        # Build concat list file
        concat_txt = self.asset_mgr.processed_dir / "concat_list.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c in clip_paths:
                f.write(f"file '{c.resolve().as_posix()}'\n")

        # Concat video
        temp_visual_mp4 = self.asset_mgr.processed_dir / "visual_master_no_audio.mp4"
        cmd_concat = [
            self.ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(temp_visual_mp4)
        ]
        proc_cat = subprocess.run(cmd_concat, capture_output=True, text=True)
        if proc_cat.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {proc_cat.stderr[:300]}")

        # Multiplex with VieNeu final_mix.wav (Section 26: discard Veo audio, VieNeu is source of truth)
        logger.info(f"[VideoRenderer] Muxing final visual master with audio {audio_master_path}...")
        cmd_mux = [
            self.ffmpeg, "-y",
            "-i", str(temp_visual_mp4),
            "-i", str(audio_master_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "320k",
            "-shortest",
            str(output_mp4)
        ]
        proc_mux = subprocess.run(cmd_mux, capture_output=True, text=True)
        if proc_mux.returncode != 0:
            raise RuntimeError(f"FFmpeg audio mux failed: {proc_mux.stderr[:300]}")

        logger.info(f"[VideoRenderer] Successfully rendered final episode: {output_mp4} ({output_mp4.stat().st_size:,} bytes)")
        return output_mp4
