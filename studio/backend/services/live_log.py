"""Per-project live processing log for the Studio UI.

Generation endpoints run synchronously for minutes (model fallback, key
rotation, QC review, repair rounds). This captures the pipeline's own log
records while a request is handling a project, so the UI can poll and show
what is happening and where it failed instead of an endless spinner.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Deque, Dict, Iterator, List, Optional

# Loggers whose records describe the generation pipeline.
_PIPELINE_LOGGERS = ("VieNeu", "SCCStudio")
_MAX_ENTRIES_PER_PROJECT = 1500

_current_project: ContextVar[Optional[str]] = ContextVar("scc_live_log_project", default=None)

# Never show credentials, even if a provider error echoes one back.
_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"([?&]key=)[^&\s\"']+"),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{12,}"),
]


def _redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


class _LiveLogStore:
    def __init__(self) -> None:
        self.epoch = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._seq = 0
        self._entries: Dict[str, Deque[Dict[str, Any]]] = {}
        # project_id -> jobs currently handling it (two buttons can overlap).
        self._running: Dict[str, List[Dict[str, Any]]] = {}

    def start_job(self, project_id: str, action: str) -> Dict[str, Any]:
        job = {"action": action, "started": time.time()}
        with self._lock:
            self._running.setdefault(project_id, []).append(job)
        return job

    def finish_job(self, project_id: str, job: Dict[str, Any]) -> None:
        with self._lock:
            jobs = self._running.get(project_id, [])
            if job in jobs:
                jobs.remove(job)
            if not jobs:
                self._running.pop(project_id, None)

    def add(self, project_id: str, level: str, source: str, message: str) -> None:
        with self._lock:
            self._seq += 1
            bucket = self._entries.setdefault(project_id, deque(maxlen=_MAX_ENTRIES_PER_PROJECT))
            bucket.append({
                "seq": self._seq,
                "ts": time.time(),
                "level": level,
                "source": source,
                "message": _redact(message)[:2000],
            })

    def read(self, project_id: str, since: int = 0) -> Dict[str, Any]:
        with self._lock:
            entries = [e for e in self._entries.get(project_id, ()) if e["seq"] > since]
            jobs = self._running.get(project_id) or []
            running = None
            if jobs:
                running = {
                    "action": " + ".join(j["action"] for j in jobs),
                    "started": min(j["started"] for j in jobs),
                    "count": len(jobs),
                }
            return {"entries": entries, "last_seq": self._seq, "running": running, "epoch": self.epoch}


store = _LiveLogStore()


class _LiveLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        project_id = _current_project.get()
        if not project_id:
            return
        try:
            message = record.getMessage()
            if record.exc_info and record.levelno >= logging.ERROR:
                message += f" ({record.exc_info[1]})"
            source = record.name.split(".", 1)[-1]
            store.add(project_id, record.levelname, source, message)
        except Exception:
            self.handleError(record)


_installed = False


def install() -> None:
    """Attaches the capture handler once; pipeline INFO records become visible."""
    global _installed
    if _installed:
        return
    handler = _LiveLogHandler(level=logging.INFO)
    for name in _PIPELINE_LOGGERS:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        if logger.level == logging.NOTSET or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
    _installed = True


@contextmanager
def project_scope(project_id: str, action: str) -> Iterator[None]:
    """Tags every pipeline log record emitted inside the block with ``project_id``."""
    token = _current_project.set(project_id)
    job = store.start_job(project_id, action)
    started = time.time()
    log = logging.getLogger("SCCStudio.Job")
    log.info(f"▶ Bắt đầu: {action}")
    try:
        yield
        log.info(f"✔ Hoàn tất: {action} ({time.time() - started:.0f}s)")
    except Exception as exc:
        log.error(f"✖ Thất bại: {action} sau {time.time() - started:.0f}s — {exc}")
        raise
    finally:
        store.finish_job(project_id, job)
        _current_project.reset(token)


def read(project_id: str, since: int = 0) -> Dict[str, Any]:
    return store.read(project_id, since)
