"""
Giao diện và xử lý sự kiện cho tính năng Production Script Storytelling JSON & Music Mixing Engine ("Sau Cánh Cửa").
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
from apps.audio_director import safe_extract_zip
from apps.music_engine import (
    init_global_music_library,
    get_music_library_table_data,
    import_track_to_library,
    resolve_track_file_for_cue,
    build_clean_voice_master,
    generate_cue_sheet_from_segments,
    calculate_music_coverage,
    generate_visual_timeline_html,
    build_final_mix,
    preview_region_mix,
    DEFAULT_CATEGORY_CONFIG,
    get_slot_cards_data,
    format_slot_markdown,
    DEFAULT_SLOT_TRACKS
)

MAX_STORY_CHARACTERS = 8

def render_production_story_ui(preset_voices_cache_getter):
    """
    Dựng giao diện cho sub-tab Production Script JSON & Music Mixing Engine.
    preset_voices_cache_getter: hàm trả về PRESET_VOICES_CACHE hiện tại.
    """
    # Khởi tạo Music Library ngay khi dựng UI
    init_global_music_library()

    gr.Markdown(
        "## 🎬 Audio Production Pipeline — Series “Sau Cánh Cửa”\n"
        "Quy trình sản xuất audio hoàn chỉnh tách biệt 2 tầng độc lập: **TTS Voice Engine** và **Music Mixing Engine**.\n"
        "Thay đổi nhạc nền, âm lượng (dB), fade hay cue sheet **TUYỆT ĐỐI KHÔNG làm mất hoặc sinh lại TTS**."
    )

    # Workflow Navigator Banner
    with gr.Row():
        gr.Markdown(
            """
            <div style="background: linear-gradient(90deg, #1e293b, #0f172a); padding: 12px 16px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 8px;">
              <span style="font-weight: 700; color: #38bdf8;">WORKFLOW CHUẨN:</span>&nbsp;&nbsp;
              <span style="color: #cbd5e1;"><b>1. Tạo Voice (TTS)</b></span> <span style="color: #64748b;">➔</span>
              <span style="color: #cbd5e1;"><b>2. Kiểm tra Clean Voice Master</b></span> <span style="color: #64748b;">➔</span>
              <span style="color: #cbd5e1;"><b>3. Tạo Music Cue</b></span> <span style="color: #64748b;">➔</span>
              <span style="color: #cbd5e1;"><b>4. Preview / Chỉnh Cue Sheet</b></span> <span style="color: #64748b;">➔</span>
              <span style="color: #cbd5e1;"><b>5. Build Final Mix</b></span> <span style="color: #64748b;">➔</span>
              <span style="color: #38bdf8; font-weight: 700;">6. Xuất Master Broadcast</span>
            </div>
            """
        )

    # 1. Action Row
    with gr.Row():
        btn_import_pack_zip = gr.UploadButton("📦 Import Production Pack (.zip)", file_types=[".zip"], variant="primary")
        btn_import_json = gr.UploadButton("📂 Import Kịch bản JSON", file_types=[".json"], variant="secondary")
        btn_preset_v9_1 = gr.Button("📋 Nạp Preset V9.1 Test (93 segments)", size="sm", variant="secondary")
        btn_sample_pilot = gr.Button("📋 Nạp Pilot Mẫu (56 segments)", size="sm", variant="secondary")
        btn_export_json = gr.Button("💾 Xuất Project JSON", size="sm")
        file_export_download = gr.File(label="Tải file JSON đã xuất", visible=False)

    # 2. Project Info Banner
    story_project_info_md = gr.Markdown("*(Chưa tải kịch bản. Vui lòng bấm 'Import Production Pack (.zip)', 'Import JSON' hoặc Nạp Preset.)*")
    story_warnings_md = gr.Markdown(visible=False)

    # Lấy toàn bộ preset voices hiện có
    initial_available_voices = get_all_available_voices()

    # 3. Characters Mapping Section
    with gr.Accordion("🎭 1. Giọng nhân vật (Character Voice Mapping)", open=True) as acc_chars:
        gr.Markdown(
            "Tự động phát hiện danh sách nhân vật từ JSON kịch bản. Đối với series *Sau Cánh Cửa*, mặc định Single MC là **MINH (Binh - Thanh Bình)**.\n"
            "Bạn có thể thay đổi giọng đọc và tốc độ cho bất kỳ nhân vật nào, sau đó bấm **'✓ Áp dụng giọng cho kịch bản'**."
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
                        label="Giọng đọc VieNeu (Chọn từ toàn bộ giọng có sẵn hoặc đã clone)",
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

    # 4. Music Library Section (Persistent & Normalized)
    with gr.Accordion("🎵 2. THƯ VIỆN NHẠC NỀN", open=True) as acc_music_lib:
        gr.Markdown(
            "Thư viện 6 loại nhạc nền chuẩn cho series *Sau Cánh Cửa* (`INTRO`, `MYSTERY`, `TENSION`, `EMOTIONAL`, `REFLECTION`, `OUTRO`).\n"
            "Tất cả track được **tự động phân tích (FFprobe) và chuẩn hóa về reference loudness (-24.0 LUFS, 48kHz WAV)** "
            "giúp âm lượng kịch bản luôn cân bằng và chuyên nghiệp."
        )

        slot_cards = get_slot_cards_data()
        slot_keys = ["INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"]
        slot_info_components = {}
        slot_audio_components = {}
        slot_file_components = {}
        slot_replace_btns = {}
        slot_status_components = {}

        # 6 Slot trực tiếp: 2 hàng x 3 cột (Mỗi slot có [▶ Preview] và [🔄 Replace] riêng biệt)
        with gr.Row():
            for sk in slot_keys[:3]:
                sdata = slot_cards[sk]
                with gr.Column(scale=1):
                    with gr.Group():
                        gr.Markdown(f"### 🎵 {sk} — {sdata['display_name']}")
                        s_info = gr.Markdown(format_slot_markdown(sdata))
                        s_audio = gr.Audio(value=sdata["audio_preview"], label=f"▶ Preview {sk}", interactive=False)
                        with gr.Row():
                            s_file = gr.File(label=f"Nạp Suno mới ({sk})", scale=2)
                            s_btn = gr.Button(f"🔄 Thay thế", variant="primary", scale=1)
                        s_status = gr.Markdown("")
                        slot_info_components[sk] = s_info
                        slot_audio_components[sk] = s_audio
                        slot_file_components[sk] = s_file
                        slot_replace_btns[sk] = s_btn
                        slot_status_components[sk] = s_status

        with gr.Row():
            for sk in slot_keys[3:]:
                sdata = slot_cards[sk]
                with gr.Column(scale=1):
                    with gr.Group():
                        gr.Markdown(f"### 🎵 {sk} — {sdata['display_name']}")
                        s_info = gr.Markdown(format_slot_markdown(sdata))
                        s_audio = gr.Audio(value=sdata["audio_preview"], label=f"▶ Preview {sk}", interactive=False)
                        with gr.Row():
                            s_file = gr.File(label=f"Nạp Suno mới ({sk})", scale=2)
                            s_btn = gr.Button(f"🔄 Thay thế", variant="primary", scale=1)
                        s_status = gr.Markdown("")
                        slot_info_components[sk] = s_info
                        slot_audio_components[sk] = s_audio
                        slot_file_components[sk] = s_file
                        slot_replace_btns[sk] = s_btn
                        slot_status_components[sk] = s_status

        # Quick Replace Panel
        with gr.Group():
            gr.Markdown("#### ⚡ Hoặc chọn nhanh từ danh sách (Hỗ trợ M4A Suno, MP3, WAV, FLAC):")
            with gr.Row():
                quick_slot_dd = gr.Dropdown(
                    label="1. Chọn Slot cần thay nhạc",
                    choices=slot_keys,
                    value="INTRO",
                    scale=2
                )
                quick_file_upload = gr.File(
                    label="2. Chọn / Kéo thả file âm thanh (M4A Suno, MP3, WAV, FLAC)",
                    scale=4
                )
                btn_replace_slot_track = gr.Button("🔄 Cập nhật Slot & Chuẩn hóa (-24 LUFS)", variant="primary", scale=2)
            replace_slot_status_md = gr.Markdown("")

        # Advanced Settings Accordion
        with gr.Accordion("⚙️ Cài đặt nâng cao (Chi tiết & Bảng mã Track)", open=False):
            music_lib_headers = ["Danh mục", "Tên hiển thị", "Mã Track", "File âm thanh gốc", "Thời lượng", "Integrated LUFS", "True Peak", "Default Level", "Trạng thái"]
            initial_lib_rows = get_music_library_table_data()
            music_library_df = gr.DataFrame(
                value=initial_lib_rows,
                headers=music_lib_headers,
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str"],
                row_count=(6, "dynamic"),
                interactive=False
            )
            with gr.Row():
                upload_cat_dd = gr.Dropdown(
                    label="Danh mục",
                    choices=slot_keys,
                    value="MYSTERY",
                    scale=2
                )
                upload_track_id_box = gr.Textbox(label="Mã Track ID tùy biến (Tùy chọn, vd: SCC_MYSTERY_02)", value="", scale=2)
                upload_file_btn = gr.File(label="Upload file âm thanh tùy biến", scale=3)
            btn_execute_import_track = gr.Button("📥 Nạp Track tùy biến vào Thư viện", variant="secondary")
            import_track_status_md = gr.Markdown("")

    # 5. Segments Table Section
    with gr.Accordion("📜 3. Bảng Phân đoạn Kịch bản (Segment Editor & Table)", open=True):
        with gr.Row():
            btn_select_all = gr.Button("Chọn tất cả", size="sm")
            btn_select_failed = gr.Button("Chọn phân đoạn lỗi", size="sm")
            btn_select_multitake = gr.Button("Chọn phân đoạn Multi-take", size="sm")
            btn_deselect_all = gr.Button("Bỏ chọn tất cả", size="sm")

        with gr.Row():
            quick_cue_dropdown = gr.Dropdown(
                label="Gán nhanh Music Cue cho các phân đoạn đã chọn",
                choices=["DRY", "INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"],
                value="MYSTERY",
                interactive=True,
                scale=3
            )
            btn_apply_quick_cue = gr.Button("🎵 Gán Music Cue cho các dòng đã chọn", size="sm", variant="secondary", scale=2)

        df_headers = [
            "Chọn", "ID", "Nhân vật", "Lời thoại (Text)", "Giọng áp dụng", "Ghi đè giọng (Override Voice)",
            "Sắc thái", "Tốc độ", "Nghỉ trước (s)", "Nghỉ sau (s)",
            "Music Cue", "Music (dB)", "Fade In (s)", "Fade Out (s)", "Ducking (dB)", "Room Tone (dB)", "Importance",
            "Takes", "Trạng thái", "Take đã chọn"
        ]
        story_segments_df = gr.DataFrame(
            headers=df_headers,
            datatype=[
                "bool", "str", "str", "str", "str", "str",
                "str", "number", "number", "number",
                "str", "number", "number", "number", "number", "number", "str",
                "number", "str", "str"
            ],
            row_count=(1, "dynamic"),
            interactive=True
        )

    # 6. Generation Controls & Progress
    with gr.Accordion("⚡ 4. Sinh âm thanh (TTS Generation)", open=True):
        with gr.Row():
            btn_generate_story = gr.Button("⚡ Sinh TTS các phân đoạn đã chọn", variant="primary", scale=3)
            btn_generate_changed = gr.Button("⚡ Sinh các phân đoạn thiếu / thay đổi", variant="secondary", scale=2)
            btn_retry_failed = gr.Button("🔄 Sinh lại phân đoạn lỗi", variant="secondary", scale=2)
            btn_stop_story = gr.Button("⏹️ Dừng lại", variant="stop", scale=1)

        story_progress_md = gr.Markdown("**Trạng thái:** Sẵn sàng.")
        story_log_output = gr.Textbox(label="Nhật ký tiến trình (Realtime Log)", lines=5, interactive=False)

    # 7. Audio Preview & Take Selection
    with gr.Accordion("🎧 5. Nghe thử & Chọn Take (Take Preview & Selection)", open=True):
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

    # 8. Clean Voice Master Section
    with gr.Accordion("🎙️ 6. Clean Voice Master (Lời thoại sạch)", open=True):
        gr.Markdown(
            "Bản master lời thoại sạch **bắt buộc được lưu giữ độc lập** (`voice_master.wav`).\n"
            "Chỉ gồm: Giọng MC và khoảng lặng chuẩn xác theo JSON. **Tuyệt đối không có room tone, white noise hay nhạc nền**."
        )
        with gr.Row():
            gap_rule_radio = gr.Radio(
                choices=[("Khuyến nghị: max(pause_after, next_pause_before)", "max"), ("Cộng dồn: pause_after + next_pause_before", "sum")],
                value="max",
                label="Quy tắc khoảng nghỉ giữa các câu"
            )
            btn_build_voice_master = gr.Button("🎙 Build Clean Voice Master", variant="primary", scale=2)

        voice_master_status_md = gr.Markdown("")
        with gr.Row():
            voice_master_audio = gr.Audio(label="Clean Voice Master (48kHz 24-bit PCM)", interactive=False)
            voice_master_download = gr.File(label="Tải file voice_master.wav", visible=False)

    # 9. Music Cue Engine & Cue Sheet Editor
    with gr.Accordion("🎼 7. Phân đoạn Nhạc & Cue Sheet (Music Cue Engine)", open=True):
        gr.Markdown(
            "Tự động gom các phân đoạn cùng cue thành **Continuous Music Regions** (không restart nhạc). "
            "Áp dụng **Major Reveal Safety Rule** để fade out nhạc trước câu cao trào và giữ im lặng tuyệt đối."
        )

        with gr.Row():
            pre_reveal_slider = gr.Slider(minimum=0.5, maximum=5.0, value=2.0, step=0.1, label="Pre-reveal Clearance (Fade out trước câu Reveal)", scale=1)
            post_reveal_slider = gr.Slider(minimum=0.5, maximum=5.0, value=2.5, step=0.1, label="Post-reveal Clearance (Trễ hồi nhạc sau Reveal)", scale=1)
            merge_gap_slider = gr.Slider(minimum=0.5, maximum=6.0, value=3.0, step=0.1, label="Gộp cue nếu khoảng cách giữa các câu < (giây)", scale=1)
            chk_gentle_ducking = gr.Checkbox(label="Bật Gentle Ducking (-2.5 dB khi MC nói)", value=False, scale=1)

        with gr.Row():
            intro_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-31.0, step=0.5, label="INTRO Level (dB)")
            mystery_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-35.0, step=0.5, label="MYSTERY Level (dB)")
            tension_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-36.0, step=0.5, label="TENSION Level (dB)")
            emotional_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-36.0, step=0.5, label="EMOTIONAL Level (dB)")
            reflection_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-35.0, step=0.5, label="REFLECTION Level (dB)")
            outro_db_slider = gr.Slider(minimum=-50.0, maximum=-20.0, value=-30.0, step=0.5, label="OUTRO Level (dB)")

        with gr.Row():
            btn_build_cues = gr.Button("🎵 Analyze / Build Music Cues", variant="primary", scale=2)

        # Coverage Banner
        coverage_metrics_md = gr.Markdown("*(Chưa phân tích Cue Sheet. Vui lòng bấm 'Analyze / Build Music Cues'.)*")

        # Visual Timeline Preview
        visual_timeline_html = gr.HTML("<div style='color: #9ca3af;'>Timeline sẽ hiển thị tại đây sau khi tạo Cue Sheet.</div>")

        # Cue Sheet Table
        gr.Markdown("#### 📋 Bảng Cue Sheet (Có thể trực tiếp chỉnh sửa Start, End, Level, Fades bên dưới)")
        cue_sheet_headers = ["Start (s)", "End (s)", "Thời lượng (s)", "Cue / Thể loại", "Mã Track", "Âm lượng (dB)", "Fade In (s)", "Fade Out (s)", "Ghi chú / Nguồn"]
        cue_sheet_df = gr.DataFrame(
            headers=cue_sheet_headers,
            datatype=["number", "number", "number", "str", "str", "number", "number", "number", "str"],
            row_count=(1, "dynamic"),
            interactive=True
        )

        # Region Preview Row
        with gr.Row():
            preview_region_dd = gr.Dropdown(label="Chọn phân đoạn nhạc để nghe thử", choices=[], interactive=True, scale=3)
            btn_preview_region = gr.Button("▶ Nghe thử Phân đoạn Nhạc (10s trước + sau)", size="sm", variant="secondary", scale=2)
            audio_region_preview = gr.Audio(label="Bản nghe thử phân đoạn nhạc + lời", interactive=False, scale=3)

    # 10. Final Mix & Mastering Section
    with gr.Accordion("🎛️ 8. Final Mix & Mastering (-14 LUFS, -1 dBTP)", open=True):
        gr.Markdown(
            "Hòa âm `voice_master.wav` với `music_mix.wav` và chuẩn hóa 2-pass sang chuẩn broadcast (-14 LUFS, -1 dBTP).\n"
            "Bấm **'🔁 Rebuild Final Mix'** để cập nhật nhanh bất kỳ thay đổi nào về nhạc **mà không chạy lại TTS**."
        )

        with gr.Row():
            target_lufs_num = gr.Number(value=-14.0, label="Target Integrated LUFS (-14 LUFS)")
            true_peak_num = gr.Number(value=-1.0, label="True Peak (-1.0 dBTP)")
            btn_build_final_mix = gr.Button("🎚 Build Final Mix", variant="primary", scale=2)
            btn_rebuild_final_mix = gr.Button("🔁 Rebuild Final Mix (Cực nhanh)", variant="secondary", scale=2)

        final_mix_status_md = gr.Markdown("")

        with gr.Row():
            final_mix_wav_audio = gr.Audio(label="Final Mix WAV (48kHz 24-bit PCM)", interactive=False)
            final_mix_mp3_audio = gr.Audio(label="Final Mix MP3 (320kbps)", interactive=False)
            music_mix_audio = gr.Audio(label="Kênh Nhạc Nền Riêng (Music Mix)", interactive=False)

        with gr.Row():
            final_wav_download = gr.File(label="Tải final_mix.wav", visible=False)
            final_mp3_download = gr.File(label="Tải final_mix.mp3", visible=False)
            music_mix_download = gr.File(label="Tải music_mix.wav", visible=False)
            cue_sheet_download = gr.File(label="Tải cue_sheet.json", visible=False)
            mix_report_download = gr.File(label="Tải mix_report.json", visible=False)

        # A/B Music Comparison
        with gr.Accordion("🎧 So sánh A/B (A: Voice Sạch ⟷ B: Bản Hòa Âm)", open=False):
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("#### 🅰️ Kênh Lời Thoại Sạch (Clean Voice Master)")
                    ab_voice_audio = gr.Audio(label="A: Clean Voice Only", interactive=False)
                with gr.Column(scale=1):
                    gr.Markdown("#### 🅱️ Bản Hòa Âm Hoàn Chỉnh (Final Mix)")
                    ab_mix_audio = gr.Audio(label="B: Voice + Music Mix", interactive=False)

    # 🎬 3. SẢN XUẤT HÌNH ẢNH & VIDEO (Google Flow + Nano Banana Pro + Veo 3)
    with gr.Accordion("🎬 3. SẢN XUẤT HÌNH ẢNH & VIDEO (Visual Engine Pipeline)", open=True):
        gr.Markdown(
            "Tự động chuyển đổi timeline lời thoại và âm thanh sang **Chuỗi hình ảnh điện ảnh (Nano Banana Pro)** "
            "và **Clip video chuyển động (Veo 3)**, sau đó ghép với `final_mix.wav` thành bản phim hoàn chỉnh 1080p."
        )

        with gr.Row():
            with gr.Column(scale=1):
                visual_flow_status_md = gr.Markdown(
                    "### 🌐 Trạng thái Google Flow\n"
                    "- **Kết nối:** ● Đang kết nối (`ws://127.0.0.1:9223`)\n"
                    "- **Extension:** Đang tải...\n"
                    "- **Flow Session:** Sẵn sàng"
                )
                btn_refresh_flow_conn = gr.Button("🔄 Kiểm tra kết nối Flow", size="sm")
                flow_project_id_txt = gr.Textbox(
                    label="🎯 Flow Project ID",
                    value="b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e",
                    info="URL: https://flow.google.com/project/b36fca1c-4d91-49eb-a7f7-5c3b7dd1598e"
                )
            with gr.Column(scale=1):
                visual_progress_md = gr.Markdown(
                    "### 📊 Tiến độ Visual Episode\n"
                    "- **Số cảnh (Scenes):** 0\n"
                    "- **Keyframe Banana Pro:** 0/0\n"
                    "- **Clip Omni Flash Video:** 0/0\n"
                    "- **Xuất bản Final MP4:** Chưa sẵn sàng"
                )

        with gr.Row():
            with gr.Column(scale=1):
                image_model_txt = gr.Textbox(
                    label="🎨 Image Model",
                    value="Banana Pro",
                    interactive=False
                )
            with gr.Column(scale=1):
                video_model_dd = gr.Dropdown(
                    label="🎥 Video Model",
                    choices=["Omni 1.1 Flash", "Veo 3.1"],
                    value="Omni 1.1 Flash",
                    interactive=True
                )
            with gr.Column(scale=2):
                video_duration_radio = gr.Radio(
                    label="⏱ Video Duration (Omni 1.1 Flash)",
                    choices=["4s", "6s", "8s", "10s"],
                    value="8s",
                    interactive=True,
                    info="Mặc định: 8s. Hỗ trợ chuẩn: 4s, 6s, 8s, 10s"
                )

        with gr.Row():
            btn_analyze_visual = gr.Button("🔍 1. Phân tích Visual & Lập Scene Plan", variant="primary", scale=2)
            btn_gen_all_images = gr.Button("🎨 2. Tạo toàn bộ Keyframe (Banana Pro)", variant="primary", scale=2)
            btn_gen_veo_videos = gr.Button("🎥 3. Tạo Video Chuyển động (Omni 1.1 Flash)", variant="secondary", scale=2)
            btn_retry_failed_visual = gr.Button("🔄 Retry cảnh lỗi", variant="secondary", scale=1)
            btn_render_final_video = gr.Button("🎬 4. Ghép Final Episode MP4", variant="stop", scale=2)

        auto_production_chk = gr.Checkbox(
            label="⚡ Auto Production (Tự động chạy toàn bộ chuỗi: Phân tích -> Keyframe -> Video -> Render MP4)",
            value=False
        )
        visual_status_log_md = gr.Markdown("")

        # 👥 Thư viện Nhân vật & Bối cảnh (Character & Location Library)
        with gr.Accordion("👥 Thư viện Nhân vật & Bối cảnh (Character & Location Library)", open=False):
            with gr.Tabs():
                with gr.Tab("🎭 Nhân vật (Characters)"):
                    char_lib_table = gr.Dataframe(
                        headers=["Char ID", "Tên", "Vai trò", "Reference ID", "Flow Status", "QC Status", "Wardrobes", "Identity Link"],
                        datatype=["str", "str", "str", "str", "str", "str", "str", "str"],
                        interactive=False
                    )
                    btn_refresh_char_lib = gr.Button("🔄 Tải lại Thư viện Nhân vật", size="sm")

                    with gr.Accordion("🔍 Xem & Phê duyệt Reference Nhân vật (Character Approval Gate)", open=True):
                        with gr.Row():
                            char_select_dd = gr.Dropdown(
                                label="Chọn Nhân vật kiểm duyệt",
                                choices=["LAN_ADULT", "HUNG", "UNCLE", "LAN_YOUNG"],
                                value="LAN_ADULT",
                                interactive=True,
                                scale=3
                            )
                            btn_load_char_ref = gr.Button("👁 Nạp thông tin", scale=1)

                        char_card_header_md = gr.Markdown("### 🎭 LAN_ADULT")

                        with gr.Row():
                            with gr.Column(scale=1):
                                char_ref_portrait_img = gr.Image(label="Reference Preview", interactive=False)
                                char_ref_status_md = gr.Markdown(
                                    "**Status:** `NOT_GENERATED`\n\n"
                                    "**Flow:** `LOCAL_ONLY`"
                                )
                            with gr.Column(scale=2):
                                char_ref_details_md = gr.Markdown("**Thông tin nhân vật:** Bấm 'Nạp thông tin' để xem chi tiết.")

                                # Credit confirmation box (hidden by default)
                                with gr.Group(visible=False) as char_ref_confirm_box:
                                    char_ref_confirm_msg_md = gr.Markdown(
                                        "### ⚠️ Xác nhận Tạo ảnh Reference\n"
                                        "Tạo ảnh reference cho **LAN_ADULT**\n\n"
                                        "- **Model:** Nano Banana Pro\n"
                                        "- **Requests:** 1\n"
                                    )
                                    with gr.Row():
                                        btn_cancel_char_gen = gr.Button("❌ Hủy", size="sm")
                                        btn_confirm_char_gen = gr.Button("🚀 Tạo ảnh", variant="primary", size="sm")

                                char_ref_type_dd = gr.Radio(
                                    choices=["Character Bible (16:9)", "Chân dung đơn (Portrait 3:4)"],
                                    value="Character Bible (16:9)",
                                    label="📐 Định dạng Reference",
                                    interactive=True
                                )

                                with gr.Row():
                                    btn_gen_char_ref = gr.Button("✨ Tạo ảnh Character Bible", variant="primary")
                                    btn_regen_char_ref = gr.Button("🔄 Tạo lại", variant="secondary")
                                    btn_toggle_upload = gr.Button("📁 Upload ảnh riêng", variant="secondary")

                                upload_char_ref_file = gr.File(
                                    label="Chọn tệp ảnh chân dung nhân vật từ máy tính (PNG/JPG)",
                                    file_types=[".png", ".jpg", ".jpeg"],
                                    visible=False
                                )

                                with gr.Row():
                                    btn_approve_char_ref = gr.Button("✅ Phê duyệt", variant="primary")
                                    btn_reject_char_ref = gr.Button("❌ Từ chối", variant="stop")

                                char_ref_action_status_md = gr.Markdown("")
                with gr.Tab("📍 Bối cảnh (Locations)"):
                    loc_lib_table = gr.Dataframe(
                        headers=["Location ID", "Tên bối cảnh", "Tính chất", "Mô tả", "Visual Style", "Ánh sáng mặc định"],
                        datatype=["str", "str", "str", "str", "str", "str"],
                        interactive=False
                    )
                    btn_refresh_loc_lib = gr.Button("🔄 Tải lại Thư viện Bối cảnh", size="sm")

        # Visual Scenes Table
        with gr.Accordion("📋 Danh sách Visual Scenes (Scene Plan)", open=True):
            visual_scenes_table = gr.Dataframe(
                headers=["Scene", "Timeline", "Story Beat", "Characters", "Location", "Type", "Motion", "Omni Duration", "Importance", "Status"],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str", "str"],
                interactive=False
            )

        # 🔍 Chi tiết Scene & Chỉnh sửa Prompt
        with gr.Accordion("🔍 Chi tiết Scene & Chỉnh sửa Prompt (Phase 2 Inspector)", open=False):
            with gr.Row():
                scene_select_dd = gr.Dropdown(label="Chọn Scene để xem / chỉnh sửa", choices=[], interactive=True, scale=3)
                btn_refresh_scene_details = gr.Button("👁 Xem chi tiết", scale=1)
            with gr.Row():
                scene_edit_beat = gr.Textbox(label="Story Beat", interactive=True, scale=2)
                scene_edit_importance = gr.Dropdown(label="Importance", choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"], interactive=True, scale=1)
                scene_edit_type = gr.Dropdown(label="Visual Type", choices=["BANANA_IMAGE", "OMNI_FLASH_I2V"], interactive=True, scale=1)
                scene_edit_duration = gr.Dropdown(label="Omni Duration", choices=["-", "4s", "6s", "8s", "10s"], interactive=True, scale=1)
            with gr.Row():
                scene_edit_chars = gr.Textbox(label="Characters (cách nhau bởi dấu phẩy)", interactive=True, scale=2)
                scene_edit_location = gr.Textbox(label="Location ID", interactive=True, scale=2)
            with gr.Row():
                scene_edit_image_prompt = gr.Textbox(label="🎨 Image Prompt (Banana Pro)", lines=4, interactive=True)
            with gr.Row():
                scene_edit_motion_prompt = gr.Textbox(label="🎥 Video Motion Prompt (Omni 1.1 Flash)", lines=3, interactive=True)
            btn_save_scene_edit = gr.Button("💾 Lưu chỉnh sửa Scene này vào Plan", variant="primary")
            scene_edit_status_md = gr.Markdown("")

        # 🎯 Phase 3: Pilot Generation & Review Center
        with gr.Accordion("🎯 Phase 3: Pilot Generation & Review Center (8 Pilot Scenes)", open=True):
            gr.Markdown(
                "### 🛡️ Pilot Quality Gatekeeper (8 Scenes: SC_001, SC_005, SC_011, SC_025, SC_030, SC_035, SC_041, SC_045)\n"
                "Quy trình bắt buộc trước khi mở khóa tạo hàng loạt (Generate All 45 scenes):\n"
                "1. Duyệt đủ 4/4 Reference Portraits của nhân vật (LAN_ADULT, HUNG, UNCLE, LAN_YOUNG).\n"
                "2. Sinh và duyệt đạt chuẩn 8/8 Pilot Keyframes (Banana Pro).\n"
                "3. Sinh và duyệt đạt chuẩn các Pilot Videos theo Visual Plan (Omni 1.1 Flash: SC_001, SC_005, SC_011, SC_030).\n"
                "4. Không còn lỗi nghiêm trọng về character identity, continuity hay chronology."
            )
            with gr.Row():
                btn_calc_pilot_cost = gr.Button("💰 1. Kiểm tra chi phí Pilot Credits", variant="secondary")
                btn_gen_pilot_keyframes = gr.Button("🎨 2. Sinh 8 Pilot Keyframes (Banana Pro)", variant="primary")
                btn_gen_pilot_videos = gr.Button("🎥 3. Sinh Pilot Videos (Omni 1.1 Flash)", variant="primary")
                btn_refresh_pilot_status = gr.Button("🔄 Cập nhật tiến độ Pilot", size="sm")

            pilot_cost_info_md = gr.Markdown("*(Bấm 'Kiểm tra chi phí' để tính toán trước khi bấm sinh hình/video)*")
            pilot_gate_status_md = gr.Markdown("### 🔒 Trạng thái Khóa: Đang khóa Generate All\n- Cần duyệt đủ 4 nhân vật và các pilot keyframes/videos.")

            with gr.Row():
                pilot_scene_select_dd = gr.Dropdown(
                    label="Chọn Pilot Scene để duyệt (QC Review)",
                    choices=["SC_001", "SC_005", "SC_011", "SC_025", "SC_030", "SC_035", "SC_041", "SC_045"],
                    value="SC_001",
                    interactive=True,
                    scale=2
                )
                btn_load_pilot_scene = gr.Button("👁 Nạp Media Scene", scale=1)

            pilot_scene_metadata_md = gr.Markdown("")

            with gr.Row():
                with gr.Column(scale=1):
                    pilot_keyframe_img = gr.Image(label="🖼 Keyframe Image (Banana Pro)", interactive=False)
                    pilot_keyframe_status_md = gr.Markdown("**Trạng thái Keyframe:** Chưa có")
                    with gr.Row():
                        btn_approve_pilot_keyframe = gr.Button("✅ Phê duyệt Keyframe", variant="primary", size="sm")
                        btn_reject_pilot_keyframe = gr.Button("❌ Từ chối Keyframe", variant="stop", size="sm")
                with gr.Column(scale=1):
                    pilot_video_player = gr.Video(label="🎬 Video Clip (Omni 1.1 Flash)", interactive=False)
                    pilot_video_status_md = gr.Markdown("**Trạng thái Video:** Chưa có")
                    with gr.Row():
                        btn_approve_pilot_video = gr.Button("✅ Phê duyệt Video", variant="primary", size="sm")
                        btn_reject_pilot_video = gr.Button("❌ Từ chối Video", variant="stop", size="sm")

            with gr.Row():
                pilot_review_notes_txt = gr.Textbox(label="Ghi chú Semantic QC Review", placeholder="Nhập ghi chú đánh giá về tính nhất quán, ánh sáng, chuyển động...", scale=3)
                btn_save_pilot_review = gr.Button("💾 Lưu Ghi chú Review", scale=1)

        # 📂 Antigravity — Manual Visual Import & Auto Assemble Mode
        with gr.Accordion("🎬 ANTIGRAVITY — MANUAL VISUAL IMPORT + AUTO ASSEMBLE", open=True):
            gr.Markdown(
                "### 🎬 Chế độ Nhập Visual Thủ công & Tự Động Lắp Ráp (Manual Visual Mode)\n"
                "- Nạp `visual_manifest_v9_3.json`, quét các thư mục `images/` và `videos/` theo mã scene (`SC_XXX`).\n"
                "- **Ưu tiên:** Video > Image. Không gọi FlowKit / Banana / Omni. Không làm thay đổi `visual_plan.json`, source script hay audio master.\n"
                "- **Quy chuẩn kỹ thuật:** Image (Ken Burns nhẹ nhàng), Video (scale/crop 1080p, trim/freeze frame), khử toàn bộ audio gốc của video và mux trực tiếp với `final_mix.wav`."
            )
            with gr.Row():
                manual_manifest_path_txt = gr.Textbox(
                    label="Đường dẫn file Manifest",
                    value="projects/sau_canh_cua_ep01_v9_3_manual_visual/visual_manifest_v9_3.json",
                    scale=3
                )
                btn_load_manual_manifest = gr.Button("📂 Nạp Manifest", variant="secondary", scale=1)

            with gr.Row():
                manual_images_dir_txt = gr.Textbox(
                    label="Thư mục Images",
                    value="projects/sau_canh_cua_ep01_v9_3_manual_visual/visual/images",
                    scale=2
                )
                manual_videos_dir_txt = gr.Textbox(
                    label="Thư mục Videos",
                    value="projects/sau_canh_cua_ep01_v9_3_manual_visual/visual/videos",
                    scale=2
                )

            with gr.Row():
                btn_manual_scan_assets = gr.Button("🔍 Scan Assets", variant="primary", scale=1)
                btn_manual_validate = gr.Button("🛡️ Validate", variant="secondary", scale=1)
                btn_manual_preview = gr.Button("👁️ Preview", variant="secondary", scale=1)
                btn_manual_auto_assemble = gr.Button("🚀 Auto Assemble", variant="stop", scale=2)

            manual_summary_report_md = gr.Markdown("*(Bấm 'Scan Assets' để quét tài nguyên hình ảnh và video)*")

            # Table Scene / Image / Video / Chosen / QC / Overlay / Status
            manual_manifest_df = gr.Dataframe(
                headers=["Scene", "Image", "Video", "Chosen", "QC", "Overlay", "Status"],
                datatype=["str", "str", "str", "str", "str", "str", "str"],
                interactive=False,
                label="Bảng Trạng Thái Tài Nguyên Cảnh (Manual Visual Manifest)"
            )

            # Duplicate resolution box
            with gr.Group(visible=False) as manual_duplicate_box:
                gr.Markdown("#### ⚠️ Giải quyết file trùng lặp (Duplicate Resolution)")
                with gr.Row():
                    manual_dup_scene_dd = gr.Dropdown(label="Chọn Scene trùng lặp", choices=[], scale=2)
                    manual_dup_file_dd = gr.Dropdown(label="Chọn File tài nguyên", choices=[], scale=3)
                    btn_manual_apply_dup = gr.Button("✅ Chọn File Này", variant="primary", scale=1)

            # Preview Section
            with gr.Group(visible=False) as manual_preview_box:
                gr.Markdown("#### 👁️ Xem trước Cảnh (Scene Preview)")
                with gr.Row():
                    manual_preview_scene_dd = gr.Dropdown(
                        label="Chọn Scene xem trước",
                        choices=[f"SC_{i:03d}" for i in range(1, 46)],
                        value="SC_001",
                        scale=2
                    )
                    btn_load_scene_preview = gr.Button("👁️ Tải Xem Trước", scale=1)
                with gr.Row():
                    manual_preview_image = gr.Image(label="Hình ảnh đã chọn", interactive=False, visible=False)
                    manual_preview_video = gr.Video(label="Video đã chọn", interactive=False, visible=False)
                manual_preview_overlay_md = gr.Markdown("")

        # Video Player
        with gr.Row():
            final_episode_video = gr.Video(label="🎬 Bản Phim Hoàn Chỉnh (Final Episode MP4)", interactive=False)
            final_episode_file_download = gr.File(label="Tải file final_episode.mp4", visible=False)

    # State stores
    manual_manifest_state = gr.State(None)
    story_raw_json_state = gr.State(None)
    story_project_info_state = gr.State({})
    story_characters_state = gr.State({})
    story_segments_state = gr.State([])
    story_project_dir_state = gr.State(None)
    story_runtime_state = gr.State({})
    story_cue_sheet_state = gr.State([])
    story_timeline_events_state = gr.State([])
    story_voice_master_path_state = gr.State(None)
    story_visual_scenes_state = gr.State([])
    story_visual_queue_state = gr.State({})

    components = {
        "btn_import_pack_zip": btn_import_pack_zip,
        "btn_import_json": btn_import_json,
        "btn_preset_v9_1": btn_preset_v9_1,
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
        "music_library_df": music_library_df,
        "slot_info_components": slot_info_components,
        "slot_audio_components": slot_audio_components,
        "slot_file_components": slot_file_components,
        "slot_replace_btns": slot_replace_btns,
        "slot_status_components": slot_status_components,
        "quick_slot_dd": quick_slot_dd,
        "quick_file_upload": quick_file_upload,
        "btn_replace_slot_track": btn_replace_slot_track,
        "replace_slot_status_md": replace_slot_status_md,
        "upload_cat_dd": upload_cat_dd,
        "upload_track_id_box": upload_track_id_box,
        "upload_file_btn": upload_file_btn,
        "btn_execute_import_track": btn_execute_import_track,
        "import_track_status_md": import_track_status_md,
        "quick_cue_dropdown": quick_cue_dropdown,
        "btn_apply_quick_cue": btn_apply_quick_cue,
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
        "btn_build_voice_master": btn_build_voice_master,
        "voice_master_status_md": voice_master_status_md,
        "voice_master_audio": voice_master_audio,
        "voice_master_download": voice_master_download,
        "pre_reveal_slider": pre_reveal_slider,
        "post_reveal_slider": post_reveal_slider,
        "merge_gap_slider": merge_gap_slider,
        "chk_gentle_ducking": chk_gentle_ducking,
        "intro_db_slider": intro_db_slider,
        "mystery_db_slider": mystery_db_slider,
        "tension_db_slider": tension_db_slider,
        "emotional_db_slider": emotional_db_slider,
        "reflection_db_slider": reflection_db_slider,
        "outro_db_slider": outro_db_slider,
        "btn_build_cues": btn_build_cues,
        "coverage_metrics_md": coverage_metrics_md,
        "visual_timeline_html": visual_timeline_html,
        "cue_sheet_df": cue_sheet_df,
        "preview_region_dd": preview_region_dd,
        "btn_preview_region": btn_preview_region,
        "audio_region_preview": audio_region_preview,
        "target_lufs_num": target_lufs_num,
        "true_peak_num": true_peak_num,
        "btn_build_final_mix": btn_build_final_mix,
        "btn_rebuild_final_mix": btn_rebuild_final_mix,
        "final_mix_status_md": final_mix_status_md,
        "final_mix_wav_audio": final_mix_wav_audio,
        "final_mix_mp3_audio": final_mix_mp3_audio,
        "music_mix_audio": music_mix_audio,
        "final_wav_download": final_wav_download,
        "final_mp3_download": final_mp3_download,
        "music_mix_download": music_mix_download,
        "cue_sheet_download": cue_sheet_download,
        "mix_report_download": mix_report_download,
        "ab_voice_audio": ab_voice_audio,
        "ab_mix_audio": ab_mix_audio,
        "story_raw_json_state": story_raw_json_state,
        "story_project_info_state": story_project_info_state,
        "story_characters_state": story_characters_state,
        "story_segments_state": story_segments_state,
        "story_project_dir_state": story_project_dir_state,
        "story_runtime_state": story_runtime_state,
        "story_cue_sheet_state": story_cue_sheet_state,
        "story_timeline_events_state": story_timeline_events_state,
        "story_voice_master_path_state": story_voice_master_path_state,
        "story_visual_scenes_state": story_visual_scenes_state,
        "story_visual_queue_state": story_visual_queue_state,
        "visual_flow_status_md": visual_flow_status_md,
        "btn_refresh_flow_conn": btn_refresh_flow_conn,
        "flow_project_id_txt": flow_project_id_txt,
        "image_model_txt": image_model_txt,
        "video_model_dd": video_model_dd,
        "video_duration_radio": video_duration_radio,
        "visual_progress_md": visual_progress_md,
        "btn_analyze_visual": btn_analyze_visual,
        "btn_gen_all_images": btn_gen_all_images,
        "btn_gen_veo_videos": btn_gen_veo_videos,
        "btn_retry_failed_visual": btn_retry_failed_visual,
        "btn_render_final_video": btn_render_final_video,
        "auto_production_chk": auto_production_chk,
        "visual_status_log_md": visual_status_log_md,
        "visual_scenes_table": visual_scenes_table,
        "char_lib_table": char_lib_table,
        "btn_refresh_char_lib": btn_refresh_char_lib,
        "char_select_dd": char_select_dd,
        "btn_load_char_ref": btn_load_char_ref,
        "char_card_header_md": char_card_header_md,
        "char_ref_portrait_img": char_ref_portrait_img,
        "char_ref_status_md": char_ref_status_md,
        "char_ref_details_md": char_ref_details_md,
        "char_ref_confirm_box": char_ref_confirm_box,
        "char_ref_confirm_msg_md": char_ref_confirm_msg_md,
        "btn_cancel_char_gen": btn_cancel_char_gen,
        "btn_confirm_char_gen": btn_confirm_char_gen,
        "char_ref_type_dd": char_ref_type_dd,
        "btn_gen_char_ref": btn_gen_char_ref,
        "btn_regen_char_ref": btn_regen_char_ref,
        "btn_toggle_upload": btn_toggle_upload,
        "upload_char_ref_file": upload_char_ref_file,
        "btn_approve_char_ref": btn_approve_char_ref,
        "btn_reject_char_ref": btn_reject_char_ref,
        "char_ref_action_status_md": char_ref_action_status_md,
        "loc_lib_table": loc_lib_table,
        "btn_refresh_loc_lib": btn_refresh_loc_lib,
        "scene_select_dd": scene_select_dd,
        "btn_refresh_scene_details": btn_refresh_scene_details,
        "scene_edit_beat": scene_edit_beat,
        "scene_edit_importance": scene_edit_importance,
        "scene_edit_type": scene_edit_type,
        "scene_edit_duration": scene_edit_duration,
        "scene_edit_chars": scene_edit_chars,
        "scene_edit_location": scene_edit_location,
        "scene_edit_image_prompt": scene_edit_image_prompt,
        "scene_edit_motion_prompt": scene_edit_motion_prompt,
        "btn_save_scene_edit": btn_save_scene_edit,
        "scene_edit_status_md": scene_edit_status_md,
        "btn_calc_pilot_cost": btn_calc_pilot_cost,
        "btn_gen_pilot_keyframes": btn_gen_pilot_keyframes,
        "btn_gen_pilot_videos": btn_gen_pilot_videos,
        "btn_refresh_pilot_status": btn_refresh_pilot_status,
        "pilot_cost_info_md": pilot_cost_info_md,
        "pilot_gate_status_md": pilot_gate_status_md,
        "pilot_scene_select_dd": pilot_scene_select_dd,
        "btn_load_pilot_scene": btn_load_pilot_scene,
        "pilot_scene_metadata_md": pilot_scene_metadata_md,
        "pilot_keyframe_img": pilot_keyframe_img,
        "pilot_keyframe_status_md": pilot_keyframe_status_md,
        "btn_approve_pilot_keyframe": btn_approve_pilot_keyframe,
        "btn_reject_pilot_keyframe": btn_reject_pilot_keyframe,
        "pilot_video_player": pilot_video_player,
        "pilot_video_status_md": pilot_video_status_md,
        "btn_approve_pilot_video": btn_approve_pilot_video,
        "btn_reject_pilot_video": btn_reject_pilot_video,
        "pilot_review_notes_txt": pilot_review_notes_txt,
        "btn_save_pilot_review": btn_save_pilot_review,
        "final_episode_video": final_episode_video,
        "final_episode_file_download": final_episode_file_download,
        # Manual Visual components
        "manual_manifest_path_txt": manual_manifest_path_txt,
        "btn_load_manual_manifest": btn_load_manual_manifest,
        "manual_images_dir_txt": manual_images_dir_txt,
        "manual_videos_dir_txt": manual_videos_dir_txt,
        "btn_manual_scan_assets": btn_manual_scan_assets,
        "btn_manual_validate": btn_manual_validate,
        "btn_manual_preview": btn_manual_preview,
        "btn_manual_auto_assemble": btn_manual_auto_assemble,
        "manual_summary_report_md": manual_summary_report_md,
        "manual_manifest_df": manual_manifest_df,
        "manual_duplicate_box": manual_duplicate_box,
        "manual_dup_scene_dd": manual_dup_scene_dd,
        "manual_dup_file_dd": manual_dup_file_dd,
        "btn_manual_apply_dup": btn_manual_apply_dup,
        "manual_preview_box": manual_preview_box,
        "manual_preview_scene_dd": manual_preview_scene_dd,
        "btn_load_scene_preview": btn_load_scene_preview,
        "manual_preview_image": manual_preview_image,
        "manual_preview_video": manual_preview_video,
        "manual_preview_overlay_md": manual_preview_overlay_md,
        "manual_manifest_state": manual_manifest_state,
    }
    return components


def _get_empty_import_returns(error_message: str):
    """Trả về cập nhật rỗng khi có lỗi import."""
    return (
        error_message,
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
        gr.update(choices=[], value=None),
        None, {}, {}, [], None, {}, [], [], None
    )


def process_loaded_story_project(data: dict, project_dir: Path, available_voices: list, t_start: float = 0.0):
    """
    Xử lý cấu trúc dữ liệu JSON kịch bản, ánh xạ nhân vật, khởi tạo project và cập nhật UI.
    """
    if t_start == 0.0:
        t_start = time.perf_counter()

    # 1. Schema validation
    t_val_start = time.perf_counter()
    all_voices = get_all_available_voices()
    if available_voices:
        existing_ids = {v[1] if isinstance(v, (tuple, list)) else v for v in all_voices}
        for item in available_voices:
            vid = item[1] if isinstance(item, (tuple, list)) else item
            if vid not in existing_ids:
                all_voices.append(item)
                existing_ids.add(vid)

    is_valid, err, proj_info, chars_map, warnings, stats = validate_story_json(data, all_voices)
    t_val_ms = (time.perf_counter() - t_val_start) * 1000.0
    print(f"[IMPORT] Schema validation: {t_val_ms:.1f} ms", flush=True)

    if not is_valid:
        return _get_empty_import_returns(f"❌ Lỗi cấu trúc JSON: {err}")

    # 2. Project state & save source.json
    t_state_start = time.perf_counter()
    project_dir.mkdir(parents=True, exist_ok=True)
    runtime_state = load_or_init_project_state(project_dir, data)
    with open(project_dir / "source.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    t_state_ms = (time.perf_counter() - t_state_start) * 1000.0
    print(f"[IMPORT] Project state: {t_state_ms:.1f} ms", flush=True)

    # 3. Character mapping
    t_char_start = time.perf_counter()
    info_md = (
        f"### 📖 Dự án: **{proj_info['title']}** — *{proj_info['episode_title']}*\n"
        f"- **Số phân đoạn (Segments):** {stats['segment_count']} | **Nhân vật:** {stats['character_count']} | "
        f"**Tổng số từ:** {stats['total_words']} từ\n"
        f"- **Thời lượng ước tính:** ~{stats['estimated_seconds']/60:.1f} phút ({int(stats['estimated_seconds'])} giây) | "
        f"**Tần số lấy mẫu:** {proj_info['sample_rate']}Hz | **Thư mục:** `{project_dir}`"
    )

    warn_md_content = "\n\n".join(warnings) if warnings else ""
    warn_md_update = gr.update(value=warn_md_content, visible=bool(warn_md_content))

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
    t_char_ms = (time.perf_counter() - t_char_start) * 1000.0
    print(f"[IMPORT] Character mapping: {t_char_ms:.1f} ms", flush=True)

    # 4. Segment table
    t_table_start = time.perf_counter()
    segments = data.get("segments", [])
    df_rows = build_segments_dataframe(segments, chars_map, runtime_state)
    t_table_ms = (time.perf_counter() - t_table_start) * 1000.0
    print(f"[IMPORT] Segment table: {t_table_ms:.1f} ms", flush=True)

    # 5. UI render & package outputs
    t_render_start = time.perf_counter()
    seg_choices = [f"[{s.get('id', idx+1):0>3}] {s.get('speaker', '')}: {s.get('text', '')[:40]}..." for idx, s in enumerate(segments)]
    preview_dd_update = gr.update(choices=seg_choices, value=seg_choices[0] if seg_choices else None)
    t_render_ms = (time.perf_counter() - t_render_start) * 1000.0
    print(f"[IMPORT] UI render: {t_render_ms:.1f} ms", flush=True)

    t_total_ms = (time.perf_counter() - t_start) * 1000.0
    print(f"[IMPORT] TOTAL: {t_total_ms:.1f} ms", flush=True)

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
        runtime_state,
        [], # cue_sheet_state
        [], # timeline_events_state
        None # voice_master_path_state
    )


def handle_import_json_data(json_content_or_file, available_voices: list):
    """Xử lý nạp file JSON kịch bản."""
    if not json_content_or_file:
        return _get_empty_import_returns("⚠️ Vui lòng chọn file JSON kịch bản.")

    print("[IMPORT] Start", flush=True)
    t_start = time.perf_counter()

    try:
        t_read_start = time.perf_counter()
        filepath = None
        if hasattr(json_content_or_file, "path") and json_content_or_file.path:
            filepath = json_content_or_file.path
        elif hasattr(json_content_or_file, "name") and json_content_or_file.name and os.path.exists(str(json_content_or_file.name)):
            filepath = json_content_or_file.name
        elif isinstance(json_content_or_file, dict) and "path" in json_content_or_file:
            filepath = json_content_or_file["path"]
        elif isinstance(json_content_or_file, str) and os.path.exists(json_content_or_file):
            filepath = json_content_or_file

        if filepath:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif isinstance(json_content_or_file, str):
            data = json.loads(json_content_or_file)
        elif isinstance(json_content_or_file, dict):
            data = json_content_or_file
        else:
            raise ValueError(f"Định dạng dữ liệu không hỗ trợ: {type(json_content_or_file)}")

        t_read_ms = (time.perf_counter() - t_read_start) * 1000.0
        print(f"[IMPORT] JSON read: {t_read_ms:.1f} ms", flush=True)

        proj_slug = sanitize_slug(data.get("project", {}).get("title", "story_project"))
        project_dir = Path("projects") / proj_slug

        return process_loaded_story_project(data, project_dir, available_voices, t_start=t_start)

    except Exception as e:
        import logging
        logging.getLogger("VieNeu.ProductionStory").exception("Production JSON import failed")
        print(f"❌ [IMPORT] Error: {e}", flush=True)
        return _get_empty_import_returns(f"❌ Lỗi xử lý JSON: {str(e)}")


def handle_import_zip_pack(zip_file, available_voices: list):
    """
    Xử lý nạp file ZIP Production Pack (gồm JSON và thư mục music/).
    """
    if not zip_file:
        return _get_empty_import_returns("⚠️ Vui lòng chọn file ZIP Production Pack.")

    try:
        temp_extract_dir = Path("projects") / "_temp_pack_extract"
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir, ignore_errors=True)
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        ok, msg, found_json, found_music = safe_extract_zip(zip_file, temp_extract_dir)
        if not ok or not found_json or not found_json.exists():
            return _get_empty_import_returns(f"❌ Lỗi giải nén ZIP Pack: {msg}")

        with open(found_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        proj_slug = sanitize_slug(data.get("project", {}).get("title", "story_project"))
        final_project_dir = Path("projects") / proj_slug
        final_project_dir.mkdir(parents=True, exist_ok=True)

        # Copy JSON vào project dir
        shutil.copy2(found_json, final_project_dir / "source.json")

        # Copy music/ nếu có
        if found_music and found_music.exists():
            final_music_dir = final_project_dir / "music"
            final_music_dir.mkdir(parents=True, exist_ok=True)
            for item in found_music.iterdir():
                if item.is_file():
                    shutil.copy2(item, final_music_dir / item.name)

        shutil.rmtree(temp_extract_dir, ignore_errors=True)
        return process_loaded_story_project(data, final_project_dir, available_voices)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _get_empty_import_returns(f"❌ Lỗi giải nén ZIP Pack: {str(e)}")


def bind_production_story_events(components: dict, get_tts_engine_fn, get_available_voices_fn, stop_event):
    """
    Gán các sự kiện tương tác cho module Production Storytelling & Music Mixing Engine.
    """
    c = components

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
        c["story_runtime_state"],
        c["story_cue_sheet_state"],
        c["story_timeline_events_state"],
        c["story_voice_master_path_state"]
    ]

    # 1. Imports
    def _on_import_pack(f):
        return handle_import_zip_pack(f, get_available_voices_fn())

    c["btn_import_pack_zip"].upload(
        fn=_on_import_pack,
        inputs=[c["btn_import_pack_zip"]],
        outputs=import_outputs
    )

    def _on_import_json_file(f):
        return handle_import_json_data(f, get_available_voices_fn())

    c["btn_import_json"].upload(
        fn=_on_import_json_file,
        inputs=[c["btn_import_json"]],
        outputs=import_outputs
    )

    # 2. Presets
    def _on_load_v9_1():
        p = Path("presets/episode01_v9_1_master_reference_vieneu.json")
        if not p.exists():
            p = Path("C:/Users/TPT/Documents/sau_canh_cua_ep01_v9_1_master_reference/01_audio/episode01_v9_1_master_reference_vieneu.json")
        return handle_import_json_data(str(p), get_available_voices_fn())

    c["btn_preset_v9_1"].click(
        fn=_on_load_v9_1,
        inputs=[],
        outputs=import_outputs
    )

    def _on_load_pilot():
        p = Path("projects/sau_canh_cua_-_pilot_01_v6/source.json")
        if not p.exists():
            p = Path("tests/test_pilot_story.json")
        return handle_import_json_data(str(p), get_available_voices_fn())

    c["btn_sample_pilot"].click(
        fn=_on_load_pilot,
        inputs=[],
        outputs=import_outputs
    )

    # 3. Preview Voice Character Cards
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

        invalidated_count = 0
        if changed_speakers:
            invalidated_count = invalidate_cache_for_speakers(project_dir, runtime_state, changed_speakers)

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

    c["btn_refresh_voices"].click(
        fn=lambda *vals: [*[gr.update(choices=get_all_available_voices(get_tts_engine_fn()), value=vals[i] if i < len(vals) else None) for i in range(MAX_STORY_CHARACTERS)], f"✅ Đã cập nhật danh sách {len(get_all_available_voices())} giọng!"],
        inputs=c["char_voice_dds"],
        outputs=[*c["char_voice_dds"], c["apply_status_md"]]
    )

    # 5. Music Library Management (Direct Slot Replacement & Advanced Upload)
    slot_keys = ["INTRO", "MYSTERY", "TENSION", "EMOTIONAL", "REFLECTION", "OUTRO"]
    slot_outputs = []
    for sk in slot_keys:
        slot_outputs.append(c["slot_info_components"][sk])
        slot_outputs.append(c["slot_audio_components"][sk])

    def _extract_upload_file(file_obj):
        if not file_obj:
            return None, None
        fp = None
        orig_name = None
        if hasattr(file_obj, "path"):
            fp = file_obj.path
            orig_name = getattr(file_obj, "orig_name", None)
        elif hasattr(file_obj, "name"):
            fp = file_obj.name
            orig_name = getattr(file_obj, "name", None)
        elif isinstance(file_obj, dict):
            fp = file_obj.get("path") or file_obj.get("name")
            orig_name = file_obj.get("orig_name")
        else:
            fp = str(file_obj)

        if fp:
            fp = str(fp)
            if not orig_name:
                orig_name = Path(fp).name
        return fp, orig_name

    def _refresh_slot_ui_states():
        sdata = get_slot_cards_data()
        returns = []
        for sk in slot_keys:
            info = sdata.get(sk, {})
            returns.append(format_slot_markdown(info))
            returns.append(info.get("audio_preview"))
        return returns

    def _on_replace_slot_track(slot, file_obj):
        fp, orig_name = _extract_upload_file(file_obj)
        if not fp:
            msg = "⚠️ Vui lòng chọn hoặc kéo thả file âm thanh cần nạp."
            return [f"**{msg}**"] + _refresh_slot_ui_states() + [get_music_library_table_data()]

        src_p = Path(fp)
        if not src_p.exists():
            msg = f"❌ File tạm không tồn tại: {src_p}"
            return [f"**{msg}**"] + _refresh_slot_ui_states() + [get_music_library_table_data()]

        try:
            ok, msg, _ = import_track_to_library(
                category=slot,
                track_id=None,
                file_source=src_p,
                orig_filename=orig_name
            )
            status_text = f"✅ {msg}" if ok else f"❌ {msg}"
        except Exception as e:
            status_text = f"❌ Lỗi: {e}"

        new_rows = get_music_library_table_data()
        return [status_text] + _refresh_slot_ui_states() + [new_rows]

    c["btn_replace_slot_track"].click(
        fn=_on_replace_slot_track,
        inputs=[c["quick_slot_dd"], c["quick_file_upload"]],
        outputs=[c["replace_slot_status_md"]] + slot_outputs + [c["music_library_df"]]
    )

    # 6 Direct Slot Replace Buttons
    for sk in slot_keys:
        if sk in c.get("slot_replace_btns", {}) and sk in c.get("slot_file_components", {}):
            s_btn = c["slot_replace_btns"][sk]
            s_file = c["slot_file_components"][sk]
            s_status = c["slot_status_components"][sk]

            def _make_slot_replace_fn(slot_name):
                return lambda f: _on_replace_slot_track(slot_name, f)

            s_btn.click(
                fn=_make_slot_replace_fn(sk),
                inputs=[s_file],
                outputs=[s_status] + slot_outputs + [c["music_library_df"]]
            )

    c["refresh_music_fn"] = lambda: _refresh_slot_ui_states() + [get_music_library_table_data()]
    c["slot_outputs_list"] = slot_outputs + [c["music_library_df"]]

    def _on_adv_import_track(cat, track_id, file_obj):
        fp, orig_name = _extract_upload_file(file_obj)
        if not fp:
            msg = "⚠️ Vui lòng cung cấp file âm thanh."
            return [f"**{msg}**"] + _refresh_slot_ui_states() + [get_music_library_table_data()]

        src_p = Path(fp)
        if not src_p.exists():
            msg = f"❌ File tạm không tồn tại: {src_p}"
            return [f"**{msg}**"] + _refresh_slot_ui_states() + [get_music_library_table_data()]

        try:
            ok, msg, _ = import_track_to_library(
                category=cat,
                track_id=track_id.strip() if track_id else None,
                file_source=src_p,
                orig_filename=orig_name
            )
            status_text = f"✅ {msg}" if ok else f"❌ {msg}"
        except Exception as e:
            status_text = f"❌ Lỗi: {e}"

        new_rows = get_music_library_table_data()
        return [status_text] + _refresh_slot_ui_states() + [new_rows]

    c["btn_execute_import_track"].click(
        fn=_on_adv_import_track,
        inputs=[c["upload_cat_dd"], c["upload_track_id_box"], c["upload_file_btn"]],
        outputs=[c["import_track_status_md"]] + slot_outputs + [c["music_library_df"]]
    )

    # 6. Segments Table Quick Cue Editor
    def _on_apply_quick_cue(chosen_cue, df_data, segments):
        if not df_data or not chosen_cue or not segments:
            return df_data, segments, "⚠️ Chưa có dữ liệu hoặc chưa chọn Music Cue."
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        id_to_seg = {str(s.get("id", "")).zfill(3): s for s in segments}
        assigned_count = 0
        for r in rows:
            if bool(r[0]): # checked
                r[10] = chosen_cue
                seg_id = str(r[1]).zfill(3)
                if seg_id in id_to_seg:
                    id_to_seg[seg_id]["music_cue"] = chosen_cue
                assigned_count += 1
        msg = f"✅ **Đã gán Music Cue '{chosen_cue}'** cho **{assigned_count} phân đoạn** được chọn."
        return rows, segments, msg

    c["btn_apply_quick_cue"].click(
        fn=_on_apply_quick_cue,
        inputs=[c["quick_cue_dropdown"], c["story_segments_df"], c["story_segments_state"]],
        outputs=[c["story_segments_df"], c["story_segments_state"], c["story_progress_md"]]
    )

    # Checkbox Selection Helpers
    def _toggle_all(df_data, checked: bool):
        if df_data is None: return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows: r[0] = checked
        return rows

    def _select_failed(df_data):
        if df_data is None: return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows: r[0] = (r[18] in ("FAILED", "NEEDS_REGENERATE"))
        return rows

    def _select_multitake(df_data):
        if df_data is None: return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows: r[0] = (int(r[17]) > 1)
        return rows

    c["btn_select_all"].click(lambda df: _toggle_all(df, True), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_deselect_all"].click(lambda df: _toggle_all(df, False), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_failed"].click(fn=_select_failed, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_multitake"].click(fn=_select_multitake, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_stop_story"].click(lambda: stop_event.set(), inputs=[], outputs=[])

    # 7. TTS Generation (Sequential with Cache, Resume & Multi-take)
    def _run_generation(df_data, segments, chars_map, project_dir_str, runtime_state, mode="selected"):
        tts = get_tts_engine_fn()
        if tts is None:
            yield "⚠️ Chưa tải model! Vui lòng tải model trước.", "⚠️ Model chưa sẵn sàng.", df_data, runtime_state
            return
        if not project_dir_str or not segments:
            yield "⚠️ Chưa có dữ liệu dự án kịch bản.", "⚠️ Không có segment để xử lý.", df_data, runtime_state
            return

        project_dir = Path(project_dir_str)
        stop_event.clear()

        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        id_to_row_idx = {str(r[1]).zfill(3): idx for idx, r in enumerate(rows)}

        targets = []
        for seg in segments:
            seg_id = str(seg.get("id", "")).zfill(3)
            row_idx = id_to_row_idx.get(seg_id)
            if row_idx is None: continue
            is_selected = bool(rows[row_idx][0])
            status = rows[row_idx][18]

            override_val = str(rows[row_idx][5] or "").strip()
            if override_val and override_val not in ("Use Character Voice", "Kế thừa (Use Character Voice)", "None"):
                seg["voice_override"] = override_val
            else:
                seg.pop("voice_override", None)

            if mode == "changed":
                if status in ("PENDING", "NEEDS_REGENERATE", "FAILED"): targets.append(seg)
            elif mode == "failed":
                if status == "FAILED": targets.append(seg)
            else:
                if is_selected: targets.append(seg)

        total_targets = len(targets)
        if total_targets == 0:
            yield "⚠️ Không có phân đoạn nào phù hợp với chế độ đã chọn.", "Không có tác vụ.", rows, runtime_state
            return

        log_lines = [f"🚀 Bắt đầu sinh TTS cho {total_targets} phân đoạn (Chế độ: {mode})..."]
        yield "\n".join(log_lines), f"⏳ Chuẩn bị sinh {total_targets} phân đoạn...", rows, runtime_state

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

            voice_override = seg.get("voice_override", "")
            effective_voice = voice_override if (voice_override and voice_override != "Kế thừa (Use Character Voice)") else char_cfg.get("voice", "")
            current_hash = compute_segment_hash(seg, effective_voice, "v3turbo")
            row_idx = id_to_row_idx.get(seg_id)

            cached_seg = runtime_state.get("segments", {}).get(seg_id)
            is_cached = False
            if cached_seg and cached_seg.get("hash") == current_hash and cached_seg.get("status") == "COMPLETED":
                sel_p = project_dir / (cached_seg.get("selected_file") or f"selected/{seg_id}.wav")
                if sel_p.exists(): is_cached = True

            if is_cached:
                cached_count += 1
                if row_idx is not None: rows[row_idx][18] = "CACHED"
                log_lines.append(f"⚡ [{idx+1}/{total_targets}] Phân đoạn {seg_id}_{speaker}: Đã có trong Cache (Bỏ qua).")
                yield "\n".join(log_lines[-10:]), f"⚡ {idx+1}/{total_targets} | Phân đoạn {seg_id}_{speaker} (Cached)", rows, runtime_state
                continue

            elapsed = time.time() - start_time
            avg_per_seg = elapsed / max(1, (success_count + failed_count))
            remaining_segs = total_targets - (idx + 1)
            eta_sec = int(avg_per_seg * remaining_segs)

            progress_msg = f"⏳ Đang sinh {idx+1}/{total_targets} | Phân đoạn: **{seg_id}_{speaker}** | Giọng: **{effective_voice}** | Còn lại: ~{eta_sec}s"
            log_lines.append(f"🎙️ [{idx+1}/{total_targets}] Đang sinh {seg_id}_{speaker} (Giọng: {effective_voice}, Takes: {seg.get('multi_take', 1)})...")
            yield "\n".join(log_lines[-10:]), progress_msg, rows, runtime_state

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
                    rows[row_idx][18] = "COMPLETED"
                    rows[row_idx][19] = f"Take {seg_result.get('selected_take', 1)}"
                log_lines.append(f"  ✅ Phân đoạn {seg_id}: Hoàn tất ({len(seg_result.get('takes', {}))} takes).")
            else:
                failed_count += 1
                runtime_state.setdefault("segments", {})[seg_id] = {"id": seg_id, "status": "FAILED", "error": msg}
                save_project_state(project_dir, runtime_state)
                if row_idx is not None: rows[row_idx][18] = "FAILED"
                log_lines.append(f"  ❌ Phân đoạn {seg_id} Lỗi: {msg}")

            yield "\n".join(log_lines[-10:]), progress_msg, rows, runtime_state

        total_elapsed = time.time() - start_time
        summary_msg = f"🎉 **Hoàn thành sinh TTS!** Thành công: {success_count} | Lỗi: {failed_count} | Cache: {cached_count} | Thời gian: {total_elapsed:.1f}s"
        log_lines.append(summary_msg)
        yield "\n".join(log_lines[-10:]), summary_msg, rows, runtime_state

    def _run_gen_selected(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="selected")

    def _run_gen_changed(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="changed")

    def _run_gen_failed(df, s, c_m, p_d, r_s):
        yield from _run_generation(df, s, c_m, p_d, r_s, mode="failed")

    c["btn_generate_story"].click(
        fn=_run_gen_selected,
        inputs=[c["story_segments_df"], c["story_segments_state"], c["story_characters_state"], c["story_project_dir_state"], c["story_runtime_state"]],
        outputs=[c["story_log_output"], c["story_progress_md"], c["story_segments_df"], c["story_runtime_state"]]
    )
    c["btn_generate_changed"].click(
        fn=_run_gen_changed,
        inputs=[c["story_segments_df"], c["story_segments_state"], c["story_characters_state"], c["story_project_dir_state"], c["story_runtime_state"]],
        outputs=[c["story_log_output"], c["story_progress_md"], c["story_segments_df"], c["story_runtime_state"]]
    )
    c["btn_retry_failed"].click(
        fn=_run_gen_failed,
        inputs=[c["story_segments_df"], c["story_segments_state"], c["story_characters_state"], c["story_project_dir_state"], c["story_runtime_state"]],
        outputs=[c["story_log_output"], c["story_progress_md"], c["story_segments_df"], c["story_runtime_state"]]
    )

    # 8. Take Selection
    def _on_preview_select(seg_label, project_dir_str, runtime_state):
        if not seg_label or not project_dir_str: return None, None, None, ""
        seg_id = seg_label.split("]")[0].replace("[", "").strip()
        paths = get_take_audio_paths(Path(project_dir_str), runtime_state, seg_id)
        selected_take = runtime_state.get("segments", {}).get(seg_id, {}).get("selected_take", 1)
        return paths.get(1), paths.get(2), paths.get(3), f"Phân đoạn **{seg_id}** đang dùng: **Take {selected_take}**"

    c["preview_seg_dropdown"].change(
        fn=_on_preview_select,
        inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"]],
        outputs=[c["audio_take1"], c["audio_take2"], c["audio_take3"], c["take_select_status_md"]]
    )

    def _choose_take(seg_label, take_num, project_dir_str, runtime_state, df_data):
        if not seg_label or not project_dir_str: return "Chưa chọn phân đoạn.", runtime_state, df_data
        seg_id = seg_label.split("]")[0].replace("[", "").strip()
        success, msg = select_take_for_segment(Path(project_dir_str), runtime_state, seg_id, take_num)
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            if str(r[1]).zfill(3) == seg_id.zfill(3):
                r[19] = f"Take {take_num}"
                break
        return (f"✅ {msg}" if success else f"❌ {msg}"), runtime_state, rows

    def _use_take_1(lbl, p, r, df):
        return _choose_take(lbl, 1, p, r, df)

    def _use_take_2(lbl, p, r, df):
        return _choose_take(lbl, 2, p, r, df)

    def _use_take_3(lbl, p, r, df):
        return _choose_take(lbl, 3, p, r, df)

    c["btn_use_take1"].click(fn=_use_take_1, inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]], outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]])
    c["btn_use_take2"].click(fn=_use_take_2, inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]], outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]])
    c["btn_use_take3"].click(fn=_use_take_3, inputs=[c["preview_seg_dropdown"], c["story_project_dir_state"], c["story_runtime_state"], c["story_segments_df"]], outputs=[c["take_select_status_md"], c["story_runtime_state"], c["story_segments_df"]])

    # 9. Clean Voice Master Builder
    def _on_build_voice_master(project_dir_str, segments, runtime_state, gap_rule):
        if not project_dir_str or not segments:
            return "⚠️ Chưa có dự án nào được mở.", None, gr.update(visible=False), None, [], None

        ok, msg, v_path, events = build_clean_voice_master(
            project_dir=Path(project_dir_str),
            segments=segments,
            project_state=runtime_state,
            gap_rule=gap_rule
        )
        if not ok:
            return f"❌ {msg}", None, gr.update(visible=False), None, [], None

        status_txt = f"🎉 **{msg}**\n- File: `{v_path}`\n- Lời thoại sạch 100%, không chứa room tone, white noise hay nhạc."
        return (
            status_txt,
            str(v_path),
            gr.update(value=str(v_path), visible=True),
            str(v_path), # story_voice_master_path_state
            events,      # story_timeline_events_state
            str(v_path)  # ab_voice_audio
        )

    c["btn_build_voice_master"].click(
        fn=_on_build_voice_master,
        inputs=[c["story_project_dir_state"], c["story_segments_state"], c["story_runtime_state"], c["gap_rule_radio"]],
        outputs=[
            c["voice_master_status_md"],
            c["voice_master_audio"],
            c["voice_master_download"],
            c["story_voice_master_path_state"],
            c["story_timeline_events_state"],
            c["ab_voice_audio"]
        ]
    )

    # 10. Music Cue Sheet Engine & Timeline
    def _on_build_cues(project_dir_str, events, pre_rev, post_rev, merge_gap, i_db, m_db, t_db, e_db, r_db, o_db):
        if not events:
            return "⚠️ Chưa có Voice Timeline. Hãy bấm **'Build Clean Voice Master'** trước.", "<div style='color: #ef4444;'>Chưa có dữ liệu.</div>", [], gr.update(choices=[]), []

        total_sec = events[-1]["speech_end_sec"]
        overrides = {
            "INTRO": {"level_db": float(i_db)},
            "MYSTERY": {"level_db": float(m_db)},
            "TENSION": {"level_db": float(t_db)},
            "EMOTIONAL": {"level_db": float(e_db)},
            "REFLECTION": {"level_db": float(r_db)},
            "OUTRO": {"level_db": float(o_db)}
        }

        cue_sheet = generate_cue_sheet_from_segments(
            timeline_events=events,
            music_overrides=overrides,
            pre_reveal_clearance=float(pre_rev),
            post_reveal_clearance=float(post_rev),
            merge_gap_threshold=float(merge_gap),
            total_episode_sec=total_sec
        )

        # Ghi đè ngay cue_sheet.json mới đã validate vào thư mục mix của dự án (Fix 6)
        if project_dir_str:
            try:
                p_dir = Path(project_dir_str)
                if p_dir.exists():
                    mix_d = p_dir / "mix"
                    mix_d.mkdir(parents=True, exist_ok=True)
                    with open(mix_d / "cue_sheet.json", "w", encoding="utf-8") as f:
                        json.dump(cue_sheet, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[CUE SAVE WARNING] Lỗi lưu cue_sheet.json: {e}", flush=True)

        cov = calculate_music_coverage(cue_sheet, total_sec)
        warn_part = f"\n\n{cov['warning_message']}" if cov["warning_message"] else ""
        cov_md = (
            f"### 📊 Thống Kê Phủ Nhạc (Music Coverage):\n"
            f"- **Tổng thời lượng tập:** `{cov['total_episode_fmt']}` ({cov['total_episode_sec']}s) | "
            f"**Có nhạc:** `{cov['music_duration_fmt']}` ({cov['music_duration_sec']}s) | "
            f"**Voice sạch (DRY):** `{cov['dry_duration_fmt']}` ({cov['dry_duration_sec']}s)\n"
            f"- **Tỷ lệ phủ nhạc:** **{cov['coverage_percent']}%** *(Khuyến nghị chuẩn: {cov['target_recommendation']})*{warn_part}"
        )

        timeline_html = generate_visual_timeline_html(cue_sheet, events, total_sec)

        # DataFrame rows
        df_rows = []
        region_choices = []
        for idx, item in enumerate(cue_sheet):
            df_rows.append([
                item["start_sec"],
                item["end_sec"],
                item["duration_sec"],
                item["cue"],
                item["track"],
                item["level_db"],
                item["fade_in_sec"],
                item["fade_out_sec"],
                item["source"]
            ])
            if item["cue"] != "DRY":
                region_choices.append(f"[{idx+1:02d}] {item['cue']} ({item['start_sec']}s → {item['end_sec']}s, {item['track']})")

        choice_upd = gr.update(choices=region_choices, value=region_choices[0] if region_choices else None)

        return cov_md, timeline_html, df_rows, choice_upd, cue_sheet

    c["btn_build_cues"].click(
        fn=_on_build_cues,
        inputs=[
            c["story_project_dir_state"],
            c["story_timeline_events_state"],
            c["pre_reveal_slider"],
            c["post_reveal_slider"],
            c["merge_gap_slider"],
            c["intro_db_slider"],
            c["mystery_db_slider"],
            c["tension_db_slider"],
            c["emotional_db_slider"],
            c["reflection_db_slider"],
            c["outro_db_slider"]
        ],
        outputs=[
            c["coverage_metrics_md"],
            c["visual_timeline_html"],
            c["cue_sheet_df"],
            c["preview_region_dd"],
            c["story_cue_sheet_state"]
        ]
    )

    # 11. Region Preview
    def _on_preview_region(project_dir_str, voice_master_path, reg_choice, cue_sheet):
        if not project_dir_str or not voice_master_path or not reg_choice or not cue_sheet:
            return None
        idx = int(reg_choice.split("]")[0].replace("[", "").strip()) - 1
        if 0 <= idx < len(cue_sheet):
            target_item = cue_sheet[idx]
            ok, msg, p = preview_region_mix(Path(project_dir_str), Path(voice_master_path), target_item)
            return str(p) if ok else None
        return None

    c["btn_preview_region"].click(
        fn=_on_preview_region,
        inputs=[c["story_project_dir_state"], c["story_voice_master_path_state"], c["preview_region_dd"], c["story_cue_sheet_state"]],
        outputs=[c["audio_region_preview"]]
    )

    # 12. Final Mix & Mastering (Build & Rebuild)
    def _on_build_final_mix(project_dir_str, voice_master_path, cue_df_data, events, enable_duck, lufs, peak):
        if not project_dir_str or not voice_master_path:
            empty_stems = [None, None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return "⚠️ Chưa có Clean Voice Master. Hãy tạo Voice Master trước.", *empty_stems

        project_dir = Path(project_dir_str)
        v_path = Path(voice_master_path)
        if not v_path.exists():
            empty_stems = [None, None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return "⚠️ File voice_master.wav không tồn tại trên đĩa.", *empty_stems

        # Đọc dữ liệu Cue Sheet từ DataFrame (để người dùng có thể chỉnh trực tiếp trên bảng)
        rows = cue_df_data.values.tolist() if hasattr(cue_df_data, "values") else list(cue_df_data)
        cue_sheet = []
        for r in rows:
            cue_sheet.append({
                "start_sec": float(r[0]),
                "end_sec": float(r[1]),
                "duration_sec": float(r[2]),
                "cue": str(r[3]),
                "track": str(r[4]),
                "level_db": float(r[5]),
                "fade_in_sec": float(r[6]),
                "fade_out_sec": float(r[7]),
                "source": str(r[8])
            })

        if not cue_sheet:
            empty_stems = [None, None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return "⚠️ Cue sheet rỗng. Hãy bấm 'Analyze / Build Music Cues' trước.", *empty_stems

        ok, msg, report = build_final_mix(
            project_dir=project_dir,
            voice_master_path=v_path,
            cue_sheet=cue_sheet,
            timeline_events=events,
            enable_ducking=bool(enable_duck),
            target_lufs=float(lufs),
            true_peak_db=float(peak)
        )

        if not ok:
            empty_stems = [None, None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return f"❌ {msg}", *empty_stems

        f_wav = report["outputs"]["final_mix_wav"]
        f_mp3 = report["outputs"]["final_mix_mp3"]
        m_mix = report["outputs"]["music_mix_wav"]
        c_json = report["outputs"]["cue_sheet_json"]
        m_rep = str(project_dir / "mix" / "mix_report.json")

        status_txt = (
            f"🎉 **{msg}**\n"
            f"- **Final Master WAV (48kHz 24-bit PCM):** `{f_wav}`\n"
            f"- **Final Master MP3 (320kbps):** `{f_mp3}`\n"
            f"- **Integrated Loudness:** `{report['master_integrated_lufs']} LUFS` | **True Peak:** `{report['master_true_peak_db']} dBTP`\n"
            f"- **Music Coverage:** `{report['music_duration_fmt']}` / `{report['total_episode_fmt']}` ({report['music_coverage_pct']}%)\n"
            f"- *Đã tách biệt 100% với TTS: Thay đổi nhạc/volume không hề sinh lại giọng đọc.*"
        )

        return (
            status_txt,
            f_wav,
            f_mp3,
            m_mix,
            str(v_path), # ab_voice_audio
            f_wav,       # ab_mix_audio
            gr.update(value=f_wav, visible=True),
            gr.update(value=f_mp3, visible=True),
            gr.update(value=m_mix, visible=True),
            gr.update(value=c_json, visible=True),
            gr.update(value=m_rep, visible=True)
        )

    final_mix_outputs = [
        c["final_mix_status_md"],
        c["final_mix_wav_audio"],
        c["final_mix_mp3_audio"],
        c["music_mix_audio"],
        c["ab_voice_audio"],
        c["ab_mix_audio"],
        c["final_wav_download"],
        c["final_mp3_download"],
        c["music_mix_download"],
        c["cue_sheet_download"],
        c["mix_report_download"]
    ]

    c["btn_build_final_mix"].click(
        fn=_on_build_final_mix,
        inputs=[
            c["story_project_dir_state"],
            c["story_voice_master_path_state"],
            c["cue_sheet_df"],
            c["story_timeline_events_state"],
            c["chk_gentle_ducking"],
            c["target_lufs_num"],
            c["true_peak_num"]
        ],
        outputs=final_mix_outputs
    )

    c["btn_rebuild_final_mix"].click(
        fn=_on_build_final_mix,
        inputs=[
            c["story_project_dir_state"],
            c["story_voice_master_path_state"],
            c["cue_sheet_df"],
            c["story_timeline_events_state"],
            c["chk_gentle_ducking"],
            c["target_lufs_num"],
            c["true_peak_num"]
        ],
        outputs=final_mix_outputs
    )

    # 13. Export Project JSON
    def _on_export(project_dir_str, raw_json, chars_map, segments, runtime_state):
        if not project_dir_str or not raw_json: return gr.update(visible=False)
        export_payload = json.loads(json.dumps(raw_json))
        if "characters" in export_payload:
            for cid, ccfg in export_payload["characters"].items():
                if cid in chars_map:
                    ccfg["voice"] = chars_map[cid].get("voice", ccfg.get("voice", ""))
                    ccfg["default_speed"] = chars_map[cid].get("default_speed", ccfg.get("default_speed", 1.0))

        export_p = export_project_json(Path(project_dir_str), export_payload, runtime_state)
        return gr.update(value=export_p, visible=True)

    c["btn_export_json"].click(
        fn=_on_export,
        inputs=[c["story_project_dir_state"], c["story_raw_json_state"], c["story_characters_state"], c["story_segments_state"], c["story_runtime_state"]],
        outputs=[c["file_export_download"]]
    )

    # 14. VISUAL PIPELINE EVENT BINDINGS
    from apps.visual_engine.flowkit_adapter import FlowKitAdapter
    from apps.visual_engine.character_manager import load_character_library, load_location_library, load_visual_preset
    from apps.visual_engine.visual_planner import VisualPlanner, VisualScene, PILOT_SCENE_IDS
    from apps.visual_engine.asset_manager import VisualAssetManager
    from apps.visual_engine.banana_client import BananaClient
    from apps.visual_engine.veo_client import VeoClient
    from apps.visual_engine.visual_qc import VisualQC, record_pilot_qc
    from apps.visual_engine.final_video_renderer import FinalVideoRenderer
    from apps.visual_engine.resolvers import (
        resolve_flow_project_id,
        resolve_video_duration,
        resolve_video_model,
        DEFAULT_FLOW_PROJECT_ID,
    )

    flow_adapter = FlowKitAdapter("http://127.0.0.1:8100")

    def _render_flow_status_md():
        st = flow_adapter.get_connection_status()
        conn_bullet = "● Đã kết nối" if st.is_connected else "○ Chưa kết nối"
        conn_color = "#10b981" if st.is_connected else "#ef4444"
        ext_text = f"Đã kết nối (v{st.extension_version})" if st.extension_connected else "Chưa kết nối"
        tab_text = "Sẵn sàng (flow.google.com)" if st.flow_tab_ready else "Chưa mở tab Flow"
        sess_text = f"Sẵn sàng ({st.flow_project_id[:12]}...)" if st.flow_project_id else ("Sẵn sàng" if st.account_session_ready else "Chưa khởi tạo")

        return (
            f"### 🌐 Trạng thái Google Flow\n"
            f"- **Kết nối:** <span style='color: {conn_color}; font-weight: bold;'>{conn_bullet}</span> (`127.0.0.1:8100`)\n"
            f"- **Chrome/Cốc Cốc Extension:** {ext_text}\n"
            f"- **Flow Tab:** {tab_text}\n"
            f"- **Session:** {sess_text}"
        )

    def _build_char_lib_table():
        chars = load_character_library()
        rows = []
        for cid, c in chars.items():
            flow_st = c.flow.get("upload_status", "LOCAL_ONLY") if getattr(c, "flow", None) else "LOCAL_ONLY"
            if getattr(c, "flow", None) and c.flow.get("media_id"):
                flow_st += f" ({c.flow['media_id'][:8]}...)"
            ref_id = c.local_reference_id or f"{cid}_REF_V1"
            qc_st = getattr(c, "qc_status", "AWAITING_REVIEW")
            wardrobe_str = ", ".join(c.wardrobes.keys()) if getattr(c, "wardrobes", None) else "-"
            identity_str = f"{c.identity_relation.get('type', '')} -> {c.identity_relation.get('character_id', '')}" if getattr(c, "identity_relation", None) else "-"
            rows.append([
                c.char_id,
                c.name,
                c.role or "-",
                ref_id,
                flow_st,
                qc_st,
                wardrobe_str,
                identity_str
            ])
        return rows

    from apps.visual_engine.character_manager import (
        CHARACTER_LIB_DIR,
        approve_character_reference,
        reject_character_reference,
        upload_custom_character_reference,
        build_character_reference_prompt
    )

    def _on_load_char_ref(char_id):
        chars = load_character_library()
        c = chars.get(char_id)
        if not c:
            return (
                None,
                f"### 🎭 {char_id}",
                "**Status:** `NOT_GENERATED`\n\n**Flow:** `LOCAL_ONLY`",
                f"⚠️ Không tìm thấy nhân vật {char_id}",
                gr.update(visible=False),
                gr.update(visible=False),
                ""
            )
        from apps.visual_engine.character_manager import get_character_preview_path
        preview_p = get_character_preview_path(char_id)
        img_val = str(preview_p) if preview_p else None

        # Status: NOT_GENERATED / AWAITING_REVIEW / APPROVED / REJECTED
        if not img_val:
            status_tag = "NOT_GENERATED"
            status_color = "#94a3b8"
        elif c.qc_status == "APPROVED":
            status_tag = "APPROVED"
            status_color = "#10b981"
        elif c.qc_status == "REJECTED":
            status_tag = "REJECTED"
            status_color = "#ef4444"
        else:
            status_tag = "AWAITING_REVIEW"
            status_color = "#f59e0b"

        # Flow: LOCAL_ONLY / UPLOADED
        has_media = bool(c.flow.get("media_id"))
        flow_tag = "UPLOADED" if has_media else "LOCAL_ONLY"
        flow_color = "#3b82f6" if has_media else "#64748b"
        flow_media = c.flow.get("media_id") or "None"

        status_md = (
            f"**Status:** <span style='color:{status_color}; font-weight:bold;'>{status_tag}</span>\n\n"
            f"**Flow:** <span style='color:{flow_color}; font-weight:bold;'>{flow_tag}</span> (`{flow_media}`)"
        )

        header_md = f"### 🎭 **{c.name}** (`{c.char_id}`)"

        # Special notice for LAN_YOUNG
        young_notice = ""
        if c.identity_relation and c.identity_relation.get("type") == "YOUNGER_VERSION_OF":
            anchor_cid = c.identity_relation.get("character_id")
            anchor_char = chars.get(anchor_cid)
            is_anchor_approved = bool(anchor_char and anchor_char.qc_status == "APPROVED")
            anchor_badge = "✅ ĐÃ PHÊ DUYỆT" if is_anchor_approved else "⚠️ CHƯA PHÊ DUYỆT (CẦN PHÊ DUYỆT TRƯỚC)"
            young_notice = f"\n\n> [!NOTE]\n> **Identity Anchor:** Dựa trên `{anchor_cid}` ({anchor_badge})"

        current_file_desc = f" (Tệp: `{preview_p.name}`)" if preview_p else ""
        details_md = (
            f"- **Độ tuổi / Vai trò:** {c.age_range} | {c.role}\n"
            f"- **Ngoại hình:** {c.appearance}\n"
            f"- **Khuôn mặt:** {c.face}\n"
            f"- **Mái tóc:** {c.hair}\n"
            f"- **Vóc dáng:** {c.body}\n"
            f"- **Trang phục mặc định:** {c.default_clothing}\n"
            f"- **Nguồn ảnh hiện tại:** `{getattr(c, 'reference_source', None) or 'N/A'}`{current_file_desc}"
            f"{young_notice}"
        )

        return (
            img_val,
            header_md,
            status_md,
            details_md,
            gr.update(visible=False),  # confirm box hidden
            gr.update(visible=False),  # file upload hidden
            ""                         # clear action status
        )

    def _on_request_gen_char_ref(char_id, custom_pid, ref_type_str):
        chars = load_character_library()
        c = chars.get(char_id)
        if not c:
            return gr.update(visible=False), "", "⚠️ Chưa chọn nhân vật."

        # Check LAN_YOUNG special rule
        if c.identity_relation and c.identity_relation.get("type") == "YOUNGER_VERSION_OF":
            anchor_cid = c.identity_relation.get("character_id")
            anchor_char = chars.get(anchor_cid)
            if not anchor_char or anchor_char.qc_status != "APPROVED":
                err_msg = f"⚠️ **Không thể tạo:** `LAN_YOUNG` yêu cầu reference của `{anchor_cid}` phải được phê duyệt trước (`APPROVED`). Vui lòng chọn và phê duyệt `{anchor_cid}` trước!"
                return gr.update(visible=False), "", err_msg

        is_bible = (ref_type_str == "Character Bible (16:9)")
        mode_label = "Character Bible Model Sheet (Đa góc nhìn: Toàn thân, 3/4, Profile, Cận cảnh)" if is_bible else "Chân dung đơn (Portrait 3:4)"
        aspect_label = "16:9 Landscape" if is_bible else "3:4 Portrait"

        pid = custom_pid or flow_adapter.default_project_id
        confirm_md = (
            f"### ⚠️ Xác nhận Tạo ảnh Reference bằng Nano Banana Pro\n\n"
            f"Tạo ảnh reference cho **{c.name}** (`{char_id}`)\n\n"
            f"- **Định dạng:** {mode_label}\n"
            f"- **Tỉ lệ khung hình:** `{aspect_label}`\n"
            f"- **Model:** Nano Banana Pro\n"
            f"- **Requests:** 1\n"
            f"- **Flow Project:** `{pid}`"
        )
        return gr.update(visible=True), confirm_md, ""

    def _on_confirm_gen_char_ref(char_id, custom_pid, project_dir_str, ref_type_str):
        if not char_id:
            return (gr.update(), gr.update(), gr.update(), gr.update(), gr.update(visible=False), "⚠️ Chưa chọn nhân vật.", gr.update())

        p_dir = Path(project_dir_str) if project_dir_str else Path("projects/sau_canh_cua_-_episode_01_v9_1_master_reference")
        asset_mgr = VisualAssetManager(p_dir) if p_dir.exists() else None
        char_lib = load_character_library()
        preset = load_visual_preset("sau_canh_cua")

        banana = BananaClient(flow_adapter, asset_mgr, char_lib, preset=preset)
        try:
            ref_mode = "CHARACTER_BIBLE" if (ref_type_str == "Character Bible (16:9)") else "PORTRAIT"
            new_ref_path = banana.generate_character_reference(
                char_id=char_id,
                project_id=custom_pid or "",
                reference_type=ref_mode,
                confirmed=True
            )
            img_val, header_md, status_md, details_md, _, _, _ = _on_load_char_ref(char_id)
            fmt_desc = "Character Bible (16:9)" if ref_mode == "CHARACTER_BIBLE" else "Chân dung (3:4)"
            success_msg = f"✨ Đã tạo thành công ảnh reference `{fmt_desc}`: `{new_ref_path.name}` (Trạng thái: AWAITING_REVIEW. Bấm 'Phê duyệt' để kích hoạt làm active reference)."
            return (
                img_val,
                header_md,
                status_md,
                details_md,
                gr.update(visible=False),
                success_msg,
                _build_char_lib_table()
            )
        except Exception as e:
            logger.exception("Error generating character reference: %s", e)
            return (
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(),
                gr.update(visible=False),
                f"❌ Lỗi: {e}",
                gr.update()
            )

    def _on_approve_char_ref(char_id):
        if not char_id:
            return gr.update(), gr.update(), gr.update(), gr.update(), "⚠️ Chưa chọn nhân vật", gr.update()
        approve_character_reference(char_id)
        img_val, header_md, status_md, details_md, _, _, _ = _on_load_char_ref(char_id)
        return img_val, header_md, status_md, details_md, "✅ Đã phê duyệt nhân vật thành công! Reference đã sẵn sàng.", _build_char_lib_table()

    def _on_reject_char_ref(char_id):
        if not char_id:
            return gr.update(), gr.update(), gr.update(), gr.update(), "⚠️ Chưa chọn nhân vật", gr.update()
        reject_character_reference(char_id)
        img_val, header_md, status_md, details_md, _, _, _ = _on_load_char_ref(char_id)
        return img_val, header_md, status_md, details_md, "❌ Đã từ chối nhân vật.", _build_char_lib_table()

    def _on_upload_custom_ref(char_id, file_obj):
        if not char_id or not file_obj:
            return gr.update(), gr.update(), gr.update(), gr.update(), "⚠️ Chưa có tệp tải lên", gr.update()
        upload_custom_character_reference(char_id, file_obj.name)
        img_val, header_md, status_md, details_md, _, _, _ = _on_load_char_ref(char_id)
        return img_val, header_md, status_md, details_md, "📁 Đã tải lên ảnh riêng thành công (Trạng thái: AWAITING_REVIEW). Bấm 'Phê duyệt' để áp dụng.", _build_char_lib_table()

    c["btn_load_char_ref"].click(
        fn=_on_load_char_ref,
        inputs=[c["char_select_dd"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_confirm_box"],
            c["upload_char_ref_file"],
            c["char_ref_action_status_md"]
        ]
    )
    c["char_select_dd"].change(
        fn=_on_load_char_ref,
        inputs=[c["char_select_dd"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_confirm_box"],
            c["upload_char_ref_file"],
            c["char_ref_action_status_md"]
        ]
    )
    c["btn_gen_char_ref"].click(
        fn=_on_request_gen_char_ref,
        inputs=[c["char_select_dd"], c["flow_project_id_txt"], c["char_ref_type_dd"]],
        outputs=[c["char_ref_confirm_box"], c["char_ref_confirm_msg_md"], c["char_ref_action_status_md"]]
    )
    c["btn_regen_char_ref"].click(
        fn=_on_request_gen_char_ref,
        inputs=[c["char_select_dd"], c["flow_project_id_txt"], c["char_ref_type_dd"]],
        outputs=[c["char_ref_confirm_box"], c["char_ref_confirm_msg_md"], c["char_ref_action_status_md"]]
    )
    c["btn_cancel_char_gen"].click(
        fn=lambda: gr.update(visible=False),
        outputs=[c["char_ref_confirm_box"]]
    )
    c["btn_confirm_char_gen"].click(
        fn=_on_confirm_gen_char_ref,
        inputs=[c["char_select_dd"], c["flow_project_id_txt"], c["story_project_dir_state"], c["char_ref_type_dd"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_confirm_box"],
            c["char_ref_action_status_md"],
            c["char_lib_table"]
        ]
    )
    c["btn_toggle_upload"].click(
        fn=lambda: gr.update(visible=True),
        outputs=[c["upload_char_ref_file"]]
    )
    c["upload_char_ref_file"].upload(
        fn=_on_upload_custom_ref,
        inputs=[c["char_select_dd"], c["upload_char_ref_file"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_action_status_md"],
            c["char_lib_table"]
        ]
    )
    c["btn_approve_char_ref"].click(
        fn=_on_approve_char_ref,
        inputs=[c["char_select_dd"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_action_status_md"],
            c["char_lib_table"]
        ]
    )
    c["btn_reject_char_ref"].click(
        fn=_on_reject_char_ref,
        inputs=[c["char_select_dd"]],
        outputs=[
            c["char_ref_portrait_img"],
            c["char_card_header_md"],
            c["char_ref_status_md"],
            c["char_ref_details_md"],
            c["char_ref_action_status_md"],
            c["char_lib_table"]
        ]
    )

    def _build_loc_lib_table():
        locs = load_location_library()
        rows = []
        for lid, l in locs.items():
            rec_str = "🔄 RECURRING" if getattr(l, "is_recurring", False) else "Standard"
            rows.append([
                l.location_id,
                l.name,
                rec_str,
                l.description or "-",
                l.visual_style or "-",
                l.lighting_default or "-"
            ])
        return rows

    c["btn_refresh_char_lib"].click(
        fn=_build_char_lib_table,
        outputs=[c["char_lib_table"]]
    )
    c["btn_refresh_loc_lib"].click(
        fn=_build_loc_lib_table,
        outputs=[c["loc_lib_table"]]
    )

    def _render_visual_progress_md(asset_mgr: VisualAssetManager, summary=None):
        prog = asset_mgr.get_progress()
        render_text = "✅ Sẵn sàng render" if prog["ready_to_render"] else "⏳ Đang chuẩn bị assets"
        val_text = "✅ Hợp lệ (100% timeline, 0 gaps)" if (summary and summary.is_valid) else ("⚠️ Cần kiểm tra" if (summary and summary.validation_issues) else "Chưa phân tích")
        dur_str = ""
        if summary and summary.omni_duration_distribution:
            dur_str = f" (4s: {summary.omni_duration_distribution.get('4s', 0)}, 6s: {summary.omni_duration_distribution.get('6s', 0)}, 8s: {summary.omni_duration_distribution.get('8s', 0)}, 10s: {summary.omni_duration_distribution.get('10s', 0)})"

        return (
            f"### 📊 Tiến độ Visual Episode\n"
            f"- **Số cảnh (Scenes):** {prog['total_scenes']} | **Kiểm định:** {val_text}\n"
            f"- **Keyframe Banana Pro:** {prog['images_ready']}/{prog['total_scenes']}\n"
            f"- **Clip Omni Flash Video:** {prog['videos_ready']}/{prog['veo_required']}{dur_str}\n"
            f"- **Lỗi / Cần retry:** {prog['failed']}\n"
            f"- **Xuất bản Final MP4:** **{render_text}**"
        )

    def _build_scenes_table_data(scenes: List[VisualScene], asset_mgr: VisualAssetManager):
        queue = asset_mgr.load_queue()
        rows = []
        for s in scenes:
            q_item = queue.get(s.scene_id)
            img_st = q_item.image_status if q_item else "PLANNED"
            vid_st = q_item.video_status if q_item else ("PLANNED" if s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V") else "-")
            status_display = f"Img: {img_st} | Vid: {vid_st}"
            chars_str = ", ".join(s.characters) if s.characters else "-"
            timeline_str = f"{s.start_sec:.1f}s - {s.end_sec:.1f}s ({s.duration_sec:.1f}s)"
            dur_str = f"{s.video_duration_sec}s" if s.video_duration_sec else "-"
            rows.append([
                s.scene_id,
                timeline_str,
                s.story_beat or s.story_context or "-",
                chars_str,
                s.location or "-",
                s.visual_type,
                s.motion or "-",
                dur_str,
                s.story_importance or "MEDIUM",
                status_display
            ])
        return rows

    # Button refresh flow connection
    c["btn_refresh_flow_conn"].click(
        fn=_render_flow_status_md,
        outputs=[c["visual_flow_status_md"]]
    )

    # 1. Analyze Visual & Plan Scenes
    def _on_analyze_visual(project_dir_str, timeline_events):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update(), [], gr.update(choices=[], value=None)
        p_dir = Path(project_dir_str)
        audio_master = p_dir / "master/final_mix.wav"
        if not audio_master.exists():
            audio_master = p_dir / "master/voice_master.wav"

        total_audio_sec = 0.0
        if audio_master.exists():
            import soundfile as sf
            total_audio_sec = sf.info(str(audio_master)).duration

        if total_audio_sec == 0.0 and timeline_events:
            total_audio_sec = timeline_events[-1].get("speech_end_sec", 0.0)

        if total_audio_sec == 0.0:
            return "⚠️ Chưa có Clean Voice Master / Final Mix. Vui lòng bấm Build Voice Master trước.", gr.update(), gr.update(), [], gr.update(choices=[], value=None)

        planner = VisualPlanner(preset_name="sau_canh_cua")
        scenes = planner.plan_episode_visuals(
            timeline_events=timeline_events,
            total_audio_sec=total_audio_sec,
            project_dir=p_dir
        )
        planner.save_plan(scenes, p_dir)

        asset_mgr = VisualAssetManager(p_dir)
        asset_mgr.sync_queue_with_plan(scenes)

        summary = planner.summarize_plan(scenes, total_audio_sec)
        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr, summary)

        scene_choices = [f"{s.scene_id}: {s.story_beat[:35]} ({s.visual_type})" for s in scenes]
        first_choice = scene_choices[0] if scene_choices else None
        dropdown_update = gr.update(choices=scene_choices, value=first_choice)

        status_log = (
            f"✅ **Phân tích Visual Hoàn tất (Phase 2):** {len(scenes)} scenes | "
            f"Banana Pro: {summary.banana_images_count} | Omni Flash: {summary.omni_videos_count} | "
            f"Durations: {summary.omni_duration_distribution} | "
            f"Coverage: {summary.timeline_coverage_pct}% ({summary.total_timeline_sec:.1f}s) | "
            f"Validation: {'PASS (0 lỗi)' if summary.is_valid else f'WARN ({len(summary.validation_issues)} cảnh báo)'}"
        )

        return status_log, progress_md, table_rows, scenes, dropdown_update

    c["btn_analyze_visual"].click(
        fn=_on_analyze_visual,
        inputs=[c["story_project_dir_state"], c["story_timeline_events_state"]],
        outputs=[
            c["visual_status_log_md"],
            c["visual_progress_md"],
            c["visual_scenes_table"],
            c["story_visual_scenes_state"],
            c["scene_select_dd"]
        ]
    )

    # Scene Inspector & Edit Handlers
    def _on_select_scene_detail(scene_choice, scenes_state, project_dir_str):
        if not scene_choice:
            return "", "MEDIUM", "BANANA_IMAGE", "-", "", "", "", "", "Chưa chọn scene."
        scene_id = scene_choice.split(":")[0].strip()

        scenes = scenes_state
        if not scenes and project_dir_str:
            plan_file = Path(project_dir_str) / "visual/visual_plan.json"
            if plan_file.exists():
                with open(plan_file, "r", encoding="utf-8") as f:
                    scenes = [VisualScene(**d) for d in json.load(f).get("scenes", [])]

        selected = next((s for s in (scenes or []) if (s.scene_id if hasattr(s, "scene_id") else s.get("scene_id")) == scene_id), None)
        if not selected:
            return "", "MEDIUM", "BANANA_IMAGE", "-", "", "", "", "", f"Không tìm thấy scene {scene_id}."

        if isinstance(selected, dict):
            s = VisualScene(**selected)
        else:
            s = selected

        dur_val = f"{s.video_duration_sec}s" if s.video_duration_sec else "-"
        chars_val = ", ".join(s.characters) if s.characters else ""
        status_md = f"ℹ️ Đang xem **{s.scene_id}** [{s.start_sec:.1f}s - {s.end_sec:.1f}s] ({s.duration_sec:.1f}s) — *{s.story_beat}*"

        return (
            s.story_beat,
            s.story_importance,
            s.visual_type,
            dur_val,
            chars_val,
            s.location,
            s.image_prompt,
            s.video_prompt or "",
            status_md
        )

    c["scene_select_dd"].change(
        fn=_on_select_scene_detail,
        inputs=[c["scene_select_dd"], c["story_visual_scenes_state"], c["story_project_dir_state"]],
        outputs=[
            c["scene_edit_beat"],
            c["scene_edit_importance"],
            c["scene_edit_type"],
            c["scene_edit_duration"],
            c["scene_edit_chars"],
            c["scene_edit_location"],
            c["scene_edit_image_prompt"],
            c["scene_edit_motion_prompt"],
            c["scene_edit_status_md"]
        ]
    )
    c["btn_refresh_scene_details"].click(
        fn=_on_select_scene_detail,
        inputs=[c["scene_select_dd"], c["story_visual_scenes_state"], c["story_project_dir_state"]],
        outputs=[
            c["scene_edit_beat"],
            c["scene_edit_importance"],
            c["scene_edit_type"],
            c["scene_edit_duration"],
            c["scene_edit_chars"],
            c["scene_edit_location"],
            c["scene_edit_image_prompt"],
            c["scene_edit_motion_prompt"],
            c["scene_edit_status_md"]
        ]
    )

    def _on_save_scene_edit(project_dir_str, scenes_state, scene_choice, edit_beat, edit_importance, edit_type, edit_duration, edit_chars, edit_location, edit_img_prompt, edit_vid_prompt):
        if not scene_choice:
            return "⚠️ Chưa chọn scene.", gr.update(), scenes_state
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), scenes_state

        p_dir = Path(project_dir_str)
        scene_id = scene_choice.split(":")[0].strip()

        # Load current scenes
        scenes = []
        if scenes_state:
            for item in scenes_state:
                scenes.append(VisualScene(**item) if isinstance(item, dict) else item)
        else:
            plan_file = p_dir / "visual/visual_plan.json"
            if plan_file.exists():
                with open(plan_file, "r", encoding="utf-8") as f:
                    scenes = [VisualScene(**d) for d in json.load(f).get("scenes", [])]

        target = next((s for s in scenes if s.scene_id == scene_id), None)
        if not target:
            return f"⚠️ Không tìm thấy scene {scene_id} để lưu.", gr.update(), scenes

        # Update target scene
        target.story_beat = edit_beat
        target.story_importance = edit_importance
        target.visual_type = edit_type
        if edit_duration and edit_duration != "-":
            try:
                target.video_duration_sec = int(edit_duration.replace("s", ""))
            except ValueError:
                target.video_duration_sec = None
        else:
            target.video_duration_sec = None

        target.characters = [c.strip() for c in edit_chars.split(",") if c.strip()]
        target.location = edit_location.strip()
        target.image_prompt = edit_img_prompt
        target.video_prompt = edit_vid_prompt.strip() if edit_vid_prompt and edit_vid_prompt.strip() else None

        # Persist to disk
        planner = VisualPlanner(preset_name="sau_canh_cua")
        planner.save_plan(scenes, p_dir)

        asset_mgr = VisualAssetManager(p_dir)
        asset_mgr.sync_queue_with_plan(scenes)

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        status_md = f"✅ Đã lưu thành công chỉnh sửa cho **{scene_id}** và cập nhật `visual_plan.json`."

        return status_md, table_rows, scenes

    c["btn_save_scene_edit"].click(
        fn=_on_save_scene_edit,
        inputs=[
            c["story_project_dir_state"],
            c["story_visual_scenes_state"],
            c["scene_select_dd"],
            c["scene_edit_beat"],
            c["scene_edit_importance"],
            c["scene_edit_type"],
            c["scene_edit_duration"],
            c["scene_edit_chars"],
            c["scene_edit_location"],
            c["scene_edit_image_prompt"],
            c["scene_edit_motion_prompt"]
        ],
        outputs=[c["scene_edit_status_md"], c["visual_scenes_table"], c["story_visual_scenes_state"]]
    )

    # 2. Generate All Images (Banana Pro) - Gated by Pilot Approval
    def _on_gen_all_images(project_dir_str, scenes_state, custom_pid):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists():
            return "⚠️ Chưa có kế hoạch visual. Hãy bấm 'Phân tích Visual' trước.", gr.update(), gr.update()

        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]

        preset = load_visual_preset("sau_canh_cua")
        char_lib = load_character_library()
        asset_mgr = VisualAssetManager(p_dir)

        # Gatekeeper: Check Pilot Lock
        unlocked, lock_info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
        if not unlocked:
            return (
                f"🔒 KHÓA GENERATE ALL: {lock_info['reason']} (Approved Keyframes: {lock_info['pilot_keyframes_approved']}, Approved Videos: {lock_info['pilot_videos_approved']}). Vui lòng hoàn thành kiểm định Pilot 8 scenes trước!",
                gr.update(),
                gr.update()
            )

        resolved_pid = resolve_flow_project_id(
            ui_project_id=custom_pid,
            visual_preset=preset,
            adapter_default=flow_adapter.default_project_id
        )
        banana_client = BananaClient(flow_adapter, asset_mgr, char_lib, preset=preset)
        res = banana_client.generate_all_keyframes(scenes, project_id=resolved_pid)

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr)
        status_log = f"🎨 Đã xử lý {res['total_requested']} scenes trên Flow project `{resolved_pid}`: {res['success']} thành công, {res['failed']} lỗi."

        return status_log, progress_md, table_rows

    c["btn_gen_all_images"].click(
        fn=_on_gen_all_images,
        inputs=[c["story_project_dir_state"], c["story_visual_scenes_state"], c["flow_project_id_txt"]],
        outputs=[c["visual_status_log_md"], c["visual_progress_md"], c["visual_scenes_table"]]
    )

    # 3. Generate Selected Videos (Omni 1.1 Flash) - Gated by Pilot Approval
    def _on_gen_veo_videos(project_dir_str, scenes_state, custom_pid, ui_duration, ui_model):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists():
            return "⚠️ Chưa có kế hoạch visual.", gr.update(), gr.update()

        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]

        preset = load_visual_preset("sau_canh_cua")
        char_lib = load_character_library()
        asset_mgr = VisualAssetManager(p_dir)

        # Gatekeeper: Check Pilot Lock
        unlocked, lock_info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
        if not unlocked:
            return (
                f"🔒 KHÓA GENERATE ALL: {lock_info['reason']} (Approved Keyframes: {lock_info['pilot_keyframes_approved']}, Approved Videos: {lock_info['pilot_videos_approved']}). Vui lòng hoàn thành kiểm định Pilot 8 scenes trước!",
                gr.update(),
                gr.update()
            )

        resolved_pid = resolve_flow_project_id(
            ui_project_id=custom_pid,
            visual_preset=preset,
            adapter_default=flow_adapter.default_project_id
        )
        resolved_model = resolve_video_model(ui_model=ui_model, preset=preset)
        resolved_duration = resolve_video_duration(ui_duration=ui_duration, preset=preset)

        video_client = VeoClient(
            flow_adapter, asset_mgr,
            model_family=resolved_model,
            duration_s=resolved_duration,
            preset=preset
        )

        video_scenes = [s for s in scenes if s.visual_type in ("VEO_I2V", "VIDEO_CLIP", "OMNI_FLASH_I2V")]
        for sc in video_scenes:
            video_client.generate_scene_video(
                sc, project_id=resolved_pid, duration_s=resolved_duration, allow_fallback=True
            )

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr)
        status_log = f"🎥 Đã xử lý {len(video_scenes)} cảnh video trên Flow project `{resolved_pid}` bằng {ui_model} ({resolved_duration}s)."

        return status_log, progress_md, table_rows

    c["btn_gen_veo_videos"].click(
        fn=_on_gen_veo_videos,
        inputs=[
            c["story_project_dir_state"],
            c["story_visual_scenes_state"],
            c["flow_project_id_txt"],
            c["video_duration_radio"],
            c["video_model_dd"],
        ],
        outputs=[c["visual_status_log_md"], c["visual_progress_md"], c["visual_scenes_table"]]
    )

    # 3.5. Phase 3 Pilot Event Handlers
    def _render_pilot_gate_status_md(asset_mgr: VisualAssetManager, project_dir: Optional[Path] = None):
        char_lib = load_character_library()
        scenes = []
        p_dir = project_dir or asset_mgr.project_dir
        if p_dir:
            plan_file = Path(p_dir) / "visual/visual_plan.json"
            if plan_file.exists():
                try:
                    with open(plan_file, "r", encoding="utf-8") as f:
                        scenes = [VisualScene(**d) for d in json.load(f).get("scenes", [])]
                except Exception:
                    scenes = []
        unlocked, info = asset_mgr.is_full_generation_unlocked(scenes, char_lib)
        badge = "🔓 **ĐÃ MỞ KHÓA GENERATE ALL**" if unlocked else "🔒 **ĐANG KHÓA GENERATE ALL (PILOT REQUIRED)**"
        color = "#10b981" if unlocked else "#f59e0b"
        hash_status = "✅ Hợp lệ (Deterministic Hash)" if info.get("semantic_hash_valid") else "❌ Không khớp (Kế hoạch bị sửa đổi post-QC)"
        num_omni = len(info.get("pilot_omni_ids", []))
        chars_status = "✅ 4/4 Sẵn sàng & Đã duyệt" if info.get("characters_approved") else "❌ Cần phê duyệt đủ 4/4 nhân vật"
        return (
            f"### <span style='color: {color};'>{badge}</span>\n"
            f"- **Nhân vật Reference:** {chars_status}\n"
            f"- **Semantic Hash QC:** {hash_status}\n"
            f"- **Pilot Keyframes Approved:** {info.get('pilot_keyframes_approved', '0/8')} (Yêu cầu 8/8)\n"
            f"- **Pilot Omni Videos Approved:** {info.get('pilot_videos_approved', f'0/{num_omni}')} (Yêu cầu {num_omni}/{num_omni})\n"
            f"- **Lỗi Semantic nghiêm trọng:** {info.get('critical_failures', 0)}\n"
            f"- **Trạng thái:** *{info.get('reason', '')}*"
        )

    def _on_calc_pilot_cost(project_dir_str):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án."
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists():
            return "⚠️ Chưa có file visual_plan.json."
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]
        asset_mgr = VisualAssetManager(p_dir)
        from apps.visual_engine.visual_planner import PILOT_SCENE_IDS
        cost = asset_mgr.calculate_batch_credit_cost(scenes, target_scene_ids=PILOT_SCENE_IDS)
        scenes_map = {s.scene_id: s for s in scenes}
        pilot_omni_scenes = [scenes_map[pid] for pid in PILOT_SCENE_IDS if pid in scenes_map and scenes_map[pid].visual_type in ("OMNI_FLASH_I2V", "VEO_I2V")]
        omni_desc = ", ".join([f"{s.scene_id} ({s.video_duration_sec}s)" for s in pilot_omni_scenes])
        total_omni_s = sum(s.video_duration_sec or 0 for s in pilot_omni_scenes)
        return (
            f"### 💰 Dự tính Credits cho Pilot Review (Section 27)\n"
            f"- **Scenes Pilot:** 8 scenes ({', '.join(PILOT_SCENE_IDS)})\n"
            f"- **Banana Pro Keyframes:** {cost['banana_requests']} requests (8 keyframes)\n"
            f"- **Omni 1.1 Flash Videos:** {cost['omni_requests']} requests ({omni_desc}) — Tổng {total_omni_s}s video\n"
            f"- **Tổng Requests dự kiến:** {cost['total_requests']}\n"
            f"*Xác nhận: Bấm nút 'Sinh 8 Pilot Keyframes' hoặc 'Sinh {cost['omni_requests']} Pilot Videos' để bắt đầu.*"
        )

    c["btn_calc_pilot_cost"].click(
        fn=_on_calc_pilot_cost,
        inputs=[c["story_project_dir_state"]],
        outputs=[c["pilot_cost_info_md"]]
    )

    def _on_gen_pilot_keyframes(project_dir_str, custom_pid):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists():
            return "⚠️ Chưa có kế hoạch visual.", gr.update(), gr.update(), gr.update()
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]
        preset = load_visual_preset("sau_canh_cua")
        char_lib = load_character_library()
        asset_mgr = VisualAssetManager(p_dir)

        # Gatekeeper: Character Approval Gate
        pilot_unlocked, pilot_gate_info = asset_mgr.is_pilot_generation_unlocked(char_lib)
        if not pilot_unlocked:
            gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
            return f"🔒 KHÓA PILOT GENERATION: {pilot_gate_info['reason']}", gr.update(), gr.update(), gate_md

        resolved_pid = resolve_flow_project_id(
            ui_project_id=custom_pid, visual_preset=preset, adapter_default=flow_adapter.default_project_id
        )
        banana_client = BananaClient(flow_adapter, asset_mgr, char_lib, preset=preset)
        from apps.visual_engine.visual_planner import PILOT_SCENE_IDS
        pilot_scenes = [s for s in scenes if s.scene_id in PILOT_SCENE_IDS]

        success_count = 0
        for sc in pilot_scenes:
            item = banana_client.generate_scene_keyframe(sc, project_id=resolved_pid, force_regenerate=True)
            if item.image_status in ("DONE", "AWAITING_QC"):
                success_count += 1

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        status_log = f"🎨 Đã sinh {success_count}/{len(pilot_scenes)} Pilot Keyframes trên Flow `{resolved_pid}`. Trạng thái hiện tại: AWAITING_QC (cần người dùng phê duyệt)."
        return status_log, progress_md, table_rows, gate_md

    c["btn_gen_pilot_keyframes"].click(
        fn=_on_gen_pilot_keyframes,
        inputs=[c["story_project_dir_state"], c["flow_project_id_txt"]],
        outputs=[c["visual_status_log_md"], c["visual_progress_md"], c["visual_scenes_table"], c["pilot_gate_status_md"]]
    )

    def _on_gen_pilot_videos(project_dir_str, custom_pid, ui_duration, ui_model):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists():
            return "⚠️ Chưa có kế hoạch visual.", gr.update(), gr.update(), gr.update()
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]
        preset = load_visual_preset("sau_canh_cua")
        asset_mgr = VisualAssetManager(p_dir)
        resolved_pid = resolve_flow_project_id(
            ui_project_id=custom_pid, visual_preset=preset, adapter_default=flow_adapter.default_project_id
        )
        resolved_model = resolve_video_model(ui_model=ui_model, preset=preset)
        resolved_duration = resolve_video_duration(ui_duration=ui_duration, preset=preset)
        video_client = VeoClient(
            flow_adapter, asset_mgr, model_family=resolved_model, duration_s=resolved_duration, preset=preset
        )

        from apps.visual_engine.visual_planner import PILOT_SCENE_IDS
        pilot_omni_scenes = [
            s for s in scenes
            if s.scene_id in PILOT_SCENE_IDS and s.visual_type in ("OMNI_FLASH_I2V", "VEO_I2V")
        ]
        success_count = 0
        err_msgs = []
        for sc in pilot_omni_scenes:
            try:
                item = video_client.generate_scene_video(
                    sc, project_id=resolved_pid, duration_s=sc.video_duration_sec or resolved_duration, force_regenerate=True, allow_fallback=False
                )
                if item.video_status in ("DONE", "AWAITING_QC"):
                    success_count += 1
            except Exception as e:
                err_msgs.append(f"{sc.scene_id}: {str(e)}")

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        omni_names = ", ".join([s.scene_id for s in pilot_omni_scenes])
        status_log = f"🎥 Đã xử lý {success_count}/{len(pilot_omni_scenes)} Pilot Videos bằng {ui_model} ({omni_names})."
        if err_msgs:
            status_log += f" Lỗi: {'; '.join(err_msgs[:2])}"
        return status_log, progress_md, table_rows, gate_md

    c["btn_gen_pilot_videos"].click(
        fn=_on_gen_pilot_videos,
        inputs=[c["story_project_dir_state"], c["flow_project_id_txt"], c["video_duration_radio"], c["video_model_dd"]],
        outputs=[c["visual_status_log_md"], c["visual_progress_md"], c["visual_scenes_table"], c["pilot_gate_status_md"]]
    )

    def _on_refresh_pilot_status(project_dir_str):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án."
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        return _render_pilot_gate_status_md(asset_mgr, p_dir)

    c["btn_refresh_pilot_status"].click(
        fn=_on_refresh_pilot_status,
        inputs=[c["story_project_dir_state"]],
        outputs=[c["pilot_gate_status_md"]]
    )

    def _on_load_pilot_scene(project_dir_str, scene_id):
        if not project_dir_str or not scene_id:
            return None, "**Keyframe:** -", None, "**Video:** -", "", ""
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        queue = asset_mgr.load_queue()
        pilot_rep = asset_mgr.load_pilot_qc_status().get("scenes", {}).get(scene_id, {})

        meta_md = ""
        plan_file = p_dir / "visual/visual_plan.json"
        if plan_file.exists():
            try:
                with open(plan_file, "r", encoding="utf-8") as f:
                    plan_data = json.load(f)
                scenes = plan_data.get("scenes", [])
                target = next((s for s in scenes if s.get("scene_id") == scene_id), None)
                if target:
                    dur_str = f" | Video: {target.get('video_duration_sec')}s" if target.get("video_duration_sec") else ""
                    overlay_str = f"- **Text Overlay:** `{target.get('text_overlay_content')}`\n" if target.get("text_overlay_content") else ""
                    vis_chars = target.get("visible_characters") or []
                    ref_ids = [f"{c}_REF_V1" for c in vis_chars]
                    meta_md = (
                        f"### 📋 Metadata Scene {scene_id} *(Nguồn: visual_plan.json)*\n"
                        f"- **Story Beat:** {target.get('story_beat')}\n"
                        f"- **Nhân vật hiển thị:** {', '.join(vis_chars) or 'None (Object/Environment)'}\n"
                        f"- **Character Reference:** {', '.join(ref_ids) or 'N/A'}\n"
                        f"- **Bối cảnh:** `{target.get('location')}` | **Visual Type:** `{target.get('visual_type')}`{dur_str}\n"
                        f"{overlay_str}"
                        f"- **Prompt Banana:** *{target.get('image_prompt')}*\n"
                        f"- **Prompt Motion:** *{target.get('video_prompt') or 'N/A'}*"
                    )
            except Exception as e:
                meta_md = f"⚠️ Lỗi đọc metadata: {e}"

        q_item = queue.get(scene_id)
        img_p = asset_mgr.images_dir / f"{scene_id}.jpg"
        img_val = str(img_p) if (img_p.exists() and img_p.stat().st_size > 0) else None

        vid_p = asset_mgr.videos_dir / f"{scene_id}.mp4"
        vid_val = str(vid_p) if (vid_p.exists() and vid_p.stat().st_size > 0) else None

        img_st = q_item.image_status if q_item else "PLANNED"
        img_qc = q_item.image_qc_status if q_item else "NONE"
        vid_st = q_item.video_status if q_item else "PLANNED"
        vid_qc = q_item.video_qc_status if q_item else "NONE"
        stale = q_item.stale_reason if q_item else None

        img_md = f"**Status:** {img_st} | **QC:** `{img_qc}`"
        if stale:
            img_md += f" | ⚠️ *{stale}*"

        vid_md = f"**Status:** {vid_st} | **QC:** `{vid_qc}`"
        notes = pilot_rep.get("image_notes") or pilot_rep.get("video_notes") or ""

        return img_val, img_md, vid_val, vid_md, notes, meta_md

    c["btn_load_pilot_scene"].click(
        fn=_on_load_pilot_scene,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"]],
        outputs=[c["pilot_keyframe_img"], c["pilot_keyframe_status_md"], c["pilot_video_player"], c["pilot_video_status_md"], c["pilot_review_notes_txt"], c["pilot_scene_metadata_md"]]
    )
    c["pilot_scene_select_dd"].change(
        fn=_on_load_pilot_scene,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"]],
        outputs=[c["pilot_keyframe_img"], c["pilot_keyframe_status_md"], c["pilot_video_player"], c["pilot_video_status_md"], c["pilot_review_notes_txt"], c["pilot_scene_metadata_md"]]
    )

    def _on_approve_pilot_keyframe(project_dir_str, scene_id, notes):
        if not project_dir_str or not scene_id:
            return "Chưa chọn scene", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        record_pilot_qc(asset_mgr, scene_id, "IMAGE", "APPROVED", notes=notes)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        plan_file = p_dir / "visual/visual_plan.json"
        table_rows = gr.update()
        if plan_file.exists():
            with open(plan_file, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
            scenes = [VisualScene(**d) for d in plan_data["scenes"]]
            table_rows = _build_scenes_table_data(scenes, asset_mgr)
        return "**Keyframe QC:** `APPROVED` ✅", gate_md, table_rows

    def _on_reject_pilot_keyframe(project_dir_str, scene_id, notes):
        if not project_dir_str or not scene_id:
            return "Chưa chọn scene", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        record_pilot_qc(asset_mgr, scene_id, "IMAGE", "REJECTED", notes=notes)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        return "**Keyframe QC:** `REJECTED` ❌", gate_md, gr.update()

    def _on_approve_pilot_video(project_dir_str, scene_id, notes):
        if not project_dir_str or not scene_id:
            return "Chưa chọn scene", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        record_pilot_qc(asset_mgr, scene_id, "VIDEO", "APPROVED", notes=notes)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        plan_file = p_dir / "visual/visual_plan.json"
        table_rows = gr.update()
        if plan_file.exists():
            with open(plan_file, "r", encoding="utf-8") as f:
                plan_data = json.load(f)
            scenes = [VisualScene(**d) for d in plan_data["scenes"]]
            table_rows = _build_scenes_table_data(scenes, asset_mgr)
        return "**Video QC:** `APPROVED` ✅", gate_md, table_rows

    def _on_reject_pilot_video(project_dir_str, scene_id, notes):
        if not project_dir_str or not scene_id:
            return "Chưa chọn scene", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        record_pilot_qc(asset_mgr, scene_id, "VIDEO", "REJECTED", notes=notes)
        gate_md = _render_pilot_gate_status_md(asset_mgr, p_dir)
        return "**Video QC:** `REJECTED` ❌", gate_md, gr.update()

    c["btn_approve_pilot_keyframe"].click(
        fn=_on_approve_pilot_keyframe,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"], c["pilot_review_notes_txt"]],
        outputs=[c["pilot_keyframe_status_md"], c["pilot_gate_status_md"], c["visual_scenes_table"]]
    )
    c["btn_reject_pilot_keyframe"].click(
        fn=_on_reject_pilot_keyframe,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"], c["pilot_review_notes_txt"]],
        outputs=[c["pilot_keyframe_status_md"], c["pilot_gate_status_md"], c["visual_scenes_table"]]
    )
    c["btn_approve_pilot_video"].click(
        fn=_on_approve_pilot_video,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"], c["pilot_review_notes_txt"]],
        outputs=[c["pilot_video_status_md"], c["pilot_gate_status_md"], c["visual_scenes_table"]]
    )
    c["btn_reject_pilot_video"].click(
        fn=_on_reject_pilot_video,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"], c["pilot_review_notes_txt"]],
        outputs=[c["pilot_video_status_md"], c["pilot_gate_status_md"], c["visual_scenes_table"]]
    )

    def _on_save_pilot_review(project_dir_str, scene_id, notes):
        if not project_dir_str or not scene_id:
            return "⚠️ Chưa tải dự án hoặc chưa chọn scene."
        p_dir = Path(project_dir_str)
        asset_mgr = VisualAssetManager(p_dir)
        report = asset_mgr.load_pilot_qc_status()
        s_data = report.setdefault("scenes", {}).setdefault(scene_id, {})
        s_data["notes"] = notes
        asset_mgr.save_pilot_qc_status(report)
        return f"💾 Đã lưu ghi chú review cho `{scene_id}` thành công."

    c["btn_save_pilot_review"].click(
        fn=_on_save_pilot_review,
        inputs=[c["story_project_dir_state"], c["pilot_scene_select_dd"], c["pilot_review_notes_txt"]],
        outputs=[c["pilot_cost_info_md"]]
    )

    # 4. Retry Failed
    def _on_retry_failed(project_dir_str, scenes_state, custom_pid, ui_duration, ui_model):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", gr.update(), gr.update()
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        if not plan_file.exists(): return "⚠️ Chưa có kế hoạch visual.", gr.update(), gr.update()

        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]

        preset = load_visual_preset("sau_canh_cua")
        resolved_pid = resolve_flow_project_id(
            ui_project_id=custom_pid,
            visual_preset=preset,
            adapter_default=flow_adapter.default_project_id
        )
        resolved_model = resolve_video_model(ui_model=ui_model, preset=preset)
        resolved_duration = resolve_video_duration(ui_duration=ui_duration, preset=preset)

        char_lib = load_character_library()
        asset_mgr = VisualAssetManager(p_dir)
        banana_client = BananaClient(flow_adapter, asset_mgr, char_lib, preset=preset)
        video_client = VeoClient(
            flow_adapter, asset_mgr,
            model_family=resolved_model,
            duration_s=resolved_duration,
            preset=preset
        )

        queue = asset_mgr.load_queue()
        retried = 0
        for sc in scenes:
            q_item = queue.get(sc.scene_id)
            if q_item and q_item.image_status == "FAILED":
                banana_client.generate_scene_keyframe(sc, project_id=resolved_pid, force_regenerate=True)
                retried += 1
            if q_item and q_item.video_status == "FAILED":
                video_client.generate_scene_video(
                    sc, project_id=resolved_pid, duration_s=resolved_duration, force_regenerate=True, allow_fallback=True
                )
                retried += 1

        table_rows = _build_scenes_table_data(scenes, asset_mgr)
        progress_md = _render_visual_progress_md(asset_mgr)
        status_log = f"🔄 Đã retry {retried} tác vụ bị lỗi trên Flow project `{resolved_pid}`."

        return status_log, progress_md, table_rows

    c["btn_retry_failed_visual"].click(
        fn=_on_retry_failed,
        inputs=[
            c["story_project_dir_state"],
            c["story_visual_scenes_state"],
            c["flow_project_id_txt"],
            c["video_duration_radio"],
            c["video_model_dd"],
        ],
        outputs=[c["visual_status_log_md"], c["visual_progress_md"], c["visual_scenes_table"]]
    )

    # 5. Render Final Episode MP4
    def _on_render_final_video(project_dir_str, scenes_state):
        if not project_dir_str:
            return "⚠️ Chưa tải dự án.", None, gr.update(visible=False)
        p_dir = Path(project_dir_str)
        plan_file = p_dir / "visual/visual_plan.json"
        audio_master = p_dir / "master/final_mix.wav"
        if not audio_master.exists():
            audio_master = p_dir / "master/voice_master.wav"

        if not plan_file.exists() or not audio_master.exists():
            return "⚠️ Thiếu kế hoạch visual hoặc file audio master (final_mix.wav).", None, gr.update(visible=False)

        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        scenes = [VisualScene(**d) for d in plan_data["scenes"]]

        asset_mgr = VisualAssetManager(p_dir)
        renderer = FinalVideoRenderer(asset_mgr)

        out_mp4 = p_dir / "final/final_episode.mp4"
        rendered_path = renderer.render_final_episode(
            scenes=scenes,
            audio_master_path=audio_master,
            output_mp4_path=out_mp4
        )

        sz_mb = rendered_path.stat().st_size / (1024 * 1024)
        status_log = f"🎉 Đã xuất bản thành công: {rendered_path.name} ({sz_mb:.1f} MB, 1080p 30fps)."
        return status_log, str(rendered_path), gr.update(value=str(rendered_path), visible=True)

    c["btn_render_final_video"].click(
        fn=_on_render_final_video,
        inputs=[c["story_project_dir_state"], c["story_visual_scenes_state"]],
        outputs=[c["visual_status_log_md"], c["final_episode_video"], c["final_episode_file_download"]]
    )

    # -------------------------------------------------------------
    # 🎬 ANTIGRAVITY — MANUAL VISUAL IMPORT & AUTO ASSEMBLE HANDLERS
    # -------------------------------------------------------------
    from apps.visual_engine.manual_visual_mode import (
        load_or_create_manifest,
        scan_project_assets,
        resolve_duplicate_asset,
        validate_manifest_for_assemble,
        assemble_manual_episode,
        get_manifest_dataframe,
    )

    def _on_load_manifest_ui(manifest_path, project_dir_str):
        p_dir = project_dir_str if project_dir_str else "projects/sau_canh_cua_ep01_v9_3_manual_visual"
        try:
            manifest = load_or_create_manifest(manifest_path=manifest_path, project_dir=p_dir)
            df_rows = get_manifest_dataframe(manifest)
            ready_cnt = sum(1 for s in manifest.scenes if s.qc_status == "READY" and s.chosen_asset)
            status_md = (
                f"### 📂 Đã nạp Manifest v{manifest.manifest_version}\n"
                f"- **Dự án:** `{manifest.project_slug}`\n"
                f"- **Nguồn Timeline:** `PROJECT_AUDIO_SEGMENTS` (Thời lượng: {manifest.total_duration_sec:.2f}s, Contiguous 100%)\n"
                f"- **Tổng scenes:** {len(manifest.scenes)} (Sẵn sàng: {ready_cnt}/{len(manifest.scenes)})\n"
                f"- **Master audio:** `{manifest.audio_master_path}`"
            )
            dup_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "DUPLICATE"]
            dup_box_vis = gr.update(visible=len(dup_scenes) > 0)
            dup_dd = gr.update(choices=dup_scenes, value=dup_scenes[0] if dup_scenes else None)
            return df_rows, status_md, manifest, dup_box_vis, dup_dd
        except Exception as exc:
            return [], f"❌ Lỗi nạp manifest: {exc}", None, gr.update(visible=False), gr.update(choices=[], value=None)

    def _on_scan_assets_ui(manifest_state, manifest_path, img_dir, vid_dir, project_dir_str):
        p_dir = project_dir_str if project_dir_str else "projects/sau_canh_cua_ep01_v9_3_manual_visual"
        manifest = manifest_state or load_or_create_manifest(manifest_path=manifest_path, project_dir=p_dir)
        try:
            manifest = scan_project_assets(
                manifest=manifest,
                project_dir=p_dir,
                images_dir=img_dir,
                videos_dir=vid_dir
            )
            df_rows = get_manifest_dataframe(manifest)
            ready_cnt = sum(1 for s in manifest.scenes if s.qc_status == "READY" and s.chosen_asset)
            dup_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "DUPLICATE"]
            missing_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "MISSING"]
            invalid_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "INVALID"]

            status_md = (
                f"### 🔍 Kết Quả Quét Tài Nguyên Visual (Case-insensitive SC_XXX)\n"
                f"- **Sẵn sàng (READY):** {ready_cnt}/{len(manifest.scenes)} scenes (Ưu tiên: Video > Image)\n"
                f"- **Thiếu tài nguyên (MISSING):** {len(missing_scenes)} scenes (Chặn render nếu thiếu)\n"
                f"- **Trùng lặp (DUPLICATE):** {len(dup_scenes)} scenes (Cần người dùng chọn file)\n"
                f"- **Tài nguyên hỏng (INVALID):** {len(invalid_scenes)} scenes"
            )
            dup_box_vis = gr.update(visible=len(dup_scenes) > 0)
            dup_dd = gr.update(choices=dup_scenes, value=dup_scenes[0] if dup_scenes else None)
            return df_rows, status_md, manifest, dup_box_vis, dup_dd
        except Exception as exc:
            return [], f"❌ Lỗi quét assets: {exc}", manifest_state, gr.update(visible=False), gr.update(choices=[], value=None)

    def _on_change_dup_scene_ui(manifest_state, scene_id):
        if not manifest_state or not scene_id:
            return gr.update(choices=[], value=None)
        sc = next((s for s in manifest_state.scenes if s.scene_id == scene_id), None)
        if not sc:
            return gr.update(choices=[], value=None)
        all_candidates = list(sc.matched_videos) + list(sc.matched_images)
        return gr.update(choices=all_candidates, value=all_candidates[0] if all_candidates else None)

    def _on_apply_dup_choice_ui(manifest_state, scene_id, chosen_file_path):
        if not manifest_state or not scene_id or not chosen_file_path:
            return gr.update(), "⚠️ Vui lòng chọn Scene và File tài nguyên.", manifest_state, gr.update(), gr.update()
        try:
            manifest = resolve_duplicate_asset(manifest_state, scene_id, chosen_file_path)
            df_rows = get_manifest_dataframe(manifest)
            dup_scenes = [s.scene_id for s in manifest.scenes if s.qc_status == "DUPLICATE"]
            status_md = f"✅ Đã chọn `{Path(chosen_file_path).name}` cho scene **{scene_id}**. Trùng lặp còn lại: {len(dup_scenes)}."
            dup_box_vis = gr.update(visible=len(dup_scenes) > 0)
            dup_dd = gr.update(choices=dup_scenes, value=dup_scenes[0] if dup_scenes else None)
            return df_rows, status_md, manifest, dup_box_vis, dup_dd
        except Exception as exc:
            return gr.update(), f"❌ Lỗi gán tài nguyên: {exc}", manifest_state, gr.update(), gr.update()

    def _on_validate_manual_ui(manifest_state, manifest_path, project_dir_str):
        p_dir = project_dir_str if project_dir_str else "projects/sau_canh_cua_ep01_v9_3_manual_visual"
        manifest = manifest_state or load_or_create_manifest(manifest_path=manifest_path, project_dir=p_dir)
        can_render, issues, stats = validate_manifest_for_assemble(manifest, project_dir=p_dir)

        if can_render:
            verdict = "### 🛡️ KẾT QUẢ KIỂM DUYỆT: ✅ PASS — ĐỦ ĐIỀU KIỆN AUTO ASSEMBLE\n"
        else:
            verdict = "### 🛡️ KẾT QUẢ KIỂM DUYỆT: ⛔ BLOCKED — CHƯA ĐỦ ĐIỀU KIỆN RENDER\n"

        details = [
            f"- **Tổng số cảnh:** {stats['total_scenes']}",
            f"- **Cảnh sẵn sàng:** {stats['ready_scenes']}/{stats['total_scenes']}",
            f"- **Cảnh thiếu tài nguyên:** {stats['missing_count']}",
            f"- **Cảnh trùng lặp cần chọn:** {stats['duplicate_count']}",
            f"- **Tài nguyên lỗi:** {stats['invalid_count']}",
            f"- **Timeline liên tục:** 100% (Khớp master audio `{Path(manifest.audio_master_path).name}`)"
        ]
        if issues:
            details.append("\n**Các vấn đề chặn render:**")
            for iss in issues:
                details.append(f"- ❌ {iss}")
        return verdict + "\n".join(details)

    def _on_toggle_preview_box():
        return gr.update(visible=True)

    def _on_load_scene_preview_ui(manifest_state, scene_id):
        if not manifest_state or not scene_id:
            return gr.update(visible=False), gr.update(visible=False), "⚠️ Chưa nạp manifest hoặc chưa chọn scene."
        sc = next((s for s in manifest_state.scenes if s.scene_id == scene_id), None)
        if not sc or not sc.chosen_asset or not Path(sc.chosen_asset).exists():
            return gr.update(visible=False), gr.update(visible=False), f"⚠️ Scene **{scene_id}** chưa có tài nguyên đã chọn ({sc.qc_status if sc else 'Unknown'})."

        chosen_p = Path(sc.chosen_asset)
        is_video = sc.chosen_type == "VIDEO" or chosen_p.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]

        ov_info = f"**Nội dung beat:** {sc.story_beat}\n\n**Thời lượng:** {sc.duration_sec:.2f}s ({sc.start_sec:.2f}s -> {sc.end_sec:.2f}s)"
        if sc.requires_text_overlay and sc.text_overlay_content:
            ov_info += f"\n\n**📝 Text Overlay (Hậu kỳ):** `{sc.text_overlay_content}`"

        if is_video:
            return gr.update(visible=False), gr.update(value=str(chosen_p), visible=True), ov_info
        else:
            return gr.update(value=str(chosen_p), visible=True), gr.update(visible=False), ov_info

    def _on_auto_assemble_ui(manifest_state, manifest_path, project_dir_str):
        p_dir = project_dir_str if project_dir_str else "projects/sau_canh_cua_ep01_v9_3_manual_visual"
        manifest = manifest_state or load_or_create_manifest(manifest_path=manifest_path, project_dir=p_dir)
        can_render, issues, stats = validate_manifest_for_assemble(manifest, project_dir=p_dir)
        if not can_render:
            err_msg = "⛔ **Auto Assemble bị chặn bởi các điều kiện an toàn:**\n" + "\n".join(f"- {iss}" for iss in issues)
            return err_msg, None, gr.update(visible=False)

        try:
            out_file = Path(p_dir) / "final" / "final_episode_manual_v9_3.mp4"
            rendered_path = assemble_manual_episode(manifest, output_mp4_path=out_file, project_dir=p_dir)
            sz_mb = rendered_path.stat().st_size / (1024 * 1024)
            status_msg = f"🎉 **Đã Auto Assemble thành công toàn bộ tập phim!**\n- File: `{rendered_path.name}` ({sz_mb:.1f} MB)\n- Độ phân giải: 1920x1080 @ 30fps H.264 / AAC 320kbps\n- Đã khử âm thanh gốc của video, multiplex master audio `{Path(manifest.audio_master_path).name}` hoàn hảo không có khoảng trống đen."
            return status_msg, str(rendered_path), gr.update(value=str(rendered_path), visible=True)
        except Exception as exc:
            return f"❌ Lỗi trong quá trình Auto Assemble: {exc}", None, gr.update(visible=False)

    # Wire up Manual Visual Mode buttons
    c["btn_load_manual_manifest"].click(
        fn=_on_load_manifest_ui,
        inputs=[c["manual_manifest_path_txt"], c["story_project_dir_state"]],
        outputs=[c["manual_manifest_df"], c["manual_summary_report_md"], c["manual_manifest_state"], c["manual_duplicate_box"], c["manual_dup_scene_dd"]]
    )

    c["btn_manual_scan_assets"].click(
        fn=_on_scan_assets_ui,
        inputs=[c["manual_manifest_state"], c["manual_manifest_path_txt"], c["manual_images_dir_txt"], c["manual_videos_dir_txt"], c["story_project_dir_state"]],
        outputs=[c["manual_manifest_df"], c["manual_summary_report_md"], c["manual_manifest_state"], c["manual_duplicate_box"], c["manual_dup_scene_dd"]]
    )

    c["manual_dup_scene_dd"].change(
        fn=_on_change_dup_scene_ui,
        inputs=[c["manual_manifest_state"], c["manual_dup_scene_dd"]],
        outputs=[c["manual_dup_file_dd"]]
    )

    c["btn_manual_apply_dup"].click(
        fn=_on_apply_dup_choice_ui,
        inputs=[c["manual_manifest_state"], c["manual_dup_scene_dd"], c["manual_dup_file_dd"]],
        outputs=[c["manual_manifest_df"], c["manual_summary_report_md"], c["manual_manifest_state"], c["manual_duplicate_box"], c["manual_dup_scene_dd"]]
    )

    c["btn_manual_validate"].click(
        fn=_on_validate_manual_ui,
        inputs=[c["manual_manifest_state"], c["manual_manifest_path_txt"], c["story_project_dir_state"]],
        outputs=[c["manual_summary_report_md"]]
    )

    c["btn_manual_preview"].click(
        fn=_on_toggle_preview_box,
        inputs=[],
        outputs=[c["manual_preview_box"]]
    )

    c["btn_load_scene_preview"].click(
        fn=_on_load_scene_preview_ui,
        inputs=[c["manual_manifest_state"], c["manual_preview_scene_dd"]],
        outputs=[c["manual_preview_image"], c["manual_preview_video"], c["manual_preview_overlay_md"]]
    )

    c["btn_manual_auto_assemble"].click(
        fn=_on_auto_assemble_ui,
        inputs=[c["manual_manifest_state"], c["manual_manifest_path_txt"], c["story_project_dir_state"]],
        outputs=[c["manual_summary_report_md"], c["final_episode_video"], c["final_episode_file_download"]]
    )


