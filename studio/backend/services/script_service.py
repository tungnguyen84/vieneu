"""Script & Story Bible Service for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from studio.backend.models import ScriptSegment, StoryBibleSection

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PILOT_02_SCRIPTS = BASE_DIR / "pilot_02_v1_3_1a"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"


class ScriptService:
    def __init__(self):
        pass

    def get_idea_id(self, project_id: str) -> str:
        mapping = {
            "EP003": "IDEA_003",
            "EP011": "IDEA_011",
            "EP001": "IDEA_001"
        }
        return mapping.get(project_id, project_id)

    def get_story_bible(self, project_id: str) -> StoryBibleSection:
        idea_id = self.get_idea_id(project_id)
        bible_path = PILOT_02_SCRIPTS / idea_id / "story_bible.json"
        if not bible_path.exists():
            return StoryBibleSection(
                premise="Câu chuyện chưa có Story Bible chi tiết.",
                mystery_core="Đang cập nhật..."
            )

        with open(bible_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        chars = data.get("characters", [])
        char_summary = ", ".join([f"{c.get('name')} ({c.get('role', 'Nhân vật')})" for c in chars])

        fact_locks = data.get("fact_lock", {}).get("locked_facts", [])
        if not fact_locks and isinstance(data.get("fact_lock"), list):
            fact_locks = data.get("fact_lock")

        return StoryBibleSection(
            premise=data.get("premise", ""),
            characters_summary=char_summary,
            relationships=str(data.get("relationships", "")),
            timeline_summary=str(data.get("timeline_structure", "") or data.get("timeline", "")),
            mystery_core=data.get("core_mystery", "") or data.get("mystery", ""),
            reveal_1=data.get("reveal_1", "") or data.get("twist_1", ""),
            reveal_2=data.get("reveal_2", "") or data.get("twist_2", ""),
            emotional_payoff=data.get("emotional_payoff", ""),
            fact_lock_items=[str(f) for f in fact_locks]
        )

    def get_script_segments(self, project_id: str) -> List[ScriptSegment]:
        idea_id = self.get_idea_id(project_id)
        # Try production pilot 03 snapshot first, then pilot 02
        script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists():
            script_path = PILOT_02_SCRIPTS / idea_id / "full_script.json"

        if not script_path.exists():
            return []

        with open(script_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_segs = data.get("segments", [])
        if not raw_segs and isinstance(data, list):
            raw_segs = data

        segments = []
        for i, s in enumerate(raw_segs):
            sid = s.get("id", s.get("segment_id", f"{i+1:03d}"))
            words = len(s.get("text", "").split())
            est_dur = round(words / 2.7, 2)  # ~160 words/min
            segments.append(ScriptSegment(
                segment_id=sid,
                speaker=s.get("speaker", "NARRATOR"),
                delivery_profile=s.get("delivery_profile", "SUSPENSE_COLD"),
                text=s.get("text", ""),
                story_function=s.get("story_function", "DEVELOPMENT"),
                estimated_duration_sec=s.get("duration", est_dur),
                qc_flags=[]
            ))
        return segments

    def get_full_script_text(self, project_id: str) -> str:
        """Returns full script in clean readable article format."""
        segments = self.get_script_segments(project_id)
        paragraphs = []
        for s in segments:
            paragraphs.append(s.text)
        return "\n\n".join(paragraphs)

    def update_segment(self, project_id: str, segment_id: str, new_text: str) -> ScriptSegment:
        idea_id = self.get_idea_id(project_id)
        script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists():
            script_path = PILOT_02_SCRIPTS / idea_id / "full_script.json"

        with open(script_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_segs = data.get("segments", data) if isinstance(data, dict) else data
        target = None
        for s in raw_segs:
            sid = s.get("id", s.get("segment_id"))
            if sid == segment_id:
                s["text"] = new_text
                target = s
                break

        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return ScriptSegment(
            segment_id=segment_id,
            speaker=target.get("speaker", "NARRATOR") if target else "NARRATOR",
            delivery_profile=target.get("delivery_profile", "SUSPENSE_COLD") if target else "SUSPENSE_COLD",
            text=new_text,
            story_function=target.get("story_function", "DEVELOPMENT") if target else "DEVELOPMENT"
        )
