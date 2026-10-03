"""Event-based Timeline and Evidence Scope Auditor for VieNeu Script QC.

Detects event-year contradictions, relationship lifecycle continuity breaks,
document/will lifecycle order bugs, and unfounded leaps from evidence to conclusions.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from apps.script_factory.models import FullScript, StoryBible


def audit_event_timeline(
    script: FullScript,
    story_bible: StoryBible,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Audit relation between characters, events, and years against story_bible.timeline."""
    fact_conflicts: List[Dict[str, Any]] = []
    evidence_issues: List[Dict[str, Any]] = []
    revision_requests: List[str] = []

    from apps.script_factory.event_facts import character_aliases, extract_events, script_duration_conflicts, bible_timeline_conflicts
    aliases = character_aliases(story_bible)
    timeline_entries = getattr(story_bible, 'timeline', []) or []
    milestones = [event for entry in timeline_entries for event in extract_events(entry, aliases) if event['year'] is not None]
    for segment in script.segments:
        for event in extract_events(segment.text, aliases):
            if event['year'] is None:
                continue
            candidates = [m for m in milestones if m['label'] == event['label']]
            if event['actor']:
                candidates = [m for m in candidates if m['actor'] == event['actor']]
            elif len({m['actor'] for m in candidates}) > 1:
                continue  # Ambiguous subject must be reviewed, never guessed.
            expected = {m['year'] for m in candidates}
            if not expected or event['year'] in expected:
                continue
            message = f"Mâu thuẫn sự kiện {event['actor'] or ''} — {event['label']}: Bible ghi {sorted(expected)}, đoạn [{segment.id}] kể {event['year']}."
            fact_conflicts.append({'fact_id':'EVENT_TIMELINE', 'field':'event_timeline', 'expected':sorted(expected), 'found':str(event['year']), 'type':'TIMELINE_CONFLICT', 'description':message})
            evidence_issues.append({'segment_id':segment.id,'excerpt':event['clause'],'rule':'EVENT_TIMELINE_CONTRADICTION','severity':'CRITICAL','message':message,'recommended_action':'Đối chiếu đúng nhân vật, sự kiện và năm với Story Bible; giữ nguyên dữ kiện đã khóa.'})
            revision_requests.append(f'Correct event timeline in segment [{segment.id}]: {message}')

    for sid, clause, message in script_duration_conflicts(script, story_bible):
        fact_conflicts.append({'fact_id':'EVENT_DURATION', 'type':'TIMELINE_CONFLICT', 'description':message})
        evidence_issues.append({'segment_id':sid,'excerpt':clause,'rule':'EVENT_TIMELINE_CONTRADICTION','severity':'CRITICAL','message':message,'recommended_action':'Giữ đúng thời lượng sự kiện được khóa trong Story Bible.'})
        revision_requests.append(f'Correct event duration in segment [{sid}]: {message}')
    for message in bible_timeline_conflicts(story_bible):
        fact_conflicts.append({'fact_id':'UPSTREAM_TIMELINE', 'type':'TIMELINE_CONFLICT', 'description':message})
        revision_requests.append(f'Repair Story Bible timeline before rewriting script: {message}')

    # 2. Relationship lifecycle contradiction:
    # If timeline records a breakup / separation, but script says "chưa bao giờ kết thúc" / "chưa từng chia tay"
    has_breakup = any(
        any(w in entry.lower() for w in ["chia tay", "chấm dứt", "ly hôn", "cắt đứt"])
        for entry in timeline_entries
    )
    if has_breakup:
        never_ended_patterns = [
            "chưa bao giờ kết thúc", "chưa từng kết thúc", "chưa từng chia tay",
            "chưa bao giờ chia tay", "chưa bao giờ dừng lại", "chưa từng chấm dứt"
        ]
        for s in script.segments:
            s_lower = s.text.lower()
            for nep in never_ended_patterns:
                if nep in s_lower:
                    # Check if explained as lie/denial/perspective
                    explained = any(ex in s_lower for ex in [
                        "nói dối", "ngụy biện", "tự lừa dối", "ảo tưởng", "ngộ nhận",
                        "về mặt tình cảm", "trên danh nghĩa", "lời biện hộ", "cố chấp"
                    ])
                    if not explained:
                        fact_conflicts.append({
                            "fact_id": "RELATIONSHIP_LIFECYCLE",
                            "field": "timeline_continuity",
                            "type": "RELATIONSHIP_TIMELINE_CONTRADICTION",
                            "description": f"Phân đoạn [{s.id}] khẳng định mối quan hệ '{nep}', mâu thuẫn với sự kiện chia tay trong Story Bible mà không giải thích lời nói dối hoặc sự khác biệt."
                        })
                        evidence_issues.append({
                            "segment_id": s.id,
                            "excerpt": s.text[:120],
                            "rule": "RELATIONSHIP_TIMELINE_CONTRADICTION",
                            "severity": "CRITICAL",
                            "message": f"Mâu thuẫn timeline: Khẳng định mối quan hệ '{nep}' dù Story Bible ghi nhận sự kiện chia tay mà không có lời giải thích.",
                            "recommended_action": "Bổ sung câu làm rõ (đây là lời ngụy biện/tự dối lòng của nhân vật, hoặc chỉ là sự cố chấp cảm xúc)."
                        })
                        revision_requests.append(f"Clarify relationship continuity in segment [{s.id}]: explain why character claims '{nep}' despite historical breakup.")

    # 3. Document / Will lifecycle contradiction:
    # Opening real will vs destroying real will
    opened_segs = [s for s in script.segments if any(op in s.text.lower() for op in ["mở bức di chúc đầu tiên", "mở di chúc thật", "mở bản di chúc", "mở di chúc"])]
    destroyed_segs = [s for s in script.segments if any(des in s.text.lower() for des in ["tiêu hủy nó", "tiêu hủy di chúc", "hủy bản di chúc", "đốt di chúc"])]
    for d_seg in destroyed_segs:
        d_idx = script.segments.index(d_seg)
        context_segs = script.segments[max(0, d_idx - 2):d_idx + 1]
        context_text = " ".join(cs.text.lower() for cs in context_segs)
        if "ngay sau khi cha qua đời" in context_text or "ngay sau khi cha mất" in context_text:
            # Hai admits destroyed real will immediately after death
            for o_seg in opened_segs:
                if int(o_seg.id) < int(d_seg.id) and "sau tang lễ" in o_seg.text.lower():
                    # Direct contradiction! How could they open the real will after funeral if it was destroyed immediately after death?
                    fact_conflicts.append({
                        "fact_id": "DOCUMENT_LIFECYCLE",
                        "field": "will_lifecycle",
                        "type": "DOCUMENT_LIFECYCLE_CONTRADICTION",
                        "description": f"Bất nhất về di chúc: Phân đoạn [{d_seg.id}] kể nhân vật tiêu hủy di chúc thật ngay sau khi cha mất, mâu thuẫn với phân đoạn [{o_seg.id}] các anh em mở di chúc sau tang lễ."
                    })
                    evidence_issues.append({
                        "segment_id": d_seg.id,
                        "excerpt": d_seg.text[:120],
                        "rule": "DOCUMENT_LIFECYCLE_CONTRADICTION",
                        "severity": "CRITICAL",
                        "message": "Bất nhất về thứ tự đọc và tiêu hủy di chúc giữa các phân đoạn.",
                        "recommended_action": "Làm rõ bản di chúc mở sau tang lễ là bản sao/bản giả hay bản nháp, hoặc giải thích rõ thời điểm tiêu hủy."
                    })
                    revision_requests.append(f"Resolve will lifecycle contradiction between segment [{o_seg.id}] and [{d_seg.id}].")

    return fact_conflicts, evidence_issues, revision_requests


def audit_evidence_scope(
    script: FullScript,
    story_bible: StoryBible,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Audit leaps from physical evidence to absolute conclusions."""
    evidence_issues: List[Dict[str, Any]] = []
    revision_requests: List[str] = []

    for idx, s in enumerate(script.segments):
        s_lower = s.text.lower()

        # 1. Leap on donor confirmation without reading donor document
        donor_conclusions = [
            "chính thức xác nhận chính", "xác nhận chính", "xác nhận chính là người",
            "chính thức xác nhận là người đã", "chứng minh chính là người đã hiến"
        ]
        if any(dc in s_lower for dc in donor_conclusions) and ("hiến" in s_lower or "thận" in s_lower):
            # Check previous 2 segments to see what was inspected
            preceding_texts = " ".join(script.segments[max(0, idx - 2):idx + 1][i].text.lower() for i in range(len(script.segments[max(0, idx - 2):idx + 1])))
            has_donor_doc = any(doc in preceding_texts for doc in [
                "hồ sơ hiến", "giấy xác nhận người hiến", "biên bản hiến", "chứng từ hiến",
                "hồ sơ bệnh án ghi rõ người hiến", "dòng chữ xác nhận hiến", "chữ ký cam kết hiến",
                "kết quả phẫu thuật hiến"
            ])
            is_just_schedule = ("lịch trình" in preceding_texts or "sổ ghi chép" in preceding_texts) and not has_donor_doc
            if is_just_schedule:
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:120],
                    "rule": "UNFOUNDED_EVIDENCE_LEAP",
                    "severity": "CRITICAL",
                    "message": "Kết luận vượt phạm vi bằng chứng: Cuốn sổ lịch trình chưa đủ để khẳng định danh tính người hiến thận nếu chưa miêu tả việc đọc dòng chữ/biên bản xác nhận người hiến.",
                    "recommended_action": "Bổ sung chi tiết đọc dòng ghi chú xác nhận người hiến trong sổ/hồ sơ trước khi kết luận."
                })
                revision_requests.append(f"Add evidence verification link in segment [{s.id}] before concluding donor identity.")

        # 2. Leap from family photo to absolute moral character verdict
        if ("bức ảnh" in s_lower or "tấm ảnh" in s_lower) and re.search(
            r"(?:chứng minh|minh chứng)\b.{0,65}?(?:hoàn toàn không|bản chất)", s_lower
        ):
            evidence_issues.append({
                "segment_id": s.id,
                "excerpt": s.text[:120],
                "rule": "UNFOUNDED_EVIDENCE_LEAP",
                "severity": "HIGH",
                "message": "Kết luận vượt phạm vi bằng chứng: Một bức ảnh không thể 'chứng minh hoàn toàn' bản chất tính cách nhân vật.",
                "recommended_action": "Thay vì khẳng định khách quan 'chứng minh hoàn toàn', hãy diễn đạt qua nhận thức/cảm xúc nhân vật ('khiến cô nhận ra', 'gợi lại cho cô thấy')."
            })
            revision_requests.append(f"Soften absolute character claim in segment [{s.id}] to character emotional realization.")

    return evidence_issues, revision_requests
