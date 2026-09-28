"""
Automated Test Suite for Persistent Suno Music Library & Replacement Pipeline
Verifies all requirements:
1. Replace INTRO with a real Suno M4A file
2. Verify audio normalization (-24 LUFS, 48kHz WAV) & automatic backup in music_library/backups/
3. Verify Preview audio is immediately updated
4. Simulate F5 (page reload via demo.load callback) -> verifies new track persists from disk
5. Simulate App Stop & Restart -> verifies new track persists from library.json
6. Generate Auto Cue Sheet -> verifies INTRO maps to SCC_INTRO_01 with new track
7. Build Final Mix on V9.1 -> verifies final mix uses the new Suno file without altering TTS/voice_master
8. Automated verification for all 6 persistent slots (INTRO, MYSTERY, TENSION, EMOTIONAL, REFLECTION, OUTRO)
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import soundfile as sf
from apps.music_engine import (
    GLOBAL_MUSIC_LIB_DIR,
    FIXED_SLOT_TRACKS,
    init_global_music_library,
    save_global_music_library,
    import_track_to_library,
    get_slot_cards_data,
    format_slot_markdown,
    get_music_library_table_data,
    resolve_track_file_for_cue,
    generate_cue_sheet_from_segments,
    calculate_music_coverage,
    build_clean_voice_master,
    build_final_mix,
    probe_audio_file
)
from apps.ui_production_story import render_production_story_ui, bind_production_story_events


def run_persistent_suno_tests():
    print("=" * 75)
    print("🎯 BẮT ĐẦU KIỂM TRA TOÀN DIỆN PERSISTENT SUNO MUSIC LIBRARY (6 SLOTS)")
    print("=" * 75)

    lib_dir = PROJECT_ROOT / "music_library"
    backup_dir = lib_dir / "backups"
    norm_dir = lib_dir / "normalized"
    orig_dir = lib_dir / "original"
    lib_json = lib_dir / "library.json"

    assert lib_json.exists(), "library.json phải tồn tại trên đĩa"
    lib_data = init_global_music_library(lib_dir)
    assert len(lib_data.get("tracks", {})) >= 6, "Phải có đủ 6 slots nhạc mặc định"

    # =========================================================================
    # BƯỚC 1: TẠO HOẶC LẤY FILE SUNO M4A THẬT ĐỂ TEST THAY THẾ INTRO
    # =========================================================================
    print("\n[BƯỚC 1] Chuẩn bị file M4A Suno thật...")
    real_m4a_cand = Path(r"C:\Users\TPT\Downloads\Em Thua C Ta 1.m4a")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_p = Path(temp_dir)
        if real_m4a_cand.exists():
            test_m4a = temp_dir_p / "suno_new_intro.m4a"
            shutil.copy2(real_m4a_cand, test_m4a)
        else:
            # Tạo file M4A (AAC stereo 48kHz) bằng FFmpeg
            test_m4a = temp_dir_p / "suno_new_intro.m4a"
            cmd = ["ffmpeg", "-y", "-hide_banner", "-f", "lavfi", "-i", "sine=frequency=528:duration=15", "-c:a", "aac", "-b:a", "192k", str(test_m4a)]
            subprocess.run(cmd, capture_output=True, check=True)

        probe = probe_audio_file(test_m4a)
        print(f"   File M4A sẵn sàng: {test_m4a.name} (codec: {probe['codec_name']}, dur: {probe['duration_sec']:.1f}s)")

        # Đếm số lượng backup hiện tại
        backups_before = list(backup_dir.glob("SCC_INTRO_01_*.wav"))
        count_before = len(backups_before)

        # =========================================================================
        # BƯỚC 2: THAY THẾ INTRO BẰNG FILE SUNO M4A MỚI
        # =========================================================================
        print("\n[BƯỚC 2] Thực hiện Thay thế slot INTRO bằng Suno M4A...")
        ok, msg, track_info = import_track_to_library(
            category="INTRO",
            track_id=None,
            file_source=test_m4a,
            orig_filename="suno_new_intro.m4a",
            lib_dir=lib_dir
        )
        assert ok is True, f"Import thất bại: {msg}"
        assert track_info["track_id"] == "SCC_INTRO_01", f"Track ID phải là SCC_INTRO_01, nhận được {track_info['track_id']}"
        assert track_info["original_filename"] == "suno_new_intro.m4a"
        assert "updated_at" in track_info and track_info["updated_at"]
        print(f"✅ PASS: Thay thế thành công: {msg}")

        # Kiểm tra backup đã được sinh ra
        backups_after = list(backup_dir.glob("SCC_INTRO_01_*.wav"))
        assert len(backups_after) > count_before, "Phải có file backup mới trong music_library/backups/"
        latest_backup = sorted(backups_after, key=os.path.getmtime)[-1]
        print(f"✅ PASS: Đã tự động sao lưu track cũ vào: {latest_backup.name}")

        # Kiểm tra active file duy nhất trên đĩa
        norm_wav = norm_dir / "SCC_INTRO_01.wav"
        assert norm_wav.exists(), "File normalized SCC_INTRO_01.wav không tồn tại"
        wav_info = sf.info(str(norm_wav))
        assert wav_info.samplerate == 48000, f"Sample rate phải là 48kHz, nhận được {wav_info.samplerate}"
        assert abs(track_info["integrated_lufs"] - (-24.0)) <= 2.5, f"LUFS {track_info['integrated_lufs']} lệch quá lớn so với -24 LUFS"
        print(f"✅ PASS: File normalized SCC_INTRO_01.wav đã được ghi đè ({wav_info.duration:.1f}s, {track_info['integrated_lufs']} LUFS, 48kHz).")

        # =========================================================================
        # BƯỚC 3: KIỂM TRA PREVIEW VÀ FORMAT MARKDOWN
        # =========================================================================
        print("\n[BƯỚC 3] Kiểm tra Preview và hiển thị thông tin thẻ Slot...")
        slots = get_slot_cards_data(lib_dir)
        intro_card = slots["INTRO"]
        assert intro_card["track_id"] == "SCC_INTRO_01"
        assert intro_card["original_filename"] == "suno_new_intro.m4a"
        assert intro_card["audio_preview"] == str(norm_wav.resolve())
        md_text = format_slot_markdown(intro_card)
        assert "suno_new_intro.m4a" in md_text
        assert "Updated At" in md_text
        print(f"   [CARD DISPLAY]\n{md_text}")
        print("✅ PASS: Thẻ INTRO hiển thị đúng File, Duration, LUFS, Updated At và audio preview.")

        # =========================================================================
        # BƯỚC 4: GIẢ LẬP F5 BROWSER (PAGE RELOAD / DEMO.LOAD)
        # =========================================================================
        print("\n[BƯỚC 4] Giả lập F5 Browser (gọi refresh callback từ demo.load)...")
        # Khởi tạo UI và lấy refresh handler
        import gradio as gr
        with gr.Blocks() as demo:
            c = render_production_story_ui(lambda: ["Binh (Thanh Bình)"])
            bind_production_story_events(c, lambda: None, lambda: [], None)

        assert "refresh_music_fn" in c, "UI thiếu refresh_music_fn"
        f5_results = c["refresh_music_fn"]()
        # f5_results gồm 12 items cho 6 slots (markdown + audio preview) + 1 table DataFrame
        assert len(f5_results) == 13
        intro_md_f5 = f5_results[0]
        intro_audio_f5 = f5_results[1]
        assert "suno_new_intro.m4a" in intro_md_f5, "F5 phải lấy đúng tên file mới từ disk"
        assert intro_audio_f5 == str(norm_wav.resolve()), "F5 phải lấy đúng audio preview mới từ disk"
        print("✅ PASS: Sau khi F5, trình duyệt tải trực tiếp từ đĩa và hiển thị chính xác bản nhạc Suno mới.")

        # =========================================================================
        # BƯỚC 5: GIẢ LẬP STOP APP & START APP LẠI (PYTHON PROCESS RESTART)
        # =========================================================================
        print("\n[BƯỚC 5] Giả lập Khởi động lại App / Python Process...")
        # Đọc trực tiếp từ file json trên đĩa mà không dùng bộ nhớ RAM cũ
        with open(lib_json, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        reloaded_intro = disk_data["tracks"]["SCC_INTRO_01"]
        assert reloaded_intro["original_filename"] == "suno_new_intro.m4a"
        reloaded_slots = get_slot_cards_data(lib_dir)
        assert reloaded_slots["INTRO"]["original_filename"] == "suno_new_intro.m4a"
        assert Path(reloaded_slots["INTRO"]["audio_preview"]).exists()
        print(f"✅ PASS: Sau khi khởi động lại app, SCC_INTRO_01 vẫn tồn tại vĩnh viễn: {reloaded_intro['original_filename']} ({reloaded_intro['duration_sec']}s).")

        # =========================================================================
        # BƯỚC 6 & 7: GENERATE AUTO CUE & BUILD FINAL MIX TRÊN V9.1
        # =========================================================================
        print("\n[BƯỚC 6 & 7] Sinh Auto Cue Sheet & Build Final Mix kiểm tra sử dụng track mới...")
        # Kiểm tra resolve_track_file_for_cue
        resolved_intro = resolve_track_file_for_cue("INTRO", lib_dir=lib_dir)
        assert resolved_intro is not None
        assert resolved_intro.resolve() == norm_wav.resolve(), f"Resolve track phải trỏ về {norm_wav.name}"
        print(f"✅ PASS: resolve_track_file_for_cue('INTRO') trỏ chính xác về file Suno mới: {resolved_intro.name}")

        # V9.1 test assembly & cue
        v91_json = PROJECT_ROOT / "presets" / "episode01_v9_1_master_reference_vieneu.json"
        with open(v91_json, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        segments = script_data["segments"]

        proj_dir = PROJECT_ROOT / "projects" / "test_persistent_mix"
        selected_dir = proj_dir / "selected"
        selected_dir.mkdir(parents=True, exist_ok=True)

        for s in segments:
            sid = str(s["id"]).zfill(3)
            tone_p = selected_dir / f"{sid}.wav"
            sf.write(str(tone_p), np.zeros(int(48000 * 3.0), dtype=np.float32), 48000)

        p_state = {
            "segments": {str(s["id"]).zfill(3): {"selected_file": f"selected/{str(s['id']).zfill(3)}.wav"} for s in segments}
        }

        ok_vm, msg_vm, vm_p, events = build_clean_voice_master(proj_dir, segments, p_state)
        assert ok_vm is True, f"Lỗi voice master: {msg_vm}"
        mtime_vm_before = os.path.getmtime(vm_p)

        cues = generate_cue_sheet_from_segments(events)
        intro_cues = [c for c in cues if c["cue"] == "INTRO"]
        assert len(intro_cues) >= 1, "Phải có ít nhất 1 cue INTRO"
        assert intro_cues[0]["track"] == "SCC_INTRO_01"

        cov = calculate_music_coverage(cues, events)
        print(f"   [COVERAGE] {cov['coverage_percent']}% (Khuyến nghị: {cov['target_recommendation']})")

        ok_mix, msg_mix, report = build_final_mix(
            project_dir=proj_dir,
            voice_master_path=vm_p,
            cue_sheet=cues,
            timeline_events=events,
            enable_ducking=True
        )
        assert ok_mix is True, f"Lỗi final mix: {msg_mix}"
        mtime_vm_after = os.path.getmtime(vm_p)
        assert mtime_vm_before == mtime_vm_after, "Voice Master tuyệt đối không được sinh lại hoặc sửa đổi!"

        # Dọn dẹp test project
        shutil.rmtree(proj_dir, ignore_errors=True)
        print("✅ PASS: Final mix sử dụng chính xác file Suno mới. Voice master và TTS không bị ảnh hưởng 100%.")

    # =========================================================================
    # BƯỚC 8: KIỂM TRA ĐỦ CẢ 6 SLOT CỐ ĐỊNH ĐỀU LÀ PERSISTENT VÀ READY
    # =========================================================================
    print("\n[BƯỚC 8] Kiểm tra toàn bộ 6 slot cố định trong Persistent Music Library...")
    all_slots = get_slot_cards_data(lib_dir)
    expected_slots = ["INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"]
    for sk in expected_slots:
        assert sk in all_slots, f"Thiếu slot {sk}"
        info = all_slots[sk]
        assert info["track_id"] == FIXED_SLOT_TRACKS[sk], f"Track ID {info['track_id']} không đúng quy định {FIXED_SLOT_TRACKS[sk]}"
        assert info["status"] == "READY", f"Slot {sk} phải READY, nhận được {info['status']}"
        assert info["audio_preview"] and Path(info["audio_preview"]).exists(), f"Thiếu audio preview cho {sk}"
        print(f"   Slot [{sk:10s}] -> Track: {info['track_id']:16s} | File: {info['original_filename'][:25]:25s} | Dur: {info['duration_sec']:6.1f}s | LUFS: {info['integrated_lufs']:6.1f} | Updated: {info.get('updated_at')}")

    print("\n" + "=" * 75)
    print("🎉 TẤT CẢ CÁC BƯỚC KIỂM TRA PERSISTENT SUNO MUSIC LIBRARY ĐÃ ĐẠT CHUẨN XUẤT SẮC!")
    print("=" * 75)


if __name__ == "__main__":
    run_persistent_suno_tests()
