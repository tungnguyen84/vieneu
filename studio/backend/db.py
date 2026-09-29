"""SQLite persistence layer for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_FILE = Path(__file__).resolve().parent.parent / "studio_data.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Projects Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                series_id TEXT NOT NULL,
                episode_number TEXT NOT NULL,
                duration_sec REAL DEFAULT 0.0,
                scene_count INTEGER DEFAULT 45,
                image_count INTEGER DEFAULT 38,
                video_count INTEGER DEFAULT 7,
                stage_statuses TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                is_archived INTEGER DEFAULT 0
            )
        """)

        # Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL DEFAULT 0.0,
                step_label TEXT DEFAULT '',
                started_at REAL,
                completed_at REAL,
                logs TEXT DEFAULT '[]',
                error_message TEXT
            )
        """)

        # Approvals / Overrides Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage_id TEXT NOT NULL,
                status TEXT NOT NULL,
                approved_by TEXT DEFAULT 'USER',
                timestamp REAL NOT NULL,
                notes TEXT
            )
        """)

        # Render History Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS render_history (
                render_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                output_path TEXT NOT NULL,
                version_label TEXT NOT NULL,
                rendered_at REAL NOT NULL,
                duration_sec REAL NOT NULL,
                resolution TEXT NOT NULL,
                status TEXT NOT NULL,
                qc_summary TEXT
            )
        """)
        conn.commit()


# Initialize on import
init_db()
