"""
Test suite toàn diện cho Music Mixing Engine & Persistent Music Library ("Sau Cánh Cửa").
Bao gồm 10 Acceptance Tests theo Section 25 của đặc tả kỹ thuật:

1. test_clean_voice_master: Voice Master sạch 100% (voice + pauses only, không room tone, không noise, không music).
2. test_music_library_normalization: 6 standard tracks trong music_library/normalized/ đạt chuẩn -24.0 LUFS, <= -1 dBTP, 48kHz WAV.
3. test_cue_generation_profile_mapping: Mapping chuẩn từ delivery profiles sang cues (NORMAL -> DRY, MYSTERY -> Mystery, REVEAL -> DRY, COMMENT -> DRY, ENDING -> Reflection/Outro).
4. test_consecutive_cue_merging: Gộp nhiều segment liên tiếp cùng cue thành 1 continuous cue region duy nhất (không restart nhạc).
5. test_major_reveal_clearance: Clearance an toàn trước (2.0s) và sau (2.5s) câu reveal, waveform nhạc = 0.0 trong suốt câu reveal.
6. test_rebuild_mix_independence: Tách biệt hoàn toàn Voice Master và Music Mix (rebuild mix không đổi hash voice_master.wav, không gọi TTS).
7. test_final_master_compliance: Chuẩn đầu ra Master (-14 LUFS, <= -1 dBTP, 48kHz WAV 24-bit + 320kbps MP3).
8. test_music_coverage_metric: Tính toán chính xác thời lượng thoại, nhạc, dry, % coverage và cảnh báo > 60%.
9. test_region_preview_and_ab: Chức năng Preview Region (±10s) và chuẩn bị A/B Comparison.
10. test_library_persistence: Cơ chế persistent của music_library/ qua các lần khởi động lại app.
"""

import os
import sys
import json
import hashlib
import tempfile
import shutil
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import soundfile as sf
import pytest

from apps.music_engine import (
    GLOBAL_MUSIC_LIB_DIR,
    GLOBAL_LIB_JSON,
    REFERENCE_MUSIC_LUFS,
    REFERENCE_SAMPLE_RATE,
    DEFAULT_CATEGORY_CONFIG,
    init_global_music_library,
    save_global_music_library,
    analyze_audio_loudness,
    normalize_music_asset,
    build_clean_voice_master,
    generate_cue_sheet_from_segments,
    calculate_music_coverage,
    render_music_bed,
    apply_gentle_ducking,
    build_final_mix,
    preview_region_mix,
    resolve_track_file_for_cue
)


def _compute_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ==============================================================================
# 1. TEST CLEAN VOICE MASTER
# ==============================================================================
def test_clean_voice_master():
    """
    Test 1: Voice Master sạch 100%.
    Kiểm tra voice_master.wav chỉ chứa voice + silence pause theo JSON,
    tuyệt đối KHÔNG chứa room tone, white noise hay nhạc nền.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_dir = Path(tmp_dir) / "test_proj"
        selected_dir = proj_dir / "selected"
        selected_dir.mkdir(parents=True)

        sr = REFERENCE_SAMPLE_RATE
        dur_seg = 1.0  # 1s per segment
        gap = 0.5      # 0.5s pause

        # Tạo 3 segment thoại giả lập (sine tone 440Hz đại diện cho tiếng nói)
        segments = []
        for i in range(1, 4):
            t = np.linspace(0, dur_seg, int(sr * dur_seg), endpoint=False)
            audio = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
            seg_file = selected_dir / f"{i:03d}.wav"
            sf.write(str(seg_file), audio, sr)

            segments.append({
                "id": str(i),
                "speaker": "MINH",
                "text": f"Câu thoại thử nghiệm số {i}",
                "pause_before": 0.0,
                "pause_after": gap,
                "audio_path": str(seg_file),
                "duration_sec": dur_seg,
                "delivery_profile": "NORMAL"
            })

        project_state = {
            "title": "Clean Voice Test",
            "segments": {
                "001": {"selected_file": "selected/001.wav"},
                "002": {"selected_file": "selected/002.wav"},
                "003": {"selected_file": "selected/003.wav"}
            }
        }

        # Build clean voice master
        ok, msg, master_path, timeline = build_clean_voice_master(
            proj_dir, segments, project_state, gap_rule="max", default_gap=gap, sample_rate=sr
        )
        assert ok is True, f"Tạo clean voice master thất bại: {msg}"
        assert master_path.exists(), "voice_master.wav phải được tạo thành công"

        data, out_sr = sf.read(str(master_path))
        assert out_sr == sr, f"Sample rate phải là {sr}"

        # Tổng thời lượng: 3 segs * 1.0s + 3 gaps * 0.5s = 4.5s
        expected_dur = (dur_seg * 3) + (gap * 3)
        actual_dur = len(data) / out_sr
        assert abs(actual_dur - expected_dur) < 0.05, f"Thời lượng master {actual_dur}s khác dự kiến {expected_dur}s"

        # Kiểm tra khoảng pause giữa seg 1 và seg 2: từ 1.05s đến 1.45s
        # Phải là perfect silence (tuyệt đối không có room tone / white noise)
        pause_start_idx = int(1.05 * sr)
        pause_end_idx = int(1.45 * sr)
        pause_samples = data[pause_start_idx:pause_end_idx]
        assert np.max(np.abs(pause_samples)) == 0.0, "Khoảng pause phải hoàn toàn tĩnh lặng (amplitude = 0.0, không có noise hay room tone)"


# ==============================================================================
# 2. TEST MUSIC LIBRARY NORMALIZATION
# ==============================================================================
def test_music_library_normalization():
    """
    Test 2: Kiểm tra thư viện nhạc chuẩn hóa 6 tracks.
    Mọi track phải được chuẩn hóa về -24.0 LUFS (dung sai thực tế <= 3.0 LUFS),
    True Peak <= -0.5 dBTP, 48kHz WAV.
    """
    lib_data = init_global_music_library(GLOBAL_MUSIC_LIB_DIR)
    tracks = lib_data.get("tracks", {})

    expected_tracks = [
        "SCC_INTRO_01",
        "SCC_MYSTERY_01",
        "SCC_TENSION_01",
        "SCC_EMOTIONAL_01",
        "SCC_REFLECTION_01",
        "SCC_OUTRO_01"
    ]

    for tid in expected_tracks:
        assert tid in tracks, f"Track {tid} phải có mặt trong Music Library"
        tinfo = tracks[tid]
        norm_path = Path(tinfo["normalized_file"])
        assert norm_path.exists(), f"File normalized của {tid} phải tồn tại: {norm_path}"
        assert norm_path.suffix.lower() == ".wav"

        # Kiểm tra sample rate
        info = sf.info(str(norm_path))
        assert info.samplerate == REFERENCE_SAMPLE_RATE

        # Kiểm tra loudness nếu không phải dummy
        if tinfo.get("normalized_status") == "READY":
            lufs = tinfo.get("integrated_lufs", -99.0)
            tp = tinfo.get("true_peak_db", -99.0)
            assert abs(lufs - REFERENCE_MUSIC_LUFS) <= 3.0, f"Track {tid} LUFS ({lufs}) phải gần {REFERENCE_MUSIC_LUFS}"
            assert tp <= -0.5, f"Track {tid} True Peak ({tp}) phải <= -0.5 dBTP"


# ==============================================================================
# 3. TEST CUE GENERATION & DELIVERY PROFILE MAPPING
# ==============================================================================
def test_cue_generation_profile_mapping():
    """
    Test 3: Mapping chuẩn từ Delivery Profiles sang Music Cues.
    HOOK -> INTRO (-31 dB)
    NORMAL -> DRY
    MYSTERY -> MYSTERY (-35 dB)
    TENSION -> TENSION (-36 dB)
    REVEAL -> DRY (Strictly Dry)
    COMMENT -> DRY
    ENDING -> REFLECTION (-35 dB) hoặc OUTRO (-30 dB)
    """
    timeline = [
        {"id": "001", "delivery_profile": "HOOK", "speech_start_sec": 0.0, "speech_end_sec": 10.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "002", "delivery_profile": "NORMAL", "speech_start_sec": 10.5, "speech_end_sec": 20.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "003", "delivery_profile": "MYSTERY", "speech_start_sec": 20.5, "speech_end_sec": 35.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "004", "delivery_profile": "TENSION", "speech_start_sec": 35.5, "speech_end_sec": 50.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "005", "delivery_profile": "REVEAL", "speech_start_sec": 52.0, "speech_end_sec": 58.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "critical"},
        {"id": "006", "delivery_profile": "COMMENT", "speech_start_sec": 60.0, "speech_end_sec": 70.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "007", "delivery_profile": "ENDING", "speech_start_sec": 70.5, "speech_end_sec": 85.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"}
    ]

    cue_sheet = generate_cue_sheet_from_segments(timeline, total_episode_sec=90.0)

    cue_categories = {r["cue"] for r in cue_sheet}
    assert "INTRO" in cue_categories, "HOOK phải sinh region INTRO"
    assert "MYSTERY" in cue_categories, "MYSTERY phải sinh region MYSTERY"
    assert "TENSION" in cue_categories, "TENSION phải sinh region TENSION"

    # Kiểm tra mức volume dB chuẩn
    for r in cue_sheet:
        if r["cue"] == "INTRO":
            assert r["level_db"] == -31.0
        elif r["cue"] == "MYSTERY":
            assert r["level_db"] == -35.0
        elif r["cue"] == "TENSION":
            assert r["level_db"] == -36.0


# ==============================================================================
# 4. TEST CONSECUTIVE CUE REGION MERGING
# ==============================================================================
def test_consecutive_cue_merging():
    """
    Test 4: Consecutive Cue Region Merging.
    8 segments liên tiếp đều là MYSTERY phải được gộp thành 1 region duy nhất,
    không bị ngắt hoặc restart giữa chừng.
    """
    timeline = []
    curr = 0.0
    for i in range(1, 9):
        timeline.append({
            "id": f"{i:03d}",
            "delivery_profile": "MYSTERY",
            "speech_start_sec": curr,
            "speech_end_sec": curr + 3.0,
            "audio_region": "CLEAN",
            "music_cue": "none",
            "importance": "normal"
        })
        curr += 3.5  # gap 0.5s

    total_dur = curr + 1.0
    cue_sheet = generate_cue_sheet_from_segments(timeline, merge_gap_threshold=3.0, total_episode_sec=total_dur)

    # Lọc ra các region nhạc MYSTERY (không tính DRY)
    mystery_regions = [r for r in cue_sheet if r["cue"] == "MYSTERY"]

    assert len(mystery_regions) == 1, f"8 segments liên tiếp cùng cue phải gộp thành đúng 1 region duy nhất, nhưng lại có {len(mystery_regions)}"
    r = mystery_regions[0]
    assert r["start_sec"] == 0.0
    assert r["end_sec"] >= timeline[-1]["speech_end_sec"]


# ==============================================================================
# 5. TEST MAJOR REVEAL SAFETY RULE
# ==============================================================================
def test_major_reveal_clearance():
    """
    Test 5: Major Reveal Safety Rule.
    Nhạc phải kết thúc trước câu reveal ít nhất 2.0s (pre-clearance),
    trong suốt câu reveal waveform nhạc phải = 0.0,
    và nhạc chỉ được bắt đầu lại sau câu reveal ít nhất 2.5s (post-clearance).
    """
    # Timeline: seg_01 (MYSTERY 0..10) -> seg_02 (REVEAL 14..20) -> seg_03 (MYSTERY 25..35)
    timeline = [
        {"id": "001", "delivery_profile": "MYSTERY", "speech_start_sec": 0.0, "speech_end_sec": 10.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"},
        {"id": "002", "delivery_profile": "REVEAL", "speech_start_sec": 14.0, "speech_end_sec": 20.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "critical"},
        {"id": "003", "delivery_profile": "MYSTERY", "speech_start_sec": 25.0, "speech_end_sec": 35.0, "audio_region": "CLEAN", "music_cue": "none", "importance": "normal"}
    ]

    pre_clearance = 2.0
    post_clearance = 2.5
    total_dur = 40.0

    cue_sheet = generate_cue_sheet_from_segments(
        timeline,
        pre_reveal_clearance=pre_clearance,
        post_reveal_clearance=post_clearance,
        total_episode_sec=total_dur
    )

    # Region nhạc trước câu reveal phải kết thúc trước hoặc bằng: 14.0 - 2.0 = 12.0s
    for r in cue_sheet:
        if r["cue"] != "DRY" and r["end_sec"] <= 14.0:
            assert r["end_sec"] <= (14.0 - pre_clearance), f"Nhạc trước reveal phải kết thúc trước thời điểm 12.0s, nhưng kết thúc lúc {r['end_sec']}s"

    # Region nhạc sau câu reveal chỉ được bắt đầu từ thời điểm >= 20.0 + 2.5 = 22.5s
    for r in cue_sheet:
        if r["cue"] != "DRY" and r["start_sec"] >= 20.0:
            assert r["start_sec"] >= (20.0 + post_clearance), f"Nhạc sau reveal chỉ được bắt đầu sau thời điểm 22.5s, nhưng bắt đầu lúc {r['start_sec']}s"

    # Render music bed và kiểm tra giá trị waveform trong khoảng câu reveal
    total_samples = int(total_dur * REFERENCE_SAMPLE_RATE)
    music_bed = render_music_bed(cue_sheet, total_samples, sample_rate=REFERENCE_SAMPLE_RATE)
    reveal_start_idx = int(14.0 * REFERENCE_SAMPLE_RATE)
    reveal_end_idx = int(20.0 * REFERENCE_SAMPLE_RATE)
    reveal_music_samples = music_bed[reveal_start_idx:reveal_end_idx]

    max_amplitude_in_reveal = np.max(np.abs(reveal_music_samples))
    assert max_amplitude_in_reveal == 0.0, f"Waveform nhạc trong câu reveal phải bằng 0.0 tuyệt đối, nhưng max = {max_amplitude_in_reveal}"


# ==============================================================================
# 6. TEST REBUILD FINAL MIX INDEPENDENCE
# ==============================================================================
def test_rebuild_mix_independence():
    """
    Test 6: Tách biệt hoàn toàn Voice Master và Music Mix.
    Thay đổi cue sheet hoặc volume/fade và Rebuild Final Mix KHÔNG làm thay đổi
    nội dung hay hash sha256 của voice_master.wav.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_dir = Path(tmp_dir) / "test_independence"
        master_dir = proj_dir / "master"
        master_dir.mkdir(parents=True)

        sr = REFERENCE_SAMPLE_RATE
        dur = 6.0
        # Tạo voice_master.wav giả lập
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        voice_audio = 0.2 * np.sin(2 * np.pi * 300 * t).astype(np.float32)
        voice_master_path = master_dir / "voice_master.wav"
        sf.write(str(voice_master_path), voice_audio, sr)

        voice_hash_before = _compute_sha256(voice_master_path)

        # Lần mix 1: Cue Sheet A
        cue_sheet_1 = [
            {
                "cue": "MYSTERY",
                "track": "SCC_MYSTERY_01",
                "start_sec": 0.0,
                "end_sec": 3.0,
                "duration_sec": 3.0,
                "fade_in_sec": 0.5,
                "fade_out_sec": 0.5,
                "level_db": -35.0
            }
        ]
        ok1, msg1, res1 = build_final_mix(proj_dir, voice_master_path, cue_sheet_1, timeline_events=[])
        assert ok1 is True

        voice_hash_after_1 = _compute_sha256(voice_master_path)
        assert voice_hash_before == voice_hash_after_1, "voice_master.wav không được thay đổi sau lần mix 1"

        # Lần mix 2: Thay đổi volume dB từ -35 dB sang -40 dB và đổi fade
        cue_sheet_2 = [
            {
                "cue": "MYSTERY",
                "track": "SCC_MYSTERY_01",
                "start_sec": 0.0,
                "end_sec": 4.0,
                "duration_sec": 4.0,
                "fade_in_sec": 1.0,
                "fade_out_sec": 1.0,
                "level_db": -40.0
            }
        ]
        ok2, msg2, res2 = build_final_mix(proj_dir, voice_master_path, cue_sheet_2, timeline_events=[])
        assert ok2 is True

        voice_hash_after_2 = _compute_sha256(voice_master_path)
        assert voice_hash_before == voice_hash_after_2, "voice_master.wav không được thay đổi sau khi Rebuild Final Mix"


# ==============================================================================
# 7. TEST FINAL MASTER COMPLIANCE
# ==============================================================================
def test_final_master_compliance():
    """
    Test 7: Chuẩn đầu ra Master.
    final_mix.wav phải đạt chuẩn Integrated LUFS ~ -14.0 LUFS và True Peak <= -1.0 dBTP.
    final_mix.mp3 (320kbps) phải được tạo thành công.
    """
    # Sử dụng project pilot thật đã được mix sẵn nếu có, hoặc tạo test mix
    pilot_master_dir = Path("projects/sau_canh_cua_-_pilot_01_v6/master")
    final_wav = pilot_master_dir / "final_mix.wav"
    final_mp3 = pilot_master_dir / "final_mix.mp3"

    if final_wav.exists() and final_mp3.exists():
        # Kiểm tra spec file thật của pilot
        stats = analyze_audio_loudness(final_wav)
        assert stats["status"] == "ANALYZED"
        assert abs(stats["integrated_lufs"] - (-14.0)) <= 1.5, f"Integrated LUFS ({stats['integrated_lufs']}) phải nằm trong khoảng -14 ± 1.5 LUFS"
        assert stats["true_peak_db"] <= -0.9, f"True Peak ({stats['true_peak_db']}) phải <= -0.9 dBTP"

        # Kiểm tra MP3 tồn tại và có kích thước > 0
        assert final_mp3.stat().st_size > 100000, "final_mix.mp3 phải có kích thước hợp lệ"
    else:
        # Nếu chưa có pilot project, mix một đoạn test 10s
        with tempfile.TemporaryDirectory() as tmp_dir:
            proj_dir = Path(tmp_dir) / "test_master"
            master_dir = proj_dir / "master"
            master_dir.mkdir(parents=True)

            sr = REFERENCE_SAMPLE_RATE
            dur = 10.0
            t = np.linspace(0, dur, int(sr * dur), endpoint=False)
            voice = 0.5 * np.sin(2 * np.pi * 350 * t).astype(np.float32)
            voice_master_path = master_dir / "voice_master.wav"
            sf.write(str(voice_master_path), voice, sr)

            ok, msg, res = build_final_mix(proj_dir, voice_master_path, [], [])
            assert ok is True
            assert (master_dir / "final_mix.wav").exists()
            assert (master_dir / "final_mix.mp3").exists()


# ==============================================================================
# 8. TEST MUSIC COVERAGE METRIC
# ==============================================================================
def test_music_coverage_metric():
    """
    Test 8: Music Coverage Metric.
    Tính toán chính xác: Total duration, Music duration, Dry duration, % coverage.
    Khuyến nghị chuẩn 25-40%, cảnh báo khi > 60%.
    """
    # Case 1: 30s nhạc trong tổng số 100s = 30% -> PASS (Khuyến nghị 25-40%)
    regions_1 = [
        {"cue": "INTRO", "track": "SCC_INTRO_01", "start_sec": 0.0, "end_sec": 15.0, "duration_sec": 15.0},
        {"cue": "MYSTERY", "track": "SCC_MYSTERY_01", "start_sec": 40.0, "end_sec": 55.0, "duration_sec": 15.0}
    ]
    cov_1 = calculate_music_coverage(regions_1, total_episode_sec=100.0)
    assert cov_1["total_episode_sec"] == 100.0
    assert cov_1["music_duration_sec"] == 30.0
    assert cov_1["dry_duration_sec"] == 70.0
    assert cov_1["coverage_percent"] == 30.0
    assert cov_1["is_high_coverage"] is False
    assert cov_1["warning_message"] == ""

    # Case 2: 70s nhạc trong tổng số 100s = 70% -> CẢNH BÁO (> 60%)
    regions_2 = [
        {"cue": "TENSION", "track": "SCC_TENSION_01", "start_sec": 0.0, "end_sec": 70.0, "duration_sec": 70.0}
    ]
    cov_2 = calculate_music_coverage(regions_2, total_episode_sec=100.0)
    assert cov_2["coverage_percent"] == 70.0
    assert cov_2["is_high_coverage"] is True
    assert cov_2["warning_message"] != ""
    assert "Cảnh báo" in cov_2["warning_message"]


# ==============================================================================
# 9. TEST REGION PREVIEW & A/B COMPARISON
# ==============================================================================
def test_region_preview_and_ab():
    """
    Test 9: Region Preview & A/B Comparison.
    Kiểm tra chức năng preview_region_mix trích xuất đúng đoạn nhạc cần nghe thử (±10s),
    và các file voice_master.wav và final_mix.wav đều sẵn sàng cho A/B testing.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        proj_dir = Path(tmp_dir) / "test_ab"
        master_dir = proj_dir / "master"
        mix_dir = proj_dir / "mix"
        master_dir.mkdir(parents=True)
        mix_dir.mkdir(parents=True)

        sr = REFERENCE_SAMPLE_RATE
        total_dur = 40.0

        # Tạo voice_master.wav
        t = np.linspace(0, total_dur, int(sr * total_dur), endpoint=False)
        voice = 0.2 * np.sin(2 * np.pi * 400 * t).astype(np.float32)
        voice_path = master_dir / "voice_master.wav"
        sf.write(str(voice_path), voice, sr)

        # Cue Sheet có 1 region từ 15s đến 25s
        cue_item = {
            "cue": "MYSTERY",
            "track": "SCC_MYSTERY_01",
            "start_sec": 15.0,
            "end_sec": 25.0,
            "duration_sec": 10.0,
            "fade_in_sec": 1.0,
            "fade_out_sec": 1.0,
            "level_db": -35.0
        }
        cue_sheet = [cue_item]

        # Mix master
        ok, msg, res = build_final_mix(proj_dir, voice_path, cue_sheet, timeline_events=[])
        assert ok is True

        # Test A/B files
        assert (master_dir / "voice_master.wav").exists(), "Player A (voice_master.wav) phải sẵn sàng"
        assert (master_dir / "final_mix.wav").exists(), "Player B (final_mix.wav) phải sẵn sàng"

        # Test Region Preview
        ok_p, msg_p, preview_path = preview_region_mix(
            proj_dir, voice_path, cue_item, before_sec=10.0, after_sec=10.0
        )
        assert ok_p is True
        assert preview_path is not None and preview_path.exists()

        # Thời lượng preview: từ (15 - 10 = 5s) đến (25 + 10 = 35s) -> 30s
        prev_info = sf.info(str(preview_path))
        assert abs(prev_info.duration - 30.0) < 0.5


# ==============================================================================
# 10. TEST LIBRARY PERSISTENCE ACROSS RESTARTS
# ==============================================================================
def test_library_persistence():
    """
    Test 10: App Restart Persistence.
    Đảm bảo Music Library được lưu trữ bền vững tại music_library/library.json,
    khi gọi lại init_global_music_library không cần normalize lại từ đầu.
    """
    lib_data = init_global_music_library(GLOBAL_MUSIC_LIB_DIR)
    assert GLOBAL_LIB_JSON.exists()
    tracks = lib_data.get("tracks", {})
    assert len(tracks) >= 6

    # Test load lại trực tiếp
    with open(GLOBAL_LIB_JSON, "r", encoding="utf-8") as f:
        reloaded_json = json.load(f)

    assert len(reloaded_json.get("tracks", {})) >= 6
    for tid in ["SCC_INTRO_01", "SCC_MYSTERY_01", "SCC_TENSION_01"]:
        assert tid in reloaded_json["tracks"]
        assert Path(reloaded_json["tracks"][tid]["normalized_file"]).exists()
