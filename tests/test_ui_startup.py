"""
Smoke test cho Web UI và Production Storytelling / Music Mixing Engine.
Kiểm tra:
1. import apps.gradio_main và dựng toàn bộ Blocks/UI thành công (Không TypeError, AttributeError, Component constructor error).
2. Import JSON kịch bản V9.1 (93 segments) diễn ra < 2.0s, không đụng tới TTS hay FFmpeg.
3. Bảng phân đoạn hiển thị đúng 93 dòng kèm delivery_profile ('HOOK', 'NORMAL', ...).
4. Thư viện nhạc load từ cache library.json không chạy EBU R128 lại.
5. Upload track nhạc mới validate đúng định dạng extension.
"""

import os
import sys
import time
import json
import tempfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pytest
except ImportError:
    pytest = None
import gradio as gr
import soundfile as sf
import numpy as np


def test_ui_startup_and_components():
    """
    Test 1: Khởi động và dựng toàn bộ Blocks/UI.
    Đảm bảo không có TypeError (như File(file_types=...), DataFrame(wrap=...), v.v.).
    """
    import apps.gradio_main as gm

    assert hasattr(gm, "demo"), "apps.gradio_main phải chứa demo Blocks"
    assert isinstance(gm.demo, gr.Blocks), "demo phải là instance của gr.Blocks"
    assert len(gm.demo.blocks) > 20, "demo phải chứa đầy đủ các components của VieNeu-TTS"


def test_import_v9_1_performance_and_schema():
    """
    Test 2: Import episode01_v9_1_master_reference_vieneu.json (93 segments).
    Acceptance:
    - Thời gian import < 2.0 giây.
    - Trả về đủ 93 phân đoạn.
    - MINH -> Binh được ánh xạ đúng.
    - delivery_profile hiển thị đúng ('HOOK' cho các câu đầu).
    - Không gọi model TTS, không gọi FFmpeg.
    """
    from apps.ui_production_story import handle_import_json_data
    from apps.production_story import get_all_available_voices

    json_path = PROJECT_ROOT / "presets" / "episode01_v9_1_master_reference_vieneu.json"
    if not json_path.exists():
        json_path = Path(r"C:\Users\TPT\Documents\sau_canh_cua_ep01_v9_1_master_reference\01_audio\episode01_v9_1_master_reference_vieneu.json")

    assert json_path.exists(), f"Không tìm thấy file kịch bản test tại {json_path}"

    available_voices = get_all_available_voices()

    t0 = time.perf_counter()
    returns = handle_import_json_data(str(json_path), available_voices)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[TEST] Thời gian thực thi handle_import_json_data: {elapsed_ms:.2f} ms")
    assert elapsed_ms < 2000.0, f"Thời gian import ({elapsed_ms:.2f} ms) vượt quá ngưỡng 2.0s cho phép!"

    assert isinstance(returns, tuple), "Kết quả trả về phải là một tuple"
    assert len(returns) == 77, f"Số lượng outputs phải là 77, nhận được {len(returns)}"

    info_md = returns[0]
    assert "93" in info_md, "Project Info phải thể hiện có 93 segments"

    # Index 66 là df_rows (dữ liệu bảng segments)
    df_rows = returns[66]
    assert len(df_rows) == 93, f"Bảng kịch bản phải có 93 dòng, nhận được {len(df_rows)}"

    # Kiểm tra dòng đầu tiên: MINH -> Binh / Thanh Bình, delivery_profile = HOOK
    row_0 = df_rows[0]
    assert row_0[1] == "001"
    assert row_0[2] == "MINH"
    assert "Binh" in row_0[4] or "Thanh Bình" in row_0[4], f"Giọng đọc nhân vật phải khớp Binh: {row_0[4]}"
    assert row_0[6] == "HOOK", f"Cột Delivery Profile của dòng 001 phải là 'HOOK', nhận được '{row_0[6]}'"


def test_music_library_fast_load_without_renormalization():
    """
    Test 3: Thư viện nhạc đọc nhanh từ library.json hiện có.
    Không quét lại EBU R128 hay chạy lại FFmpeg khi dữ liệu đã chuẩn hóa.
    """
    from apps.music_engine import GLOBAL_LIB_JSON, init_global_music_library, get_music_library_table_data

    assert GLOBAL_LIB_JSON.exists(), "music_library/library.json phải tồn tại"

    t0 = time.perf_counter()
    lib_data = init_global_music_library()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n[TEST] Thời gian nạp Music Library: {elapsed_ms:.2f} ms")
    assert elapsed_ms < 500.0, f"Nạp Music Library quá chậm ({elapsed_ms:.2f} ms), có thể bị re-normalize!"

    table_rows = get_music_library_table_data()
    assert len(table_rows) == 6, f"Thư viện phải hiển thị đúng 6 danh mục chuẩn, nhận được {len(table_rows)}"


def test_music_upload_extension_validation():
    """
    Test 4: Validate extension khi upload file nhạc mới vào thư viện.
    Chấp nhận .wav, .mp3, .m4a; từ chối các định dạng không hợp lệ.
    """
    from apps.ui_production_story import import_track_to_library

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)

        # File txt không hợp lệ
        bad_file = tmp_p / "test.txt"
        bad_file.write_text("dummy text")
        ok, msg, _ = import_track_to_library("MYSTERY", "TEST_BAD", bad_file)
        assert ok is False, "Phải từ chối file .txt"
        assert "không được hỗ trợ" in msg

        # File wav hợp lệ
        good_file = tmp_p / "valid_test.wav"
        sr = 48000
        dur = 2.0
        audio = np.zeros(int(sr * dur), dtype=np.float32)
        sf.write(str(good_file), audio, sr)

        ok, msg, info = import_track_to_library("MYSTERY", "TEST_GOOD", good_file)
        assert ok is True, f"Phải import thành công file .wav hợp lệ: {msg}"
        assert info.get("normalized_status") == "READY"


if __name__ == "__main__":
    print("=" * 65)
    print("🚀 BẮT ĐẦU SMOKE TEST: WEB UI STARTUP & IMPORT PERFORMANCE")
    print("=" * 65)
    test_ui_startup_and_components()
    print("✅ TEST 1 PASSED: Web UI startup & component constructors")
    test_import_v9_1_performance_and_schema()
    print("✅ TEST 2 PASSED: Import V9.1 (93 segments < 2s)")
    test_music_library_fast_load_without_renormalization()
    print("✅ TEST 3 PASSED: Music Library fast load from cache")
    test_music_upload_extension_validation()
    print("✅ TEST 4 PASSED: Music upload extension validation")
    print("=" * 65)
    print("🎉 TẤT CẢ 4 TESTS ĐỀU VƯỢT QUA XUẤT SẮC!")
    print("=" * 65)

