"""
Giao diện và xử lý sự kiện cho tính năng Production Script Storytelling JSON.
Tích hợp trực tiếp vào Tab Hội thoại của VieNeu-TTS.
"""

import os
import json
import time
import shutil
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import gradio as gr
import soundfile as sf
import numpy as np

from apps.production_story import (
    validate_story_json,
    generate_single_segment_takes,
    build_master_audio,
    load_or_init_project_state,
    save_project_state,
    export_project_json,
    build_segments_dataframe,
    select_take_for_segment,
    get_take_audio_paths,
    compute_segment_hash,
    sanitize_slug
)

MAX_STORY_CHARACTERS = 8

def render_production_story_ui(preset_voices_cache_getter):
    """
    Dựng giao diện cho sub-tab Production Script JSON.
    preset_voices_cache_getter: hàm trả về PRESET_VOICES_CACHE hiện tại.
    """
    gr.Markdown(
        "## 🎬 Production Storytelling Script (JSON Engine)\n"
        "Nhập kịch bản JSON cấu trúc cao cho video dài tập: Quản lý nhân vật, sinh độc lập từng segment, "
        "hỗ trợ multi-take, post-process tốc độ (FFmpeg), chèn khoảng lặng chuẩn xác chống double pause, "
        "và xuất Master Audio chuẩn broadcast (-14 LUFS, -1 dBTP)."
    )

    # 1. Action Row
    with gr.Row():
        btn_import_json = gr.UploadButton("📂 Import Kịch bản JSON", file_types=[".json"], variant="primary")
        btn_sample_pilot = gr.Button("📋 Nạp Kịch bản Pilot Mẫu (92 segments)", size="sm", variant="secondary")
        btn_export_json = gr.Button("💾 Xuất Project JSON", size="sm")
        file_export_download = gr.File(label="Tải file JSON đã xuất", visible=False)

    # 2. Project Info Banner
    story_project_info_md = gr.Markdown("*(Chưa tải kịch bản JSON. Vui lòng nhấn Import hoặc Nạp kịch bản mẫu.)*")
    story_warnings_md = gr.Markdown(visible=False)

    # 3. Characters Mapping Accordion
    with gr.Accordion("👥 1. Quản lý Nhân vật & Ánh xạ Giọng đọc (Character Mapping)", open=True) as acc_chars:
        gr.Markdown("*Tự động phát hiện từ trường `characters` trong JSON. Nếu giọng không tồn tại, vui lòng chọn giọng thay thế bên dưới.*")
        char_rows = []
        char_id_labels = []
        char_name_boxes = []
        char_voice_dds = []
        char_speed_sliders = []
        char_status_labels = []

        for idx in range(MAX_STORY_CHARACTERS):
            with gr.Row(visible=False) as r:
                c_id = gr.Textbox(label="Mã ID", interactive=False, scale=1, min_width=80)
                c_name = gr.Textbox(label="Tên hiển thị / Vai trò", interactive=False, scale=2, min_width=130)
                c_voice = gr.Dropdown(
                    choices=preset_voices_cache_getter() or [],
                    label="Giọng đọc VieNeu",
                    interactive=True,
                    scale=3,
                    allow_custom_value=True
                )
                c_speed = gr.Slider(minimum=0.88, maximum=1.05, value=1.0, step=0.01, label="Tốc độ mặc định", scale=2)
                c_status = gr.Textbox(label="Trạng thái", interactive=False, scale=2, min_width=120)

            char_rows.append(r)
            char_id_labels.append(c_id)
            char_name_boxes.append(c_name)
            char_voice_dds.append(c_voice)
            char_speed_sliders.append(c_speed)
            char_status_labels.append(c_status)

        with gr.Row():
            btn_apply_char_mapping = gr.Button("✅ Áp dụng thay đổi giọng & tốc độ vào kịch bản", size="sm", variant="secondary")

    # 4. Segments Table Accordion
    with gr.Accordion("📜 2. Bảng Phân đoạn Kịch bản (Segment Editor & Table)", open=True):
        with gr.Row():
            btn_select_all = gr.Button("Chọn tất cả", size="sm")
            btn_select_failed = gr.Button("Chọn phân đoạn lỗi", size="sm")
            btn_select_multitake = gr.Button("Chọn phân đoạn Multi-take", size="sm")
            btn_deselect_all = gr.Button("Bỏ chọn tất cả", size="sm")

        df_headers = [
            "Chọn", "ID", "Nhân vật", "Lời thoại (Text)", "Giọng đọc",
            "Sắc thái", "Tốc độ", "Nghỉ trước (s)", "Nghỉ sau (s)", "Takes", "Trạng thái", "Take đã chọn"
        ]
        story_segments_df = gr.DataFrame(
            headers=df_headers,
            datatype=["bool", "str", "str", "str", "str", "str", "number", "number", "number", "number", "str", "str"],
            row_count=(1, "dynamic"),
            interactive=True,
            wrap=True
        )

    # 5. Generation Controls & Progress
    with gr.Row():
        btn_generate_story = gr.Button("⚡ Sinh TTS các phân đoạn đã chọn", variant="primary", scale=3)
        btn_retry_failed = gr.Button("🔄 Sinh lại phân đoạn lỗi", variant="secondary", scale=2)
        btn_stop_story = gr.Button("⏹️ Dừng lại", variant="stop", scale=1)

    story_progress_md = gr.Markdown("**Trạng thái:** Sẵn sàng.")
    story_log_output = gr.Textbox(label="Nhật ký tiến trình (Realtime Log)", lines=5, interactive=False)

    # 6. Audio Preview & Take Selection
    with gr.Accordion("🎧 3. Nghe thử & Chọn Take (Take Preview & Selection)", open=True):
        with gr.Row():
            preview_seg_dropdown = gr.Dropdown(label="Chọn phân đoạn để nghe các take", choices=[], interactive=True, scale=3)
            btn_refresh_preview = gr.Button("🔄 Tải lại danh sách", size="sm", scale=1)

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### 🔹 Take 01 (Mặc định)")
                audio_take1 = gr.Audio(label="Take 01", interactive=False)
                btn_use_take1 = gr.Button("✅ Sử dụng Take 01", size="sm", variant="secondary")
            with gr.Column(scale=1):
                gr.Markdown("#### 🔹 Take 02")
                audio_take2 = gr.Audio(label="Take 02", interactive=False)
                btn_use_take2 = gr.Button("✅ Sử dụng Take 02", size="sm", variant="secondary")
            with gr.Column(scale=1):
                gr.Markdown("#### 🔹 Take 03")
                audio_take3 = gr.Audio(label="Take 03", interactive=False)
                btn_use_take3 = gr.Button("✅ Sử dụng Take 03", size="sm", variant="secondary")

        take_select_status_md = gr.Markdown("")

    # 7. Master Audio Assembly
    with gr.Accordion("🎛️ 4. Ghép & Xuất Master Audio (Timeline & Normalization)", open=True):
        with gr.Row():
            gap_rule_radio = gr.Radio(
                choices=[("Khuyến nghị: max(pause_after, next_pause_before)", "max"), ("Cộng dồn: pause_after + next_pause_before", "sum")],
                value="max",
                label="Quy tắc khoảng nghỉ (Tránh Double Pause)"
            )
            room_tone_upload = gr.File(label="Upload Room Tone / Ambience (Tùy chọn WAV/MP3)", file_types=[".wav", ".mp3"])
            room_tone_vol_slider = gr.Slider(minimum=-60.0, maximum=-10.0, value=-40.0, step=1.0, label="Âm lượng Room Tone (dB)")

        with gr.Row():
            target_lufs_num = gr.Number(value=-14.0, label="Target Integrated LUFS")
            true_peak_num = gr.Number(value=-1.0, label="True Peak (dBTP)")
            btn_build_master = gr.Button("🎛️ Bắt đầu Ghép Master Audio", variant="primary", scale=2)

        master_status_md = gr.Markdown("")
        with gr.Row():
            master_wav_audio = gr.Audio(label="Master Audio WAV (48kHz 24-bit PCM)", interactive=False)
            master_mp3_audio = gr.Audio(label="Master Audio MP3 (320kbps)", interactive=False)

        with gr.Row():
            master_wav_download = gr.File(label="Tải file Master WAV", visible=False)
            master_mp3_download = gr.File(label="Tải file Master MP3", visible=False)

    # State stores
    story_raw_json_state = gr.State(None)
    story_project_info_state = gr.State({})
    story_characters_state = gr.State({})
    story_segments_state = gr.State([])
    story_project_dir_state = gr.State(None)
    story_runtime_state = gr.State({})

    components = {
        "btn_import_json": btn_import_json,
        "btn_sample_pilot": btn_sample_pilot,
        "btn_export_json": btn_export_json,
        "file_export_download": file_export_download,
        "story_project_info_md": story_project_info_md,
        "story_warnings_md": story_warnings_md,
        "char_rows": char_rows,
        "char_id_labels": char_id_labels,
        "char_name_boxes": char_name_boxes,
        "char_voice_dds": char_voice_dds,
        "char_speed_sliders": char_speed_sliders,
        "char_status_labels": char_status_labels,
        "btn_apply_char_mapping": btn_apply_char_mapping,
        "btn_select_all": btn_select_all,
        "btn_select_failed": btn_select_failed,
        "btn_select_multitake": btn_select_multitake,
        "btn_deselect_all": btn_deselect_all,
        "story_segments_df": story_segments_df,
        "btn_generate_story": btn_generate_story,
        "btn_retry_failed": btn_retry_failed,
        "btn_stop_story": btn_stop_story,
        "story_progress_md": story_progress_md,
        "story_log_output": story_log_output,
        "preview_seg_dropdown": preview_seg_dropdown,
        "btn_refresh_preview": btn_refresh_preview,
        "audio_take1": audio_take1,
        "audio_take2": audio_take2,
        "audio_take3": audio_take3,
        "btn_use_take1": btn_use_take1,
        "btn_use_take2": btn_use_take2,
        "btn_use_take3": btn_use_take3,
        "take_select_status_md": take_select_status_md,
        "gap_rule_radio": gap_rule_radio,
        "room_tone_upload": room_tone_upload,
        "room_tone_vol_slider": room_tone_vol_slider,
        "target_lufs_num": target_lufs_num,
        "true_peak_num": true_peak_num,
        "btn_build_master": btn_build_master,
        "master_status_md": master_status_md,
        "master_wav_audio": master_wav_audio,
        "master_mp3_audio": master_mp3_audio,
        "master_wav_download": master_wav_download,
        "master_mp3_download": master_mp3_download,
        "story_raw_json_state": story_raw_json_state,
        "story_project_info_state": story_project_info_state,
        "story_characters_state": story_characters_state,
        "story_segments_state": story_segments_state,
        "story_project_dir_state": story_project_dir_state,
        "story_runtime_state": story_runtime_state,
    }
    return components


def handle_import_json_data(json_content_or_file, available_voices: list):
    """Xử lý nạp dữ liệu JSON và cập nhật trạng thái UI."""
    if not json_content_or_file:
        return (
            "⚠️ Vui lòng chọn file JSON kịch bản.",
            gr.update(visible=False),
            *[gr.update(visible=False)] * (MAX_STORY_CHARACTERS * 5),
            [],
            gr.update(choices=[]),
            None, {}, {}, [], None, {}
        )

    try:
        if hasattr(json_content_or_file, "name"):
            filepath = json_content_or_file.name
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif isinstance(json_content_or_file, str):
            if os.path.exists(json_content_or_file):
                with open(json_content_or_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = json.loads(json_content_or_file)
        elif isinstance(json_content_or_file, dict):
            data = json_content_or_file
        else:
            raise ValueError("Định dạng dữ liệu không hỗ trợ.")

        is_valid, err, proj_info, chars_map, warnings, stats = validate_story_json(data, available_voices)
        if not is_valid:
            return (
                f"❌ Lỗi cấu trúc JSON: {err}",
                gr.update(visible=False),
                *[gr.update(visible=False)] * (MAX_STORY_CHARACTERS * 5),
                [],
                gr.update(choices=[]),
                None, {}, {}, [], None, {}
            )

        # Tạo thư mục project
        base_projects_dir = Path("projects")
        base_projects_dir.mkdir(exist_ok=True)
        proj_slug = proj_info["slug"]
        project_dir = base_projects_dir / proj_slug
        project_dir.mkdir(parents=True, exist_ok=True)

        # Tải hoặc khởi tạo runtime state
        runtime_state = load_or_init_project_state(project_dir, data)

        # Lưu source.json vào thư mục project
        with open(project_dir / "source.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Thông tin project
        info_md = (
            f"### 📖 Dự án: **{proj_info['title']}** — *{proj_info['episode_title']}*\n"
            f"- **Số phân đoạn (Segments):** {stats['segment_count']} | **Nhân vật:** {stats['character_count']} | "
            f"**Tổng số từ:** {stats['total_words']} từ\n"
            f"- **Thời lượng ước tính:** ~{stats['estimated_seconds']/60:.1f} phút ({int(stats['estimated_seconds'])} giây) | "
            f"**Tần số lấy mẫu:** {proj_info['sample_rate']}Hz | **Thư mục:** `{project_dir}`"
        )

        warn_md_content = "\n\n".join(warnings) if warnings else ""
        warn_md_update = gr.update(value=warn_md_content, visible=bool(warn_md_content))

        # Cập nhật danh sách nhân vật
        char_list = list(chars_map.values())
        char_ui_updates = []
        for i in range(MAX_STORY_CHARACTERS):
            if i < len(char_list):
                c = char_list[i]
                status_txt = "✅ Khớp" if c["match_status"] == "EXACT" else ("ℹ️ Ánh xạ" if "ALIASED" in c["match_status"] else "⚠️ Chưa khớp")
                char_ui_updates.extend([
                    gr.update(value=c["char_id"], visible=True),
                    gr.update(value=f"{c['display_name']} ({c['role']})" if c['role'] else c['display_name'], visible=True),
                    gr.update(value=c["voice"], visible=True),
                    gr.update(value=c["default_speed"], visible=True),
                    gr.update(value=status_txt, visible=True),
                ])
            else:
                char_ui_updates.extend([
                    gr.update(value="", visible=False),
                    gr.update(value="", visible=False),
                    gr.update(value=None, visible=False),
                    gr.update(value=1.0, visible=False),
                    gr.update(value="", visible=False),
                ])

        # DataFrame segments
        segments = data.get("segments", [])
        df_rows = build_segments_dataframe(segments, chars_map, runtime_state)

        # Dropdown options for preview
        seg_choices = [f"[{s.get('id', idx+1):0>3}] {s.get('speaker', '')}: {s.get('text', '')[:40]}..." for idx, s in enumerate(segments)]
        preview_dd_update = gr.update(choices=seg_choices, value=seg_choices[0] if seg_choices else None)

        return (
            info_md,
            warn_md_update,
            *char_ui_updates,
            df_rows,
            preview_dd_update,
            data,
            proj_info,
            chars_map,
            segments,
            str(project_dir),
            runtime_state
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return (
            f"❌ Đã xảy ra lỗi khi đọc file JSON: {str(e)}",
            gr.update(visible=False),
            *[gr.update(visible=False)] * (MAX_STORY_CHARACTERS * 5),
            [],
            gr.update(choices=[]),
            None, {}, {}, [], None, {}
        )


def bind_production_story_events(components: dict, get_tts_engine_fn, get_available_voices_fn, stop_event):
    """
    Gán các sự kiện tương tác cho module Production Storytelling.
    """
    c = components

    # 1. Import JSON
    char_flat_outputs = []
    for i in range(MAX_STORY_CHARACTERS):
        char_flat_outputs.extend([
            c["char_id_labels"][i],
            c["char_name_boxes"][i],
            c["char_voice_dds"][i],
            c["char_speed_sliders"][i],
            c["char_status_labels"][i]
        ])

    def _on_import(file):
        voices = get_available_voices_fn()
        return handle_import_json_data(file, voices)

    import_outputs = [
        c["story_project_info_md"],
        c["story_warnings_md"],
        *char_flat_outputs,
        c["story_segments_df"],
        c["preview_seg_dropdown"],
        c["story_raw_json_state"],
        c["story_project_info_state"],
        c["story_characters_state"],
        c["story_segments_state"],
        c["story_project_dir_state"],
        c["story_runtime_state"]
    ]

    c["btn_import_json"].upload(
        fn=_on_import,
        inputs=[c["btn_import_json"]],
        outputs=import_outputs
    )

    # 2. Sample Pilot Load
    def _on_load_sample():
        sample_path = "tests/test_pilot_story.json"
        if not os.path.exists(sample_path):
            return (
                "❌ Không tìm thấy file tests/test_pilot_story.json",
                gr.update(visible=False),
                *[gr.update(visible=False)] * (MAX_STORY_CHARACTERS * 5),
                [],
                gr.update(choices=[]),
                None, {}, {}, [], None, {}
            )
        voices = get_available_voices_fn()
        return handle_import_json_data(sample_path, voices)

    c["btn_sample_pilot"].click(
        fn=_on_load_sample,
        inputs=[],
        outputs=import_outputs
    )

    # 3. Apply Character Mapping
    def _on_apply_char_mapping(chars_map, segments, runtime_state, *char_inputs):
        if not chars_map:
            return gr.update(), chars_map

        new_map = dict(chars_map)
        char_keys = list(new_map.keys())

        # char_inputs theo thứ tự id, name, voice, speed, status cho mỗi nhân vật
        for i in range(min(len(char_keys), MAX_STORY_CHARACTERS)):
            idx_base = i * 5
            cid = char_inputs[idx_base]
            voice = char_inputs[idx_base + 2]
            speed = char_inputs[idx_base + 3]
            if cid in new_map:
                new_map[cid]["voice"] = voice
                new_map[cid]["default_speed"] = speed

        # Cập nhật lại DataFrame
        new_df = build_segments_dataframe(segments, new_map, runtime_state)
        return new_df, new_map

    c["btn_apply_char_mapping"].click(
        fn=_on_apply_char_mapping,
        inputs=[
            c["story_characters_state"],
            c["story_segments_state"],
            c["story_runtime_state"],
            *char_flat_outputs
        ],
        outputs=[c["story_segments_df"], c["story_characters_state"]]
    )

    # 4. Checkbox Selection Helpers
    def _toggle_all(df_data, checked: bool):
        if df_data is None:
            return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            r[0] = checked
        return rows

    def _select_failed(df_data):
        if df_data is None:
            return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            r[0] = (r[10] == "FAILED")
        return rows

    def _select_multitake(df_data):
        if df_data is None:
            return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            r[0] = (int(r[9]) > 1)
        return rows

    c["btn_select_all"].click(lambda df: _toggle_all(df, True), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_deselect_all"].click(lambda df: _toggle_all(df, False), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_failed"].click(fn=_select_failed, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_multitake"].click(fn=_select_multitake, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])

    # 5. Stop Generation
    c["btn_stop_story"].click(lambda: stop_event.set(), inputs=[], outputs=[])

    # 6. Generator: TTS Generation (Sequential with Cache, Resume, & Multi-take)
    def _run_generation(df_data, segments, chars_map, project_dir_str, runtime_state, is_retry_failed_only=False):
        tts = get_tts_engine_fn()
        if tts is None:
            yield (
                "⚠️ **Chưa tải model!** Vui lòng bấm nút **'Tải Model'** ở thanh điều khiển bên trái trước.",
                "⚠️ Model chưa sẵn sàng.",
                df_data,
                runtime_state
            )
            return

        if not project_dir_str or not segments:
            yield (
                "⚠️ Chưa có dữ liệu dự án kịch bản.",
                "⚠️ Không có segment để xử lý.",
                df_data,
                runtime_state
            )
            return

        project_dir = Path(project_dir_str)
        stop_event.clear()

        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        # Tạo map id -> row index
        id_to_row_idx = {str(r[1]).zfill(3): idx for idx, r in enumerate(rows)}

        # Xác định danh sách cần sinh
        targets = []
        for seg in segments:
            seg_id = str(seg.get("id", "")).zfill(3)
            row_idx = id_to_row_idx.get(seg_id)
            if row_idx is None:
                continue
            is_selected = bool(rows[row_idx][0])
            status = rows[row_idx][10]

            if is_retry_failed_only:
                if status == "FAILED":
                    targets.append(seg)
            else:
                if is_selected:
                    targets.append(seg)

        total_targets = len(targets)
        if total_targets == 0:
            yield (
                "⚠️ Không có phân đoạn nào được chọn để sinh.",
                "Không có tác vụ.",
                rows,
                runtime_state
            )
            return

        log_lines = [f"🚀 Bắt đầu sinh TTS cho {total_targets} phân đoạn..."]
        yield ("\n".join(log_lines), f"⏳ Chuẩn bị sinh {total_targets} phân đoạn...", rows, runtime_state)

        success_count = 0
        failed_count = 0
        cached_count = 0
        start_time = time.time()

        for idx, seg in enumerate(targets):
            if stop_event.is_set():
                log_lines.append("⏹️ Quá trình sinh đã bị dừng lại bởi người dùng.")
                break

            seg_id = str(seg.get("id", "")).zfill(3)
            speaker = seg.get("speaker", "UNKNOWN")
            char_cfg = chars_map.get(speaker, {})
            voice = char_cfg.get("voice", "")
            current_hash = compute_segment_hash(seg, voice, "v3turbo")

            row_idx = id_to_row_idx.get(seg_id)

            # Kiểm tra Cache
            cached_seg = runtime_state.get("segments", {}).get(seg_id)
            is_cached = False
            if cached_seg and cached_seg.get("hash") == current_hash and cached_seg.get("status") == "COMPLETED":
                # Kiểm tra file selected và file raw tồn tại
                sel_p = project_dir / (cached_seg.get("selected_file") or f"selected/{seg_id}.wav")
                if sel_p.exists():
                    is_cached = True

            if is_cached:
                cached_count += 1
                if row_idx is not None:
                    rows[row_idx][10] = "CACHED"
                log_lines.append(f"⚡ [{idx+1}/{total_targets}] Phân đoạn {seg_id}_{speaker}: Đã có trong Cache (Bỏ qua).")
                yield (
                    "\n".join(log_lines[-10:]),
                    f"⚡ {idx+1}/{total_targets} | Phân đoạn {seg_id}_{speaker} (Cached)",
                    rows,
                    runtime_state
                )
                continue

            # Tiến hành sinh mới
            elapsed = time.time() - start_time
            avg_per_seg = elapsed / max(1, (success_count + failed_count))
            remaining_segs = total_targets - (idx + 1)
            eta_sec = int(avg_per_seg * remaining_segs)

            progress_msg = f"⏳ Đang sinh {idx+1}/{total_targets} | Phân đoạn: **{seg_id}_{speaker}** | Đã chạy: {int(elapsed)}s | Còn lại: ~{eta_sec}s"
            log_lines.append(f"🎙️ [{idx+1}/{total_targets}] Đang sinh {seg_id}_{speaker} (Takes: {seg.get('multi_take', 1)}, Speed: {seg.get('speed', 1.0)})...")
            yield ("\n".join(log_lines[-10:]), progress_msg, rows, runtime_state)

            success, msg, seg_result = generate_single_segment_takes(
                tts_engine=tts,
                project_dir=project_dir,
                segment=seg,
                char_config=char_cfg,
                model_version="v3turbo",
                temperature=0.8
            )

            if success:
                success_count += 1
                runtime_state.setdefault("segments", {})[seg_id] = seg_result
                save_project_state(project_dir, runtime_state)
                if row_idx is not None:
                    rows[row_idx][10] = "COMPLETED"
                    rows[row_idx][11] = f"Take {seg_result.get('selected_take', 1)}"
                log_lines.append(f"  ✅ Phân đoạn {seg_id}: Hoàn tất ({len(seg_result.get('takes', {}))} takes).")
            else:
                failed_count += 1
                runtime_state.setdefault("segments", {})[seg_id] = {
                    "id": seg_id,
                    "status": "FAILED",
                    "error": msg
                }
                save_project_state(project_dir, runtime_state)
                if row_idx is not None:
                    rows[row_idx][10] = "FAILED"
                log_lines.append(f"  ❌ Phân đoạn {seg_id} Lỗi: {msg}")

            yield ("\n".join(log_lines[-10:]), progress_msg, rows, runtime_state)

        total_elapsed = time.time() - start_time
        summary_msg = f"🎉 **Hoàn thành!** Thành công: {success_count} | Lỗi: {failed_count} | Cache: {cached_count} | Tổng thời gian: {total_elapsed:.1f}s"
        log_lines.append(summary_msg)
        yield ("\n".join(log_lines[-10:]), summary_msg, rows, runtime_state)

    c["btn_generate_story"].click(
        fn=lambda df, s, c_m, p_d, r_s: _run_generation(df, s, c_m, p_d, r_s, is_retry_failed_only=False),
        inputs=[
            c["story_segments_df"],
            c["story_segments_state"],
            c["story_characters_state"],
            c["story_project_dir_state"],
            c["story_runtime_state"]
        ],
        outputs=[
            c["story_log_output"],
            c["story_progress_md"],
            c["story_segments_df"],
            c["story_runtime_state"]
        ]
    )

    c["btn_retry_failed"].click(
        fn=lambda df, s, c_m, p_d, r_s: _run_generation(df, s, c_m, p_d, r_s, is_retry_failed_only=True),
        inputs=[
            c["story_segments_df"],
            c["story_segments_state"],
            c["story_characters_state"],
            c["story_project_dir_state"],
            c["story_runtime_state"]
        ],
        outputs=[
            c["story_log_output"],
            c["story_progress_md"],
            c["story_segments_df"],
            c["story_runtime_state"]
        ]
    )

    # 7. Take Preview & Selection
    def _on_preview_select(seg_label, project_dir_str, runtime_state):
        if not seg_label or not project_dir_str:
            return None, None, None, ""
        seg_id = seg_label.split("]")[0].replace("[", "").strip()
        project_dir = Path(project_dir_str)
        paths = get_take_audio_paths(project_dir, runtime_state, seg_id)
        selected_take = runtime_state.get("segments", {}).get(seg_id, {}).get("selected_take", 1)
        status = f"Phân đoạn **{seg_id}** đang sử dụng: **Take {selected_take}**"
        return paths.get(1), paths.get(2), paths.get(3), status

    c["preview_seg_dropdown"].change(
        fn=_on_preview_select,
        inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"]],
        outputs=[c["audio_take1"], c["audio_take2"], c["audio_take3"], c["take_select_status_md"]]
    )

    def _choose_take(seg_label, take_num, project_dir_str, runtime_state, df_data):
        if not seg_label or not project_dir_str:
            return "Chưa chọn phân đoạn.", runtime_state, df_data
        seg_id = seg_label.split("]")[0].replace("[", "").strip()
        project_dir = Path(project_dir_str)
        success, msg = select_take_for_segment(project_dir, runtime_state, seg_id, take_num)

        # Cập nhật DataFrame
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            if str(r[1]).zfill(3) == seg_id.zfill(3):
                r[11] = f"Take {take_num}"
                break

        status_text = f"✅ {msg}" if success else f"❌ {msg}"
        return status_text, runtime_state, rows

    c["btn_use_take1"].click(
        fn=lambda lbl, p, r, df: _choose_take(lbl, 1, p, r, df),
        inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]],
        outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]]
    )
    c["btn_use_take2"].click(
        fn=lambda lbl, p, r, df: _choose_take(lbl, 2, p, r, df),
        inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]],
        outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]]
    )
    c["btn_use_take3"].click(
        fn=lambda lbl, p, r, df: _choose_take(lbl, 3, p, r, df),
        inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]],
        outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]]
    )

    # 8. Build Master Audio
    def _on_build_master(project_dir_str, segments, runtime_state, gap_rule, room_tone_file, room_tone_vol, target_lufs, true_peak):
        if not project_dir_str or not segments:
            return "⚠️ Chưa có dự án nào được mở.", None, None, gr.update(visible=False), gr.update(visible=False)

        project_dir = Path(project_dir_str)
        room_tone_p = room_tone_file.name if (room_tone_file and hasattr(room_tone_file, "name")) else None

        success, msg, wav_path, mp3_path = build_master_audio(
            project_dir=project_dir,
            segments=segments,
            project_state=runtime_state,
            gap_rule=gap_rule,
            room_tone_path=room_tone_p,
            room_tone_volume_db=float(room_tone_vol),
            target_lufs=float(target_lufs),
            true_peak_db=float(true_peak),
            sample_rate=48000
        )

        if not success:
            return f"❌ {msg}", None, None, gr.update(visible=False), gr.update(visible=False)

        wav_download_upd = gr.update(value=wav_path, visible=bool(wav_path))
        mp3_download_upd = gr.update(value=mp3_path, visible=bool(mp3_path))
        status_md = f"🎉 **{msg}**\n- File WAV (48kHz PCM): `{wav_path}`\n- File MP3 (320kbps): `{mp3_path}`"
        return status_md, wav_path, mp3_path, wav_download_upd, mp3_download_upd

    c["btn_build_master"].click(
        fn=_on_build_master,
        inputs=[
            c["story_project_dir_state"],
            c["story_segments_state"],
            c["story_runtime_state"],
            c["gap_rule_radio"],
            c["room_tone_upload"],
            c["room_tone_vol_slider"],
            c["target_lufs_num"],
            c["true_peak_num"]
        ],
        outputs=[
            c["master_status_md"],
            c["master_wav_audio"],
            c["master_mp3_audio"],
            c["master_wav_download"],
            c["master_mp3_download"]
        ]
    )

    # 9. Export Project JSON
    def _on_export(project_dir_str, raw_json, runtime_state):
        if not project_dir_str or not raw_json:
            return gr.update(visible=False)
        project_dir = Path(project_dir_str)
        export_p = export_project_json(project_dir, raw_json, runtime_state)
        return gr.update(value=export_p, visible=True)

    c["btn_export_json"].click(
        fn=_on_export,
        inputs=[c["story_project_dir_state"], c["story_raw_json_state"], c["story_runtime_state"]],
        outputs=[c["file_export_download"]]
    )
