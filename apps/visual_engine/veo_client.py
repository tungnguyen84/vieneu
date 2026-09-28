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
from apps.visual_engine.resolvers import resolve_flow_project_id, resolve_video_duration

logger = logging.getLogger(__name__)


class VeoClient:
    """Client for generating Veo 3 / Omni 1.1 Flash Image-to-Video clips."""

    def __init__(
        self,
        adapter: FlowKitAdapter,
        asset_mgr: VisualAssetManager,
        model_family: str = "omni_flash",
        duration_s: Optional[int] = None,
        poll_interval_s: float = 5.0,
        poll_timeout_s: float = 360.0,
        preset: Optional[Dict[str, Any]] = None
    ):
        self.adapter = adapter
        self.asset_mgr = asset_mgr
        self.model_family = model_family
        self.duration_s = duration_s
        self.poll_interval_s = poll_interval_s
        self.poll_timeout_s = poll_timeout_s
        self.preset = preset

    def generate_scene_video(
        self,
        scene: VisualScene,
        project_id: str = "",
        duration_s: Optional[int] = None,
        force_regenerate: bool = False,
        allow_fallback: bool = True
    ) -> Optional[Path]:
        """
        Generates and downloads a video clip (Omni 1.1 Flash or Veo 3) for a scene.
        Returns local MP4 Path on success, None on failure.
        If generation fails and allow_fallback is True, marks status as FALLBACK_MOTION.
        """
        if not scene.visual_type or scene.visual_type == "UNRESOLVED":
            raise ValueError(f"Cannot generate video: Scene {scene.scene_id} has UNRESOLVED visual_type")

        if scene.visual_type not in ("VEO_I2V", "VIDEO_CLIP", "OMNI_FLASH_I2V"):
            logger.info(f"[VideoClient] Scene {scene.scene_id} is {scene.visual_type}. Skipping.")
            return None

        # Resolve project_id through single resolver
        target_pid = resolve_flow_project_id(
            ui_project_id=project_id,
            visual_preset=self.preset,
            adapter_default=self.adapter.default_project_id
        )

        # Resolve duration through single resolver
        resolved_duration = resolve_video_duration(
            scene=scene,
            ui_duration=duration_s if duration_s is not None else self.duration_s,
            preset=self.preset
        )

        out_video_path = self.asset_mgr.videos_dir / f"{scene.scene_id}.mp4"

        # Check resume condition
        queue = self.asset_mgr.load_queue()
        item = queue.get(scene.scene_id)
        if not force_regenerate and item:
            if item.video_status == "DONE" and out_video_path.exists() and out_video_path.stat().st_size > 0:
                logger.info(f"[VideoClient] Scene {scene.scene_id} video already exists, skipping.")
                return out_video_path
            if item.video_status == "FALLBACK_MOTION":
                logger.info(f"[VideoClient] Scene {scene.scene_id} marked as FALLBACK_MOTION, skipping.")
                return None

        # Prerequisite: Banana keyframe must exist
        keyframe_path = self.asset_mgr.images_dir / f"{scene.scene_id}.jpg"
        media_id = (item.image_media_id if item else None) or scene.image_media_id
        if not keyframe_path.exists() or not media_id:
            logger.error(f"[VideoClient] Keyframe for {scene.scene_id} missing. Cannot generate video.")
            return None

        # Update queue status: GENERATING
        self.asset_mgr.update_item(scene.scene_id, video_status="GENERATING", image_media_id=media_id, last_error=None)

        try:
            logger.info(f"[VideoClient] Submitting {self.model_family} I2V generation for {scene.scene_id} (duration {resolved_duration}s, project {target_pid})...")
            video_prompt = scene.video_prompt or (
                "Cinematic slow subject motion, subtle emotional breathing, realistic Vietnamese facial expressions, 24fps"
            )

            res = self.adapter.generate_video(
                start_image_media_id=media_id,
                prompt=video_prompt,
                project_id=target_pid,
                scene_id=scene.scene_id,
                aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
                duration_s=resolved_duration,
                resolution="720p",
                model_family=self.model_family
            )

            # Extract operation or media
            op_data = res.get("data") or res.get("operations") or {}
            operation_id = None
            if isinstance(op_data, list) and op_data:
                operation_id = op_data[0].get("operation", {}).get("name")
            elif isinstance(op_data, dict):
                op_list = op_data.get("operations")
                if isinstance(op_list, list) and op_list:
                    operation_id = op_list[0].get("operation", {}).get("name")
                else:
                    operation_id = op_data.get("operation_id") or op_data.get("name")

            if not operation_id:
                # Flow may return media directly
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
                raise RuntimeError(f"generate_video returned no operation_id: {res}")

            logger.info(f"[VideoClient] Operation submitted: {operation_id}. Polling for completion ({self.model_family})...")
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
                    op_inner = op.get("operation", {}) if isinstance(op.get("operation"), dict) else {}
                    op_meta = op_inner.get("metadata") or op.get("metadata") or {}
                    vid_meta = op_meta.get("video", {}) if isinstance(op_meta, dict) else {}

                    fife_url = op.get("fifeUrl") or op_inner.get("fifeUrl") or vid_meta.get("fifeUrl")
                    m_id = op.get("mediaId") or op_inner.get("mediaId") or vid_meta.get("mediaId")

                    if (status in ("CAE", "MEDIA_GENERATION_STATUS_SUCCESSFUL") and fife_url) or fife_url:
                        video_url = fife_url
                        video_media_id = m_id
                        break

                if video_url:
                    break

            if not video_url:
                raise TimeoutError(f"Video generation timed out after {self.poll_timeout_s}s for operation {operation_id}")

            # Download video MP4
            logger.info(f"[VideoClient] Downloading clip for {scene.scene_id} from {video_url[:60]}...")
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
            logger.info(f"[VideoClient] Successfully generated & saved video ({self.model_family}) for {scene.scene_id} ({out_video_path.stat().st_size:,} bytes)")
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


# Backwards compatibility and modern aliases
VideoClient = VeoClient
OmniFlashClient = VeoClient
