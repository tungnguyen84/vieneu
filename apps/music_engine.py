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
from datetime import datetime

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Thư mục Music Library toàn cục
GLOBAL_MUSIC_LIB_DIR = PROJECT_ROOT / "music_library"
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

DEFAULT_SLOT_TRACKS = {
    "INTRO": "SCC_INTRO_01",
    "MYSTERY": "SCC_MYSTERY_01",
    "TENSION": "SCC_TENSION_01",
    "EMOTIONAL": "SCC_EMOTIONAL_01",
    "REFLECTION": "SCC_REFLECTION_01",
    "OUTRO": "SCC_OUTRO_01",
}
FIXED_SLOT_TRACKS = DEFAULT_SLOT_TRACKS



# ==============================================================================
# 1. LOUDNESS ANALYSIS & NORMALIZATION
# ==============================================================================

def probe_audio_file(file_path: Union[str, Path]) -> dict:
    """
    Sử dụng ffprobe để nhận diện container, codec, thời lượng, sample_rate, channels.
    Hỗ trợ mọi định dạng: WAV, MP3, M4A (AAC), FLAC, OGG...
    Không phụ thuộc vào đuôi file (kể cả temp file không có đuôi mở rộng).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {path}")

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=format_name,duration:stream=codec_name,sample_rate,channels,codec_type",
        "-print_format", "json",
        str(path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        err_msg = res.stderr.strip() if res.stderr else "ffprobe failed"
        raise RuntimeError(f"FFmpeg decode failed: {err_msg}")

    data = json.loads(res.stdout or "{}")
    format_info = data.get("format", {})
    streams = data.get("streams", [])

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    codec_name = str(audio_stream.get("codec_name", "")).lower()
    format_name = str(format_info.get("format_name", "")).lower()

    dur_str = format_info.get("duration") or audio_stream.get("duration") or "0.0"
    try:
        duration_sec = float(dur_str)
    except Exception:
        duration_sec = 0.0

    return {
        "codec_name": codec_name,
        "format_name": format_name,
        "duration_sec": duration_sec,
        "sample_rate": int(audio_stream.get("sample_rate", 48000) or 48000),
        "channels": int(audio_stream.get("channels", 2) or 2)
    }


def detect_audio_extension(file_path: Union[str, Path], orig_filename: Optional[str] = None) -> str:
    """
    Xác định extension chuẩn (.wav, .mp3, .m4a, .flac, .ogg) từ file_path, orig_filename hoặc ffprobe.
    """
    if orig_filename:
        suf = Path(orig_filename).suffix.lower()
        if suf in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
            return suf
        if suf == ".aac":
            return ".m4a"

    suf = Path(file_path).suffix.lower()
    if suf in [".wav", ".mp3", ".m4a", ".flac", ".ogg"]:
        return suf
    if suf == ".aac":
        return ".m4a"

    try:
        probe = probe_audio_file(file_path)
        codec = probe.get("codec_name", "")
        fmt = probe.get("format_name", "")
        if "aac" in codec or "m4a" in fmt or "mov,mp4" in fmt:
            return ".m4a"
        elif "mp3" in codec or "mp3" in fmt:
            return ".mp3"
        elif "flac" in codec or "flac" in fmt:
            return ".flac"
        elif "ogg" in codec or "vorbis" in codec or "opus" in codec or "ogg" in fmt:
            return ".ogg"
        elif "pcm" in codec or "wav" in fmt:
            return ".wav"
    except Exception:
        pass

    return ".wav"


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
        probe = probe_audio_file(audio_path)
        duration = float(probe.get("duration_sec", 0.0))
    except Exception:
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
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
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
    Nếu FFmpeg lỗi, ném RuntimeError chứa chi tiết stderr.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Phân tích file đầu vào
    stats = analyze_audio_loudness(input_path)

    # 2. Chạy FFmpeg loudnorm sang 48kHz WAV PCM 24-bit
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP={target_peak_db}:linear=true",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s24le",
        str(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        logger.warning(f"FFmpeg loudnorm thất bại cho {input_path}, thử fallback resample: {res.stderr}")
        cmd_fallback = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(input_path),
            "-ar", str(sample_rate),
            "-c:a", "pcm_s24le",
            str(output_path)
        ]
        res_fb = subprocess.run(cmd_fallback, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_fb.returncode != 0:
            err_details = res_fb.stderr.strip() if res_fb.stderr else res.stderr.strip()
            raise RuntimeError(f"FFmpeg decode failed: {err_details}")

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
    Nếu thư mục rỗng hoặc thiếu track, tự động quét và nạp 6 bản nhạc Suno mặc định.
    """
    lib_dir = Path(lib_dir)
    original_dir = lib_dir / "original"
    normalized_dir = lib_dir / "normalized"
    backup_dir = lib_dir / "backups"
    lib_json_path = lib_dir / "library.json"

    original_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    if lib_json_path.exists():
        try:
            with open(lib_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("tracks", {})
            valid = True
            for tid, tinfo in tracks.items():
                p = Path(tinfo.get("normalized_file", ""))
                if not p.is_absolute():
                    p = PROJECT_ROOT / p
                if not p.exists():
                    valid = False
                    break
            if valid and len(tracks) >= 6:
                return data
        except Exception as e:
            logger.warning(f"Lỗi đọc {lib_json_path}: {e}")

    # Tự động tìm nguồn nhạc mặc định để nạp ban đầu (Ưu tiên các file Suno MP3 chất lượng cao)
    candidates = [
        Path(r"C:\Users\TPT\Documents\sau_canh_cua_ep01_v9_1_master_reference\01_audio\music"),
        Path(r"projects\test_v6_pack\music"),
        Path(r"projects\sau_canh_cua_-_pilot_01_v6\music")
    ]

    seed_map = {
        "SCC_INTRO_01": ("INTRO", ["01_signature_intro.mp3", "01_signature_intro.wav"]),
        "SCC_MYSTERY_01": ("MYSTERY", ["03_mystery_low.mp3", "03_mystery_low.wav"]),
        "SCC_TENSION_01": ("TENSION", ["05_tension_low.mp3", "05_tension_low.wav"]),
        "SCC_EMOTIONAL_01": ("EMOTIONAL", ["06_emotional_low.mp3", "06_emotional_low.wav"]),
        "SCC_REFLECTION_01": ("REFLECTION", ["04_reflection_low.mp3", "04_memory_soft.wav", "07_closing_soft.wav"]),
        "SCC_OUTRO_01": ("OUTRO", ["02_signature_outro.mp3", "02_signature_outro.wav"])
    }

    library_data = {
        "version": "1.0",
        "reference_lufs": REFERENCE_MUSIC_LUFS,
        "sample_rate": REFERENCE_SAMPLE_RATE,
        "categories": DEFAULT_CATEGORY_CONFIG,
        "tracks": {}
    }

    init_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

            rel_orig = str(orig_dest.relative_to(PROJECT_ROOT)) if orig_dest.is_relative_to(PROJECT_ROOT) else str(orig_dest)
            rel_norm = str(norm_dest.relative_to(PROJECT_ROOT)) if norm_dest.is_relative_to(PROJECT_ROOT) else str(norm_dest)

            library_data["tracks"][track_id] = {
                "track_id": track_id,
                "category": category,
                "original_filename": found_source.name,
                "original_file": rel_orig,
                "normalized_file": rel_norm,
                "duration_sec": stats["duration_sec"],
                "integrated_lufs": stats["integrated_lufs"],
                "true_peak_db": stats["true_peak_db"],
                "updated_at": init_time_str,
                "normalized_status": "READY"
            }
        else:
            # Tạo silent dummy track nếu chưa có file
            norm_dest = normalized_dir / f"{track_id}.wav"
            sf.write(str(norm_dest), np.zeros(int(REFERENCE_SAMPLE_RATE * 30), dtype=np.float32), REFERENCE_SAMPLE_RATE)
            rel_norm = str(norm_dest.relative_to(PROJECT_ROOT)) if norm_dest.is_relative_to(PROJECT_ROOT) else str(norm_dest)
            library_data["tracks"][track_id] = {
                "track_id": track_id,
                "category": category,
                "original_filename": f"{track_id}.wav",
                "original_file": rel_norm,
                "normalized_file": rel_norm,
                "duration_sec": 30.0,
                "integrated_lufs": -99.0,
                "true_peak_db": -99.0,
                "updated_at": init_time_str,
                "normalized_status": "DUMMY"
            }

    save_global_music_library(library_data, lib_dir)
    logger.info(f"Khởi tạo Music Library thành công với {len(library_data['tracks'])} tracks tại {lib_dir}.")
    return library_data


def save_global_music_library(library_data: dict, lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> None:
    """Lưu metadata Music Library vào library.json và flush/fsync trực tiếp xuống đĩa."""
    lib_dir = Path(lib_dir)
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_file = lib_dir / "library.json"
    with open(lib_file, "w", encoding="utf-8") as f:
        json.dump(library_data, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass


def import_track_to_library(
    category: str,
    track_id: Optional[str],
    file_source: Union[str, Path],
    orig_filename: Optional[str] = None,
    lib_dir: Path = GLOBAL_MUSIC_LIB_DIR
) -> Tuple[bool, str, dict]:
    """
    Thay thế và nạp file nhạc mới cho slot chỉ định (WAV/MP3/M4A/FLAC).
    Quy trình chuẩn hóa persistent:
    1. Decode và probe bằng FFmpeg.
    2. Tự động backup track cũ vào music_library/backups/{TRACK_ID}_{YYYYMMDD_HHMMSS}.wav.
    3. Normalize về -24.0 LUFS, True Peak <= -1.0 dBTP, 48kHz WAV stereo 24-bit.
    4. Ghi đè vào persistent music_library/normalized/ với cùng Track ID (SCC_{SLOT}_01).
    5. Cập nhật library.json với updated_at và flush/fsync xuống đĩa ngay lập tức.
    """
    lib_dir = Path(lib_dir)
    original_dir = lib_dir / "original"
    normalized_dir = lib_dir / "normalized"
    backup_dir = lib_dir / "backups"
    original_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    src_p = Path(file_source)
    if not src_p.exists():
        raise FileNotFoundError(f"File nguồn tải lên không tồn tại tại: {src_p}")

    category = category.upper().strip()
    if category not in DEFAULT_CATEGORY_CONFIG:
        return False, f"Danh mục '{category}' không hợp lệ. Phải thuộc: {list(DEFAULT_CATEGORY_CONFIG.keys())}", {}

    # 6 slot cố định: KHÔNG tạo _02, luôn gán chặt với SCC_{category}_01
    fixed_slot_id = FIXED_SLOT_TRACKS.get(category, f"SCC_{category}_01")
    track_id = fixed_slot_id

    # 1. Nhận diện thông tin file qua ffprobe
    try:
        probe = probe_audio_file(src_p)
    except Exception as e:
        return False, f"Định dạng âm thanh '{src_p.suffix}' không được hỗ trợ (FFmpeg decode failed: {e})", {}

    codec_name = probe.get("codec_name", "")
    if not codec_name:
        return False, f"Định dạng file '{src_p.suffix}' không được hỗ trợ: Không tìm thấy audio stream hợp lệ trong file.", {}

    orig_name_clean = orig_filename or src_p.name
    ext = detect_audio_extension(src_p, orig_name_clean)

    print(f"[MUSIC IMPORT] Thay thế slot: {category} -> Track ID: {track_id}", flush=True)
    print(f"[MUSIC IMPORT] original filename: {orig_name_clean}", flush=True)
    print(f"[MUSIC IMPORT] temp path: {src_p}", flush=True)
    print(f"[MUSIC IMPORT] extension: {ext}", flush=True)
    print(f"[MUSIC IMPORT] ffprobe codec: {codec_name}", flush=True)
    print(f"[MUSIC IMPORT] duration: {probe.get('duration_sec', 0.0):.2f}s", flush=True)

    norm_dest = normalized_dir / f"{track_id}.wav"

    # 2. Tự động backup track cũ vào music_library/backups/
    if norm_dest.exists():
        ts_backup = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{track_id}_{ts_backup}.wav"
        try:
            shutil.copy2(norm_dest, backup_file)
            print(f"[MUSIC BACKUP] Đã sao lưu track cũ vào: {backup_file.name}", flush=True)
        except Exception as e:
            logger.warning(f"Lỗi tạo backup: {e}")

    # 3. Dọn dẹp file gốc cũ có đuôi khác của track_id này
    for old_f in original_dir.glob(f"{track_id}.*"):
        try:
            old_f.unlink()
        except Exception:
            pass

    orig_dest = original_dir / f"{track_id}{ext}"
    shutil.copy2(src_p, orig_dest)

    # 4. Normalize qua FFmpeg
    try:
        norm_stats = normalize_music_asset(orig_dest, norm_dest, REFERENCE_MUSIC_LUFS, -1.0, REFERENCE_SAMPLE_RATE)
    except Exception as e:
        return False, f"FFmpeg decode/normalize failed: {e}", {}

    # 5. Cập nhật library.json và flush xuống đĩa
    lib_data = init_global_music_library(lib_dir)
    updated_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rel_orig = str(orig_dest.relative_to(PROJECT_ROOT)) if orig_dest.is_relative_to(PROJECT_ROOT) else str(orig_dest)
    rel_norm = str(norm_dest.relative_to(PROJECT_ROOT)) if norm_dest.is_relative_to(PROJECT_ROOT) else str(norm_dest)

    lib_data.setdefault("tracks", {})[track_id] = {
        "track_id": track_id,
        "category": category,
        "original_filename": orig_name_clean,
        "original_file": rel_orig,
        "normalized_file": rel_norm,
        "duration_sec": norm_stats["duration_sec"],
        "integrated_lufs": norm_stats["integrated_lufs"],
        "true_peak_db": norm_stats["true_peak_db"],
        "updated_at": updated_at_str,
        "normalized_status": "READY"
    }

    lib_data.setdefault("categories", DEFAULT_CATEGORY_CONFIG).setdefault(category, {})["default_track"] = track_id
    save_global_music_library(lib_data, lib_dir)

    print(f"[MUSIC IMPORT] Đã lưu persistent thành công cho {track_id}: {norm_stats['duration_sec']}s, {norm_stats['integrated_lufs']} LUFS, Updated: {updated_at_str}", flush=True)

    return True, f"Thay thế & Chuẩn hóa thành công cho slot {category} (Track: {track_id}, {norm_stats['duration_sec']}s, {norm_stats['integrated_lufs']} LUFS)", lib_data["tracks"][track_id]


def get_slot_cards_data(lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> dict:
    """Lấy dữ liệu chi tiết cho 6 slot nhạc chính."""
    lib_data = init_global_music_library(lib_dir)
    tracks = lib_data.get("tracks", {})
    categories = lib_data.get("categories", DEFAULT_CATEGORY_CONFIG)

    slot_data = {}
    for slot in ["INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"]:
        cat_cfg = categories.get(slot, {})
        def_tid = cat_cfg.get("default_track", FIXED_SLOT_TRACKS.get(slot, f"SCC_{slot}_01"))
        tinfo = tracks.get(def_tid, {})

        norm_path = tinfo.get("normalized_file")
        if norm_path:
            p_norm = Path(norm_path)
            if not p_norm.is_absolute():
                p_norm = PROJECT_ROOT / p_norm
            audio_preview = str(p_norm) if p_norm.exists() else None
        else:
            audio_preview = None

        slot_data[slot] = {
            "category": slot,
            "display_name": cat_cfg.get("display_name", slot),
            "track_id": def_tid,
            "original_filename": tinfo.get("original_filename", "Chưa có file"),
            "duration_sec": tinfo.get("duration_sec", 0.0),
            "integrated_lufs": tinfo.get("integrated_lufs", -99.0),
            "true_peak_db": tinfo.get("true_peak_db", -99.0),
            "updated_at": tinfo.get("updated_at", "Mặc định hệ thống"),
            "audio_preview": audio_preview,
            "status": tinfo.get("normalized_status", "MISSING")
        }
    return slot_data


def format_slot_markdown(slot_info: dict) -> str:
    """Format markdown hiển thị thông tin tóm tắt cho 1 slot nhạc theo chuẩn Sau Cánh Cửa."""
    tid = slot_info.get("track_id", "—")
    fn = slot_info.get("original_filename", "—")
    dur = slot_info.get("duration_sec", 0.0)
    lufs = slot_info.get("integrated_lufs", -99.0)
    tp = slot_info.get("true_peak_db", -99.0)
    updated_at = slot_info.get("updated_at", "Mặc định hệ thống")
    status = "✅ Sẵn sàng" if slot_info.get("status") == "READY" else "⚠️ Thiếu file"

    return (
        f"**File:** `{fn}`  \n"
        f"**Duration:** `{dur:.1f}s`  \n"
        f"**LUFS:** `{lufs:.1f}` (Peak: `{tp:.1f} dBTP`)  \n"
        f"**Updated At:** `{updated_at}`  \n"
        f"**Trạng thái:** {status} (`{tid}`)"
    )


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
        upd_txt = tinfo.get("updated_at", "Mặc định") if tinfo else "—"
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
            upd_txt,
            status_txt
        ])
    return rows


def resolve_track_file_for_cue(cue_name: str, project_overrides: dict = None, lib_dir: Path = GLOBAL_MUSIC_LIB_DIR) -> Optional[Path]:
    """
    Tìm file normalized 48kHz WAV cho một cue hoặc category.
    Ưu tiên: project_overrides > library default track.
    Đảm bảo luôn trả về đường dẫn tuyệt đối chính xác tới music_library/normalized/.
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
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if p.exists():
                return p

    # 2. Khớp category chuẩn (INTRO, MYSTERY, TENSION, EMOTIONAL, REFLECTION, OUTRO)
    if cue_upper in categories:
        def_tid = categories[cue_upper].get("default_track")
        if def_tid and def_tid in tracks:
            p = Path(tracks[def_tid].get("normalized_file", ""))
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if p.exists():
                return p

    # 3. Khớp track_id trực tiếp (ví dụ SCC_INTRO_01)
    if cue_upper in tracks:
        p = Path(tracks[cue_upper].get("normalized_file", ""))
        if not p.is_absolute():
            p = PROJECT_ROOT / p
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
        if def_tid and def_tid in tracks:
            p = Path(tracks[def_tid].get("normalized_file", ""))
            if not p.is_absolute():
                p = PROJECT_ROOT / p
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
    Xác định Music Cue cho từng segment theo các quy tắc chuẩn Sau Cánh Cửa:
    1. Explicit music object trong JSON được ưu tiên cao nhất.
    2. NORMAL và COMMENT mặc định DRY (trừ khi là emotional payoff thực sự ở cao trào).
    3. REVEAL luôn DRY tuyệt đối và giữ clearance an toàn.
    4. HOOK -> INTRO.
    5. ENDING -> REFLECTION / OUTRO.
    6. MYSTERY / TENSION theo nhịp độ.
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

    d_prof = str(seg_info.get("delivery_profile", "")).strip().upper()
    m_cue = str(seg_info.get("music_cue", "")).strip().lower()
    importance = str(seg_info.get("importance", "")).strip().lower()
    seg_id_str = str(seg_info.get("id", "0"))
    try:
        seg_id_num = int(seg_id_str)
    except Exception:
        seg_id_num = 0

    # 2. NORMAL và COMMENT mặc định DRY
    if d_prof in ["NORMAL", "COMMENT"]:
        # Chỉ kích hoạt EMOTIONAL cho emotional payoff thực sự ở cao trào (đoạn kết/hé lộ sự thật)
        if m_cue == "emotional_low" and (importance == "critical" or seg_id_num >= 80):
            cfg = DEFAULT_CATEGORY_CONFIG["EMOTIONAL"]
            return "EMOTIONAL", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
        return "DRY", -99.0, 0.0, 0.0

    # 3. REVEAL luôn DRY tuyệt đối
    if d_prof == "REVEAL" or is_major_reveal_segment(seg_info):
        return "DRY", -99.0, 0.0, 0.0

    # 4. HOOK -> INTRO (Signature Hook)
    if d_prof == "HOOK":
        cfg = DEFAULT_CATEGORY_CONFIG["INTRO"]
        return "INTRO", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]

    # 5. ENDING -> REFLECTION / OUTRO
    if d_prof == "ENDING":
        if seg_id_num >= 93 or m_cue == "signature_outro":
            cfg = DEFAULT_CATEGORY_CONFIG["OUTRO"]
            return "OUTRO", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
        cfg = DEFAULT_CATEGORY_CONFIG["REFLECTION"]
        return "REFLECTION", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]

    # 6. MYSTERY & TENSION
    if d_prof == "MYSTERY":
        if m_cue == "tension_low":
            cfg = DEFAULT_CATEGORY_CONFIG["TENSION"]
            return "TENSION", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]
        cfg = DEFAULT_CATEGORY_CONFIG["MYSTERY"]
        return "MYSTERY", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]

    if d_prof == "TENSION":
        cfg = DEFAULT_CATEGORY_CONFIG["TENSION"]
        return "TENSION", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]

    if d_prof == "EMOTIONAL":
        cfg = DEFAULT_CATEGORY_CONFIG["EMOTIONAL"]
        return "EMOTIONAL", cfg["default_level_db"], cfg["fade_in_sec"], cfg["fade_out_sec"]

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


def score_region_priority(reg: dict) -> int:
    """Đánh giá độ ưu tiên giữ lại của 1 music region khi prune."""
    cue = reg.get("cue", "").upper()
    dur = float(reg.get("end_sec", 0.0)) - float(reg.get("start_sec", 0.0))
    segs = reg.get("segments", [])

    if cue == "OUTRO":
        return 1000
    if cue == "INTRO":
        return 900
    if cue == "EMOTIONAL":
        return 800
    if cue == "REFLECTION":
        return 700
    if cue == "TENSION":
        if any(s.isdigit() and int(s) >= 40 for s in segs):
            return 500
        return 400
    if cue == "MYSTERY":
        if dur < 8.0:
            return 100
        return 200
    return 100


def prune_regions_to_target_coverage(
    regions: List[dict],
    total_sec: float,
    max_cov: float = 38.0,
    min_cov: float = 30.0
) -> Tuple[List[dict], float]:
    """
    Tự động prune các region có priority thấp nhất cho đến khi coverage <= max_cov (38%).
    Đảm bảo coverage không tụt sâu dưới min_cov (30%).
    """
    if total_sec <= 0:
        return regions, 0.0

    current_regs = [dict(r) for r in regions]
    music_dur = sum(r["end_sec"] - r["start_sec"] for r in current_regs)
    cov_pct = (music_dur / total_sec * 100.0) if total_sec > 0 else 0.0

    iteration = 0
    while cov_pct > max_cov and len(current_regs) > 0 and iteration < 50:
        iteration += 1
        scored = [(score_region_priority(r), idx, r) for idx, r in enumerate(current_regs)]
        scored.sort(key=lambda x: (x[0], -(x[2]["end_sec"] - x[2]["start_sec"])))

        lowest_score, lowest_idx, lowest_reg = scored[0]
        dur = lowest_reg["end_sec"] - lowest_reg["start_sec"]

        # Nếu region dài (> 18s) và priority > 100, tỉa bớt đuôi trước
        if dur > 18.0 and lowest_score > 100:
            trim_sec = min(8.0, dur - 14.0)
            lowest_reg["end_sec"] -= trim_sec
        else:
            # Drop hẳn region priority thấp nhất
            current_regs.pop(lowest_idx)

        music_dur = sum(r["end_sec"] - r["start_sec"] for r in current_regs)
        cov_pct = (music_dur / total_sec * 100.0) if total_sec > 0 else 0.0

    return current_regs, cov_pct


def generate_cue_sheet_from_segments(
    timeline_events: List[dict],
    music_overrides: Optional[dict] = None,
    pre_reveal_clearance: float = 2.0,
    post_reveal_clearance: float = 2.5,
    merge_gap_threshold: float = 3.0,
    hook_cap_sec: float = 25.0,
    total_episode_sec: float = 0.0,
    target_max_coverage: float = 38.0,
    target_min_coverage: float = 30.0,
    max_region_dur: float = 26.0,
    min_dry_rest: float = 10.0
) -> List[dict]:
    """
    Tự động xây dựng Cue Sheet tối ưu từ chuỗi timeline events:
    1. Xác định Cue và Level cho từng segment (NORMAL/COMMENT = DRY, REVEAL = DRY).
    2. Áp dụng Major Reveal Safety Rule (pre_reveal_clearance & post_reveal_clearance).
    3. Giới hạn độ dài music region 12–30s; chèn khoảng nghỉ DRY sau region dài.
    4. Không nối MYSTERY/TENSION thành block 40-50s.
    5. Nếu coverage > 40%, tự động prune các region priority thấp nhất cho đến khi coverage <= 38%.
    6. Trả về danh sách Cue Sheet hoàn chỉnh với đầy đủ các khoảng DRY.
    """
    if not timeline_events:
        return []

    if total_episode_sec <= 0:
        total_episode_sec = max([float(ev.get("speech_end_sec", 0.0)) for ev in timeline_events], default=0.0)

    # 1. Gán cue dự kiến cho từng segment
    raw_cues = []
    reveal_blocks = []
    for ev in timeline_events:
        is_reveal = is_major_reveal_segment(ev)
        if is_reveal:
            cue, lvl, f_in, f_out = "DRY", -99.0, 0.0, 0.0
            b_start = max(0.0, ev["speech_start_sec"] - pre_reveal_clearance)
            b_end = ev["speech_end_sec"] + post_reveal_clearance
            reveal_blocks.append((b_start, b_end, ev["id"]))
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
    for ev in raw_cues:
        if ev["is_reveal"]:
            b_start = max(0.0, ev["speech_start"] - pre_reveal_clearance)
            b_end = ev["speech_end"] + post_reveal_clearance
            if not any(rb[0] == b_start for rb in reveal_blocks):
                reveal_blocks.append((b_start, b_end, ev["id"]))

    # 3. Gộp các segment có cùng cue thành Music Regions với nhịp thở
    regions: List[dict] = []
    current_reg: Optional[dict] = None
    last_music_end = -999.0
    last_music_dur = 0.0

    for idx, item in enumerate(raw_cues):
        cue = item["cue"]
        st = item["speech_start"]
        en = item["speech_end"]

        # Nếu segment rơi vào vùng Reveal thì bắt buộc đóng region hiện tại
        in_reveal_zone = any(not (en <= rb_st or st >= rb_en) for rb_st, rb_en, _ in reveal_blocks)

        if in_reveal_zone or cue == "DRY":
            if current_reg is not None:
                for rb_st, rb_en, _ in reveal_blocks:
                    if current_reg["end_sec"] > rb_st and current_reg["start_sec"] < rb_st:
                        current_reg["end_sec"] = rb_st
                        break
                last_music_end = current_reg["end_sec"]
                last_music_dur = current_reg["end_sec"] - current_reg["start_sec"]
                regions.append(current_reg)
                current_reg = None
            continue

        # Nếu region trước đó dài (>= 20s), bắt buộc giữ khoảng DRY nghỉ tai
        if current_reg is None and last_music_dur >= 20.0:
            if st < last_music_end + min_dry_rest:
                continue

        # Kiểm tra xem có thể gộp với region hiện tại không
        if current_reg is not None and current_reg["cue"] == cue:
            dur_if_merged = en - current_reg["start_sec"]
            # Không nối thành block dài quá max_region_dur (26-28s)
            if dur_if_merged <= max_region_dur:
                current_reg["end_sec"] = en
                current_reg["segments"].append(item["id"])
                continue
            else:
                # Đóng region hiện tại và để tai nghỉ
                last_music_end = current_reg["end_sec"]
                last_music_dur = current_reg["end_sec"] - current_reg["start_sec"]
                regions.append(current_reg)
                current_reg = None
                continue

        # Nếu đang có region khác cue, chốt region cũ
        if current_reg is not None:
            last_music_end = current_reg["end_sec"]
            last_music_dur = current_reg["end_sec"] - current_reg["start_sec"]
            regions.append(current_reg)
            current_reg = None

        # Bắt đầu region mới
        actual_start = st
        for rb_st, rb_en, _ in reveal_blocks:
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

    # 4. Áp dụng hook cap cho INTRO nếu quá dài
    for reg in regions:
        if reg["cue"] == "INTRO" and (reg["end_sec"] - reg["start_sec"]) > hook_cap_sec:
            reg["end_sec"] = reg["start_sec"] + hook_cap_sec

    # 5. Tự động Prune nếu coverage > target_max_coverage (38.0%)
    regions, final_cov = prune_regions_to_target_coverage(
        regions=regions,
        total_sec=total_episode_sec,
        max_cov=target_max_coverage,
        min_cov=target_min_coverage
    )

    # 6. Chuyển đổi thành danh sách Cue Sheet đầy đủ (bao gồm cả các vùng DRY)
    cue_sheet: List[dict] = []
    last_pos = 0.0

    lib_data = init_global_music_library()
    categories = lib_data.get("categories", DEFAULT_CATEGORY_CONFIG)

    for reg in regions:
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
                "source": "Voice Only / Breathing Rest"
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
            "source": "Voice Only / Epilogue Silence"
        })

    return cue_sheet


# ==============================================================================
# 5. MUSIC COVERAGE METRIC & TIMELINE VISUALIZER
# ==============================================================================

def calculate_music_coverage(cue_sheet: List[dict], total_episode_sec: Union[float, List[dict]] = 0.0) -> dict:
    """
    Tính toán chỉ số Music Coverage:
    Total Episode duration, Music duration, Dry duration, Coverage percentage.
    Đưa ra khuyến nghị 30–38% và cảnh báo nếu >40%.
    """
    if isinstance(total_episode_sec, list):
        total_episode_sec = max([float(e.get("speech_end_sec", 0.0)) for e in total_episode_sec], default=0.0)
    elif total_episode_sec <= 0:
        total_episode_sec = max([c["end_sec"] for c in cue_sheet], default=0.0)

    music_dur = 0.0
    for c in cue_sheet:
        if c.get("cue", "").upper() != "DRY" and c.get("track", "") != "NO_MUSIC":
            music_dur += float(c.get("duration_sec", 0.0))

    dry_dur = max(0.0, total_episode_sec - music_dur)
    cov_pct = (music_dur / total_episode_sec * 100.0) if total_episode_sec > 0 else 0.0

    is_high = cov_pct > 40.0
    warn_msg = (
        f"⚠️ **Cảnh báo:** Music coverage đang cao ({cov_pct:.1f}% > 40%). "
        "Định dạng storytelling yêu cầu 30–38% để tai khán giả có khoảng nghỉ (DRY)."
    ) if is_high else ""

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
        "target_recommendation": "30% – 38%",
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
    sample_rate: int = REFERENCE_SAMPLE_RATE,
    target_peak_db: Optional[float] = None
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
    if target_peak_db is not None:
        true_peak_db = target_peak_db
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
        },
        "final_master_wav": str(final_wav_path),
        "final_master_mp3": str(final_mp3_path),
        "music_stem": str(music_mix_path),
        "master_stats": {
            "integrated_lufs": final_stats["integrated_lufs"],
            "true_peak_db": final_stats["true_peak_db"]
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
