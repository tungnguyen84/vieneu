"""
Module xử lý Production Script JSON cho Storytelling dài tập trên VieNeu-TTS.
Hỗ trợ:
- Import & Validate JSON schema
- Mapping nhân vật & giọng đọc VieNeu
- Generate TTS từng segment độc lập (multi-take, speed post-processing bằng FFmpeg, cache & resume)
- Pause Engine (chống double pause thông minh)
- Ghép Master Audio chuyên nghiệp (Room tone, Loudness normalization 2-pass LUFS/dBTP)
- Xuất Master WAV 48kHz & MP3 320kbps
"""

import os
import re
import json
import time
import shutil
import hashlib
import logging
import subprocess
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger("VieNeu.ProductionStory")

# Các tag biểu cảm hợp lệ của VieNeu v3 Turbo được giữ lại trong text
VALID_NATIVE_EMOTION_TAGS = {"[cười]", "[hắng giọng]", "[thở dài]"}

import unicodedata

def sanitize_slug(name: str) -> str:
    """Tạo slug không dấu an toàn cho thư mục dự án."""
    if not name:
        return f"project_{int(time.time())}"
    name_ascii = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^\w\-_]', '_', name_ascii.strip().lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug or f"project_{int(time.time())}"

def clean_text_for_tts(text: str) -> str:
    """
    Giữ lại các native emotion tags [cười], [hắng giọng], [thở dài].
    Loại bỏ các tag lạ dạng [xyz] không được VieNeu hỗ trợ để tránh bị đọc thành tiếng.
    """
    if not text:
        return ""
    
    # Tìm tất cả các đoạn [...]
    def _replace_tag(match):
        tag = match.group(0).strip().lower()
        if tag in VALID_NATIVE_EMOTION_TAGS:
            return tag
        # Nếu là tag khác như [quiet_confession], [slow], [delivery] -> bỏ qua
        return ""

    cleaned = re.sub(r'\[[^\]]+\]', _replace_tag, text)
    # Chuẩn hóa khoảng trắng thừa
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def get_all_available_voices(tts_engine: Any = None) -> List[Tuple[str, str]]:
    """
    Lấy danh sách [(display_label, voice_id), ...] của toàn bộ preset voices VieNeu-TTS v3 Turbo
    BAO GỒM CẢ các giọng người dùng đã lưu từ tab Voice Cloning (~/.vieneu/user_voices_v3_turbo.json).
    Nếu engine đã load: gọi tts_engine.list_preset_voices().
    Nếu chưa load: đọc trực tiếp file assets/voices_v3_turbo.json kết hợp user_voices_v3_turbo.json.
    """
    engine_voices = []
    if tts_engine is not None and hasattr(tts_engine, "list_preset_voices"):
        try:
            # Đảm bảo các giọng clone người dùng đã được load vào preset_voices của engine
            try:
                from apps.user_voices import load_user_voices
                load_user_voices(tts_engine)
            except Exception:
                pass
            engine_voices = tts_engine.list_preset_voices() or []
        except Exception:
            engine_voices = []

    # 1. Đọc built-in presets từ voices_v3_turbo.json nếu engine_voices rỗng
    built_in_voices = []
    if not engine_voices:
        for candidate_path in [
            Path(__file__).parent.parent / "src" / "vieneu" / "assets" / "voices_v3_turbo.json",
            Path("src/vieneu/assets/voices_v3_turbo.json")
        ]:
            if candidate_path.exists():
                try:
                    with open(candidate_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    presets = data.get("presets", {})
                    sorted_items = sorted(
                        presets.items(),
                        key=lambda kv: (kv[1].get("featured") is None, kv[1].get("featured") or 0)
                    )
                    for name, v in sorted_items:
                        desc = v.get("description", "")
                        gender = v.get("gender", "")
                        featured = v.get("featured")
                        info_parts = [p for p in [desc, gender] if p]
                        label = f"{name} ({', '.join(info_parts)})" if info_parts else name
                        if featured is not None:
                            label = f"⭐ {label}"
                        built_in_voices.append((label, name))
                    break
                except Exception:
                    pass

    base_list = list(engine_voices) if engine_voices else list(built_in_voices)
    existing_ids = {v[1] if isinstance(v, (tuple, list)) else v for v in base_list}

    # 2. Luôn đọc thêm từ user_voices_v3_turbo.json & user_voices_v3_nano.json
    # để chắc chắn các giọng đã lưu từ tab Clone luôn xuất hiện ngay cả khi chưa load model
    user_voices_list = []
    home_dir = Path(os.environ.get("VIENEU_HOME") or (Path.home() / ".vieneu"))
    for uv_filename in ["user_voices_v3_turbo.json", "user_voices_v3_nano.json"]:
        uv_path = home_dir / uv_filename
        if uv_path.is_file():
            try:
                with open(uv_path, "r", encoding="utf-8") as f:
                    u_data = json.load(f)
                for uname, uv in (u_data.get("presets") or {}).items():
                    if uname not in existing_ids:
                        u_desc = uv.get("description", "") or "Giọng đã lưu từ tab Clone"
                        u_label = f"{uname} — {u_desc}"
                        user_voices_list.append((u_label, uname))
                        existing_ids.add(uname)
            except Exception:
                pass

    return base_list + user_voices_list

def compute_segment_hash(seg: dict, voice: str, model_version: str) -> str:
    """Tạo hash để cache và resume cho từng segment."""
    data = (
        f"{seg.get('id', '')}_"
        f"{seg.get('speaker', '')}_"
        f"{voice}_"
        f"{seg.get('text', '')}_"
        f"{seg.get('speed', 1.0)}_"
        f"{seg.get('multi_take', 1)}_"
        f"{model_version}"
    )
    return hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]

def resolve_character_voice(requested_voice: str, available_voices: List[Tuple[str, str]]) -> Tuple[Optional[str], str]:
    """
    Tìm giọng VieNeu phù hợp nhất từ requested_voice trong JSON.
    Trả về (matched_voice_id, status_note):
    - status_note: 'EXACT', 'ALIASED', hoặc 'MISSING'
    """
    if not requested_voice:
        return None, "MISSING"

    req_clean = requested_voice.strip().lower()

    # Tạo map từ voice_id và label
    # available_voices thường có dạng [("⭐ Tên hiển thị", "voice_id"), ...]
    voice_ids = [v[1] if isinstance(v, (list, tuple)) else v for v in available_voices]

    # 1. Exact match
    for v_id in voice_ids:
        if v_id.lower() == req_clean:
            return v_id, "EXACT"

    # 2. Known mapping / Substring match (ví dụ "Binh" -> "Thanh Bình", "Ly" -> "Trúc Ly")
    SPECIAL_MAP = {
        "binh": "Thanh Bình",
        "thanh binh": "Thanh Bình",
        "ly": "Trúc Ly",
        "truc ly": "Trúc Ly",
        "dang": "Hải Đăng",
        "hai dang": "Hải Đăng",
        "anh": "Mai Anh",
        "mai anh": "Mai Anh",
        "duc": "Minh Đức",
        "minh duc": "Minh Đức",
        "tuyen": "Phạm Tuyên",
        "pham tuyen": "Phạm Tuyên",
        "son": "Thái Sơn",
        "thai son": "Thái Sơn"
    }

    if req_clean in SPECIAL_MAP:
        mapped = SPECIAL_MAP[req_clean]
        for v_id in voice_ids:
            if v_id.lower() == mapped.lower():
                return v_id, f"ALIASED: '{requested_voice}' → '{v_id}'"

    # 3. Fuzzy substring trong voice_ids
    for v_id in voice_ids:
        if req_clean in v_id.lower():
            return v_id, f"ALIASED: '{requested_voice}' → '{v_id}'"

    return None, "MISSING"

def validate_story_json(data: dict, available_voices: List[Tuple[str, str]]) -> Tuple[bool, str, dict, dict, List[str], dict]:
    """
    Validate JSON schema và khởi tạo mapping nhân vật.
    Trả về:
    - is_valid (bool)
    - error_message (str)
    - project_info (dict)
    - characters_map (dict): { CHAR_ID: { "display_name": ..., "voice": ..., "status": ... } }
    - warnings (list of str)
    - stats (dict): { "segment_count": int, "character_count": int, "estimated_seconds": float }
    """
    warnings = []
    
    if not isinstance(data, dict):
        return False, "JSON gốc phải là một Object ({...})", {}, {}, [], {}

    # 1. Project Info
    project = data.get("project", {})
    if not isinstance(project, dict):
        project = {}
    
    project_title = project.get("title", "Storytelling_Project")
    episode_title = project.get("episode_title", project.get("title", "Episode_01"))
    sample_rate = int(project.get("sample_rate", 48000))
    default_gap = float(project.get("default_gap_seconds", 0.3))
    target_lufs = float(project.get("target_master_lufs", -14.0))
    true_peak = float(project.get("true_peak_db", -1.0))

    project_info = {
        "title": project_title,
        "episode_title": episode_title,
        "slug": sanitize_slug(project_title or "story_project"),
        "sample_rate": sample_rate,
        "default_gap_seconds": default_gap,
        "target_master_lufs": target_lufs,
        "true_peak_db": true_peak,
        "language": project.get("language", "vi-VN"),
        "tts_engine": project.get("tts_engine", "VieNeu-TTS-v3-Turbo")
    }

    # 2. Characters
    raw_characters = data.get("characters", {})
    if not isinstance(raw_characters, dict) or not raw_characters:
        return False, "Thiếu mục 'characters' hoặc danh sách nhân vật rỗng.", {}, {}, [], {}

    characters_map = {}
    for char_id, char_cfg in raw_characters.items():
        if not isinstance(char_cfg, dict):
            char_cfg = {"display_name": char_id, "voice": ""}
        
        display_name = char_cfg.get("display_name", char_id)
        requested_voice = char_cfg.get("voice", "")
        role = char_cfg.get("role", "")
        default_speed = float(char_cfg.get("default_speed", 1.0))

        matched_voice, match_status = resolve_character_voice(requested_voice, available_voices)

        if match_status == "MISSING":
            warnings.append(
                f"⚠️ Nhân vật '{char_id}' ({display_name}): Giọng '{requested_voice}' không có trong VieNeu. Vui lòng chọn giọng thay thế."
            )
        elif match_status.startswith("ALIASED"):
            warnings.append(
                f"ℹ️ Nhân vật '{char_id}' ({display_name}): Tự động ánh xạ {match_status}."
            )

        characters_map[char_id] = {
            "char_id": char_id,
            "display_name": display_name,
            "role": role,
            "requested_voice": requested_voice,
            "voice": matched_voice or "",
            "default_speed": max(0.88, min(1.05, default_speed)),
            "match_status": match_status
        }

    # 3. Segments
    segments = data.get("segments", [])
    if not isinstance(segments, list) or not segments:
        return False, "Mục 'segments' phải là một danh sách các câu thoại hợp lệ.", {}, {}, [], {}

    # Tính toán thống kê & thời lượng ước tính
    total_words = 0
    total_pause = 0.0
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        speaker = seg.get("speaker", "")
        if speaker not in characters_map:
            warnings.append(f"⚠️ Segment {seg.get('id', idx+1)}: Speaker '{speaker}' chưa được định nghĩa trong characters.")
        
        text = seg.get("text", "")
        words = len(text.split())
        total_words += words
        
        p_before = float(seg.get("pause_before", 0.0) or 0.0)
        p_after = float(seg.get("pause_after", default_gap) or default_gap)
        total_pause += (p_before + p_after)

    # Ước tính thời lượng: tiếng Việt nói trung bình ~150 từ/phút (~2.5 từ/giây) + khoảng lặng
    estimated_speech_seconds = total_words / 2.5
    estimated_total_seconds = estimated_speech_seconds + total_pause

    # 4. Music Library (nếu có trong JSON V6)
    music_library = data.get("music_library", {})
    has_music = isinstance(music_library, dict) and len(music_library) > 0

    stats = {
        "segment_count": len(segments),
        "character_count": len(characters_map),
        "total_words": total_words,
        "estimated_seconds": estimated_total_seconds,
        "has_music_library": has_music,
        "music_cues_count": len(music_library) if has_music else 0
    }

    if has_music:
        project_info["music_library"] = music_library

    return True, "", project_info, characters_map, warnings, stats


def apply_audio_speed(input_wav: Path, output_wav: Path, speed: float, sample_rate: int = 48000) -> bool:
    """
    Dùng FFmpeg bộ lọc atempo để thay đổi tốc độ đọc mà không làm thay đổi cao độ (pitch).
    Tốc độ được giới hạn an toàn trong khoảng [0.88, 1.05].
    """
    speed = max(0.88, min(1.05, float(speed)))
    if abs(speed - 1.0) < 0.005:
        if input_wav != output_wav:
            shutil.copy2(input_wav, output_wav)
        return True

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(input_wav),
        "-filter:a", f"atempo={speed:.4f}",
        "-ar", str(sample_rate),
        str(output_wav)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except (subprocess.CalledProcessError, OSError) as e:
        # Windows packaged/sandboxed launches can see an App Execution Alias for
        # ffmpeg but cannot execute it (WinError 5).  Librosa provides a local,
        # pitch-preserving fallback so contextual delivery speed still applies.
        logger.warning(f"FFmpeg atempo unavailable ({e}); using local time-stretch fallback.")
        try:
            import librosa
            audio, sr = sf.read(str(input_wav), dtype="float32", always_2d=False)
            if sr != sample_rate:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=sample_rate)
            stretched = librosa.effects.time_stretch(audio, rate=speed)
            sf.write(str(output_wav), stretched, sample_rate)
            return True
        except Exception as fallback_error:
            logger.error(f"Local time-stretch fallback failed: {fallback_error}")
            if input_wav != output_wav and input_wav.exists():
                shutil.copy2(input_wav, output_wav)
            return False


def generate_single_segment_takes(
    tts_engine: Any,
    project_dir: Path,
    segment: dict,
    char_config: dict,
    model_version: str = "v3turbo",
    temperature: float = 0.8
) -> Tuple[bool, str, dict]:
    """
    Sinh các take âm thanh cho một segment độc lập.
    Lưu vào:
      raw/{id}_{speaker}_take{take:02d}.wav
      selected/{id}.wav (mặc định take 1)
    """
    seg_id = str(segment.get("id", "001")).zfill(3)
    speaker = segment.get("speaker", "UNKNOWN")
    raw_text = segment.get("text", "").strip()
    clean_text = clean_text_for_tts(raw_text)
    
    if not clean_text:
        return False, f"Segment {seg_id}: Nội dung văn bản rỗng sau khi lọc.", {}

    # PRIORITY RULE CHO VOICE:
    # 1. segment.voice_override (nếu có giá trị hợp lệ khác 'Use Character Voice')
    # 2. char_config.voice
    # 3. Báo lỗi nếu chưa có giọng
    voice_override = str(segment.get("voice_override", "") or segment.get("override_voice", "")).strip()
    if voice_override and voice_override not in ("Use Character Voice", "Kế thừa (Use Character Voice)", "None", ""):
        voice = voice_override
    else:
        voice = char_config.get("voice", "")

    if not voice:
        return False, f"Segment {seg_id}: Chưa chọn giọng đọc cho nhân vật '{speaker}'. Vui lòng chọn giọng cho nhân vật hoặc chọn ghi đè giọng.", {}

    # PRIORITY RULE CHO SPEED:
    # 1. segment.speed (nếu segment khai báo riêng)
    # 2. char_config.default_speed
    # 3. 1.0
    if segment.get("speed") is not None and str(segment.get("speed")).strip() != "":
        speed = float(segment.get("speed"))
    elif char_config.get("default_speed") is not None:
        speed = float(char_config.get("default_speed"))
    else:
        speed = 1.0
    speed = max(0.88, min(1.05, speed))

    multi_take = max(1, int(segment.get("multi_take", 1)))

    raw_dir = project_dir / "raw"
    selected_dir = project_dir / "selected"
    raw_dir.mkdir(parents=True, exist_ok=True)
    selected_dir.mkdir(parents=True, exist_ok=True)

    takes_info = {}
    sample_rate = getattr(tts_engine, "sample_rate", 48000)

    for take_idx in range(1, multi_take + 1):
        take_filename = f"{seg_id}_{speaker}_take{take_idx:02d}.wav"
        take_path = raw_dir / take_filename

        # Biến thiên nhiệt độ nhẹ theo take để tạo các sắc thái khác biệt cho đạo diễn chọn
        take_temp = temperature if take_idx == 1 else min(1.0, temperature + (take_idx - 1) * 0.05)

        try:
            # Đảm bảo voice (đặc biệt là giọng clone đã lưu) đã có trong preset của engine
            if hasattr(tts_engine, "_preset_voices") and voice not in tts_engine._preset_voices:
                try:
                    from apps.user_voices import load_user_voices
                    load_user_voices(tts_engine)
                except Exception:
                    pass

            # Gọi phương thức infer của VieNeu instance hiện tại
            wav_data = tts_engine.infer(
                text=clean_text,
                voice=voice,
                temperature=take_temp,
                max_chars=256
            )

            if wav_data is None or len(wav_data) == 0:
                raise RuntimeError(f"Engine trả về âm thanh rỗng cho take {take_idx}.")

            # Lưu file wav gốc tạm thời
            temp_take_path = raw_dir / f"tmp_{take_filename}"
            sf.write(str(temp_take_path), wav_data, sample_rate)

            # Áp dụng tốc độ speed (nếu khác 1.0) qua FFmpeg atempo
            apply_audio_speed(temp_take_path, take_path, speed=speed, sample_rate=sample_rate)
            if temp_take_path.exists():
                temp_take_path.unlink()

            takes_info[str(take_idx)] = str(take_path.relative_to(project_dir))

        except Exception as e:
            logger.error(f"Lỗi khi sinh take {take_idx} cho segment {seg_id}: {e}")
            return False, f"Segment {seg_id} Take {take_idx} error: {str(e)}", {}

    # Mặc định chọn Take 1 vào selected/{seg_id}.wav
    selected_file = selected_dir / f"{seg_id}.wav"
    take01_path = raw_dir / f"{seg_id}_{speaker}_take01.wav"
    if take01_path.exists():
        shutil.copy2(take01_path, selected_file)

    segment_result = {
        "id": seg_id,
        "speaker": speaker,
        "voice": voice,
        "text": raw_text,
        "clean_text": clean_text,
        "speed": speed,
        "multi_take": multi_take,
        "takes": takes_info,
        "selected_take": 1,
        "selected_file": str(selected_file.relative_to(project_dir)),
        "status": "COMPLETED",
        "hash": compute_segment_hash(segment, voice, model_version)
    }

    return True, "SUCCESS", segment_result


def build_master_audio(
    project_dir: Path,
    segments: List[dict],
    project_state: dict,
    gap_rule: str = "max",
    default_gap: float = 0.18,
    room_tone_path: Optional[str] = None,
    room_tone_volume_db: float = -41.0,
    target_lufs: float = -14.0,
    true_peak_db: float = -1.0,
    sample_rate: int = 48000,
    music_lib: Optional[Dict[str, dict]] = None,
    enable_music: bool = True,
    enable_room_tone: bool = True,
    auto_silence_critical: bool = True,
    global_music_gain_db: float = 0.0,
    default_ducking_db: float = -8.0,
    crossfade_sec: float = 1.2,
    reveal_music_return_delay_sec: float = 0.8
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Tạo Master Audio hoàn chỉnh thông qua Audio Director Engine:
    - Dialogue timeline (loại bỏ double pause)
    - Continuous Room Tone timeline
    - Music regions không ngắt giữa các câu cùng cue, crossfade khi đổi cue
    - Tự động tắt nhạc trước Critical Reveal
    - Ducking nhạc mượt mà khi có giọng nói
    - 2-pass Loudness Normalization (-14 LUFS, -1 dBTP)
    - Xuất đầy đủ Stems (dialogue, room_tone, music, master WAV/MP3, timeline JSON).
    """
    from apps.audio_director import parse_music_library, build_audio_director_master

    if music_lib is None:
        source_json_path = project_dir / "source.json"
        if source_json_path.exists():
            try:
                with open(source_json_path, "r", encoding="utf-8") as f:
                    source_data = json.load(f)
                music_lib = parse_music_library(project_dir, source_data)
            except Exception:
                music_lib = {}
        else:
            music_lib = {}

    ok, msg, outputs = build_audio_director_master(
        project_dir=project_dir,
        segments=segments,
        project_state=project_state,
        music_lib=music_lib,
        enable_music=enable_music,
        enable_room_tone=enable_room_tone,
        auto_silence_critical=auto_silence_critical,
        global_music_gain_db=global_music_gain_db,
        room_tone_volume_db=room_tone_volume_db,
        default_ducking_db=default_ducking_db,
        crossfade_sec=crossfade_sec,
        reveal_music_return_delay_sec=reveal_music_return_delay_sec,
        target_lufs=target_lufs,
        true_peak_db=true_peak_db,
        gap_rule=gap_rule,
        default_gap=default_gap,
        sample_rate=sample_rate
    )

    wav_out = outputs.get("episode_master_wav") if ok else None
    mp3_out = outputs.get("episode_master_mp3") if ok else None
    return ok, msg, wav_out, mp3_out


def load_or_init_project_state(project_dir: Path, json_data: dict) -> dict:
    """Tải hoặc khởi tạo project_state.json cho tính năng Resume."""
    state_file = project_dir / "project_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Tạo state mới
    initial_state = {
        "project_slug": project_dir.name,
        "created_at": time.time(),
        "updated_at": time.time(),
        "segments": {}
    }
    save_project_state(project_dir, initial_state)
    return initial_state


def save_project_state(project_dir: Path, state_data: dict) -> None:
    """Lưu project_state.json."""
    state_file = project_dir / "project_state.json"
    state_data["updated_at"] = time.time()
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)


def export_project_json(project_dir: Path, source_json: dict, project_state: dict) -> str:
    """
    Xuất file JSON hoàn chỉnh của project kèm selected_take và status
    để có thể mở lại bất cứ lúc nào.
    """
    exported = json.loads(json.dumps(source_json))
    segments_state = project_state.get("segments", {})

    for seg in exported.get("segments", []):
        seg_id = str(seg.get("id", "")).zfill(3)
        state_seg = segments_state.get(seg_id)
        if state_seg:
            seg["selected_take"] = state_seg.get("selected_take", 1)
            seg["generation_status"] = state_seg.get("status", "PENDING")
            seg["available_takes"] = state_seg.get("takes", {})

    export_path = project_dir / "exported_project.json"
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(exported, f, ensure_ascii=False, indent=2)

    return str(export_path)


def build_segments_dataframe(segments: List[dict], characters_map: dict, project_state: dict) -> List[List[Any]]:
    """Tạo bảng dữ liệu phân đoạn cho Gradio DataFrame."""
    rows = []
    segments_state = project_state.get("segments", {}) if project_state else {}
    for seg in segments:
        seg_id = str(seg.get("id", "")).zfill(3)
        speaker = seg.get("speaker", "")
        char_cfg = characters_map.get(speaker, {})
        char_voice = char_cfg.get("voice", "")
        voice_override = seg.get("voice_override", "") or "Kế thừa (Use Character Voice)"
        
        # Priority rule cho speed
        if seg.get("speed") is not None and str(seg.get("speed")).strip() != "":
            spd = float(seg.get("speed"))
        elif char_cfg.get("default_speed") is not None:
            spd = float(char_cfg.get("default_speed"))
        else:
            spd = 1.0

        state_seg = segments_state.get(seg_id, {})
        status = state_seg.get("status", "PENDING")
        selected_take = state_seg.get("selected_take", 1)
        
        # Xác định giọng thực tế được áp dụng
        applied_voice = voice_override if (voice_override and voice_override != "Kế thừa (Use Character Voice)") else char_voice

        # Các trường Audio Director (V6)
        m_cue = str(seg.get("music_cue", "none") or "none")
        m_vol = seg.get("music_volume_db")
        m_vol_num = float(m_vol) if m_vol is not None and str(m_vol).strip() != "" else -34.0
        f_in = float(seg.get("music_fade_in_sec", 1.2) or 1.2)
        f_out = float(seg.get("music_fade_out_sec", 1.0) or 1.0)
        duck_val = float(seg.get("ducking_db", -8.0) if seg.get("ducking_db") is not None else -8.0)
        rt_val = float(seg.get("room_tone_db", -41.0) if seg.get("room_tone_db") is not None else -41.0)
        imp_val = str(seg.get("importance", "normal") or "normal")
        deliv_val = str(seg.get("delivery_profile") or seg.get("delivery", "neutral"))

        rows.append([
            True,  # Checkbox chọn
            seg_id,
            speaker,
            seg.get("text", ""),
            applied_voice,
            voice_override,
            deliv_val,
            spd,
            float(seg.get("pause_before", 0.0) or 0.0),
            float(seg.get("pause_after", 0.3) or 0.3),
            m_cue,
            m_vol_num,
            f_in,
            f_out,
            duck_val,
            rt_val,
            imp_val,
            int(seg.get("multi_take", 1)),
            status,
            f"Take {selected_take}"
        ])
    return rows


def invalidate_cache_for_speakers(project_dir: Path, project_state: dict, changed_speakers: set) -> int:
    """
    Invalidate cache CHỈ cho các segment thuộc các nhân vật có giọng/tốc độ bị thay đổi.
    Đánh dấu status = 'NEEDS_REGENERATE'. Các nhân vật khác giữ nguyên 100%!
    Trả về số lượng segment bị invalidate.
    """
    if not changed_speakers:
        return 0

    count = 0
    segments_state = project_state.get("segments", {})
    for seg_id, seg_data in segments_state.items():
        if seg_data.get("speaker") in changed_speakers:
            seg_data["status"] = "NEEDS_REGENERATE"
            # Xóa file selected cũ để tránh lấy nhầm audio cũ vào master
            sel_file = project_dir / "selected" / f"{seg_id}.wav"
            if sel_file.exists():
                try:
                    sel_file.unlink()
                except Exception:
                    pass
            count += 1

    save_project_state(project_dir, project_state)
    return count


def generate_character_preview_voice(
    tts_engine: Any,
    project_dir: Path,
    char_id: str,
    display_name: str,
    role: str,
    voice: str,
    speed: float = 1.0
) -> Tuple[bool, str, Optional[str]]:
    """
    Sinh câu preview ngắn cho nhân vật để nghe thử giọng trên Character Card.
    Không lưu vào production segment cache.
    """
    if not voice:
        return False, "Chưa chọn giọng đọc.", None

    preview_dir = project_dir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    out_wav = preview_dir / f"preview_{char_id}.wav"

    # Câu thoại mẫu theo ngữ cảnh nhân vật
    cid_upper = char_id.upper()
    if "MINH" in cid_upper:
        text = "Bạn đang nghe Sau Cánh Cửa. Có những chuyện, người ta chỉ dám kể khi không ai nhìn thấy mặt mình."
    elif "LAN" in cid_upper:
        text = "Tôi đã giữ bí mật này rất lâu. Và hôm nay, tôi nghĩ mình nên kể lại."
    else:
        role_txt = f" đảm nhận vai trò {role}" if role else ""
        text = f"Xin chào, tôi là {display_name or char_id}{role_txt}. Đây là giọng đọc thử nghiệm trong kịch bản."

    try:
        sample_rate = getattr(tts_engine, "sample_rate", 48000)
        # Đảm bảo voice (đặc biệt là giọng clone đã lưu) đã có trong preset của engine
        if hasattr(tts_engine, "_preset_voices") and voice not in tts_engine._preset_voices:
            try:
                from apps.user_voices import load_user_voices
                load_user_voices(tts_engine)
            except Exception:
                pass

        wav_data = tts_engine.infer(
            text=text,
            voice=voice,
            temperature=0.8,
            max_chars=256
        )
        if wav_data is None or len(wav_data) == 0:
            return False, "Engine trả về âm thanh rỗng.", None

        temp_path = preview_dir / f"tmp_{char_id}.wav"
        sf.write(str(temp_path), wav_data, sample_rate)
        apply_audio_speed(temp_path, out_wav, speed=speed, sample_rate=sample_rate)
        if temp_path.exists():
            temp_path.unlink()

        return True, "Thành công", str(out_wav)
    except Exception as e:
        logger.error(f"Lỗi sinh preview cho {char_id}: {e}")
        return False, str(e), None


def select_take_for_segment(project_dir: Path, project_state: dict, seg_id: str, take_num: int) -> Tuple[bool, str]:
    """Chọn take cho một segment và copy sang selected/{seg_id}.wav."""
    seg_id = str(seg_id).zfill(3)
    seg_data = project_state.get("segments", {}).get(seg_id)
    if not seg_data:
        return False, f"Không tìm thấy dữ liệu cho segment {seg_id}."
    
    takes = seg_data.get("takes", {})
    take_rel = takes.get(str(take_num))
    if not take_rel:
        return False, f"Take {take_num} không tồn tại cho segment {seg_id}."
    
    src_path = project_dir / take_rel
    dest_path = project_dir / "selected" / f"{seg_id}.wav"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    if not src_path.exists():
        return False, f"File {src_path.name} không tồn tại trên đĩa."
        
    shutil.copy2(src_path, dest_path)
    seg_data["selected_take"] = int(take_num)
    seg_data["selected_file"] = str(dest_path.relative_to(project_dir))
    save_project_state(project_dir, project_state)
    return True, f"Đã chọn Take {take_num} cho phân đoạn {seg_id}."


def get_take_audio_paths(project_dir: Path, project_state: dict, seg_id: str) -> Dict[int, Optional[str]]:
    """Lấy đường dẫn các file take của segment để nghe thử."""
    seg_id = str(seg_id).zfill(3)
    seg_data = project_state.get("segments", {}).get(seg_id, {})
    takes = seg_data.get("takes", {})
    
    paths = {1: None, 2: None, 3: None}
    for t_num in [1, 2, 3]:
        rel = takes.get(str(t_num))
        if rel:
            abs_p = project_dir / rel
            if abs_p.exists():
                paths[t_num] = str(abs_p)
    return paths

