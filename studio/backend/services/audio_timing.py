"""Measure segment boundaries using the same WAV loader and pause rule as AudioDirector."""
from pathlib import Path
from typing import Any, Dict, List, Tuple


def measure_segment_timeline(work_dir: Path, segments: List[Dict[str, Any]], state: Dict[str, Any],
                             sample_rate: int) -> Tuple[List[Dict[str, Any]], int]:
    from apps.audio_director import load_audio_file

    events, cursor = [], 0
    for index, segment in enumerate(segments):
        sid = str(segment["id"])
        selected = state.get("segments", {}).get(sid, {}).get("selected_file")
        path = work_dir / selected if selected else work_dir / "selected" / f"{sid}.wav"
        if not path.is_file():
            raise FileNotFoundError(f"Thiếu WAV cho phân đoạn {sid}")
        wav = load_audio_file(path, target_sr=sample_rate)
        if wav is None or not len(wav):
            raise ValueError(f"WAV phân đoạn {sid} không hợp lệ")
        before = float(segment.get("pause_before", 0.0) or 0.0)
        after = float(segment.get("pause_after", 0.18) or 0.18)
        if index == 0:
            cursor += int(before * sample_rate)
        start = cursor
        cursor += len(wav)
        events.append({**segment, "speech_start_sample": start, "speech_end_sample": cursor,
                       "speech_start_sec": start / sample_rate, "speech_end_sec": cursor / sample_rate,
                       "duration_sec": len(wav) / sample_rate, "timing_source": "MEASURED_WAV"})
        next_before = float(segments[index + 1].get("pause_before", 0.0) or 0.0) if index + 1 < len(segments) else 0
        cursor += int(max(after, next_before) * sample_rate)
    return events, cursor
