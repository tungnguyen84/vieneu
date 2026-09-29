"""Gradio UI Component for Final Auto Assembler (🎬 Ghép Video Hoàn Chỉnh)."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from apps.visual_engine.final_auto_assembler import (
    CANONICAL_SCENE_DEFINITIONS,
    AssemblyPlan,
    AssetValidationReport,
    assemble_full_episode,
    build_assembly_plan,
    inspect_and_extract_zip,
    render_preview_60s,
    validate_imported_assets,
)

logger = logging.getLogger("VieNeu.UIFinalAutoAssembler")

DEFAULT_ZIP_PATH = r"D:\Youtube\Sau cánh cửa\Sau_Canh_Cua_EP01_V9_3_1_FULL_NO_MUSIC\New_Project_FULL_EXPORT.zip"
DEFAULT_AUDIO_MASTER = r"projects/sau_canh_cua_ep01_v9_3_manual_visual/master/final_mix.wav"

ASSEMBLY_TABLE_HEADERS = [
    "Scene", "Segments", "Start", "End", "Duration", "Source", "Asset", "Fallback", "Motion", "Overlay", "Status"
]


def render_final_auto_assembler_ui() -> Dict[str, Any]:
    """Renders the UI elements for Final Auto Assembler."""
    components: Dict[str, Any] = {}

    gr.Markdown(
        "## 🎬 Final Auto Assembler — Ghép Video Hoàn Chỉnh V9.3.1\n"
        "Ghép nối tự động gói xuất khẩu Google Flow (`FULL_EXPORT.zip`) và Audio Master (`final_mix.wav`) "
        "thành video hoàn chỉnh 1080p 30fps. Hoàn toàn cục bộ, bảo toàn nguyên bản 15 scene video đã sinh."
    )

    with gr.Row():
        with gr.Column(scale=3):
            components["zip_path_txt"] = gr.Textbox(
                value=DEFAULT_ZIP_PATH if Path(DEFAULT_ZIP_PATH).exists() else "",
                label="📦 Đường dẫn Google Flow FULL EXPORT ZIP",
                placeholder="D:\\path\\to\\New_Project_FULL_EXPORT.zip",
                info="Tự động quét đệ quy thư mục images/, videos/, manifest_v9_3_1.json trong ZIP."
            )
        with gr.Column(scale=3):
            components["audio_master_txt"] = gr.Textbox(
                value=DEFAULT_AUDIO_MASTER if Path(DEFAULT_AUDIO_MASTER).exists() else "",
                label="🎵 Đường dẫn Audio Master (final_mix.wav)",
                placeholder="projects/sau_canh_cua_ep01_v9_3_manual_visual/master/final_mix.wav",
                info="Audio Master là MASTER CLOCK. Độ dài video thích ứng chính xác theo audio."
            )

    with gr.Row():
        components["btn_validate_assets"] = gr.Button("🔍 1. Kiểm tra Asset (Validate)", variant="secondary")
        components["btn_build_timeline"] = gr.Button("🧩 2. Tạo Timeline (Assembly Plan)", variant="primary")
        components["btn_preview_60s"] = gr.Button("▶ 3. Xem Preview 60 giây", variant="secondary")
        components["btn_auto_assemble"] = gr.Button("🎬 4. Ghép Video Hoàn Chỉnh", variant="primary")
        components["btn_cancel_assemble"] = gr.Button("⏹ Dừng Render", variant="stop")

    components["md_validation_report"] = gr.Markdown("*(Nhấn 'Kiểm tra Asset' để thẩm định tệp ZIP và Audio Master)*")

    # State stores
    components["images_map_state"] = gr.State({})
    components["videos_map_state"] = gr.State({})
    components["manifest_state"] = gr.State({})
    components["assembly_plan_state"] = gr.State(None)
    components["manual_overrides_state"] = gr.State({})
    components["cancel_event_state"] = gr.State(None)

    with gr.Accordion("🔍 Bảng Kế Hoạch Ghép Nối (Assembly Plan Inspector) & Ghi Đè Thủ Công", open=True):
        components["assembly_table"] = gr.Dataframe(
            headers=ASSEMBLY_TABLE_HEADERS,
            datatype=["str"] * len(ASSEMBLY_TABLE_HEADERS),
            interactive=False,
            wrap=True,
            label="Kế hoạch ghép nối 45 scenes"
        )
        with gr.Row():
            components["dd_override_scene"] = gr.Dropdown(
                choices=[f"SC_{i:03d}" for i in range(1, 46)],
                value="SC_001",
                label="Chọn Scene ghi đè thủ công (Manual Override)",
                scale=2
            )
            components["dd_override_source"] = gr.Dropdown(
                choices=["Mặc định (Auto)", "Dùng Video (Use Video)", "Dùng Ảnh (Use Image)"],
                value="Mặc định (Auto)",
                label="Chỉ định nguồn",
                scale=2
            )
            components["btn_apply_override"] = gr.Button("✅ Áp dụng Ghi Đè", scale=1)

    with gr.Row():
        with gr.Column(scale=3):
            components["preview_video_player"] = gr.Video(label="▶ Preview Video (60s)")
        with gr.Column(scale=3):
            components["final_video_player"] = gr.Video(label="🎬 Final Video Hoàn Chỉnh (1080p 30fps)")
            components["final_file_download"] = gr.File(label="📥 Tải Final MP4", interactive=False)

    components["md_status_log"] = gr.Markdown("### ℹ️ Trạng thái hệ thống: Sẵn sàng")

    return components


def format_assembly_table_rows(plan: AssemblyPlan) -> List[List[str]]:
    """Formats assembly plan into rows for Gradio Dataframe."""
    rows = []
    for sc in plan.scenes:
        sc_col = sc.scene_id
        segs_col = f"{sc.segment_start} - {sc.segment_end}"
        start_col = f"{sc.start_sec:.2f}s"
        end_col = f"{sc.end_sec:.2f}s"
        dur_col = f"{sc.duration_sec:.2f}s"
        source_col = f"🎥 VIDEO" if sc.source_type == "VIDEO" else "🖼️ IMAGE"
        asset_col = Path(sc.source_file).name if sc.source_file else "None"
        fb_col = Path(sc.fallback_image).name if sc.fallback_image else "-"
        motion_col = sc.image_motion or "STATIC"
        overlay_col = f"📝 {sc.overlays[0]}" if sc.overlays else "-"
        status_col = f"✅ READY ({sc.status})" if sc.status == "READY" else f"⚠️ {sc.status}"
        rows.append([sc_col, segs_col, start_col, end_col, dur_col, source_col, asset_col, fb_col, motion_col, overlay_col, status_col])
    return rows


def bind_final_auto_assembler_events(components: Dict[str, Any]) -> None:
    """Binds event handlers for Final Auto Assembler UI."""

    def _on_validate(zip_path: str, audio_path: str):
        if not zip_path or not Path(zip_path).exists():
            return (
                "⚠️ **Lỗi:** Đường dẫn Google Flow ZIP không tồn tại. Vui lòng kiểm tra lại.",
                {}, {}, {}, None, []
            )

        extract_dir = Path("cache/final_assembler/extracted_assets")
        try:
            img_map, vid_map, manifest_p, unknown_files = inspect_and_extract_zip(zip_path, extract_dir)
            report = validate_imported_assets(img_map, vid_map, unknown_files=unknown_files)
            rep_md = report.to_markdown()

            # Stringify paths for Gradio state
            img_dict = {k: str(v) for k, v in img_map.items()}
            vid_dict = {k: str(v) for k, v in vid_map.items()}

            manifest_data = {}
            if manifest_p and manifest_p.exists():
                with open(manifest_p, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)

            return rep_md, img_dict, vid_dict, manifest_data, None, []
        except Exception as exc:
            logger.error(f"[UI] Asset validation error: {exc}", exc_info=True)
            return f"❌ **Lỗi thẩm định:** `{exc}`", {}, {}, {}, None, []

    components["btn_validate_assets"].click(
        fn=_on_validate,
        inputs=[components["zip_path_txt"], components["audio_master_txt"]],
        outputs=[
            components["md_validation_report"],
            components["images_map_state"],
            components["videos_map_state"],
            components["manifest_state"],
            components["assembly_plan_state"],
            components["assembly_table"]
        ]
    )

    def _on_build_timeline(img_dict, vid_dict, audio_path, overrides, manifest_data):
        if not img_dict:
            return None, [], "⚠️ Vui lòng nhấn **Kiểm tra Asset** trước khi tạo Timeline."
        if not audio_path or not Path(audio_path).exists():
            return None, [], "⚠️ Tệp Audio Master không tồn tại."

        img_map = {k: Path(v) for k, v in img_dict.items()}
        vid_map = {k: Path(v) for k, v in vid_dict.items()}

        plan = build_assembly_plan(
            images_map=img_map,
            videos_map=vid_map,
            audio_master_path=audio_path,
            manual_overrides=overrides,
            manifest_data=manifest_data,
        )
        plan_dict = plan.to_dict()
        rows = format_assembly_table_rows(plan)
        msg = (
            f"### 🧩 Kế Hoạch Ghép Nối Đã Khởi Tạo Thành Công\n"
            f"- **Tổng số scenes:** `{len(plan.scenes)}` | **Video Scenes:** `{plan.video_scene_count}` | **Image Scenes:** `{plan.image_scene_count}`\n"
            f"- **Audio Duration:** `{plan.total_audio_duration_sec:.2f}s` | **Visual Duration:** `{plan.total_visual_duration_sec:.2f}s` (Delta: `{plan.av_delta_sec:.3f}s`)"
        )
        return plan_dict, rows, msg

    components["btn_build_timeline"].click(
        fn=_on_build_timeline,
        inputs=[
            components["images_map_state"],
            components["videos_map_state"],
            components["audio_master_txt"],
            components["manual_overrides_state"],
            components["manifest_state"]
        ],
        outputs=[
            components["assembly_plan_state"],
            components["assembly_table"],
            components["md_status_log"]
        ]
    )

    def _on_apply_override(scene_id: str, choice: str, current_overrides: Dict[str, str], img_dict, vid_dict, audio_path, manifest_data):
        overrides = dict(current_overrides or {})
        if choice == "Dùng Video (Use Video)":
            overrides[scene_id] = "USE_VIDEO"
        elif choice == "Dùng Ảnh (Use Image)":
            overrides[scene_id] = "USE_IMAGE"
        else:
            overrides.pop(scene_id, None)

        if not img_dict or not audio_path:
            return overrides, None, [], f"Đã lưu override cho {scene_id}: {choice}"

        img_map = {k: Path(v) for k, v in img_dict.items()}
        vid_map = {k: Path(v) for k, v in vid_dict.items()}
        plan = build_assembly_plan(img_map, vid_map, audio_path, overrides, manifest_data)
        rows = format_assembly_table_rows(plan)
        return overrides, plan.to_dict(), rows, f"✅ Đã áp dụng ghi đè cho **{scene_id}**: `{choice}`"

    components["btn_apply_override"].click(
        fn=_on_apply_override,
        inputs=[
            components["dd_override_scene"],
            components["dd_override_source"],
            components["manual_overrides_state"],
            components["images_map_state"],
            components["videos_map_state"],
            components["audio_master_txt"],
            components["manifest_state"]
        ],
        outputs=[
            components["manual_overrides_state"],
            components["assembly_plan_state"],
            components["assembly_table"],
            components["md_status_log"]
        ]
    )

    def _on_preview_60s(plan_dict):
        if not plan_dict:
            return None, "⚠️ Chưa có Assembly Plan. Vui lòng nhấn **Tạo Timeline** trước."
        plan = AssemblyPlan.from_dict(plan_dict)
        preview_out = Path("preview/EP001_preview_60s.mp4")
        cache_dir = Path("cache/final_assembler")
        out_p, stats = render_preview_60s(plan, preview_output_path=preview_out, cache_dir=cache_dir)
        msg = (
            f"### ▶ Preview 60 Giây Sẵn Sàng\n"
            f"- **Tệp:** `{out_p}`\n"
            f"- **Thời lượng:** `{stats['duration_sec']:.2f}s` | **Độ phân giải:** `{stats['resolution']}`\n"
            f"- **Kích thước:** `{stats['file_size_bytes']:,} bytes`"
        )
        return str(out_p), msg

    components["btn_preview_60s"].click(
        fn=_on_preview_60s,
        inputs=[components["assembly_plan_state"]],
        outputs=[components["preview_video_player"], components["md_status_log"]]
    )

    def _on_auto_assemble(plan_dict):
        if not plan_dict:
            return None, None, "⚠️ Chưa có Assembly Plan. Vui lòng nhấn **Tạo Timeline** trước."
        plan = AssemblyPlan.from_dict(plan_dict)
        final_out = Path("final/EP001_Sau_Canh_Cua_V9_3_1_FINAL.mp4")
        cache_dir = Path("cache/final_assembler")

        cancel_ev = threading.Event()
        out_p, qc = assemble_full_episode(
            plan=plan,
            output_mp4_path=final_out,
            cache_dir=cache_dir,
            cancel_event=cancel_ev,
        )
        msg = (
            f"### 🎉 Ghép Video Hoàn Chỉnh Thành Công!\n"
            f"- **Tệp xuất xưởng:** `{out_p}`\n"
            f"- **QC Status:** `{qc['qc_status']}` | **A/V Sync Delta:** `{qc['av_delta_sec']:.3f}s`\n"
            f"- **Độ phân giải:** `{qc['resolution']}` (30 fps) | **Video Codec:** `{qc['video_codec']}` | **Audio Codec:** `{qc['audio_codec']}`\n"
            f"- **Số scenes:** `{qc['scene_count']}` (Videos: `{qc['video_scenes_count']}`, Images: `{qc['image_scenes_count']}`)\n"
            f"- **Black Gaps:** `{qc['black_gaps_detected']}`\n"
        )
        return str(out_p), str(out_p), msg

    components["btn_auto_assemble"].click(
        fn=_on_auto_assemble,
        inputs=[components["assembly_plan_state"]],
        outputs=[
            components["final_video_player"],
            components["final_file_download"],
            components["md_status_log"]
        ]
    )
