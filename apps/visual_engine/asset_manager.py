"""Visual Asset Manager & Persistent Queue for VieNeu Production Storytelling.

Manages:
- Project visual storage layout: projects/<slug>/visual/
- Persistent generation queue: visual_queue.json
- Resume & retry logic (zero regeneration of completed assets)
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

from apps.visual_engine.visual_planner import VisualScene

logger = logging.getLogger(__name__)


@dataclass
class QueueItem:
    scene_id: str
    visual_type: str  # "BANANA_IMAGE" or "VEO_I2V"
    image_status: str = "PLANNED"  # "PLANNED", "GENERATING", "DONE", "FAILED", "SKIPPED"
    video_status: str = "PLANNED"  # "PLANNED", "GENERATING", "DONE", "FAILED", "SKIPPED"
    image_media_id: Optional[str] = None
    image_file: Optional[str] = None
    video_media_id: Optional[str] = None
    video_file: Optional[str] = None
    video_operation_id: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None
    updated_at: float = field(default_factory=time.time)


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

    def init_queue(self, scenes: List[VisualScene], force_reset: bool = False) -> Dict[str, QueueItem]:
        """Initializes or resumes visual_queue.json."""
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

        # Merge in any new scenes
        for s in scenes:
            if s.scene_id not in queue:
                queue[s.scene_id] = QueueItem(
                    scene_id=s.scene_id,
                    visual_type=s.visual_type,
                    image_status="PLANNED",
                    video_status="PLANNED" if s.visual_type == "VEO_I2V" else "SKIPPED"
                )

        self.save_queue(queue)
        return queue

    def load_queue(self) -> Dict[str, QueueItem]:
        """Loads queue from disk."""
        if not self.queue_file.exists():
            return {}
        with open(self.queue_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {s_id: QueueItem(**d) for s_id, d in data.items()}

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
            return None

        for k, v in kwargs.items():
            if hasattr(item, k):
                setattr(item, k, v)
        item.updated_at = time.time()
        self.save_queue(queue)
        return item

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
        veo_required = sum(1 for q in queue.values() if q.visual_type == "VEO_I2V")
        videos_ready = sum(1 for q in queue.values() if q.video_status == "DONE")
        failed = sum(1 for q in queue.values() if q.image_status == "FAILED" or q.video_status == "FAILED")

        return {
            "total_scenes": total_scenes,
            "images_ready": images_ready,
            "veo_required": veo_required,
            "videos_ready": videos_ready,
            "failed": failed,
            "ready_to_render": (images_ready == total_scenes and videos_ready == veo_required and failed == 0)
        }
