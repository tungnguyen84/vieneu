"""Batch Generation and Resume Safety Manager for Script Factory V1."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apps.script_factory.models import FullScript, IdeaItem, StoryBible

logger = logging.getLogger("VieNeu.BatchManager")

BATCH_JOBS_FILE = Path("script_factory/batch_jobs.json")


@dataclass
class BatchJob:
    job_id: str
    job_type: str  # "GENERATE_IDEAS", "GENERATE_SCRIPTS"
    total_items: int
    completed_items: int
    status: str  # "QUEUED", "RUNNING", "DONE", "FAILED", "CANCELLED"
    item_ids: List[str] = field(default_factory=list)
    done_ids: List[str] = field(default_factory=list)
    failed_ids: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BatchJob:
        return cls(**data)


class BatchManager:
    """Manages batch operations with persistence and restart resumption safety."""

    def __init__(self, persistence_file: Optional[Path] = None):
        self.file_path = Path(persistence_file) if persistence_file else BATCH_JOBS_FILE
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load_jobs(self) -> Dict[str, BatchJob]:
        """Loads all batch jobs from disk."""
        if not self.file_path.exists():
            return {}
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: BatchJob.from_dict(v) for k, v in data.items()}
        except Exception:
            return {}

    def save_jobs(self, jobs: Dict[str, BatchJob]) -> None:
        """Saves batch jobs to disk."""
        data = {k: v.to_dict() for k, v in jobs.items()}
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_script_batch_job(self, episode_ids: List[str]) -> BatchJob:
        """Creates a batch job for full script generation."""
        jobs = self.load_jobs()
        job_id = f"BATCH_SCRIPT_{int(time.time())}"
        job = BatchJob(
            job_id=job_id,
            job_type="GENERATE_SCRIPTS",
            total_items=len(episode_ids),
            completed_items=0,
            status="QUEUED",
            item_ids=list(episode_ids),
            done_ids=[],
            failed_ids=[],
        )
        jobs[job_id] = job
        self.save_jobs(jobs)
        return job

    def run_script_batch(
        self,
        job_id: str,
        generate_fn: Callable[[str], FullScript],
        resume_only: bool = True,
    ) -> BatchJob:
        """
        Executes a script generation batch job.
        Strict rule: Resumes without re-running any item already marked DONE!
        """
        jobs = self.load_jobs()
        if job_id not in jobs:
            raise KeyError(f"Batch job {job_id} not found.")

        job = jobs[job_id]
        job.status = "RUNNING"
        job.updated_at = time.time()
        self.save_jobs(jobs)

        for ep_id in job.item_ids:
            if resume_only and ep_id in job.done_ids:
                logger.info(f"[BatchManager] Skipping already completed episode {ep_id}")
                continue

            try:
                generate_fn(ep_id)
                job.done_ids.append(ep_id)
                job.completed_items = len(job.done_ids)
                job.updated_at = time.time()
                self.save_jobs(jobs)
            except Exception as e:
                logger.error(f"[BatchManager] Episode {ep_id} failed in batch {job_id}: {e}")
                if ep_id not in job.failed_ids:
                    job.failed_ids.append(ep_id)
                self.save_jobs(jobs)

        if len(job.done_ids) == job.total_items:
            job.status = "DONE"
        elif job.failed_ids:
            job.status = "FAILED"
            job.error = f"{len(job.failed_ids)} items failed."
        else:
            job.status = "DONE"

        job.updated_at = time.time()
        self.save_jobs(jobs)
        return job
