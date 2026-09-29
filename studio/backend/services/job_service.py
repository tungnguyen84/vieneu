"""Job Service for asynchronous background task execution."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from studio.backend.db import get_db_connection
from studio.backend.models import JobItem, JobStatus


class JobService:
    def __init__(self):
        pass

    def list_jobs(self, project_id: Optional[str] = None) -> List[JobItem]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("SELECT * FROM jobs WHERE project_id = ? ORDER BY started_at DESC LIMIT 20", (project_id,))
            else:
                cursor.execute("SELECT * FROM jobs ORDER BY started_at DESC LIMIT 20")
            rows = cursor.fetchall()
            jobs = []
            for r in rows:
                jobs.append(JobItem(
                    job_id=r["job_id"],
                    project_id=r["project_id"],
                    job_type=r["job_type"],
                    status=JobStatus(r["status"]),
                    progress=r["progress"],
                    step_label=r["step_label"],
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    logs=json.loads(r["logs"]) if r["logs"] else [],
                    error_message=r["error_message"]
                ))
            return jobs

    def create_job(self, job_id: str, project_id: str, job_type: str, step_label: str = "") -> JobItem:
        now = time.time()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO jobs (
                    job_id, project_id, job_type, status, progress, step_label, started_at, logs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (job_id, project_id, job_type, JobStatus.RUNNING.value, 0.0, step_label, now, "[]"))
            conn.commit()
        return JobItem(
            job_id=job_id,
            project_id=project_id,
            job_type=job_type,
            status=JobStatus.RUNNING,
            progress=0.0,
            step_label=step_label,
            started_at=now
        )

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[float] = None,
        step_label: Optional[str] = None,
        log_line: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT logs FROM jobs WHERE job_id = ?", (job_id,))
            r = cursor.fetchone()
            logs = json.loads(r["logs"]) if r and r["logs"] else []
            if log_line:
                logs.append(log_line)

            updates = ["logs = ?"]
            params: List[Any] = [json.dumps(logs)]

            if status is not None:
                updates.append("status = ?")
                params.append(status.value)
                if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    updates.append("completed_at = ?")
                    params.append(time.time())

            if progress is not None:
                updates.append("progress = ?")
                params.append(progress)

            if step_label is not None:
                updates.append("step_label = ?")
                params.append(step_label)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            params.append(job_id)
            cursor.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?", params)
            conn.commit()
