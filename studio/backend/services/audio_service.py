"""Audio services backed by the existing VieNeu production engine."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = BASE_DIR / "src"
VENV_SITE = BASE_DIR / ".venv" / "Lib" / "site-packages"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.append(str(VENV_SITE))

from apps.production_story import build_master_audio, generate_single_segment_takes, get_all_available_voices
from studio.backend.services.artifact_lineage import require_current_full_script
from studio.backend.services.artifact_files import file_sha256
from studio.backend.services.audio_timing import measure_segment_timeline

PROJECTS_DIR = BASE_DIR / "projects"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"
logger = logging.getLogger('SCCStudio.AudioService')

PROFILE_SPEEDS = {
    "HOOK": 0.98,
    "NORMAL": 1.01,
    "MYSTERY": 0.96,
    "REVEAL": 0.92,
    "COMMENT": 1.025,
    "ENDING": 0.965,
}

VOICE_ALIASES: Dict[str, str] = {
    "binh": "020",
    "minh": "020",
    "mc minh": "020",
    "mc_minh": "020",
    "thanh binh": "020",
    "thanh bình": "020",
    "020": "020",
}


def normalize_voice_id(voice_id: Optional[str]) -> str:
    """Normalizes host/voice aliases (e.g., 'Binh', 'MINH', 'MC Minh') to canonical voice ID '020'."""
    if not voice_id or not str(voice_id).strip():
        return "020"
    cleaned = str(voice_id).strip().lower()
    return VOICE_ALIASES.get(cleaned, str(voice_id).strip())


def normalize_script_segment(
    raw: Dict[str, Any],
    index: int,
    voice_id: str = "020",
    contextual_speed: bool = True,
    global_speed: float = 1.0,
) -> Dict[str, Any]:
    """Normalizes both legacy and new Full MC Script segments into Audio pipeline format."""
    seg = dict(raw)
    raw_id = seg.get("id") or seg.get("segment_id") or str(index + 1)
    match = re.search(r"\d+", str(raw_id))
    if match:
        seg_id = str(int(match.group(0))).zfill(3)
    else:
        seg_id = str(index + 1).zfill(3)
    seg["id"] = seg_id
    seg["segment_id"] = seg_id

    speaker = str(seg.get("speaker") or "MINH").strip()
    if speaker.upper() in ("NARRATOR", "HOST", "MC", "MC MINH", "MC_MINH"):
        speaker = "MINH"
    seg["speaker"] = speaker
    seg["voice"] = normalize_voice_id(voice_id)

    prof = str(seg.get("delivery_profile") or "NORMAL").upper()
    seg["delivery_profile"] = prof

    if contextual_speed:
        seg_speed = seg.get("speed")
        if seg_speed is not None and str(seg_speed).strip() != "":
            try:
                speed = float(seg_speed)
            except Exception:
                speed = PROFILE_SPEEDS.get(prof, 1.0)
        else:
            speed = PROFILE_SPEEDS.get(prof, 1.0)
    else:
        speed = max(0.88, min(1.05, float(global_speed)))
    seg["speed"] = max(0.88, min(1.05, speed))

    seg["pause_before"] = float(seg.get("pause_before", 0.05) or 0.0)
    seg["pause_after"] = float(seg.get("pause_after", 0.25) or 0.25)
    seg["text"] = str(seg.get("text", "")).strip()
    seg["importance"] = str(seg.get("importance") or "normal").lower()
    if "music_cue" not in seg:
        seg["music_cue"] = "none"

    return seg


class AudioService:
    normalize_voice_id = staticmethod(normalize_voice_id)
    normalize_script_segment = staticmethod(normalize_script_segment)

    def __init__(self):
        self._engine: Any = None
        self._engine_lock = threading.Lock()

    def _project_audio_dir(self, project_id: str) -> Path:
        return PROJECTS_DIR / project_id / "audio"

    def require_current_audio(self, project_id: str) -> Dict[str, Any]:
        lineage = require_current_full_script(project_id, PROJECTS_DIR)
        audio_dir = self._project_audio_dir(project_id)
        try:
            report = json.loads((audio_dir / "generation_report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ValueError("Audio STALE: chưa có chứng cứ audio thuộc kịch bản hiện tại; cần tạo/import lại")
        if (report.get("status") != "COMPLETE" or not report.get("full_episode")
                or report.get("script_content_hash") != lineage["script_content_hash"]
                or report.get("story_content_hash") != lineage["story_content_hash"]
                or report.get("script_generation_request_id") != lineage["generation_request_id"]
                or report.get("story_generation_request_id") != lineage["story_generation_request_id"]):
            raise ValueError("Audio STALE: audio không thuộc toàn bộ kịch bản/Story Bible hiện tại")
        dry = Path(report.get("narration_path", ""))
        if not dry.is_file() or not report.get("narration_sha256") or file_sha256(dry) != report["narration_sha256"]:
            raise ValueError("Audio STALE: file narration đã thay đổi hoặc không còn tồn tại")
        if report.get("mix_sha256"):
            final = audio_dir / "final_mix.wav"
            if not final.is_file() or file_sha256(final) != report["mix_sha256"]:
                raise ValueError("Audio STALE: bản mix đã thay đổi; cần hòa âm lại")
        return report

    def get_measured_timing(self, project_id: str) -> List[Dict[str, Any]]:
        report = self.require_current_audio(project_id)
        path = self._project_audio_dir(project_id) / "segment_timing.json"
        if not path.is_file() or file_sha256(path) != report.get("timing_sha256"):
            raise ValueError("Timing STALE: cần tạo lại narration hoặc cung cấp timing đã đo cho audio import")
        events = json.loads(path.read_text(encoding="utf-8"))
        script = json.loads(self._script_path(project_id).read_text(encoding="utf-8"))
        ids = [normalize_script_segment(s, i)["id"] for i, s in enumerate(script["segments"])]
        if not isinstance(events, list) or [e.get("id") for e in events] != ids:
            raise ValueError("Timing không khớp ID/thứ tự phân đoạn hiện tại")
        if any(e.get("timing_source") != "MEASURED_WAV" for e in events):
            raise ValueError("Timing đang là ước tính, cần đo từ WAV thật")
        return events

    def _script_path(self, project_id: str) -> Optional[Path]:
        path = PROJECTS_DIR / project_id / "script" / "full_script.json"
        return path if path.exists() else None

    def get_audio_stem_path(self, project_id: str, stem: str = "final") -> Optional[Path]:
        stem = (stem or "final").lower().strip()
        project_audio = self._project_audio_dir(project_id)
        is_legacy = project_id in {"EP003", "EP011"}
        legacy_audio = (PILOT_03_AUDIO / project_id) if is_legacy else None
        try:
            binding = json.loads((project_audio / "generation_report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            binding = {}
        if binding.get("status") == "COMPLETE":
            if stem == "music" and not binding.get("mix_sha256"):
                return None
            if stem == "final" and not binding.get("mix_sha256"):
                dry = Path(binding.get("narration_path", ""))
                if dry.is_file():
                    return dry

        if stem == "music":
            music_candidates = [
                project_audio / "music_mix.wav",
                project_audio / "master" / "music_mix.wav",
                project_audio / "mix" / "music_mix.wav",
            ]
            if legacy_audio and legacy_audio.exists():
                music_candidates.extend([
                    legacy_audio / "audio" / "music_mix.wav",
                    legacy_audio / "master" / "music_mix.wav",
                    legacy_audio / "music_mix.wav",
                ])
            for c in music_candidates:
                if c.exists():
                    return c
            return None

        if stem == "dry":
            dry_candidates = [
                project_audio / "narration_dry.wav",
                project_audio / "narration_dry.mp3",
                project_audio / "narration.wav",
                project_audio / "narration.mp3",
                project_audio / "tts" / "master" / "voice_master.wav",
                project_audio / "tts" / "narration.wav",
                project_audio / f"{project_id}_imported_master.wav",
                project_audio / f"{project_id}_imported_master.mp3",
            ]
            if legacy_audio and legacy_audio.exists():
                dry_candidates.extend([
                    legacy_audio / "audio" / "narration_dry.wav",
                    legacy_audio / "audio" / "narration_dry.mp3",
                    legacy_audio / "narration_dry.wav",
                    legacy_audio / "narration_dry.mp3",
                    legacy_audio / "narration.wav",
                    legacy_audio / "master" / "voice_master.wav",
                ])
            for c in dry_candidates:
                if c.exists():
                    return c
            return None

        # stem == "final"
        # 1. Check if narration is newer than final_mix (narration was regenerated)
        dry_path = self.get_audio_stem_path(project_id, stem="dry")
        final_file = project_audio / "final_mix.wav"
        if final_file.exists() and dry_path and dry_path.exists():
            if dry_path.stat().st_mtime > final_file.stat().st_mtime:
                # Narration was updated AFTER final_mix was rendered! Prioritize fresh narration.
                return dry_path

        final_candidates = [
            project_audio / "final_mix.wav",
            project_audio / "final_mix.mp3",
            project_audio / "master" / "final_mix.wav",
            project_audio / "master" / "final_mix.mp3",
            project_audio / "narration.wav",
            project_audio / "narration.mp3",
            project_audio / "narration_dry.wav",
            project_audio / "narration_dry.mp3",
            project_audio / f"{project_id}_imported_master.wav",
            project_audio / f"{project_id}_imported_master.mp3",
            project_audio / f"{project_id}_imported_master.m4a",
        ]
        if legacy_audio and legacy_audio.exists():
            final_candidates.extend([
                legacy_audio / "audio" / "final_mix.wav",
                legacy_audio / "audio" / "final_mix.mp3",
                legacy_audio / "final_mix.wav",
                legacy_audio / "final_mix.mp3",
                legacy_audio / "master" / "final_mix.wav",
                legacy_audio / "master" / "final_mix.mp3",
                legacy_audio / f"{project_id}_audio_formula_v1_master.wav",
                legacy_audio / "audio_master" / "final_mix.wav",
                legacy_audio / "narration.wav",
                legacy_audio / "narration_dry.wav",
                legacy_audio / "master.wav",
            ])

        for candidate in final_candidates:
            if candidate.exists():
                return candidate
        if project_audio.exists():
            masters = sorted(project_audio.rglob("*final_mix*.wav")) + sorted(project_audio.rglob("*master*.wav")) + sorted(project_audio.glob("*.wav"))
            if masters:
                return masters[0]
        return None

    def get_audio_master_path(self, project_id: str) -> Optional[Path]:
        return self.get_audio_stem_path(project_id, stem="final")

    def _probe_audio(self, path: Path) -> Dict[str, Any]:
        try:
            import soundfile as sf
            info = sf.info(str(path))
            return {"duration_sec": float(info.duration), "sample_rate": int(info.samplerate), "channels": int(info.channels)}
        except Exception:
            return {"duration_sec": 0.0, "sample_rate": 0, "channels": 0}

    def get_audio_info(self, project_id: str) -> Dict[str, Any]:
        master = self.get_audio_master_path(project_id)
        project_audio = self._project_audio_dir(project_id)
        legacy_audio = PILOT_03_AUDIO / project_id

        has_final = self.get_audio_stem_path(project_id, "final") is not None
        has_dry = self.get_audio_stem_path(project_id, "dry") is not None
        has_music = self.get_audio_stem_path(project_id, "music") is not None

        from studio.backend.services.artifact_lineage import validate_full_script
        lineage = validate_full_script(project_id, PROJECTS_DIR)
        try:
            self.require_current_audio(project_id)
            audio_current, audio_reason = True, None
        except ValueError as exc:
            audio_current, audio_reason = False, str(exc)

        if not master:
            return {
                "available": False,
                "audio_current": False, "audio_stale_reason": audio_reason,
                "duration_sec": 0.0,
                "sample_rate": 0,
                "channels": 0,
                "format": "None",
                "file_path": None,
                "waveform_peaks": [0.1] * 100,
                "markers": [],
                "has_bgm": False,
                "bgm_info": None,
                "stems": {"final": False, "dry": False, "music": False},
                "audio_gate_allowed": lineage.get("audio_gate_allowed", False),
                "audio_gate_reason": lineage.get("audio_gate_reason"),
                "script_lineage": lineage,
            }
        metadata = self._probe_audio(master)
        duration = metadata["duration_sec"]

        cue_sheet_candidates = [
            project_audio / "music_cue_sheet.json",
            project_audio / "mix" / "cue_sheet.json",
            legacy_audio / "audio" / "music_cue_sheet.json",
            legacy_audio / "music_cue_sheet.json",
            legacy_audio / "mix" / "cue_sheet.json",
        ]
        cue_sheet_path = next((p for p in cue_sheet_candidates if p.exists()), None)
        cue_sheet_data = []
        if cue_sheet_path:
            try:
                cue_sheet_data = json.loads(cue_sheet_path.read_text(encoding="utf-8"))
            except Exception:
                cue_sheet_data = []

        mix_report_candidates = [
            project_audio / "mix" / "mix_report.json",
            project_audio / "mix_report.json",
            legacy_audio / "mix" / "mix_report.json",
            legacy_audio / "production_report.json",
        ]
        mix_report_path = next((p for p in mix_report_candidates if p.exists()), None)
        mix_report_data = {}
        if mix_report_path:
            try:
                mix_report_data = json.loads(mix_report_path.read_text(encoding="utf-8"))
            except Exception:
                mix_report_data = {}

        has_bgm = bool(
            has_music or (cue_sheet_data and any(c.get("cue", "").upper() not in ["DRY", "NONE"] for c in cue_sheet_data))
        )

        bgm_info = None
        if has_bgm and cue_sheet_data:
            from apps.music_engine import calculate_music_coverage
            cov = calculate_music_coverage(cue_sheet_data, duration)
            music_cues_summary = [
                {
                    "cue": c.get("cue", "DRY").upper(),
                    "start_sec": round(float(c.get("start_sec", 0.0)), 2),
                    "end_sec": round(float(c.get("end_sec", 0.0)), 2),
                    "duration_sec": round(float(c.get("duration_sec", 0.0)), 2),
                    "track": c.get("track", ""),
                    "level_db": c.get("level_db", -35.0),
                }
                for c in cue_sheet_data
            ]
            bgm_vol = 0.0
            if "bgm_volume_db" in mix_report_data:
                bgm_vol = float(mix_report_data["bgm_volume_db"])
            else:
                config_path = project_audio / "mix_config.json"
                if config_path.exists():
                    try:
                        cfg = json.loads(config_path.read_text(encoding="utf-8"))
                        bgm_vol = float(cfg.get("bgm_volume_db") or 0.0)
                    except Exception:
                        pass

            bgm_info = {
                "coverage_percent": cov.get("coverage_percent", 0.0),
                "music_duration_sec": cov.get("music_duration_sec", 0.0),
                "music_duration_fmt": cov.get("music_duration_fmt", ""),
                "dry_duration_sec": cov.get("dry_duration_sec", 0.0),
                "dry_duration_fmt": cov.get("dry_duration_fmt", ""),
                "target_recommendation": cov.get("target_recommendation", "30% – 38%"),
                "is_high_coverage": cov.get("is_high_coverage", False),
                "ducking_enabled": mix_report_data.get("ducking_enabled", True),
                "bgm_volume_db": bgm_vol,
                "master_integrated_lufs": mix_report_data.get("master_integrated_lufs"),
                "master_true_peak_db": mix_report_data.get("master_true_peak_db"),
                "cues": music_cues_summary,
            }

        markers = []
        if cue_sheet_data:
            for item in cue_sheet_data:
                cue = item.get("cue", "").upper()
                if cue not in ["DRY", "NONE", "NO_MUSIC"]:
                    markers.append({
                        "label": f"{cue} ({item.get('track', '')})",
                        "time_sec": round(float(item.get("start_sec", 0.0)), 2),
                        "type": cue,
                    })
        if not markers:
            markers = [
                {"label": "Hook", "time_sec": 0.0, "type": "INTRO"},
                {"label": "Phát hiện", "time_sec": round(duration * 0.25, 2), "type": "DEVELOPMENT"},
                {"label": "Reveal 1", "time_sec": round(duration * 0.65, 2), "type": "REVEAL_1"},
                {"label": "Reveal 2", "time_sec": round(duration * 0.85, 2), "type": "REVEAL_2"},
                {"label": "Kết luận", "time_sec": round(duration * 0.95, 2), "type": "OUTRO"},
            ]

        return {
            "available": True,
            "audio_current": audio_current, "audio_stale_reason": audio_reason,
            "duration_sec": round(duration, 3),
            "sample_rate": metadata["sample_rate"],
            "channels": metadata["channels"],
            "format": master.suffix.lstrip(".").upper(),
            "file_path": str(master),
            "waveform_peaks": self._generate_peaks(duration, audio_path=master),
            "markers": markers,
            "has_bgm": has_bgm,
            "bgm_info": bgm_info,
            "stems": {
                "final": has_final,
                "dry": has_dry,
                "music": has_music,
            },
            "audio_gate_allowed": lineage.get("audio_gate_allowed", False),
            "audio_gate_reason": lineage.get("audio_gate_reason"),
            "script_lineage": lineage,
        }

    def _generate_peaks(self, duration: float, count: int = 120, audio_path: Optional[Path] = None) -> List[float]:
        if audio_path and audio_path.exists():
            try:
                import soundfile as sf
                import numpy as np
                data, sr = sf.read(str(audio_path), dtype="float32")
                if data.ndim > 1:
                    data = np.mean(data, axis=1)
                total_samples = len(data)
                if total_samples > 0:
                    samples_per_bin = max(1, total_samples // count)
                    peaks = []
                    for i in range(count):
                        start_idx = i * samples_per_bin
                        end_idx = min(total_samples, start_idx + samples_per_bin)
                        if start_idx < total_samples:
                            chunk = data[start_idx:end_idx]
                            val = float(np.max(np.abs(chunk))) if len(chunk) > 0 else 0.05
                            peaks.append(round(min(1.0, max(0.05, val)), 3))
                        else:
                            peaks.append(0.05)
                    return peaks
            except Exception:
                pass
        return [0.05] * count

    def list_voices(self) -> Dict[str, Any]:
        saved_ids = set()
        voice_home = Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu"))
        for filename in ("user_voices_v3_turbo.json", "user_voices_v3_nano.json"):
            path = voice_home / filename
            if path.exists():
                try:
                    saved_ids.update((json.loads(path.read_text(encoding="utf-8")).get("presets") or {}).keys())
                except Exception:
                    pass
        all_voices = get_all_available_voices(None)
        voices = []
        found_020 = False
        for label, v_id in all_voices:
            if v_id == "020":
                found_020 = True
                voices.append({
                    "label": "⭐ MC Minh (Binh / 020) — Giọng dẫn chuyện Sau Cánh Cửa",
                    "voice_id": "020",
                    "cloned": True,
                })
            else:
                voices.append({
                    "label": label,
                    "voice_id": v_id,
                    "cloned": v_id in saved_ids,
                })
        if not found_020:
            voices.insert(0, {
                "label": "⭐ MC Minh (Binh / 020) — Giọng dẫn chuyện Sau Cánh Cửa",
                "voice_id": "020",
                "cloned": True,
            })
        voices.sort(key=lambda x: 0 if x["voice_id"] == "020" else 1)
        return {"voices": voices, "profile_speeds": PROFILE_SPEEDS}

    def import_audio_file(self, project_id: str, source: Path) -> Dict[str, Any]:
        lineage = require_current_full_script(project_id, PROJECTS_DIR)
        if not source.exists():
            raise FileNotFoundError(f"Không tìm thấy file audio: {source}")
        extension = source.suffix.lower()
        if extension not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
            raise ValueError("Chỉ hỗ trợ WAV, MP3, M4A, FLAC hoặc OGG")
        target_dir = self._project_audio_dir(project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / f"{project_id}_imported_master{extension}"
        shutil.copy2(source, destination)
        # Keep the imported narration separate from an older TTS dry stem.
        dry = target_dir / "narration_dry.wav"
        import subprocess
        decoded = target_dir / f"import-{uuid.uuid4().hex}.wav"
        try:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(destination),
                            "-vn", "-c:a", "pcm_s16le", str(decoded)], check=True, capture_output=True, timeout=300)
            decoded.replace(dry)
        finally:
            decoded.unlink(missing_ok=True)
        report = {"status": "COMPLETE", "full_episode": True, "origin": "IMPORTED",
                  "script_content_hash": lineage["script_content_hash"], "story_content_hash": lineage["story_content_hash"],
                  "script_generation_request_id": lineage["generation_request_id"],
                  "story_generation_request_id": lineage["story_generation_request_id"],
                  "narration_path": str(dry.resolve()), "narration_sha256": file_sha256(dry)}
        (target_dir / "generation_report.json").write_text(json.dumps(report), encoding="utf-8")
        return self.get_audio_info(project_id)

    def save_upload(self, project_id: str, filename: str, source: BinaryIO, purpose: str) -> Path:
        safe_name = Path(filename or "audio.wav").name
        extension = Path(safe_name).suffix.lower()
        if extension not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
            raise ValueError("File audio không đúng định dạng được hỗ trợ")
        target_dir = self._project_audio_dir(project_id) / purpose
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / safe_name
        with destination.open("wb") as output:
            shutil.copyfileobj(source, output)
        return destination

    def _get_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            import yaml
            from vieneu import Vieneu
            config = yaml.safe_load((BASE_DIR / "config.yaml").read_text(encoding="utf-8")) or {}
            turbo = (config.get("backbone_configs") or {}).get("VieNeu-TTS-v3-Turbo (new release)") or {}
            self._engine = Vieneu(
                mode="v3turbo", backbone_repo=turbo.get("repo", "pnnbao-ump/VieNeu-TTS-v3-Turbo"),
                device="auto", precision=turbo.get("precision", "int8"),
            )
            from apps.user_voices import load_user_voices
            load_user_voices(self._engine)
            return self._engine

    def clone_voice(self, project_id: str, name: str, description: str, filename: str, source: BinaryIO) -> Dict[str, Any]:
        sample_path = self.save_upload(project_id, filename, source, "voice_samples")
        from apps.user_voices import save_user_voice
        voice_id = save_user_voice(self._get_engine(), name, str(sample_path), denoise=True, description=description)
        return {"voice_id": voice_id, **self.list_voices()}

    def auto_mix_background_music(
        self, project_id: str, enable_ducking: bool = True, target_lufs: float = -14.0, bgm_volume_db: float = 0.0
    ) -> Dict[str, Any]:
        audio_binding = self.require_current_audio(project_id)
        from apps.music_engine import (
            generate_cue_sheet_from_segments,
            build_final_mix,
            calculate_music_coverage,
        )
        import soundfile as sf
        import subprocess

        project_audio = self._project_audio_dir(project_id)
        project_audio.mkdir(parents=True, exist_ok=True)

        # 1. Xác định voice audio mộc
        voice_path = Path(audio_binding["narration_path"])
        if not voice_path or not voice_path.exists():
            voice_path = self.get_audio_master_path(project_id)

        if not voice_path or not voice_path.exists():
            raise FileNotFoundError("Chưa có audio narration (giọng đọc). Vui lòng tạo TTS hoặc import file audio trước.")

        dry_target_wav = project_audio / "narration_dry.wav"
        if voice_path.suffix.lower() == ".wav":
            if voice_path.resolve() != dry_target_wav.resolve():
                shutil.copy2(voice_path, dry_target_wav)
            active_voice_path = dry_target_wav
        else:
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(voice_path),
                "-ar", "48000", "-ac", "1",
                str(dry_target_wav)
            ]
            subprocess.run(cmd, check=True)
            active_voice_path = dry_target_wav

        # 2. Đo thời lượng audio
        info = sf.info(str(active_voice_path))
        total_duration = float(info.duration)
        if total_duration <= 0.0:
            raise ValueError("File audio có thời lượng bằng 0.")

        # 3. Thu thập hoặc xây dựng timeline events
        timeline_events = self.get_measured_timing(project_id)
        # 4. Gán narrative music cue theo chuẩn Audio Formula V1
        annotated_events = []
        for ev in timeline_events:
            item = dict(ev)
            sid_num = 0
            try:
                sid_num = int(item["id"])
            except Exception:
                pass
            prof = str(item.get("delivery_profile", "NORMAL")).upper()
            importance = str(item.get("importance", "")).lower()

            if prof == "HOOK":
                item["music_cue"] = "signature_intro"
            elif prof == "REVEAL" or importance == "critical":
                item["music_cue"] = "none"
                item["delivery_profile"] = "REVEAL"
            elif prof == "MYSTERY":
                if 40 <= sid_num <= 75:
                    item["music_cue"] = "tension_low"
                else:
                    item["music_cue"] = "mystery_low"
            elif prof == "TENSION":
                item["music_cue"] = "tension_low"
            elif prof == "EMOTIONAL" or (sid_num >= 78 and prof in ["NORMAL", "COMMENT"]):
                item["music_obj"] = {"cue": "EMOTIONAL", "level_db": -36.0, "fade_in_sec": 2.0, "fade_out_sec": 2.5}
            elif prof == "ENDING":
                if sid_num >= 88:
                    item["music_cue"] = "signature_outro"
                else:
                    item["music_obj"] = {"cue": "REFLECTION", "level_db": -35.0, "fade_in_sec": 2.5, "fade_out_sec": 3.0}
            elif prof in ["NORMAL", "COMMENT"]:
                item["music_cue"] = "none"

            annotated_events.append(item)

        # 5. Xây dựng Cue Sheet (30-38% coverage, pre-reveal clearance 2.0s, post-reveal clearance 2.5s)
        cue_sheet = generate_cue_sheet_from_segments(
            timeline_events=annotated_events,
            pre_reveal_clearance=2.0,
            post_reveal_clearance=2.5,
            target_max_coverage=38.0,
            target_min_coverage=30.0,
            total_episode_sec=total_duration
        )

        # 6. Render & Master final mix (-14 LUFS, -1 dBTP, additive bgm_volume_db)
        ok, msg, mix_report = build_final_mix(
            project_dir=project_audio,
            voice_master_path=active_voice_path,
            cue_sheet=cue_sheet,
            timeline_events=annotated_events,
            enable_ducking=enable_ducking,
            ducking_db=-2.5,
            target_lufs=target_lufs,
            true_peak_db=-1.0,
            sample_rate=48000,
            bgm_volume_db=bgm_volume_db,
        )
        if not ok:
            raise RuntimeError(f"Hòa âm BGM thất bại: {msg}")

        # Save mix config
        mix_config = {
            "enable_ducking": enable_ducking,
            "target_lufs": target_lufs,
            "bgm_volume_db": bgm_volume_db,
            "updated_at": time.time(),
        }
        (project_audio / "mix_config.json").write_text(
            json.dumps(mix_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 7. Đồng bộ ra thư mục gốc của audio
        master_dir = project_audio / "master"
        mix_dir = project_audio / "mix"

        if (master_dir / "final_mix.wav").exists():
            shutil.copy2(master_dir / "final_mix.wav", project_audio / "final_mix.wav")
        if (master_dir / "final_mix.mp3").exists():
            shutil.copy2(master_dir / "final_mix.mp3", project_audio / "final_mix.mp3")
        if (master_dir / "music_mix.wav").exists():
            shutil.copy2(master_dir / "music_mix.wav", project_audio / "music_mix.wav")
        if (mix_dir / "cue_sheet.json").exists():
            shutil.copy2(mix_dir / "cue_sheet.json", project_audio / "music_cue_sheet.json")

        (project_audio / "segment_timing.json").write_text(
            json.dumps(timeline_events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        audio_binding["timing_sha256"] = file_sha256(project_audio / "segment_timing.json")
        audio_binding["mix_sha256"] = file_sha256(project_audio / "final_mix.wav")
        audio_binding["mix_config"] = mix_config
        (project_audio / "generation_report.json").write_text(json.dumps(audio_binding, ensure_ascii=False, indent=2), encoding="utf-8")

        return self.get_audio_info(project_id)

    def generate_narration(
        self,
        project_id: str,
        voice_id: str,
        contextual_speed: bool = True,
        global_speed: float = 1.0,
        enable_music: bool = True,
        segment_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        lineage = require_current_full_script(project_id, PROJECTS_DIR)
        voice_id = normalize_voice_id(voice_id)
        available_voice_ids = {voice["voice_id"] for voice in self.list_voices()["voices"]}
        if voice_id not in available_voice_ids and voice_id not in VOICE_ALIASES.values():
            raise ValueError(f"Giọng '{voice_id}' không tồn tại")
        script_path = self._script_path(project_id)
        if not script_path:
            raise FileNotFoundError("Chưa có kịch bản để tạo audio")
        script_data = json.loads(script_path.read_text(encoding="utf-8"))
        raw_segments = script_data.get("segments", script_data if isinstance(script_data, list) else [])
        if not raw_segments:
            raise ValueError("Kịch bản không có phân đoạn")
        if segment_ids:
            wanted = {
                str(int(match.group(0))).zfill(3) if (match := re.search(r"\d+", str(value))) else str(value)
                for value in segment_ids
            }
            raw_segments = [
                segment for index, segment in enumerate(raw_segments)
                if (
                    str(int(match.group(0))).zfill(3)
                    if (match := re.search(r"\d+", str(segment.get("id") or segment.get("segment_id") or index + 1)))
                    else str(segment.get("id") or segment.get("segment_id") or index + 1)
                ) in wanted
            ]
            if not raw_segments:
                raise ValueError("Không tìm thấy phân đoạn được yêu cầu trong Full Script hiện tại")

        audio_dir = self._project_audio_dir(project_id)
        preview = bool(segment_ids)
        run_id = uuid.uuid4().hex
        work_dir = (audio_dir / "previews" / run_id / "tts") if preview else (audio_dir / "tts")
        work_dir.mkdir(parents=True, exist_ok=True)
        logger.info('Khởi tạo VieNeu thật, voice %s; %s phân đoạn', voice_id, len(raw_segments))
        engine = self._get_engine()
        project_state: Dict[str, Any] = {"segments": {}}
        generated_segments = []
        for index, original in enumerate(raw_segments):
            segment = normalize_script_segment(
                original, index, voice_id=voice_id,
                contextual_speed=contextual_speed, global_speed=global_speed
            )
            char_config = {
                "char_id": segment["speaker"],
                "display_name": "MC Minh" if segment["speaker"] == "MINH" else segment["speaker"],
                "voice": voice_id,
                "default_speed": segment["speed"],
            }
            ok, message, result = generate_single_segment_takes(
                engine, work_dir, segment, char_config
            )
            if not ok:
                raise RuntimeError(f"Lỗi tạo audio cho phân đoạn {segment['id']}: {message}")
            logger.info('Đã tạo WAV phân đoạn %s (%s/%s), tốc độ %.3fx',
                        segment['id'], index + 1, len(raw_segments), segment['speed'])
            project_state["segments"][segment["id"]] = result
            generated_segments.append(segment)

        (work_dir / "project_state.json").write_text(json.dumps(project_state, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info('Ghép master và đo thời gian từng WAV')
        ok, message, wav_output, _ = build_master_audio(
            project_dir=work_dir, segments=generated_segments, project_state=project_state,
            enable_music=False, enable_room_tone=False,
            sample_rate=int(getattr(engine, "sample_rate", 48000)),
        )
        if not ok or not wav_output:
            raise RuntimeError(message or "Không ghép được audio master")
        import soundfile as sf
        source_master = Path(wav_output)
        master_info = sf.info(source_master)
        timing, total_frames = measure_segment_timeline(work_dir, generated_segments, project_state, master_info.samplerate)
        if abs(total_frames - master_info.frames) > 1:
            raise ValueError("Master không khớp timeline WAV đã đo; dừng để tránh Visual/BGM sai timing")
        if preview:
            return {"available": True, "preview": True, "file_path": str(source_master),
                    "duration_sec": master_info.duration,
                    "generation": {"segments": len(generated_segments), "full_episode": False,
                                   "requested_segment_ids": segment_ids, "voice_id": voice_id}}
        # Validate before replacing any previously published master or stem.
        current = require_current_full_script(project_id, PROJECTS_DIR)
        if current["script_content_hash"] != lineage["script_content_hash"] or current["story_content_hash"] != lineage["story_content_hash"]:
            raise ValueError("Kịch bản thay đổi trong lúc tạo audio; output không được duyệt")
        master_path = self._project_audio_dir(project_id) / "narration.wav"
        source_master = Path(wav_output)
        if source_master.resolve() != master_path.resolve():
            shutil.copy2(source_master, master_path)

        # Chép sang narration_dry.wav để phục vụ stem voice mộc
        dry_path = self._project_audio_dir(project_id) / "narration_dry.wav"
        shutil.copy2(master_path, dry_path)

        report = {
            "status": "COMPLETE", "full_episode": True, "origin": "VIENEU",
            "project_id": project_id, "voice_id": voice_id, "contextual_speed": contextual_speed,
            "global_speed": global_speed, "enable_music": enable_music,
            "segments": len(generated_segments), "profile_speeds": PROFILE_SPEEDS,
            "requested_segment_ids": segment_ids or [],
            "script_generation_request_id": lineage["generation_request_id"],
            "story_generation_request_id": lineage["story_generation_request_id"],
            "script_content_hash": lineage["script_content_hash"], "story_content_hash": lineage["story_content_hash"],
            "narration_path": str(dry_path.resolve()), "narration_sha256": file_sha256(dry_path),
        }
        # Do not publish output if Script changed while synthesis was running.
        current = require_current_full_script(project_id, PROJECTS_DIR)
        if current["script_content_hash"] != report["script_content_hash"] or current["story_content_hash"] != report["story_content_hash"]:
            raise ValueError("Kịch bản thay đổi trong lúc tạo audio; output không được duyệt")
        timing_path = audio_dir / "segment_timing.json"
        timing_path.write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
        report["timing_sha256"] = file_sha256(timing_path)
        (self._project_audio_dir(project_id) / "generation_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if enable_music:
            try:
                config = json.loads((audio_dir / "mix_config.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                config = {}
            self.auto_mix_background_music(project_id, enable_ducking=config.get("enable_ducking", True),
                                           target_lufs=config.get("target_lufs", -14.0), bgm_volume_db=config.get("bgm_volume_db", 0.0))
        return {**self.get_audio_info(project_id), "generation": report}
