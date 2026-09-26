"""
Audio Director Engine cho Production Storytelling (VieNeu-TTS).
==============================================================
Hỗ trợ đầy đủ JSON V6 "Sau Cánh Cửa" và pipeline TTS Audio Director chuyên nghiệp:
- Safe ZIP Extract (chống Zip Slip, kiểm duyệt extension an toàn).
- Music Library Management (quản lý 8 cues, volume, loop, status).
- Continuous Room Tone Engine (loop không restart, 50-100ms crossfade chống click, không bị ducking).
- Music Region Segmentation (KHÔNG restart nhạc giữa các segment cùng cue, crossfade khi đổi cue).
- Fade Out & Silence trước Critical Reveals (đoạn "Ngày mất", "mười bốn năm trước", "Là cậu ruột tôi").
- Smooth Dialogue Ducking (Attack: 120ms, Release: 600ms, ducking_db theo segment/global).
- Stems Export (dialogue_only, room_tone, music_only, pre_master_mix, episode_master WAV+MP3).
- Music Timeline JSON export để trực quan hóa và debug timeline.
- Preview Mix 30s & Preview Critical Reveal.
- Tách biệt 100% giữa Voice Cache và Mix Cache (đổi nhạc KHÔNG regenerate TTS).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf

logger = logging.getLogger("VieNeu.AudioDirector")

# Các định dạng file an toàn cho Music Pack
ALLOWED_ZIP_EXTENSIONS = {".json", ".wav", ".mp3", ".flac", ".txt", ".md"}

# Default cues nếu chưa có
DEFAULT_V6_CUES = [
    "signature_intro",
    "signature_outro",
    "mystery_low",
    "memory_soft",
    "tension_low",
    "emotional_low",
    "closing_soft",
    "room_tone"
]


def safe_extract_zip(zip_source: Union[str, Path, Any], target_dir: Path) -> Tuple[bool, str, Optional[Path], Optional[Path]]:
    """
    Giải nén ZIP an toàn:
    - Chống Zip Slip / Path Traversal (kiểm tra resolve path nằm trọn trong target_dir).
    - Chỉ cho phép các extension an toàn (.json, .wav, .mp3, .flac, .txt, .md).
    - Tìm và trả về đường dẫn tới file JSON chính và thư mục music/.
    """
    try:
        target_dir = Path(target_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        zip_path = None
        if hasattr(zip_source, "name"):
            zip_path = Path(zip_source.name)
        elif isinstance(zip_source, (str, Path)):
            zip_path = Path(zip_source)

        if not zip_path or not zip_path.exists():
            return False, f"File ZIP không tồn tại: {zip_path}", None, None

        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for member in zf.infolist():
                # Chống Zip Slip
                member_path = Path(member.filename)
                if member_path.is_absolute() or ".." in member_path.parts:
                    return False, f"Cảnh báo bảo mật: File ZIP chứa đường dẫn nguy hiểm ({member.filename})", None, None

                dest_file = (target_dir / member_path).resolve()
                if not str(dest_file).startswith(str(target_dir)):
                    return False, f"Cảnh báo bảo mật: File trỏ ra ngoài thư mục đích ({member.filename})", None, None

                # Kiểm tra extension cho các file thường
                if not member.is_dir():
                    ext = dest_file.suffix.lower()
                    if ext and ext not in ALLOWED_ZIP_EXTENSIONS:
                        return False, f"File ZIP chứa định dạng không được phép: {ext}", None, None

            # Giải nén
            zf.extractall(path=str(target_dir))

        # Tìm file JSON chính trong thư mục vừa giải nén
        json_candidates = list(target_dir.glob("*.json"))
        if not json_candidates:
            # Tìm sâu hơn 1 cấp
            json_candidates = list(target_dir.glob("*/*.json"))

        found_json: Optional[Path] = None
        if json_candidates:
            # Ưu tiên file có v6 hoặc có dung lượng lớn nhất
            v6_match = [p for p in json_candidates if "v6" in p.name.lower()]
            found_json = v6_match[0] if v6_match else max(json_candidates, key=lambda p: p.stat().st_size)

        # Tìm thư mục music/
        music_candidates = [target_dir / "music"]
        for d in target_dir.iterdir():
            if d.is_dir() and d.name.lower() == "music":
                music_candidates.append(d)
            elif d.is_dir():
                sub_m = d / "music"
                if sub_m.is_dir():
                    music_candidates.append(sub_m)

        found_music: Optional[Path] = None
        for mc in music_candidates:
            if mc.exists() and mc.is_dir():
                found_music = mc
                break

        return True, "Giải nén Production Pack an toàn thành công!", found_json, found_music

    except Exception as e:
        logger.error(f"Lỗi khi giải nén ZIP: {e}", exc_info=True)
        return False, f"Lỗi giải nén ZIP: {str(e)}", None, None


def load_audio_file(file_path: Union[str, Path], target_sr: int = 48000) -> Optional[np.ndarray]:
    """
    Đọc file audio bất kỳ (.wav, .mp3, .flac), chuyển thành mono float32,
    và resample chuẩn xác sang target_sr.
    """
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None
    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data.mean(axis=1)
        data = np.asarray(data, dtype=np.float32)

        if sr != target_sr:
            # Resample
            from scipy.signal import resample_poly
            gcd = math.gcd(target_sr, sr)
            up = target_sr // gcd
            down = sr // gcd
            data = resample_poly(data, up, down).astype(np.float32)

        return data
    except Exception as e:
        logger.error(f"Không thể đọc file audio {file_path}: {e}")
        return None


def parse_music_library(project_dir: Path, source_json: dict) -> Dict[str, dict]:
    """
    Đọc mục 'music_library' từ JSON và kiểm tra tình trạng file thực tế trong project_dir.
    Trả về cấu trúc:
    {
        "cue_name": {
            "file": "music/01_signature_intro.wav",
            "abs_path": Path(...),
            "default_db": -28.0,
            "loop": False,
            "status": "READY" # hoặc "MISSING",
            "duration_sec": float
        }
    }
    """
    raw_lib = source_json.get("music_library", {})
    parsed_lib: Dict[str, dict] = {}

    for cue_name, cue_info in raw_lib.items():
        if not isinstance(cue_info, dict):
            continue
        rel_file = cue_info.get("file", f"music/{cue_name}.wav")
        abs_file = (project_dir / rel_file).resolve()

        # Kiểm tra fallback nếu rel_file là music/xxx nhưng thực tế xxx nằm ở project_dir
        if not abs_file.exists():
            alt = project_dir / Path(rel_file).name
            if alt.exists():
                abs_file = alt

        is_ready = abs_file.exists() and abs_file.is_file()
        dur = 0.0
        if is_ready:
            try:
                info = sf.info(str(abs_file))
                dur = float(info.duration)
            except Exception:
                pass

        parsed_lib[cue_name] = {
            "cue": cue_name,
            "file": rel_file,
            "abs_path": abs_file,
            "default_db": float(cue_info.get("default_db", -34.0)),
            "loop": bool(cue_info.get("loop", True)),
            "status": "READY" if is_ready else "MISSING",
            "duration_sec": dur
        }

    return parsed_lib


def build_music_library_table_data(music_lib: Dict[str, dict]) -> List[List[Any]]:
    """Tạo bảng dữ liệu cho UI DataFrame Music Library."""
    rows = []
    for cue, info in music_lib.items():
        loop_str = "Yes" if info["loop"] else "No"
        status_str = "✅ READY" if info["status"] == "READY" else "⚠️ MISSING"
        rows.append([
            cue,
            Path(info["file"]).name,
            f"{info['default_db']:.1f} dB",
            loop_str,
            f"{info['duration_sec']:.1f}s",
            status_str
        ])
    return rows


def loop_audio_seamless(audio: np.ndarray, needed_samples: int, crossfade_samples: int = 2400) -> np.ndarray:
    """
    Lặp lại audio một cách liền mạch với crossfade 50ms (2400 samples @ 48kHz)
    tại các điểm giáp mí để không phát ra tiếng click hoặc giật âm thanh.
    """
    L = len(audio)
    if L >= needed_samples:
        return audio[:needed_samples].copy()

    if L <= crossfade_samples * 2:
        # Nếu audio quá ngắn thì lặp thông thường
        repeat = int(np.ceil(needed_samples / L))
        return np.tile(audio, repeat)[:needed_samples].copy()

    fade_len = min(crossfade_samples, L // 4)
    fade_out = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
    fade_in = 1.0 - fade_out

    # Tạo một block đã làm mềm biên (smooth loop unit)
    step = L - fade_len
    num_blocks = int(np.ceil(needed_samples / step)) + 2

    out = np.zeros(num_blocks * step + fade_len, dtype=np.float32)
    pos = 0

    for i in range(num_blocks):
        if i == 0:
            out[pos : pos + L] += audio
        else:
            # Crossfade vùng giao thoa
            out[pos : pos + fade_len] = out[pos : pos + fade_len] * fade_out + audio[:fade_len] * fade_in
            out[pos + fade_len : pos + L] += audio[fade_len:]
        pos += step
        if pos >= needed_samples:
            break

    return out[:needed_samples]


def build_dialogue_timeline(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    gap_rule: str = "max",
    default_gap: float = 0.18,
    sample_rate: int = 48000
) -> Tuple[np.ndarray, List[dict], int]:
    """
    Ráp các file âm thanh đã sinh của segments thành Dialogue Timeline.
    Tính toán chính xác:
    - speech_start_sec & speech_end_sec
    - pause_before & pause_after
    - Tránh double pause theo gap_rule ('max' hoặc 'sum')
    Trả về:
    - dialogue_audio: np.ndarray (float32)
    - timeline_events: danh sách metadata từng segment kèm vị trí thời gian
    - total_samples: int
    """
    segments_state = project_state.get("segments", {}) if project_state else {}
    timeline_events = []
    audio_pieces = []
    current_sample = 0

    total_segs = len(segments)

    for i in range(total_segs):
        seg = segments[i]
        seg_id = str(seg.get("id", i + 1)).zfill(3)
        seg_data = segments_state.get(seg_id, {})

        # Tìm file audio selected
        selected_rel = seg_data.get("selected_file")
        if selected_rel:
            selected_path = project_dir / selected_rel
        else:
            selected_path = project_dir / "selected" / f"{seg_id}.wav"

        if not selected_path.exists():
            raise FileNotFoundError(
                f"Thiếu file âm thanh cho phân đoạn {seg_id} ({selected_path.name}). "
                f"Vui lòng hoàn tất sinh giọng nói trước khi Master."
            )

        wav = load_audio_file(selected_path, target_sr=sample_rate)
        if wav is None:
            raise RuntimeError(f"Không thể đọc âm thanh phân đoạn {seg_id}.")

        # 1. Pause before cho câu đầu tiên
        p_before = float(seg.get("pause_before", 0.0) or 0.0)
        if i == 0 and p_before > 0:
            silence_samples = int(p_before * sample_rate)
            audio_pieces.append(np.zeros(silence_samples, dtype=np.float32))
            current_sample += silence_samples

        # 2. Vị trí bắt đầu của lời nói
        speech_start_sample = current_sample
        speech_start_sec = speech_start_sample / sample_rate

        audio_pieces.append(wav)
        current_sample += len(wav)

        speech_end_sample = current_sample
        speech_end_sec = speech_end_sample / sample_rate

        p_after = float(seg.get("pause_after", default_gap) or default_gap)

        # Lưu metadata của event
        event = {
            "id": seg_id,
            "speaker": seg.get("speaker", "UNKNOWN"),
            "text": seg.get("text", ""),
            "speech_start_sample": speech_start_sample,
            "speech_end_sample": speech_end_sample,
            "speech_start_sec": speech_start_sec,
            "speech_end_sec": speech_end_sec,
            "pause_before": p_before,
            "pause_after": p_after,
            "music_cue": seg.get("music_cue", "none") or "none",
            "music_volume_db": seg.get("music_volume_db"),
            "music_fade_in_sec": float(seg.get("music_fade_in_sec", 1.2) or 1.2),
            "music_fade_out_sec": float(seg.get("music_fade_out_sec", 1.0) or 1.0),
            "ducking_db": float(seg.get("ducking_db", -8.0) if seg.get("ducking_db") is not None else -8.0),
            "room_tone_db": float(seg.get("room_tone_db", -41.0) if seg.get("room_tone_db") is not None else -41.0),
            "importance": seg.get("importance", "normal") or "normal",
            "section_type": seg.get("section_type", "normal")
        }
        timeline_events.append(event)

        # 3. Chèn khoảng nghỉ giữa các câu
        if i < total_segs - 1:
            next_seg = segments[i + 1]
            next_p_before = float(next_seg.get("pause_before", 0.0) or 0.0)
            if gap_rule == "max":
                gap = max(p_after, next_p_before)
            else:
                gap = p_after + next_p_before

            if gap > 0:
                silence_samples = int(gap * sample_rate)
                audio_pieces.append(np.zeros(silence_samples, dtype=np.float32))
                current_sample += silence_samples
        else:
            # Câu cuối cùng
            if p_after > 0:
                silence_samples = int(p_after * sample_rate)
                audio_pieces.append(np.zeros(silence_samples, dtype=np.float32))
                current_sample += silence_samples

    dialogue_audio = np.concatenate(audio_pieces) if audio_pieces else np.zeros(0, dtype=np.float32)
    return dialogue_audio, timeline_events, len(dialogue_audio)


def build_room_tone_track(
    project_dir: Path,
    total_samples: int,
    music_lib: Dict[str, dict],
    room_tone_volume_db: float = -41.0,
    sample_rate: int = 48000
) -> np.ndarray:
    """
    Sinh track Room Tone chạy liên tục xuyên suốt từ đầu tới cuối chương trình.
    - Không ngắt giữa các câu.
    - Loop mượt mà chống click.
    - Không ducking.
    """
    rt_info = music_lib.get("room_tone")
    if not rt_info or rt_info["status"] != "READY":
        logger.warning("Room tone không khả dụng. Trả về track im lặng.")
        return np.zeros(total_samples, dtype=np.float32)

    rt_wav = load_audio_file(rt_info["abs_path"], target_sr=sample_rate)
    if rt_wav is None or len(rt_wav) == 0:
        return np.zeros(total_samples, dtype=np.float32)

    # Loop liền mạch
    looped = loop_audio_seamless(rt_wav, total_samples, crossfade_samples=int(0.05 * sample_rate))
    
    # Chuẩn hóa về đúng target room_tone_volume_db (dBFS RMS)
    current_rms = np.sqrt(np.mean(rt_wav ** 2))
    current_rms_db = 20.0 * np.log10(max(1e-9, float(current_rms)))
    gain = 10.0 ** ((room_tone_volume_db - current_rms_db) / 20.0)
    # Giới hạn an toàn tránh clipping
    gain = min(gain, 12.0)
    return looped * gain


def analyze_music_regions(
    timeline_events: List[dict],
    music_lib: Dict[str, dict],
    auto_silence_critical: bool = True,
    crossfade_sec: float = 1.2,
    reveal_music_return_delay_sec: float = 0.8,
    global_music_gain_db: float = 0.0,
    total_duration_sec: float = 0.0
) -> Tuple[List[dict], List[dict]]:
    """
    Phân tích và gộp các phân đoạn thành các Music Regions liên tục.
    QUY TẮC CỐT LÕI:
    - Nếu các segment liền kề có cùng cue -> KHÔNG restart nhạc, gộp chung thành một region.
    - Nếu cue đổi sang cue khác -> Crossfade giữa 2 cue (mặc định 1.2s).
    - Nếu cue == 'fade_out' -> Fade out nhạc hiện tại về 0, không start cue mới.
    - Nếu cue == 'none' -> Im lặng.
    - Nếu segment có importance == 'critical' và auto_silence_critical = True:
      + Nhạc trước đó fade out hoàn toàn trước khi câu thoại bắt đầu.
      + Suốt câu critical: HOÀN TOÀN KHÔNG CÓ NHẠC (chỉ voice + room tone).
      + Sau khi câu critical dứt lời: Chờ reveal_music_return_delay_sec rồi mới fade nhạc tiếp theo vào.
    Trả về:
    - music_regions: danh sách các vùng phát nhạc thực tế.
    - debug_timeline: danh sách events cho file master/music_timeline.json.
    """
    if not timeline_events:
        return [], []

    # 1. Xác định trạng thái mong muốn tại từng segment
    # Xử lý override volume theo priority: segment.music_volume_db > music_lib[cue].default_db > -34
    processed_events = []
    for idx, ev in enumerate(timeline_events):
        cue = (ev.get("music_cue") or ev.get("cue") or "none").strip()
        is_crit = (ev.get("importance") == "critical" or bool(ev.get("is_critical"))) and auto_silence_critical

        # Xác định target volume
        seg_vol = ev.get("music_volume_db")
        if seg_vol is not None:
            vol = float(seg_vol)
        elif cue in music_lib:
            vol = float(music_lib[cue].get("default_db", -34.0))
        else:
            vol = -34.0
        vol += global_music_gain_db

        st_sec = ev.get("speech_start_sec", ev.get("speech_start", 0.0))
        en_sec = ev.get("speech_end_sec", ev.get("speech_end", 0.0))
        processed_events.append({
            "idx": idx,
            "id": ev.get("id", str(idx+1)),
            "cue": cue,
            "is_critical": is_crit,
            "speech_start": float(st_sec),
            "speech_end": float(en_sec),
            "target_vol": vol,
            "fade_in": float(ev.get("music_fade_in_sec", 1.2) or 1.2),
            "fade_out": float(ev.get("music_fade_out_sec", 1.0) or 1.0),
            "ducking_db": float(ev.get("ducking_db", -8.0) or -8.0)
        })

    # 2. Xây dựng các Region liên tục
    regions: List[dict] = []
    debug_timeline: List[dict] = []

    current_region: Optional[dict] = None

    for i, ev in enumerate(processed_events):
        cue = ev["cue"]
        is_crit = ev["is_critical"]

        # Nếu là câu Critical Reveal: bắt buộc SILENCE
        if is_crit:
            if current_region is not None:
                # Đóng region trước đó tại thời điểm bắt đầu câu critical (trừ đi thời gian fade out)
                fade_dur = min(ev["fade_out"], 1.0)
                current_region["end_sec"] = ev["speech_start"]
                current_region["fade_out_sec"] = fade_dur
                regions.append(current_region)
                debug_timeline.append({
                    "start": round(current_region["start_sec"], 2),
                    "end": round(current_region["end_sec"], 2),
                    "cue": current_region["cue"],
                    "volume_db": round(current_region["volume_db"], 1),
                    "action": "play"
                })
                current_region = None

            debug_timeline.append({
                "start": round(ev["speech_start"], 2),
                "end": round(ev["speech_end"], 2),
                "cue": "SILENCE_CRITICAL_REVEAL",
                "segment_id": ev["id"],
                "action": "silence"
            })
            continue

        # Nếu cue == 'none'
        if cue.lower() == "none":
            if current_region is not None:
                current_region["end_sec"] = ev["speech_start"]
                current_region["fade_out_sec"] = min(ev["fade_out"], 1.0)
                regions.append(current_region)
                debug_timeline.append({
                    "start": round(current_region["start_sec"], 2),
                    "end": round(current_region["end_sec"], 2),
                    "cue": current_region["cue"],
                    "volume_db": round(current_region["volume_db"], 1),
                    "action": "play"
                })
                current_region = None
            continue

        # Nếu cue == 'fade_out'
        if cue.lower() == "fade_out":
            if current_region is not None:
                # Cho nhạc fade out xuyên qua câu này và kết thúc tại speech_end
                current_region["end_sec"] = ev["speech_end"]
                current_region["fade_out_sec"] = ev["fade_out"]
                regions.append(current_region)
                debug_timeline.append({
                    "start": round(current_region["start_sec"], 2),
                    "end": round(current_region["end_sec"], 2),
                    "cue": current_region["cue"],
                    "volume_db": round(current_region["volume_db"], 1),
                    "action": "fade_out"
                })
                current_region = None
            continue

        # Là một cue nhạc cụ thể (e.g. tension_low, memory_soft)
        # Kiểm tra xem có nối tiếp cùng cue từ region trước không
        if current_region is not None:
            if current_region["cue"] == cue:
                # CÙNG CUE: Tiếp tục kéo dài region, KHÔNG RESTART NHẠC!
                current_region["end_sec"] = ev["speech_end"]
                current_region["segments"].append(ev["id"])
                continue
            else:
                # ĐỔI CUE: Kết thúc region cũ với crossfade
                current_region["end_sec"] = ev["speech_start"] + crossfade_sec / 2.0
                current_region["fade_out_sec"] = crossfade_sec
                regions.append(current_region)
                debug_timeline.append({
                    "start": round(current_region["start_sec"], 2),
                    "end": round(current_region["end_sec"], 2),
                    "cue": current_region["cue"],
                    "volume_db": round(current_region["volume_db"], 1),
                    "action": "crossfade_out"
                })
                current_region = None

        # Khởi tạo một region mới
        # Nếu ngay trước đó là một câu critical reveal thì delay một khoảng trước khi fade in
        prev_is_crit = (i > 0 and processed_events[i-1]["is_critical"])
        if prev_is_crit:
            start_time = processed_events[i-1]["speech_end"] + reveal_music_return_delay_sec
        else:
            # Bắt đầu tại speech_start hoặc sớm hơn một chút nếu là câu đầu
            start_time = max(0.0, ev["speech_start"] - (crossfade_sec / 2.0 if i > 0 else 0.0))

        current_region = {
            "cue": cue,
            "start_sec": start_time,
            "end_sec": ev["speech_end"],
            "volume_db": ev["target_vol"],
            "fade_in_sec": ev["fade_in"],
            "fade_out_sec": ev["fade_out"],
            "segments": [ev["id"]]
        }

    # Đóng region cuối nếu còn
    if current_region is not None:
        if total_duration_sec > current_region["end_sec"]:
            current_region["end_sec"] = total_duration_sec
        regions.append(current_region)
        debug_timeline.append({
            "start": round(current_region["start_sec"], 2),
            "end": round(current_region["end_sec"], 2),
            "cue": current_region["cue"],
            "volume_db": round(current_region["volume_db"], 1),
            "action": "play"
        })

    return regions, debug_timeline


def build_music_track(
    project_dir: Path,
    total_samples: int,
    music_regions: List[dict],
    music_lib: Dict[str, dict],
    sample_rate: int = 48000
) -> np.ndarray:
    """
    Kết xuất các music regions thành track nhạc nền duy nhất trải dài toàn bộ timeline.
    - Lặp seamless các bản loop.
    - Áp dụng các đường cong fade in / fade out / crossfade chuẩn.
    - Đảm bảo không chồng lấp méo tiếng và không bị click.
    """
    music_track = np.zeros(total_samples, dtype=np.float32)

    for reg in music_regions:
        cue = reg["cue"]
        info = music_lib.get(cue)
        if not info or info["status"] != "READY":
            logger.warning(f"Bỏ qua cue '{cue}' do thiếu file audio.")
            continue

        raw_wav = load_audio_file(info["abs_path"], target_sr=sample_rate)
        if raw_wav is None or len(raw_wav) == 0:
            continue

        start_samp = max(0, int(reg["start_sec"] * sample_rate))
        end_samp = min(total_samples, int(reg["end_sec"] * sample_rate))
        reg_samples = end_samp - start_samp
        if reg_samples <= 0:
            continue

        # Chuẩn bị audio cho độ dài cần thiết
        if info["loop"]:
            chunk = loop_audio_seamless(raw_wav, reg_samples, crossfade_samples=int(0.05 * sample_rate))
        else:
            # Không loop (e.g. signature_intro, outro)
            if len(raw_wav) >= reg_samples:
                chunk = raw_wav[:reg_samples].copy()
            else:
                chunk = np.zeros(reg_samples, dtype=np.float32)
                chunk[:len(raw_wav)] = raw_wav

        # Chuẩn hóa về target volume_db (dBFS RMS)
        raw_rms = np.sqrt(np.mean(raw_wav ** 2))
        raw_rms_db = 20.0 * np.log10(max(1e-9, float(raw_rms)))
        gain = 10.0 ** ((reg["volume_db"] - raw_rms_db) / 20.0)
        gain = min(gain, 4.0)  # Bảo vệ chống clipping quá mức
        chunk *= gain

        # Áp dụng Fade In
        fade_in_len = min(reg_samples, int(reg.get("fade_in_sec", 1.2) * sample_rate))
        if fade_in_len > 0:
            fade_in_curve = np.linspace(0.0, 1.0, fade_in_len, dtype=np.float32)
            chunk[:fade_in_len] *= fade_in_curve

        # Áp dụng Fade Out
        fade_out_len = min(reg_samples, int(reg.get("fade_out_sec", 1.0) * sample_rate))
        if fade_out_len > 0:
            fade_out_curve = np.linspace(1.0, 0.0, fade_out_len, dtype=np.float32)
            chunk[-fade_out_len:] *= fade_out_curve

        # Cộng vào track tổng
        music_track[start_samp : end_samp] += chunk

    return music_track


def apply_voice_ducking(
    music_track: np.ndarray,
    timeline_events: List[dict],
    sample_rate: int = 48000,
    default_ducking_db: float = -8.0,
    attack_ms: float = 120.0,
    release_ms: float = 600.0
) -> np.ndarray:
    """
    Áp dụng thuật toán Ducking analog-style làm giảm âm lượng nhạc nền khi có tiếng nói:
    - Khi có giọng thoại: Giảm thêm ducking_db (mặc định -8 dB).
    - Khi hết câu: Nhạc từ từ trở lại âm lượng ban đầu.
    - Attack time: 120ms (chuyển êm, không click).
    - Release time: 600ms (hồi âm tự nhiên, không pump).
    - Sử dụng bộ lọc làm mịn 100 Hz control-rate nội suy tuyến tính, tối ưu tốc độ CPU.
    """
    total_samples = len(music_track)
    if total_samples == 0:
        return music_track

    # 1. Tạo target gain tại control rate (100 Hz = 10ms per frame)
    frame_step = int(sample_rate / 100) # 480 samples
    num_frames = int(math.ceil(total_samples / frame_step))
    target_gains = np.ones(num_frames, dtype=np.float32)

    # Đánh dấu các vùng có giọng nói
    for ev in timeline_events:
        st_samp = ev.get("speech_start_sample")
        if st_samp is None:
            st_samp = int(ev.get("speech_start_sec", ev.get("speech_start", 0.0)) * sample_rate)
        en_samp = ev.get("speech_end_sample")
        if en_samp is None:
            en_samp = int(ev.get("speech_end_sec", ev.get("speech_end", 0.0)) * sample_rate)
        st_frame = max(0, int(st_samp / frame_step))
        end_frame = min(num_frames, int(en_samp / frame_step))
        d_db = ev.get("ducking_db", default_ducking_db)
        d_gain = 10.0 ** (float(d_db) / 20.0)
        target_gains[st_frame:end_frame] = np.minimum(target_gains[st_frame:end_frame], d_gain)

    # 2. Bộ lọc làm mịn Attack / Release
    attack_frames = max(1, int((attack_ms / 1000.0) * 100))
    release_frames = max(1, int((release_ms / 1000.0) * 100))

    alpha_att = 1.0 - math.exp(-1.0 / attack_frames)
    alpha_rel = 1.0 - math.exp(-1.0 / release_frames)

    smooth_gains = np.empty(num_frames, dtype=np.float32)
    g = 1.0
    for i in range(num_frames):
        target = target_gains[i]
        if target < g:
            g += alpha_att * (target - g)
        else:
            g += alpha_rel * (target - g)
        smooth_gains[i] = g

    # 3. Nội suy tuyến tính lên full sample rate
    frame_indices = np.arange(num_frames) * frame_step
    sample_indices = np.arange(total_samples)
    full_gain_envelope = np.interp(sample_indices, frame_indices, smooth_gains).astype(np.float32)

    return music_track * full_gain_envelope


def normalize_master_ffmpeg(
    input_wav: Path,
    output_wav: Path,
    output_mp3: Path,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    sample_rate: int = 48000
) -> bool:
    """
    Chuẩn hóa âm lượng Broadcast bằng 2-pass FFmpeg EBU R128 Loudness Normalization:
    - Pass 1: Đo lường chính xác input_i, input_tp, input_lra.
    - Pass 2: Linear loudness normalization sang target_lufs và true_peak_db.
    - Xuất file Master WAV (48kHz 24-bit PCM) và MP3 (320kbps).
    """
    try:
        cmd_pass1 = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(input_wav),
            "-af", f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11:print_format=json",
            "-f", "null", "-"
        ]
        res1 = subprocess.run(cmd_pass1, capture_output=True, text=True, check=True)
        stderr_output = res1.stderr

        json_match = re.search(r'\{[\s\S]*"input_i"[\s\S]*\}', stderr_output)
        if json_match:
            stats = json.loads(json_match.group(0))
            input_i = stats.get("input_i", "-24")
            input_tp = stats.get("input_tp", "-2")
            input_lra = stats.get("input_lra", "7")
            input_thresh = stats.get("input_thresh", "-34")
            target_offset = stats.get("target_offset", "0")

            cmd_pass2 = [
                "ffmpeg", "-y", "-hide_banner",
                "-i", str(input_wav),
                "-af", (
                    f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11:"
                    f"measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:"
                    f"measured_thresh={input_thresh}:offset={target_offset}:linear=true"
                ),
                "-ar", str(sample_rate),
                str(output_wav)
            ]
            subprocess.run(cmd_pass2, capture_output=True, text=True, check=True)
        else:
            # 1-pass fallback
            cmd_fallback = [
                "ffmpeg", "-y", "-hide_banner",
                "-i", str(input_wav),
                "-af", f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11",
                "-ar", str(sample_rate),
                str(output_wav)
            ]
            subprocess.run(cmd_fallback, capture_output=True, text=True, check=True)

        # Xuất MP3 320kbps
        cmd_mp3 = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(output_wav),
            "-codec:a", "libmp3lame",
            "-b:a", "320k",
            str(output_mp3)
        ]
        subprocess.run(cmd_mp3, capture_output=True, text=True, check=True)
        return True

    except Exception as e:
        logger.error(f"Lỗi khi normalize master audio qua FFmpeg: {e}")
        shutil.copy2(input_wav, output_wav)
        return False


def build_audio_director_master(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    music_lib: Dict[str, dict],
    enable_music: bool = True,
    enable_room_tone: bool = True,
    auto_silence_critical: bool = True,
    global_music_gain_db: float = 0.0,
    room_tone_volume_db: float = -41.0,
    default_ducking_db: float = -8.0,
    crossfade_sec: float = 1.2,
    reveal_music_return_delay_sec: float = 0.8,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    gap_rule: str = "max",
    default_gap: float = 0.18,
    sample_rate: int = 48000
) -> Tuple[bool, str, Dict[str, str]]:
    """
    Toàn bộ quy trình TTS Audio Director:
    STEP 1: Ráp Dialogue timeline từ các takes đã chọn.
    STEP 2: Sinh continuous Room Tone timeline.
    STEP 3: Phân tích và tạo các continuous Music Regions.
    STEP 4: Render Music track với crossfade, fade out, và reveal silence.
    STEP 5: Áp dụng Dialogue Ducking tự nhiên.
    STEP 6: Mix: dialogue + room_tone + music.
    STEP 7: 2-Pass Loudness Normalization.
    STEP 8: Xuất đầy đủ các Stems (WAV + MP3 + JSON Timeline).
    """
    master_dir = project_dir / "master"
    master_dir.mkdir(parents=True, exist_ok=True)

    # 1. Dialogue timeline
    try:
        dialogue_audio, timeline_events, total_samples = build_dialogue_timeline(
            project_dir=project_dir,
            segments=segments,
            project_state=project_state,
            gap_rule=gap_rule,
            default_gap=default_gap,
            sample_rate=sample_rate
        )
    except Exception as e:
        return False, f"Lỗi tạo Dialogue Timeline: {str(e)}", {}

    if total_samples == 0:
        return False, "Không có phân đoạn âm thanh nào để ghép.", {}

    total_duration_sec = total_samples / sample_rate

    # Lưu stem dialogue_only
    dialogue_wav_path = master_dir / "dialogue_only.wav"
    sf.write(str(dialogue_wav_path), dialogue_audio, sample_rate)

    # 2. Room tone track
    if enable_room_tone:
        room_tone_audio = build_room_tone_track(
            project_dir=project_dir,
            total_samples=total_samples,
            music_lib=music_lib,
            room_tone_volume_db=room_tone_volume_db,
            sample_rate=sample_rate
        )
    else:
        room_tone_audio = np.zeros(total_samples, dtype=np.float32)

    room_tone_wav_path = master_dir / "room_tone.wav"
    sf.write(str(room_tone_wav_path), room_tone_audio, sample_rate)

    # 3 & 4. Music track & Ducking
    if enable_music and music_lib:
        regions, debug_timeline = analyze_music_regions(
            timeline_events=timeline_events,
            music_lib=music_lib,
            auto_silence_critical=auto_silence_critical,
            crossfade_sec=crossfade_sec,
            reveal_music_return_delay_sec=reveal_music_return_delay_sec,
            global_music_gain_db=global_music_gain_db,
            total_duration_sec=total_duration_sec
        )
        raw_music = build_music_track(
            project_dir=project_dir,
            total_samples=total_samples,
            music_regions=regions,
            music_lib=music_lib,
            sample_rate=sample_rate
        )
        ducked_music = apply_voice_ducking(
            music_track=raw_music,
            timeline_events=timeline_events,
            sample_rate=sample_rate,
            default_ducking_db=default_ducking_db
        )
    else:
        ducked_music = np.zeros(total_samples, dtype=np.float32)
        debug_timeline = []

    music_wav_path = master_dir / "music_only.wav"
    sf.write(str(music_wav_path), ducked_music, sample_rate)

    # Lưu music_timeline.json
    timeline_json_path = master_dir / "music_timeline.json"
    timeline_payload = {
        "music_regions": regions if enable_music else [],
        "timeline_events": debug_timeline
    }
    with open(timeline_json_path, "w", encoding="utf-8") as f:
        json.dump(timeline_payload, f, ensure_ascii=False, indent=2)

    # 5. Mix: Dialogue + Room Tone + Ducked Music
    pre_master_audio = dialogue_audio + room_tone_audio + ducked_music
    pre_master_wav_path = master_dir / "pre_master_mix.wav"
    sf.write(str(pre_master_wav_path), pre_master_audio, sample_rate)

    # 6. Normalize Master
    master_wav_path = master_dir / "episode_master.wav"
    master_mp3_path = master_dir / "episode_master.mp3"

    normalize_master_ffmpeg(
        input_wav=pre_master_wav_path,
        output_wav=master_wav_path,
        output_mp3=master_mp3_path,
        target_lufs=target_lufs,
        true_peak_db=true_peak_db,
        sample_rate=sample_rate
    )

    outputs = {
        "dialogue_only": str(dialogue_wav_path),
        "room_tone": str(room_tone_wav_path),
        "music_only": str(music_wav_path),
        "pre_master_mix": str(pre_master_wav_path),
        "episode_master_wav": str(master_wav_path),
        "episode_master_mp3": str(master_mp3_path),
        "music_timeline_json": str(timeline_json_path),
        "total_duration_sec": f"{total_duration_sec:.1f}"
    }

    return True, f"Tạo Master thành công ({total_duration_sec/60:.1f} phút)!", outputs


def build_preview_mix_clip(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    music_lib: Dict[str, dict],
    start_seg_id: str,
    duration_sec: float = 30.0,
    enable_music: bool = True,
    enable_room_tone: bool = True,
    auto_silence_critical: bool = True,
    global_music_gain_db: float = 0.0,
    room_tone_volume_db: float = -41.0,
    default_ducking_db: float = -8.0,
    crossfade_sec: float = 1.2,
    sample_rate: int = 48000
) -> Tuple[bool, str, Optional[str]]:
    """
    Tạo nhanh bản preview mix 30 giây từ phân đoạn được chọn:
    Voice + Room tone + Background Music (có ducking & crossfade) mà không cần render full tập.
    """
    previews_dir = project_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    out_preview_path = previews_dir / f"preview_mix_{start_seg_id}_{int(duration_sec)}s.wav"

    try:
        dialogue_audio, timeline_events, total_samples = build_dialogue_timeline(
            project_dir=project_dir,
            segments=segments,
            project_state=project_state,
            sample_rate=sample_rate
        )
    except Exception as e:
        return False, f"Lỗi tạo preview dialogue: {e}", None

    # Tìm vị trí bắt đầu của start_seg_id
    start_sec = 0.0
    for ev in timeline_events:
        if ev["id"] == start_seg_id:
            start_sec = ev["speech_start_sec"]
            break

    start_sample = int(start_sec * sample_rate)
    window_samples = int(duration_sec * sample_rate)
    end_sample = min(total_samples, start_sample + window_samples)

    if start_sample >= total_samples:
        return False, f"Phân đoạn {start_seg_id} vượt quá độ dài timeline.", None

    sub_samples = end_sample - start_sample
    sub_dialogue = dialogue_audio[start_sample:end_sample]

    # Room tone
    if enable_room_tone:
        full_rt = build_room_tone_track(project_dir, total_samples, music_lib, room_tone_volume_db, sample_rate)
        sub_rt = full_rt[start_sample:end_sample]
    else:
        sub_rt = np.zeros(sub_samples, dtype=np.float32)

    # Music
    if enable_music and music_lib:
        regions, _ = analyze_music_regions(
            timeline_events=timeline_events,
            music_lib=music_lib,
            auto_silence_critical=auto_silence_critical,
            crossfade_sec=crossfade_sec,
            global_music_gain_db=global_music_gain_db,
            total_duration_sec=total_samples / sample_rate
        )
        full_music = build_music_track(project_dir, total_samples, regions, music_lib, sample_rate)
        full_ducked = apply_voice_ducking(full_music, timeline_events, sample_rate, default_ducking_db)
        sub_music = full_ducked[start_sample:end_sample]
    else:
        sub_music = np.zeros(sub_samples, dtype=np.float32)

    sub_mix = sub_dialogue + sub_rt + sub_music
    sf.write(str(out_preview_path), sub_mix, sample_rate)
    return True, f"Đã tạo Preview Mix {duration_sec}s thành công!", str(out_preview_path)


def build_preview_reveal_clip(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    music_lib: Dict[str, dict],
    reveal_seg_id: str,
    before_sec: float = 8.0,
    after_sec: float = 8.0,
    enable_music: bool = True,
    enable_room_tone: bool = True,
    auto_silence_critical: bool = True,
    room_tone_volume_db: float = -41.0,
    default_ducking_db: float = -8.0,
    reveal_music_return_delay_sec: float = 0.8,
    sample_rate: int = 48000
) -> Tuple[bool, str, Optional[str]]:
    """
    Tạo bản nghe thử cho khoảnh khắc hé lộ then chốt (Critical Reveal):
    Cắt đoạn trước ~8s + câu thoại Reveal (Music = Silence, chỉ Voice + Room Tone) + đoạn sau ~8s (Nhạc từ từ quay lại).
    """
    previews_dir = project_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)
    out_reveal_path = previews_dir / f"preview_reveal_{reveal_seg_id}.wav"

    try:
        dialogue_audio, timeline_events, total_samples = build_dialogue_timeline(
            project_dir=project_dir,
            segments=segments,
            project_state=project_state,
            sample_rate=sample_rate
        )
    except Exception as e:
        return False, f"Lỗi tạo timeline: {e}", None

    rev_ev = None
    for ev in timeline_events:
        if ev["id"] == reveal_seg_id:
            rev_ev = ev
            break

    if not rev_ev:
        return False, f"Không tìm thấy phân đoạn {reveal_seg_id}.", None

    start_sec = max(0.0, rev_ev["speech_start_sec"] - before_sec)
    end_sec = min(total_samples / sample_rate, rev_ev["speech_end_sec"] + after_sec)

    start_sample = int(start_sec * sample_rate)
    end_sample = int(end_sec * sample_rate)
    sub_samples = end_sample - start_sample

    sub_dialogue = dialogue_audio[start_sample:end_sample]

    if enable_room_tone:
        full_rt = build_room_tone_track(project_dir, total_samples, music_lib, room_tone_volume_db, sample_rate)
        sub_rt = full_rt[start_sample:end_sample]
    else:
        sub_rt = np.zeros(sub_samples, dtype=np.float32)

    if enable_music and music_lib:
        regions, _ = analyze_music_regions(
            timeline_events=timeline_events,
            music_lib=music_lib,
            auto_silence_critical=auto_silence_critical,
            reveal_music_return_delay_sec=reveal_music_return_delay_sec,
            total_duration_sec=total_samples / sample_rate
        )
        full_music = build_music_track(project_dir, total_samples, regions, music_lib, sample_rate)
        full_ducked = apply_voice_ducking(full_music, timeline_events, sample_rate, default_ducking_db)
        sub_music = full_ducked[start_sample:end_sample]
    else:
        sub_music = np.zeros(sub_samples, dtype=np.float32)

    sub_mix = sub_dialogue + sub_rt + sub_music
    sf.write(str(out_reveal_path), sub_mix, sample_rate)
    return True, f"Đã tạo Preview Critical Reveal ({reveal_seg_id}) thành công!", str(out_reveal_path)
