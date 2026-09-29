import json
from pathlib import Path
import soundfile as sf
from apps.visual_engine.visual_planner import VisualPlanner, validate_plan_for_generation
from apps.visual_engine.asset_manager import VisualAssetManager

def main():
    project_dir = Path("projects/sau_canh_cua_-_episode_01_v9_1_master_reference")
    source_path = project_dir / "source.json"
    with open(source_path, "r", encoding="utf-8") as f:
        source = json.load(f)

    v_info = sf.info(str(project_dir / "master/voice_master.wav"))
    total_audio_sec = v_info.duration
    sample_rate = v_info.samplerate

    timeline_events = []
    current_sample = 0
    for seg in source.get("segments", []):
        sid = seg["id"]
        wav_p = project_dir / "selected" / f"{int(sid):03d}.wav"
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
            "duration_sec": en_sec - st_sec,
        })
        p_gap = float(seg.get("pause_after", 0.18))
        current_sample += samp_len + int(p_gap * sample_rate)

    planner = VisualPlanner(preset_name="sau_canh_cua")
    plan = planner.plan_episode_visuals(
        timeline_events=timeline_events,
        total_audio_sec=total_audio_sec,
        project_dir=project_dir,
        target_scenes_min=35,
        target_scenes_max=45,
        target_omni_min=14,
        target_omni_max=22,
    )
    print(f"Generated {len(plan)} scenes")

    is_valid, issues = validate_plan_for_generation(plan, total_audio_sec, planner.characters, planner.locations)
    print(f"Generation gate valid: {is_valid}, issues count: {len(issues)}")
    for iss in issues:
        print(f"  Issue: {iss}")

    planner.save_plan(plan, project_dir)
    print(f"Saved visual_plan.json with {len(plan)} scenes")

    asset_mgr = VisualAssetManager(project_dir)
    asset_mgr.sync_queue_with_plan(plan)
    print("Synced visual_queue.json")

    report_path = Path("reports/episode01_visual_semantic_qc.json")
    report = planner.audit_and_export_semantic_qc(plan, total_audio_sec, report_path)
    print(f"Exported report: {report_path}")
    print(f"Status: {report['generation_gate_status']}")
    print(f"Visible character mismatches: {report['visible_character_mismatches']}")
    print(f"Location mismatches: {report['location_mismatches']}")
    print(f"Chronology mismatches: {report['chronology_mismatches']}")
    print(f"Critical scenes passed: {report['critical_scenes_passed']}/{report['critical_scenes_count']}")
    print(f"Banana images: {report['banana_images_count']}, Omni videos: {report['omni_videos_count']}")
    print(f"Omni duration distribution: {report['omni_duration_distribution']}")

if __name__ == "__main__":
    main()
