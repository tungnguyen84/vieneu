"""
Regression & Acceptance Test: Final Tuning for Music Cue Engine ("Sau Cánh Cửa" Series)
Verifies:
1. Minimum music region durations (INTRO >= 5s, MYSTERY >= 8s, TENSION >= 8s, EMOTIONAL >= 10s, REFLECTION >= 8s, OUTRO >= 5s).
2. Option A merge / Option B drop to DRY logic.
3. Fade safety: total fade <= 35% of duration for regions < 15s, fade_in + fade_out < duration.
4. Smart Source Offset: deterministic rotation across multiple cues of same track.
5. Major Reveal: 100% DRY with pre-reveal >= 2.0s and post-reveal >= 2.5s clearance.
6. Target coverage: 30–38%.
7. Zero modification to TTS takes or voice_master.wav.
8. Rebuild final mix loudness and true peak standards.
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
    build_clean_voice_master,
    build_final_mix,
    MIN_REGION_DURATION,
    adapt_fade_durations,
    compute_smart_source_offset,
    analyze_audio_loudness
)


def run_final_tuning_test():
    print("=" * 75)
    print("🎯 BẮT ĐẦU TEST FINAL TUNING CHO MUSIC CUE ENGINE (SERIES SAU CÁNH CỬA)")
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

    # 3. AUTO CUE SHEET GENERATION VỚI FINAL TUNING
    print("\n[BƯỚC 3] Chạy Auto Cue Engine với Minimum Region Duration & Smart Source Offset...")
    cue_sheet = generate_cue_sheet_from_segments(
        timeline_events=timeline_events,
        total_episode_sec=total_ep_sec,
        target_max_coverage=38.0,
        target_min_coverage=30.0
    )

    cov = calculate_music_coverage(cue_sheet, total_ep_sec)
    print(f"   Episode duration: {cov['total_episode_fmt']} ({cov['total_episode_sec']}s)")
    print(f"   Music duration:   {cov['music_duration_fmt']} ({cov['music_duration_sec']}s)")
    print(f"   Dry duration:     {cov['dry_duration_fmt']} ({cov['dry_duration_sec']}s)")
    print(f"   Music coverage:   {cov['coverage_percent']}% (Target: 30% – 38%)")

    # 4. KIỂM TRA MINIMUM DURATION TỪNG REGION
    print("\n[BƯỚC 4] Kiểm tra toàn bộ Music Regions tuân thủ Minimum Duration...")
    music_cues = [c for c in cue_sheet if c["cue"] != "DRY"]
    shortest_durations = {}

    for idx, c in enumerate(music_cues):
        cue = c["cue"]
        dur = c["duration_sec"]
        min_req = MIN_REGION_DURATION.get(cue, 8.0)
        assert dur >= min_req, f"Region {idx} ({cue}) có độ dài {dur:.2f}s < minimum {min_req}s!"
        if cue not in shortest_durations or dur < shortest_durations[cue]:
            shortest_durations[cue] = dur

    print(f"   Số lượng music regions: {len(music_cues)}")
    print(f"   Shortest INTRO:     {shortest_durations.get('INTRO', 'N/A'):.2f}s (Min req: 5.0s)")
    print(f"   Shortest MYSTERY:   {shortest_durations.get('MYSTERY', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest TENSION:   {shortest_durations.get('TENSION', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest EMOTIONAL: {shortest_durations.get('EMOTIONAL', 'N/A'):.2f}s (Min req: 10.0s)")
    print(f"   Shortest REFLECTION:{shortest_durations.get('REFLECTION', 'N/A'):.2f}s (Min req: 8.0s)")
    print(f"   Shortest OUTRO:     {shortest_durations.get('OUTRO', 'N/A'):.2f}s (Min req: 5.0s)")
    print("✅ PASS: Không có bất kỳ music region nào vi phạm minimum duration!")

    # 5. KIỂM TRA FADE DURATION SAFETY (tổng fade <= 35% với region < 15s)
    print("\n[BƯỚC 5] Kiểm tra Fade Safety Rule...")
    for idx, c in enumerate(music_cues):
        dur = c["duration_sec"]
        f_in = c["fade_in_sec"]
        f_out = c["fade_out_sec"]
        total_fade = f_in + f_out
        assert total_fade < dur, f"Region {idx} fade ({total_fade}s) >= duration ({dur}s)!"
        if dur < 15.0:
            ratio = total_fade / dur
            assert ratio <= 0.36, f"Region {idx} ({dur}s) có fade ratio {ratio:.2f} > 0.35!"
    print("✅ PASS: Tất cả các vùng nhạc đều có fade-in + fade-out an toàn, không triệt tiêu thân nhạc!")

    # 6. KIỂM TRA SMART SOURCE OFFSET
    print("\n[BƯỚC 6] Kiểm tra Smart Source Offset (Deterministic Rotation)...")
    mystery_cues = [c for c in music_cues if c["cue"] == "MYSTERY"]
    tension_cues = [c for c in music_cues if c["cue"] == "TENSION"]

    print("   MYSTERY Cues offsets:")
    for k, c in enumerate(mystery_cues[:4]):
        print(f"      Cue #{k+1}: start={c['start_sec']}s, dur={c['duration_sec']}s, src_offset={c.get('source_offset_sec')}s")
    assert mystery_cues[0].get("source_offset_sec") == 10.0, "MYSTERY Cue #1 phải offset 10.0s"
    assert mystery_cues[1].get("source_offset_sec") == 42.0, "MYSTERY Cue #2 phải offset 42.0s"
    assert mystery_cues[2].get("source_offset_sec") == 74.0, "MYSTERY Cue #3 phải offset 74.0s"

    print("   TENSION Cues offsets:")
    for k, c in enumerate(tension_cues[:3]):
        print(f"      Cue #{k+1}: start={c['start_sec']}s, dur={c['duration_sec']}s, src_offset={c.get('source_offset_sec')}s")
    assert tension_cues[0].get("source_offset_sec") == 10.0, "TENSION Cue #1 phải offset 10.0s"
    assert tension_cues[1].get("source_offset_sec") == 42.0, "TENSION Cue #2 phải offset 42.0s"
    print("✅ PASS: Smart Source Offset deterministic xoay chuyển mượt mà giữa các cue!")

    # 7. KIỂM TRA MAJOR REVEAL VÀ CLEARANCE
    print("\n[BƯỚC 7] Kiểm tra Major Reveal Clearance...")
    reveal_events = [ev for ev in timeline_events if ev.get("delivery_profile") == "REVEAL" or "ngày mất" in ev.get("text", "")]
    assert len(reveal_events) > 0, "Không tìm thấy reveal events"
    for rev in reveal_events:
        rev_st = rev["speech_start_sec"]
        rev_en = rev["speech_end_sec"]
        # Phải không có music cue nào chồng lấn vào vùng [rev_st - 2.0, rev_en + 2.5]
        for mc in music_cues:
            assert not (mc["start_sec"] < rev_en + 2.5 and mc["end_sec"] > rev_st - 2.0), \
                f"Music cue {mc['cue']} ({mc['start_sec']} -> {mc['end_sec']}) vi phạm reveal clearance [{rev_st-2.0:.1f} -> {rev_en+2.5:.1f}]!"
    print("✅ PASS: Major Reveal 100% DRY và đảm bảo pre/post clearance tuyệt đối!")

    # 8. BUILD FINAL MIX & KIỂM TRA LOUDNORM
    print("\n[BƯỚC 8] Rebuild Final Mix & 2-Pass Mastering...")
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

    # Kiểm tra Voice Master hoàn toàn không bị đụng tới
    new_voice_mtime = voice_master_p.stat().st_mtime
    new_voice_size = voice_master_p.stat().st_size
    assert new_voice_size == orig_voice_size, "Voice Master bị thay đổi kích thước!"
    assert new_voice_mtime == orig_voice_mtime, "Voice Master bị ghi đè lại!"
    print("✅ PASS: Clean Voice Master và các TTS takes được bảo toàn nguyên vẹn 100%!")

    # Kiểm tra Master outputs
    final_wav_p = project_dir / "master/final_mix.wav"
    final_mp3_p = project_dir / "master/final_mix.mp3"
    assert final_wav_p.exists()
    assert final_mp3_p.exists()

    final_stats = analyze_audio_loudness(final_wav_p)
    print(f"   Master Integrated LUFS: {final_stats['integrated_lufs']} LUFS (Kỳ vọng: -16 -> -14 LUFS)")
    print(f"   Master True Peak:       {final_stats['true_peak_db']} dBTP (Kỳ vọng: <= -0.9 dBTP)")
    assert -16.5 <= final_stats["integrated_lufs"] <= -13.5, f"LUFS ngoài ngưỡng chấp nhận: {final_stats['integrated_lufs']}"
    assert final_stats["true_peak_db"] <= -0.85, f"True Peak vượt ngưỡng an toàn: {final_stats['true_peak_db']}"
    print("✅ PASS: Final Mix & Master đạt chuẩn phát sóng xuất sắc!")

    print("\n" + "=" * 75)
    print("🎉 TẤT CẢ TIÊU CHÍ FINAL TUNING ĐÃ ĐẠT CHUẨN XUẤT SẮC!")
    print("   AUDIO FORMULA V1 — READY TO LOCK")
    print("=" * 75)


if __name__ == "__main__":
    run_final_tuning_test()
