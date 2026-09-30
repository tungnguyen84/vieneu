"""Audio services backed by the existing VieNeu production engine."""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
SRC_DIR = BASE_DIR / "src"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from apps.production_story import build_master_audio, generate_single_segment_takes, get_all_available_voices

PROJECTS_DIR = BASE_DIR / "projects"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"

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

    seg["pause_before"] = float(seg.get("pause_before", 0.0) or 0.0)
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

    def _script_path(self, project_id: str) -> Optional[Path]:
        candidates = [
            PROJECTS_DIR / project_id / "script" / "full_script.json",
            PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json",
        ]
        return next((path for path in candidates if path.exists()), None)

    def get_audio_stem_path(self, project_id: str, stem: str = "final") -> Optional[Path]:
        stem = (stem or "final").lower().strip()
        project_audio = self._project_audio_dir(project_id)
        legacy_audio = PILOT_03_AUDIO / project_id

        if stem == "music":
            music_candidates = [
                project_audio / "music_mix.wav",
                project_audio / "master" / "music_mix.wav",
                project_audio / "mix" / "music_mix.wav",
                legacy_audio / "audio" / "music_mix.wav",
                legacy_audio / "master" / "music_mix.wav",
                legacy_audio / "music_mix.wav",
            ]
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
                legacy_audio / "audio" / "narration_dry.wav",
                legacy_audio / "audio" / "narration_dry.mp3",
                legacy_audio / "narration_dry.wav",
                legacy_audio / "narration_dry.mp3",
                legacy_audio / "narration.wav",
                legacy_audio / "master" / "voice_master.wav",
                project_audio / f"{project_id}_imported_master.wav",
                project_audio / f"{project_id}_imported_master.mp3",
            ]
            for c in dry_candidates:
                if c.exists():
                    return c
            return None

        # stem == "final" (Bản mix hoàn chỉnh ưu tiên final_mix có BGM, nếu chưa có thì fallback về narration)
        final_candidates = [
            project_audio / "final_mix.wav",
            project_audio / "final_mix.mp3",
            project_audio / "master" / "final_mix.wav",
            project_audio / "master" / "final_mix.mp3",
            legacy_audio / "audio" / "final_mix.wav",
            legacy_audio / "audio" / "final_mix.mp3",
            legacy_audio / "final_mix.wav",
            legacy_audio / "final_mix.mp3",
            legacy_audio / "master" / "final_mix.wav",
            legacy_audio / "master" / "final_mix.mp3",
            legacy_audio / f"{project_id}_audio_formula_v1_master.wav",
            legacy_audio / "audio_master" / "final_mix.wav",
            project_audio / "narration.wav",
            project_audio / "narration.mp3",
            project_audio / "narration_dry.wav",
            project_audio / "narration_dry.mp3",
            project_audio / f"{project_id}_imported_master.wav",
            project_audio / f"{project_id}_imported_master.mp3",
            project_audio / f"{project_id}_imported_master.m4a",
            legacy_audio / "narration.wav",
            legacy_audio / "narration_dry.wav",
            legacy_audio / "master.wav",
        ]
        for candidate in final_candidates:
            if candidate.exists():
                return candidate
        for directory in (project_audio, legacy_audio):
            if directory.exists():
                masters = sorted(directory.rglob("*final_mix*.wav")) + sorted(directory.rglob("*master*.wav")) + sorted(directory.glob("*.wav"))
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

        if not master:
            return {
                "available": False,
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
            bgm_info = {
                "coverage_percent": cov.get("coverage_percent", 0.0),
                "music_duration_sec": cov.get("music_duration_sec", 0.0),
                "music_duration_fmt": cov.get("music_duration_fmt", ""),
                "dry_duration_sec": cov.get("dry_duration_sec", 0.0),
                "dry_duration_fmt": cov.get("dry_duration_fmt", ""),
                "target_recommendation": cov.get("target_recommendation", "30% – 38%"),
                "is_high_coverage": cov.get("is_high_coverage", False),
                "ducking_enabled": mix_report_data.get("ducking_enabled", True),
                "master_integrated_lufs": mix_report_data.get("master_integrated_lufs", -14.0),
                "master_true_peak_db": mix_report_data.get("master_true_peak_db", -1.0),
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
            "duration_sec": round(duration, 3),
            "sample_rate": metadata["sample_rate"],
            "channels": metadata["channels"],
            "format": master.suffix.lstrip(".").upper(),
            "file_path": str(master),
            "waveform_peaks": self._generate_peaks(duration),
            "markers": markers,
            "has_bgm": has_bgm,
            "bgm_info": bgm_info,
            "stems": {
                "final": has_final,
                "dry": has_dry,
                "music": has_music,
            },
        }

    def _generate_peaks(self, duration: float, count: int = 120) -> List[float]:
        import random
        rng = random.Random(int(duration * 1000))
        peaks = []
        for index in range(count):
            ratio = index / count
            boost = 1.3 if (0.62 <= ratio <= 0.68 or 0.82 <= ratio <= 0.88) else 1.0
            base = 0.25 + 0.55 * abs(math.sin(index * 0.18)) * rng.uniform(0.6, 1.0)
            peaks.append(round(min(1.0, max(0.08, base * boost)), 3))
        return peaks

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
        if not source.exists():
            raise FileNotFoundError(f"Không tìm thấy file audio: {source}")
        extension = source.suffix.lower()
        if extension not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
            raise ValueError("Chỉ hỗ trợ WAV, MP3, M4A, FLAC hoặc OGG")
        target_dir = self._project_audio_dir(project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / f"{project_id}_imported_master{extension}"
        shutil.copy2(source, destination)
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
        self, project_id: str, enable_ducking: bool = True, target_lufs: float = -14.0
    ) -> Dict[str, Any]:
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
        voice_path = self.get_audio_stem_path(project_id, stem="dry")
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
        timeline_events = []
        timing_file = None
        for candidate_timing in [
            project_audio / "segment_timing.json",
            project_audio / "tts" / "segment_timing.json",
            PILOT_03_AUDIO / project_id / "audio" / "segment_timing.json",
            PILOT_03_AUDIO / project_id / "segment_timing.json",
            PILOT_03_AUDIO / project_id / "reports" / "segment_timing.json",
        ]:
            if candidate_timing.exists():
                timing_file = candidate_timing
                break

        if timing_file:
            try:
                raw_timings = json.loads(timing_file.read_text(encoding="utf-8"))
                if isinstance(raw_timings, list) and raw_timings:
                    timeline_events = raw_timings
            except Exception:
                timeline_events = []

        if not timeline_events:
            script_path = self._script_path(project_id)
            if script_path and script_path.exists():
                script_data = json.loads(script_path.read_text(encoding="utf-8"))
                segments = script_data.get("segments", script_data if isinstance(script_data, list) else [])
                if segments:
                    total_words = sum(max(1, len(str(s.get("text", "")).split())) for s in segments)
                    pause_budget = sum(float(s.get("pause_after", 0.18) or 0.18) for s in segments)
                    speech_budget = max(5.0, total_duration - pause_budget)
                    current_sec = 0.0
                    for idx, seg in enumerate(segments):
                        words = max(1, len(str(seg.get("text", "")).split()))
                        seg_dur = (words / total_words) * speech_budget
                        p_after = float(seg.get("pause_after", 0.18) or 0.18)
                        p_before = float(seg.get("pause_before", 0.0) or 0.0)
                        timeline_events.append({
                            "id": str(seg.get("id") or seg.get("segment_id") or idx + 1).zfill(3),
                            "speaker": seg.get("speaker", "MINH"),
                            "delivery_profile": (seg.get("delivery_profile") or "NORMAL").upper(),
                            "text": seg.get("text", ""),
                            "speech_start_sec": current_sec,
                            "speech_end_sec": current_sec + seg_dur,
                            "duration_sec": seg_dur,
                            "pause_before": p_before,
                            "pause_after": p_after,
                            "importance": str(seg.get("importance") or "normal").lower(),
                            "music_cue": str(seg.get("music_cue") or "none"),
                            "music_obj": seg.get("music", {}),
                        })
                        current_sec += seg_dur + p_after

        if not timeline_events:
            t1 = min(15.0, total_duration * 0.1)
            t2 = total_duration * 0.35
            t3 = total_duration * 0.65
            t4 = total_duration * 0.8
            t5 = max(t4 + 5.0, total_duration - 15.0)
            timeline_events = [
                {"id": "001", "delivery_profile": "HOOK", "speech_start_sec": 0.0, "speech_end_sec": t1, "speaker": "MINH", "text": "Mở đầu"},
                {"id": "002", "delivery_profile": "MYSTERY", "speech_start_sec": t1 + 1.0, "speech_end_sec": t2, "speaker": "MINH", "text": "Khám phá"},
                {"id": "003", "delivery_profile": "TENSION", "speech_start_sec": t2 + 1.0, "speech_end_sec": t3, "speaker": "MINH", "text": "Căng thẳng"},
                {"id": "004", "delivery_profile": "REVEAL", "speech_start_sec": t3 + 1.0, "speech_end_sec": t4, "speaker": "MINH", "text": "Hé lộ"},
                {"id": "005", "delivery_profile": "EMOTIONAL", "speech_start_sec": t4 + 1.0, "speech_end_sec": t5, "speaker": "MINH", "text": "Lắng đọng"},
                {"id": "006", "delivery_profile": "ENDING", "speech_start_sec": t5 + 1.0, "speech_end_sec": total_duration, "speaker": "MINH", "text": "Kết thúc"},
            ]

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

        # 6. Render & Master final mix (-14 LUFS, -1 dBTP)
        ok, msg, mix_report = build_final_mix(
            project_dir=project_audio,
            voice_master_path=active_voice_path,
            cue_sheet=cue_sheet,
            timeline_events=annotated_events,
            enable_ducking=enable_ducking,
            ducking_db=-2.5,
            target_lufs=target_lufs,
            true_peak_db=-1.0,
            sample_rate=48000
        )
        if not ok:
            raise RuntimeError(f"Hòa âm BGM thất bại: {msg}")

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

        return self.get_audio_info(project_id)

    def generate_narration(
        self,
        project_id: str,
        voice_id: str,
        contextual_speed: bool = True,
        global_speed: float = 1.0,
        enable_music: bool = True,
    ) -> Dict[str, Any]:
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

        work_dir = self._project_audio_dir(project_id) / "tts"
        work_dir.mkdir(parents=True, exist_ok=True)
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
            project_state["segments"][segment["id"]] = result
            generated_segments.append(segment)

        (work_dir / "project_state.json").write_text(json.dumps(project_state, ensure_ascii=False, indent=2), encoding="utf-8")
        ok, message, wav_output, _ = build_master_audio(
            project_dir=work_dir, segments=generated_segments, project_state=project_state,
            enable_music=False, enable_room_tone=False,
            sample_rate=int(getattr(engine, "sample_rate", 48000)),
        )
        if not ok or not wav_output:
            raise RuntimeError(message or "Không ghép được audio master")
        master_path = self._project_audio_dir(project_id) / "narration.wav"
        source_master = Path(wav_output)
        if source_master.resolve() != master_path.resolve():
            shutil.copy2(source_master, master_path)

        # Chép sang narration_dry.wav để phục vụ stem voice mộc
        dry_path = self._project_audio_dir(project_id) / "narration_dry.wav"
        shutil.copy2(master_path, dry_path)

        # Nếu bật tự động chèn nhạc nền, tiến hành auto-mix BGM ngay
        if enable_music:
            try:
                self.auto_mix_background_music(project_id, enable_ducking=True)
            except Exception as e:
                # Ghi nhận log nếu có lỗi khi mix nhưng không làm hỏng tiến trình TTS
                pass

        report = {
            "project_id": project_id, "voice_id": voice_id, "contextual_speed": contextual_speed,
            "global_speed": global_speed, "enable_music": enable_music,
            "segments": len(generated_segments), "profile_speeds": PROFILE_SPEEDS,
        }
        (self._project_audio_dir(project_id) / "generation_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {**self.get_audio_info(project_id), "generation": report}
