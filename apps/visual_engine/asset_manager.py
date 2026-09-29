"""Visual Asset Manager & Persistent Queue for VieNeu Production Storytelling.

Manages:
- Project visual storage layout: projects/<slug>/visual/
- Persistent generation queue: visual_queue.json
- Resume & retry logic (zero regeneration of completed assets, resume-safe re-plan)
- Asset file storage and validation
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    scene_id: str
    visual_type: str = "UNRESOLVED"  # "BANANA_IMAGE", "OMNI_FLASH_I2V", or "VEO_I2V"
    image_status: str = "PLANNED"    # "PLANNED", "GENERATING", "DONE", "FAILED", "SKIPPED", "STALE"
    video_status: str = "PLANNED"    # "PLANNED", "GENERATING", "DONE", "FAILED", "SKIPPED", "STALE"
    image_media_id: Optional[str] = None
    image_file: Optional[str] = None
    video_media_id: Optional[str] = None
    video_file: Optional[str] = None
    video_operation_id: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None
    is_stale: bool = False
    stale_reason: Optional[str] = None  # "STALE_REFERENCE", "STALE_KEYFRAME", None
    image_qc_status: str = "PLANNED"  # "PLANNED", "AWAITING_QC", "APPROVED", "RETRY", "FAILED"
    video_qc_status: str = "PLANNED"  # "PLANNED", "AWAITING_QC", "APPROVED", "RETRY", "FAILED"
    source_keyframe_media_id: Optional[str] = None
    source_keyframe_hash: Optional[str] = None
    source_character_references: Dict[str, str] = field(default_factory=dict)
    generation_metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)


# Backward-compatible alias
VisualQueueItem = QueueItem


class VisualAssetManager:
    """Handles folder structure, disk I/O, and queue state for an episode."""

    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.visual_dir = self.project_dir / "visual"
        self.images_dir = self.visual_dir / "images"
        self.videos_dir = self.visual_dir / "videos"
        self.processed_dir = self.visual_dir / "processed"
        self.thumbnails_dir = self.visual_dir / "thumbnails"
        self.queue_file = self.visual_dir / "visual_queue.json"
        self.plan_file = self.visual_dir / "visual_plan.json"

        # Ensure all folders exist
        for d in (self.images_dir, self.videos_dir, self.processed_dir, self.thumbnails_dir):
            d.mkdir(parents=True, exist_ok=True)

    def init_queue(self, scenes: List[Any], force_reset: bool = False) -> Dict[str, QueueItem]:
        """Initializes or resumes visual_queue.json from a list of VisualScene objects."""
        return self.sync_queue_with_plan(scenes, force_reset=force_reset)

    def sync_queue_with_plan(self, scenes: List[Any], force_reset: bool = False) -> Dict[str, QueueItem]:
        """Synchronizes queue with visual plan while preserving existing assets (resume-safe)."""
        queue: Dict[str, QueueItem] = {}

        if not force_reset and self.queue_file.exists():
            try:
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for s_id, item_data in data.items():
                    queue[s_id] = QueueItem(**item_data)
                logger.info(f"Loaded existing visual queue with {len(queue)} items.")
            except Exception as e:
                logger.warning(f"Failed to load queue file, creating fresh: {e}")

        # Validate that every scene has a resolved visual_type
        for s in scenes:
            vtype = getattr(s, "visual_type", None) or (s.get("visual_type") if isinstance(s, dict) else None)
            s_id = getattr(s, "scene_id", None) or (s.get("scene_id") if isinstance(s, dict) else None)
            if not vtype or vtype == "UNRESOLVED":
                raise ValueError(f"Scene {s_id} has UNRESOLVED visual_type. Cannot sync queue.")

        seen_scene_ids = set()

        for s in scenes:
            s_id = getattr(s, "scene_id", None) or s.get("scene_id")
            vtype = getattr(s, "visual_type", None) or s.get("visual_type")
            seen_scene_ids.add(s_id)
            is_video = vtype in ("OMNI_FLASH_I2V", "VEO_I2V")

            if s_id not in queue:
                queue[s_id] = QueueItem(
                    scene_id=s_id,
                    visual_type=vtype,
                    image_status="PLANNED",
                    video_status="PLANNED" if is_video else "SKIPPED"
                )
            else:
                item = queue[s_id]
                old_type = item.visual_type
                item.visual_type = vtype

                # If changed to video from image
                if is_video and old_type not in ("OMNI_FLASH_I2V", "VEO_I2V"):
                    if item.video_status == "SKIPPED":
                        item.video_status = "PLANNED"
                # If changed to image from video
                elif not is_video and old_type in ("OMNI_FLASH_I2V", "VEO_I2V"):
                    # keep old video file on disk, but mark status SKIPPED
                    item.video_status = "SKIPPED"

                item.updated_at = time.time()

        # Clean up obsolete scenes from active queue if removed from plan,
        # but NEVER delete files from disk.
        current_keys = list(queue.keys())
        for k in current_keys:
            if k not in seen_scene_ids:
                del queue[k]

        self.save_queue(queue)
        return queue

    def load_queue(self) -> Dict[str, QueueItem]:
        """Loads queue from disk, filtering valid fields."""
        if not self.queue_file.exists():
            return {}
        with open(self.queue_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid_fields = {f.name for f in QueueItem.__dataclass_fields__.values()}
        return {s_id: QueueItem(**{k: v for k, v in d.items() if k in valid_fields}) for s_id, d in data.items()}

    def save_queue(self, queue: Dict[str, QueueItem]) -> None:
        """Persists visual queue to disk safely."""
        data = {s_id: asdict(item) for s_id, item in queue.items()}
        tmp_file = self.queue_file.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, self.queue_file)

    def update_item(self, scene_id: str, **kwargs) -> Optional[QueueItem]:
        """Updates a specific queue item and flushes to disk."""
        queue = self.load_queue()
        item = queue.get(scene_id)
        if not item:
            item = QueueItem(scene_id=scene_id, visual_type=kwargs.get("visual_type", "UNRESOLVED"))
            queue[scene_id] = item

        for k, v in kwargs.items():
            if hasattr(item, k):
                setattr(item, k, v)
        item.updated_at = time.time()
        self.save_queue(queue)
        return item

    # Alias for update_item
    update_queue_item = update_item

    def append_generation_log(self, entry: Dict[str, Any]) -> None:
        """Appends a generation request log entry to visual/generation_log.jsonl (Section 28)."""
        log_file = self.visual_dir / "generation_log.jsonl"
        safe_entry = {
            "scene_id": entry.get("scene_id", ""),
            "operation": entry.get("operation", ""),
            "project_id": entry.get("project_id", ""),
            "model": entry.get("model", ""),
            "timestamp": entry.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "status": entry.get("status", ""),
            "media_id": entry.get("media_id", ""),
            "attempt": entry.get("attempt", 1),
            "duration_sec": entry.get("duration_sec"),
            "error": entry.get("error")
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(safe_entry, ensure_ascii=False) + "\n")

    def mark_character_updated(self, char_id: str, new_media_id_or_scenes: Any = None) -> List[str]:
        """Marks all scenes depending on this character as STALE_REFERENCE (Section 26).
        Does NOT delete files from disk.
        """
        queue = self.load_queue()
        stale_scenes = []

        # Load plan to see which scenes reference this character
        scenes_data = []
        if isinstance(new_media_id_or_scenes, list):
            scenes_data = [
                {
                    "scene_id": getattr(s, "scene_id", None) or s.get("scene_id"),
                    "visible_characters": getattr(s, "visible_characters", None) or s.get("visible_characters") or [],
                    "characters": getattr(s, "characters", None) or s.get("characters") or []
                }
                for s in new_media_id_or_scenes
            ]
        elif self.plan_file.exists():
            try:
                with open(self.plan_file, "r", encoding="utf-8") as f:
                    pdata = json.load(f)
                scenes_data = pdata.get("scenes", [])
            except Exception as e:
                logger.warning(f"Failed to read plan_file: {e}")

        for sc in scenes_data:
            s_id = sc.get("scene_id")
            vis_chars = sc.get("visible_characters") or []
            story_chars = sc.get("story_characters") or sc.get("characters") or []
            if char_id in vis_chars or char_id in story_chars:
                item = queue.get(s_id)
                if item:
                    item.is_stale = True
                    item.stale_reason = "STALE_REFERENCE"
                    item.image_status = "STALE_REFERENCE"
                    item.image_qc_status = "AWAITING_QC"
                    if item.video_status == "DONE":
                        item.video_status = "STALE_KEYFRAME"
                        item.video_qc_status = "AWAITING_QC"
                    stale_scenes.append(s_id)

        self.save_queue(queue)
        logger.warning(f"Character {char_id} updated. Marked {len(stale_scenes)} scenes STALE_REFERENCE: {stale_scenes}")
        return stale_scenes

    def mark_keyframe_updated(self, scene_id: str, new_keyframe_hash: Optional[str] = None) -> None:
        """Marks dependent Omni video as STALE_KEYFRAME when keyframe changes (Section 26).
        Does NOT delete files from disk.
        """
        queue = self.load_queue()
        item = queue.get(scene_id)
        if item:
            item.is_stale = True
            item.stale_reason = f"STALE_KEYFRAME (new hash: {new_keyframe_hash})" if new_keyframe_hash else "STALE_KEYFRAME"
            if item.video_status in ("DONE", "GENERATING"):
                item.video_status = "STALE_KEYFRAME"
                item.video_qc_status = "AWAITING_QC"
            self.save_queue(queue)
            logger.warning(f"Keyframe {scene_id} updated. Dependent video marked STALE_KEYFRAME.")

    def approve_keyframe(self, scene_id: str, notes: str = "") -> None:
        """Approves a keyframe after user review (Section 15, 21)."""
        self.update_item(scene_id, image_qc_status="APPROVED", is_stale=False, stale_reason=None)

    def approve_video(self, scene_id: str, notes: str = "") -> None:
        """Approves a video clip after user review (Section 25)."""
        self.update_item(scene_id, video_qc_status="APPROVED", is_stale=False, stale_reason=None)

    def calculate_batch_credit_cost(
        self,
        scenes: List[Any],
        target_scene_ids: Optional[List[str]] = None,
        include_images: bool = True,
        include_videos: bool = True
    ) -> Dict[str, int]:
        """Calculates exact request count before batch generation (Section 27)."""
        targets = [
            s for s in scenes
            if not target_scene_ids or (getattr(s, "scene_id", None) or s.get("scene_id")) in target_scene_ids
        ]
        banana_cnt = len(targets) if include_images else 0
        omni_cnt = sum(
            1 for s in targets
            if (getattr(s, "visual_type", None) or s.get("visual_type")) in ("OMNI_FLASH_I2V", "VEO_I2V")
        ) if include_videos else 0
        return {
            "banana_requests": banana_cnt,
            "omni_requests": omni_cnt,
            "total_requests": banana_cnt + omni_cnt
        }

    def load_pilot_qc_status(self) -> Dict[str, Any]:
        """Loads pilot QC report from visual/pilot_qc_report.json."""
        qc_file = self.visual_dir / "pilot_qc_report.json"
        if not qc_file.exists():
            return {}
        try:
            with open(qc_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_pilot_qc_status(self, report: Dict[str, Any]) -> None:
        """Persists pilot QC report to visual/pilot_qc_report.json."""
        qc_file = self.visual_dir / "pilot_qc_report.json"
        with open(qc_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def is_full_generation_unlocked(
        self,
        scenes: List[Any],
        character_lib: Dict[str, Any]
    ) -> Tuple[bool, Dict[str, Any]]:
        """Strict lock gate for Generate All (Section 30).
        Unlock ONLY when:
        - all required character references ready
        - 8/8 pilot keyframes reviewed & approved
        - all required pilot Omni clips reviewed & approved
        - 0 critical semantic failure
        """
        pilot_ids = ["SC_001", "SC_005", "SC_011", "SC_025", "SC_030", "SC_035", "SC_041", "SC_045"]
        pilot_omni_ids = ["SC_001", "SC_025", "SC_035", "SC_041", "SC_045"]

        queue = self.load_queue()
        pilot_report = self.load_pilot_qc_status()

        # 1. Required character references
        required_chars = ["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"]
        chars_ready = all(
            cid in character_lib and getattr(character_lib[cid], "references", None)
            for cid in required_chars
        )

        # 2. Pilot keyframes reviewed & approved
        pilot_keyframes_approved = 0
        for pid in pilot_ids:
            item = queue.get(pid)
            if item and item.image_qc_status == "APPROVED":
                pilot_keyframes_approved += 1

        # 3. Pilot Omni videos reviewed & approved
        pilot_videos_approved = 0
        for pid in pilot_omni_ids:
            item = queue.get(pid)
            if item and item.video_qc_status == "APPROVED":
                pilot_videos_approved += 1

        # 4. Critical semantic failures
        critical_failures = 0
        for pid, data in pilot_report.get("scenes", {}).items():
            if data.get("status") == "FAILED" or data.get("critical_failure"):
                critical_failures += 1

        unlocked = (
            chars_ready
            and (pilot_keyframes_approved == len(pilot_ids))
            and (pilot_videos_approved == len(pilot_omni_ids))
            and (critical_failures == 0)
        )

        status_info = {
            "full_generation_unlocked": unlocked,
            "characters_ready": chars_ready,
            "pilot_keyframes_approved": f"{pilot_keyframes_approved}/{len(pilot_ids)}",
            "pilot_videos_approved": f"{pilot_videos_approved}/{len(pilot_omni_ids)}",
            "critical_failures": critical_failures,
            "reason": "Ready" if unlocked else "Pilot review pending: Approve all 8 pilot keyframes and 5 pilot videos first."
        }
        return unlocked, status_info

    def get_progress(self) -> Dict[str, Any]:
        """Calculates current visual generation progress for UI."""
        queue = self.load_queue()
        total_scenes = len(queue)
        if total_scenes == 0:
            return {
                "total_scenes": 0,
                "images_ready": 0,
                "videos_ready": 0,
                "failed": 0,
                "status_text": "Not Planned"
            }

        images_ready = sum(1 for q in queue.values() if q.image_status == "DONE")
        veo_required = sum(1 for q in queue.values() if q.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"))
        videos_ready = sum(1 for q in queue.values() if q.video_status == "DONE" and q.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V"))
        failed = sum(1 for q in queue.values() if q.image_status == "FAILED" or q.video_status == "FAILED")

        return {
            "total_scenes": total_scenes,
            "images_ready": images_ready,
            "veo_required": veo_required,
            "videos_ready": videos_ready,
            "failed": failed,
            "ready_to_render": (images_ready == total_scenes and videos_ready == veo_required and failed == 0)
        }
