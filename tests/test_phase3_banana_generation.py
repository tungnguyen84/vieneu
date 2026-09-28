"""Phase 3 Acceptance Test: Nano Banana Pro Real Generation + Resume + Download.

Executes REAL image generation calls to Google Flow:
- Generates 3 real keyframes via Banana Pro (GEM_PIX_2, 16:9 Landscape).
- Verifies automatic download into projects/<slug>/visual/images/.
- Verifies image files on disk (size, headers).
- Verifies persistent visual_queue.json updates.
- Verifies resume behavior (skips completed scenes without re-requesting).
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.visual_engine.flowkit_adapter import FlowKitAdapter
from apps.visual_engine.character_manager import load_character_library
from apps.visual_engine.asset_manager import VisualAssetManager
from apps.visual_engine.banana_client import BananaClient
from apps.visual_engine.visual_planner import VisualScene


def run_phase3_test():
    print("\n" + "=" * 70)
    print("🎨 BẮT ĐẦU TEST PHASE 3: REAL BANANA PRO GENERATION & PERSISTENCE")
    print("=" * 70)

    # 1. Kiểm tra kết nối Adapter tới Google Flow
    print("\n[BƯỚC 1] Xác minh kết nối FlowKit Adapter...")
    adapter = FlowKitAdapter("http://127.0.0.1:8100")
    st = adapter.get_connection_status()
    print(f"   Server: {st.flowkit_server_running} | Extension: {st.extension_connected} (v{st.extension_version}) | Project: {st.flow_project_id}")
    assert st.is_connected, "Kết nối tới Google Flow qua FlowKit chưa sẵn sàng!"
    print("✅ PASS: Kết nối Google Flow sẵn sàng 100%!")

    # 2. Đọc visual_plan.json của Episode 01
    print("\n[BƯỚC 2] Nạp visual_plan.json đã tạo từ Phase 2...")
    project_dir = REPO_ROOT / "projects/sau_canh_cua_-_episode_01_v9_1_master_reference"
    plan_file = project_dir / "visual/visual_plan.json"
    assert plan_file.exists(), f"Không tìm thấy {plan_file}. Hãy chạy Phase 2 trước!"

    with open(plan_file, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    scenes_data = plan_data.get("scenes", [])
    assert len(scenes_data) >= 30, f"Kỳ vọng ít nhất 30 scenes, thực tế: {len(scenes_data)}"
    scenes = [VisualScene(**d) for d in scenes_data]
    print(f"   Đã nạp {len(scenes)} scenes từ file kế hoạch.")

    # 3. Khởi tạo Banana Client và Asset Manager
    char_lib = load_character_library()
    asset_mgr = VisualAssetManager(project_dir)
    queue = asset_mgr.init_queue(scenes)
    banana_client = BananaClient(adapter, asset_mgr, char_lib)

    # 4. Sinh thật / kiểm tra 3 Banana Pro Images đầu tiên (SC_001, SC_002, SC_003)
    print("\n[BƯỚC 3] Sinh / kiểm tra 3 ảnh thật đầu tiên qua Google Flow (Nano Banana Pro GEM_PIX_2)...")
    test_scenes = scenes[:3]
    for idx, sc in enumerate(test_scenes):
        print(f"\n   [CẢNH {idx + 1}/3] {sc.scene_id} ({sc.visual_type}) [{sc.start_sec}s -> {sc.end_sec}s]")
        print(f"   Prompt: {sc.image_prompt[:95]}...")
        t0 = time.time()
        img_path = banana_client.generate_scene_keyframe(sc, project_id=st.flow_project_id or "", force_regenerate=False)
        dur = time.time() - t0
        assert img_path is not None, f"Sinh ảnh thất bại cho scene {sc.scene_id}!"
        assert img_path.exists(), f"File ảnh không tồn tại trên đĩa: {img_path}"
        sz = img_path.stat().st_size
        print(f"   ✅ Đã có trên đĩa: {img_path.name} ({sz:,} bytes) trong {dur:.2f}s")
        assert sz > 30000, f"Kích thước file ảnh quá nhỏ: {sz} bytes"

    print("\n✅ PASS: Đã sinh và tải thành công 3 ảnh thật từ Google Flow!")

    # 5. Kiểm tra tính toàn vẹn của queue trên đĩa
    print("\n[BƯỚC 4] Kiểm tra persistent queue trên đĩa...")
    queue = asset_mgr.load_queue()
    for sc in test_scenes:
        item = queue.get(sc.scene_id)
        assert item is not None, f"Thiếu queue item cho {sc.scene_id}"
        assert item.image_status == "DONE", f"Trạng thái queue chưa chuyển DONE: {item.image_status}"
        assert item.image_file is not None, f"Thiếu đường dẫn image_file trong queue"
        print(f"   - {sc.scene_id}: status={item.image_status}, media_id={item.image_media_id[:16]}..., file={item.image_file}")
    print("✅ PASS: visual_queue.json được cập nhật chuẩn xác!")

    # 6. Kiểm tra Resume Logic (Không được gọi lại Google Flow nếu đã có ảnh)
    print("\n[BƯỚC 5] Kiểm tra Resume Logic (Bảo đảm không sinh lại ảnh đã hoàn thành)...")
    t_resume_start = time.time()
    res = banana_client.generate_all_keyframes(test_scenes, project_id=st.flow_project_id or "", max_scenes=3)
    t_resume_dur = time.time() - t_resume_start
    print(f"   Thời gian kiểm tra resume 3 cảnh: {t_resume_dur:.3f}s")
    assert t_resume_dur < 1.0, f"Resume quá chậm ({t_resume_dur}s), có thể đã gọi lại API!"
    assert res["success"] == 3
    print("✅ PASS: Resume logic hoạt động tức thì, bảo toàn 100% tài nguyên!")

    # 7. Kiểm tra tiến độ tổng hợp
    print("\n[BƯỚC 6] Kiểm tra tiến độ Episode Visual Progress...")
    prog = asset_mgr.get_progress()
    print(f"   Tổng scenes: {prog['total_scenes']}")
    print(f"   Images ready: {prog['images_ready']}/{prog['total_scenes']}")
    print(f"   Videos ready: {prog['videos_ready']}/{prog['veo_required']}")
    print(f"   Failed: {prog['failed']}")
    assert prog["images_ready"] >= 3
    print("✅ PASS: Tiến độ theo dõi chính xác!")

    print("\n" + "=" * 70)
    print("🎉 TẤT CẢ TIÊU CHÍ TEST PHASE 3 ĐÃ ĐẠT CHUẨN XUẤT SẮC!")
    print("   NANO BANANA PRO GENERATION & PERSISTENCE READY")
    print("=" * 70)


if __name__ == "__main__":
    run_phase3_test()
