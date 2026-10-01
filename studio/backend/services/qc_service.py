"""Final QC reports only measured properties of the current video file."""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from studio.backend.db import get_db_connection
from studio.backend.models import FinalQCReport
from studio.backend.services.artifact_files import file_sha256

logger = logging.getLogger("VieNeu.QCService")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class QCService:
    def find_project_video_path(self, project_id: str) -> Optional[Path]:
        candidates = [
            BASE_DIR / "final" / f"{project_id}_FINAL_V9_3_2.mp4",
            BASE_DIR / "final" / f"{project_id}.mp4",
            BASE_DIR / "projects" / project_id / "render" / "final.mp4",
            BASE_DIR / "projects" / project_id / f"{project_id}.mp4",
        ]
        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT output_path FROM render_history WHERE project_id = ? ORDER BY rendered_at DESC LIMIT 1",
                    (project_id,),
                ).fetchone()
                if row and row["output_path"]:
                    candidates.append(BASE_DIR / row["output_path"])
        except Exception:
            pass
        return next((p for p in candidates if p.is_file() and p.stat().st_size > 0), None)

    def _probe_video_file(self, video_path: Path) -> Dict[str, Any]:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=index,codec_type,codec_name,width,height,r_frame_rate,start_time,duration:format=duration,size",
            "-of", "json", str(video_path),
        ], capture_output=True, text=True, check=True, timeout=60)
        return json.loads(result.stdout)

    def _inspect_signal(self, video_path: Path) -> Dict[str, Any]:
        result = subprocess.run([
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(video_path),
            "-af", "ebur128=peak=true:framelog=verbose",
            "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-",
        ], capture_output=True, text=True, check=True, timeout=1800)
        output = result.stderr or ""
        lufs = re.findall(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", output)
        peaks = re.findall(r"True peak:\s+Peak:\s+([-\d.]+)\s+dB(?:TP|FS)", output)
        if not lufs or not peaks:
            raise ValueError("ffmpeg không trả về phép đo LUFS/True Peak hợp lệ")
        measured = float(lufs[-1]), float(peaks[-1])
        if not all(math.isfinite(value) for value in measured):
            raise ValueError("Phép đo âm lượng không hữu hạn")
        return {
            "lufs": measured[0], "true_peak": measured[1],
            "black_gaps": re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", output),
        }

    def _measure_audio_loudness(self, video_path: Path) -> Tuple[float, float]:
        measured = self._inspect_signal(video_path)
        return measured["lufs"], measured["true_peak"]

    def get_qc_report(self, project_id: str, video_path: Optional[Path] = None) -> FinalQCReport:
        video_path = video_path or self.find_project_video_path(project_id)
        checks = []

        def add(key: str, name: str, value: Any, required: str, passed: Optional[bool]) -> None:
            checks.append({"id": key, "name": name, "value": str(value), "required": required,
                           "status": "NOT_RUN" if passed is None else "PASS" if passed else "FAIL"})

        if not video_path or not video_path.is_file() or video_path.stat().st_size == 0:
            add("file_existence", "File video render", "Chưa có video render", "File MP4 thực tế", None)
            return FinalQCReport(overall_status="NOT_RUN", resolution="N/A", fps=0,
                                 video_codec="NONE", audio_codec="NONE", checks_summary=checks)
        add("file_existence", "File video render", video_path.name, "File MP4 thực tế", True)
        try:
            probe = self._probe_video_file(video_path)
            streams = probe.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), {})
            audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
            width, height = int(video.get("width", 0)), int(video.get("height", 0))
            num, den = str(video.get("r_frame_rate", "0/1")).split("/")
            fps = float(num) / float(den)
            duration = float(probe.get("format", {}).get("duration") or 0)
            if not math.isfinite(duration) or not math.isfinite(fps):
                raise ValueError("Metadata video không hữu hạn")
        except Exception as exc:
            add("probe", "Đọc metadata", exc, "ffprobe thành công", False)
            return FinalQCReport(overall_status="FAIL", resolution="N/A", fps=0,
                                 video_codec="NONE", audio_codec="NONE", checks_summary=checks)

        add("resolution", "Độ phân giải", f"{width}x{height}", "1920x1080", (width, height) == (1920, 1080))
        add("framerate", "Tốc độ khung hình", f"{fps:.3f} fps", "30 fps", 29.9 <= fps <= 30.1)
        add("codec", "Định dạng nén", f"{video.get('codec_name')} / {audio.get('codec_name', 'NONE')}",
            "H.264/AAC", video.get("codec_name") == "h264" and audio.get("codec_name") == "aac")
        audio_count = len([s for s in streams if s.get("codec_type") == "audio"])
        add("audio_stream", "Giọng đọc trong video", audio_count, "1 audio stream", audio_count == 1)
        add("duration", "Thời lượng", duration, "> 0s", duration > 0)

        sync = None
        try:
            vs, aus = float(video["start_time"]), float(audio["start_time"])
            ve, ae = vs + float(video["duration"]), aus + float(audio["duration"])
            sync = max(abs(vs - aus), abs(ve - ae)) * 1000
            if not math.isfinite(sync):
                raise ValueError("A/V duration invalid")
            add("av_sync", "Độ lệch A/V đầu và cuối", f"{sync:.3f} ms", "≤ 20 ms", sync <= 20)
        except (KeyError, ValueError, TypeError):
            add("av_sync", "Độ lệch A/V", "Thiếu metadata thời gian stream", "≤ 20 ms", None)

        lufs = peak = black = None
        if audio and video:
            try:
                signal = self._inspect_signal(video_path)
                lufs, peak, black = signal["lufs"], signal["true_peak"], bool(signal["black_gaps"])
                add("loudness", "Âm lượng tích hợp", f"{lufs} LUFS", "-18 đến -14 LUFS", -18 <= lufs <= -14)
                add("true_peak", "Đỉnh âm", f"{peak} dBTP", "≤ -1.0 dBTP", peak <= -1)
                add("black_gap", "Khoảng đen", len(signal["black_gaps"]), "0 khoảng đen ≥ 0.5s", not black)
            except Exception as exc:
                logger.warning("QC signal measurement failed: %s", exc)
                add("signal_measurement", "Đo âm thanh/hình ảnh", exc, "ffmpeg đo thành công", False)

        missing = static = None
        try:
            evidence = json.loads(video_path.with_suffix(".studio_render.json").read_text(encoding="utf-8"))
            if evidence.get("video_sha256") != file_sha256(video_path):
                raise ValueError("Chứng cứ render không thuộc video hiện tại")
            from studio.backend.services.audio_service import AudioService
            binding = AudioService().require_current_audio(project_id)
            plan_path, audio_path = Path(evidence["visual_plan_path"]), Path(evidence["audio_path"])
            if (evidence.get("project_id") != project_id
                    or evidence.get("visual_plan_sha256") != file_sha256(plan_path)
                    or evidence.get("audio_sha256") != file_sha256(audio_path)):
                raise ValueError("Nguồn render đã thay đổi")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if plan.get("source_script_content_hash") != binding["script_content_hash"]:
                raise ValueError("Script đã thay đổi sau lần render")
            expected, rendered = evidence["expected_scene_ids"], evidence["rendered_scene_ids"]
            missing = len(set(expected) - set(rendered))
            add("scenes_coverage", "Độ phủ cảnh", f"{missing} cảnh thiếu", "Đủ cảnh, không trùng ID",
                bool(expected) and missing == 0 and len(rendered) == len(set(rendered)) == len(expected))
            longest = float(evidence["longest_accidental_static_hold_sec"])
            if not math.isfinite(longest):
                raise ValueError("Phép đo static hold không hợp lệ")
            static = longest > 2
            add("static_hold", "Ảnh đứng ngoài ý đồ", f"{longest}s", "≤ 2s", not static)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            has_evidence = video_path.with_suffix(".studio_render.json").is_file()
            add("render_evidence", "Độ phủ cảnh / static hold", str(exc) if has_evidence else "Chưa có chứng cứ render cho video này",
                "Render qua Studio, nguồn còn hiện hành", False if has_evidence else None)

        overall = "FAIL" if any(c["status"] == "FAIL" for c in checks) else (
            "WARNING" if any(c["status"] == "NOT_RUN" for c in checks) else "PASS")
        return FinalQCReport(overall_status=overall, duration_sec=duration, resolution=f"{width}x{height}",
                             fps=round(fps), video_codec=str(video.get("codec_name", "NONE")),
                             audio_codec=str(audio.get("codec_name", "NONE")), av_sync_delta_ms=sync,
                             black_gap_detected=black, missing_scenes_count=missing, static_hold_exceeded=static,
                             integrated_loudness_lufs=lufs, true_peak_db=peak, checks_summary=checks)
