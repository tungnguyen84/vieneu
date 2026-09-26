"""
Giao diện và xử lý sự kiện cho tính năng Production Script Storytelling JSON & TTS Audio Director.
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
from apps.audio_director import (
    safe_extract_zip,
    parse_music_library,
    build_music_library_table_data,
    build_audio_director_master,
    build_preview_mix_clip,
    build_preview_reveal_clip
)

MAX_STORY_CHARACTERS = 8

def render_production_story_ui(preset_voices_cache_getter):
    """
    Dựng giao diện cho sub-tab Production Script JSON & TTS Audio Director.
    preset_voices_cache_getter: hàm trả về PRESET_VOICES_CACHE hiện tại.
    """
    gr.Markdown(
        "## 🎬 TTS Audio Director — Production Storytelling Script (JSON V6)\n"
        "Quy trình sản xuất audio chuyên nghiệp cho video storytelling dài tập:\n"
        "- **Voice Director**: Quản lý giọng nhân vật trực quan, nghe thử từng giọng, multi-take, selective cache.\n"
        "- **Music Director**: Continuous underscore regions, crossfade mượt mà, dialogue ducking analog-style (-8 dB), "
        "im lặng tuyệt đối tại khoảnh khắc cao trào (Critical Reveal Silence Window).\n"
        "- **Ambience Engine**: Continuous Room Tone liền mạch chống giật khựng.\n"
        "- **Mastering Broadcast**: 2-pass Loudness Normalization (-14 LUFS, -1 dBTP), xuất WAV + MP3 và đầy đủ 4 Stem tracks."
    )

    # 1. Action Row
    with gr.Row():
        btn_import_pack_zip = gr.UploadButton("📦 Import Production Pack (.zip)", file_types=[".zip"], variant="primary")
        btn_import_json = gr.UploadButton("📂 Import Kịch bản JSON", file_types=[".json"], variant="secondary")
        btn_sample_pilot = gr.Button("📋 Nạp Kịch bản Pilot Mẫu (92 segments)", size="sm", variant="secondary")
        btn_export_json = gr.Button("💾 Xuất Project JSON", size="sm")
        file_export_download = gr.File(label="Tải file JSON đã xuất", visible=False)

    # 2. Project Info Banner
    story_project_info_md = gr.Markdown("*(Chưa tải kịch bản. Vui lòng bấm 'Import Production Pack (.zip)' hoặc 'Import Kịch bản JSON'.)*")
    story_warnings_md = gr.Markdown(visible=False)

    # Lấy toàn bộ preset voices hiện có
    initial_available_voices = get_all_available_voices()

    # 3. Characters Mapping Section
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

    # 4. Music Library & Ambience Section (NEW: TTS Audio Director)
    with gr.Accordion("🎵 2. Nhạc & Không gian (Music Library & Ambience)", open=True) as acc_music:
        gr.Markdown(
            "Thư viện nhạc nền và không gian phòng của tập phim (tự động nhận diện từ JSON / ZIP Pack). "
            "Nhạc nền trải dài qua các phân đoạn có cùng cue (continuous regions), tự động crossfade khi chuyển cue "
            "và ngắt âm im lặng hoàn toàn trước các phân đoạn then chốt (Critical Reveal)."
        )
        music_lib_headers = ["Mã Cue (ID)", "File âm thanh", "Target RMS (dB)", "Lặp (Loop)", "Thời lượng", "Trạng thái file"]
        music_library_df = gr.DataFrame(
            headers=music_lib_headers,
            datatype=["str", "str", "str", "str", "str", "str"],
            row_count=(1, "dynamic"),
            interactive=False,
            wrap=True
        )

        with gr.Row():
            music_cue_dropdown = gr.Dropdown(label="Chọn bản nhạc trong thư viện để nghe thử", choices=[], interactive=True, scale=3)
            btn_preview_music_cue = gr.Button("▶ Nghe thử track nhạc", size="sm", variant="secondary", scale=1)
        audio_music_preview = gr.Audio(label="Audio Player Nhạc nền", interactive=False)

    # 5. Segments Table Section
    with gr.Accordion("📜 3. Bảng Phân đoạn Kịch bản (Segment Editor & Table)", open=True):
        with gr.Row():
            btn_select_all = gr.Button("Chọn tất cả", size="sm")
            btn_select_failed = gr.Button("Chọn phân đoạn lỗi", size="sm")
            btn_select_multitake = gr.Button("Chọn phân đoạn Multi-take", size="sm")
            btn_deselect_all = gr.Button("Bỏ chọn tất cả", size="sm")

        with gr.Row():
            quick_cue_dropdown = gr.Dropdown(
                label="Gán nhanh Music Cue cho các phân đoạn đã tick chọn",
                choices=["none", "signature_intro", "mystery_low", "memory_soft", "tension_low", "emotional_low", "closing_soft", "signature_outro"],
                value="mystery_low",
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
            interactive=True,
            wrap=True
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

    # 8. Master Audio Assembly (TTS Audio Director)
    with gr.Accordion("🎛️ 6. Ghép & Xuất Master Audio (TTS Audio Director Engine)", open=True):
        with gr.Row():
            gap_rule_radio = gr.Radio(
                choices=[("Khuyến nghị: max(pause_after, next_pause_before)", "max"), ("Cộng dồn: pause_after + next_pause_before", "sum")],
                value="max",
                label="Quy tắc khoảng nghỉ (Tránh Double Pause)"
            )
            target_lufs_num = gr.Number(value=-14.0, label="Target Integrated LUFS (-14 LUFS)")
            true_peak_num = gr.Number(value=-1.0, label="True Peak (-1.0 dBTP)")

        with gr.Row():
            music_gain_slider = gr.Slider(minimum=-20.0, maximum=10.0, value=0.0, step=0.5, label="Âm lượng Nhạc nền Master Gain (dB)")
            room_tone_vol_slider = gr.Slider(minimum=-60.0, maximum=-20.0, value=-41.0, step=1.0, label="Âm lượng Room Tone (dBFS RMS)")
            ducking_db_slider = gr.Slider(minimum=-24.0, maximum=0.0, value=-8.0, step=0.5, label="Dialogue Ducking (dB)")
            crossfade_sec_slider = gr.Slider(minimum=0.2, maximum=3.0, value=1.2, step=0.1, label="Music Crossfade (giây)")
            reveal_delay_sec_slider = gr.Slider(minimum=0.2, maximum=3.0, value=0.8, step=0.1, label="Reveal Music Return Delay (giây)")

        with gr.Row():
            chk_enable_music = gr.Checkbox(label="Bật Nhạc nền (Continuous Underscore)", value=True)
            chk_enable_room_tone = gr.Checkbox(label="Bật Continuous Room Tone", value=True)
            chk_silence_critical = gr.Checkbox(label="Tự động im lặng trước Critical Reveal", value=True)

        # Previews Section
        gr.Markdown("### 🎧 Nghe thử Preview trước khi Ghép Toàn tập (Mix Previews)")
        with gr.Row():
            with gr.Column(scale=1):
                btn_preview_mix_30s = gr.Button("🎧 Nghe thử Mix 30s Mở đầu", size="sm", variant="secondary")
                preview_mix_30s_audio = gr.Audio(label="Preview Mix 30 giây", interactive=False)
            with gr.Column(scale=1):
                preview_reveal_seg_dd = gr.Dropdown(label="Chọn phân đoạn Critical Reveal", choices=[], interactive=True)
                btn_preview_reveal = gr.Button("🎧 Nghe thử khoảnh khắc Critical Reveal", size="sm", variant="secondary")
                preview_reveal_audio = gr.Audio(label="Preview Critical Reveal Window", interactive=False)

        gr.Markdown("---")
        btn_build_master = gr.Button("🎛️ Bắt đầu Ghép Master Audio (TTS Audio Director)", variant="primary", size="lg")
        master_status_md = gr.Markdown("")

        with gr.Row():
            master_wav_audio = gr.Audio(label="Master Audio WAV (48kHz 24-bit PCM)", interactive=False)
            master_mp3_audio = gr.Audio(label="Master Audio MP3 (320kbps)", interactive=False)

        with gr.Row():
            master_wav_download = gr.File(label="Tải file Master WAV", visible=False)
            master_mp3_download = gr.File(label="Tải file Master MP3", visible=False)

        # Stems Section
        with gr.Accordion("🎚️ Stem Tracks & Music Timeline (Xuất rời các kênh âm thanh)", open=False):
            gr.Markdown(
                "Các kênh âm thanh rời (Stems) đồng bộ hoàn hảo về thời lượng, sẵn sàng nhập vào DAW chuyên nghiệp "
                "(Pro Tools, Reaper, Premiere, DaVinci Resolve) nếu bạn muốn hậu kỳ nâng cao."
            )
            with gr.Row():
                stem_dialogue_audio = gr.Audio(label="🗣️ Dialogue Only Stem (WAV)", interactive=False)
                stem_room_tone_audio = gr.Audio(label="🍃 Room Tone Stem (WAV)", interactive=False)
            with gr.Row():
                stem_music_audio = gr.Audio(label="🎵 Music Underscore Stem (WAV)", interactive=False)
                stem_pre_master_audio = gr.Audio(label="🎚️ Pre-master Mix Stem (WAV)", interactive=False)

            with gr.Row():
                stem_timeline_file = gr.File(label="Tải Music Timeline JSON", visible=False)
                stem_dialogue_file = gr.File(label="Tải Dialogue WAV", visible=False)
                stem_room_tone_file = gr.File(label="Tải Room Tone WAV", visible=False)
                stem_music_file = gr.File(label="Tải Music WAV", visible=False)

    # State stores
    story_raw_json_state = gr.State(None)
    story_project_info_state = gr.State({})
    story_characters_state = gr.State({})
    story_segments_state = gr.State([])
    story_project_dir_state = gr.State(None)
    story_runtime_state = gr.State({})
    story_music_lib_state = gr.State({})

    components = {
        "btn_import_pack_zip": btn_import_pack_zip,
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
        "music_library_df": music_library_df,
        "music_cue_dropdown": music_cue_dropdown,
        "btn_preview_music_cue": btn_preview_music_cue,
        "audio_music_preview": audio_music_preview,
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
        "target_lufs_num": target_lufs_num,
        "true_peak_num": true_peak_num,
        "music_gain_slider": music_gain_slider,
        "room_tone_vol_slider": room_tone_vol_slider,
        "ducking_db_slider": ducking_db_slider,
        "crossfade_sec_slider": crossfade_sec_slider,
        "reveal_delay_sec_slider": reveal_delay_sec_slider,
        "chk_enable_music": chk_enable_music,
        "chk_enable_room_tone": chk_enable_room_tone,
        "chk_silence_critical": chk_silence_critical,
        "btn_preview_mix_30s": btn_preview_mix_30s,
        "preview_mix_30s_audio": preview_mix_30s_audio,
        "preview_reveal_seg_dd": preview_reveal_seg_dd,
        "btn_preview_reveal": btn_preview_reveal,
        "preview_reveal_audio": preview_reveal_audio,
        "btn_build_master": btn_build_master,
        "master_status_md": master_status_md,
        "master_wav_audio": master_wav_audio,
        "master_mp3_audio": master_mp3_audio,
        "master_wav_download": master_wav_download,
        "master_mp3_download": master_mp3_download,
        "stem_dialogue_audio": stem_dialogue_audio,
        "stem_room_tone_audio": stem_room_tone_audio,
        "stem_music_audio": stem_music_audio,
        "stem_pre_master_audio": stem_pre_master_audio,
        "stem_timeline_file": stem_timeline_file,
        "stem_dialogue_file": stem_dialogue_file,
        "stem_room_tone_file": stem_room_tone_file,
        "stem_music_file": stem_music_file,
        "story_raw_json_state": story_raw_json_state,
        "story_project_info_state": story_project_info_state,
        "story_characters_state": story_characters_state,
        "story_segments_state": story_segments_state,
        "story_project_dir_state": story_project_dir_state,
        "story_runtime_state": story_runtime_state,
        "story_music_lib_state": story_music_lib_state,
    }
    return components


def _get_empty_import_returns(error_message: str):
    """Trả về cấu trúc cập nhật rỗng khi có lỗi import."""
    return (
        error_message,
        gr.update(visible=False),
        *[gr.update(visible=False)] * MAX_STORY_CHARACTERS, # char_groups
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_headers
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_id
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_name
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_role
        *[gr.update(value=None)] * MAX_STORY_CHARACTERS,   # char_voice
        *[gr.update(value=1.0)] * MAX_STORY_CHARACTERS,    # char_speed
        *[gr.update(value="")] * MAX_STORY_CHARACTERS,     # char_status
        [],                                                # music_library_df
        gr.update(choices=[], value=None),                 # music_cue_dropdown
        gr.update(choices=[], value=None),                 # preview_reveal_seg_dd
        [],                                                # story_segments_df
        gr.update(choices=[], value=None),                 # preview_seg_dropdown
        None, {}, {}, [], None, {}, {}                     # states
    )


def process_loaded_story_project(data: dict, project_dir: Path, available_voices: list):
    """
    Xử lý cấu trúc dữ liệu JSON kịch bản, ánh xạ nhân vật, phân tích music library và cập nhật UI.
    """
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
        return _get_empty_import_returns(f"❌ Lỗi cấu trúc JSON: {err}")

    project_dir.mkdir(parents=True, exist_ok=True)

    # Tải hoặc khởi tạo runtime state
    runtime_state = load_or_init_project_state(project_dir, data)

    # Lưu source.json vào thư mục project
    with open(project_dir / "source.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Đọc và xác thực Music Library
    music_lib = parse_music_library(project_dir, data)
    music_df_rows = build_music_library_table_data(music_lib)
    music_cues_list = list(music_lib.keys())
    music_dd_update = gr.update(choices=music_cues_list, value=music_cues_list[0] if music_cues_list else None)

    # Thông tin project
    ready_cues = sum(1 for m in music_lib.values() if m.get("status") == "READY")
    info_md = (
        f"### 📖 Dự án: **{proj_info['title']}** — *{proj_info['episode_title']}*\n"
        f"- **Số phân đoạn (Segments):** {stats['segment_count']} | **Nhân vật:** {stats['character_count']} | "
        f"**Tổng số từ:** {stats['total_words']} từ\n"
        f"- **Thời lượng ước tính:** ~{stats['estimated_seconds']/60:.1f} phút ({int(stats['estimated_seconds'])} giây) | "
        f"**Tần số lấy mẫu:** {proj_info['sample_rate']}Hz | **Thư mục:** `{project_dir}`\n"
        f"- **Music Library:** {ready_cues}/{len(music_lib)} track nhạc sẵn sàng trong thư viện."
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

    # Dropdown options for preview take
    seg_choices = [f"[{s.get('id', idx+1):0>3}] {s.get('speaker', '')}: {s.get('text', '')[:40]}..." for idx, s in enumerate(segments)]
    preview_dd_update = gr.update(choices=seg_choices, value=seg_choices[0] if seg_choices else None)

    # Dropdown options for preview Critical Reveal
    crit_choices = [
        f"[{s.get('id', idx+1):0>3}] {s.get('speaker', '')}: {s.get('text', '')[:35]}..."
        for idx, s in enumerate(segments)
        if s.get("importance") == "critical" or s.get("is_critical")
    ]
    if not crit_choices:
        crit_choices = seg_choices[:10]
    default_reveal_val = None
    for c in crit_choices:
        if "037" in c:
            default_reveal_val = c
            break
    if not default_reveal_val and crit_choices:
        default_reveal_val = crit_choices[0]
    preview_reveal_update = gr.update(choices=crit_choices, value=default_reveal_val)

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
        music_df_rows,
        music_dd_update,
        preview_reveal_update,
        df_rows,
        preview_dd_update,
        data,
        proj_info,
        chars_map,
        segments,
        str(project_dir),
        runtime_state,
        music_lib
    )


def handle_import_json_data(json_content_or_file, available_voices: list):
    """Xử lý nạp file JSON kịch bản."""
    if not json_content_or_file:
        return _get_empty_import_returns("⚠️ Vui lòng chọn file JSON kịch bản.")

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

        proj_slug = sanitize_slug(data.get("project", {}).get("title", "story_project"))
        project_dir = Path("projects") / proj_slug

        return process_loaded_story_project(data, project_dir, available_voices)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _get_empty_import_returns(f"❌ Lỗi xử lý JSON: {str(e)}")


def handle_import_zip_pack(zip_file, available_voices: list):
    """
    Xử lý nạp file ZIP Production Pack (gồm JSON kịch bản và thư mục music/).
    Giải nén an toàn chống Zip Slip và tự động cấu hình thư viện nhạc.
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

        # Copy music/ vào project dir
        if found_music and found_music.exists():
            final_music_dir = final_project_dir / "music"
            final_music_dir.mkdir(parents=True, exist_ok=True)
            for item in found_music.iterdir():
                if item.is_file():
                    shutil.copy2(item, final_music_dir / item.name)

        # Dọn dẹp temp
        shutil.rmtree(temp_extract_dir, ignore_errors=True)

        return process_loaded_story_project(data, final_project_dir, available_voices)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return _get_empty_import_returns(f"❌ Lỗi giải nén ZIP Pack: {str(e)}")


def bind_production_story_events(components: dict, get_tts_engine_fn, get_available_voices_fn, stop_event):
    """
    Gán các sự kiện tương tác cho module Production Storytelling & TTS Audio Director.
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
        c["music_library_df"],
        c["music_cue_dropdown"],
        c["preview_reveal_seg_dd"],
        c["story_segments_df"],
        c["preview_seg_dropdown"],
        c["story_raw_json_state"],
        c["story_project_info_state"],
        c["story_characters_state"],
        c["story_segments_state"],
        c["story_project_dir_state"],
        c["story_runtime_state"],
        c["story_music_lib_state"]
    ]

    # Import ZIP Pack
    def _on_import_zip(file):
        voices = get_available_voices_fn()
        return handle_import_zip_pack(file, voices)

    c["btn_import_pack_zip"].upload(
        fn=_on_import_zip,
        inputs=[c["btn_import_pack_zip"]],
        outputs=import_outputs
    )

    # Import JSON
    def _on_import_json(file):
        voices = get_available_voices_fn()
        return handle_import_json_data(file, voices)

    c["btn_import_json"].upload(
        fn=_on_import_json,
        inputs=[c["btn_import_json"]],
        outputs=import_outputs
    )

    # Sample Pilot Load
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

    # 2. Preview Voice for each character card
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

    # 3. Apply Character Voice Mapping with SELECTIVE Cache Invalidation
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

    # Refresh voices list
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

    # 4. Music Cue Preview in Library
    def _on_preview_music_cue(cue_name, music_lib):
        if not music_lib or not cue_name:
            return None
        info = music_lib.get(cue_name)
        if info and info.get("status") == "READY":
            return str(info.get("abs_path"))
        return None

    c["btn_preview_music_cue"].click(
        fn=_on_preview_music_cue,
        inputs=[c["music_cue_dropdown"], c["story_music_lib_state"]],
        outputs=[c["audio_music_preview"]]
    )

    # 5. Quick Cue Assignment on selected rows
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

    # 6. Checkbox Selection Helpers
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
            r[0] = (r[18] in ("FAILED", "NEEDS_REGENERATE"))
        return rows

    def _select_multitake(df_data):
        if df_data is None:
            return []
        rows = df_data.values.tolist() if hasattr(df_data, "values") else list(df_data)
        for r in rows:
            r[0] = (int(r[17]) > 1)
        return rows

    c["btn_select_all"].click(lambda df: _toggle_all(df, True), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_deselect_all"].click(lambda df: _toggle_all(df, False), inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_failed"].click(fn=_select_failed, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])
    c["btn_select_multitake"].click(fn=_select_multitake, inputs=[c["story_segments_df"]], outputs=[c["story_segments_df"]])

    # 7. Stop Generation
    c["btn_stop_story"].click(lambda: stop_event.set(), inputs=[], outputs=[])

    # 8. TTS Generation (Sequential with Cache, Resume, Multi-take & Override)
    def _run_generation(df_data, segments, chars_map, project_dir_str, runtime_state, mode="selected"):
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
            status = rows[row_idx][18]

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
                    rows[row_idx][18] = "CACHED"
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
                    rows[row_idx][18] = "COMPLETED"
                    rows[row_idx][19] = f"Take {seg_result.get('selected_take', 1)}"
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
                    rows[row_idx][18] = "FAILED"
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

    # 9. Take Preview & Selection
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
                r[19] = f"Take {take_num}"
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

    # 10. Preview Mix 30s
    def _on_preview_mix_30s(project_dir_str, segments, runtime_state, music_lib,
                            enable_m, enable_rt, auto_sil_crit, m_gain, rt_vol, duck_db, xfade):
        if not project_dir_str or not segments:
            return None, "⚠️ Chưa có dự án nào được mở."
        project_dir = Path(project_dir_str)
        ok, msg, clip_path = build_preview_mix_clip(
            project_dir=project_dir,
            segments=segments,
            project_state=runtime_state,
            music_lib=music_lib or {},
            start_seg_id="001",
            duration_sec=30.0,
            enable_music=bool(enable_m),
            enable_room_tone=bool(enable_rt),
            auto_silence_critical=bool(auto_sil_crit),
            global_music_gain_db=float(m_gain),
            room_tone_volume_db=float(rt_vol),
            default_ducking_db=float(duck_db),
            crossfade_sec=float(xfade)
        )
        if not ok:
            return None, f"❌ {msg}"
        return clip_path, f"✅ Đã tạo Preview Mix 30s: `{clip_path}`"

    c["btn_preview_mix_30s"].click(
        fn=_on_preview_mix_30s,
        inputs=[
            c["story_project_dir_state"],
            c["story_segments_state"],
            c["story_runtime_state"],
            c["story_music_lib_state"],
            c["chk_enable_music"],
            c["chk_enable_room_tone"],
            c["chk_silence_critical"],
            c["music_gain_slider"],
            c["room_tone_vol_slider"],
            c["ducking_db_slider"],
            c["crossfade_sec_slider"]
        ],
        outputs=[c["preview_mix_30s_audio"], c["master_status_md"]]
    )

    # 11. Preview Critical Reveal
    def _on_preview_reveal(project_dir_str, segments, runtime_state, music_lib,
                           reveal_label, enable_m, enable_rt, auto_sil_crit, rt_vol, duck_db, ret_delay):
        if not project_dir_str or not segments or not reveal_label:
            return None, "⚠️ Vui lòng chọn phân đoạn Critical Reveal."
        seg_id = reveal_label.split("]")[0].replace("[", "").strip()
        project_dir = Path(project_dir_str)
        ok, msg, clip_path = build_preview_reveal_clip(
            project_dir=project_dir,
            segments=segments,
            project_state=runtime_state,
            music_lib=music_lib or {},
            reveal_seg_id=seg_id,
            before_sec=8.0,
            after_sec=8.0,
            enable_music=bool(enable_m),
            enable_room_tone=bool(enable_rt),
            auto_silence_critical=bool(auto_sil_crit),
            room_tone_volume_db=float(rt_vol),
            default_ducking_db=float(duck_db),
            reveal_music_return_delay_sec=float(ret_delay)
        )
        if not ok:
            return None, f"❌ {msg}"
        return clip_path, f"✅ Đã tạo Preview Critical Reveal (Phân đoạn {seg_id}): `{clip_path}`"

    c["btn_preview_reveal"].click(
        fn=_on_preview_reveal,
        inputs=[
            c["story_project_dir_state"],
            c["story_segments_state"],
            c["story_runtime_state"],
            c["story_music_lib_state"],
            c["preview_reveal_seg_dd"],
            c["chk_enable_music"],
            c["chk_enable_room_tone"],
            c["chk_silence_critical"],
            c["room_tone_vol_slider"],
            c["ducking_db_slider"],
            c["reveal_delay_sec_slider"]
        ],
        outputs=[c["preview_reveal_audio"], c["master_status_md"]]
    )

    # 12. Build Master Audio (Audio Director Engine)
    def _on_build_master(project_dir_str, segments, runtime_state, music_lib,
                         enable_m, enable_rt, auto_sil_crit, m_gain, rt_vol, duck_db,
                         xfade, ret_delay, target_lufs, true_peak, gap_rule):
        if not project_dir_str or not segments:
            empty_stems = [None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return "⚠️ Chưa có dự án nào được mở.", None, None, gr.update(visible=False), gr.update(visible=False), *empty_stems

        project_dir = Path(project_dir_str)
        ok, msg, outputs = build_audio_director_master(
            project_dir=project_dir,
            segments=segments,
            project_state=runtime_state,
            music_lib=music_lib or {},
            enable_music=bool(enable_m),
            enable_room_tone=bool(enable_rt),
            auto_silence_critical=bool(auto_sil_crit),
            global_music_gain_db=float(m_gain),
            room_tone_volume_db=float(rt_vol),
            default_ducking_db=float(duck_db),
            crossfade_sec=float(xfade),
            reveal_music_return_delay_sec=float(ret_delay),
            target_lufs=float(target_lufs),
            true_peak_db=float(true_peak),
            gap_rule=gap_rule,
            sample_rate=48000
        )

        if not ok:
            empty_stems = [None, None, None, None, gr.update(visible=False), gr.update(visible=False), gr.update(visible=False), gr.update(visible=False)]
            return f"❌ {msg}", None, None, gr.update(visible=False), gr.update(visible=False), *empty_stems

        wav_p = outputs.get("episode_master_wav")
        mp3_p = outputs.get("episode_master_mp3")
        dia_p = outputs.get("dialogue_only")
        rt_p = outputs.get("room_tone")
        mus_p = outputs.get("music_only")
        pre_p = outputs.get("pre_master_mix")
        time_p = outputs.get("music_timeline_json")

        status_md = (
            f"🎉 **{msg}**\n"
            f"- **Master WAV (48kHz 24-bit PCM):** `{wav_p}`\n"
            f"- **Master MP3 (320kbps):** `{mp3_p}`\n"
            f"- **Stems:** Dialogue, Room Tone, Music, Pre-master Mix & Timeline JSON đã xuất trong thư mục `master/`."
        )

        return (
            status_md,
            wav_p,
            mp3_p,
            gr.update(value=wav_p, visible=bool(wav_p)),
            gr.update(value=mp3_p, visible=bool(mp3_p)),
            dia_p,
            rt_p,
            mus_p,
            pre_p,
            gr.update(value=time_p, visible=bool(time_p)),
            gr.update(value=dia_p, visible=bool(dia_p)),
            gr.update(value=rt_p, visible=bool(rt_p)),
            gr.update(value=mus_p, visible=bool(mus_p))
        )

    c["btn_build_master"].click(
        fn=_on_build_master,
        inputs=[
            c["story_project_dir_state"],
            c["story_segments_state"],
            c["story_runtime_state"],
            c["story_music_lib_state"],
            c["chk_enable_music"],
            c["chk_enable_room_tone"],
            c["chk_silence_critical"],
            c["music_gain_slider"],
            c["room_tone_vol_slider"],
            c["ducking_db_slider"],
            c["crossfade_sec_slider"],
            c["reveal_delay_sec_slider"],
            c["target_lufs_num"],
            c["true_peak_num"],
            c["gap_rule_radio"]
        ],
        outputs=[
            c["master_status_md"],
            c["master_wav_audio"],
            c["master_mp3_audio"],
            c["master_wav_download"],
            c["master_mp3_download"],
            c["stem_dialogue_audio"],
            c["stem_room_tone_audio"],
            c["stem_music_audio"],
            c["stem_pre_master_audio"],
            c["stem_timeline_file"],
            c["stem_dialogue_file"],
            c["stem_room_tone_file"],
            c["stem_music_file"]
        ]
    )

    # 13. Export Project JSON with UPDATED character voices and overrides
    def _on_export(project_dir_str, raw_json, chars_map, segments, runtime_state):
        if not project_dir_str or not raw_json:
            return gr.update(visible=False)
        project_dir = Path(project_dir_str)

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
