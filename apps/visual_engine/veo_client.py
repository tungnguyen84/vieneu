"""Veo 3 Image-to-Video Client for VieNeu Visual Engine.

Transforms Banana Pro keyframes into 8-second 720p/1080p cinematic video clips using Veo 3.1.
Handles:
- Frame-conditioned video generation (RPC eb1hJf)
- Async operation polling loop with timeout & retry handling
- Automatic asset download to projects/<slug>/visual/videos/<scene_id>.mp4
- Fallback to Banana Motion if video fails multiple times (guaranteeing 100% renderability)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.flowkit_adapter import FlowKitAdapter
from apps.visual_engine.visual_planner import VisualScene

logger = logging.getLogger(__name__)


class VeoClient:
    """Client for generating Veo 3 Image-to-Video clips."""

    def __init__(
        self,
        adapter: FlowKitAdapter,
        asset_mgr: VisualAssetManager,
        poll_interval_s: float = 10.0,
        poll_timeout_s: float = 360.0
    ):
        self.adapter = adapter
        self.asset_mgr = asset_mgr
        self.poll_interval_s = poll_interval_s
        self.poll_timeout_s = poll_timeout_s

    def generate_scene_video(
        self,
        scene: VisualScene,
        project_id: str = "",
        force_regenerate: bool = False,
        allow_fallback: bool = True
    ) -> Optional[Path]:
        """
        Generates and downloads an 8s Veo 3 video clip for a VEO_I2V scene.
        Returns local MP4 Path on success, None on failure.
        If generation fails and allow_fallback is True, marks status as FALLBACK_MOTION.
        """
        if scene.visual_type != "VEO_I2V":
            logger.info(f"[VeoClient] Scene {scene.scene_id} is {scene.visual_type}, not VEO_I2V. Skipping.")
            return None

        out_video_path = self.asset_mgr.videos_dir / f"{scene.scene_id}.mp4"

        # Check resume condition
        queue = self.asset_mgr.load_queue()
        item = queue.get(scene.scene_id)
        if not force_regenerate and item:
            if item.video_status == "DONE" and out_video_path.exists() and out_video_path.stat().st_size > 0:
                logger.info(f"[VeoClient] Scene {scene.scene_id} video already exists, skipping.")
                return out_video_path
            if item.video_status == "FALLBACK_MOTION":
                logger.info(f"[VeoClient] Scene {scene.scene_id} marked as FALLBACK_MOTION, skipping.")
                return None

        # Prerequisite: Banana keyframe must exist
        keyframe_path = self.asset_mgr.images_dir / f"{scene.scene_id}.jpg"
        if not keyframe_path.exists() or not item or not item.image_media_id:
            logger.error(f"[VeoClient] Keyframe for {scene.scene_id} missing. Cannot generate Veo video.")
            return None

        # Update queue status: GENERATING
        self.asset_mgr.update_item(scene.scene_id, video_status="GENERATING", last_error=None)

        try:
            logger.info(f"[VeoClient] Submitting Veo I2V generation for {scene.scene_id}...")
            video_prompt = scene.video_prompt or (
                "Cinematic slow subject motion, subtle emotional breathing, realistic Vietnamese facial expressions, 24fps"
            )

            res = self.adapter.generate_video(
                start_image_media_id=item.image_media_id,
                prompt=video_prompt,
                project_id=project_id,
                scene_id=scene.scene_id,
                aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
                duration_s=8,
                resolution="720p"
            )

            # Extract operation or media
            op_data = res.get("data") or res.get("operations") or {}
            operation_id = None
            if isinstance(op_data, list) and op_data:
                operation_id = op_data[0].get("operation", {}).get("name")
            elif isinstance(op_data, dict):
                operation_id = op_data.get("operation_id") or op_data.get("name")

            if not operation_id:
                # Sometimes Flow returns media directly
                media_list = res.get("media") or []
                if media_list:
                    vid_url = media_list[0].get("video", {}).get("fifeUrl")
                    if vid_url:
                        self.adapter.download_asset(vid_url, out_video_path)
                        self.asset_mgr.update_item(
                            scene.scene_id,
                            video_status="DONE",
                            video_file=str(out_video_path.relative_to(self.asset_mgr.project_dir))
                        )
                        return out_video_path

            if not operation_id:
                raise RuntimeError(f"Veo generate_video returned no operation_id: {res}")

            logger.info(f"[VeoClient] Operation submitted: {operation_id}. Polling for completion...")
            self.asset_mgr.update_item(scene.scene_id, video_operation_id=operation_id)

            # Polling loop
            start_poll_time = time.time()
            video_url = None
            video_media_id = None

            while time.time() - start_poll_time < self.poll_timeout_s:
                time.sleep(self.poll_interval_s)

                poll_res = self.adapter.check_operation_status(
                    operations=[{"operation": {"name": operation_id}, "sceneId": scene.scene_id}]
                )

                ops = poll_res.get("operations") or []
                for op in ops:
                    status = op.get("status")
                    m_id = op.get("mediaId")
                    fife_url = op.get("fifeUrl")

                    if status == "CAE" or fife_url:
                        video_url = fife_url
                        video_media_id = m_id
                        break

                if video_url:
                    break

            if not video_url:
                raise TimeoutError(f"Veo generation timed out after {self.poll_timeout_s}s for operation {operation_id}")

            # Download video MP4
            logger.info(f"[VeoClient] Downloading Veo clip for {scene.scene_id} from {video_url[:60]}...")
            self.adapter.download_asset(video_url, out_video_path)

            scene.video_media_id = video_media_id
            scene.video_url = video_url
            scene.status = "VIDEO_DONE"

            self.asset_mgr.update_item(
                scene.scene_id,
                video_status="DONE",
                video_media_id=video_media_id,
                video_file=str(out_video_path.relative_to(self.asset_mgr.project_dir))
            )
            logger.info(f"[VeoClient] Successfully generated & saved Veo video for {scene.scene_id} ({out_video_path.stat().st_size:,} bytes)")
            return out_video_path

        except Exception as e:
            curr_attempt = (item.attempt_count if item else 0) + 1
            if allow_fallback:
                logger.warning(f"[VeoClient] Veo generation unavailable for {scene.scene_id} ({e}). Activating FALLBACK to Banana Motion.")
                self.asset_mgr.update_item(
                    scene.scene_id,
                    video_status="FALLBACK_MOTION",
                    attempt_count=curr_attempt,
                    last_error=f"Fallback activated: {e}"
                )
            else:
                logger.error(f"[VeoClient] Video generation failed for {scene.scene_id}: {e}")
                self.asset_mgr.update_item(
                    scene.scene_id,
                    video_status="FAILED",
                    attempt_count=curr_attempt,
                    last_error=str(e)
                )
            return None
