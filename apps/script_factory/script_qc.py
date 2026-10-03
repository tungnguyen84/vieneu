"""Script QC Engine for Script Factory V1."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.cost_control import CostController
from apps.script_factory.information_release_map import (
    InformationReleaseMap,
    build_information_release_map,
)
from apps.script_factory.leakage_guard import StoryBibleLeakageGuard
from apps.script_factory.models import FullScript, QCReport, ScriptSegment, StoryBible
from apps.script_factory.narrative_continuity import find_repeated_narrative_block
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.spoiler_timing_guard import SpoilerTimingGuard

logger = logging.getLogger("VieNeu.ScriptQC")

SERIES_BIBLE_PATH = Path("script_factory/series_bible.json")
STORY_FORMULA_PATH = Path("script_factory/story_formula_v1.json")
SCRIPT_QC_VERSION = "script-qc-v5.3-knowledge-source-bound"


def _vietnamese_integer_words(value: int) -> Optional[str]:
    """Return the common spoken Vietnamese form for small locked-fact numbers."""
    digits = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
    if value < 0 or value > 99:
        return None
    if value < 10:
        return digits[value]
    tens, units = divmod(value, 10)
    prefix = "mười" if tens == 1 else f"{digits[tens]} mươi"
    if units == 0:
        return prefix
    spoken_unit = "mốt" if units == 1 and tens > 1 else "lăm" if units == 5 else digits[units]
    return f"{prefix} {spoken_unit}"


def _numeric_unit_fact_present(value: str, script_text: str) -> Optional[bool]:
    """Match `18 tháng`, `mười tám tháng`, and decimal punctuation variants."""
    match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|nghìn|trăm|năm|tháng|ngày)\b",
        value.lower(),
    )
    if not match:
        return None

    raw_number, unit = match.groups()
    canonical_number = raw_number.replace(",", ".")
    normalized_text = re.sub(r"(?<=\d),(?=\d)", ".", script_text.lower())
    if re.search(rf"\b{re.escape(canonical_number)}\s*{re.escape(unit)}\b", normalized_text):
        return True

    if "." not in canonical_number:
        words = _vietnamese_integer_words(int(canonical_number))
        if words and re.search(rf"\b{re.escape(words)}\s*{re.escape(unit)}\b", normalized_text):
            return True
    return False


class ScriptQCEngine:
    """Audits scripts against Story Bible, Locked Facts, and narrative standards."""

    def __init__(
        self,
        provider: Optional[ScriptAIProvider] = None,
        cost_controller: Optional[CostController] = None,
        episodes_root: Optional[Path] = None,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller or CostController()
        self.episodes_root = Path(episodes_root) if episodes_root else Path("episodes")

    @classmethod
    def audit_script(
        cls,
        script: FullScript,
        story_bible: StoryBible,
        story_formula: Optional[Dict[str, Any]] = None,
        series_bible: Optional[Dict[str, Any]] = None,
    ) -> QCReport:
        """Convenience method to execute full QC audit without explicit controller instantiation."""
        from apps.script_factory.cost_control import CostController
        engine = cls(provider=None, cost_controller=CostController())
        return engine.run_qc(script=script, story_bible=story_bible)

    def run_qc(
        self,
        script: FullScript,
        story_bible: StoryBible,
        past_scripts: Optional[List[FullScript]] = None,
        model: Optional[str] = None,
        release_map: Optional[InformationReleaseMap] = None,
        semantic_review: Optional[Dict[str, Any]] = None,
    ) -> QCReport:
        """Executes full QC audit."""
        self.cost_ctrl.check_budget_pre_flight(episode_id=script.episode_id)

        fact_conflicts: List[Dict[str, Any]] = []
        logic_issues: List[str] = []
        repetition_issues: List[str] = []
        revision_requests: List[str] = []
        evidence_issues: List[Dict[str, Any]] = []

        all_text = " ".join(s.text for s in script.segments)

        # 0. STORY BIBLE & INTERNAL TEMPLATE LEAKAGE AUDIT
        leakage_guard = StoryBibleLeakageGuard()
        leakage_violations = leakage_guard.audit_script(script)
        for lv in leakage_violations:
            evidence_issues.append({
                "segment_id": lv.segment_id,
                "excerpt": lv.excerpt,
                "rule": lv.violation_code,  # "STORY_BIBLE_LEAKAGE" or "INTERNAL_TEMPLATE_LEAKAGE"
                "severity": lv.severity,
                "recommended_action": lv.recommended_action,
                "message": lv.message,
            })
            logic_issues.append(f"[{lv.segment_id}] {lv.violation_code}: {lv.message}")
            revision_requests.append(f"Remove {lv.violation_code} in segment {lv.segment_id}: {lv.matched_pattern}")

        # 0.1 INFORMATION RELEASE & SPOILER TIMING AUDIT (Premature reveal prevention)
        rel_map = release_map or build_information_release_map(
            story_bible,
            total_segments=len(script.segments) if script.segments else 90,
        )
        known_setup = set()
        setup_sources = [
            getattr(story_bible, "secret", ""),
            getattr(story_bible, "mystery_question", ""),
            getattr(story_bible, "false_lead", ""),
            *(getattr(story_bible, "clues", []) or []),
        ]
        for src in setup_sources:
            if src and isinstance(src, str):
                for t in re.findall(r"\w+", src.lower()):
                    if len(t) >= 3:
                        known_setup.add(t)

        # Include characters from story bible so character names are not flagged as spoilers
        for ch in (getattr(story_bible, "characters", []) or []):
            ch_name = ch.name if hasattr(ch, "name") else (ch.get("name") if isinstance(ch, dict) else str(ch or ""))
            if ch_name:
                known_setup.add(ch_name.lower())
                for part in re.findall(r"\w+", ch_name.lower()):
                    if len(part) >= 2:
                        known_setup.add(part)
        if hasattr(story_bible, "protagonist"):
            p_name = story_bible.protagonist.get("name") if isinstance(story_bible.protagonist, dict) else str(story_bible.protagonist or "")
            if p_name:
                known_setup.add(p_name.lower())
                for part in re.findall(r"\w+", p_name.lower()):
                    if len(part) >= 2:
                        known_setup.add(part)
        for sc in (getattr(story_bible, "supporting_characters", []) or []):
            sc_name = sc.get("name") if isinstance(sc, dict) else str(sc or "")
            if sc_name:
                known_setup.add(sc_name.lower())
                for part in re.findall(r"\w+", sc_name.lower()):
                    if len(part) >= 2:
                        known_setup.add(part)

        spoiler_guard = SpoilerTimingGuard(rel_map, known_setup_entities=known_setup)
        spoiler_violations = spoiler_guard.audit_script(script)
        for sv in spoiler_violations:
            evidence_issues.append({
                "segment_id": sv.segment_id,
                "excerpt": sv.excerpt,
                "rule": "BLOCKED_PREMATURE_REVEAL",
                "severity": sv.severity,
                "recommended_action": sv.recommended_action,
                "message": sv.message,
            })
            fact_conflicts.append({
                "fact_id": sv.fact_id,
                "segment_id": sv.segment_id,
                "type": "BLOCKED_PREMATURE_REVEAL",
                "description": sv.message,
            })
            revision_requests.append(f"Fix premature reveal in segment {sv.segment_id}: {sv.matched_term}")

        # 0.2 HOOK SPECIFICITY AUDIT (No generic philosophical filler in opening)
        for s in script.segments[:3]:
            txt_lower = s.text.lower().strip()
            cliches = ["trong cuộc sống", "có những câu chuyện", "có những bí mật", "có bao giờ bạn", "người ta thường nói"]
            for cl in cliches:
                if txt_lower.startswith(cl):
                    evidence_issues.append({
                        "segment_id": s.id,
                        "excerpt": s.text[:80],
                        "rule": "GENERIC_HOOK_OPENING",
                        "severity": "HIGH",
                        "recommended_action": "Mở đầu trực tiếp bằng nhân vật cụ thể, dị thường vật lý và rủi ro cảm xúc thay vì câu triết lý chung chung.",
                        "message": f"Phân đoạn [{s.id}] mở đầu bằng khuôn mẫu sáo rỗng ('{cl}')."
                    })
                    logic_issues.append(f"Generic hook opening in segment {s.id}: starts with '{cl}'.")
                    revision_requests.append(f"Rewrite segment {s.id} with specific concrete person/object/hook.")

        # 1. FACT CONSISTENCY AUDIT (Strict Locked Facts Check)
        for fact in story_bible.critical_facts:
            if fact.status == "LOCKED":
                # Check for direct value presence or contradictory numbers
                val = fact.value.strip()
                val_lower = val.lower()

                # If checking years / numbers, make sure no conflicting numbers appear in same context
                if val.isdigit():
                    num_val = int(val)
                    # Search if wrong number was stated where correct number should be
                    # e.g., if fact is 7 years, search if 8 years, 9 years or 10 years was stated
                    if "năm" in fact.description.lower() or "year" in fact.field.lower():
                        if 1900 <= num_val <= 2100:
                            calendar_years = re.findall(r"(?:năm\s+)?(\b(?:19|20)\d{2}\b)", all_text.lower())
                            if calendar_years and str(num_val) not in calendar_years and str(num_val) not in all_text:
                                fact_conflicts.append({
                                    "fact_id": fact.fact_id,
                                    "field": fact.field,
                                    "expected": fact.value,
                                    "found": calendar_years,
                                    "type": "TIMELINE_CONFLICT",
                                    "description": f"Timeline conflict: Expected calendar year {num_val}, but found conflicting years: {calendar_years}."
                                })
                                revision_requests.append(f"Correct timeline conflict: change calendar year to {num_val}.")
                        else:
                            found_years = re.findall(r"(\d+)\s+năm", all_text.lower())
                            if found_years and str(num_val) not in found_years and str(num_val) not in all_text:
                                fact_conflicts.append({
                                    "fact_id": fact.fact_id,
                                    "field": fact.field,
                                    "expected": fact.value,
                                    "found": found_years,
                                    "type": "TIMELINE_CONFLICT",
                                    "description": f"Timeline conflict: Expected {num_val} năm, but found conflicting years: {found_years}."
                                })
                                revision_requests.append(f"Correct timeline conflict: change to {num_val} năm.")
                elif "money" in fact.field.lower() or "payment" in fact.field.lower() or (("vnd" in val_lower or "triệu" in val_lower or "đồng" in val_lower) and len(val.split()) <= 5):
                    # Money conflict check
                    clean_money = re.sub(r"[^\d]", "", val)
                    clean_text_digits = re.sub(r"[^\d]", " ", all_text)
                    num_words = {"1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín", "10": "mười"}
                    numeric_unit_match = _numeric_unit_fact_present(val, all_text)
                    found_money = numeric_unit_match is True
                    if not found_money and clean_money and clean_money in clean_text_digits:
                        found_money = True
                    elif val_lower in all_text.lower():
                        found_money = True
                    elif clean_money and len(clean_money) >= 7 and clean_money.endswith("000000"):
                        millions = str(int(clean_money) // 1000000)
                        if f"{millions} triệu" in all_text.lower() or f"{num_words.get(millions, '')} triệu" in all_text.lower():
                            found_money = True
                    elif clean_money and len(clean_money) >= 10 and clean_money.endswith("000000000"):
                        billions = str(int(clean_money) // 1000000000)
                        if f"{billions} tỷ" in all_text.lower() or f"{num_words.get(billions, '')} tỷ" in all_text.lower():
                            found_money = True

                    if not found_money:
                        fact_conflicts.append({
                            "fact_id": fact.fact_id,
                            "field": fact.field,
                            "expected": fact.value,
                            "type": "MONEY_CONFLICT",
                            "description": f"Money conflict: Expected {fact.value} missing or conflicting in script narration."
                        })
                        revision_requests.append(f"Correct money conflict: ensure exact amount {fact.value} is stated.")
                else:
                    # General fact / relationship check
                    num_words = {"1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín", "10": "mười"}
                    parts = [p.strip().lower() for p in re.split(r"[;,]", val) if p.strip()]
                    found = any(p in all_text.lower() for p in parts) if parts else (val_lower in all_text.lower())
                    if not found and _numeric_unit_fact_present(val, all_text) is True:
                        found = True
                    if not found:
                        for p in parts:
                            m = re.match(r"^(\d+)\s+(năm|tháng|ngày|năm\s+trước)$", p)
                            if m:
                                d, unit = m.group(1), m.group(2)
                                word_num = num_words.get(d)
                                if word_num and f"{word_num} {unit}" in all_text.lower():
                                    found = True
                                    break
                    if not found:
                        # Try digit to Vietnamese word conversion
                        val_words = val_lower
                        for d_str, w_str in num_words.items():
                            val_words = re.sub(rf"\b{d_str}\b", w_str, val_words)
                        if val_words in all_text.lower():
                            found = True
                    if not found:
                        # Try Vietnamese word to digit conversion
                        val_digits = val_lower
                        for d_str, w_str in num_words.items():
                            val_digits = re.sub(rf"\b{w_str}\b", d_str, val_digits)
                        if val_digits in all_text.lower():
                            found = True
                    if not found and len(val) >= 15:
                        key_words = [w for w in re.findall(r"\b\w{3,}\b", val_lower) if w not in ["người", "những", "trong", "được", "không", "thực", "hiện"]]
                        match_count = sum(1 for kw in key_words if kw in all_text.lower())
                        found = (match_count / max(1, len(key_words))) >= 0.6
                    if not found and ("năm" in fact.description.lower() or "year" in fact.field.lower() or "timeline" in fact.field.lower() or "năm" in fact.field.lower() or "tuổi" in fact.field.lower()):
                        from apps.script_factory.vietnamese_cleaner import year_to_vietnamese_words, num_to_vietnamese_words
                        desc_years = set(re.findall(r"\b(?:19|20)\d{2}\b", fact.description))
                        if desc_years:
                            matched_years = 0
                            for yr in desc_years:
                                yr_variants = year_to_vietnamese_words(yr)
                                if any(yv.lower() in all_text.lower() for yv in yr_variants):
                                    matched_years += 1
                            if matched_years >= min(2, len(desc_years)):
                                found = True
                        if not found:
                            val_digits_match = re.search(r"\b(\d+)\b", val)
                            if val_digits_match:
                                num_val = int(val_digits_match.group(1))
                                word_variants = num_to_vietnamese_words(num_val)
                                unit_suffix = "năm" if "năm" in val_lower else ("tuổi" if "tuổi" in val_lower else "")
                                if any(f"{wv} {unit_suffix}".strip() in all_text.lower() for wv in word_variants):
                                    found = True

                    if not found:
                        fact_conflicts.append({
                            "fact_id": fact.fact_id,
                            "field": fact.field,
                            "expected": fact.value,
                            "type": "RELATIONSHIP_CONFLICT" if "cậu" in val_lower or "chú" in val_lower or "bác" in val_lower or "relat" in fact.field.lower() else "FACT_CONFLICT",
                            "description": f"Fact conflict: Expected '{fact.value}' for {fact.field} missing or contradicted."
                        })
                        revision_requests.append(f"Correct relationship/fact conflict: clarify that {fact.field} is {fact.value}.")

        # 1.1 EVENT-BASED TIMELINE & CONTINUITY AUDIT
        from apps.script_factory.timeline_qc import audit_event_timeline, audit_evidence_scope
        tl_conflicts, tl_evidence_issues, tl_requests = audit_event_timeline(script, story_bible)
        fact_conflicts.extend(tl_conflicts)
        evidence_issues.extend(tl_evidence_issues)
        revision_requests.extend(tl_requests)

        # 1.2 EVIDENCE SCOPE VS CONCLUSION AUDIT
        scope_issues, scope_requests = audit_evidence_scope(script, story_bible)
        evidence_issues.extend(scope_issues)
        revision_requests.extend(scope_requests)

        # 1.3 DETERMINISTIC VIETNAMESE LANGUAGE QUALITY (GARBLED_VIETNAMESE)
        from apps.script_factory.vietnamese_cleaner import find_garbled_vietnamese_issues
        for s in script.segments:
            v_issues = find_garbled_vietnamese_issues(s.text)
            for vi in v_issues:
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:80],
                    "rule": "GARBLED_VIETNAMESE",
                    "severity": "CRITICAL",
                    "recommended_action": "Sửa lại từ ngữ tiếng Việt tự nhiên, không dùng số tiếng Anh trước đơn vị, không để phụ âm đơn lẻ hoặc âm tiết lặp.",
                    "message": f"Phân đoạn [{s.id}] chứa lỗi tiếng Việt: {vi['reason']}",
                })
                revision_requests.append(f"Sửa lỗi tiếng Việt ở phân đoạn [{s.id}]: {vi['reason']}")

        # 2. MAJOR REVEAL RULE AUDIT
        # No audience address in Major Reveal block
        for s in script.segments:
            if (s.delivery_profile == "REVEAL" or s.importance == "critical") and s.audience_address:
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:80],
                    "rule": "REVEAL_AUDIENCE_RESTRAINT",
                    "severity": "HIGH",
                    "recommended_action": "Tập trung tuyệt đối vào diễn biến sự thật, không ngắt quãng bằng giao lưu khán giả.",
                    "message": f"Phân đoạn [{s.id}] mang nhãn REVEAL nhưng chứa audience_address=True."
                })
                logic_issues.append(f"Major Reveal segment {s.id} contains direct audience address, violating reveal restraint rule.")
                revision_requests.append(f"Remove audience address from reveal segment {s.id} to preserve dramatic weight.")

        # 3. AUDIENCE INTERACTION FREQUENCY (3–6)
        audience_segs = [s for s in script.segments if s.audience_address]
        if len(audience_segs) < 3 or len(audience_segs) > 6:
            repetition_issues.append(f"Audience interaction count is {len(audience_segs)} (Required: 3 to 6).")
            revision_requests.append("Rebalance audience interactions to be between 3 and 6 per episode.")

        # 4. REPETITION & HOOK AUDIT ACROSS PAST SCRIPTS
        if past_scripts and script.segments:
            current_hook = script.segments[0].text.strip().lower()
            for ps in past_scripts:
                if ps.episode_id != script.episode_id and ps.segments:
                    past_hook = ps.segments[0].text.strip().lower()
                    # Check for repeated opening hook formula
                    hook_words_curr = set(current_hook.split()[:8])
                    hook_words_past = set(past_hook.split()[:8])
                    overlap = len(hook_words_curr & hook_words_past) / max(1, len(hook_words_curr))
                    if overlap > 0.70:
                        repetition_issues.append(f"Repeated hook detected: opening formula is too similar to {ps.episode_id}.")
                        revision_requests.append(f"Rewrite opening hook to avoid duplicating the hook structure of {ps.episode_id}.")

        # 4.1 INTERNAL NARRATIVE BLOCK REPETITION
        # Two-pass providers can accidentally restart Part 2 by retelling the
        # final investigation/confrontation sequence from Part 1. A single clue
        # callback is valid; four distant segments with high content overlap are not.
        repeated_block = find_repeated_narrative_block(script.segments)
        if repeated_block:
            first_start = repeated_block["first_start"]
            second_start = repeated_block["second_start"]
            first_id = script.segments[first_start].id
            second_id = script.segments[second_start].id
            score = repeated_block["score"]
            evidence_issues.append({
                "segment_id": second_id,
                "excerpt": script.segments[second_start].text[:100],
                "rule": "REPEATED_NARRATIVE_BLOCK",
                "severity": "CRITICAL",
                "recommended_action": "Xóa vòng kể lại ở phần sau và nối trực tiếp từ hành động cuối phần trước tới chứng cứ/reveal mới.",
                "message": (
                    f"Phân đoạn bắt đầu tại [{second_id}] kể lại chuỗi sự kiện đã xuất hiện từ "
                    f"[{first_id}] (độ tương đồng {score * 100:.1f}%)."
                ),
                "first_start": first_start,
                "first_end": repeated_block["first_end"],
                "second_start": second_start,
                "second_end": repeated_block["second_end"],
                # The whole retold block must change together; fixing only its
                # first segment leaves the repetition in place round after round.
                "related_segment_ids": [
                    s.id for s in script.segments[second_start + 1:repeated_block["second_end"]]
                ],
            })
            repetition_issues.append(
                f"Repeated narrative block: segments {first_id} and {second_id} restart the same event sequence."
            )
            revision_requests.append(
                f"Remove the repeated event sequence beginning at segment {second_id}; continue directly to new evidence or reveal."
            )

        # 4.15 LETTER VOICE: the episode is one person's letter. Narration that
        # says another character "viết rằng"/"viết trong thư" swaps the letter's
        # author mid-episode (a writer copied the voice sample's sender name).
        sender = (
            story_bible.protagonist.get("name", "") if isinstance(story_bible.protagonist, dict)
            else str(story_bible.protagonist or "")
        ).strip()
        sender_tokens = {t.casefold() for t in sender.split()} if sender else set()
        others = {
            str(c.get("name", "")).strip()
            for c in (story_bible.supporting_characters or []) if isinstance(c, dict) and c.get("name")
        }
        other_tokens = {
            name.split()[-1] for name in others
            if name and name.split()[-1].casefold() not in sender_tokens
        }
        if sender_tokens and other_tokens:
            letter_voice = re.compile(
                r"\b(" + "|".join(re.escape(t) for t in sorted(other_tokens)) + r")\s+"
                r"(?:viết\s+(?:rằng|lại|trong\s+thư)|kể\s+trong\s+thư|viết:)"
            )
            for seg in script.segments:
                match = letter_voice.search(seg.text)
                if match:
                    evidence_issues.append({
                        "segment_id": seg.id,
                        "excerpt": seg.text[:120],
                        "rule": "LETTER_VOICE_MIXUP",
                        "severity": "CRITICAL",
                        "recommended_action": f"Lá thư do {sender} gửi. Chuyển thành lời thoại của {match.group(1)} hoặc lời kể của {sender}.",
                        "message": f"Phân đoạn [{seg.id}] để {match.group(1)} 'viết' như thể là người gửi thư, trong khi người gửi thư là {sender}.",
                    })
                    logic_issues.append(f"[{seg.id}] Letter voice attributed to {match.group(1)} instead of {sender}.")

        # 4.155 PROCEDURAL EVIDENCE: a hotel/bank/building handing private data to a spouse.
        from apps.script_factory.script_craft import procedural_evidence_hits
        for index in procedural_evidence_hits([seg.text for seg in script.segments]):
            seg = script.segments[index]
            evidence_issues.append({
                "segment_id": seg.id,
                "excerpt": seg.text[:120],
                "rule": "INFEASIBLE_EVIDENCE",
                "severity": "CRITICAL",
                "recommended_action": "Thay bằng bằng chứng đời thường người thường có được (tận mắt thấy, người quen kể, đồ vật, máy dùng chung).",
                "message": f"Phân đoạn [{seg.id}] lấy bằng chứng nhờ một tổ chức cung cấp dữ liệu riêng của người khác; ngoài đời không xảy ra.",
            })

        # 4.158 ENDING NOT DELIVERED: the confession goes straight to the closing
        # reflection and the Story Bible resolution never airs. Advisory only: the
        # measure is lexical, and the writer already inserts a missing resolution.
        from apps.script_factory.script_craft import ENDING_COVERAGE_MIN, closing_block_start, ending_coverage
        coverage = ending_coverage([seg.text for seg in script.segments], getattr(story_bible, "ending", ""))
        if coverage is not None and coverage < ENDING_COVERAGE_MIN:
            close_at = max(0, closing_block_start(script.segments) - 1)
            seg = script.segments[close_at]
            evidence_issues.append({
                "segment_id": seg.id,
                "excerpt": seg.text[:120],
                "rule": "ENDING_NOT_DELIVERED",
                "severity": "WARNING",
                "recommended_action": "Thêm 5-7 đoạn kể phần giải quyết bằng hành động theo kết thúc trong Story Bible, trước lời chiêm nghiệm.",
                "message": f"Sau cảnh đối chất, kịch bản chuyển ngay sang lời kết; phần kết thúc trong Story Bible gần như không được kể (độ phủ {coverage:.2f}).",
            })

        # 4.16 REPEATED SCENE: the same line of dialogue said again in a later
        # scene means the second half retold a scene (shop visit asked twice).
        from apps.script_factory.scene_outline import repeated_dialogue_pairs
        by_seg = {seg.id: seg for seg in script.segments}
        for first_id, later_id in repeated_dialogue_pairs(script.segments):
            evidence_issues.append({
                "segment_id": later_id,
                "related_segment_ids": [first_id],
                "excerpt": by_seg[later_id].text[:120],
                "rule": "REPEATED_SCENE_DIALOGUE",
                "severity": "CRITICAL",
                "recommended_action": (
                    f"Cảnh này lặp lại cuộc trò chuyện ở [{first_id}]. Viết lại thành diễn biến MỚI tiếp nối "
                    "hoặc rút gọn thành một câu chuyển cảnh; không hỏi lại câu đã hỏi."
                ),
                "message": f"Phân đoạn [{later_id}] lặp lại gần nguyên văn lời thoại đã có ở [{first_id}]: \"{by_seg[first_id].text[:100]}\"",
            })
            repetition_issues.append(f"[{later_id}] repeats dialogue from [{first_id}].")

        # 4.2 ADJACENT SEGMENT ECHO
        # Chunked generation often restates the last beat of a segment as the
        # opening of the next one ("... bắt máy." -> "Đầu dây bên kia bắt máy, ...").
        def _sentences(text: str) -> List[str]:
            return [s for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]

        def _ngrams(sentence: str, n: int = 5) -> set:
            words = re.findall(r"\w+", sentence.casefold())
            return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}

        for prev_seg, next_seg in zip(script.segments, script.segments[1:]):
            prev_sents, next_sents = _sentences(prev_seg.text), _sentences(next_seg.text)
            if not prev_sents or not next_sents:
                continue
            shared = _ngrams(prev_sents[-1]) & _ngrams(next_sents[0])
            if shared:
                phrase = " ".join(sorted(shared)[0])
                evidence_issues.append({
                    "segment_id": next_seg.id,
                    "excerpt": next_seg.text[:120],
                    "rule": "ADJACENT_SEGMENT_ECHO",
                    "related_segment_ids": [prev_seg.id],
                    "severity": "HIGH",
                    "recommended_action": "Bỏ phần nhắc lại ở đầu phân đoạn sau và nối tiếp bằng diễn biến mới.",
                    "message": f"Phân đoạn [{next_seg.id}] mở đầu bằng việc lặp lại hành động vừa kể ở [{prev_seg.id}] ('{phrase}').",
                })
                repetition_issues.append(f"[{next_seg.id}] echoes the closing beat of [{prev_seg.id}]: '{phrase}'.")
                revision_requests.append(f"Remove the restated beat at the start of segment {next_seg.id}.")

        # 5. STRUCTURE AUDIT (Check acts representation)
        has_hook = any(s.delivery_profile == "HOOK" for s in script.segments)
        has_reveal = any(s.delivery_profile == "REVEAL" for s in script.segments)
        has_ending = any(s.delivery_profile == "ENDING" for s in script.segments)

        if not has_hook:
            logic_issues.append("Missing HOOK delivery profile segments in Act 1.")
            revision_requests.append("Add HOOK delivery profile segments in opening act.")
        if not has_reveal:
            logic_issues.append("Missing REVEAL delivery profile segments in Act 6/7.")
            revision_requests.append("Ensure Major Reveal segments are explicitly marked REVEAL.")
        if not has_ending:
            logic_issues.append("Missing ENDING delivery profile segments in Act 9.")
            revision_requests.append("Add ENDING delivery profile segments in closing act.")

        # 6. HOOK VS STORY / REVEAL FACT CONTRADICTION AUDIT
        hook_segs = [s for s in script.segments[:5] if s.delivery_profile == "HOOK"] or script.segments[:3]
        reveal_segs = [s for s in script.segments if s.delivery_profile == "REVEAL"]
        truth_corpus = " ".join(
            [str(story_bible.reveal_1 or ""), str(story_bible.reveal_2 or ""), str(story_bible.secret or "")]
            + [s.text for s in reveal_segs]
            + [f"{f.value} {f.description}" for f in story_bible.critical_facts]
        ).lower()

        contradiction_rules = [
            (
                ["vô hiệu", "giả mạo", "không hợp lệ", "không có giá trị", "di chúc giả"],
                ["hợp pháp", "có hiệu lực", "hoàn toàn thật", "xác thực", "chính thức khẳng định", "di chúc hợp pháp"],
                "Hook khẳng định văn bản/di chúc vô hiệu hoặc giả mạo nhưng Reveal/Story Bible xác nhận văn bản hợp pháp/xác thực."
            ),
            (
                ["đã phản bội", "kẻ phản bội", "đã chiếm đoạt", "đã biển thủ", "ăn cắp tiền"],
                ["hy sinh", "cứu sống", "không hề biển thủ", "không phải bị chiếm đoạt", "không phải là một vụ biển thủ", "bảo vệ"],
                "Hook kết luận nhân vật phản bội/chiếm đoạt như sự thật hiển nhiên nhưng Reveal chứng minh đó là sự hy sinh/cứu giúp."
            ),
        ]
        for hs in hook_segs:
            hs_lower = hs.text.lower()
            has_hedging = any(
                hedge in hs_lower
                for hedge in ["nghi ngờ", "tưởng rằng", "ngỡ rằng", "ngỡ là", "liệu có phải", "câu hỏi", "hoài nghi", "tưởng chừng"]
            )
            for hook_terms, truth_terms, reason_msg in contradiction_rules:
                matched_hook = next((ht for ht in hook_terms if ht in hs_lower), None)
                matched_truth = next((tt for tt in truth_terms if tt in truth_corpus), None)
                if matched_hook and matched_truth and not has_hedging:
                    fact_conflicts.append({
                        "fact_id": "HOOK_REVEAL_LOGIC",
                        "segment_id": hs.id,
                        "type": "HOOK_FACT_CONTRADICTION",
                        "expected": matched_truth,
                        "found": matched_hook,
                        "description": f"{reason_msg} (Hook: '{matched_hook}' vs Reveal: '{matched_truth}')",
                    })
                    evidence_issues.append({
                        "segment_id": hs.id,
                        "excerpt": hs.text[:100],
                        "rule": "HOOK_FACT_CONTRADICTION",
                        "severity": "CRITICAL",
                        "recommended_action": "Viết lại Hook dưới dạng nghi vấn hoặc góc nhìn hạn chế ban đầu, tuyệt đối không khẳng định ngược với sự thật ở Reveal.",
                        "message": f"Phân đoạn [{hs.id}] mâu thuẫn trực tiếp với sự thật ở Reveal: '{matched_hook}' trái ngược với '{matched_truth}'."
                    })
                    logic_issues.append(f"[{hs.id}] Hook fact contradiction: '{matched_hook}' contradicts truth '{matched_truth}'.")
                    revision_requests.append(f"Rewrite Hook segment {hs.id} to remove false assertion '{matched_hook}' that contradicts Reveal.")
                    break

        # 6.6 HOOK VS BODY DISCOVERY TIMELINE AUDIT (HOOK_TIMELINE_CONTRADICTION)
        tod_patterns = [
            ("NIGHT", re.compile(r"\b(tối\s+hôm\s+ấy|tối\s+hôm\s+đó|tối\s+đó|đêm\s+ấy|đêm\s+đó|nửa\s+đêm|buổi\s+tối\s+hôm\s+ấy|buổi\s+tối\s+đó)\b", re.IGNORECASE)),
            ("MORNING", re.compile(r"\b(sáng\s+hôm\s+sau|sáng\s+hôm\s+đó|sáng\s+ấy|buổi\s+sáng\s+hôm\s+sau|buổi\s+sáng\s+đó|sáng\s+sớm\s+hôm\s+sau)\b", re.IGNORECASE)),
            ("AFTERNOON", re.compile(r"\b(chiều\s+hôm\s+ấy|chiều\s+hôm\s+đó|buổi\s+chiều\s+hôm\s+ấy)\b", re.IGNORECASE)),
            ("NOON", re.compile(r"\b(trưa\s+hôm\s+ấy|trưa\s+hôm\s+đó|buổi\s+trưa)\b", re.IGNORECASE)),
        ]
        prop_stems = [
            "chiếc kẹp", "kẹp tóc", "kẹp pha lê", "kẹp", "thỏi son", "son", "chìa khóa",
            "bức thư", "lá thư", "thư", "nhẫn", "sổ", "hóa đơn", "biên lai", "vali",
            "điện thoại", "khăn", "ảnh", "áo khoác",
        ]
        prop_re = re.compile(r"\b(" + "|".join(re.escape(p) for p in prop_stems) + r")\b", re.IGNORECASE)

        def _clean_prop_name(raw_p: str) -> str:
            cleaned = re.sub(r"^(?:chiếc|cái|thỏi|bức|lá|tấm|cuốn)\s+", "", raw_p.strip().lower())
            if "kẹp" in cleaned:
                return "kẹp"
            if "son" in cleaned:
                return "son"
            if "thư" in cleaned:
                return "thư"
            return cleaned

        def _is_surface_observation_text(text: str) -> bool:
            t = text.lower()
            if re.search(r"\b(?:thấy|nhìn\s+(?:thấy|lại)?|trông\s+thấy)\s+.*?\s+(?:trên|tại)\s+(?:bàn|kệ|tủ|giường|mặt\s+bàn|ghế|sàn)\b", t):
                return True
            if re.search(r"\bvẫn\s+(?:ở|nằm|đúng\s+nơi|y\s+nguyên|y\s+vị\s+trí)\b", t):
                return True
            if re.search(r"\bnhớ\s+lại\b", t):
                return True
            return False

        hook_candidates = [
            (idx, s) for idx, s in enumerate(script.segments[:6])
            if s.delivery_profile == "HOOK" or idx < 3
        ]

        for h_idx, hs in hook_candidates:
            hs_prop_m = prop_re.search(hs.text)
            if not hs_prop_m:
                continue
            matched_prop = _clean_prop_name(hs_prop_m.group(1))
            hook_tod = None
            for tod_name, tod_pat in tod_patterns:
                m_tod = tod_pat.search(hs.text)
                if m_tod:
                    hook_tod = (tod_name, m_tod.group(1))
                    break
            if not hook_tod:
                continue

            prop_already_taken_out = False

            for b_idx in range(h_idx + 1, len(script.segments)):
                bs = script.segments[b_idx]
                if bs.delivery_profile in ("HOOK", "ENDING"):
                    continue

                bs_lower = bs.text.lower()
                is_flashback = any(fb in bs_lower for fb in ["nhớ lại", "hồi tưởng", "lúc trước", "khi nãy", "trước đó"])
                if is_flashback:
                    continue

                if _is_surface_observation_text(bs.text):
                    continue

                window_segs = [bs]
                next_seg = script.segments[b_idx + 1] if b_idx + 1 < len(script.segments) else None
                if next_seg and next_seg.delivery_profile not in ("HOOK", "ENDING"):
                    has_next_tod = any(tod_pat.search(next_seg.text) for _, tod_pat in tod_patterns)
                    if not has_next_tod:
                        window_segs.append(next_seg)

                window_text = " ".join(s.text for s in window_segs)
                win_lower = window_text.lower()

                if matched_prop not in win_lower:
                    continue

                has_strong_discovery = any(act in win_lower for act in [
                    "tìm thấy", "phát hiện", "chạm phải", "bất ngờ thấy", "tình cờ thấy",
                    "vô tình thấy", "rơi ra từ", "lấy ra khỏi", "rút ra khỏi", "lấy ra một",
                    "lấy ra chiếc", "lấy ra thỏi", "lấy ra bức", "lấy ra lá", "lấy ra tấm",
                ])
                has_container_action = (
                    any(act in win_lower for act in ["lấy ra", "mở ra", "đưa tay vào"])
                    and any(c in win_lower for c in ["túi", "áo", "ví", "cốp", "hộc", "ngăn kéo"])
                )
                has_discovery = has_strong_discovery or has_container_action

                if prop_already_taken_out:
                    continue

                if not has_discovery:
                    continue

                body_tod = None
                for tod_name, tod_pat in tod_patterns:
                    m_tod = tod_pat.search(window_text)
                    if m_tod:
                        body_tod = (tod_name, m_tod.group(1))
                        break

                if not body_tod and b_idx > 0:
                    prev_s = script.segments[b_idx - 1]
                    if prev_s.delivery_profile not in ("HOOK", "ENDING"):
                        for tod_name, tod_pat in tod_patterns:
                            m_tod = tod_pat.search(prev_s.text)
                            if m_tod:
                                body_tod = (tod_name, m_tod.group(1))
                                break

                prop_already_taken_out = True

                if body_tod and body_tod[0] != hook_tod[0]:
                    conflict_seg = bs
                    fact_conflicts.append({
                        "fact_id": "HOOK_BODY_TIMELINE_CONTRADICTION",
                        "segment_id": hs.id,
                        "type": "HOOK_TIMELINE_CONTRADICTION",
                        "rule": "HOOK_TIMELINE_CONTRADICTION",
                        "expected": body_tod[1],
                        "found": hook_tod[1],
                        "description": f"Hook [{hs.id}] kể phát hiện {matched_prop} vào '{hook_tod[1]}', nhưng cảnh phát hiện thực tế tại [{conflict_seg.id}] diễn ra vào '{body_tod[1]}'.",
                    })
                    evidence_issues.append({
                        "segment_id": hs.id,
                        "related_segment_ids": [conflict_seg.id],
                        "excerpt": hs.text[:120],
                        "rule": "HOOK_TIMELINE_CONTRADICTION",
                        "type": "HOOK_TIMELINE_CONTRADICTION",
                        "severity": "CRITICAL",
                        "recommended_action": f"Đồng bộ thời gian phát hiện manh mối giữa Hook [{hs.id}] và thân truyện [{conflict_seg.id}] (sửa [{hs.id}] thành '{body_tod[1]}').",
                        "message": f"Phân đoạn Hook [{hs.id}] mâu thuẫn thời gian với phân đoạn [{conflict_seg.id}]: Hook kể '{hook_tod[1]}' trong khi thân truyện diễn ra vào '{body_tod[1]}'.",
                    })
                    logic_issues.append(f"[{hs.id}] Hook timeline mismatch with [{conflict_seg.id}]: '{hook_tod[1]}' vs '{body_tod[1]}'.")
                    revision_requests.append(f"Synchronize discovery time in Hook {hs.id} with body segment {conflict_seg.id}.")
                    break

        # 6.8 PROP LOCATION & CONTINUITY STATE AUDIT (PROP_LOCATION_CONTRADICTION / OBJECT_CONTINUITY_CONTRADICTION)
        def _normalize_container_name(raw_text: str) -> Optional[str]:
            raw = raw_text.strip().lower()
            if re.search(r"\b(?:túi\s+áo(?:\s+khoác|\s+vest)?|túi\s+quần)\b", raw):
                return "túi áo"
            if re.search(r"\b(?:túi\s+xách|túi\s+cầm\s+tay|balo|ba\s+lô|cặp\s+xách|cặp)\b", raw):
                return "túi xách"
            if re.search(r"\b(?:ví(?:\s+tiền|\s+cầm\s+tay)?|chiếc\s+ví|trong\s+ví|bóp)\b", raw):
                return "ví"
            if re.search(r"\b(?:cốp(?:\s+xe)?|hộc\s+xe)\b", raw):
                return "cốp xe"
            if re.search(r"\b(?:ngăn\s+kéo|hộc\s+bàn)\b", raw):
                return "ngăn kéo"
            if re.search(r"\btúi\b", raw):
                return "túi"
            return None

        container_pats = [
            ("túi áo", re.compile(r"\b(túi\s+áo\s+khoác|túi\s+áo|túi\s+quần)\b", re.IGNORECASE)),
            ("túi xách", re.compile(r"\b(túi\s+xách|túi\s+cầm\s+tay|balo|ba\s+lô|cặp\s+xách)\b", re.IGNORECASE)),
            ("ví", re.compile(r"\b(ví\s+tiền|chiếc\s+ví|trong\s+ví)\b", re.IGNORECASE)),
            ("cốp xe", re.compile(r"\b(cốp\s+xe|hộc\s+xe)\b", re.IGNORECASE)),
            ("ngăn kéo", re.compile(r"\b(ngăn\s+kéo|hộc\s+bàn)\b", re.IGNORECASE)),
        ]
        placed_pats = [
            re.compile(r"\bđặt\s+(?:lại\s+)?(?:chiếc\s+|thỏi\s+|tấm\s+|bức\s+|cuốn\s+|lá\s+)?(?:\w+\s+)?(?:kẹp|son|nhẫn|thư|sổ|hóa\s+đơn|ảnh|khăn|chìa\s+khóa|ví)\s+(?:lên|xuống|vào|trên)\s+(bàn|kệ|giường|mặt\s+bàn|tủ|hộp|ngăn\s+kéo)\b", re.IGNORECASE),
            re.compile(r"\b(?:cất|để)\s+(?:chiếc\s+|thỏi\s+|tấm\s+|bức\s+|cuốn\s+|lá\s+)?(?:\w+\s+)?(?:kẹp|son|nhẫn|thư|sổ|hóa\s+đơn|ảnh|khăn|chìa\s+khóa|ví)\s+(?:lên|vào|trên)\s+(bàn|kệ|hộp)\b", re.IGNORECASE),
        ]
        return_to_container_pat = re.compile(
            r"\b(?:bỏ|cất|nhét|cho|đút|đặt)\s+"
            r"(?:(?:chiếc|cái|thỏi|lá|tấm|bức|cuốn|món|vật|nó)?\s*([a-zA-Z0-9_\s\u00C0-\u1EF9]{0,25}?)\s*)?"
            r"(?:trở\s+lại|lại)?\s*(?:vào|vào\s+lại)\s+"
            r"(?:trong\s+)?(túi(?:\s+áo|\s+quần|\s+xách)?|ví|cốp(?:\s+xe)?|hộc(?:\s+bàn|\s+xe)?|ngăn\s+kéo)\b",
            re.IGNORECASE,
        )

        prop_locations = {}
        for seg in script.segments:
            seg_lower = seg.text.lower()
            cur_idx = script.segments.index(seg)

            for pat in placed_pats:
                m_placed = pat.search(seg.text)
                if m_placed:
                    prop_m = prop_re.search(m_placed.group(0)) or prop_re.search(seg.text)
                    if prop_m:
                        p_name = _clean_prop_name(prop_m.group(1))
                        orig_c = None
                        for c_name, c_pat in container_pats:
                            if c_pat.search(seg_lower) or any(c_pat.search(s.text.lower()) for s in script.segments[max(0, cur_idx-3):cur_idx]):
                                orig_c = c_name
                                break
                        prop_locations[p_name] = {
                            "current_loc": m_placed.group(1) or "bàn",
                            "is_surface": True,
                            "from_container": orig_c or "túi áo",
                            "placed_id": seg.id,
                            "placed_excerpt": seg.text[:100],
                        }

            # Return / move to container check
            for ret_m in return_to_container_pat.finditer(seg_lower):
                ret_obj_text = ret_m.group(1) or ""
                ret_container_text = ret_m.group(2) or ""
                dest_c = _normalize_container_name(ret_container_text)
                # Search prop specifically within the object or clause of this action, not the entire sentence
                ret_prop_m = prop_re.search(ret_obj_text) or prop_re.search(ret_m.group(0))
                ret_p_name = _clean_prop_name(ret_prop_m.group(1)) if ret_prop_m else None

                if not ret_p_name and ("nó" in ret_obj_text or not ret_obj_text.strip()):
                    surface_props = [p for p, loc in prop_locations.items() if loc.get("is_surface")]
                    if len(surface_props) == 1:
                        ret_p_name = surface_props[0]

                if ret_p_name and dest_c:
                    if ret_p_name in prop_locations:
                        prop_locations[ret_p_name]["current_loc"] = dest_c
                        prop_locations[ret_p_name]["is_surface"] = False
                        prop_locations[ret_p_name]["moved_id"] = seg.id
                    else:
                        prop_locations[ret_p_name] = {
                            "current_loc": dest_c,
                            "is_surface": False,
                            "from_container": dest_c,
                            "placed_id": seg.id,
                            "placed_excerpt": seg.text[:100],
                            "moved_id": seg.id,
                        }

            # Check for contradiction with subsequent segments
            for p_name, loc in list(prop_locations.items()):
                placed_id = loc.get("placed_id", "001")
                if int(seg.id) <= int(placed_id):
                    continue
                if _is_surface_observation_text(seg.text):
                    continue
                is_flashback = any(fb in seg_lower for fb in ["nhớ lại", "hồi tưởng", "lúc trước", "khi nãy", "hình ảnh"])
                if is_flashback:
                    continue

                claimed_c = _normalize_container_name(seg_lower)
                has_prop_mention = (
                    f"ngoài {p_name}" in seg_lower
                    or f"ngoài chiếc {p_name}" in seg_lower
                    or f"ngoài thỏi {p_name}" in seg_lower
                    or f"vẫn còn {p_name}" in seg_lower
                    or f"còn có {p_name}" in seg_lower
                    or (bool(claimed_c) and (f"trong {claimed_c}" in seg_lower and p_name in seg_lower))
                    or ("trong túi" in seg_lower and p_name in seg_lower)
                )

                if has_prop_mention:
                    is_contradiction = False
                    reason = ""
                    if loc.get("is_surface"):
                        if claimed_c or "trong túi" in seg_lower or "trong ví" in seg_lower:
                            is_contradiction = True
                            c_display = claimed_c or "túi"
                            reason = f"kể {p_name} trong {c_display}, trong khi ở [{placed_id}] đã được lấy ra đặt lên {loc.get('current_loc', 'bàn')}"
                    else:
                        cur_c = loc.get("current_loc")
                        if claimed_c and cur_c:
                            if claimed_c == "túi" and ("túi" in cur_c):
                                pass
                            elif claimed_c != cur_c:
                                is_contradiction = True
                                moved_from_id = loc.get("moved_id", placed_id)
                                reason = f"kể {p_name} trong {claimed_c}, trong khi ở [{moved_from_id}] đã cất vào {cur_c}"

                    if is_contradiction:
                        fact_conflicts.append({
                            "fact_id": "PROP_LOCATION_CONTRADICTION",
                            "segment_id": seg.id,
                            "type": "PROP_LOCATION_CONTRADICTION",
                            "expected": f"{p_name} ở {loc.get('current_loc')}",
                            "found": reason,
                            "description": f"Phân đoạn [{seg.id}] mâu thuẫn vị trí đạo cụ (PROP_LOCATION_CONTRADICTION): {reason}.",
                        })
                        evidence_issues.append({
                            "segment_id": seg.id,
                            "related_segment_ids": [placed_id],
                            "excerpt": seg.text[:120],
                            "rule": "PROP_LOCATION_CONTRADICTION",
                            "severity": "CRITICAL",
                            "recommended_action": f"Sửa phân đoạn [{seg.id}] để không mâu thuẫn vị trí đạo cụ của {p_name}.",
                            "message": f"Phân đoạn [{seg.id}] vi phạm vị trí đạo cụ (PROP_LOCATION_CONTRADICTION): {reason}.",
                        })
                        logic_issues.append(f"[{seg.id}] Prop location contradiction with [{placed_id}]: {reason}.")
                        revision_requests.append(f"Fix segment {seg.id} prop location contradiction with {placed_id}.")
                        break

        # 7. CHARACTER FACT VIOLATION AUDIT (Family structure / gender / role consistency)
        bible_text_lower = json.dumps(story_bible.to_dict(), ensure_ascii=False).lower()
        has_daughter_or_sister_in_bible = any(
            term in bible_text_lower
            for term in ["con gái", "chị gái", "em gái", "một trai một gái", "hai chị em"]
        )
        two_sons_in_bible = any(
            term in bible_text_lower
            for term in ["hai người con trai", "hai con trai", "2 người con trai", "hai anh em trai"]
        )
        for s in script.segments:
            s_lower = s.text.lower()
            if any(term in s_lower for term in ["hai người con trai", "hai con trai", "2 người con trai", "cả hai cậu con trai", "hai anh em trai"]):
                if has_daughter_or_sister_in_bible and not two_sons_in_bible:
                    fact_conflicts.append({
                        "fact_id": "CHAR_FAMILY_STRUCTURE",
                        "segment_id": s.id,
                        "type": "CHARACTER_FACT_VIOLATION",
                        "expected": "1 con trai, 1 con gái / chị em",
                        "found": "hai người con trai",
                        "description": f"Character fact violation in segment {s.id}: Script states 'hai người con trai' but Story Bible specifies daughter/sister."
                    })
                    evidence_issues.append({
                        "segment_id": s.id,
                        "excerpt": s.text[:100],
                        "rule": "CHARACTER_FACT_VIOLATION",
                        "severity": "CRITICAL",
                        "recommended_action": "Sửa lại giới tính và cấu trúc con cái/anh chị em khớp chính xác với Story Bible.",
                        "message": f"Phân đoạn [{s.id}] sai lệch cấu trúc nhân vật ('hai người con trai' mâu thuẫn với dữ kiện con gái/chị gái trong Story Bible)."
                    })
                    logic_issues.append(f"[{s.id}] Character fact violation: stated two sons contradicting Story Bible family structure.")
                    revision_requests.append(f"Fix character gender/family count in segment {s.id} to match Story Bible.")

        # 8. UNGROUNDED NAMED CHARACTER HALLUCINATION AUDIT
        allowed_names = {"minh"}
        if isinstance(story_bible.protagonist, dict):
            p_name = str(story_bible.protagonist.get("name", "")).strip()
            if p_name:
                allowed_names.add(p_name.lower())
                for token in p_name.split():
                    allowed_names.add(token.lower())
        elif isinstance(story_bible.protagonist, str) and story_bible.protagonist.strip():
            allowed_names.add(story_bible.protagonist.strip().lower())
            for token in story_bible.protagonist.strip().split():
                allowed_names.add(token.lower())

        for sc in (story_bible.supporting_characters or []):
            if isinstance(sc, dict):
                sc_name = str(sc.get("name", "")).strip()
                if sc_name:
                    allowed_names.add(sc_name.lower())
                    for token in sc_name.split():
                        allowed_names.add(token.lower())

        # Also extract any capitalized proper names mentioned anywhere in Story Bible fields
        bible_raw_str = json.dumps(story_bible.to_dict(), ensure_ascii=False)
        for cap_word in re.findall(r"\b[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặẹẻẽềềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+\b", bible_raw_str):
            allowed_names.add(cap_word.lower())

        excluded_cap_words = {
            "việt", "nam", "hà", "nội", "sài", "gòn", "đà", "nẵng", "huế", "sau", "cánh", "cửa",
            "hai", "ba", "tư", "năm", "sáu", "bảy", "chủ", "nhật", "tết", "xuân", "hạ", "thu", "đông"
        }
        honorific_pattern = re.compile(
            r"\b(anh|chị|ông|bà|cô|chú|bác|cậu|dì|mợ)\s+([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ][a-zàáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặẹẻẽềềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+)\b"
        )
        for s in script.segments:
            for match in honorific_pattern.finditer(s.text):
                honorific, char_name = match.group(1), match.group(2)
                name_lower = char_name.lower()
                if name_lower not in allowed_names and name_lower not in excluded_cap_words:
                    fact_conflicts.append({
                        "fact_id": "UNGROUNDED_CHARACTER",
                        "segment_id": s.id,
                        "type": "UNGROUNDED_CHARACTER_HALLUCINATION",
                        "expected": list(allowed_names),
                        "found": f"{honorific} {char_name}",
                        "description": f"Ungrounded character '{honorific} {char_name}' in segment {s.id} does not exist in Story Bible."
                    })
                    evidence_issues.append({
                        "segment_id": s.id,
                        "excerpt": s.text[:100],
                        "rule": "UNGROUNDED_CHARACTER_HALLUCINATION",
                        "severity": "CRITICAL",
                        "recommended_action": "Chỉ sử dụng nhân vật đã được khai báo trong Story Bible hoặc dùng danh từ chung ('người hàng xóm', 'người thân').",
                        "message": f"Phân đoạn [{s.id}] tự ý bịa thêm nhân vật có tên riêng '{honorific} {char_name}' không có trong Story Bible."
                    })
                    logic_issues.append(f"[{s.id}] Ungrounded character hallucination: '{honorific} {char_name}' not in Story Bible.")
                    revision_requests.append(f"Remove ungrounded character '{honorific} {char_name}' in segment {s.id}.")

        # 9. NATURAL LANGUAGE & MELODRAMA DENSITY V2 AUDIT (SHOW, DON'T LABEL)
        v2_severe_melodrama = [
            "bí mật động trời",
            "sự thật động trời",
            "đòn chí mạng",
            "sự thật kinh hoàng",
            "cuộc gặp gỡ định mệnh",
            "đau đớn đến tận cùng",
            "vĩ đại ẩn giấu",
            "mê cung không lối thoát",
            "nấc nghẹn ngào đến xé lòng",
            "nghẹn ngào đến xé lòng",
        ]
        melodrama_cliches = v2_severe_melodrama + [
            "chấn động toàn bộ",
            "cuộc chiến ngầm khốc liệt",
            "không tiếng súng",
            "đập tan mọi nghi kỵ",
            "bóc tách sự thật",
            "sét đánh ngang tai",
            "bão táp phong ba",
            "chết lặng trong đau đớn",
            "tan nát cõi lòng",
            "cơn địa chấn",
            "vạch trần bộ mặt thật",
            "bản án lương tâm",
            "bi kịch đẫm nước mắt",
            "sự thật rỉ máu",
            "chiếc lồng kính ngột ngạt",
            "bóng ma vô hình",
            "mặt nạ hoàn hảo",
            "bức tường phòng thủ cuối cùng sụp đổ",
            "mảnh vỡ vụn",
            "đẩy mọi thứ xuống vực sâu",
            "không gian xung quanh đặc quánh lại",
            "như một nhát dao đâm thẳng",
            "đứng lặng như tượng đá",
            "những giọt nước mắt muộn màng",
            "tiếng khóc xé lòng",
            "vết thương sâu hoắm",
            "vén bức màn dối trá",
            "lời cảnh tỉnh",
            "cái tát trời giáng",
            "sự thật nghiệt ngã",
            "đau đớn tột cùng",
            "hạnh phúc vô bờ",
            "xé toạc thành từng mảnh",
            "phơi bày dưới ánh sáng",
        ]
        cliche_hits: List[Tuple[str, str, str]] = []
        severe_v2_hits: List[Tuple[str, str, str]] = []
        for s in script.segments:
            s_lower = s.text.lower()
            for phrase in melodrama_cliches:
                if phrase in s_lower:
                    hit = (s.id, phrase, s.text[:90])
                    cliche_hits.append(hit)
                    if phrase in v2_severe_melodrama:
                        severe_v2_hits.append(hit)

        if len(cliche_hits) >= 2 or len(severe_v2_hits) >= 1:
            first_seg_id, _, first_excerpt = (severe_v2_hits or cliche_hits)[0]
            found_phrases = ", ".join(f"'{p}'" for _, p, _ in cliche_hits[:6])
            evidence_issues.append({
                "segment_id": first_seg_id,
                "excerpt": first_excerpt,
                "rule": "MELODRAMA_DENSITY_V2",
                "severity": "HIGH",
                "recommended_action": "Show, Don't Label: Mô tả hành động, vật thể, khoảng lặng và cử chỉ cụ thể thay vì dùng tính từ giật gân/kịch tính hóa.",
                "message": f"Phát hiện ngôn từ AI kịch tính hóa / dán nhãn cảm xúc ({len(cliche_hits)} cụm từ: {found_phrases})."
            })
            if len(cliche_hits) >= 2:
                evidence_issues.append({
                    "segment_id": first_seg_id,
                    "excerpt": first_excerpt,
                    "rule": "MELODRAMATIC_CLICHE_DENSITY",
                    "severity": "HIGH",
                    "recommended_action": "Chuyển sang giọng kể MC Minh tự nhiên, điềm đạm, gần gũi; loại bỏ các cụm từ sáo rỗng, cường điệu giật gân.",
                    "message": f"Mật độ ngôn từ sáo rỗng/kịch tính hóa quá cao ({len(cliche_hits)} cụm từ: {found_phrases})."
                })
            logic_issues.append(f"Melodramatic cliche density V2 too high ({len(cliche_hits)} hits: {found_phrases}).")
            revision_requests.append("Replace melodramatic cliches with natural conversational MC Minh phrasing (Show, Don't Label).")

        # 10. ENDING PROPORTION & SEMANTIC REPETITION AUDIT (5-8% target, 1 clear takeaway)
        if len(script.segments) >= 20:
            closing_segs = [
                s for i, s in enumerate(script.segments)
                if s.delivery_profile == "ENDING" or (i >= int(len(script.segments) * 0.88) and s.delivery_profile in ("ENDING", "COMMENT"))
            ]
            ratio = len(closing_segs) / len(script.segments)
            if ratio > 0.12:
                evidence_issues.append({
                    "segment_id": closing_segs[0].id if closing_segs else script.segments[-1].id,
                    "excerpt": closing_segs[0].text[:90] if closing_segs else "",
                    "rule": "ENDING_PROPORTION_VIOLATION",
                    "severity": "HIGH",
                    "recommended_action": "Rút gọn phần kết và chiêm nghiệm về mức 5% - 8% tổng thời lượng kịch bản, tránh giảng đạo lặp lại.",
                    "message": f"Phần kết & chiêm nghiệm chiếm {ratio*100:.1f}% ({len(closing_segs)}/{len(script.segments)} phân đoạn), vượt quá giới hạn 5–8%."
                })
                repetition_issues.append(f"Ending/reflection block is too long ({ratio*100:.1f}%, target 5-8%).")
                revision_requests.append("Trim repetitive moralizing ending segments to keep ending within 5-8% of script.")

        # Semantic Repetition across final 10 segments
        tail_window = script.segments[-10:] if len(script.segments) >= 6 else []
        if len(tail_window) >= 4:
            # Exclude Hook/Reveal segments if script is short
            non_reveal_tail = [
                s for s in tail_window
                if s.delivery_profile not in ("HOOK", "REVEAL", "MYSTERY")
            ]
            moral_markers = [
                "bài học", "đạo lý", "luân lý", "lời cảnh tỉnh", "cuộc sống dạy",
                "nhắc nhở chúng ta", "chân lý", "triết lý sống", "mặt nạ",
                "bài học đắt giá", "đúc kết lại", "giảng giải", "quy luật cuộc đời",
            ]
            moral_segs: List[ScriptSegment] = []
            for s in non_reveal_tail:
                s_low = s.text.lower()
                # Do not count pure sign-off ("Cảm ơn quý vị...", "Tôi là Minh... Hẹn gặp lại") as moralizing lesson
                is_pure_signoff = any(k in s_low for k in ["hẹn gặp lại quý vị", "tôi là minh", "cảm ơn quý vị đã lắng nghe", "bấm chia sẻ"]) and not any(m in s_low for m in ["bài học", "chiếc mặt nạ", "nhận ra rằng"])
                if not is_pure_signoff and any(m in s_low for m in moral_markers):
                    moral_segs.append(s)

            # Check pairwise semantic/lexical similarity on content words among tail reflection segments
            high_sim_pairs = 0
            stop_words = {
                "của", "những", "trong", "không", "được", "người", "mình", "chúng", "ta",
                "rằng", "một", "như", "khi", "với", "cho", "này", "đó", "đã", "sẽ", "và", "là", "có",
            }
            for idx_a in range(len(moral_segs)):
                toks_a = {w for w in re.findall(r"\w+", moral_segs[idx_a].text.lower()) if len(w) > 2 and w not in stop_words}
                for idx_b in range(idx_a + 1, len(moral_segs)):
                    toks_b = {w for w in re.findall(r"\w+", moral_segs[idx_b].text.lower()) if len(w) > 2 and w not in stop_words}
                    if toks_a and toks_b:
                        jacc = len(toks_a & toks_b) / max(1, min(len(toks_a), len(toks_b)))
                        if jacc >= 0.35:
                            high_sim_pairs += 1

            if len(moral_segs) >= 4 or (len(moral_segs) >= 3 and high_sim_pairs >= 2):
                first_rep_seg = moral_segs[0]
                evidence_issues.append({
                    "segment_id": first_rep_seg.id,
                    "excerpt": first_rep_seg.text[:100],
                    "rule": "ENDING_SEMANTIC_REPETITION",
                    "severity": "HIGH",
                    "recommended_action": "Gộp các đoạn giảng đạo trùng ý ở cuối kịch bản thành đúng 1 thông điệp chiêm nghiệm duy nhất (emotional resolution -> 1 reflection -> optional question -> concise sign-off).",
                    "message": f"Phát hiện {len(moral_segs)} phân đoạn ở cuối kịch bản lặp lại cùng một bài học đạo lý/chiêm nghiệm."
                })
                repetition_issues.append(f"Ending semantic repetition detected across {len(moral_segs)} closing segments.")
                revision_requests.append("Compress semantically repetitive reflection segments in closing act into a single takeaway.")

        # 11. NATURAL PROSE, STRUCTURED-DATA LEAKAGE & PROOF REALISM
        malformed_patterns = [
            r"khiến\s+[^.!?]{0,45}\s+đau\s+lòng\s+vào\s+(?:trái\s+)?tim",
            r"khiến\s+[^.!?]{0,30}\s+như\s+bị\s+bàng\s+hoàng\s+sửng\s+sốt",
            r"\bcòn\s+[^.!?]{1,35}\s+thì\.\s*$",
            r"^sự\s+sụp\s+đổ\s+[^.!?]{5,90}\s+khi\s+[^.!?]+\.\s*$",
        ]
        # A sentence that resumes in lowercase after a full stop ("sếp Hùng. ở công ty")
        # is a truncated ellipsis; TTS reads it as two broken sentences.
        lowercase_restart = re.compile(
            r"(?<![A-ZĐ])[^\W\d_]{2,}\.\s+[a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]"
        )
        # "là1 phần"; times such as "17h30" are fine.
        glued_digit = re.compile(r"(?<![\w])[a-zđàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]{2,}\d")
        for segment in script.segments:
            if glued_digit.search(segment.text) or lowercase_restart.search(segment.text) or any(re.search(pattern, segment.text, re.IGNORECASE) for pattern in malformed_patterns):
                evidence_issues.append({
                    "segment_id": segment.id,
                    "excerpt": segment.text[:120],
                    "rule": "MALFORMED_VIETNAMESE_PROSE",
                    "severity": "CRITICAL",
                    "recommended_action": "Viết lại thành câu tiếng Việt hoàn chỉnh, đúng chủ-vị và đúng đối tượng cảm xúc; không ghép các mảnh câu máy móc.",
                    "message": f"Phân đoạn [{segment.id}] có câu gãy nghĩa hoặc quan hệ chủ thể sai.",
                })
                logic_issues.append(f"[{segment.id}] Malformed Vietnamese prose.")
                revision_requests.append(f"Rewrite malformed Vietnamese prose in segment {segment.id}.")

        # Narration that grades evidence like an audit report ("Manh mối thứ ba
        # này chứng minh…") is a prompt artefact, not storytelling.
        # Defensive narration ("chưa đủ để kết luận" in segment after segment) is
        # what a model writes when it only knows prohibitions; flag it for the editor.
        from apps.script_factory.script_craft import hedge_segment_ids
        hedged = hedge_segment_ids(script.segments)
        if len(hedged) >= 4:
            evidence_issues.append({
                "segment_id": hedged[0],
                "excerpt": next(seg.text for seg in script.segments if seg.id == hedged[0])[:120],
                "rule": "NARRATOR_HEDGING",
                "severity": "WARNING",
                "recommended_action": "Thay câu rào đón bằng một hành động kiểm chứng cụ thể của nhân vật.",
                "message": f"Người kể rào đón ở {len(hedged)} đoạn ({', '.join(hedged[:6])}), làm truyện nhạt.",
            })

        analyst_pattern = re.compile(
            r"(?:manh\s+mối|chi\s+tiết|bằng\s+chứng)\s+(?:thứ\s+\w+|đầu\s+tiên|cuối\s+cùng|\d+)\s+(?:này\s+)?"
            r"(?:từ\s+[^.,]{1,30}\s+)?(?:chỉ\s+)?(?:chứng\s+minh|cho\s+thấy|xác\s+nhận)"
            r"|\bchưa\s+chứng\s+minh\s+được\b",
            re.IGNORECASE,
        )
        for segment in script.segments:
            if analyst_pattern.search(segment.text):
                evidence_issues.append({
                    "segment_id": segment.id,
                    "excerpt": segment.text[:120],
                    "rule": "ANALYST_NARRATION",
                    "severity": "HIGH",
                    "recommended_action": "Bỏ giọng phân tích kiểu biên bản; thể hiện giới hạn bằng chứng qua suy nghĩ hoặc câu hỏi của nhân vật.",
                    "message": f"Phân đoạn [{segment.id}] kể như biên bản phân tích bằng chứng thay vì kể chuyện.",
                })
                logic_issues.append(f"[{segment.id}] Analyst-style evidence narration.")
                revision_requests.append(f"Rewrite analyst-style narration in segment {segment.id}.")

        causal_values: List[Tuple[str, str]] = []
        for chain_index, chain in enumerate(story_bible.causal_chains or []):
            if not isinstance(chain, dict):
                continue
            for field_name in ("cause", "decision", "action", "consequence", "why", "motivation", "how"):
                value = str(chain.get(field_name, "") or "").strip()
                if len(value.split()) >= 8:
                    causal_values.append((f"causal_chains[{chain_index}].{field_name}", value))
        for segment in script.segments:
            normalized_segment = re.sub(r"\s+", " ", segment.text).casefold()
            copied_fields = [
                field_name for field_name, value in causal_values
                if re.sub(r"\s+", " ", value).casefold().rstrip(".") in normalized_segment
            ]
            if len(copied_fields) >= 2:
                evidence_issues.append({
                    "segment_id": segment.id,
                    "excerpt": segment.text[:120],
                    "rule": "STRUCTURED_STORY_DATA_LEAKAGE",
                    "severity": "CRITICAL",
                    "recommended_action": "Chuyển dữ kiện nhân quả thành hành động, đối thoại hoặc lời kể tự nhiên; không ghép nguyên văn nhiều trường Story Bible.",
                    "message": f"Phân đoạn [{segment.id}] chép nguyên văn {len(copied_fields)} trường dữ liệu có cấu trúc từ Story Bible.",
                    "copied_fields": copied_fields,
                })
                logic_issues.append(f"[{segment.id}] Structured Story Bible fields leaked into spoken prose.")
                revision_requests.append(f"Naturalize structured Story Bible data in segment {segment.id}.")

        full_script_text = " ".join(segment.text for segment in script.segments).lower()
        definitive_paternity_claim = bool(re.search(
            r"(?:đứa\s+(?:bé|con)[^.!?]{0,45}(?:không\s+(?:phải|thể\s+là)\s+con\s+của|không\s+hề\s+có\s+huyết\s+thống)|"
            r"không\s+phải\s+máu\s+mủ\s+của|"
            r"không\s+(?:có|hề\s+có)\s+(?:bất\s+kỳ\s+)?(?:mối\s+)?(?:liên\s+hệ\s+)?huyết\s+thống)",
            full_script_text,
        ))
        paternity_proof_markers = (
            "xét nghiệm adn", "kết quả adn", "đối chiếu thời điểm thụ thai",
            "tuổi thai", "ngày thụ thai", "thời điểm thụ thai", "kết quả xét nghiệm huyết thống",
        )
        if definitive_paternity_claim and not any(marker in full_script_text for marker in paternity_proof_markers):
            target_segment = next(
                (segment for segment in script.segments if re.search(r"không\s+(?:phải|thể\s+là)\s+con\s+của|không\s+phải\s+máu\s+mủ|không\s+(?:có|hề\s+có)\s+[^.!?]{0,25}huyết\s+thống", segment.text, re.IGNORECASE)),
                script.segments[-1],
            )
            evidence_issues.append({
                "segment_id": target_segment.id,
                "excerpt": target_segment.text[:120],
                "rule": "UNSUPPORTED_PATERNITY_CLAIM",
                "severity": "CRITICAL",
                "recommended_action": "Chỉ nêu nghi vấn cho tới khi có xét nghiệm ADN hoặc mốc tuổi thai/thụ thai được đối chiếu rõ ràng trong câu chuyện.",
                "message": "Kịch bản kết luận huyết thống chắc chắn nhưng không kể ra căn cứ sinh học hoặc mốc thụ thai đủ kiểm chứng.",
            })
            logic_issues.append("Definitive paternity claim lacks biological or conception-timeline proof.")
            revision_requests.append("Add verifiable paternity proof or keep the claim explicitly uncertain.")

        # 12. LEGAL CLAIM SAFETY AUDIT
        unsafe_legal_patterns = [
            (r"tòa\s+án\s+tuyên\s+bố\s+vô\s+hiệu\s+ngay\s+lập\s+tức", "tuyên bố pháp lý tức thời của tòa án"),
            (r"công\s+an\s+bắt\s+giữ\s+khẩn\s+cấp\s+ngay\s+tại", "thủ tục bắt giữ hình sự khẩn cấp không xác thực"),
            (r"di\s+chúc\s+miệng\s+mặc\s+nhiên\s+vô\s+giá\s+trị", "kết luận luật thừa kế cứng nhắc"),
            (r"tước\s+quyền\s+thừa\s+kế\s+ngay\s+tức\s+khắc", "kết luận tước quyền thừa kế pháp lý"),
            (r"khẳng\s+định\s+quyền\s+sở\s+hữu\s+hợp\s+pháp\s+tuyệt\s+đối", "khẳng định pháp lý tuyệt đối từ giấy tờ cũ"),
            (r"tờ\s+giấy\s+này\s+chứng\s+minh\s+hoàn\s+toàn\s+quyền\s+sở\s+hữu", "khẳng định quyền sở hữu pháp lý tuyệt đối"),
            (r"vô\s+hiệu\s+hóa\s+hoàn\s+toàn\s+về\s+mặt\s+pháp\s+lý\s+ngay\s+tại\s+chỗ", "kết luận pháp lý tại chỗ thiếu căn cứ"),
            (r"(?:văn\s+bản\s+)?từ\s+bỏ\s+(?:mọi\s+|toàn\s+bộ\s+)?quyền\s+(?:làm\s+cha|nuôi\s+con|của\s+người\s+cha)", "coi việc xác định/không công nhận quan hệ cha con là một giấy từ bỏ đơn phương"),
        ]
        for s in script.segments:
            for pat, desc in unsafe_legal_patterns:
                if re.search(pat, s.text, re.IGNORECASE):
                    evidence_issues.append({
                        "segment_id": s.id,
                        "excerpt": s.text[:100],
                        "rule": "LEGAL_CLAIM_SAFETY",
                        "severity": "CRITICAL",
                        "recommended_action": "Diễn đạt dưới góc độ tâm lý, tình cảm gia đình hoặc manh mối cần xác minh, tránh phán quyết pháp lý chủ quan.",
                        "message": f"Phân đoạn [{s.id}] đưa ra khẳng định pháp lý thiếu an toàn ({desc})."
                    })
                    logic_issues.append(f"[{s.id}] Unsafe legal claim: {desc}.")
                    revision_requests.append(f"Soften assertive legal claim in segment {s.id} to emotional/social narrative framing.")
                    break

        # 13. INTERNAL EPISODE ID != PUBLIC EPISODE NUMBER AUDIT (INTERNAL_EPISODE_ID_SPOKEN)
        pub_ep_num = getattr(story_bible, "public_episode_number", None)
        internal_code_pat = re.compile(
            r"\b(?:mã\s+số\s+)?(EP_?[A-Z0-9_]*\d+|IDEA_\d+|PROJ_[A-Z0-9_]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            re.IGNORECASE,
        )
        spoken_ep_num_pat = re.compile(
            r"\btập\s+(?:số\s+|phim\s+|thứ\s+)?("
            r"\d+"
            r"|(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn)(?:\s+(?:một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn|linh|lẻ|không))*"
            r")\b",
            re.IGNORECASE,
        )
        for s in script.segments:
            m_code = internal_code_pat.search(s.text)
            m_spoken = spoken_ep_num_pat.search(s.text)
            spoken_hit = None
            if m_code:
                spoken_hit = m_code.group(0)
            elif m_spoken:
                num_phrase = m_spoken.group(1).strip().lower()
                # Check if this is an unauthorized episode number
                if pub_ep_num is None or str(pub_ep_num) != num_phrase:
                    spoken_hit = m_spoken.group(0)

            if spoken_hit:
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:100],
                    "rule": "INTERNAL_EPISODE_ID_SPOKEN",
                    "severity": "CRITICAL",
                    "recommended_action": "Xóa bỏ mã dự án/số tập nội bộ. Nếu không có public_episode_number, chỉ nói: 'Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.'",
                    "message": f"Phân đoạn [{s.id}] đọc mã dự án hoặc số tập nội bộ ('{spoken_hit}') vào lời dẫn."
                })
                fact_conflicts.append({
                    "fact_id": "INTERNAL_EPISODE_ID",
                    "segment_id": s.id,
                    "type": "INTERNAL_EPISODE_ID_SPOKEN",
                    "found": spoken_hit,
                    "description": f"MC spoke internal episode ID or unauthorized episode number '{spoken_hit}' in segment {s.id}."
                })
                logic_issues.append(f"[{s.id}] Internal episode ID spoken: '{spoken_hit}'.")
                revision_requests.append(f"Remove spoken episode ID '{spoken_hit}' in segment {s.id}.")

        # 13. FAKE SERIAL BREAK AUDIT (FAKE_SERIAL_BREAK)
        serial_break_pat = re.compile(
            r"(tập\s+tiếp\s+theo|phần\s+tiếp\s+theo|ở\s+phần\s+sau|hãy\s+đón\s+xem|đón\s+xem|chúng\s+ta\s+sẽ\s+quay\s+lại\s+sau|quay\s+lại\s+sau\s+ít\s+phút|hé\s+lộ\s+ở\s+phần\s+sau)",
            re.IGNORECASE,
        )
        for idx, s in enumerate(script.segments):
            m_serial = serial_break_pat.search(s.text)
            if m_serial:
                hit_str = m_serial.group(0)
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:100],
                    "rule": "FAKE_SERIAL_BREAK",
                    "severity": "CRITICAL",
                    "recommended_action": (
                        "Xóa bỏ hoàn toàn ngôn từ ngắt tập/hẹn phần sau giữa kịch bản hoặc ở đoạn kết; "
                        "mỗi tập là một câu chuyện hoàn chỉnh. Dùng lời chào kết chuẩn: "
                        "'Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.'"
                    ),
                    "message": f"Phân đoạn [{s.id}] chứa cụm từ ngắt tập / hẹn phần tiếp theo ('{hit_str}')."
                })
                logic_issues.append(f"[{s.id}] Fake serial break detected: '{hit_str}'.")
                revision_requests.append(f"Remove fake serial break '{hit_str}' in segment {s.id}.")

        # 14. CAUSAL LOGIC QC AUDIT (CAUSAL_GAP)
        from apps.script_factory.story_qc import (
            StoryQCEngine,
            _has_necessity_markers,
            _has_weak_cause_to_extreme_action,
        )
        story_qc_report = StoryQCEngine().audit_story_bible(story_bible)
        has_bible_causal_gap = "CAUSAL_GAP" in story_qc_report.rule_codes
        script_lower = all_text.lower()
        has_script_causal_gap = _has_weak_cause_to_extreme_action(
            script_lower,
            has_strong_necessity=_has_necessity_markers(script_lower),
        )
        if has_bible_causal_gap or has_script_causal_gap:
            body_segs = [s for s in script.segments if s.delivery_profile not in ("HOOK", "ENDING")]
            target_seg = next((s for s in script.segments if s.delivery_profile == "REVEAL"), body_segs[0] if body_segs else (script.segments[-1] if script.segments else ScriptSegment(id="001")))
            evidence_issues.append({
                "segment_id": target_seg.id,
                "excerpt": target_seg.text[:100],
                "rule": "CAUSAL_GAP",
                "severity": "CRITICAL",
                "recommended_action": "Bổ sung đầy đủ chuỗi nhân quả CAUSE -> DECISION -> ACTION -> CONSEQUENCE, giải thích rõ tại sao giải pháp bình thường là bất khả thi.",
                "message": f"Phân đoạn [{target_seg.id}] / Story Bible thiếu tính tất yếu nhân quả (CAUSAL_GAP) cho hành động/bước ngoặt lớn."
            })
            fact_conflicts.append({
                "fact_id": "CAUSAL_CHAIN",
                "segment_id": target_seg.id,
                "type": "CAUSAL_GAP",
                "description": "Causal gap between initial trigger/request and long-term extreme action."
            })
            logic_issues.append(f"[{target_seg.id}] CAUSAL_GAP: Missing causal necessity explaining why simpler alternative was impossible.")
            revision_requests.append(f"Repair causal gap in segment {target_seg.id} with explicit necessity and mechanism.")

        # Carry over critical Story Bible V3 logic failures (RELATIONSHIP_TIMELINE_CONTRADICTION, TIMELINE_FACT_CONTRADICTION, REVEAL_UNDERJUSTIFIED)
        for s_iss in (story_qc_report.issues if hasattr(story_qc_report, "issues") else []):
            s_rule = s_iss.get("rule")
            if s_rule in ("RELATIONSHIP_TIMELINE_CONTRADICTION", "TIMELINE_FACT_CONTRADICTION", "REVEAL_UNDERJUSTIFIED"):
                body_segs = [s for s in script.segments if s.delivery_profile not in ("HOOK", "ENDING")]
                target_seg = next((s for s in script.segments if s.delivery_profile == "REVEAL"), body_segs[0] if body_segs else (script.segments[-1] if script.segments else ScriptSegment(id="001")))
                evidence_issues.append({
                    "segment_id": target_seg.id,
                    "excerpt": target_seg.text[:100],
                    "rule": s_rule,
                    "severity": "CRITICAL",
                    "recommended_action": s_iss.get("suggested_repair") or "Sửa đổi mâu thuẫn thời gian/quan hệ trong Story Bible trước khi viết kịch bản.",
                    "message": s_iss.get("message", ""),
                })
                fact_conflicts.append({
                    "fact_id": "STORY_BIBLE_V3_LOGIC",
                    "segment_id": target_seg.id,
                    "type": s_rule,
                    "description": s_iss.get("message", "")
                })
                logic_issues.append(f"[{target_seg.id}] {s_rule}: {s_iss.get('message', '')}")
                revision_requests.append(f"Repair {s_rule} in Story Bible.")

        # 15. CHARACTER SECRET KNOWLEDGE CONSISTENCY AUDIT (CHARACTER_KNOWLEDGE_CONTRADICTION)
        knowing_chars: List[str] = []
        ignorant_chars: List[str] = []
        for sc in (story_bible.supporting_characters or []):
            if isinstance(sc, dict):
                sc_name = str(sc.get("name", "")).strip()
                sc_desc = " ".join(str(sc.get(k, "")) for k in ("description", "role", "reason_for_silence")).lower()
                if any(p in sc_desc for p in ["biết toàn bộ", "biết sự thật", "biết rõ", "biết hết", "cùng che giấu", "chọn cách câm lặng", "giữ kín bí mật cùng"]):
                    if sc_name:
                        knowing_chars.append(sc_name)
        for entry in (story_bible.knowledge_ledger or []):
            if isinstance(entry, dict):
                c_name = str(entry.get("character", "") or entry.get("who_knows_what", "")).strip()
                scope = str(entry.get("knowledge_scope", "")).strip().lower()
                if scope in ("full", "partial") and c_name:
                    knowing_chars.append(c_name)
                elif scope == "none" and c_name:
                    ignorant_chars.append(c_name)

        # Also check if any segment in the script explicitly states a character knew the whole truth
        char_knew_seg_pat = re.compile(
            r"(?:bà|ông|vợ|chồng|mẹ|cha|chị|anh|cô|chú|bác)\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐĨŨƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴỶỸ\w]*\s*(?:đã\s+biết\s+toàn\s+bộ|biết\s+rõ\s+sự\s+thật|biết\s+hết\s+mọi\s+chuyện|nhận\s+ra\s+ngay\s+từ\s+đầu|cùng\s+giữ\s+kín\s+bí\s+mật)",
            re.IGNORECASE,
        )
        for s in script.segments:
            m_knew = char_knew_seg_pat.search(s.text)
            if m_knew:
                knowing_chars.append(m_knew.group(0))

        solitude_pat = re.compile(
            r"(không\s+thể\s+sẻ\s+chia\s+cùng\s+ai|kể\s+cả\s+(?:với\s+)?người\s+vợ(?:\s+gối\s+chăn)?|không\s+một\s+ai\s+(?:hay\s+)?biết|không\s+ai\s+trên\s+đời\s+biết|chỉ\s+một\s+mình\s+[^\s,]+\s+biết)",
            re.IGNORECASE,
        )
        for s in script.segments:
            m_sol = solitude_pat.search(s.text)
            if m_sol and (knowing_chars or "CHARACTER_KNOWLEDGE_CONTRADICTION" in story_qc_report.rule_codes):
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:100],
                    "rule": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                    "severity": "CRITICAL",
                    "recommended_action": "Đồng bộ trạng thái biết/không biết bí mật của các nhân vật xuyên suốt Story Bible và toàn bộ phân đoạn.",
                    "message": f"Phân đoạn [{s.id}] khẳng định '{m_sol.group(0)}' mâu thuẫn với dữ kiện nhân vật khác ({', '.join(knowing_chars[:2])}) đã biết bí mật."
                })
                fact_conflicts.append({
                    "fact_id": "KNOWLEDGE_LEDGER",
                    "segment_id": s.id,
                    "type": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                    "found": m_sol.group(0),
                    "description": f"Segment {s.id} claims '{m_sol.group(0)}' contradicting character secret knowledge ({knowing_chars})."
                })
                logic_issues.append(f"[{s.id}] CHARACTER_KNOWLEDGE_CONTRADICTION: '{m_sol.group(0)}' contradicts known secret holders.")
                revision_requests.append(f"Fix character knowledge contradiction in segment {s.id}.")

        # Also check if an ignorant character reacts with secret knowledge before the reveal
        early_cutoff = max(1, int(len(script.segments) * 0.5))
        for s in script.segments[:early_cutoff]:
            if s.delivery_profile == "REVEAL":
                continue
            s_low = s.text.lower()
            for ig_char in ignorant_chars:
                ig_low = ig_char.lower()
                if ig_low and ig_low in s_low:
                    if any(p in s_low for p in [f"{ig_low} đã biết rõ sự thật từ trước", f"{ig_low} vốn đã biết toàn bộ bí mật", f"{ig_low} biết hết chân tướng ngay từ đầu"]):
                        evidence_issues.append({
                            "segment_id": s.id,
                            "excerpt": s.text[:100],
                            "rule": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                            "severity": "CRITICAL",
                            "recommended_action": f"Nhân vật '{ig_char}' chưa thể biết bí mật ở phần đầu kịch bản.",
                            "message": f"Phân đoạn [{s.id}] mô tả '{ig_char}' đã biết toàn bộ bí mật trước thời điểm phát hiện."
                        })
                        fact_conflicts.append({
                            "fact_id": "KNOWLEDGE_LEDGER",
                            "segment_id": s.id,
                            "type": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                            "found": ig_char,
                            "description": f"Character '{ig_char}' reacts with secret knowledge in segment {s.id} before learning it."
                        })
                        logic_issues.append(f"[{s.id}] CHARACTER_KNOWLEDGE_CONTRADICTION: '{ig_char}' has premature secret knowledge.")
                        revision_requests.append(f"Remove premature secret knowledge of '{ig_char}' in segment {s.id}.")

        # 16. EVIDENCE CHAIN MUST PROVE THE CLAIM AUDIT (EVIDENCE_DOES_NOT_PROVE_CLAIM)
        overreach_seg_pat = re.compile(
            r"(?:tấm\s+thẻ\s+bài|chiếc\s+thẻ\s+bài|chữ\s+ký\s+khác\s+lạ|bức\s+ảnh\s+cũ|mảnh\s+giấy\s+nhỏ|số\s+điện\s+thoại\s+lạ|chiếc\s+phong\s+bì|vết\s+sẹo).*?"
            r"(?:chứng\s+minh\s+hoàn\s+toàn|khẳng\s+định\s+chắc\s+chắn|đủ\s+để\s+kết\s+luận|là\s+bằng\s+chứng\s+không\s+thể\s+chối\s+cãi\s+rằng|chứng\s+tỏ\s+chắc\s+chắn).*?"
            r"(?:đã\s+đánh\s+tráo\s+danh\s+tính|chính\s+là\s+kẻ\s+giả\s+mạo|không\s+phải\s+là\s+ông\s+nội\s+thật|không\s+phải\s+là\s+cha\s+ruột|đã\s+chiếm\s+đoạt\s+toàn\s+bộ|đã\s+mạo\s+danh\s+suốt)",
            re.IGNORECASE,
        )
        for s in script.segments:
            m_ev = overreach_seg_pat.search(s.text)
            if m_ev:
                evidence_issues.append({
                    "segment_id": s.id,
                    "excerpt": s.text[:100],
                    "rule": "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    "severity": "CRITICAL",
                    "recommended_action": "Trình bày đúng giới hạn chứng minh của vật chứng (what_it_proves vs what_it_does_NOT_prove) và dẫn dắt sang câu hỏi điều tra tiếp theo.",
                    "message": f"Phân đoạn [{s.id}] nhảy cóc từ một vật chứng đơn lẻ sang kết luận cuối cùng mà thiếu bằng chứng trung gian."
                })
                fact_conflicts.append({
                    "fact_id": "EVIDENCE_CHAIN",
                    "segment_id": s.id,
                    "type": "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    "found": m_ev.group(0)[:80],
                    "description": f"Segment {s.id} jumps from initial clue directly to unsupported conclusion."
                })
                logic_issues.append(f"[{s.id}] EVIDENCE_DOES_NOT_PROVE_CLAIM: Clue does not directly prove final claim.")
                revision_requests.append(f"Rewrite segment {s.id} so the clue raises the next question instead of jumping to final conclusion.")

        if "EVIDENCE_DOES_NOT_PROVE_CLAIM" in story_qc_report.rule_codes and not any(iss.get("rule") == "EVIDENCE_DOES_NOT_PROVE_CLAIM" for iss in evidence_issues):
            first_seg = script.segments[0] if script.segments else ScriptSegment(id="001")
            evidence_issues.append({
                "segment_id": first_seg.id,
                "excerpt": first_seg.text[:100],
                "rule": "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                "severity": "CRITICAL",
                "recommended_action": "Bổ sung bằng chứng trung gian trong chuỗi manh mối trước khi đưa ra kết luận.",
                "message": "Chuỗi manh mối trong Story Bible nhảy cóc từ vật chứng ban đầu sang kết luận cuối cùng."
            })
            logic_issues.append("EVIDENCE_DOES_NOT_PROVE_CLAIM: Story Bible clue chain overreaches what single clue can prove.")
            revision_requests.append("Fix evidence-to-claim jump in clue chain.")

        # 15. SCRIPT TOPIC ADHERENCE AUDIT (FINAL_SCRIPT_TOPIC_DRIFT)
        # Evaluates actual script narration against user topic. Does NOT trust metadata.
        orig_topic = (
            getattr(story_bible, "original_user_topic", "")
            or getattr(story_bible, "topic", "")
            or ""
        ).strip()
        topic_intent_dict = getattr(story_bible, "topic_intent", None)
        script_topic_score = 100.0

        if orig_topic:
            from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent
            if isinstance(topic_intent_dict, dict) and topic_intent_dict.get("original_topic"):
                ti = TopicIntent.from_dict(topic_intent_dict)
            else:
                ti = extract_topic_intent(orig_topic)

            topic_eval = ti.evaluate_content_adherence(script, stage="script")
            script_topic_score = topic_eval["score"]
            if topic_eval["status"] != "PASS" or script_topic_score < 75.0:
                first_seg = script.segments[0] if script.segments else ScriptSegment(id="001")
                drift_msg = (
                    f"Kịch bản hoàn chỉnh bị trôi dạt chủ đề (FINAL_SCRIPT_TOPIC_DRIFT): "
                    f"Điểm bám sát chỉ đạt {script_topic_score}/100 "
                    f"(Centrality: {topic_eval['topic_centrality_score']}, "
                    f"Evidence: {topic_eval['topic_evidence_coverage']}, "
                    f"Reveal: {topic_eval['topic_reveal_alignment']}). "
                    f"Lời dẫn không giữ chủ đề người dùng '{orig_topic}' làm trọng tâm xuyên suốt câu chuyện."
                )
                if topic_eval.get("drift_terms"):
                    drift_msg += f" Phát hiện yếu tố ngoại lai lấn át: {', '.join(topic_eval['drift_terms'][:5])}."

                # Centrality only counts topic keywords. A story whose evidence and
                # reveal are both on topic, with no foreign trope, is not drifting —
                # it just phrases the topic differently ("quan hệ ngoài hôn nhân").
                # That is an editor note; a hard FAIL here sent on-topic scripts into
                # endless repair rounds that rewrote segment 001 and changed nothing.
                on_topic_story = (
                    topic_eval["topic_reveal_alignment"] >= 80
                    and topic_eval["topic_evidence_coverage"] >= 80
                    and not topic_eval.get("drift_terms")
                )
                if on_topic_story:
                    evidence_issues.append({
                        "segment_id": first_seg.id,
                        "excerpt": first_seg.text[:100],
                        "rule": "TOPIC_EMPHASIS_LOW",
                        "severity": "WARNING",
                        "recommended_action": f"Cân nhắc nhắc rõ hơn chủ đề '{orig_topic}' ở mở đầu và cao trào.",
                        "message": (
                            f"Cú lật và bằng chứng đúng chủ đề, nhưng lời dẫn ít gọi tên chủ đề "
                            f"(Centrality {topic_eval['topic_centrality_score']}/100)."
                        ),
                    })
                    script_topic_score = max(script_topic_score, 75.0)
                    drift_msg = ""
                if drift_msg:
                    evidence_issues.append({
                        "segment_id": first_seg.id,
                        "excerpt": first_seg.text[:100],
                        "rule": "FINAL_SCRIPT_TOPIC_DRIFT",
                        "severity": "CRITICAL",
                        "recommended_action": f"Viết lại kịch bản bám sát tuyệt đối chủ đề '{orig_topic}'.",
                        "message": drift_msg,
                    })
                    fact_conflicts.append({
                        "fact_id": "TOPIC_DRIFT",
                        "segment_id": first_seg.id,
                        "type": "FINAL_SCRIPT_TOPIC_DRIFT",
                        "expected": orig_topic,
                        "found": f"Score {script_topic_score}/100",
                        "description": drift_msg,
                    })
                    logic_issues.append(f"[FINAL_SCRIPT_TOPIC_DRIFT] {drift_msg}")
                    revision_requests.append(f"Regenerate/revise script to center on user topic: {orig_topic}.")

        # 20. SCRIPT PROSE & NATURAL STORYTELLING QC V3
        from apps.script_factory.story_logic_v3 import ScriptProseQCV3Engine
        prose_v3_engine = ScriptProseQCV3Engine()
        prose_issues = prose_v3_engine.audit_script_prose(script, story_bible)
        for p_iss in prose_issues:
            target_seg = script.segments[0] if script.segments else ScriptSegment(id="001")
            evidence_issues.append({
                "segment_id": target_seg.id,
                "excerpt": "",
                "rule": p_iss["rule"],
                "severity": p_iss.get("severity", "HIGH"),
                "recommended_action": "Chuẩn hóa văn phong theo hướng tự nhiên, không mang giọng báo cáo kiểm định.",
                "message": p_iss["message"],
            })
            if p_iss.get("severity") in ("CRITICAL", "HIGH"):
                logic_issues.append(f"[{p_iss['rule']}] {p_iss['message']}")

        # Compute status
        # 14. SEMANTIC STORY-LOGIC REVIEW (LLM, quote-anchored)
        # ``semantic_review`` may be passed in to reuse a review of identical text.
        if semantic_review is None:
            semantic_review = self._run_semantic_review(script, story_bible, model)
        if (semantic_review or {}).get("status") == "ERROR":
            evidence_issues.append({
                "segment_id": None,
                "excerpt": "",
                "rule": "SEMANTIC_REVIEW_FAILED",
                "severity": "CRITICAL",
                "recommended_action": "Chạy lại QC (Auto-Repair) khi model AI đủ mạnh khả dụng trở lại (thường do hết quota ngày); không duyệt kịch bản khi chưa kiểm tra logic.",
                "message": f"Không chạy được QC logic cốt truyện: {semantic_review.get('error')}",
            })
            logic_issues.append(f"[SEMANTIC_REVIEW_FAILED] Không chạy được QC logic cốt truyện: {semantic_review.get('error')}")
        for issue in (semantic_review or {}).get("issues", []):
            evidence_issues.append(dict(issue))
            logic_issues.append(f"[{issue.get('segment_id')}] {issue.get('rule')}: {issue.get('message')}")
            revision_requests.append(f"Fix {issue.get('rule')} in segment {issue.get('segment_id')}: {issue.get('recommended_action')}")

        critical_rule_set = {
            "TIMELINE_FACT_CONTRADICTION",
            "RELATIONSHIP_TIMELINE_CONTRADICTION",
            "CAUSAL_GAP",
            "CHARACTER_KNOWLEDGE_CONTRADICTION",
            "EVIDENCE_DOES_NOT_PROVE_CLAIM",
            "REVEAL_UNDERJUSTIFIED",
            "SCRIPT_FACT_DRIFT",
            "FINAL_SCRIPT_TOPIC_DRIFT",
            "INTERNAL_TEMPLATE_LEAKAGE",
            "PREMATURE_SIGNOFF",
            "DUPLICATE_SIGNOFF",
            "CONTENT_AFTER_SIGNOFF",
            "REPEATED_NARRATIVE_BLOCK",
            "MALFORMED_VIETNAMESE_PROSE",
            "STRUCTURED_STORY_DATA_LEAKAGE",
            "UNSUPPORTED_PATERNITY_CLAIM",
            "LEGAL_CLAIM_SAFETY",
            "SEMANTIC_REVIEW_FAILED",
            "GENERIC_PHILOSOPHICAL_HOOK",
            "OBJECT_CONTINUITY_CONTRADICTION",
            "HOOK_TIMELINE_CONTRADICTION",
            "PROP_LOCATION_CONTRADICTION",
        }
        hard_fail_rules = {
            "FINAL_SCRIPT_TOPIC_DRIFT",
            "INTERNAL_TEMPLATE_LEAKAGE",
            "RELATIONSHIP_TIMELINE_CONTRADICTION",
            "TIMELINE_FACT_CONTRADICTION",
            "PREMATURE_SIGNOFF",
            "DUPLICATE_SIGNOFF",
            "CONTENT_AFTER_SIGNOFF",
            "REPEATED_NARRATIVE_BLOCK",
            "MALFORMED_VIETNAMESE_PROSE",
            "STRUCTURED_STORY_DATA_LEAKAGE",
            "UNSUPPORTED_PATERNITY_CLAIM",
            "LEGAL_CLAIM_SAFETY",
            "HOOK_TIMELINE_CONTRADICTION",
            "PROP_LOCATION_CONTRADICTION",
        }

        # TIERED VERDICT. An LLM judge always finds something in 90 segments, so
        # "zero findings" is unreachable and repair rounds that chase taste-level
        # findings rewrite fragments and create new defects. Only objective defects
        # block; judgement calls (POV nuance, ordering, style) become warnings that
        # are shown to the user and never trigger automatic rewrites.
        objective_rules = {
            "INFEASIBLE_EVIDENCE", "CONCLUSION_BEFORE_PROOF", "LEGAL_OR_MEDICAL_UNREALISTIC",
            "GARBLED_VIETNAMESE", "UNRESOLVED_SETUP", "SEMANTIC_REVIEW_PENDING",
            "POV_KNOWLEDGE_VIOLATION", "TIMELINE_ORDER_ERROR", "REPEATED_DISCOVERY",
            "REPEATED_SCENE_DIALOGUE", "UNRESOLVED_CORE_PROP", "PROP_LOCATION_CONTRADICTION",
            "HOOK_TIMELINE_CONTRADICTION", "OBJECT_CONTINUITY_CONTRADICTION", "ACTION_SEQUENCE_INVERSION",
            "KNOWLEDGE_STATE_REGRESSION", "CHARACTER_IDENTITY_CONTRADICTION", "TOPIC_TRUTH_DRIFT",
            "REVEAL_LEAKED_EARLY", "UNMOTIVATED_DISCLOSURE",
        }
        from apps.script_factory.narrative_rules import JUDGEMENT_RULES as judgement_rules, is_blocking_logic_issue

        def _blocks(issue: Dict[str, Any]) -> bool:
            rule = str(issue.get("rule") or issue.get("type") or "").strip().upper()
            if rule in hard_fail_rules:
                return True
            if rule in judgement_rules:
                return False
            if issue.get("severity") == "WARNING" and rule not in objective_rules:
                return False
            if rule in objective_rules or is_blocking_logic_issue({"rule": rule}):
                return True
            return issue.get("severity") == "CRITICAL" and rule not in judgement_rules

        warnings = [dict(iss, blocking=False) for iss in evidence_issues if not _blocks(iss)]
        evidence_issues = [iss for iss in evidence_issues if _blocks(iss)]
        for adv in (semantic_review or {}).get("advisories", []):
            if not isinstance(adv, dict):
                continue
            if _blocks(adv):
                evidence_issues.append(dict(adv, severity="CRITICAL", blocking=True))
            else:
                warnings.append(dict(adv, severity="WARNING", blocking=False))

        has_critical_failure = (
            any(
                c.get("type") in [
                    "TIMELINE_CONFLICT",
                    "MONEY_CONFLICT",
                    "RELATIONSHIP_CONFLICT",
                    "BLOCKED_PREMATURE_REVEAL",
                    "HOOK_FACT_CONTRADICTION",
                    "HOOK_TIMELINE_CONTRADICTION",
                    "PROP_LOCATION_CONTRADICTION",
                    "CHARACTER_FACT_VIOLATION",
                    "UNGROUNDED_CHARACTER_HALLUCINATION",
                    "CAUSAL_GAP",
                    "CHARACTER_KNOWLEDGE_CONTRADICTION",
                    "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    "INTERNAL_EPISODE_ID_SPOKEN",
                    "FINAL_SCRIPT_TOPIC_DRIFT",
                    "INTERNAL_TEMPLATE_LEAKAGE",
                    "RELATIONSHIP_TIMELINE_CONTRADICTION",
                    "TIMELINE_FACT_CONTRADICTION",
                    "TIMELINE_ORDER_ERROR",
                    "OBJECT_CONTINUITY_CONTRADICTION",
                    "REVEAL_UNDERJUSTIFIED",
                    "SCRIPT_FACT_DRIFT",
                ]
                for c in fact_conflicts
            )
            or any(iss.get("severity") == "CRITICAL" or iss.get("rule") in critical_rule_set or _blocks(iss) for iss in evidence_issues)
        )
        has_hard_fail = any(iss.get("rule") in hard_fail_rules for iss in evidence_issues)
        has_issues = bool(fact_conflicts or logic_issues or repetition_issues or evidence_issues)

        if has_hard_fail:
            status = "FAIL"
        elif has_critical_failure or evidence_issues or fact_conflicts:
            status = "NEEDS_REVISION"
        else:
            # Remaining findings (if any) are in ``warnings``: visible, non-blocking.
            status = "PASS"

        melodrama_v2_score = max(0.0, 100.0 - len(cliche_hits) * 15.0 - len(severe_v2_hits) * 20.0)
        has_template_leak = any(iss.get("rule") in ("INTERNAL_TEMPLATE_LEAKAGE", "STORY_BIBLE_LEAKAGE", "INTERNAL_EPISODE_ID_SPOKEN", "FAKE_SERIAL_BREAK") for iss in evidence_issues)
        scores = {
            "hook": 95.0 if has_hook and not any(iss.get("rule") in ("GENERIC_HOOK_OPENING", "HOOK_FACT_CONTRADICTION", "HOOK_TOO_SLOW") for iss in evidence_issues) else 60.0,
            "mystery": 92.0 if not any(iss.get("rule") in ("BLOCKED_PREMATURE_REVEAL", "EVIDENCE_DOES_NOT_PROVE_CLAIM") for iss in evidence_issues) else 50.0,
            "logic": 40.0 if has_critical_failure else (90.0 if not logic_issues and not any(iss.get("rule") in ("STORY_BIBLE_LEAKAGE", "INTERNAL_TEMPLATE_LEAKAGE", "CHARACTER_FACT_VIOLATION", "UNGROUNDED_CHARACTER_HALLUCINATION", "CAUSAL_GAP", "CHARACTER_KNOWLEDGE_CONTRADICTION", "EVIDENCE_DOES_NOT_PROVE_CLAIM", "FINAL_SCRIPT_TOPIC_DRIFT") for iss in evidence_issues) else 50.0),
            "twist": 96.0 if has_reveal and not any(iss.get("rule") in ("CAUSAL_GAP", "REVEAL_UNDERJUSTIFIED") for iss in evidence_issues) else 60.0,
            "emotion": 93.0 if not any(iss.get("rule") in ("MELODRAMATIC_CLICHE_DENSITY", "MELODRAMA_DENSITY_V2") for iss in evidence_issues) else 68.0,
            "novelty": 94.0 if not repetition_issues else 68.0,
            "tts_readability": 40.0 if (has_hard_fail or has_template_leak) else 98.0,
            "melodrama_density_v2": melodrama_v2_score,
            "topic_adherence": script_topic_score,
        }

        from apps.script_factory.semantic_review import script_content_hash
        report = QCReport(
            episode_id=script.episode_id,
            status=status,
            scores=scores,
            fact_conflicts=fact_conflicts,
            logic_issues=logic_issues,
            repetition_issues=repetition_issues,
            revision_requests=revision_requests,
            evidence_issues=evidence_issues,
            warnings=warnings,
            checked_at=time.time(),
            qc_version=SCRIPT_QC_VERSION,
            semantic_review=semantic_review,
            script_content_hash=script_content_hash(script),
        )

        semantic_state = (semantic_review or {}).get("status")
        logger.info(
            f"[ScriptQC] {script.episode_id}: {status} — {len(evidence_issues)} lỗi"
            + (f" ({', '.join(sorted({str(i.get('rule')) for i in evidence_issues})[:8])})" if evidence_issues else "")
            + f"; QC logic: {semantic_state}"
            + (f" bằng {semantic_review.get('model')}" if semantic_review and semantic_review.get('model') else "")
        )
        self.save_qc_report(report)
        return report

    def _run_semantic_review(
        self, script: FullScript, story_bible: StoryBible, model: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Runs the LLM logic review when the provider supports JSON completion."""
        complete_json = getattr(self.provider, "complete_json", None)
        if not callable(complete_json) or not script.segments:
            return {"status": "NOT_RUN", "issues": [], "advisories": []}
        from apps.script_factory.semantic_review import review_script_logic
        try:
            review = review_script_logic(
                script, story_bible,
                lambda system, prompt: complete_json(system, prompt, model=model),
                _require_grounding=bool(getattr(self.provider, 'requires_grounded_review', False)),
            )
        except Exception as exc:
            logger.warning(f"[ScriptQC] Semantic review failed for {script.episode_id}: {exc}")
            return {"status": "ERROR", "error": str(exc), "issues": [], "advisories": []}
        review["model"] = getattr(self.provider, "last_used_model", None) or model
        try:
            in_tok, out_tok = review.get("tokens", [0, 0])
            self.cost_ctrl.record_operation(
                operation="semantic_review", episode_id=script.episode_id,
                provider=getattr(self.provider, "provider_name", "unknown"), model=review["model"] or "default",
                status="SUCCESS", latency_sec=0.0, input_tokens=in_tok, output_tokens=out_tok,
            )
        except Exception:
            pass
        return review

    def save_qc_report(self, report: QCReport) -> Path:
        """Saves QC report to episodes/EPXXX/qc_report.json."""
        ep_dir = self.episodes_root / report.episode_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        file_path = ep_dir / "qc_report.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"[ScriptQC] Saved QC report for {report.episode_id} (Status: {report.status})")
        return file_path

    def load_qc_report(self, episode_id: str) -> Optional[QCReport]:
        """Loads QC report for an episode."""
        file_path = self.episodes_root / episode_id / "qc_report.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return QCReport.from_dict(data)


def apply_targeted_repairs(
    script: FullScript,
    story_bible: StoryBible,
    qc_report: QCReport,
    preserve_segment_ids: Optional[set] = None,
    allow_prose_templates: bool = True,
) -> FullScript:
    """Applies targeted repairs to specific segments flagged by QC without regenerating the entire script.

    ``preserve_segment_ids`` are segments an AI rewrite just fixed; the template
    replacements below must not overwrite them with generic sentences.
    """
    preserved = set(preserve_segment_ids or ())
    seg_map = {s.id: s for s in script.segments}
    protag = (
        story_bible.protagonist.get("name", "nhân vật chính")
        if isinstance(story_bible.protagonist, dict)
        else str(story_bible.protagonist or "nhân vật chính")
    )
    issue_rules = {
        str(issue.get("rule", ""))
        for issue in qc_report.evidence_issues
        if isinstance(issue, dict)
    }

    # A long script is generated in two calls. If the second call restarts the
    # investigation, keep the original occurrence and cut only the later
    # duplicate bridge. The first REVEAL after that bridge is preserved.
    if "REPEATED_NARRATIVE_BLOCK" in issue_rules:
        repeated = find_repeated_narrative_block(script.segments)
        if repeated and any(
            s.id in preserved for s in script.segments[repeated["second_start"]:repeated["second_end"]]
        ):
            # The AI just rewrote the retold block into new events; cutting it
            # would delete that work. The next QC pass re-checks it.
            repeated = None
        if repeated:
            # If the repeated block is a full story restart from the beginning:
            if repeated.get("first_start", 0) <= 4 and repeated.get("second_start", 0) >= 40:
                second_half = script.segments[repeated["second_start"]:]
                prefix = script.segments[:repeated["second_start"]]
                if any(s.delivery_profile == "ENDING" or "hẹn gặp lại" in s.text.lower() for s in second_half) and len(second_half) >= 45:
                    logger.info(f"[ScriptQC] Phát hiện tập khởi động lại; giữ nửa sau hoàn chỉnh ({len(second_half)} đoạn).")
                    script.segments = second_half
                    repeated = None
                elif any(s.delivery_profile == "REVEAL" for s in prefix) and len(prefix) >= 45:
                    logger.info(f"[ScriptQC] Phát hiện tập khởi động lại; giữ nửa đầu ({len(prefix)} đoạn).")
                    script.segments = prefix
                    repeated = None
                if repeated is None:
                    for index, segment in enumerate(script.segments, start=1):
                        segment.id = f"{index:03d}"
                    seg_map = {s.id: s for s in script.segments}
            if repeated:
                cut_start = int(repeated["second_start"])
                reset_pattern = re.compile(
                    r"\b(?:những ngày|vài ngày|một thời gian|thời gian)\s+sau\s+đó\b",
                    re.IGNORECASE,
                )
                if cut_start > 0 and reset_pattern.search(script.segments[cut_start - 1].text):
                    cut_start -= 1
                cut_end = int(repeated["second_end"])
                for idx in range(cut_end, min(len(script.segments), cut_end + 9)):
                    if script.segments[idx].delivery_profile == "REVEAL":
                        cut_end = idx
                        break
                if cut_end > cut_start:
                    del script.segments[cut_start:cut_end]
                    for index, segment in enumerate(script.segments, start=1):
                        segment.id = f"{index:03d}"
                    seg_map = {s.id: s for s in script.segments}

    # Repair a slow/generic hook using facts that already exist in the Story
    # Bible. This changes presentation only and never invents a new clue.
    if allow_prose_templates and "HOOK_TOO_SLOW" in issue_rules and script.segments and script.segments[0].id not in preserved:
        clue_source = story_bible.structured_clues or story_bible.clues or []
        first_clue = ""
        if clue_source:
            raw_clue = clue_source[0]
            if isinstance(raw_clue, dict):
                first_clue = str(
                    raw_clue.get("clue")
                    or raw_clue.get("description")
                    or raw_clue.get("text")
                    or ""
                ).strip()
            else:
                first_clue = str(raw_clue).strip()
        mystery = str(story_bible.mystery_question or "Điều gì thực sự đang bị che giấu?").strip()
        concrete_detail = first_clue or str(story_bible.secret or "một chi tiết không khớp").strip()
        script.segments[0].text = (
            f"Trong lá thư gửi về chương trình, {protag} kể về một dấu hiệu bất thường: "
            f"{concrete_detail.rstrip('.')}. {mystery}"
        )
        script.segments[0].delivery_profile = "HOOK"
        script.segments[0].audience_address = False

    # Legacy repairs remain available to offline callers. Production prose is
    # rewritten by AI and must not mutate its approved Story Bible.
    if allow_prose_templates:
        # 1. Clean Story Bible Leakage & Internal Templates
        leakage_guard = StoryBibleLeakageGuard()
        for s in script.segments:
            s.text = leakage_guard.clean_text_from_leakage(s.text, protagonist_name=protag)

        # 2. Repair Fact & Logic Conflicts (Hook, Character, Hallucination, Causal Gap, Knowledge, Evidence, Episode ID)
        from apps.script_factory.story_qc import StoryQCEngine
        StoryQCEngine().repair_story_bible(story_bible)

        for conflict in qc_report.fact_conflicts:
            ctype = conflict.get("type")
            sid = conflict.get("segment_id")
            if sid in preserved:
                continue
            if ctype == "HOOK_FACT_CONTRADICTION" and sid in seg_map:
                seg = seg_map[sid]
                seg.text = (
                    f"Trong bức thư gửi về chương trình, {protag} chia sẻ về những nghi ngờ ban đầu xoay quanh "
                    f"biến cố của gia đình, đặt ra câu hỏi lớn về sự thật bị che giấu."
                )
            elif ctype == "CHARACTER_FACT_VIOLATION" and sid in seg_map:
                seg = seg_map[sid]
                for wrong_term in ["hai người con trai", "hai con trai", "2 người con trai", "cả hai cậu con trai", "hai anh em trai"]:
                    seg.text = re.sub(wrong_term, "hai chị em trong gia đình", seg.text, flags=re.IGNORECASE)
            elif ctype == "UNGROUNDED_CHARACTER_HALLUCINATION" and sid in seg_map:
                seg = seg_map[sid]
                found_char = conflict.get("found", "")
                if found_char:
                    seg.text = seg.text.replace(found_char, "người quen trong câu chuyện")
            elif ctype == "CAUSAL_GAP" and sid in seg_map:
                seg = seg_map[sid]
                if seg.delivery_profile != "ENDING":
                    causal_desc = ""
                    for c in (story_bible.causal_chains or []):
                        if isinstance(c, dict) and c.get("motivation"):
                            causal_desc = c.get("motivation")
                            break
                    if causal_desc:
                        seg.text = (
                            f"Trong bối cảnh thực tế lúc đó, {causal_desc.lower().rstrip('.')} nên việc giữ im lặng và giải quyết "
                            f"trong âm thầm là phương án bất khả kháng duy nhất của những người trong cuộc."
                        )
                    else:
                        seg.text = (
                            f"Trước những áp lực và ràng buộc thực tế tại thời điểm đó, việc giữ im lặng và giải quyết vấn đề "
                            f"trong âm thầm là phương án bất khả kháng duy nhất để hạn chế những tổn thương không đáng có."
                        )
            elif ctype == "CHARACTER_KNOWLEDGE_CONTRADICTION" and sid in seg_map:
                seg = seg_map[sid]
                seg.text = re.sub(
                    r"(?:không\s+thể\s+sẻ\s+chia\s+cùng\s+ai(?:\s*,?\s*kể\s+cả\s+(?:với\s+)?người\s+vợ(?:\s+gối\s+chăn)?)?|kể\s+cả\s+(?:với\s+)?người\s+vợ(?:\s+gối\s+chăn)?|không\s+một\s+ai\s+(?:hay\s+)?biết|không\s+ai\s+trên\s+đời\s+biết|chỉ\s+một\s+mình\s+[^\s,]+\s+biết)",
                    "chỉ được giữ kín giữa những người trong cuộc suốt nhiều năm",
                    seg.text,
                    flags=re.IGNORECASE,
                )
            elif ctype == "EVIDENCE_DOES_NOT_PROVE_CLAIM" and sid in seg_map:
                seg = seg_map[sid]
                seg.text = (
                    f"Chi tiết vật chứng này bước đầu cho thấy mối liên hệ đặc biệt trong quá khứ, "
                    f"nhưng chưa đủ để kết luận ngay sự thật mà đặt ra câu hỏi cần tiếp tục đối chiếu hồ sơ gốc."
                )

        # 2b. Repair Spoken Internal Episode IDs & Fake Serial Breaks across all segments
        internal_code_pat = re.compile(
            r"\b(?:mã\s+số\s+)?(EP_?[A-Z0-9_]*\d+|IDEA_\d+|PROJ_[A-Z0-9_]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b",
            re.IGNORECASE,
        )
        spoken_ep_num_pat = re.compile(
            r"\btập\s+(?:số\s+|phim\s+|thứ\s+)?("
            r"\d+"
            r"|(?:một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn)(?:\s+(?:một|mốt|hai|ba|bốn|tư|năm|lăm|sáu|bảy|tám|chín|mười|mươi|trăm|nghìn|ngàn|linh|lẻ|không))*"
            r")\s*(?:của\s+(?:series\s+|chương\s+trình\s+)?)?",
            re.IGNORECASE,
        )
        serial_break_pat = re.compile(
            r"(?:hãy\s+đón\s+xem\s+phần\s+tiếp\s+theo|đón\s+xem\s+phần\s+sau|ở\s+phần\s+tiếp\s+theo|phần\s+tiếp\s+theo|ở\s+phần\s+sau|hãy\s+đón\s+xem|chúng\s+ta\s+sẽ\s+quay\s+lại\s+sau|quay\s+lại\s+sau\s+ít\s+phút)",
            re.IGNORECASE,
        )
        for idx, s in enumerate(script.segments):
            if internal_code_pat.search(s.text) or spoken_ep_num_pat.search(s.text):
                if "chào mừng" in s.text.lower() or "sau cánh cửa" in s.text.lower():
                    s.text = "Chào mừng quý vị và các bạn đến với Sau Cánh Cửa."
                else:
                    s.text = internal_code_pat.sub("", s.text)
                    s.text = spoken_ep_num_pat.sub("", s.text)
                    s.text = re.sub(r"\s{2,}", " ", s.text).strip()

            if serial_break_pat.search(s.text):
                if idx >= len(script.segments) - 2:
                    s.text = serial_break_pat.sub("", s.text)
                    s.text = re.sub(r"\s{2,}", " ", s.text).strip()
                else:
                    s.text = serial_break_pat.sub("tiếp nối mạch câu chuyện", s.text)
            if re.search(r"\btập\s+tiếp\s+theo\b", s.text, re.IGNORECASE):
                if idx >= len(script.segments) - 2:
                    # Ending segment: standard sign-off
                    s.text = re.sub(r"(?:hẹn\s+gặp\s+lại\s+quý\s+vị\s+trong\s+)?tập\s+tiếp\s+theo(?:\s+của\s+sau\s+cánh\s+cửa)?\.?", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", s.text, flags=re.IGNORECASE)
                    s.text = re.sub(r"\btập\s+tiếp\s+theo\b", "", s.text, flags=re.IGNORECASE)
                else:
                    s.text = re.sub(r"\btập\s+tiếp\s+theo\b", "diễn biến tiếp theo của câu chuyện", s.text, flags=re.IGNORECASE)
                s.text = re.sub(r"\s{2,}", " ", s.text).strip()

        # 3. Repair Melodramatic Cliches V2 -> Conversational MC Minh Phrasing (Show, Don't Label)
        cliche_replacements = {
            "bí mật động trời": "bí mật được giấu kín nhiều năm",
            "sự thật động trời": "sự thật bất ngờ",
            "như một đòn chí mạng": "khiến mọi người lặng đi",
            "đòn chí mạng": "cú sốc lớn",
            "sự thật kinh hoàng": "sự thật nặng nề",
            "cuộc gặp gỡ định mệnh": "cuộc gặp gỡ năm ấy",
            "đau đớn đến tận cùng": "xót xa nghẹn lời",
            "vĩ đại ẩn giấu": "lặng lẽ",
            "mê cung không lối thoát": "những câu hỏi chưa có lời giải",
            "nấc nghẹn ngào đến xé lòng": "khóc lặng lẽ",
            "nghẹn ngào đến xé lòng": "rưng rưng xúc động",
            "chấn động toàn bộ": "làm xáo trộn",
            "cuộc chiến ngầm khốc liệt": "những rạn nứt âm thầm",
            "không tiếng súng": "lặng lẽ",
            "đập tan mọi nghi kỵ": "tháo gỡ những hoài nghi",
            "bóc tách sự thật": "lần mở từng mảnh ghép sự thật",
            "sét đánh ngang tai": "bàng hoàng sửng sốt",
            "bão táp phong ba": "những biến cố dồn dập",
            "chết lặng trong đau đớn": "lặng người đi vì xót xa",
            "tan nát cõi lòng": "trĩu nặng nỗi buồn",
            "cơn địa chấn": "cú sốc lớn",
            "vạch trần bộ mặt thật": "nhìn rõ câu chuyện phía sau",
            "bản án lương tâm": "nỗi day dứt trong lòng",
            "bi kịch đẫm nước mắt": "câu chuyện nhiều nỗi niềm",
            "sự thật rỉ máu": "sự thật đau lòng",
            "chiếc lồng kính ngột ngạt": "không gian tĩnh lặng",
            "bóng ma vô hình": "nỗi ám ảnh vô hình",
            "mặt nạ hoàn hảo": "vẻ ngoài bình thường",
            "bức tường phòng thủ cuối cùng sụp đổ": "cô không còn né tránh câu hỏi",
            "mảnh vỡ vụn": "những điều đã rạn nứt",
            "đẩy mọi thứ xuống vực sâu": "khiến mọi chuyện trở nên tệ hơn",
            "không gian xung quanh đặc quánh lại": "căn phòng im hẳn",
            "như một nhát dao đâm thẳng": "khiến anh đau lòng",
            "đứng lặng như tượng đá": "đứng lặng, chưa biết nói gì",
            "những giọt nước mắt muộn màng": "cô bật khóc",
            "tiếng khóc xé lòng": "tiếng khóc nghẹn lại",
            "vết thương sâu hoắm": "tổn thương khó nguôi",
        }
        for s in script.segments:
            for bad_phrase, natural_phrase in cliche_replacements.items():
                if bad_phrase in s.text.lower():
                    s.text = re.sub(re.escape(bad_phrase), natural_phrase, s.text, flags=re.IGNORECASE)

        # 4. Repair Unsafe Legal Claims -> Grounded Social/Familial Phrasing
        legal_replacements = [
            (r"tòa\s+án\s+tuyên\s+bố\s+vô\s+hiệu\s+ngay\s+lập\s+tức", "dấy lên nhiều tranh cãi về tính xác thực"),
            (r"công\s+an\s+bắt\s+giữ\s+khẩn\s+cấp\s+ngay\s+tại", "cơ quan chức năng mời làm việc để xác minh tại"),
            (r"di\s+chúc\s+miệng\s+mặc\s+nhiên\s+vô\s+giá\s+trị", "lời dặn dò lúc lâm chung khiến gia đình bối rối"),
            (r"tước\s+quyền\s+thừa\s+kế\s+ngay\s+tức\s+khắc", "làm thay đổi hoàn toàn dự định phân chia tài sản"),
            (r"khẳng\s+định\s+quyền\s+sở\s+hữu\s+hợp\s+pháp\s+tuyệt\s+đối", "là manh mối quan trọng để đối chiếu nguồn gốc tài sản"),
            (r"tờ\s+giấy\s+này\s+chứng\s+minh\s+hoàn\s+toàn\s+quyền\s+sở\s+hữu", "tờ giấy này hé lộ nguồn gốc thực sự của tài sản"),
            (r"vô\s+hiệu\s+hóa\s+hoàn\s+toàn\s+về\s+mặt\s+pháp\s+lý\s+ngay\s+tại\s+chỗ", "đặt ra dấu hỏi lớn về giá trị thực sự của văn bản"),
        ]
        for s in script.segments:
            for pat, repl in legal_replacements:
                s.text = re.sub(pat, repl, s.text, flags=re.IGNORECASE)

        # 5. Repair Ending Proportion & Semantic Repetition if overlong or repetitive
        has_ending_rep = any(iss.get("rule") == "ENDING_SEMANTIC_REPETITION" for iss in qc_report.evidence_issues)
        if has_ending_rep and len(script.segments) >= 5:
            tail_len = max(5, int(len(script.segments) * 0.15))
            tail_start = max(0, len(script.segments) - tail_len)
            moralizing_phrases = [
                r"bài\s+học", r"thấu\s+hiểu", r"bao\s+dung", r"tha\s+thứ", r"chữa\s+lành",
                r"mặt\s+nạ", r"đằng\s+sau\s+cánh\s+cửa", r"giá\s+trị\s+của", r"cuộc\s+sống\s+dạy\s+chúng\s+ta",
                r"lời\s+cảnh\s+tỉnh", r"nhìn\s+lại\s+chính\s+mình", r"tình\s+thân",
            ]
            reflection_kept = False
            for idx in range(tail_start, len(script.segments) - 1):
                seg = script.segments[idx]
                if seg.delivery_profile in ("HOOK", "REVEAL"):
                    continue
                hits = sum(1 for p in moralizing_phrases if re.search(p, seg.text, re.IGNORECASE))
                if hits >= 2 or (hits >= 1 and seg.delivery_profile == "COMMENT"):
                    if not reflection_kept:
                        seg.text = story_bible.reflection_theme or "Đằng sau cánh cửa mỗi gia đình, sự thấu hiểu luôn bắt đầu từ lòng bao dung."
                        seg.delivery_profile = "COMMENT"
                        reflection_kept = True
                    else:
                        seg.text = "Mọi biến cố rồi cũng dần khép lại trong sự bình yên của căn nhà nhỏ."
                        seg.delivery_profile = "NORMAL"
                        seg.audience_address = False

    if len(script.segments) >= 20:
        closing_indices = [
            i for i, s in enumerate(script.segments)
            if s.delivery_profile == "ENDING" or (i >= int(len(script.segments) * 0.88) and s.delivery_profile in ("ENDING", "COMMENT"))
        ]
        max_allowed = max(2, int(len(script.segments) * 0.08))
        if len(closing_indices) > max_allowed:
            for idx in closing_indices[:-max_allowed]:
                script.segments[idx].delivery_profile = "NORMAL"
                script.segments[idx].audience_address = False

    # Normalize the broadcast close deterministically. A provider sometimes
    # emits a thank-you to the letter sender as ENDING, or repeats the canonical
    # station sign-off in the penultimate segment. Neither requires rewriting
    # the narrative body.
    signoff_pattern = re.compile(
        r"(?:cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|"
        r"xin\s+chào\s+và\s+hẹn\s+gặp\s+lại|"
        r"tôi\s+là\s+minh[^.]{0,80}hẹn\s+gặp\s+lại)",
        re.IGNORECASE,
    )
    if script.segments:
        normalized_segments = []
        for segment in script.segments[:-1]:
            if signoff_pattern.search(segment.text):
                continue
            if segment.delivery_profile == "ENDING":
                segment.delivery_profile = "COMMENT"
            normalized_segments.append(segment)

        final_segment = script.segments[-1]
        if not signoff_pattern.search(final_segment.text):
            penultimate = script.segments[-1]
            if penultimate.delivery_profile == "ENDING":
                penultimate.delivery_profile = "COMMENT"
            normalized_segments.append(penultimate)
            final_segment = ScriptSegment(
                id="",
                speaker=script.host.get("id", "MINH") if isinstance(script.host, dict) else "MINH",
                text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
                delivery_profile="ENDING",
                importance="normal",
                audience_address=False,
                speed=0.965,
                pause_before=0.05,
                pause_after=0.25,
            )
        final_segment.delivery_profile = "ENDING"
        final_segment.audience_address = False
        normalized_segments.append(final_segment)
        script.segments = normalized_segments
        for index, segment in enumerate(script.segments, start=1):
            segment.id = f"{index:03d}"

    # 6. Repair Reveal Audience Restraint & Audience Frequency
    for s in script.segments:
        if (s.delivery_profile == "REVEAL" or s.importance == "critical") and s.audience_address:
            s.audience_address = False

    aud_segs = [s for s in script.segments if s.audience_address and s.delivery_profile != "REVEAL"]
    if len(aud_segs) > 6:
        for s in aud_segs[6:]:
            s.audience_address = False
            if s.delivery_profile == "COMMENT":
                s.delivery_profile = "NORMAL"
    elif len(aud_segs) < 3 and len(script.segments) >= 6:
        candidates = [s for s in script.segments[1:-1] if s.delivery_profile not in ("REVEAL", "HOOK", "ENDING") and not s.audience_address]
        for s in candidates[: 3 - len(aud_segs)]:
            s.audience_address = True
            s.delivery_profile = "COMMENT"

    # 7. Deduplicate adjacent identical or verbatim substring segments
    cleaned_segments = []
    for s in script.segments:
        if cleaned_segments:
            prev = cleaned_segments[-1]
            prev_t = prev.text.strip().lower()
            curr_t = s.text.strip().lower()
            if prev_t == curr_t or (len(curr_t) > 30 and curr_t in prev_t):
                continue
            elif len(prev_t) > 30 and prev_t in curr_t:
                cleaned_segments[-1] = s
                continue
        cleaned_segments.append(s)
    script.segments = cleaned_segments

    from apps.script_factory.script_craft import trim_overlong_closing
    trimmed = trim_overlong_closing(script.segments)
    if len(trimmed) != len(script.segments):
        script.segments = trimmed
        for index, segment in enumerate(script.segments, start=1):
            segment.id = f"{index:03d}"

    script.total_words = sum(len(s.text.split()) for s in script.segments)
    script.updated_at = time.time()
    return script
