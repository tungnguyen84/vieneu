"""Lineage and leakage checks for Studio creative artifacts.

The Studio keeps generated files on disk for audit/history.  A file existing is
therefore not proof that it belongs to the currently selected Story Bible.
This module is the single gate used by Script and Audio services.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


STALE_LABEL = "STALE — REGENERATE REQUIRED"

# These are production-template labels/content that must never appear in a
# generated listener-facing script.  Keep the patterns narrow so legitimate
# words such as "bệnh viện" are not rejected on their own.
_LEAK_PATTERNS = (
    ("Nhân vật chính", re.compile(r"\bnhân\s+vật\s+chính\b", re.IGNORECASE)),
    ("Manh mối 1/2/3", re.compile(r"\bmanh\s+mối\s*[123]\b", re.IGNORECASE)),
    ("Bước ngoặt 1/2", re.compile(r"\bbước\s+ngoặt\s*[12]\b", re.IGNORECASE)),
    ("100.000.000 VND", re.compile(r"\b100(?:[.,\s]?000){2}\s*(?:vnd|đồng)?\b", re.IGNORECASE)),
)

_SIGNOFF_RE = re.compile(
    r"(?:cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|"
    r"xin\s+chào\s+và\s+hẹn\s+gặp\s+lại|"
    r"tôi\s+là\s+minh[^.]{0,80}hẹn\s+gặp\s+lại)",
    re.IGNORECASE,
)

_VOLATILE_STORY_KEYS = {
    "status", "approved_by", "approved_at", "last_modified_at", "generated_at",
    "story_qc_report", "artifact_status", "stale_reason", "stale_reasons", "stale_at",
}


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _valid_request_id(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        uuid.UUID(value.strip())
        return True
    except (ValueError, AttributeError):
        return False


def story_content_hash(story: Dict[str, Any]) -> str:
    """Stable hash of Story Bible semantics, excluding review timestamps/status."""
    semantic = {k: v for k, v in story.items() if k not in _VOLATILE_STORY_KEYS}
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def find_template_leakage(script: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = "\n".join(
        str(segment.get("text", ""))
        for segment in script.get("segments", [])
        if isinstance(segment, dict)
    )
    matches: List[Dict[str, Any]] = []
    for label, pattern in _LEAK_PATTERNS:
        count = len(pattern.findall(text))
        if count:
            matches.append({"pattern": label, "count": count})
    return matches


def validate_full_script(project_id: str, projects_dir: Path) -> Dict[str, Any]:
    project_dir = projects_dir / project_id
    project_path = project_dir / "project.json"
    story_path = project_dir / "story" / "story_bible.json"
    script_path = project_dir / "script" / "full_script.json"
    project = _read_json(project_path) if project_path.exists() else {}
    story = _read_json(story_path) if story_path.exists() else {}
    script = _read_json(script_path) if script_path.exists() else {}
    reasons: List[str] = []

    story_request_id = story.get("generation_request_id")
    script_request_id = script.get("generation_request_id")
    source_story_request_id = script.get("source_story_generation_request_id")
    current_story_hash = story_content_hash(story) if story else None
    source_story_hash = script.get("source_story_content_hash")
    selected_idea = project.get("selected_idea") if isinstance(project.get("selected_idea"), dict) else {}
    selected_idea_id = selected_idea.get("idea_id")
    story_source_idea_id = story.get("source_idea_id")

    if not script_path.exists():
        reasons.append("Full Script chưa tồn tại trong dự án hiện tại")
    if not story_path.exists():
        reasons.append("Story Bible hiện tại không tồn tại")
    if story.get("generation_source") != "REAL_AI":
        reasons.append("Story Bible không có generation_source REAL_AI")
    if not _valid_request_id(story_request_id):
        reasons.append("Story Bible không có REAL_AI request ID hợp lệ")
    if selected_idea_id and story_source_idea_id != selected_idea_id:
        reasons.append("Story Bible không thuộc ý tưởng đang được chọn trong project.json")
    if script.get("generation_source") != "REAL_AI":
        reasons.append("Full Script không có generation_source REAL_AI")
    if not _valid_request_id(script_request_id):
        reasons.append("Full Script không có REAL_AI request ID hợp lệ")
    if source_story_request_id != story_request_id:
        reasons.append("Full Script không thuộc generation lineage của Story Bible hiện tại")
    if not source_story_hash or source_story_hash != current_story_hash:
        reasons.append("Nội dung Story Bible đã thay đổi sau khi Full Script được tạo")
    artifact_state = str(script.get("artifact_status", "")).upper()
    if artifact_state == "STALE":
        reasons.append(str(script.get("stale_reason") or "Full Script đã được đánh dấu stale"))
    elif artifact_state in {"NEEDS_REVISION", "REJECTED"}:
        reasons.append("Full Script chưa vượt qua QC và cần được tạo hoặc sửa lại")

    segments = script.get("segments") if isinstance(script.get("segments"), list) else []
    valid_segments = [s for s in segments if isinstance(s, dict) and str(s.get("text", "")).strip()]
    if not valid_segments:
        reasons.append("Full Script không có phân đoạn hợp lệ")
    else:
        signoff_indices = [
            idx for idx, segment in enumerate(valid_segments)
            if _SIGNOFF_RE.search(str(segment.get("text", "")))
        ]
        ending_indices = [
            idx for idx, segment in enumerate(valid_segments)
            if str(segment.get("delivery_profile", "")).upper() == "ENDING"
        ]
        final_idx = len(valid_segments) - 1
        has_premature_closure = any(idx < final_idx for idx in [*signoff_indices, *ending_indices])
        has_duplicate_closure = len(signoff_indices) > 1 or len(ending_indices) > 1
        if has_premature_closure or has_duplicate_closure:
            reasons.append("Kịch bản phải có đúng một lời chào kết và một nhãn ENDING tại phân đoạn cuối")

    leakage = find_template_leakage(script)
    if leakage:
        detail = ", ".join(f"{item['pattern']} ({item['count']})" for item in leakage)
        reasons.append(f"Phát hiện nội dung template nội bộ: {detail}")

    # Preserve order while removing duplicate reasons.
    reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    is_current = not reasons
    generated_at = script.get("created_at") or script.get("generated_at") or script.get("updated_at")

    # Audio Gate requirements:
    # 1. Script is current (is_current)
    # 2. Stage status is APPROVED (or COMPLETED / LOCKED)
    # 3. 0 unresolved CRITICAL QC issues in qc_report.json
    qc_path = project_dir / "script" / "qc_report.json"
    qc = _read_json(qc_path) if qc_path.exists() else {}

    stage_statuses = project.get("stage_statuses") if isinstance(project.get("stage_statuses"), dict) else {}
    script_stage_status = stage_statuses.get("03_script") or script.get("status")

    critical_qc_issues: List[str] = []
    qc_status = str(qc.get("status", "")).upper()
    has_critical_failure = bool(qc.get("has_critical_failure") or qc_status == "FAIL")

    for issue in qc.get("evidence_issues", []) + qc.get("fact_conflicts", []) + qc.get("issues", []):
        if isinstance(issue, dict):
            rule_code = issue.get("rule") or issue.get("type", "")
            severity = str(issue.get("severity", "")).upper()
            if severity == "CRITICAL" or rule_code in [
                "TIMELINE_FACT_CONTRADICTION", "RELATIONSHIP_TIMELINE_CONTRADICTION", "CAUSAL_GAP",
                "CHARACTER_KNOWLEDGE_CONTRADICTION", "EVIDENCE_DOES_NOT_PROVE_CLAIM", "REVEAL_UNDERJUSTIFIED",
                "SCRIPT_FACT_DRIFT", "FINAL_SCRIPT_TOPIC_DRIFT", "INTERNAL_TEMPLATE_LEAKAGE",
                "PREMATURE_SIGNOFF", "DUPLICATE_SIGNOFF", "CONTENT_AFTER_SIGNOFF", "MISSING_FINAL_SIGNOFF",
            ]:
                has_critical_failure = True
                msg = issue.get("message") or issue.get("rule") or "Lỗi QC nghiêm trọng"
                critical_qc_issues.append(f"[{rule_code}] {msg}")

    audio_gate_reasons: List[str] = []
    if not is_current:
        audio_gate_reasons.append(f"Kịch bản không hợp lệ hoặc lỗi thời ({'; '.join(reasons)})")
    if has_critical_failure:
        crit_detail = "; ".join(critical_qc_issues[:2]) if critical_qc_issues else "Báo cáo QC ở trạng thái FAIL"
        audio_gate_reasons.append(f"Kịch bản có lỗi QC mức CRITICAL chưa được giải quyết ({crit_detail})")
    if script_stage_status not in ["APPROVED", "COMPLETED", "LOCKED"]:
        audio_gate_reasons.append(f"Kịch bản chưa được phê duyệt ở bước Script (trạng thái: {script_stage_status or 'DRAFT'})")

    audio_gate_allowed = len(audio_gate_reasons) == 0
    audio_gate_reason = " | ".join(audio_gate_reasons) if audio_gate_reasons else None

    return {
        "project_id": project_id,
        "artifact_status": "CURRENT" if is_current else "STALE",
        "status_label": "CURRENT" if is_current else STALE_LABEL,
        "is_current": is_current,
        "stale_reasons": reasons,
        "audio_gate_allowed": audio_gate_allowed,
        "audio_gate_reason": audio_gate_reason,
        "critical_qc_count": len(critical_qc_issues),
        "critical_qc_issues": critical_qc_issues,
        "qc_status": qc_status or None,
        "script_stage_status": script_stage_status,
        "generation_source": script.get("generation_source"),
        "generated_by": "Gemini" if "gemini" in str(script.get("provider_name", "")).lower() else script.get("provider_name"),
        "provider_name": script.get("provider_name"),
        "model_name": script.get("model_name"),
        "generation_request_id": script_request_id,
        "prompt_version": script.get("prompt_version"),
        "generated_at": generated_at,
        "story_generation_request_id": story_request_id,
        "selected_idea_id": selected_idea_id,
        "story_source_idea_id": story_source_idea_id,
        "source_story_generation_request_id": source_story_request_id,
        "story_content_hash": current_story_hash,
        "source_story_content_hash": source_story_hash,
        "segment_count": len(valid_segments),
        "leakage_count": sum(item["count"] for item in leakage),
        "leakage_matches": leakage,
        "script_path": str(script_path),
        "story_path": str(story_path),
    }


def require_current_full_script(
    project_id: str,
    projects_dir: Path,
    require_approved: bool = True,
    require_clean_qc: bool = True,
) -> Dict[str, Any]:
    status = validate_full_script(project_id, projects_dir)
    if not status["is_current"]:
        details = "; ".join(status["stale_reasons"])
        raise ValueError(f"{STALE_LABEL}: {details}")
    if require_clean_qc and status.get("critical_qc_count", 0) > 0:
        details = "; ".join(status.get("critical_qc_issues", []))
        raise ValueError(f"Kịch bản bị chặn do có lỗi QC CRITICAL: {details}")
    if require_approved and not status.get("audio_gate_allowed", True):
        raise ValueError(f"Audio Gate: {status.get('audio_gate_reason')}")
    return status


def mark_full_script_stale(project_id: str, projects_dir: Path, reason: str) -> bool:
    """Marks the current script/QC on disk stale without deleting audit evidence."""
    project_dir = projects_dir / project_id
    script_path = project_dir / "script" / "full_script.json"
    if not script_path.exists():
        return False
    script = _read_json(script_path)
    reasons = script.get("stale_reasons") if isinstance(script.get("stale_reasons"), list) else []
    reasons = list(dict.fromkeys([*reasons, reason]))
    script.update({
        "artifact_status": "STALE",
        "stale_reason": reason,
        "stale_reasons": reasons,
        "stale_at": time.time(),
    })
    script_path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    qc_path = project_dir / "script" / "qc_report.json"
    if qc_path.exists():
        qc = _read_json(qc_path)
        qc.update({"artifact_status": "STALE", "stale_reason": reason, "stale_at": time.time()})
        qc_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2), encoding="utf-8")
    project_path = project_dir / "project.json"
    if project_path.exists():
        project = _read_json(project_path)
        project.update({
            "script_artifact_status": "STALE",
            "script_stale_reason": reason,
            "updated_at": time.time(),
        })
        project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def mark_story_bible_stale(project_id: str, projects_dir: Path, reason: str) -> bool:
    """Marks both compatibility copies of Story Bible stale after idea change."""
    changed = False
    for story_path in (
        projects_dir / project_id / "story" / "story_bible.json",
        projects_dir / project_id / "story_bible.json",
    ):
        if not story_path.exists():
            continue
        story = _read_json(story_path)
        story.update({
            "artifact_status": "STALE",
            "stale_reason": reason,
            "stale_at": time.time(),
        })
        story_path.write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
        changed = True
    return changed
