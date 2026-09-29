"""Banana Pro Client for VieNeu Visual Engine.

Generates style-anchored keyframes via Google Flow Nano Banana Pro (GEM_PIX_2).
Handles:
- Reference image upload & UUID resolution for characters/locations
- Scene keyframe generation (16:9 Landscape)
- Asset download to projects/<slug>/visual/images/
- Queue status updates (DONE, FAILED) with automatic resume & retry
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.visual_engine.asset_manager import VisualAssetManager, QueueItem
from apps.visual_engine.character_manager import CharacterProfile, save_character
from apps.visual_engine.flowkit_adapter import FlowKitAdapter, GeneratedMediaAsset
from apps.visual_engine.visual_planner import VisualScene
from apps.visual_engine.resolvers import resolve_flow_project_id

logger = logging.getLogger(__name__)


class BananaClient:
    """Client for generating scene keyframes using Nano Banana Pro."""

    def __init__(
        self,
        adapter: FlowKitAdapter,
        asset_mgr: VisualAssetManager,
        character_lib: Dict[str, CharacterProfile],
        preset: Optional[Dict[str, Any]] = None
    ):
        self.adapter = adapter
        self.asset_mgr = asset_mgr
        self.character_lib = character_lib
        self.preset = preset

    def generate_character_reference(self, char_id: str, project_id: str = "") -> Path:
        """Generates a clean identity reference portrait for a character via Banana Pro (Section 4)."""
        char = self.character_lib.get(char_id)
        if not char:
            raise ValueError(f"Character '{char_id}' not found in character library.")

        target_pid = resolve_flow_project_id(
            ui_project_id=project_id,
            visual_preset=self.preset,
            adapter_default=self.adapter.default_project_id
        )

        from apps.visual_engine.character_manager import CHARACTER_LIB_DIR
        char_dir = CHARACTER_LIB_DIR / char_id
        char_dir.mkdir(parents=True, exist_ok=True)
        out_ref_path = char_dir / "ref_portrait.png"

        # Anchor to LAN_ADULT if younger version (Section 5)
        ref_anchor_ids = []
        if char.identity_relation and char.identity_relation.get("type") == "YOUNGER_VERSION_OF":
            anchor_cid = char.identity_relation.get("character_id")
            if anchor_cid:
                ref_anchor_ids.extend(self.ensure_character_references(anchor_cid, project_id=target_pid))

        prompt = (
            f"Clean character identity reference sheet of {char.name}, {char.appearance}. "
            f"Neutral solid studio background, waist-up portrait, natural front-facing pose, "
            f"neutral calm facial expression, soft even cinematic lighting, accurate realistic Vietnamese skin texture and features, "
            f"no dramatic camera angle, no text, no props obscuring face, 35mm portrait photography."
        )

        logger.info(f"[BananaClient] Generating clean character reference for {char_id} on Flow project {target_pid}...")
        assets = self.adapter.generate_image(
            prompt=prompt,
            project_id=target_pid,
            aspect_ratio="IMAGE_ASPECT_RATIO_PORTRAIT",
            image_model="NANO_BANANA_PRO",
            reference_media_ids=ref_anchor_ids or None,
            count=1
        )
        if not assets:
            raise RuntimeError(f"Failed to generate character reference for {char_id}")

        asset = assets[0]
        self.adapter.download_asset(asset.url, out_ref_path)

        if "ref_portrait.png" not in char.references:
            char.references.append("ref_portrait.png")
        char.flow_media_ids[target_pid] = asset.media_id
        save_character(char)

        # Mark all scenes using this character as STALE_REFERENCE (Section 26)
        self.asset_mgr.mark_character_updated(char_id, asset.media_id)

        # Append generation log (Section 28)
        self.asset_mgr.append_generation_log({
            "scene_id": f"REF_{char_id}",
            "operation": "CHARACTER_REFERENCE",
            "project_id": target_pid,
            "model": "NANO_BANANA_PRO",
            "status": "DONE",
            "media_id": asset.media_id
        })

        return out_ref_path

    def ensure_character_references(self, char_id: str, project_id: str = "") -> List[str]:
        """
        Uploads local reference images for a character to Google Flow if not already uploaded.
        Returns list of Google Flow media_id UUIDs.
        """
        target_pid = resolve_flow_project_id(
            ui_project_id=project_id,
            visual_preset=self.preset,
            adapter_default=self.adapter.default_project_id
        )
        char = self.character_lib.get(char_id)
        if not char or not char.references:
            return []

        flow_ids = []
        updated = False
        from apps.visual_engine.character_manager import CHARACTER_LIB_DIR
        char_dir = CHARACTER_LIB_DIR / char_id

        for ref_filename in char.references:
            # Check cached flow_media_id
            if ref_filename in char.flow_media_ids and char.flow_media_ids[ref_filename]:
                flow_ids.append(char.flow_media_ids[ref_filename])
                continue

            # Upload to Flow
            ref_path = char_dir / ref_filename
            if ref_path.exists():
                try:
                    logger.info(f"[BananaClient] Uploading reference {ref_filename} for character {char_id} to Flow project {target_pid}...")
                    media_id = self.adapter.upload_image_file(ref_path, project_id=target_pid)
                    char.flow_media_ids[ref_filename] = media_id
                    flow_ids.append(media_id)
                    updated = True
                    logger.info(f"[BananaClient] Uploaded {ref_filename} -> Flow media_id: {media_id}")
                except Exception as e:
                    logger.error(f"[BananaClient] Failed uploading reference {ref_path}: {e}")

        if updated:
            save_character(char)

        return flow_ids

    def generate_scene_keyframe(
        self,
        scene: VisualScene,
        project_id: str = "",
        force_regenerate: bool = False
    ) -> Optional[Path]:
        """
        Generates and downloads a keyframe for a single scene.
        Returns local image Path on success, None on failure.
        """
        if not scene.visual_type or scene.visual_type == "UNRESOLVED":
            raise ValueError(f"Cannot generate keyframe: Scene {scene.scene_id} has UNRESOLVED visual_type")

        target_pid = resolve_flow_project_id(
            ui_project_id=project_id,
            visual_preset=self.preset,
            adapter_default=self.adapter.default_project_id
        )

        out_image_path = self.asset_mgr.images_dir / f"{scene.scene_id}.jpg"

        # Check resume condition
        queue = self.asset_mgr.load_queue()
        item = queue.get(scene.scene_id)
        if not force_regenerate and item and item.image_status == "DONE" and out_image_path.exists() and out_image_path.stat().st_size > 0:
            logger.info(f"[BananaClient] Scene {scene.scene_id} keyframe already exists, skipping.")
            return out_image_path

        # Update queue status: GENERATING
        self.asset_mgr.update_item(scene.scene_id, image_status="GENERATING", last_error=None)

        try:
            # Resolve character references (only for visible characters, never all story characters)
            ref_media_ids: List[str] = []
            chars_to_reference = getattr(scene, "visible_characters", None) or scene.characters
            for c_id in chars_to_reference:
                char = self.character_lib.get(c_id)
                if not char or not char.references:
                    raise ValueError(f"Cannot generate keyframe: Visible character '{c_id}' has no reference image.")
                ref_media_ids.extend(self.ensure_character_references(c_id, project_id=target_pid))

            logger.info(f"[BananaClient] Requesting Banana Pro for {scene.scene_id} ({scene.visual_type}) on Flow project {target_pid}...")
            assets = self.adapter.generate_image(
                prompt=scene.image_prompt,
                project_id=target_pid,
                aspect_ratio="IMAGE_ASPECT_RATIO_LANDSCAPE",
                image_model="NANO_BANANA_PRO",
                reference_media_ids=ref_media_ids or None,
                count=1
            )

            if not assets:
                raise RuntimeError("No image asset returned from Google Flow")

            asset = assets[0]

            # Download asset to disk
            logger.info(f"[BananaClient] Downloading keyframe {scene.scene_id} from {asset.url[:60]}...")
            self.adapter.download_asset(asset.url, out_image_path)

            # Calculate MD5 hash of downloaded image (Section 21)
            with open(out_image_path, "rb") as f:
                img_hash = hashlib.md5(f.read()).hexdigest()
            prompt_hash = hashlib.md5(scene.image_prompt.encode("utf-8")).hexdigest()[:12]

            # Update scene & queue
            scene.image_media_id = asset.media_id
            scene.image_url = asset.url
            scene.status = "IMAGE_DONE"

            # Check if this replaces an existing keyframe -> mark dependent video STALE (Section 26)
            if item and item.image_media_id and item.image_media_id != asset.media_id:
                self.asset_mgr.mark_keyframe_updated(scene.scene_id)

            self.asset_mgr.update_item(
                scene.scene_id,
                image_status="DONE",
                image_qc_status="AWAITING_QC",  # Section 12: does not auto-approve
                image_media_id=asset.media_id,
                source_keyframe_media_id=asset.media_id,
                source_keyframe_hash=img_hash,
                image_file=str(out_image_path.relative_to(self.asset_mgr.project_dir)),
                generation_metadata={
                    "prompt_hash": prompt_hash,
                    "generated_at": time.time(),
                    "reference_media_ids": ref_media_ids
                },
                is_stale=False,
                stale_reason=None
            )

            # Append generation log (Section 28)
            self.asset_mgr.append_generation_log({
                "scene_id": scene.scene_id,
                "operation": "BANANA_KEYFRAME",
                "project_id": target_pid,
                "model": "NANO_BANANA_PRO",
                "status": "DONE",
                "media_id": asset.media_id,
                "attempt": (item.attempt_count if item else 0) + 1
            })

            logger.info(f"[BananaClient] Successfully generated & saved keyframe for {scene.scene_id} ({out_image_path.stat().st_size:,} bytes, hash: {img_hash[:8]})")
            return out_image_path

        except Exception as e:
            logger.error(f"[BananaClient] Keyframe generation failed for {scene.scene_id}: {e}")
            curr_attempt = (item.attempt_count if item else 0) + 1
            self.asset_mgr.update_item(
                scene.scene_id,
                image_status="FAILED",
                image_qc_status="FAILED",
                attempt_count=curr_attempt,
                last_error=str(e)
            )
            self.asset_mgr.append_generation_log({
                "scene_id": scene.scene_id,
                "operation": "BANANA_KEYFRAME",
                "project_id": target_pid,
                "model": "NANO_BANANA_PRO",
                "status": "FAILED",
                "error": str(e),
                "attempt": curr_attempt
            })
            return None

    def generate_all_keyframes(
        self,
        scenes: List[VisualScene],
        project_id: str = "",
        max_scenes: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Batch generates missing keyframes for all scenes in the plan.
        Supports optional max_scenes limit for incremental production or testing.
        """
        target_scenes = scenes[:max_scenes] if max_scenes else scenes
        success_count = 0
        failed_count = 0

        for sc in target_scenes:
            out_image_path = self.asset_mgr.images_dir / f"{sc.scene_id}.jpg"
            queue = self.asset_mgr.load_queue()
            item = queue.get(sc.scene_id)
            already_exists = bool(item and item.image_status == "DONE" and out_image_path.exists() and out_image_path.stat().st_size > 0)

            res = self.generate_scene_keyframe(sc, project_id=project_id)
            if res:
                success_count += 1
            else:
                failed_count += 1

            # Brief pause between real requests to respect Flow rate limits
            if not already_exists:
                time.sleep(1.0)

        return {
            "total_requested": len(target_scenes),
            "success": success_count,
            "failed": failed_count
        }
