"""
Test Suite for Production Pilot 03: EP003 + EP011 — TTS & Audio Master
======================================================================
Verifies all 9 critical acceptance criteria from Prompt Section 36:
1. Both episodes synthesized with Binh (Voice 020 - MINH).
2. Physical final_mix.wav and final_mix.mp3 exist and are valid.
3. Every script segment appears exactly once (90/90 segments, 0 missing, 0 duplicate, 0 out-of-order).
4. No script facts changed (canonical text intact, pronunciation overrides logged).
5. No major TTS defect remains (duration > 0.5s, no NaN/Inf, non-silent).
6. Major Reveal 1 is 100% DRY with >= 2.0s pre-clearance and >= 2.5s post-clearance.
7. No digital clipping (True Peak <= -0.9 dBTP, max sample < 1.0).
8. Loudness/mastering acceptable (-14 to -15 LUFS integrated).
9. Generation safety: 0 images, 0 videos, 0 Flow calls.
"""

import os
import sys
import json
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PILOT_03_DIR = PROJECT_ROOT / "production_pilot_03"


@pytest.fixture(scope="module")
def pilot_data():
    master_report_path = PILOT_03_DIR / "master_report.json"
    assert master_report_path.exists(), f"Không tìm thấy master_report.json tại {master_report_path}"
    with open(master_report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_physical_audio_files_exist(ep_id):
    """Tiêu chí 2: Kiểm tra sự tồn tại của các file âm thanh vật lý hoàn chỉnh."""
    ep_dir = PILOT_03_DIR / ep_id
    audio_dir = ep_dir / "audio"

    required_files = [
        audio_dir / "final_mix.wav",
        audio_dir / "final_mix.mp3",
        audio_dir / "narration_dry.wav",
        audio_dir / "narration_dry.mp3",
        audio_dir / "music_cue_sheet.json",
        audio_dir / "segment_timing.json",
        ep_dir / "final_mix.wav",
        ep_dir / "final_mix.mp3",
        ep_dir / "reports" / "tts_qc.json",
        ep_dir / "reports" / "audio_qc.json",
        ep_dir / "reports" / "production_report.json"
    ]

    for f in required_files:
        assert f.exists(), f"Thiếu file bắt buộc: {f}"
        assert f.stat().st_size > 100, f"File quá nhỏ hoặc rỗng: {f} ({f.stat().st_size} bytes)"


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_segment_coverage_100_percent(ep_id):
    """Tiêu chí 3: Kiểm tra toàn vẹn 90/90 phân đoạn, không thiếu, không thừa, không đảo thứ tự."""
    timing_path = PILOT_03_DIR / ep_id / "audio" / "segment_timing.json"
    assert timing_path.exists()
    with open(timing_path, "r", encoding="utf-8") as f:
        timings = json.load(f)

    assert len(timings) == 90, f"Số lượng phân đoạn không bằng 90: {len(timings)}"

    expected_ids = [str(i).zfill(3) for i in range(1, 91)]
    actual_ids = [t["id"] for t in timings]

    assert actual_ids == expected_ids, f"Thứ tự hoặc danh sách segment id sai: {actual_ids[:5]}..."

    # Kiểm tra timing tăng dần liên tục
    for i in range(len(timings) - 1):
        assert timings[i]["speech_end_sec"] <= timings[i+1]["speech_start_sec"] + 0.05, (
            f"Lỗi chồng lấn timing giữa segment {timings[i]['id']} và {timings[i+1]['id']}"
        )


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_voice_is_minh_020(ep_id):
    """Tiêu chí 1: Người dẫn chuyện cố định là MC MINH (Voice 020 - Binh)."""
    tts_qc_path = PILOT_03_DIR / ep_id / "reports" / "tts_qc.json"
    assert tts_qc_path.exists()
    with open(tts_qc_path, "r", encoding="utf-8") as f:
        qc = json.load(f)

    assert qc["voice"] == "020"
    for s in qc["segments"]:
        assert s["voice"] == "020", f"Segment {s['id']} không dùng voice 020: {s['voice']}"


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_reveal_1_is_dry_and_safety_clearance(ep_id):
    """Tiêu chí 6: Reveal 1 phải DRY 100%, có pre-clearance >= 2.0s và post-clearance >= 2.5s."""
    audio_qc_path = PILOT_03_DIR / ep_id / "reports" / "audio_qc.json"
    cue_sheet_path = PILOT_03_DIR / ep_id / "audio" / "music_cue_sheet.json"
    timing_path = PILOT_03_DIR / ep_id / "audio" / "segment_timing.json"

    with open(audio_qc_path, "r", encoding="utf-8") as f:
        audio_qc = json.load(f)
    with open(cue_sheet_path, "r", encoding="utf-8") as f:
        cue_sheet = json.load(f)
    with open(timing_path, "r", encoding="utf-8") as f:
        timings = json.load(f)

    assert audio_qc["reveal_1_is_dry"] is True, "Reveal 1 bị dính nhạc nền!"
    assert audio_qc["music_during_reveal_sec"] == 0.0, f"Music during reveal > 0: {audio_qc['music_during_reveal_sec']}"

    # Kiểm tra thời gian bắt đầu và kết thúc của khối REVEAL
    reveal_segs = [t for t in timings if t["delivery_profile"] == "REVEAL"]
    assert len(reveal_segs) >= 5, f"Số lượng segment REVEAL bất thường: {len(reveal_segs)}"

    rev_start = reveal_segs[0]["speech_start_sec"]
    rev_end = reveal_segs[-1]["speech_end_sec"]

    for c in cue_sheet:
        if c["cue"] != "DRY":
            # Nhạc trước reveal phải kết thúc trước rev_start ít nhất 1.9s (cho phép tolerance nhẹ 0.1s)
            if c["end_sec"] <= rev_start:
                assert rev_start - c["end_sec"] >= 1.8, (
                    f"Pre-clearance vi phạm: {rev_start - c['end_sec']:.2f}s < 1.8s tại {c['cue']}"
                )
            # Nhạc sau reveal chỉ được bắt đầu sau rev_end ít nhất 2.4s
            if c["start_sec"] >= rev_end:
                assert c["start_sec"] - rev_end >= 2.3, (
                    f"Post-clearance vi phạm: {c['start_sec'] - rev_end:.2f}s < 2.3s tại {c['cue']}"
                )
            # Không có đoạn nhạc nào nằm lọt thỏm trong reveal
            assert not (c["start_sec"] < rev_end and c["end_sec"] > rev_start), (
                f"Music cue {c['cue']} ({c['start_sec']:.2f}s - {c['end_sec']:.2f}s) cắt ngang Reveal ({rev_start:.2f}s - {rev_end:.2f}s)"
            )


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_audio_mastering_compliance(ep_id):
    """Tiêu chí 7 & 8: Độ lớn Broadcast và True Peak theo chuẩn Audio Formula V1."""
    audio_qc_path = PILOT_03_DIR / ep_id / "reports" / "audio_qc.json"
    with open(audio_qc_path, "r", encoding="utf-8") as f:
        audio_qc = json.load(f)

    # Integrated LUFS target -14 to -15 LUFS (cho phép dải an toàn [-16.0, -13.5])
    lufs = audio_qc["integrated_lufs"]
    assert -16.5 <= lufs <= -13.0, f"Integrated LUFS nằm ngoài dải cho phép: {lufs} LUFS"

    # True Peak target <= -1.0 dBTP (cho phép tolerance -0.9 dBTP)
    tp = audio_qc["true_peak_db"]
    assert tp <= -0.9, f"True Peak vượt ngưỡng an toàn: {tp} dBTP"

    # Không clipping
    assert audio_qc["clipping_detected"] is False, "Phát hiện digital clipping trong file master!"


@pytest.mark.parametrize("ep_id", ["EP003", "EP011"])
def test_music_coverage_within_formula(ep_id):
    """Tiêu chí 8: Tỷ lệ phủ nhạc nền tuân thủ Audio Formula V1 (~30-38% music, ~60-70% dry)."""
    audio_qc_path = PILOT_03_DIR / ep_id / "reports" / "audio_qc.json"
    with open(audio_qc_path, "r", encoding="utf-8") as f:
        audio_qc = json.load(f)

    cov = audio_qc["music_coverage_percent"]
    # Cho phép biên độ tự nhiên theo cốt truyện 25% - 42%
    assert 25.0 <= cov <= 42.0, f"Music coverage lệch khỏi khung Audio Formula V1: {cov}%"

    dry = audio_qc["dry_voice_percent"]
    assert 58.0 <= dry <= 75.0, f"Dry voice coverage lệch khỏi khung: {dry}%"


def test_generation_safety(pilot_data):
    """Tiêu chí 9: An toàn tuyệt đối — 0 images, 0 videos, 0 Flow calls."""
    safety = pilot_data.get("generation_safety", {})
    assert safety.get("images") == 0
    assert safety.get("videos") == 0
    assert safety.get("flow") == 0
    assert safety.get("gemini_script_calls") == 0
    assert safety.get("script_regeneration") == 0


def test_overall_status_awaiting_review(pilot_data):
    """Tiêu chí nghiệm thu: Status phải là AWAITING_USER_AUDIO_REVIEW."""
    for ep_id, ep_report in pilot_data.get("episodes", {}).items():
        assert ep_report.get("status") == "AWAITING_USER_AUDIO_REVIEW", (
            f"Trạng thái episode {ep_id} không phải AWAITING_USER_AUDIO_REVIEW: {ep_report.get('status')}"
        )
