"""Script & Story Bible Service for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from studio.backend.models import ScriptSegment, StoryBibleSection

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PILOT_02_SCRIPTS = BASE_DIR / "pilot_02_v1_3_1a"
PILOT_03_AUDIO = BASE_DIR / "production_pilot_03"


PROJECTS_DIR = BASE_DIR / "projects"


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
        # Check newly created project directory first
        bible_path = PROJECTS_DIR / project_id / "story" / "story_bible.json"
        if not bible_path.exists():
            idea_id = self.get_idea_id(project_id)
            bible_path = PILOT_02_SCRIPTS / idea_id / "story_bible.json"

        if not bible_path.exists():
            proj_dir = PROJECTS_DIR / project_id
            premise_file = proj_dir / "story" / "premise.txt"
            p_json = proj_dir / "project.json"
            premise_text = ""
            mystery_text = "Đang chờ phát triển cốt truyện..."
            sel_idea = None
            title_text = ""
            if p_json.exists():
                try:
                    with open(p_json, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        premise_text = meta.get("topic") or meta.get("premise") or ""
                        sel_idea = meta.get("selected_idea")
                        title_text = meta.get("title", "")
                except Exception:
                    pass

            if not premise_text and premise_file.exists():
                try:
                    content = premise_file.read_text(encoding="utf-8").strip()
                    lines = content.splitlines()
                    for line in lines:
                        if line.startswith("Ý tưởng:"):
                            premise_text = line.replace("Ý tưởng:", "").strip()
                        elif line.startswith("Bí ẩn:") and line.replace("Bí ẩn:", "").strip():
                            mystery_text = line.replace("Bí ẩn:", "").strip()
                    if not premise_text and content:
                        premise_text = content
                except Exception:
                    pass

            return StoryBibleSection(
                premise=premise_text or "Câu chuyện chưa có Story Bible chi tiết.",
                mystery_core=mystery_text,
                has_story_bible=False,
                selected_idea=sel_idea,
                title=title_text
            )

        with open(bible_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p_json = PROJECTS_DIR / project_id / "project.json"
        sel_idea = None
        if p_json.exists():
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    sel_idea = json.load(f).get("selected_idea")
            except Exception:
                pass

        chars = data.get("characters", [])
        if not chars:
            all_chars = []
            if data.get("protagonist"):
                all_chars.append(data["protagonist"])
            all_chars.extend(data.get("supporting_characters", []))
            chars = all_chars
        char_summary = ", ".join([f"{c.get('name')} ({c.get('role', 'Nhân vật')})" for c in chars if isinstance(c, dict)])

        premise_val = data.get("premise", "") or data.get("secret", "") or data.get("false_lead", "")
        if not premise_val and isinstance(data.get("protagonist"), dict):
            premise_val = data["protagonist"].get("description", "")

        raw_fact_lock = data.get("fact_lock", {})
        fact_locks = raw_fact_lock.get("locked_facts", []) if isinstance(raw_fact_lock, dict) else []
        if not fact_locks and isinstance(raw_fact_lock, list):
            fact_locks = raw_fact_lock
        if not fact_locks and data.get("critical_facts"):
            fact_locks = [f.get("value") or f.get("description") for f in data.get("critical_facts", [])]

        raw_clues = data.get("clues", [])
        clues_list = [str(c) for c in raw_clues] if isinstance(raw_clues, list) else []

        timeline_data = data.get("timeline_structure", "") or data.get("timeline", "")
        if isinstance(timeline_data, list):
            timeline_str = " -> ".join([str(t) for t in timeline_data])
        else:
            timeline_str = str(timeline_data)

        return StoryBibleSection(
            premise=premise_val,
            characters_summary=char_summary,
            relationships=str(data.get("relationships", "")),
            timeline_summary=timeline_str,
            mystery_core=data.get("core_mystery", "") or data.get("mystery", "") or data.get("secret", ""),
            reveal_1=data.get("reveal_1", "") or data.get("twist_1", ""),
            reveal_2=data.get("reveal_2", "") or data.get("twist_2", ""),
            emotional_payoff=data.get("emotional_payoff", ""),
            fact_lock_items=[str(f) for f in fact_locks],
            has_story_bible=True,
            selected_idea=sel_idea,
            clues=clues_list,
            reflection_theme=str(data.get("reflection_theme", "")),
            title=str(data.get("title", ""))
        )


    def get_script_segments(self, project_id: str) -> List[ScriptSegment]:
        # Check newly created project directory first
        script_path = PROJECTS_DIR / project_id / "script" / "full_script.json"
        if not script_path.exists():
            # Try production pilot 03 snapshot first, then pilot 02
            script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists():
            idea_id = self.get_idea_id(project_id)
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
                speed=float(s.get("speed", 1.0) or 1.0),
                pause_before=float(s.get("pause_before", 0.0) or 0.0),
                pause_after=float(s.get("pause_after", 0.25) or 0.25),
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
        script_path = PROJECTS_DIR / project_id / "script" / "full_script.json"
        if not script_path.exists():
            script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists():
            script_path = PILOT_02_SCRIPTS / idea_id / "full_script.json"

        if not script_path.exists():
            raise FileNotFoundError(f"No script file found for project {project_id}")

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
            story_function=target.get("story_function", "DEVELOPMENT") if target else "DEVELOPMENT",
            speed=float(target.get("speed", 1.0) or 1.0) if target else 1.0,
            pause_before=float(target.get("pause_before", 0.0) or 0.0) if target else 0.0,
            pause_after=float(target.get("pause_after", 0.25) or 0.25) if target else 0.25,
        )

    def get_script_qc(self, project_id: str) -> Optional[Dict[str, Any]]:
        qc_path = PROJECTS_DIR / project_id / "script" / "qc_report.json"
        if not qc_path.exists():
            idea_id = self.get_idea_id(project_id)
            qc_path = PILOT_02_SCRIPTS / idea_id / "qc_report.json"

        if qc_path.exists():
            with open(qc_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def import_script_text(self, project_id: str, text: str) -> List[ScriptSegment]:
        """Imports raw script text, chunks into segments, and saves full_script.json."""
        proj_dir = PROJECTS_DIR / project_id
        script_dir = proj_dir / "script"
        script_dir.mkdir(parents=True, exist_ok=True)

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        segments = []
        for i, line in enumerate(lines):
            sid = f"SEG_{i+1:03d}"
            # Delivery profile assignment heuristic
            lower = line.lower()
            if "sự thật" in lower or "bất ngờ" in lower or "hóa ra" in lower:
                profile = "REVEAL"
            elif i == 0:
                profile = "HOOK"
            elif i == len(lines) - 1:
                profile = "ENDING"
            elif i < 3:
                profile = "HOOK"
            elif i > len(lines) - 4:
                profile = "ENDING"
            else:
                profile = "NORMAL"

            segments.append({
                "segment_id": sid,
                "speaker": "NARRATOR",
                "delivery_profile": profile,
                "text": line,
                "story_function": "DEVELOPMENT",
                "speed": {
                    "HOOK": 0.98,
                    "REVEAL": 0.92,
                    "ENDING": 0.965,
                    "NORMAL": 1.01,
                }.get(profile, 1.0),
                "pause_before": 0.05,
                "pause_after": 0.25,
            })

        data = {
            "episode_id": project_id,
            "word_count": sum(len(s["text"].split()) for s in segments),
            "estimated_duration_sec": sum(len(s["text"].split()) / 2.7 for s in segments),
            "segments": segments
        }

        with open(script_dir / "full_script.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return self.get_script_segments(project_id)

