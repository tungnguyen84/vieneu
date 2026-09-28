"""
Music Mixing Engine & Persistent Music Library for Production Storytelling ("Sau Cánh Cửa").
Đảm nhiệm:
1. Persistent Music Library (6 categories: INTRO, MYSTERY, TENSION, EMOTIONAL, REFLECTION, OUTRO, DRY).
2. Loudness Analysis & Normalization (chuẩn hóa về reference -24.0 LUFS cho mọi track nhạc).
3. Clean Voice Master Builder (voice_master.wav: chỉ voice + pause, tuyệt đối không room tone/noise/music).
4. Delivery Profile → Music Cue Inference & Major Reveal Safety Rule (clearance trước và sau reveal).
5. Consecutive Cue Region Merging (không restart nhạc giữa các segment cùng cue).
6. Music Bed Renderer (seamless looping crossfade 3.0s, smooth equal-power fades, dB-accurate gain).
7. Gentle Dialogue Ducking (-2.5 dB soft attack/release).
8. Final Mix & Mastering (-14 LUFS, -1 dBTP, xuất voice_master.wav, music_mix.wav, final_mix_pre_master.wav, final_mix.wav, final_mix.mp3, cue_sheet.json, mix_report.json).
9. Music Coverage Calculation & Visual Timeline HTML.
10. A/B Voice/Mix Comparison & Region Preview.
"""

import os
import sys
import json
import time
import math
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

import numpy as np
import soundfile as sf

logger = logging.getLogger("VieNeu.MusicEngine")
if not logger.handlers:
    class SafeStreamHandler(logging.StreamHandler):
        def emit(self, record):
            try:
                msg = self.format(record)
                stream = self.stream
                try:
                    stream.write(msg + self.terminator)
                except UnicodeEncodeError:
                    stream.write(msg.encode("ascii", "replace").decode("ascii") + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)

    handler = SafeStreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [MusicEngine] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Thư mục Music Library toàn cục
GLOBAL_MUSIC_LIB_DIR = Path("music_library")
GLOBAL_ORIGINAL_DIR = GLOBAL_MUSIC_LIB_DIR / "original"
GLOBAL_NORMALIZED_DIR = GLOBAL_MUSIC_LIB_DIR / "normalized"
GLOBAL_LIB_JSON = GLOBAL_MUSIC_LIB_DIR / "library.json"

REFERENCE_MUSIC_LUFS = -24.0
REFERENCE_SAMPLE_RATE = 48000

# 6 danh mục nhạc chuẩn theo quy định của series "Sau Cánh Cửa"
DEFAULT_CATEGORY_CONFIG = {
    "INTRO": {
        "display_name": "Nhạc mở đầu (Intro)",
        "default_track": "SCC_INTRO_01",
        "default_level_db": -31.0,
        "fade_in_sec": 1.0,
        "fade_out_sec": 2.0,
        "max_duration_sec": 30.0,
        "color": "#3b82f6"  # Blue
    },
    "MYSTERY": {
        "display_name": "Bí ẩn, tò mò (Mystery)",
        "default_track": "SCC_MYSTERY_01",
        "default_level_db": -35.0,
        "fade_in_sec": 2.0,
        "fade_out_sec": 2.5,
        "max_duration_sec": None,
        "color": "#8b5cf6"  # Purple
    },
    "TENSION": {
        "display_name": "Căng thẳng, hồi hộp (Tension)",
        "default_track": "SCC_TENSION_01",
        "default_level_db": -36.0,
        "fade_in_sec": 2.0,
        "fade_out_sec": 2.0,
        "max_duration_sec": None,
        "color": "#ef4444"  # Red
    },
    "EMOTIONAL": {
        "display_name": "Cảm xúc, lắng đọng (Emotional)",
        "default_track": "SCC_EMOTIONAL_01",
        "default_level_db": -36.0,
        "fade_in_sec": 2.0,
        "fade_out_sec": 2.5,
        "max_duration_sec": None,
        "color": "#ec4899"  # Pink
    },
    "REFLECTION": {
        "display_name": "Chiêm nghiệm, nhìn lại (Reflection)",
        "default_track": "SCC_REFLECTION_01",
        "default_level_db": -35.0,
        "fade_in_sec": 2.5,
        "fade_out_sec": 3.0,
        "max_duration_sec": None,
        "color": "#06b6d4"  # Cyan
    },
    "OUTRO": {
        "display_name": "Nhạc kết thúc (Outro)",
        "default_track": "SCC_OUTRO_01",
        "default_level_db": -30.0,
        "fade_in_sec": 2.0,
        "fade_out_sec": 4.0,
        "max_duration_sec": 45.0,
        "color": "#6366f1"  # Indigo
    },
    "DRY": {
        "display_name": "Voice sạch, không nhạc (DRY)",
        "default_track": "NO_MUSIC",
        "default_level_db": -99.0,
        "fade_in_sec": 0.0,
        "fade_out_sec": 0.0,
        "max_duration_sec": None,
        "color": "#9ca3af"  # Gray
    }
}


# ==============================================================================
# 1. LOUDNESS ANALYSIS & NORMALIZATION
# ==============================================================================

def analyze_audio_loudness(audio_path: Path) -> dict:
    """
    Phân tích độ lớn âm thanh bằng FFmpeg loudnorm pass 1 (chuẩn EBU R128).
    Trả về dict: duration_sec, integrated_lufs, true_peak_db, lra, threshold.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return {
            "duration_sec": 0.0,
            "integrated_lufs": -99.0,
            "true_peak_db": -99.0,
            "lra": 0.0,
            "threshold": -99.0,
            "status": "MISSING"
        }

    duration = 0.0
    try:
        info = sf.info(str(audio_path))
        duration = float(info.duration)
    except Exception:
        pass

    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(audio_path),
        "-af", "loudnorm=I=-24:TP=-1:print_format=json",
        "-f", "null", "-"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        out = res.stderr
        st = out.rfind("{")
        en = out.rfind("}") + 1
        if st != -1 and en > st:
            d = json.loads(out[st:en])
            return {
                "duration_sec": round(duration, 2),
                "integrated_lufs": round(float(d.get("input_i", -99.0)), 2),
                "true_peak_db": round(float(d.get("input_tp", -99.0)), 2),
                "lra": round(float(d.get("input_lra", 0.0)), 2),
                "threshold": round(float(d.get("input_thresh", -99.0)), 2),
                "status": "ANALYZED"
            }
    except Exception as e:
        logger.warning(f"Lỗi phân tích loudness {audio_path}: {e}")

    return {
        "duration_sec": round(duration, 2),
        "integrated_lufs": -30.0,
        "true_peak_db": -1.0,
        "lra": 0.0,
        "threshold": -40.0,
        "status": "FALLBACK"
    }


def normalize_music_asset(
    input_path: Path,
    output_path: Path,
    target_lufs: float = REFERENCE_MUSIC_LUFS,
    target_peak_db: float = -1.0,
    sample_rate: int = REFERENCE_SAMPLE_RATE
) -> dict:
    """
    Chuẩn hóa track nhạc về reference loudness (-24.0 LUFS, 48kHz WAV).
    Không làm thay đổi file gốc. Lưu bản normalized vào output_path.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Phân tích file đầu vào
    stats = analyze_audio_loudness(input_path)

    # 2. Chạy FFmpeg loudnorm 2-pass hoặc linear normalization sang 48kHz WAV
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={target_peak_db}:linear=true",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s24le",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except Exception as e:
        logger.warning(f"Lỗi khi chạy ffmpeg loudnorm cho {input_path}, thử resample thông thường: {e}")
        cmd_fallback = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(input_path),
            "-ar", str(sample_rate),
            "-c:a", "pcm_s24le",
            str(output_path)
        ]
        subprocess.run(cmd_fallback, capture_output=True, check=True)

    # 3. Phân tích lại file normalized
    norm_stats = analyze_audio_loudness(output_path)
    norm_stats["original_file"] = str(input_path)
    norm_stats["normalized_file"] = str(output_path)
    norm_stats["normalized_status"] = "READY"
    return norm_stats


# ==============================================================================
# 2. PERSISTENT MUSIC LIBRARY
# ==============================================================================

def init_global_music_library(lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> dict:
    """
    Khởi tạo hoặc tải Music Library toàn cục lưu tại music_library/.
    Nếu thư mục rỗng, tự động quét và nạp 6 bản nhạc mặc định từ assets sẵn có.
    """
    lib_dir = Path(lib_dir)
    original_dir = lib_dir / "original"
    normalized_dir = lib_dir / "normalized"
    lib_json_path = lib_dir / "library.json"

    original_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    if lib_json_path.exists():
        try:
            with open(lib_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Kiểm tra xem các file normalized có còn đủ trên đĩa không
            tracks = data.get("tracks", {})
            valid = True
            for tid, tinfo in tracks.items():
                p = Path(tinfo.get("normalized_file", ""))
                if not p.exists():
                    valid = False
                    break
            if valid and len(tracks) >= 6:
                return data
        except Exception:
            pass

    # Tự động tìm nguồn nhạc mặc định để nạp ban đầu
    candidates = [
        Path(r"C:\Users\TPT\Documents\sau_canh_cua_ep01_v9_1_master_reference\01_audio\music"),
        Path(r"projects\test_v6_pack\music"),
        Path(r"projects\sau_canh_cua_-_pilot_01_v6\music")
    ]

    seed_map = {
        "SCC_INTRO_01": ("INTRO", ["01_signature_intro.wav"]),
        "SCC_MYSTERY_01": ("MYSTERY", ["03_mystery_low.wav"]),
        "SCC_TENSION_01": ("TENSION", ["05_tension_low.wav"]),
        "SCC_EMOTIONAL_01": ("EMOTIONAL", ["06_emotional_low.wav"]),
        "SCC_REFLECTION_01": ("REFLECTION", ["04_memory_soft.wav", "07_closing_soft.wav"]),
        "SCC_OUTRO_01": ("OUTRO", ["02_signature_outro.wav"])
    }

    library_data = {
        "version": "1.0",
        "reference_lufs": REFERENCE_MUSIC_LUFS,
        "sample_rate": REFERENCE_SAMPLE_RATE,
        "categories": DEFAULT_CATEGORY_CONFIG,
        "tracks": {}
    }

    for track_id, (category, filenames) in seed_map.items():
        found_source = None
        for cand_dir in candidates:
            if not cand_dir.exists():
                continue
            for fn in filenames:
                p = cand_dir / fn
                if p.exists():
                    found_source = p
                    break
            if found_source:
                break

        if found_source and found_source.exists():
            orig_dest = original_dir / f"{track_id}{found_source.suffix.lower()}"
            shutil.copy2(found_source, orig_dest)

            norm_dest = normalized_dir / f"{track_id}.wav"
            stats = normalize_music_asset(orig_dest, norm_dest, REFERENCE_MUSIC_LUFS, -1.0, REFERENCE_SAMPLE_RATE)

            library_data["tracks"][track_id] = {
                "track_id": track_id,
                "category": category,
                "original_filename": found_source.name,
                "original_file": str(orig_dest),
                "normalized_file": str(norm_dest),
                "duration_sec": stats["duration_sec"],
                "integrated_lufs": stats["integrated_lufs"],
                "true_peak_db": stats["true_peak_db"],
                "normalized_status": "READY"
            }
        else:
            # Tạo silent dummy track nếu chưa có file
            norm_dest = normalized_dir / f"{track_id}.wav"
            sf.write(str(norm_dest), np.zeros(int(REFERENCE_SAMPLE_RATE * 30), dtype=np.float32), REFERENCE_SAMPLE_RATE)
            library_data["tracks"][track_id] = {
                "track_id": track_id,
                "category": category,
                "original_filename": f"{track_id}.wav",
                "original_file": str(norm_dest),
                "normalized_file": str(norm_dest),
                "duration_sec": 30.0,
                "integrated_lufs": -99.0,
                "true_peak_db": -99.0,
                "normalized_status": "DUMMY"
            }

    with open(lib_json_path, "w", encoding="utf-8") as f:
        json.dump(library_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Khởi tạo Music Library thành công với {len(library_data['tracks'])} tracks tại {lib_dir}.")
    return library_data


def save_global_music_library(library_data: dict, lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> None:
    """Lưu metadata Music Library vào library.json."""
    lib_dir = Path(lib_dir)
    lib_dir.mkdir(parents=True, exist_ok=True)
    with open(lib_dir / "library.json", "w", encoding="utf-8") as f:
        json.dump(library_data, f, ensure_ascii=False, indent=2)


def import_track_to_library(
    category: str,
    track_id: str,
    file_source: Union[str, Path],
    lib_dir: Path = GLOBAL_MUSIC_LIB_DIR
) -> Tuple[bool, str, dict]:
    """
    Import một file nhạc mới (MP3/WAV/M4A) vào category chỉ định.
    Tự động phân tích, convert sang 48kHz WAV, normalize về -24 LUFS và lưu vào Library.
    """
    lib_dir = Path(lib_dir)
    original_dir = lib_dir / "original"
    normalized_dir = lib_dir / "normalized"
    original_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    src_p = Path(file_source)
    if not src_p.exists():
        return False, f"File không tồn tại: {src_p}", {}

    category = category.upper().strip()
    if category not in DEFAULT_CATEGORY_CONFIG:
        return False, f"Danh mục '{category}' không hợp lệ. Phải thuộc: {list(DEFAULT_CATEGORY_CONFIG.keys())}", {}

    ext = src_p.suffix.lower()
    if ext not in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
        return False, f"Định dạng âm thanh '{ext}' không được hỗ trợ.", {}

    orig_dest = original_dir / f"{track_id}{ext}"
    shutil.copy2(src_p, orig_dest)

    norm_dest = normalized_dir / f"{track_id}.wav"
    norm_stats = normalize_music_asset(orig_dest, norm_dest, REFERENCE_MUSIC_LUFS, -1.0, REFERENCE_SAMPLE_RATE)

    lib_data = init_global_music_library(lib_dir)
    lib_data.setdefault("tracks", {})[track_id] = {
        "track_id": track_id,
        "category": category,
        "original_filename": src_p.name,
        "original_file": str(orig_dest),
        "normalized_file": str(norm_dest),
        "duration_sec": norm_stats["duration_sec"],
        "integrated_lufs": norm_stats["integrated_lufs"],
        "true_peak_db": norm_stats["true_peak_db"],
        "normalized_status": "READY"
    }

    # Cập nhật default track của category nếu cần
    lib_data.setdefault("categories", DEFAULT_CATEGORY_CONFIG).setdefault(category, {})["default_track"] = track_id
    save_global_music_library(lib_data, lib_dir)

    return True, f"Import & Normalize thành công: {track_id} ({norm_stats['duration_sec']}s, {norm_stats['integrated_lufs']} LUFS)", lib_data["tracks"][track_id]


def get_music_library_table_data(lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> List[List[Any]]:
    """Tạo bảng dữ liệu hiển thị trên Web UI cho Music Library."""
    lib_data = init_global_music_library(lib_dir)
    tracks = lib_data.get("tracks", {})
    categories = lib_data.get("categories", DEFAULT_CATEGORY_CONFIG)

    rows = []
    for cat_name, cat_cfg in categories.items():
        if cat_name == "DRY":
            continue
        def_tid = cat_cfg.get("default_track", "")
        tinfo = tracks.get(def_tid, {})
        dur_txt = f"{tinfo.get('duration_sec', 0.0):.1f}s" if tinfo else "—"
        lufs_txt = f"{tinfo.get('integrated_lufs', -99.0):.1f} LUFS" if tinfo else "—"
        tp_txt = f"{tinfo.get('true_peak_db', -99.0):.1f} dBTP" if tinfo else "—"
        status_txt = "✅ Sẵn sàng" if tinfo.get("normalized_status") == "READY" else "⚠️ Thiếu file"

        rows.append([
            cat_name,
            cat_cfg.get("display_name", cat_name),
            def_tid,
            tinfo.get("original_filename", "—"),
            dur_txt,
            lufs_txt,
            tp_txt,
            f"{cat_cfg.get('default_level_db', -35.0):.1f} dB",
            status_txt
        ])
    return rows


def resolve_track_file_for_cue(cue_name: str, project_overrides: dict = None, lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> Optional[Path]:
    """
    Tìm file normalized 48kHz WAV cho một cue hoặc category.
    Ưu tiên: project_overrides > library default track.
    """
    cue_upper = cue_name.upper().strip()
    if cue_upper == "DRY" or cue_upper == "NONE":
        return None

    lib_data = init_global_music_library(lib_dir)
    tracks = lib_data.get("tracks", {})
    categories = lib_data.get("categories", DEFAULT_CATEGORY_CONFIG)

    # 1. Project override trực tiếp
    if project_overrides and cue_upper in project_overrides:
        target_track_id = project_overrides[cue_upper]
        if target_track_id in tracks:
            p = Path(tracks[target_track_id].get("normalized_file", ""))
            if p.exists():
                return p

    # 2. Khớp category chuẩn
    if cue_upper in categories:
        def_tid = categories[cue_upper].get("default_track")
        if def_tid in tracks:
            p = Path(tracks[def_tid].get("normalized_file", ""))
            if p.exists():
                return p

    # 3. Khớp track_id trực tiếp
    if cue_upper in tracks:
        p = Path(tracks[cue_upper].get("normalized_file", ""))
        if p.exists():
            return p

    # 4. Alias mapping từ tên cue V6 cũ (e.g. signature_intro, mystery_low, tension_low, etc.)
    alias_map = {
        "SIGNATURE_INTRO": "INTRO",
        "SIGNATURE_OUTRO": "OUTRO",
        "MYSTERY_LOW": "MYSTERY",
        "TENSION_LOW": "TENSION",
        "EMOTIONAL_LOW": "EMOTIONAL",
        "MEMORY_SOFT": "REFLECTION",
        "CLOSING_SOFT": "REFLECTION"
    }
    if cue_upper in alias_map:
        mapped_cat = alias_map[cue_upper]
        def_tid = categories.get(mapped_cat, {}).get("default_track")
        if def_tid in tracks:
            p = Path(tracks[def_tid].get("normalized_file", ""))
            if p.exists():
                return p

    return None


# ==============================================================================
# 3. CLEAN VOICE MASTER BUILDER (voice_master.wav)
# ==============================================================================

def build_clean_voice_master(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    gap_rule: str = "max",
    default_gap: float = 0.18,
    sample_rate: int = REFERENCE_SAMPLE_RATE
) -> Tuple[bool, str, Optional[Path], List[dict]]:
    """
    Ráp các take đã chọn thành voice_master.wav.
    TUYỆT ĐỐI CHỈ GỒM: Voice + Pause/Silence theo JSON.
    KHÔNG room tone, KHÔNG white noise, KHÔNG ambience, KHÔNG music.
    Đây là clean voice master bắt buộc được giữ lại độc lập.
    """
    project_dir = Path(project_dir)
    master_dir = project_dir / "master"
    master_dir.mkdir(parents=True, exist_ok=True)
    voice_master_path = master_dir / "voice_master.wav"

    segments_state = project_state.get("segments", {}) if project_state else {}
    audio_pieces: List[np.ndarray] = []
    timeline_events: List[dict] = []
    current_sample = 0

    total_segs = len(segments)
    for idx, seg in enumerate(segments):
        seg_id = str(seg.get("id", idx + 1)).zfill(3)
        speaker = seg.get("speaker", "MINH")

        # Xác định file take đã chọn
        seg_st = segments_state.get(seg_id, {})
        sel_rel = seg_st.get("selected_file") or f"selected/{seg_id}.wav"
        seg_file = project_dir / sel_rel

        # Fallback nếu chưa có trong selected: tìm trong raw take 01
        if not seg_file.exists():
            cand_raw = list((project_dir / "raw").glob(f"{seg_id}_*take01.wav"))
            if cand_raw:
                seg_file = cand_raw[0]

        if not seg_file.exists():
            return False, f"Thiếu audio cho phân đoạn {seg_id} ({seg_file.name}). Vui lòng sinh TTS trước.", None, []

        try:
            wav_data, sr = sf.read(str(seg_file), dtype="float32")
            if sr != sample_rate:
                from apps.audio_director import resample_audio
                wav_data = resample_audio(wav_data, sr, sample_rate)
            if wav_data.ndim > 1:
                wav_data = np.mean(wav_data, axis=1)
        except Exception as e:
            return False, f"Lỗi đọc file {seg_file}: {e}", None, []

        # Khoảng lặng trước câu
        p_before = float(seg.get("pause_before", 0.0) or 0.0)
        if idx == 0 and p_before > 0:
            silence_samples = int(p_before * sample_rate)
            audio_pieces.append(np.zeros(silence_samples, dtype=np.float32))
            current_sample += silence_samples

        speech_start_sample = current_sample
        speech_start_sec = speech_start_sample / sample_rate

        audio_pieces.append(wav_data)
        current_sample += len(wav_data)

        speech_end_sample = current_sample
        speech_end_sec = speech_end_sample / sample_rate
        speech_dur_sec = speech_end_sec - speech_start_sec

        # Lưu event chi tiết cho timeline
        timeline_events.append({
            "id": seg_id,
            "speaker": speaker,
            "text": seg.get("text", ""),
            "speech_start_sec": speech_start_sec,
            "speech_end_sec": speech_end_sec,
            "duration_sec": speech_dur_sec,
            "speech_start_sample": speech_start_sample,
            "speech_end_sample": speech_end_sample,
            "delivery_profile": (seg.get("delivery_profile") or "NORMAL").upper(),
            "audio_region": (seg.get("audio_region") or "CLEAN").upper(),
            "music_cue": str(seg.get("music_cue") or "none"),
            "music_volume_db": seg.get("music_volume_db"),
            "importance": str(seg.get("importance") or "normal").lower(),
            "pause_before": p_before,
            "pause_after": float(seg.get("pause_after", 0.18) or 0.18),
            "music_obj": seg.get("music", {})
        })

        # Xử lý khoảng lặng sau câu (tránh double pause)
        p_after = float(seg.get("pause_after", default_gap) or default_gap)
        if idx < total_segs - 1:
            next_seg = segments[idx + 1]
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
            if p_after > 0:
                silence_samples = int(p_after * sample_rate)
                audio_pieces.append(np.zeros(silence_samples, dtype=np.float32))
                current_sample += silence_samples

    voice_audio = np.concatenate(audio_pieces) if audio_pieces else np.zeros(0, dtype=np.float32)
    sf.write(str(voice_master_path), voice_audio, sample_rate, subtype="PCM_24")

    total_sec = len(voice_audio) / sample_rate
    logger.info(f"Đã xuất Clean Voice Master: {voice_master_path} ({total_sec:.2f}s).")
    return True, f"Đã tạo Clean Voice Master ({total_sec/60:.1f} phút)!", voice_master_path, timeline_events


# ==============================================================================
# 4. DELIVERY PROFILE → MUSIC LOGIC & CUE SHEET ENGINE
# ==============================================================================

def infer_music_cue_for_segment(seg_info: dict) -> Tuple[str, float, float, float]:
    """
    Xác định Music Cue cho từng segment theo thứ tự ưu tiên:
    explicit music object > music_cue > audio_region > delivery_profile > DRY.
    Trả về: (cue_category, level_db, fade_in_sec, fade_out_sec)
    """
    # 1. Explicit music object trong JSON
    m_obj = seg_info.get("music_obj") or {}
    if isinstance(m_obj, dict) and m_obj.get("cue"):
        cue = str(m_obj.get("cue")).upper().strip()
        lvl = float(m_obj.get("level_db", -35.0))
        f_in = float(m_obj.get("fade_in_sec", 2.0))
        f_out = float(m_obj.get("fade_out_sec", 2.5))
        return cue, lvl, f_in, f_out

    # 2. music_cue field
    m_cue = str(seg_info.get("music_cue", "")).strip().upper()
    if m_cue and m_cue not in ["NONE", "FADE_OUT", ""]:
        alias = {
            "SIGNATURE_INTRO": "INTRO",
            "SIGNATURE_OUTRO": "OUTRO",
            "MYSTERY_LOW": "MYSTERY",
            "TENSION_LOW": "TENSION",
            "EMOTIONAL_LOW": "EMOTIONAL",
            "MEMORY_SOFT": "REFLECTION",
            "CLOSING_SOFT": "REFLECTION"
        }
        mapped_cat = alias.get(m_cue, m_cue)
        cfg = DEFAULT_CATEGORY_CONFIG.get(mapped_cat, DEFAULT_CATEGORY_CONFIG["MYSTERY"])
        lvl = float(seg_info.get("music_volume_db") or cfg["default_level_db"])
        return mapped_cat, lvl, cfg["fade_in_sec"], cfg["fade_out_sec"]

    # 3. audio_region field
    a_region = str(seg_info.get("audio_region", "")).strip().upper()
    if a_region and a_region not in ["CLEAN", "DRY", "SILENCE_REVEAL", "NONE"]:
        if a_region in DEFAULT_CATEGORY_CONFIG:
            cfg = DEFAULT_CATEGORY_CONFIG[a_region]
            lvl = float(seg_info.get("music_volume_db") or cfg["default_level_db"])
            return a_region, lvl, cfg["fade_in_sec"], cfg["fade_out_sec"]

    # 4. delivery_profile field (V9.1 default rules)
    d_prof = str(seg_info.get("delivery_profile", "")).strip().upper()
    if d_prof == "HOOK":
        cfg = DEFAULT_CATEGORY_CONFIG["INTRO"]
        return "INTRO", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
    elif d_prof == "MYSTERY":
        cfg = DEFAULT_CATEGORY_CONFIG["MYSTERY"]
        return "MYSTERY", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
    elif d_prof == "TENSION":
        cfg = DEFAULT_CATEGORY_CONFIG["TENSION"]
        return "TENSION", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
    elif d_prof == "ENDING":
        # Mặc định kết thúc dùng REFLECTION trước, OUTRO ở câu chót
        cfg = DEFAULT_CATEGORY_CONFIG["REFLECTION"]
        return "REFLECTION", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
    elif d_prof in ["REVEAL", "NORMAL", "COMMENT"]:
        return "DRY", -99.0, 0.0, 0.0

    return "DRY", -99.0, 0.0, 0.0


def is_major_reveal_segment(seg_info: dict) -> bool:
    """
    Kiểm tra segment có thuộc Major Reveal không.
    Bao gồm: delivery_profile == REVEAL, importance == critical, hoặc chứa từ khóa cốt lõi.
    """
    if str(seg_info.get("delivery_profile", "")).upper() == "REVEAL":
        return True
    if str(seg_info.get("audio_region", "")).upper() == "SILENCE_REVEAL":
        return True
    if str(seg_info.get("importance", "")).lower() == "critical":
        return True

    text = str(seg_info.get("text", "")).lower()
    keywords = ["ngày mất", "mười bốn năm trước", "qua đời", "là cậu ruột tôi", "chuyển tiền cho ai"]
    for kw in keywords:
        if kw in text:
            return True

    return False


def generate_cue_sheet_from_segments(
    timeline_events: List[dict],
    music_overrides: Optional[dict] = None,
    pre_reveal_clearance: float = 2.0,
    post_reveal_clearance: float = 2.5,
    merge_gap_threshold: float = 3.0,
    hook_cap_sec: float = 30.0,
    total_episode_sec: float = 0.0
) -> List[dict]:
    """
    Tự động xây dựng Cue Sheet tối ưu từ chuỗi timeline events:
    1. Xác định Cue và Level cho từng segment.
    2. Áp dụng Major Reveal Safety Rule: Fade out trước reveal (pre_reveal_clearance), giữ DRY tuyệt đối, trễ post_reveal_clearance mới vào nhạc mới.
    3. Gộp các segment liên tiếp có cùng cue thành 1 Region duy nhất (KHÔNG restart nhạc).
    4. Giới hạn thời lượng INTRO nếu hook quá dài (mục tiêu 15-30s).
    """
    if not timeline_events:
        return []

    # 1. Gán cue dự kiến cho từng segment
    raw_cues = []
    for ev in timeline_events:
        is_reveal = is_major_reveal_segment(ev)
        if is_reveal:
            cue, lvl, f_in, f_out = "DRY", -99.0, 0.0, 0.0
        else:
            cue, lvl, f_in, f_out = infer_music_cue_for_segment(ev)

        # Áp dụng override nếu có
        if music_overrides and cue in music_overrides:
            override_val = music_overrides[cue]
            if isinstance(override_val, dict):
                lvl = float(override_val.get("level_db", lvl))
                f_in = float(override_val.get("fade_in_sec", f_in))
                f_out = float(override_val.get("fade_out_sec", f_out))
            elif isinstance(override_val, (int, float)):
                lvl = float(override_val)

        raw_cues.append({
            "id": ev["id"],
            "speech_start": ev["speech_start_sec"],
            "speech_end": ev["speech_end_sec"],
            "cue": cue,
            "level_db": lvl,
            "fade_in_sec": f_in,
            "fade_out_sec": f_out,
            "is_reveal": is_reveal
        })

    # 2. Xử lý Major Reveal Clearance
    # Tìm tất cả các khoảng thời gian bị khóa bởi Reveal: [start - pre, end + post]
    reveal_blocks = []
    for ev in raw_cues:
        if ev["is_reveal"]:
            b_start = max(0.0, ev["speech_start"] - pre_reveal_clearance)
            b_end = ev["speech_end"] + post_reveal_clearance
            reveal_blocks.append((b_start, b_end, ev["id"]))

    # 3. Gộp các segment có cùng cue thành Music Regions
    regions: List[dict] = []
    current_reg: Optional[dict] = None

    for idx, item in enumerate(raw_cues):
        cue = item["cue"]
        st = item["speech_start"]
        en = item["speech_end"]

        # Nếu segment rơi vào vùng Reveal thì bắt buộc đóng region hiện tại
        in_reveal_zone = False
        for rb_st, rb_en, r_id in reveal_blocks:
            if not (en <= rb_st or st >= rb_en):
                in_reveal_zone = True
                break

        if in_reveal_zone or cue == "DRY":
            if current_reg is not None:
                # Cắt ngắn region hiện tại nếu lấn vào reveal
                for rb_st, rb_en, r_id in reveal_blocks:
                    if current_reg["end_sec"] > rb_st and current_reg["start_sec"] < rb_st:
                        current_reg["end_sec"] = rb_st
                        break
                regions.append(current_reg)
                current_reg = None
            continue

        # Kiểm tra xem có thể gộp với region hiện tại không
        if current_reg is not None and current_reg["cue"] == cue:
            gap = st - current_reg["end_sec"]
            if gap <= merge_gap_threshold:
                # Kéo dài region hiện tại
                current_reg["end_sec"] = en
                current_reg["segments"].append(item["id"])
                continue
            else:
                # Khoảng cách quá lớn, chốt region cũ và tạo mới
                regions.append(current_reg)
                current_reg = None

        # Nếu đang có region khác cue, chốt region cũ
        if current_reg is not None:
            regions.append(current_reg)
            current_reg = None

        # Bắt đầu region mới
        # Nếu ngay trước đó là reveal block, đảm bảo start_sec >= rb_en
        actual_start = st
        for rb_st, rb_en, r_id in reveal_blocks:
            if rb_st <= st < rb_en:
                actual_start = rb_en
                break

        if actual_start < en:
            current_reg = {
                "cue": cue,
                "start_sec": actual_start,
                "end_sec": en,
                "level_db": item["level_db"],
                "fade_in_sec": item["fade_in_sec"],
                "fade_out_sec": item["fade_out_sec"],
                "segments": [item["id"]]
            }

    if current_reg is not None:
        regions.append(current_reg)

    # 4. Áp dụng hook cap cho INTRO nếu quá dài (15-30s)
    for reg in regions:
        if reg["cue"] == "INTRO" and (reg["end_sec"] - reg["start_sec"]) > hook_cap_sec:
            reg["end_sec"] = reg["start_sec"] + hook_cap_sec

    # 5. Chuyển đổi thành danh sách Cue Sheet đầy đủ (bao gồm cả các vùng DRY)
    cue_sheet: List[dict] = []
    last_pos = 0.0

    # Lấy thông tin track mặc định
    lib_data = init_global_music_library()
    categories = lib_data.get("categories", DEFAULT_CATEGORY_CONFIG)

    for reg in regions:
        # Nếu có khoảng trống giữa các region, tạo mục DRY
        if reg["start_sec"] > last_pos + 0.1:
            dry_dur = reg["start_sec"] - last_pos
            cue_sheet.append({
                "start_sec": round(last_pos, 2),
                "end_sec": round(reg["start_sec"], 2),
                "duration_sec": round(dry_dur, 2),
                "cue": "DRY",
                "track": "NO_MUSIC",
                "level_db": -99.0,
                "fade_in_sec": 0.0,
                "fade_out_sec": 0.0,
                "source": "Voice Only / Reveal Silence"
            })

        dur = reg["end_sec"] - reg["start_sec"]
        cat_cfg = categories.get(reg["cue"], {})
        def_trk = cat_cfg.get("default_track", f"SCC_{reg['cue']}_01")

        cue_sheet.append({
            "start_sec": round(reg["start_sec"], 2),
            "end_sec": round(reg["end_sec"], 2),
            "duration_sec": round(dur, 2),
            "cue": reg["cue"],
            "track": def_trk,
            "level_db": round(reg["level_db"], 1),
            "fade_in_sec": round(reg["fade_in_sec"], 2),
            "fade_out_sec": round(reg["fade_out_sec"], 2),
            "source": f"Auto Region ({', '.join(reg['segments'][:3])}{'...' if len(reg['segments'])>3 else ''})"
        })
        last_pos = reg["end_sec"]

    # Đóng đuôi DRY nếu còn thời gian đến hết tập
    if total_episode_sec > last_pos + 0.1:
        cue_sheet.append({
            "start_sec": round(last_pos, 2),
            "end_sec": round(total_episode_sec, 2),
            "duration_sec": round(total_episode_sec - last_pos, 2),
            "cue": "DRY",
            "track": "NO_MUSIC",
            "level_db": -99.0,
            "fade_in_sec": 0.0,
            "fade_out_sec": 0.0,
            "source": "End of Episode"
        })

    return cue_sheet


# ==============================================================================
# 5. MUSIC COVERAGE METRIC & TIMELINE VISUALIZER
# ==============================================================================

def calculate_music_coverage(cue_sheet: List[dict], total_episode_sec: float) -> dict:
    """
    Tính toán chỉ số Music Coverage:
    Total Episode duration, Music duration, Dry duration, Coverage percentage.
    Đưa ra khuyến nghị 25–40% và cảnh báo nếu >60%.
    """
    if total_episode_sec <= 0:
        total_episode_sec = max([c["end_sec"] for c in cue_sheet], default=0.0)

    music_dur = 0.0
    for c in cue_sheet:
        if c.get("cue", "").upper() != "DRY" and c.get("track", "") != "NO_MUSIC":
            music_dur += float(c.get("duration_sec", 0.0))

    dry_dur = max(0.0, total_episode_sec - music_dur)
    cov_pct = (music_dur / total_episode_sec * 100.0) if total_episode_sec > 0 else 0.0

    is_high = cov_pct > 60.0
    warn_msg = "⚠️ **Cảnh báo:** Music coverage đang cao (> 60%). Định dạng storytelling nên có nhiều vùng voice sạch (DRY) để tạo sự chú ý và giữ trọng lượng cảm xúc." if is_high else ""

    def fmt_time(sec: float) -> str:
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02d}:{s:02d}"

    return {
        "total_episode_sec": round(total_episode_sec, 1),
        "total_episode_fmt": fmt_time(total_episode_sec),
        "music_duration_sec": round(music_dur, 1),
        "music_duration_fmt": fmt_time(music_dur),
        "dry_duration_sec": round(dry_dur, 1),
        "dry_duration_fmt": fmt_time(dry_dur),
        "coverage_percent": round(cov_pct, 1),
        "target_recommendation": "25% – 40%",
        "is_high_coverage": is_high,
        "warning_message": warn_msg
    }


def generate_visual_timeline_html(cue_sheet: List[dict], timeline_events: List[dict], total_duration_sec: float) -> str:
    """
    Tạo visual timeline HTML hiển thị trực quan dải Voice và các dải Music Cue / DRY regions.
    """
    if total_duration_sec <= 0:
        total_duration_sec = max([c["end_sec"] for c in cue_sheet], default=1.0)

    color_map = {
        "INTRO": "#3b82f6",       # Blue
        "MYSTERY": "#8b5cf6",     # Purple
        "TENSION": "#ef4444",     # Red
        "EMOTIONAL": "#ec4899",   # Pink
        "REFLECTION": "#06b6d4",  # Cyan
        "OUTRO": "#6366f1",       # Indigo
        "DRY": "#4b5563"          # Slate/Gray
    }

    music_blocks = []
    for item in cue_sheet:
        cue = item.get("cue", "DRY").upper()
        st = item.get("start_sec", 0.0)
        en = item.get("end_sec", 0.0)
        trk = item.get("track", "")
        left_pct = (st / total_duration_sec) * 100.0
        width_pct = max(0.5, ((en - st) / total_duration_sec) * 100.0)
        col = color_map.get(cue, "#9ca3af")
        lvl = f"{item.get('level_db', -35):.1f}dB" if cue != "DRY" else "DRY"
        label = f"{cue} ({lvl})" if width_pct > 6 else (cue if width_pct > 3 else "")

        block = (
            f'<div style="position: absolute; left: {left_pct:.2f}%; width: {width_pct:.2f}%; '
            f'height: 28px; background-color: {col}; border-radius: 4px; overflow: hidden; '
            f'display: flex; align-items: center; justify-content: center; color: white; '
            f'font-size: 11px; font-weight: bold; text-overflow: ellipsis; white-space: nowrap; '
            f'box-shadow: 0 1px 2px rgba(0,0,0,0.2);" title="{cue}: {st:.1f}s → {en:.1f}s ({trk})">'
            f'{label}</div>'
        )
        music_blocks.append(block)

    voice_blocks = []
    for ev in timeline_events:
        st = ev.get("speech_start_sec", 0.0)
        en = ev.get("speech_end_sec", 0.0)
        left_pct = (st / total_duration_sec) * 100.0
        width_pct = max(0.2, ((en - st) / total_duration_sec) * 100.0)
        is_crit = is_major_reveal_segment(ev)
        v_col = "#eab308" if is_crit else "#10b981"  # Yellow for reveal, Emerald for normal voice
        ev_id = ev.get("id", "")
        ev_spk = ev.get("speaker", "")
        ev_text = ev.get("text", "")[:30]

        block = (
            f'<div style="position: absolute; left: {left_pct:.2f}%; width: {width_pct:.2f}%; '
            f'height: 20px; background-color: {v_col}; border-radius: 2px; '
            f'title="[{ev_id}] {ev_spk}: {ev_text}... ({st:.1f}s → {en:.1f}s)"></div>'
        )
        voice_blocks.append(block)

    m = int(total_duration_sec // 60)
    s = int(total_duration_sec % 60)
    dur_str = f"{m:02d}:{s:02d}"

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1f2937; padding: 14px; border-radius: 8px; color: #f3f4f6; margin-top: 8px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="font-size: 13px; font-weight: 600;">📊 Timeline Phân đoạn Âm thanh (Audio Cue Timeline)</span>
        <span style="font-size: 12px; color: #9ca3af;">Tổng thời lượng: <b>{dur_str}</b></span>
      </div>
      
      <!-- Voice Track -->
      <div style="margin-bottom: 10px;">
        <div style="font-size: 11px; color: #10b981; font-weight: 600; margin-bottom: 4px;">🎙️ VOICE (Lời thoại sạch - Vàng: Major Reveal)</div>
        <div style="position: relative; width: 100%; height: 20px; background: #374151; border-radius: 3px;">
          {''.join(voice_blocks)}
        </div>
      </div>
      
      <!-- Music Track -->
      <div>
        <div style="font-size: 11px; color: #60a5fa; font-weight: 600; margin-bottom: 4px;">🎵 MUSIC BED (Continuous Underscore & Reveal Clearance)</div>
        <div style="position: relative; width: 100%; height: 28px; background: #374151; border-radius: 4px;">
          {''.join(music_blocks)}
        </div>
      </div>
      
      <!-- Legend -->
      <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; font-size: 11px; color: #d1d5db;">
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #3b82f6; border-radius: 2px;"></span> INTRO</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #8b5cf6; border-radius: 2px;"></span> MYSTERY</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #ef4444; border-radius: 2px;"></span> TENSION</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #ec4899; border-radius: 2px;"></span> EMOTIONAL</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #06b6d4; border-radius: 2px;"></span> REFLECTION</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #6366f1; border-radius: 2px;"></span> OUTRO</span>
        <span><span style="display: inline-block; width: 10px; height: 10px; background: #4b5563; border-radius: 2px;"></span> DRY (Voice Sạch)</span>
      </div>
    </div>
    """
    return html


# ==============================================================================
# 6. MUSIC BED RENDERER (Loop, Smooth Fades & Gain)
# ==============================================================================

def render_music_bed(
    cue_sheet: List[dict],
    total_samples: int,
    project_overrides: Optional[dict] = None,
    sample_rate: int = REFERENCE_SAMPLE_RATE,
    loop_crossfade_sec: float = 3.0
) -> np.ndarray:
    """
    Kết xuất toàn bộ track nhạc nền (music_mix) theo Cue Sheet:
    - Nạp file 48kHz WAV normalized (-24 LUFS reference).
    - Loop liền mạch với crossfade 3.0s nếu region dài hơn track.
    - Smooth equal-power fade in / fade out.
    - Áp dụng gain chính xác theo dB: gain = 10 ** ((level_db - (-24)) / 20).
    - Vùng DRY và Reveal Clearance tuyệt đối im lặng (0.0).
    """
    music_bed = np.zeros(total_samples, dtype=np.float32)

    for item in cue_sheet:
        cue = item.get("cue", "DRY").upper()
        if cue == "DRY" or item.get("track") == "NO_MUSIC":
            continue

        track_file = resolve_track_file_for_cue(cue, project_overrides)
        if not track_file or not track_file.exists():
            logger.warning(f"Không tìm thấy file nhạc cho cue '{cue}'.")
            continue

        try:
            raw_wav, sr = sf.read(str(track_file), dtype="float32")
            if sr != sample_rate:
                from apps.audio_director import resample_audio
                raw_wav = resample_audio(raw_wav, sr, sample_rate)
            if raw_wav.ndim > 1:
                raw_wav = np.mean(raw_wav, axis=1)
        except Exception as e:
            logger.warning(f"Lỗi đọc nhạc {track_file}: {e}")
            continue

        st_sec = float(item["start_sec"])
        en_sec = float(item["end_sec"])
        st_sample = max(0, int(st_sec * sample_rate))
        en_sample = min(total_samples, int(en_sec * sample_rate))
        region_len = en_sample - st_sample
        if region_len <= 0:
            continue

        # 1. Loop audio nếu region dài hơn track
        raw_len = len(raw_wav)
        if region_len > raw_len:
            xfade_samp = min(int(loop_crossfade_sec * sample_rate), raw_len // 4)
            step = raw_len - xfade_samp
            num_loops = int(math.ceil(region_len / max(1, step))) + 1
            full_looped = np.zeros(num_loops * step + xfade_samp, dtype=np.float32)
            pos = 0
            for l_idx in range(num_loops):
                if l_idx == 0:
                    full_looped[:raw_len] += raw_wav
                    pos = step
                else:
                    # Crossfade nối mép
                    fade_out = np.cos(0.5 * np.pi * np.linspace(0, 1, xfade_samp, endpoint=False)) ** 2
                    fade_in = np.sin(0.5 * np.pi * np.linspace(0, 1, xfade_samp, endpoint=False)) ** 2
                    full_looped[pos:pos + xfade_samp] = (full_looped[pos:pos + xfade_samp] * fade_out) + (raw_wav[:xfade_samp] * fade_in)
                    full_looped[pos + xfade_samp:pos + raw_len] += raw_wav[xfade_samp:]
                    pos += step
            chunk = full_looped[:region_len]
        else:
            chunk = raw_wav[:region_len].copy()

        # 2. Áp dụng Smooth Fade In & Fade Out
        f_in_sec = float(item.get("fade_in_sec", 2.0))
        f_out_sec = float(item.get("fade_out_sec", 2.5))
        f_in_samp = min(int(f_in_sec * sample_rate), region_len // 2)
        f_out_samp = min(int(f_out_sec * sample_rate), region_len // 2)

        if f_in_samp > 0:
            fade_in_curve = np.sin(0.5 * np.pi * np.linspace(0, 1, f_in_samp, endpoint=False)) ** 2
            chunk[:f_in_samp] *= fade_in_curve

        if f_out_samp > 0:
            fade_out_curve = np.cos(0.5 * np.pi * np.linspace(0, 1, f_out_samp, endpoint=False)) ** 2
            chunk[-f_out_samp:] *= fade_out_curve

        # 3. Áp dụng Target Level (dB) so với reference -24.0 LUFS
        lvl_db = float(item.get("level_db", -35.0))
        gain = 10.0 ** ((lvl_db - REFERENCE_MUSIC_LUFS) / 20.0)
        chunk *= gain

        # Trộn vào music_bed
        music_bed[st_sample:en_sample] += chunk

    return music_bed


# ==============================================================================
# 7. GENTLE DIALOGUE DUCKING
# ==============================================================================

def apply_gentle_ducking(
    music_audio: np.ndarray,
    timeline_events: List[dict],
    sample_rate: int = REFERENCE_SAMPLE_RATE,
    ducking_db: float = -2.5,
    attack_ms: float = 150.0,
    release_ms: float = 800.0
) -> np.ndarray:
    """
    Bộ lọc Gentle Ducking analog-style (-2.5 dB khi MC nói):
    - Attack mềm mại 150ms: tránh click/pop.
    - Release tự nhiên 800ms: không tạo hiệu ứng pumping.
    - Control rate 100 Hz nội suy tuyến tính, tiết kiệm CPU.
    """
    total_samples = len(music_audio)
    if total_samples == 0:
        return music_audio

    frame_step = int(sample_rate / 100) # 480 samples = 10ms
    num_frames = int(math.ceil(total_samples / frame_step))
    target_gains = np.ones(num_frames, dtype=np.float32)

    duck_gain = 10.0 ** (ducking_db / 20.0)

    for ev in timeline_events:
        st_samp = ev.get("speech_start_sample", int(ev.get("speech_start_sec", 0.0) * sample_rate))
        en_samp = ev.get("speech_end_sample", int(ev.get("speech_end_sec", 0.0) * sample_rate))
        st_f = max(0, int(st_samp / frame_step))
        en_f = min(num_frames, int(en_samp / frame_step))
        target_gains[st_f:en_f] = np.minimum(target_gains[st_f:en_f], duck_gain)

    # Lọc IIR làm mịn attack và release
    att_f = max(1, int((attack_ms / 1000.0) * 100))
    rel_f = max(1, int((release_ms / 1000.0) * 100))
    alpha_att = 1.0 - math.exp(-1.0 / att_f)
    alpha_rel = 1.0 - math.exp(-1.0 / rel_f)

    smooth_gains = np.empty(num_frames, dtype=np.float32)
    current_g = 1.0
    for i in range(num_frames):
        target = target_gains[i]
        if target < current_g:
            current_g += alpha_att * (target - current_g)
        else:
            current_g += alpha_rel * (target - current_g)
        smooth_gains[i] = current_g

    # Nội suy lên full sample rate
    gain_curve = np.interp(
        np.arange(total_samples),
        np.arange(num_frames) * frame_step,
        smooth_gains
    ).astype(np.float32)

    return music_audio * gain_curve


# ==============================================================================
# 8. FINAL MIX & 2-PASS MASTERING (-14 LUFS, -1 dBTP)
# ==============================================================================

def build_final_mix(
    project_dir: Path,
    voice_master_path: Path,
    cue_sheet: List[dict],
    timeline_events: List[dict],
    project_overrides: Optional[dict] = None,
    enable_ducking: bool = False,
    ducking_db: float = -2.5,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    sample_rate: int = REFERENCE_SAMPLE_RATE
) -> Tuple[bool, str, dict]:
    """
    Quy trình hòa âm & Master hoàn thiện:
    1. Đọc voice_master.wav.
    2. Render music_bed theo cue_sheet.
    3. Áp dụng gentle ducking (nếu bật).
    4. Xuất master/music_mix.wav.
    5. Cộng tổng: final_mix_pre_master.wav = voice_master + music_mix.
    6. 2-pass Loudness Normalization sang -14 LUFS, -1 dBTP.
    7. Xuất master/final_mix.wav và master/final_mix.mp3 (320kbps).
    8. Lưu mix/cue_sheet.json và mix/mix_report.json.
    """
    project_dir = Path(project_dir)
    master_dir = project_dir / "master"
    mix_dir = project_dir / "mix"
    master_dir.mkdir(parents=True, exist_ok=True)
    mix_dir.mkdir(parents=True, exist_ok=True)

    voice_master_path = Path(voice_master_path)
    if not voice_master_path.exists():
        return False, f"Không tìm thấy Voice Master tại: {voice_master_path}", {}

    voice_wav, sr = sf.read(str(voice_master_path), dtype="float32")
    if sr != sample_rate:
        from apps.audio_director import resample_audio
        voice_wav = resample_audio(voice_wav, sr, sample_rate)
    if voice_wav.ndim > 1:
        voice_wav = np.mean(voice_wav, axis=1)

    total_samples = len(voice_wav)
    total_sec = total_samples / sample_rate

    # 1. Render music bed
    music_bed = render_music_bed(
        cue_sheet=cue_sheet,
        total_samples=total_samples,
        project_overrides=project_overrides,
        sample_rate=sample_rate
    )

    # 2. Ducking nếu bật
    if enable_ducking:
        music_bed = apply_gentle_ducking(
            music_audio=music_bed,
            timeline_events=timeline_events,
            sample_rate=sample_rate,
            ducking_db=ducking_db
        )

    # 3. Lưu music_mix.wav
    music_mix_path = master_dir / "music_mix.wav"
    sf.write(str(music_mix_path), music_bed, sample_rate, subtype="PCM_24")

    # 4. Trộn pre-master
    pre_master = voice_wav + music_bed
    pre_master_path = master_dir / "final_mix_pre_master.wav"
    sf.write(str(pre_master_path), pre_master, sample_rate, subtype="PCM_24")

    # 5. 2-pass Loudness Normalization
    final_wav_path = master_dir / "final_mix.wav"
    final_mp3_path = master_dir / "final_mix.mp3"

    from apps.audio_director import normalize_master_ffmpeg
    ok_norm = normalize_master_ffmpeg(
        input_wav=pre_master_path,
        output_wav=final_wav_path,
        output_mp3=final_mp3_path,
        target_lufs=target_lufs,
        true_peak_db=true_peak_db,
        sample_rate=sample_rate
    )
    if not ok_norm:
        shutil.copy2(pre_master_path, final_wav_path)

    # 6. Đo lường kết quả master thực tế
    final_stats = analyze_audio_loudness(final_wav_path)
    cov_stats = calculate_music_coverage(cue_sheet, total_sec)

    # 7. Lưu cue_sheet.json và mix_report.json
    cue_sheet_path = mix_dir / "cue_sheet.json"
    with open(cue_sheet_path, "w", encoding="utf-8") as f:
        json.dump(cue_sheet, f, ensure_ascii=False, indent=2)

    mix_report = {
        "project_slug": project_dir.name,
        "timestamp": time.time(),
        "created_at_str": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_episode_sec": cov_stats["total_episode_sec"],
        "total_episode_fmt": cov_stats["total_episode_fmt"],
        "music_duration_sec": cov_stats["music_duration_sec"],
        "music_duration_fmt": cov_stats["music_duration_fmt"],
        "dry_duration_sec": cov_stats["dry_duration_sec"],
        "dry_duration_fmt": cov_stats["dry_duration_fmt"],
        "music_coverage_pct": cov_stats["coverage_percent"],
        "target_recommendation": cov_stats["target_recommendation"],
        "is_high_coverage": cov_stats["is_high_coverage"],
        "warning_message": cov_stats["warning_message"],
        "ducking_enabled": enable_ducking,
        "ducking_db": ducking_db if enable_ducking else 0.0,
        "master_integrated_lufs": final_stats["integrated_lufs"],
        "master_true_peak_db": final_stats["true_peak_db"],
        "master_lra": final_stats["lra"],
        "target_lufs": target_lufs,
        "target_true_peak_db": true_peak_db,
        "outputs": {
            "voice_master_wav": str(voice_master_path),
            "music_mix_wav": str(music_mix_path),
            "final_mix_pre_master_wav": str(pre_master_path),
            "final_mix_wav": str(final_wav_path),
            "final_mix_mp3": str(final_mp3_path),
            "cue_sheet_json": str(cue_sheet_path)
        }
    }

    mix_report_path = mix_dir / "mix_report.json"
    with open(mix_report_path, "w", encoding="utf-8") as f:
        json.dump(mix_report, f, ensure_ascii=False, indent=2)

    logger.info(f"Hoàn thành Final Mix & Master: {final_wav_path} ({final_stats['integrated_lufs']} LUFS, {final_stats['true_peak_db']} dBTP).")
    return True, f"Tạo Final Mix thành công ({total_sec/60:.1f} phút, {final_stats['integrated_lufs']} LUFS, {final_stats['true_peak_db']} dBTP)!", mix_report


# ==============================================================================
# 9. REGION PREVIEW & A/B COMPARISON
# ==============================================================================

def preview_region_mix(
    project_dir: Path,
    voice_master_path: Path,
    cue_item: dict,
    project_overrides: Optional[dict] = None,
    before_sec: float = 10.0,
    after_sec: float = 10.0,
    sample_rate: int = REFERENCE_SAMPLE_RATE
) -> Tuple[bool, str, Optional[Path]]:
    """
    Tạo nhanh bản nghe thử cho 1 phân đoạn nhạc:
    Cắt 10s trước + toàn bộ region + 10s sau của cả Voice + Music.
    """
    previews_dir = Path(project_dir) / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)

    voice_master_path = Path(voice_master_path)
    if not voice_master_path.exists():
        return False, "Chưa có Voice Master để nghe thử.", None

    voice_wav, sr = sf.read(str(voice_master_path), dtype="float32")
    if sr != sample_rate:
        from apps.audio_director import resample_audio
        voice_wav = resample_audio(voice_wav, sr, sample_rate)
    if voice_wav.ndim > 1:
        voice_wav = np.mean(voice_wav, axis=1)

    total_samples = len(voice_wav)
    total_sec = total_samples / sample_rate

    st_sec = max(0.0, float(cue_item["start_sec"]) - before_sec)
    en_sec = min(total_sec, float(cue_item["end_sec"]) + after_sec)

    st_samp = int(st_sec * sample_rate)
    en_samp = int(en_sec * sample_rate)
    sub_len = en_samp - st_samp
    if sub_len <= 0:
        return False, "Khoảng thời gian nghe thử rỗng.", None

    # Render music bed riêng cho đoạn này
    mini_cue_sheet = [cue_item]
    full_music = render_music_bed(mini_cue_sheet, total_samples, project_overrides, sample_rate)

    sub_voice = voice_wav[st_samp:en_samp]
    sub_music = full_music[st_samp:en_samp]
    sub_mix = sub_voice + sub_music

    cue_name = cue_item.get("cue", "region")
    out_path = previews_dir / f"preview_region_{cue_name}_{int(st_sec)}s.wav"
    sf.write(str(out_path), sub_mix, sample_rate, subtype="PCM_24")

    return True, f"Đã tạo preview region ({sub_len/sample_rate:.1f}s)", out_path
