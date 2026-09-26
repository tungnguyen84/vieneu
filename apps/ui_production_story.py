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
    sanitize_slug,
    get_all_available_voices,
    generate_character_preview_voice,
    invalidate_cache_for_speakers
)

MAX_STORY_CHARACTERS = 8

def render_production_story_ui(preset_voices_cache_getter):
    """
    Dựng giao diện cho sub-tab Production Script JSON.
    preset_voices_cache_getter: hàm trả về PRESET_VOICES_CACHE hiện tại.
    """
    gr.Markdown(
        "## 🎬 Production Storytelling Script (JSON Engine)\n"
        "Quy trình sản xuất âm thanh chuyên nghiệp cho video dài tập: Quản lý giọng nhân vật trực quan, "
        "nghe thử từng giọng, sinh độc lập từng segment, hỗ trợ multi-take, post-process tốc độ (FFmpeg), "
        "chèn khoảng lặng chuẩn xác chống double pause, và xuất Master Audio chuẩn broadcast (-14 LUFS, -1 dBTP)."
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

    # Lấy toàn bộ 25 preset voices hiện có
    initial_available_voices = get_all_available_voices()

    # 3. Characters Mapping Section (Mở mặc định, giao diện Card trực quan)
    with gr.Accordion("🎭 1. Giọng nhân vật (Character Voice Mapping)", open=True) as acc_chars:
        gr.Markdown(
            "Tự động phát hiện danh sách nhân vật từ JSON kịch bản. Bạn có thể tự do thay đổi giọng đọc và tốc độ "
            "cho bất kỳ nhân vật nào bằng dropdown bên dưới, sau đó bấm **'✓ Áp dụng giọng cho kịch bản'**."
        )

        char_groups = []
        char_headers = []
        char_id_labels = []
        char_name_boxes = []
        char_role_boxes = []
        char_voice_dds = []
        char_speed_sliders = []
        char_status_labels = []
        char_preview_btns = []
        char_preview_audios = []

        for idx in range(MAX_STORY_CHARACTERS):
            with gr.Group(visible=False) as grp:
                header_md = gr.Markdown(f"### 👤 Nhân vật #{idx+1}")
                with gr.Row():
                    c_id = gr.Textbox(label="Mã ID", interactive=False, scale=1, min_width=80)
                    c_name = gr.Textbox(label="Tên hiển thị", interactive=False, scale=2, min_width=120)
                    c_role = gr.Textbox(label="Vai trò / Ghi chú", interactive=False, scale=2, min_width=140)
                    c_status = gr.Textbox(label="Trạng thái nhận diện", interactive=False, scale=2, min_width=120)

                with gr.Row():
                    c_voice = gr.Dropdown(
                        choices=initial_available_voices,
                        label="Giọng đọc VieNeu (Chọn từ toàn bộ 25 giọng)",
                        interactive=True,
                        scale=3,
                        allow_custom_value=False
                    )
                    c_speed = gr.Slider(minimum=0.88, maximum=1.05, value=1.0, step=0.01, label="Tốc độ mặc định", scale=2)

                with gr.Row():
                    c_prev_btn = gr.Button("▶ Nghe thử giọng", size="sm", variant="secondary", scale=1)
                    c_prev_audio = gr.Audio(label="Bản nghe thử", interactive=False, scale=3)

            char_groups.append(grp)
            char_headers.append(header_md)
            char_id_labels.append(c_id)
            char_name_boxes.append(c_name)
            char_role_boxes.append(c_role)
            char_voice_dds.append(c_voice)
            char_speed_sliders.append(c_speed)
            char_status_labels.append(c_status)
            char_preview_btns.append(c_prev_btn)
            char_preview_audios.append(c_prev_audio)

        with gr.Row():
            btn_apply_char_mapping = gr.Button("✓ Áp dụng giọng cho kịch bản", size="lg", variant="primary", scale=3)
            btn_refresh_voices = gr.Button("🔄 Cập nhật giọng từ tab Clone", size="lg", variant="secondary", scale=2)
        apply_status_md = gr.Markdown("")

    # 4. Segments Table Section
    with gr.Accordion("📜 2. Bảng Phân đoạn Kịch bản (Segment Editor & Table)", open=True):
        with gr.Row():
            btn_select_all = gr.Button("Chọn tất cả", size="sm")
            btn_select_failed = gr.Button("Chọn phân đoạn lỗi", size="sm")
            btn_select_multitake = gr.Button("Chọn phân đoạn Multi-take", size="sm")
            btn_deselect_all = gr.Button("Bỏ chọn tất cả", size="sm")

        df_headers = [
            "Chọn", "ID", "Nhân vật", "Lời thoại (Text)", "Giọng áp dụng", "Ghi đè giọng (Override Voice)",
            "Sắc thái", "Tốc độ", "Nghỉ trước (s)", "Nghỉ sau (s)", "Takes", "Trạng thái", "Take đã chọn"
        ]
        story_segments_df = gr.DataFrame(
            headers=df_headers,
            datatype=["bool", "str", "str", "str", "str", "str", "str", "number", "number", "number", "number", "str", "str"],
            row_count=(1, "dynamic"),
            interactive=True,
            wrap=True
        )

    # 5. Generation Controls & Progress
    with gr.Accordion("⚡ 3. Sinh âm thanh (TTS Generation)", open=True):
        with gr.Row():
            btn_generate_story = gr.Button("⚡ Sinh TTS các phân đoạn đã chọn", variant="primary", scale=3)
            btn_generate_changed = gr.Button("⚡ Sinh các phân đoạn thiếu / thay đổi", variant="secondary", scale=2)
            btn_retry_failed = gr.Button("🔄 Sinh lại phân đoạn lỗi", variant="secondary", scale=2)
            btn_stop_story = gr.Button("⏹️ Dừng lại", variant="stop", scale=1)

        story_progress_md = gr.Markdown("**Trạng thái:** Sẵn sàng.")
        story_log_output = gr.Textbox(label="Nhật ký tiến trình (Realtime Log)", lines=5, interactive=False)

    # 6. Audio Preview & Take Selection
    with gr.Accordion("🎧 4. Nghe thử & Chọn Take (Take Preview & Selection)", open=True):
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
    with gr.Accordion("🎛️ 5. Ghép & Xuất Master Audio (Timeline & Normalization)", open=True):
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
        "char_groups": char_groups,
        "char_headers": char_headers,
        "char_id_labels": char_id_labels,
        "char_name_boxes": char_name_boxes,
        "char_role_boxes": char_role_boxes,
        "char_voice_dds": char_voice_dds,
        "char_speed_sliders": char_speed_sliders,
        "char_status_labels": char_status_labels,
        "char_preview_btns": char_preview_btns,
        "char_preview_audios": char_preview_audios,
        "btn_apply_char_mapping": btn_apply_char_mapping,
        "btn_refresh_voices": btn_refresh_voices,
        "apply_status_md": apply_status_md,
        "btn_select_all": btn_select_all,
        "btn_select_failed": btn_select_failed,
        "btn_select_multitake": btn_select_multitake,
        "btn_deselect_all": btn_deselect_all,
        "story_segments_df": story_segments_df,
        "btn_generate_story": btn_generate_story,
        "btn_generate_changed": btn_generate_changed,
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
    empty_returns = (
        "⚠️ Vui lòng chọn file JSON kịch bản.",
        gr.update(visible=False),
        *[gr.update(visible=False)] * MAX_STORY_CHARACTERS, # char_groups
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_headers
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_id
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_name
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_role
        *[gr.update(value=None)] * MAX_STORY_CHARACTERS,   # char_voice
        *[gr.update(value=1.0)] * MAX_STORY_CHARACTERS,    # char_speed
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_status
        [],
        gr.update(choices=[]),
        None, {}, {}, [], None, {}
    )

    if not json_content_or_file:
        return empty_returns

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

        # Lấy đầy đủ voices: toàn bộ built-in và user cloned voices
        all_voices = get_all_available_voices()
        if available_voices:
            existing_ids = {v[1] if isinstance(v, (tuple, list)) else v for v in all_voices}
            for item in available_voices:
                vid = item[1] if isinstance(item, (tuple, list)) else item
                if vid not in existing_ids:
                    all_voices.append(item)
                    existing_ids.add(vid)

        is_valid, err, proj_info, chars_map, warnings, stats = validate_story_json(data, all_voices)
        if not is_valid:
            return (
                f"❌ Lỗi cấu trúc JSON: {err}",
                gr.update(visible=False),
                *[gr.update(visible=False)] * MAX_STORY_CHARACTERS,
                *[gr.update(value="")] * MAX_STORY_CHARACTERS,
                *[gr.update(value="")] * MAX_STORY_CHARACTERS,
                *[gr.update(value="")] * MAX_STORY_CHARACTERS,
                *[gr.update(value="")] * MAX_STORY_CHARACTERS,
                *[gr.update(value=None)] * MAX_STORY_CHARACTERS,
                *[gr.update(value=1.0)] * MAX_STORY_CHARACTERS,
                *[gr.update(value="")] * MAX_STORY_CHARACTERS,
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

        # Cập nhật danh sách nhân vật vào các Cards
        char_list = list(chars_map.values())
        group_updates = []
        header_updates = []
        id_updates = []
        name_updates = []
        role_updates = []
        voice_updates = []
        speed_updates = []
        status_updates = []

        for i in range(MAX_STORY_CHARACTERS):
            if i < len(char_list):
                c = char_list[i]
                status_txt = "✅ Tự động khớp" if c["match_status"] == "EXACT" else ("ℹ️ Ánh xạ alias" if "ALIASED" in c["match_status"] else "⚠️ Chưa khớp (Vui lòng chọn)")
                hdr_txt = f"### 🎭 Nhân vật: **{c['char_id']}** — *{c['display_name']}* ({c['role'] or 'Nhân vật'})"
                
                group_updates.append(gr.update(visible=True))
                header_updates.append(gr.update(value=hdr_txt))
                id_updates.append(gr.update(value=c["char_id"]))
                name_updates.append(gr.update(value=c["display_name"]))
                role_updates.append(gr.update(value=c["role"] or "Không có ghi chú"))
                voice_updates.append(gr.update(choices=all_voices, value=c["voice"] or None))
                speed_updates.append(gr.update(value=c["default_speed"]))
                status_updates.append(gr.update(value=status_txt))
            else:
                group_updates.append(gr.update(visible=False))
                header_updates.append(gr.update(value=""))
                id_updates.append(gr.update(value=""))
                name_updates.append(gr.update(value=""))
                role_updates.append(gr.update(value=""))
                voice_updates.append(gr.update(choices=all_voices, value=None))
                speed_updates.append(gr.update(value=1.0))
                status_updates.append(gr.update(value=""))

        # DataFrame segments
        segments = data.get("segments", [])
        df_rows = build_segments_dataframe(segments, chars_map, runtime_state)

        # Dropdown options for preview
        seg_choices = [f"[{s.get('id', idx+1):0>3}] {s.get('speaker', '')}: {s.get('text', '')[:40]}..." for idx, s in enumerate(segments)]
        preview_dd_update = gr.update(choices=seg_choices, value=seg_choices[0] if seg_choices else None)

        return (
            info_md,
            warn_md_update,
            *group_updates,
            *header_updates,
            *id_updates,
            *name_updates,
            *role_updates,
            *voice_updates,
            *speed_updates,
            *status_updates,
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
        return empty_returns


def bind_production_story_events(components: dict, get_tts_engine_fn, get_available_voices_fn, stop_event):
    """
    Gán các sự kiện tương tác cho module Production Storytelling.
    """
    c = components

    # 1. Output components list for Import
    import_outputs = [
        c["story_project_info_md"],
        c["story_warnings_md"],
        *c["char_groups"],
        *c["char_headers"],
        *c["char_id_labels"],
        *c["char_name_boxes"],
        *c["char_role_boxes"],
        *c["char_voice_dds"],
        *c["char_speed_sliders"],
        *c["char_status_labels"],
        c["story_segments_df"],
        c["preview_seg_dropdown"],
        c["story_raw_json_state"],
        c["story_project_info_state"],
        c["story_characters_state"],
        c["story_segments_state"],
        c["story_project_dir_state"],
        c["story_runtime_state"]
    ]

    def _on_import(file):
        voices = get_available_voices_fn()
        return handle_import_json_data(file, voices)

    c["btn_import_json"].upload(
        fn=_on_import,
        inputs=[c["btn_import_json"]],
        outputs=import_outputs
    )

    # 2. Sample Pilot Load
    def _on_load_sample():
        sample_path = "tests/test_pilot_story.json"
        if not os.path.exists(sample_path):
            sample_path = str(Path(__file__).parent.parent / "tests" / "test_pilot_story.json")
        voices = get_available_voices_fn()
        return handle_import_json_data(sample_path, voices)

    c["btn_sample_pilot"].click(
        fn=_on_load_sample,
        inputs=[],
        outputs=import_outputs
    )

    # 3. Preview Voice for each character card
    for i in range(MAX_STORY_CHARACTERS):
        def _make_preview_handler(slot_idx):
            def _handler(project_dir_str, cid, cname, crole, cvoice, cspeed):
                tts = get_tts_engine_fn()
                if tts is None:
                    return None
                if not project_dir_str:
                    project_dir_str = "projects/temp_preview"
                project_dir = Path(project_dir_str)
                ok, msg, path = generate_character_preview_voice(
                    tts_engine=tts,
                    project_dir=project_dir,
                    char_id=cid or f"char_{slot_idx}",
                    display_name=cname or cid,
                    role=crole or "",
                    voice=cvoice,
                    speed=float(cspeed or 1.0)
                )
                return path if ok else None
            return _handler

        c["char_preview_btns"][i].click(
            fn=_make_preview_handler(i),
            inputs=[
                c["story_project_dir_state"],
                c["char_id_labels"][i],
                c["char_name_boxes"][i],
                c["char_role_boxes"][i],
                c["char_voice_dds"][i],
                c["char_speed_sliders"][i]
            ],
            outputs=[c["char_preview_audios"][i]]
        )

    # 4. Apply Character Voice Mapping with SELECTIVE Cache Invalidation
    apply_inputs = [
        c["story_project_dir_state"],
        c["story_characters_state"],
        c["story_segments_state"],
        c["story_runtime_state"],
        *c["char_id_labels"],
        *c["char_voice_dds"],
        *c["char_speed_sliders"]
    ]

    def _on_apply_voice_changes(project_dir_str, old_chars_map, segments, runtime_state, *args):
        if not old_chars_map or not project_dir_str:
            return gr.update(), old_chars_map, runtime_state, "⚠️ Chưa có dữ liệu kịch bản."

        project_dir = Path(project_dir_str)
        new_map = dict(old_chars_map)
        char_keys = list(new_map.keys())

        # args: MAX_STORY_CHARACTERS ids, then voices, then speeds
        n = MAX_STORY_CHARACTERS
        ids = args[:n]
        voices = args[n:2*n]
        speeds = args[2*n:3*n]

        changed_speakers = set()
        change_logs = []

        for j in range(min(len(char_keys), n)):
            cid = ids[j]
            v = voices[j]
            s = speeds[j]
            if cid in new_map:
                old_v = new_map[cid].get("voice", "")
                old_s = new_map[cid].get("default_speed", 1.0)
                if v and (v != old_v or abs(float(s or 1.0) - float(old_s or 1.0)) > 0.005):
                    changed_speakers.add(cid)
                    change_logs.append(f"**{cid}**: {old_v} → **{v}** (Speed: {s})")
                new_map[cid]["voice"] = v
                new_map[cid]["default_speed"] = float(s or 1.0)

        # Invalidate cache CHỈ cho các segment thuộc changed_speakers
        invalidated_count = 0
        if changed_speakers:
            invalidated_count = invalidate_cache_for_speakers(project_dir, runtime_state, changed_speakers)

        # Cập nhật lại DataFrame
        new_df = build_segments_dataframe(segments, new_map, runtime_state)

        if changed_speakers:
            msg = (
                f"✅ **Đã áp dụng thay đổi giọng!**\n"
                f"- Các nhân vật thay đổi: {', '.join(change_logs)}\n"
                f"- **{invalidated_count} phân đoạn** thuộc nhân vật thay đổi đã được đánh dấu cần sinh lại (`NEEDS_REGENERATE`).\n"
                f"- Toàn bộ các phân đoạn của nhân vật khác được **GIỮ NGUYÊN HOÀN TOÀN** trong Cache."
            )
        else:
            msg = "ℹ️ Không có thay đổi nào về giọng hoặc tốc độ so với cấu hình hiện tại."

        return new_df, new_map, runtime_state, msg

    c["btn_apply_char_mapping"].click(
        fn=_on_apply_voice_changes,
        inputs=apply_inputs,
        outputs=[c["story_segments_df"], c["story_characters_state"], c["story_runtime_state"], c["apply_status_md"]]
    )

    # 4b. Refresh voices list on demand (Sync from Clone tab)
    def _on_refresh_voices(*current_vals):
        tts = get_tts_engine_fn()
        voices = get_all_available_voices(tts)
        updates = []
        for i in range(MAX_STORY_CHARACTERS):
            v_val = current_vals[i] if i < len(current_vals) else None
            updates.append(gr.update(choices=voices, value=v_val))
        msg = f"✅ **Đã cập nhật danh sách giọng!** Tổng cộng **{len(voices)} giọng** khả dụng (bao gồm toàn bộ giọng mẫu và giọng bạn đã lưu từ tab Clone)."
        return [*updates, msg]

    c["btn_refresh_voices"].click(
        fn=_on_refresh_voices,
        inputs=c["char_voice_dds"],
        outputs=[*c["char_voice_dds"], c["apply_status_md"]]
    )

    # 5. Checkbox Selection Helpers
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
            r[0] = (r[11] in ("FAILED", "NEEDS_REGENERATE"))
        return rows

    def _select_multitake(df_data):
        if df_data is None:
            return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            r[0] = (int(r[10]) > 1)
        return rows

    c["btn_select_all"].click(lambda df: _toggle_all(df, True), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_deselect_all"].click(lambda df: _toggle_all(df, False), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_failed"].click(fn=_select_failed, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_multitake"].click(fn=_select_multitake, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])

    # 6. Stop Generation
    c["btn_stop_story"].click(lambda: stop_event.set(), inputs=[], outputs=[])

    # 7. Generator: TTS Generation (Sequential with Cache, Resume, Multi-take & Override)
    def _run_generation(df_data, segments, chars_map, project_dir_str, runtime_state, mode="selected"):
        """
        mode:
        - 'selected': sinh các segment có checkbox = True
        - 'changed': chỉ sinh các segment PENDING, NEEDS_REGENERATE hoặc FAILED
        - 'failed': chỉ sinh các segment FAILED
        """
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
        id_to_row_idx = {str(r[1]).zfill(3): idx for idx, r in enumerate(rows)}

        # Xác định danh sách cần sinh
        targets = []
        for seg in segments:
            seg_id = str(seg.get("id", "")).zfill(3)
            row_idx = id_to_row_idx.get(seg_id)
            if row_idx is None:
                continue
            is_selected = bool(rows[row_idx][0])
            status = rows[row_idx][11]

            # Cập nhật override voice nếu user sửa trong dataframe
            override_val = str(rows[row_idx][5] or "").strip()
            if override_val and override_val not in ("Use Character Voice", "Kế thừa (Use Character Voice)", "None"):
                seg["voice_override"] = override_val
            else:
                seg.pop("voice_override", None)

            if mode == "changed":
                if status in ("PENDING", "NEEDS_REGENERATE", "FAILED"):
                    targets.append(seg)
            elif mode == "failed":
                if status == "FAILED":
                    targets.append(seg)
            else: # "selected"
                if is_selected:
                    targets.append(seg)

        total_targets = len(targets)
        if total_targets == 0:
            yield (
                "⚠️ Không có phân đoạn nào phù hợp với chế độ đã chọn.",
                "Không có tác vụ.",
                rows,
                runtime_state
            )
            return

        log_lines = [f"🚀 Bắt đầu sinh TTS cho {total_targets} phân đoạn (Chế độ: {mode})..."]
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
            
            # Tính toán voice sau override
            voice_override = seg.get("voice_override", "")
            effective_voice = voice_override if (voice_override and voice_override != "Kế thừa (Use Character Voice)") else char_cfg.get("voice", "")
            current_hash = compute_segment_hash(seg, effective_voice, "v3turbo")

            row_idx = id_to_row_idx.get(seg_id)

            # Kiểm tra Cache
            cached_seg = runtime_state.get("segments", {}).get(seg_id)
            is_cached = False
            if cached_seg and cached_seg.get("hash") == current_hash and cached_seg.get("status") == "COMPLETED":
                sel_p = project_dir / (cached_seg.get("selected_file") or f"selected/{seg_id}.wav")
                if sel_p.exists():
                    is_cached = True

            if is_cached:
                cached_count += 1
                if row_idx is not None:
                    rows[row_idx][11] = "CACHED"
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

            progress_msg = f"⏳ Đang sinh {idx+1}/{total_targets} | Phân đoạn: **{seg_id}_{speaker}** | Giọng: **{effective_voice}** | Đã chạy: {int(elapsed)}s | Còn lại: ~{eta_sec}s"
            log_lines.append(f"🎙️ [{idx+1}/{total_targets}] Đang sinh {seg_id}_{speaker} (Giọng: {effective_voice}, Takes: {seg.get('multi_take', 1)}, Speed: {seg.get('speed', char_cfg.get('default_speed', 1.0))})...")
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
                    rows[row_idx][4] = effective_voice
                    rows[row_idx][11] = "COMPLETED"
                    rows[row_idx][12] = f"Take {seg_result.get('selected_take', 1)}"
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
                    rows[row_idx][11] = "FAILED"
                log_lines.append(f"  ❌ Phân đoạn {seg_id} Lỗi: {msg}")

            yield ("\n".join(log_lines[-10:]), progress_msg, rows, runtime_state)

        total_elapsed = time.time() - start_time
        summary_msg = f"🎉 **Hoàn thành!** Thành công: {success_count} | Lỗi: {failed_count} | Cache: {cached_count} | Tổng thời gian: {total_elapsed:.1f}s"
        log_lines.append(summary_msg)
        yield ("\n".join(log_lines[-10:]), summary_msg, rows, runtime_state)

    def _on_generate_selected(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="selected")

    def _on_generate_changed(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="changed")

    def _on_retry_failed(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="failed")

    c["btn_generate_story"].click(
        fn=_on_generate_selected,
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

    c["btn_generate_changed"].click(
        fn=_on_generate_changed,
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
        fn=_on_retry_failed,
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

    # 8. Take Preview & Selection
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
                r[12] = f"Take {take_num}"
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

    # 9. Build Master Audio
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

    # 10. Export Project JSON with UPDATED character voices and overrides
    def _on_export(project_dir_str, raw_json, chars_map, segments, runtime_state):
        if not project_dir_str or not raw_json:
            return gr.update(visible=False)
        project_dir = Path(project_dir_str)

        # Cập nhật các lựa chọn mới nhất của user vào JSON export
        export_payload = json.loads(json.dumps(raw_json))
        if "characters" in export_payload:
            for cid, ccfg in export_payload["characters"].items():
                if cid in chars_map:
                    ccfg["voice"] = chars_map[cid].get("voice", ccfg.get("voice", ""))
                    ccfg["default_speed"] = chars_map[cid].get("default_speed", ccfg.get("default_speed", 1.0))

        export_p = export_project_json(project_dir, export_payload, runtime_state)
        return gr.update(value=export_p, visible=True)

    c["btn_export_json"].click(
        fn=_on_export,
        inputs=[
            c["story_project_dir_state"],
            c["story_raw_json_state"],
            c["story_characters_state"],
            c["story_segments_state"],
            c["story_runtime_state"]
        ],
        outputs=[c["file_export_download"]]
    )
