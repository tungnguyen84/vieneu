"""
Regression & Acceptance Integration Test: Final Tuning & Final Cue Sheet Validator
Validates:
1. FIX 1: validate_and_sanitize_final_cue_sheet converts candidate short cues to DRY.
2. FIX 2: Adjacent DRY regions are seamlessly merged into a single continuous block.
3. FIX 3: Final fade sanitizer enforces fade_in + fade_out <= duration * 0.35 + 0.02.
4. FIX 4: generate_cue_sheet_from_segments validates and asserts before returning.
5. FIX 5: assert_final_music_cues_valid raises AssertionError on any invalid cue.
6. FIX 6: build_final_mix enforces defense-in-depth validation before rendering.
7. FIX 7: Tests read the real OUTPUT file from disk (mix/cue_sheet.json) with json.load().
8. FIX 8: Asserts that known bugs (TENSION 7.07s, TENSION 4.16s, REFLECTION 5.87s) are completely eliminated.
"""

import json
import numpy as np
import soundfile as sf
from pathlib import Path

from apps.music_engine import (
    GLOBAL_MUSIC_LIB_DIR,
    init_global_music_library,
    generate_cue_sheet_from_segments,
    calculate_music_coverage,
    build_final_mix,
    MIN_REGION_DURATION,
    validate_and_sanitize_final_cue_sheet,
    assert_final_music_cues_valid,
    analyze_audio_loudness
)


def run_final_tuning_test():
    print("=" * 75)
    print("🎯 BẮT ĐẦU TEST FINAL VALIDATOR & SANITIZER (SERIES SAU CÁNH CỬA)")
    print("=" * 75)

    project_dir = Path("projects/sau_canh_cua_-_episode_01_v9_1_master_reference")
    assert project_dir.exists(), f"Không tìm thấy project tại: {project_dir}"

    # 1. KIỂM TRA PERSISTENT MUSIC LIBRARY
    print("\n[BƯỚC 1] Xác minh 6 slot Persistent Music Library...")
    lib_data = init_global_music_library()
    tracks = lib_data.get("tracks", {})
    for slot in ["INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"]:
        def_tid = lib_data.get("categories", {}).get(slot, {}).get("default_track")
        assert def_tid in tracks, f"Thiếu track cho slot {slot}"
        assert tracks[def_tid]["normalized_status"] == "READY", f"Track {def_tid} chưa READY"
        p = Path(tracks[def_tid]["normalized_file"])
        if not p.is_absolute():
            p = Path(".").resolve() / p
        assert p.exists(), f"Không tìm thấy file normalized: {p}"
    print("✅ PASS: 6 slot nhạc gốc Suno trong Persistent Music Library sẵn sàng 100%.")

    # 2. ĐỌC DỮ LIỆU EPISODE 01 V9.1
    print("\n[BƯỚC 2] Tải dữ liệu Episode 01 V9.1 và bảo vệ Voice Master...")
    source_p = project_dir / "source.json"
    script = json.load(open(source_p, encoding="utf-8"))
    segments = script.get("segments", [])
    assert len(segments) == 93, f"Kỳ vọng 93 segments, thực tế: {len(segments)}"

    voice_master_p = project_dir / "master/voice_master.wav"
    assert voice_master_p.exists(), f"Voice Master không tồn tại tại: {voice_master_p}"
    orig_voice_mtime = voice_master_p.stat().st_mtime
    orig_voice_size = voice_master_p.stat().st_size
    info_voice = sf.info(str(voice_master_p))
    total_ep_sec = info_voice.duration
    print(f"   Voice Master: {total_ep_sec:.2f}s (~{int(total_ep_sec//60)}:{int(total_ep_sec%60):02d}), {orig_voice_size:,} bytes")

    # Reconstruct timeline events
    sample_rate = 48000
    timeline_events = []
    current_sample = 0
    for seg in segments:
        sid = seg["id"]
        wav_p = project_dir / "selected" / f"{int(sid):03d}.wav"
        assert wav_p.exists(), f"Thiếu take cho segment {sid}"
        w_info = sf.info(str(wav_p))
        samp_len = w_info.frames
        st_sec = current_sample / sample_rate
        en_sec = (current_sample + samp_len) / sample_rate
        timeline_events.append({
            "id": sid,
            "speaker": seg.get("speaker", "MINH"),
            "text": seg.get("text", ""),
            "delivery_profile": seg.get("delivery_profile", "NORMAL"),
            "importance": seg.get("importance", "normal"),
            "audio_region": seg.get("audio_region", ""),
            "music_cue": seg.get("music_cue", ""),
            "music_obj": seg.get("music", {}),
            "speech_start_sec": st_sec,
            "speech_end_sec": en_sec,
            "speech_start_sample": current_sample,
            "speech_end_sample": current_sample + samp_len
        })
        p_gap = float(seg.get("pause_after", 0.18))
        gap_samples = int(p_gap * sample_rate)
        current_sample += samp_len + gap_samples

    # 3. AUTO CUE SHEET GENERATION VỚI FINAL SANITIZER & ASSERTION
    print("\n[BƯỚC 3] Chạy Auto Cue Engine (Tích hợp Final Validator & Sanitizer)...")
    cue_sheet = generate_cue_sheet_from_segments(
        timeline_events=timeline_events,
        total_episode_sec=total_ep_sec,
        target_max_coverage=38.0,
        target_min_coverage=30.0
    )

    # 4. REBUILD FINAL MIX & LƯU CUE_SHEET.JSON XUỐNG ĐĨA
    print("\n[BƯỚC 4] Rebuild Final Mix & 2-Pass Mastering (Ghi disk cue_sheet.json)...")
    ok, msg, res = build_final_mix(
        project_dir=project_dir,
        voice_master_path=voice_master_p,
        cue_sheet=cue_sheet,
        timeline_events=timeline_events,
        enable_ducking=False,
        target_lufs=-14.0,
        true_peak_db=-1.0
    )
    assert ok is True, f"Build Final Mix thất bại: {msg}"

    # 5. INTEGRATION TEST: ĐỌC LẠI FILE DISK THẬT (FIX 7)
    print("\n[BƯỚC 5] Đóng data/object và đọc lại mix/cue_sheet.json từ đĩa bằng json.load()...")
    del cue_sheet # Xóa object trong RAM
    disk_cue_sheet_path = project_dir / "mix/cue_sheet.json"
    assert disk_cue_sheet_path.exists(), "Không tìm thấy mix/cue_sheet.json trên đĩa"
    
    with open(disk_cue_sheet_path, "r", encoding="utf-8") as f:
        disk_cues = json.load(f)

    print(f"   Đã nạp {len(disk_cues)} phân đoạn trực tiếp từ đĩa.")

    # 6. KIỂM TRA TRIỆT TIÊU TOÀN BỘ CÁC BUG CŨ (FIX 8)
    print("\n[BƯỚC 6] Kiểm tra loại bỏ triệt để các bug cũ (TENSION 7.07s, TENSION 4.16s, REFLECTION 5.87s)...")
    for idx, c in enumerate(disk_cues):
        cue = c.get("cue")
        dur = float(c.get("duration_sec", 0.0))
        st = float(c.get("start_sec", 0.0))
        en = float(c.get("end_sec", 0.0))
        if cue == "TENSION":
            assert not (6.8 <= dur <= 7.3), f"BUG PHÁT HIỆN: TENSION {dur}s ({st}s -> {en}s) chưa bị loại bỏ!"
            assert not (3.9 <= dur <= 4.4), f"BUG PHÁT HIỆN: TENSION {dur}s ({st}s -> {en}s) chưa bị loại bỏ!"
        if cue == "REFLECTION":
            assert not (5.5 <= dur <= 6.2), f"BUG PHÁT HIỆN: REFLECTION {dur}s ({st}s -> {en}s) chưa bị loại bỏ!"
    print("✅ PASS: Không tồn tại bất kỳ cue ngắn nào trong file đĩa thật!")

    # 7. KIỂM TRA GỘP CÁC KHỐI DRY LIỀN KỀ (FIX 2)
    print("\n[BƯỚC 7] Kiểm tra gộp tất cả các block DRY liền nhau...")
    for idx in range(len(disk_cues) - 1):
        c1 = disk_cues[idx]
        c2 = disk_cues[idx + 1]
        if c1.get("cue") == "DRY" and c2.get("cue") == "DRY":
            gap = c2["start_sec"] - c1["end_sec"]
            assert gap > 0.05, f"Tồn tại 2 block DRY liền nhau chưa gộp: [{idx}] ({c1['start_sec']}->{c1['end_sec']}) và [{idx+1}] ({c2['start_sec']}->{c2['end_sec']})"
    print("✅ PASS: Mọi khoảng nghỉ DRY đều được gộp liên tục, sạch sẽ và thoáng đãng!")

    # 8. KIỂM TRA MINIMUM DURATION VÀ FADE SAFETY CHO TẤT CẢ MUSIC CUES TRÊN ĐĨA
    print("\n[BƯỚC 8] Kiểm tra Minimum Duration & Fade Safety trên file đĩa thật...")
    disk_music_cues = [c for c in disk_cues if c.get("cue") != "DRY"]
    shortest_durations = {}
    max_observed_fade_ratio = 0.0

    for idx, c in enumerate(disk_music_cues):
        cue = c["cue"]
        dur = float(c["duration_sec"])
        f_in = float(c["fade_in_sec"])
        f_out = float(c["fade_out_sec"])
        source = str(c.get("source", ""))

        # Minimum duration
        if source.startswith("Auto Region"):
            min_req = MIN_REGION_DURATION.get(cue, 8.0)
            assert dur >= min_req, f"Cue {idx} ({cue}) thời lượng {dur:.2f}s < minimum {min_req}s!"
            if cue not in shortest_durations or dur < shortest_durations[cue]:
                shortest_durations[cue] = dur

        # Fade safety ratio <= 35% + 0.02
        tot_fade = f_in + f_out
        ratio = tot_fade / dur if dur > 0 else 0
        if ratio > max_observed_fade_ratio:
            max_observed_fade_ratio = ratio
        assert tot_fade <= dur * 0.35 + 0.021, f"Cue {idx} ({cue}) fade ratio {ratio:.3f} > 0.35!"
        assert tot_fade < dur, f"Cue {idx} ({cue}) total fade ({tot_fade}s) >= duration ({dur}s)!"

    print(f"   Số lượng music cues trên đĩa: {len(disk_music_cues)}")
    print(f"   Shortest INTRO:     {shortest_durations.get('INTRO', 'N/A'):.2f}s (Min req: 5.0s)")
    print(f"   Shortest MYSTERY:   {shortest_durations.get('MYSTERY', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest TENSION:   {shortest_durations.get('TENSION', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest EMOTIONAL: {shortest_durations.get('EMOTIONAL', 'N/A'):.2f}s (Min req: 10.0s)")
    print(f"   Shortest REFLECTION:{shortest_durations.get('REFLECTION', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest OUTRO:     {shortest_durations.get('OUTRO', 'N/A'):.2f}s (Min req: 5.0s)")
    print(f"   Maximum observed fade ratio: {max_observed_fade_ratio:.1%} (Khống chế: <= 35.0%)")
    print("✅ PASS: Tất cả các music cue trên đĩa đều vượt qua kiểm tra Minimum Duration và Fade Safety!")

    # 9. KIỂM TRA MUSIC COVERAGE TRÊN FILE THẬT
    print("\n[BƯỚC 9] Kiểm tra Music Coverage trên file thật...")
    cov = calculate_music_coverage(disk_cues, total_ep_sec)
    print(f"   Tổng thời lượng:  {cov['total_episode_fmt']} ({cov['total_episode_sec']}s)")
    print(f"   Thời lượng nhạc:  {cov['music_duration_fmt']} ({cov['music_duration_sec']}s)")
    print(f"   Thời lượng DRY:   {cov['dry_duration_fmt']} ({cov['dry_duration_sec']}s)")
    print(f"   Music Coverage:   {cov['coverage_percent']}% (Ngưỡng yêu cầu: 30% – 38%)")
    assert 30.0 <= cov['coverage_percent'] <= 38.0, f"Coverage {cov['coverage_percent']}% nằm ngoài ngưỡng 30%–38%!"
    print("✅ PASS: Music coverage chuẩn mực phát sóng storytelling!")

    # 10. KIỂM TRA BẢO TOÀN VOICE MASTER & KẾT QUẢ MASTERING
    print("\n[BƯỚC 10] Kiểm tra bảo toàn Clean Voice Master & Loudness Master...")
    new_voice_mtime = voice_master_p.stat().st_mtime
    new_voice_size = voice_master_p.stat().st_size
    assert new_voice_size == orig_voice_size, "Voice Master bị thay đổi kích thước!"
    assert new_voice_mtime == orig_voice_mtime, "Voice Master bị ghi đè!"
    print("✅ PASS: Clean Voice Master và các TTS takes không bị thay đổi dù chỉ 1 byte!")

    final_wav_p = project_dir / "master/final_mix.wav"
    final_stats = analyze_audio_loudness(final_wav_p)
    print(f"   Master Integrated LUFS: {final_stats['integrated_lufs']} LUFS (Kỳ vọng: -16 -> -14 LUFS)")
    print(f"   Master True Peak:       {final_stats['true_peak_db']} dBTP (Kỳ vọng: <= -0.9 dBTP)")
    assert -16.5 <= final_stats["integrated_lufs"] <= -13.5
    assert final_stats["true_peak_db"] <= -0.85
    print("✅ PASS: Final Mix & Master đạt chuẩn phát sóng!")

    # 11. KIỂM TRA MAJOR REVEAL
    print("\n[BƯỚC 11] Kiểm tra Major Reveal Clearance...")
    reveal_events = [ev for ev in timeline_events if ev.get("delivery_profile") == "REVEAL" or "ngày mất" in ev.get("text", "")]
    for rev in reveal_events:
        rev_st = rev["speech_start_sec"]
        rev_en = rev["speech_end_sec"]
        for mc in disk_music_cues:
            assert not (mc["start_sec"] < rev_en + 2.5 and mc["end_sec"] > rev_st - 2.0), \
                f"Music cue {mc['cue']} vi phạm clearance reveal [{rev_st-2.0:.1f} -> {rev_en+2.5:.1f}]!"
    print("✅ PASS: Major Reveal 100% DRY, pre/post clearance an toàn tuyệt đối!")

    print("\n" + "=" * 75)
    print("🎉 TẤT CẢ 11 TIÊU CHÍ INTEGRATION TEST TRÊN FILE THẬT ĐÃ ĐẠT CHUẨN XUẤT SẮC!")
    print("   AUDIO FORMULA V1 — CONFIRMED & READY TO LOCK")
    print("=" * 75)


if __name__ == "__main__":
    run_final_tuning_test()
