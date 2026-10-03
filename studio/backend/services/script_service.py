"""Script & Story Bible Service for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from studio.backend.models import ScriptSegment, StoryBibleSection
from studio.backend.services.artifact_lineage import validate_full_script

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

        if data.get('artifact_status') == 'STALE' or (
            sel_idea and sel_idea.get('idea_id') and sel_idea['idea_id'] != data.get('source_idea_id')
        ):
            return StoryBibleSection(
                premise=(sel_idea or {}).get('hook') or (sel_idea or {}).get('premise') or '',
                mystery_core='STALE — REGENERATE REQUIRED: cốt truyện cũ không thuộc ý tưởng hiện tại.',
                selected_idea=sel_idea, title=(sel_idea or {}).get('title', ''), has_story_bible=False,
            )

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
            adaptation_mode=(data.get('adaptation_context') or {}).get('brief', {}).get('adaptation_mode'),
            premise=premise_val,
            characters_summary=char_summary,
            relationships=str(data.get("relationships", "")),
            timeline_summary=timeline_str,
            mystery_core=data.get("core_mystery", "") or data.get("mystery", "") or data.get("secret", ""),
            reveal_1=data.get("reveal_1", "") or data.get("twist_1", ""),
            reveal_2=data.get("reveal_2", "") or data.get("twist_2", ""),
            emotional_payoff=data.get("emotional_payoff", ""),
            fact_lock_items=[str(f) for f in fact_locks],
            selected_idea=sel_idea,
            clues=clues_list,
            reflection_theme=str(data.get("reflection_theme", "")),
            title=str(data.get("title", "")),
            story_qc_report=self.get_story_qc(project_id),
            causal_chains=data.get("causal_chains", []),
            knowledge_ledger=data.get("knowledge_ledger", []),
            reveal_justifications=data.get("reveal_justifications", {}),
            has_story_bible=True,
        )

    def _compute_story_qc(self, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from apps.script_factory.models import StoryBible
            from apps.script_factory.story_qc import StoryQCEngine
            story_bible = StoryBible.from_dict(data)
            return StoryQCEngine().audit_story_bible(story_bible).to_dict()
        except Exception:
            return {}

    def get_story_qc(self, project_id: str) -> Dict[str, Any]:
        proj_dir = PROJECTS_DIR / project_id
        story_path = proj_dir / "story" / "story_bible.json"
        if not story_path.exists():
            story_path = proj_dir / "story_bible.json"
        if not story_path.exists():
            idea_id = self.get_idea_id(project_id)
            story_path = PILOT_02_SCRIPTS / idea_id / "story_bible.json"
        if not story_path.exists():
            raise FileNotFoundError(f"Story Bible không tồn tại cho project {project_id}")

        with open(story_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta_path = proj_dir / 'project.json'
        meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        selected = meta.get('selected_idea') or {}
        if data.get('artifact_status') == 'STALE' or (
            selected.get('idea_id') and selected['idea_id'] != data.get('source_idea_id')
        ):
            return {'status': 'FAIL', 'rule_codes': ['STALE_STORY_BIBLE'],
                    'issues': [{'rule': 'STALE_STORY_BIBLE', 'severity': 'CRITICAL',
                                'message': 'STALE — REGENERATE REQUIRED: cốt truyện không thuộc ý tưởng hiện tại.'}]}
        if data.get('adaptation_context') or (proj_dir / 'adaptation' / 'brief.json').exists():
            from studio.backend.services.source_service import assert_context
            try:
                assert_context(proj_dir, data.get('adaptation_context'))
            except (ValueError, OSError, KeyError) as exc:
                return {'status':'FAIL','rule_codes':['STALE_SOURCE'],
                        'issues':[{'rule':'STALE_SOURCE','severity':'CRITICAL','message':str(exc)}]}
        # A stored PASS cannot override newer deterministic rules or edited content.
        current = self._compute_story_qc(data)
        if current.get("status") == "FAIL":
            return current
        from apps.script_factory.models import StoryBible
        from apps.script_factory.semantic_review import valid_story_semantic_review, semantic_review_version, story_bible_content_hash
        stored = data.get('story_qc_report') or {}
        try:
            bible = StoryBible.from_dict(data)
        except (TypeError, ValueError, KeyError):
            return {'status': 'FAIL', 'rule_codes': ['INVALID_STORY_BIBLE'],
                    'issues': [{'rule': 'INVALID_STORY_BIBLE', 'severity': 'CRITICAL',
                                'message': 'Story Bible thiếu trường bắt buộc; cần tạo lại cốt truyện.'}]}
        if valid_story_semantic_review(bible, stored.get('semantic_review')):
            return stored
        review = stored.get('semantic_review') or {}
        if (stored.get('status') == 'FAIL' and review.get('status') == 'RUN'
                and review.get('review_version') == semantic_review_version(bible)
                and review.get('bible_hash') == story_bible_content_hash(bible)):
            return stored
        return {**current, 'status': 'FAIL', 'rule_codes': ['SEMANTIC_REVIEW_FAILED'],
                'issues': [{'rule': 'SEMANTIC_REVIEW_FAILED', 'severity': 'CRITICAL',
                            'message': 'Cốt truyện chưa có kiểm định semantic hiện hành gắn với nội dung này. Chọn Kiểm tra lại QC.'}]}


    def get_script_segments(self, project_id: str) -> List[ScriptSegment]:
        # Check newly created project directory first
        script_path = PROJECTS_DIR / project_id / "script" / "full_script.json"
        # Only the two explicitly migrated legacy pilots may use legacy snapshots.
        # New Studio projects must never resolve to an unrelated pre-Studio file.
        if not script_path.exists() and project_id in {"EP003", "EP011"}:
            script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists() and project_id in {"EP003", "EP011"}:
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

    def get_script_status(self, project_id: str) -> Dict[str, Any]:
        return validate_full_script(project_id, PROJECTS_DIR)

    def update_segment(self, project_id: str, segment_id: str, new_text: str) -> ScriptSegment:
        idea_id = self.get_idea_id(project_id)
        script_path = PROJECTS_DIR / project_id / "script" / "full_script.json"
        if not script_path.exists() and project_id in {"EP003", "EP011"}:
            script_path = PILOT_03_AUDIO / project_id / "script_snapshot" / "full_script.json"
        if not script_path.exists() and project_id in {"EP003", "EP011"}:
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

        # Mark script EDITED and clear approval hash
        if isinstance(data, dict):
            data["artifact_status"] = "EDITED"
            data.pop("approved_content_hash", None)

        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Mark QC report as STALE
        qc_path = PROJECTS_DIR / project_id / "script" / "qc_report.json"
        if qc_path.exists():
            try:
                qc_data = json.loads(qc_path.read_text(encoding="utf-8"))
                qc_data["artifact_status"] = "STALE"
                qc_data["stale_reason"] = f"Phân đoạn [{segment_id}] đã được chỉnh sửa; cần chạy lại QC"
                qc_path.write_text(json.dumps(qc_data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        # Reset Script stage to DRAFT and cascade STALE downstream
        try:
            from studio.backend.models import StageId, StageStatus
            from studio.backend.project_manager import ProjectManager
            ProjectManager().update_stage_status(project_id, StageId.SCRIPT, StageStatus.DRAFT)
        except Exception:
            pass

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
        if not qc_path.exists() and project_id in {"EP003", "EP011"}:
            idea_id = self.get_idea_id(project_id)
            qc_path = PILOT_02_SCRIPTS / idea_id / "qc_report.json"

        if qc_path.exists():
            with open(qc_path, "r", encoding="utf-8") as f:
                report = json.load(f)
            return self._refresh_outdated_qc(project_id, qc_path, report)
        return None

    def _refresh_outdated_qc(self, project_id: str, qc_path: Path, report: Dict[str, Any]) -> Dict[str, Any]:
        """Re-audits a script whose QC report predates the current rule set or script hash.

        A PASS produced by an older QC version or for different script text must not keep showing
        as PASS once stricter rules or edits exist, so the deterministic audit is re-run and persisted.
        """
        from dataclasses import asdict

        from apps.script_factory.models import FullScript, StoryBible
        from apps.script_factory.script_qc import script_qc_version, ScriptQCEngine
        from studio.backend.services.artifact_lineage import script_content_hash

        script_path = qc_path.parent / "full_script.json"
        current_hash = None
        if script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    raw_sc = json.load(f)
                current_hash = script_content_hash(raw_sc)
            except Exception:
                pass

        story_path = PROJECTS_DIR / project_id / "story" / "story_bible.json"
        raw_story = json.loads(story_path.read_text(encoding='utf-8')) if story_path.exists() else {}
        if report.get("qc_version") == script_qc_version(raw_story) and report.get("script_content_hash") == current_hash:
            return report
        story_path = PROJECTS_DIR / project_id / "story" / "story_bible.json"
        if not script_path.exists() or not story_path.exists():
            return report

        with open(script_path, "r", encoding="utf-8") as f:
            script = FullScript.from_dict(json.load(f))
        with open(story_path, "r", encoding="utf-8") as f:
            story_bible = StoryBible.from_dict(json.load(f))

        engine = ScriptQCEngine(provider=None)
        engine.save_qc_report = lambda _report: None  # persisted below with lineage fields
        # Re-auditing on page load must not call a paid model. Reuse the previous
        # story-logic review when the script text is unchanged; otherwise the
        # verdict cannot be PASS until a full QC (Auto-Repair) runs it again.
        from apps.script_factory.semantic_review import carry_over_semantic_review
        semantic = carry_over_semantic_review(report, script, story_bible) or {"status": "NOT_RUN", "issues": [], "advisories": []}
        fresh = asdict(engine.run_qc(script=script, story_bible=story_bible, semantic_review=semantic))
        if semantic.get("status") == "NOT_RUN" and fresh["status"] == "PASS":
            fresh["status"] = "NEEDS_REVISION"
            fresh["evidence_issues"].append({
                "segment_id": None,
                "excerpt": "",
                "rule": "SEMANTIC_REVIEW_PENDING",
                "severity": "HIGH",
                "recommended_action": "Bấm Auto-Repair để chạy QC logic cốt truyện bằng AI.",
                "message": "Kịch bản chưa được kiểm tra logic cốt truyện bằng bộ QC hiện tại.",
            })
        for key in ("generation_source", "generation_request_id",
                    "source_story_generation_request_id", "source_story_content_hash"):
            if key in report:
                fresh[key] = report[key]
        fresh["artifact_status"] = "CURRENT" if fresh["status"] == "PASS" else "NEEDS_REVISION"
        fresh["previous_qc_version"] = report.get("qc_version")
        with open(qc_path, "w", encoding="utf-8") as f:
            json.dump(fresh, f, ensure_ascii=False, indent=2)
        if fresh["status"] != "PASS":
            from studio.backend.services.artifact_lineage import invalidate_script_approval
            invalidate_script_approval(project_id, PROJECTS_DIR)
        return fresh

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
            "generation_source": "MANUAL_IMPORT",
            "artifact_status": "STALE",
            "stale_reason": "Kịch bản nhập tay không có REAL_AI generation lineage",
            "word_count": sum(len(s["text"].split()) for s in segments),
            "estimated_duration_sec": sum(len(s["text"].split()) / 2.7 for s in segments),
            "segments": segments
        }

        with open(script_dir / "full_script.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return self.get_script_segments(project_id)

