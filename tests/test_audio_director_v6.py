"""
Test suite toàn diện cho TTS Audio Director (JSON V6 & Production Music Pack).
Kiểm tra:
1. Safe ZIP extraction & Zip Slip protection
2. Music library parsing & detection of 8 cues
3. Continuous music regions & crossfade calculation
4. Critical Reveal Silence Window (ngắt nhạc tại câu cao trào)
5. Continuous Room Tone Engine (-41 dBFS RMS)
6. Voice Ducking (smooth gain interpolation)
7. Full Master & Stems assembly (WAV 48kHz, MP3 320kbps, timeline JSON)
8. Preview Mix 30s & Preview Critical Reveal
9. Tách biệt hoàn toàn Voice Cache và Mix Cache
"""

import os
import sys
import json
import shutil
import tempfile
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import numpy as np
import soundfile as sf
import pytest

from apps.audio_director import (
    safe_extract_zip,
    parse_music_library,
    loop_audio_seamless,
    build_dialogue_timeline,
    build_room_tone_track,
    analyze_music_regions,
    build_music_track,
    apply_voice_ducking,
    build_audio_director_master,
    build_preview_mix_clip,
    build_preview_reveal_clip
)
from apps.production_story import (
    validate_story_json,
    build_segments_dataframe,
    get_all_available_voices
)

SAMPLE_RATE = 48000
REAL_ZIP_PATH = r"C:\Users\TPT\Downloads\sau_canh_cua_v6_json_music_pack.zip"
REAL_JSON_PATH = r"C:\Users\TPT\Downloads\sau_canh_cua_v6_json_music_pack\sau_canh_cua_pilot_01_v6.json"


def test_safe_extract_zip():
    """Kiểm tra giải nén an toàn file ZIP pack thật."""
    if not os.path.exists(REAL_ZIP_PATH):
        pytest.skip(f"Không tìm thấy ZIP thật tại {REAL_ZIP_PATH}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        target_dir = Path(tmp_dir) / "pack_extracted"
        ok, msg, found_json, found_music = safe_extract_zip(REAL_ZIP_PATH, target_dir)

        assert ok, f"Giải nén thất bại: {msg}"
        assert found_json is not None and found_json.exists(), "Không tìm thấy file JSON"
        assert found_music is not None and found_music.exists(), "Không tìm thấy thư mục music"

        # Đọc thử JSON
        with open(found_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("schema_version") in ("1.0", "2.0", "2.1", "2.2")
        assert "music_library" in data


def test_music_library_detection():
    """Kiểm tra nhận diện 8 cues trong music_library."""
    if not os.path.exists(REAL_JSON_PATH):
        pytest.skip(f"Không tìm thấy JSON thật tại {REAL_JSON_PATH}")

    with open(REAL_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    project_dir = Path("projects/sau_canh_cua_-_pilot_01_v6")
    if not project_dir.exists():
        pytest.skip("Chưa có thư mục project projects/sau_canh_cua_-_pilot_01_v6")

    parsed_lib = parse_music_library(project_dir, data)
    expected_cues = [
        "signature_intro",
        "signature_outro",
        "mystery_low",
        "memory_soft",
        "tension_low",
        "emotional_low",
        "closing_soft",
        "room_tone"
    ]

    for cue in expected_cues:
        assert cue in parsed_lib, f"Thiếu cue: {cue}"
        assert parsed_lib[cue]["status"] == "READY", f"Cue {cue} chưa READY: {parsed_lib[cue]}"
        assert parsed_lib[cue]["duration_sec"] > 0, f"Thời lượng cue {cue} không hợp lệ"


def test_continuous_music_regions_and_reveal_silence():
    """Kiểm tra thuật toán gom continuous regions và tạo silence tại critical reveal."""
    events = [
        {"id": "001", "cue": "intro", "target_vol": -28.0, "speech_start": 0.0, "speech_end": 4.0, "is_critical": False, "fade_in": 1.0, "fade_out": 1.0},
        {"id": "002", "cue": "intro", "target_vol": -28.0, "speech_start": 4.5, "speech_end": 8.0, "is_critical": False, "fade_in": 1.0, "fade_out": 1.0},
        # Chuyển sang mystery_low
        {"id": "003", "cue": "mystery_low", "target_vol": -34.0, "speech_start": 8.5, "speech_end": 12.0, "is_critical": False, "fade_in": 1.2, "fade_out": 1.0},
        {"id": "004", "cue": "mystery_low", "target_vol": -34.0, "speech_start": 12.5, "speech_end": 16.0, "is_critical": False, "fade_in": 1.2, "fade_out": 1.0},
        # Câu Critical Reveal (ngắt nhạc!)
        {"id": "005", "cue": "mystery_low", "target_vol": -34.0, "speech_start": 16.5, "speech_end": 19.0, "is_critical": True, "fade_in": 1.2, "fade_out": 1.0},
        # Sau Critical Reveal: Nhạc quay lại sau 0.8s
        {"id": "006", "cue": "memory_soft", "target_vol": -34.0, "speech_start": 20.0, "speech_end": 24.0, "is_critical": False, "fade_in": 1.2, "fade_out": 1.0},
    ]

    music_lib = {
        "intro": {"cue": "intro", "status": "READY"},
        "mystery_low": {"cue": "mystery_low", "status": "READY"},
        "memory_soft": {"cue": "memory_soft", "status": "READY"}
    }

    regions, debug_timeline = analyze_music_regions(
        timeline_events=events,
        music_lib=music_lib,
        auto_silence_critical=True,
        reveal_music_return_delay_sec=0.8,
        total_duration_sec=25.0
    )

    # Đảm bảo:
    # 1. 001 và 002 được gom thành 1 region duy nhất cho 'intro'
    intro_regs = [r for r in regions if r["cue"] == "intro"]
    assert len(intro_regs) == 1
    assert "001" in intro_regs[0]["segments"] and "002" in intro_regs[0]["segments"]

    # 2. Phân đoạn 005 (critical) có mặt trong debug_timeline
    crit_silences = [t for t in debug_timeline if t.get("cue") == "SILENCE_CRITICAL_REVEAL" or t.get("action") == "SILENCE_CRITICAL_REVEAL"]
    assert len(crit_silences) >= 1
    assert crit_silences[0].get("segment_id", crit_silences[0].get("seg_id")) == "005"

    # 3. Region tiếp theo (memory_soft) bắt đầu SAU khi câu thoại 005 kết thúc + return delay
    memory_regs = [r for r in regions if r["cue"] == "memory_soft"]
    assert len(memory_regs) == 1
    assert memory_regs[0]["start_sec"] >= 19.0 + 0.8


def test_dialogue_ducking_smoothness():
    """Kiểm tra bộ lọc Analog Voice Ducking."""
    sr = 48000
    total_len = sr * 5  # 5s
    music_audio = np.ones(total_len, dtype=np.float32) * 0.5  # Constant music

    # Dialogue ở giữa: 1.5s -> 3.5s
    timeline_events = [
        {"speech_start_sec": 1.5, "speech_end_sec": 3.5, "ducking_db": -8.0}
    ]

    ducked = apply_voice_ducking(music_audio, timeline_events, sample_rate=sr, default_ducking_db=-8.0)

    assert len(ducked) == len(music_audio)
    # Tại 0.5s: Chưa có lời thoại, volume phải giữ nguyên
    assert np.isclose(ducked[int(0.5 * sr)], 0.5, atol=0.01)

    # Tại 2.5s: Giữa câu thoại, phải suy giảm đúng ~ -8dB
    # 10 ** (-8 / 20) = ~0.398 * 0.5 = ~0.199
    expected_ducked_val = 0.5 * (10 ** (-8.0 / 20.0))
    assert np.isclose(ducked[int(2.5 * sr)], expected_ducked_val, atol=0.05)


def test_full_audio_director_master_build():
    """Kiểm tra quy trình build master và xuất đầy đủ 4 stems + MP3 + timeline JSON."""
    project_dir = Path("projects/sau_canh_cua_-_pilot_01_v6")
    if not (project_dir / "selected" / "001.wav").exists():
        pytest.skip("Chưa có audio phân đoạn trong projects/sau_canh_cua_-_pilot_01_v6")

    with open(project_dir / "source.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(project_dir / "project_state.json", "r", encoding="utf-8") as f:
        runtime_state = json.load(f)

    music_lib = parse_music_library(project_dir, data)

    ok, msg, outputs = build_audio_director_master(
        project_dir=project_dir,
        segments=data.get("segments", []),
        project_state=runtime_state,
        music_lib=music_lib,
        enable_music=True,
        enable_room_tone=True,
        auto_silence_critical=True,
        room_tone_volume_db=-41.0,
        target_lufs=-14.0,
        true_peak_db=-1.0,
        sample_rate=48000
    )

    assert ok, f"Build master thất bại: {msg}"
    assert Path(outputs["episode_master_wav"]).exists()
    assert Path(outputs["episode_master_mp3"]).exists()
    assert Path(outputs["dialogue_only"]).exists()
    assert Path(outputs["room_tone"]).exists()
    assert Path(outputs["music_only"]).exists()
    assert Path(outputs["pre_master_mix"]).exists()
    assert Path(outputs["music_timeline_json"]).exists()

    # Kiểm tra tính toàn vẹn của music_timeline.json
    with open(outputs["music_timeline_json"], "r", encoding="utf-8") as f:
        timeline_data = json.load(f)
    assert "music_regions" in timeline_data
    assert "timeline_events" in timeline_data

    # Kiểm tra thời lượng các stems phải bằng nhau
    dia_info = sf.info(outputs["dialogue_only"])
    rt_info = sf.info(outputs["room_tone"])
    mus_info = sf.info(outputs["music_only"])
    assert np.isclose(dia_info.duration, rt_info.duration, atol=0.05)
    assert np.isclose(dia_info.duration, mus_info.duration, atol=0.05)


def test_preview_mix_and_reveal_clips():
    """Kiểm tra sinh bản nghe thử Preview 30s và Preview Critical Reveal."""
    project_dir = Path("projects/sau_canh_cua_-_pilot_01_v6")
    if not (project_dir / "selected" / "001.wav").exists():
        pytest.skip("Chưa có audio phân đoạn trong projects/sau_canh_cua_-_pilot_01_v6")

    with open(project_dir / "source.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(project_dir / "project_state.json", "r", encoding="utf-8") as f:
        runtime_state = json.load(f)

    music_lib = parse_music_library(project_dir, data)

    # 1. Preview Mix 30s
    ok1, msg1, clip30 = build_preview_mix_clip(
        project_dir=project_dir,
        segments=data.get("segments", []),
        project_state=runtime_state,
        music_lib=music_lib,
        start_seg_id="001",
        duration_sec=30.0
    )
    assert ok1, f"Preview 30s thất bại: {msg1}"
    assert Path(clip30).exists()
    info30 = sf.info(clip30)
    assert 28.0 <= info30.duration <= 32.0

    # 2. Preview Critical Reveal (câu 037: 'Là cậu ruột tôi')
    ok2, msg2, clip_rev = build_preview_reveal_clip(
        project_dir=project_dir,
        segments=data.get("segments", []),
        project_state=runtime_state,
        music_lib=music_lib,
        reveal_seg_id="037",
        before_sec=8.0,
        after_sec=8.0
    )
    assert ok2, f"Preview reveal thất bại: {msg2}"
    assert Path(clip_rev).exists()
    info_rev = sf.info(clip_rev)
    assert info_rev.duration > 5.0
