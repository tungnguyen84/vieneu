"""Render Service orchestrating Auto Assembler V9.3.2 and Dynamic Still Engine."""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from studio.backend.db import get_db_connection
from studio.backend.models import JobStatus
from studio.backend.services.artifact_files import file_sha256

logger = logging.getLogger("VieNeu.RenderService")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "final"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR = BASE_DIR / "projects"
PILOT_03_VISUAL = BASE_DIR / "production_pilot_03_visual_v1_0a"


class RenderService:
    def __init__(self):
        self._active_renders: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}

    def get_render_status(self, project_id: str) -> Dict[str, Any]:
        with self._lock:
            if project_id in self._active_renders and self._active_renders[project_id].get("stage") != "COMPLETE":
                return self._active_renders[project_id]

        # Check DB history - only trust if output file exists on disk!
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM render_history WHERE project_id = ? ORDER BY rendered_at DESC LIMIT 1",
                (project_id,)
            )
            r = cursor.fetchone()
            if r and r["output_path"]:
                out_path = BASE_DIR / r["output_path"]
                if out_path.exists() and out_path.is_file() and out_path.stat().st_size > 0:
                    qc = self._inspect_output(project_id, out_path)
                    return {
                        "is_rendering": False,
                        "progress": 100.0,
                        "stage": "COMPLETE",
                        "output_file": r["output_path"],
                        "status": qc["overall_status"],
                        "qc_summary": qc
                    }

        # Check existing final render file on disk
        final_mp4s = [
            p for p in OUTPUT_DIR.glob(f"{project_id}_*.mp4")
            if p.is_file() and p.stat().st_size > 0
        ]
        if final_mp4s:
            return {
                "is_rendering": False,
                "progress": 100.0,
                "stage": "READY",
                "output_file": str(final_mp4s[0].relative_to(BASE_DIR)),
                "status": self._inspect_output(project_id, final_mp4s[0])["overall_status"]
            }

        return {
            "is_rendering": False,
            "progress": 0.0,
            "stage": "NOT_STARTED",
            "output_file": None,
            "status": "NOT_STARTED"
        }

    def start_render(
        self,
        project_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """Starts asynchronous rendering job with live multi-stage updates."""
        render_id = f"render_{project_id}_{int(time.time())}"

        state = {
            "render_id": render_id,
            "project_id": project_id,
            "is_rendering": True,
            "progress": 0.0,
            "stage": "PREPARING_ASSETS",
            "stage_label": "Chuẩn bị tài nguyên và kiểm tra file...",
            "current_scene": "SC_001",
            "elapsed_sec": 0.0,
            "logs": ["Khởi động Render Service...", "Đọc visual_plan.json và audio_master..."],
            "output_file": None,
            "status": "RUNNING",
            "cancel_requested": False
        }

        with self._lock:
            if self._active_renders.get(project_id, {}).get("is_rendering"):
                raise ValueError("Tập này đang render")
            self._active_renders[project_id] = state
            self._cancel_events[project_id] = threading.Event()

        # Launch background thread
        thread = threading.Thread(
            target=self._run_render_worker,
            args=(project_id, render_id, progress_callback),
            daemon=True
        )
        thread.start()
        return render_id

    def cancel_render(self, project_id: str) -> bool:
        with self._lock:
            if project_id in self._active_renders:
                self._active_renders[project_id]["cancel_requested"] = True
                self._active_renders[project_id]["status"] = "CANCELLED"
                self._cancel_events[project_id].set()
                return True
        return False

    def _inspect_output(self, project_id: str, output: Path) -> Dict[str, Any]:
        from studio.backend.services.qc_service import QCService
        return QCService().get_qc_report(project_id, video_path=output).model_dump()

    def _build_project_plan(self, project_id: str, plan_path: Path, audio_path: Path, flow_zip: Optional[Path], audio_binding=None):
        from apps.visual_engine.final_auto_assembler import (
            build_assembly_plan, inspect_and_extract_zip, normalize_scene_id,
            validate_image_file, get_video_info, VALID_IMAGE_EXTS, VALID_VIDEO_EXTS,
        )
        import soundfile as sf

        raw = json.loads(plan_path.read_text(encoding="utf-8"))
        if raw.get("audio_sha256") != file_sha256(audio_path):
            raise ValueError("Visual Plan STALE: không thuộc Audio Master hiện tại; cần lập lại Visual")
        if audio_binding and (raw.get("source_script_content_hash") != audio_binding["script_content_hash"]
                              or raw.get("source_story_content_hash") != audio_binding["story_content_hash"]):
            raise ValueError("Visual Plan STALE: không thuộc Script/Story hiện tại")
        scenes = raw.get("scenes", [])
        if not scenes:
            raise ValueError("Visual Plan không có cảnh")
        audio_duration = sf.info(audio_path).duration
        definitions = []
        for scene in scenes:
            start, end = float(scene["start_time"]), float(scene["end_time"])
            if not all(math.isfinite(v) for v in (start, end)) or end <= start:
                raise ValueError(f"Timing cảnh {scene['scene_id']} không hợp lệ")
            motion = scene.get("image_motion", "SLOW_PUSH_IN")
            if isinstance(motion, dict):
                motion = motion.get("type", "SLOW_PUSH_IN")
            definitions.append({**scene, "start_sec": start, "end_sec": end, "duration_sec": end - start,
                                "image_motion": motion, "source_segment_ids": scene.get("source_segments") or ["001"]})
        if abs(definitions[0]["start_sec"]) > 0.001 or abs(definitions[-1]["end_sec"] - audio_duration) > 0.02:
            raise ValueError("Visual Plan không khớp Audio Master hiện tại; cần lập lại Visual")
        for left, right in zip(definitions, definitions[1:]):
            if abs(left["end_sec"] - right["start_sec"]) > 0.001:
                raise ValueError("Visual Plan có khoảng trống hoặc cảnh chồng nhau")
        if len({s['scene_id'] for s in definitions}) != len(definitions):
            raise ValueError("Visual Plan có scene ID trùng nhau")

        project = PROJECTS_DIR / project_id
        images, videos = {}, {}
        if flow_zip:
            images, videos, _, _ = inspect_and_extract_zip(flow_zip, project / "render" / "imported_assets")
        # Also support assets imported by the Studio assets endpoint.
        for asset in (project / "assets").rglob("*"):
            scene_id = normalize_scene_id(asset.name)
            if asset.is_file() and scene_id:
                if asset.suffix.lower() in VALID_IMAGE_EXTS:
                    images[scene_id] = asset
                elif asset.suffix.lower() in VALID_VIDEO_EXTS:
                    videos[scene_id] = asset
        for scene in definitions:
            sid = scene["scene_id"]
            # Both styles (SC001 / SC_001) resolve through the engine normalizer.
            normalized = normalize_scene_id(sid)
            for mapping in (images, videos):
                if normalized in mapping:
                    mapping[sid] = mapping[normalized]
            image, video = images.get(sid), videos.get(sid)
            if image and not validate_image_file(image)[0]:
                raise ValueError(f"Ảnh cảnh {sid} bị hỏng")
            if video and not get_video_info(video)[0]:
                raise ValueError(f"Video cảnh {sid} bị hỏng")
            if not image and not video:
                raise FileNotFoundError(f"Thiếu media cho cảnh {sid}; cần import tài nguyên Google Flow")
        overrides = {s["scene_id"]: "USE_IMAGE" for s in definitions if s.get("visual_mode") == "IMAGE_ONLY"}
        plan = build_assembly_plan(images, videos, audio_path, manual_overrides=overrides, scene_definitions=definitions)
        plan.episode_id = project_id
        plan.project_slug = project_id
        plan.total_audio_duration_sec = audio_duration
        plan.av_delta_sec = abs(plan.total_visual_duration_sec - audio_duration)
        return plan

    def _run_render_worker(
        self,
        project_id: str,
        render_id: str,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]]
    ) -> None:
        start_t = time.time()
        out_name = f"{project_id}_FINAL_V9_3_2.mp4"
        out_path = OUTPUT_DIR / out_name

        try:
            # Stage 1: Validate dependencies
            with self._lock:
                cur = self._active_renders[project_id]
                cur["stage"] = "PREPARING_ASSETS"
                cur["stage_label"] = "Kiểm tra Audio Master và Visual Plan..."
                cur["progress"] = 10.0
                cur["logs"].append("Kiểm tra Audio Master...")
            if progress_cb:
                progress_cb(self._active_renders[project_id])

            from studio.backend.services.audio_service import AudioService
            audio_binding = AudioService().require_current_audio(project_id)
            audio_path = AudioService().get_audio_master_path(project_id)
            if not audio_path or not audio_path.exists():
                raise FileNotFoundError(
                    f"Chưa có Audio Master cho tập {project_id}. "
                    "Vui lòng tạo TTS và hòa âm nhạc nền trước khi render video."
                )

            # Check Visual Plan
            plan_path = PROJECTS_DIR / project_id / "visual_plan.json"
            if not plan_path.exists():
                plan_path = PILOT_03_VISUAL / project_id / "visual_plan.json"
            if not plan_path.exists():
                raise FileNotFoundError(
                    f"Chưa có Visual Plan cho tập {project_id}. "
                    "Vui lòng lập Visual Plan ở bước Visual trước khi render video."
                )

            # Check Google Flow assets (images/videos)
            assets_dir = PROJECTS_DIR / project_id / "assets"
            flow_zip = None
            for candidate_zip in [
                PROJECTS_DIR / project_id / "google_flow_export.zip",
                PROJECTS_DIR / project_id / "New_Project_FULL_EXPORT.zip",
                BASE_DIR / f"{project_id}_FULL_EXPORT.zip",
            ]:
                if candidate_zip.exists():
                    flow_zip = candidate_zip
                    break

            has_assets = (assets_dir.exists() and any(assets_dir.iterdir())) or (flow_zip is not None)
            
            # If assets are missing and output MP4 doesn't exist, fail with clear error
            if not has_assets:
                raise FileNotFoundError(
                    "Không thể Render: Chưa có tài nguyên hình ảnh/video từ Google Flow. "
                    "Hãy tải lên gói xuất Google Flow (ZIP) hoặc các file media vào thư mục assets/ trước khi Render."
                )

            # If real assembler is applicable
            if has_assets:
                from apps.visual_engine.final_auto_assembler import assemble_full_episode
                plan = self._build_project_plan(project_id, plan_path, audio_path, flow_zip, audio_binding)
                with self._lock:
                    cur = self._active_renders[project_id]
                    cur["stage"] = "TIMELINE_ASSEMBLY"
                    cur["stage_label"] = "Đang chạy Final Auto Assembler ghép video..."
                    cur["progress"] = 50.0
                    cur["logs"].append(f"Chạy assembler từ {flow_zip.name if flow_zip else 'media đã import trong Assets'}...")
                if progress_cb:
                    progress_cb(self._active_renders[project_id])

                def update_progress(done, total, message):
                    with self._lock:
                        self._active_renders[project_id].update(
                            progress=20 + 70 * done / max(1, total), stage_label=message,
                            elapsed_sec=time.time() - start_t,
                        )
                    if progress_cb:
                        progress_cb(self._active_renders[project_id])

                # Render in a project-specific directory so the engine's reports
                # and cache cannot be reused accidentally by another episode.
                render_dir = PROJECTS_DIR / project_id / "render" / render_id
                source_plan_hash, source_audio_hash = file_sha256(plan_path), file_sha256(audio_path)
                result_path, rep = assemble_full_episode(
                    plan=plan, output_mp4_path=render_dir / out_name,
                    cache_dir=PROJECTS_DIR / project_id / "render" / "cache",
                    cancel_event=self._cancel_events[project_id], progress_callback=update_progress,
                )
                if self._cancel_events[project_id].is_set():
                    raise RuntimeError("Render đã được hủy")
                if not result_path.is_file() or result_path.stat().st_size == 0:
                    raise RuntimeError("Assembler không tạo được video")
                AudioService().require_current_audio(project_id)
                if file_sha256(plan_path) != source_plan_hash or file_sha256(audio_path) != source_audio_hash:
                    raise ValueError("Nguồn Visual/Audio thay đổi trong lúc render; video chưa được công bố")
                shutil.copy2(result_path, out_path)
                evidence = {
                    "project_id": project_id,
                    "visual_plan_path": str(plan_path.resolve()), "audio_path": str(audio_path.resolve()),
                    "video_sha256": file_sha256(out_path),
                    "expected_scene_ids": [s.scene_id for s in plan.scenes],
                    "rendered_scene_ids": [s.scene_id for s in plan.scenes],
                    "longest_accidental_static_hold_sec": rep.get("longest_accidental_static_hold_sec"),
                    "visual_plan_sha256": source_plan_hash,
                    "audio_sha256": source_audio_hash,
                }
                out_path.with_suffix(".studio_render.json").write_text(json.dumps(evidence), encoding="utf-8")

            # Verify output file exists
            if not out_path.exists() or out_path.stat().st_size == 0:
                raise FileNotFoundError(f"Quá trình render không tạo được file output tại: {out_path}")

            # Run real QC inspection on the generated video
            from studio.backend.services.qc_service import QCService
            qc_service = QCService()
            qc_rep = qc_service.get_qc_report(project_id, video_path=out_path)
            qc_summary = {
                "overall_status": qc_rep.overall_status,
                "duration_sec": qc_rep.duration_sec,
                "resolution": qc_rep.resolution,
                "fps": qc_rep.fps,
                "av_sync_delta_ms": qc_rep.av_sync_delta_ms,
                "black_gap_detected": qc_rep.black_gap_detected,
                "static_hold_exceeded": qc_rep.static_hold_exceeded,
                "integrated_loudness_lufs": qc_rep.integrated_loudness_lufs,
                "true_peak_db": qc_rep.true_peak_db
            }

            with self._lock:
                cur_state = self._active_renders[project_id]
                cur_state["is_rendering"] = False
                cur_state["progress"] = 100.0
                cur_state["stage"] = "COMPLETE"
                cur_state["stage_label"] = f"Video Render hoàn tất! Trạng thái QC: {qc_rep.overall_status}"
                cur_state["output_file"] = f"final/{out_name}"
                cur_state["status"] = qc_rep.overall_status
                cur_state["qc_summary"] = qc_summary
                cur_state["logs"].append(f"Xuất file thành công: {out_name} ({qc_rep.duration_sec}s)")

            # Record in DB
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO render_history (
                        render_id, project_id, output_path, version_label,
                        rendered_at, duration_sec, resolution, status, qc_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    render_id, project_id, f"final/{out_name}", "V9.3.2",
                    time.time(), qc_rep.duration_sec, qc_rep.resolution, qc_rep.overall_status, json.dumps(qc_summary)
                ))
                conn.commit()

        except Exception as e:
            logger.error(f"Render failed for {project_id}: {e}", exc_info=True)
            with self._lock:
                if project_id in self._active_renders:
                    cur = self._active_renders[project_id]
                    cur["is_rendering"] = False
                    cancelled = self._cancel_events[project_id].is_set()
                    cur["status"] = "CANCELLED" if cancelled else "FAILED"
                    cur["stage"] = cur["status"]
                    cur["stage_label"] = f"Render thất bại: {str(e)}"
                    cur["logs"].append(f"[LỖI] {str(e)}")
            if progress_cb:
                progress_cb(self._active_renders[project_id])
