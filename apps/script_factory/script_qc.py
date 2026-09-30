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
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.spoiler_timing_guard import SpoilerTimingGuard

logger = logging.getLogger("VieNeu.ScriptQC")

SERIES_BIBLE_PATH = Path("script_factory/series_bible.json")
STORY_FORMULA_PATH = Path("script_factory/story_formula_v1.json")


class ScriptQCEngine:
    """Audits scripts against Story Bible, Locked Facts, and narrative standards."""

    def __init__(
        self,
        provider: ScriptAIProvider,
        cost_controller: CostController,
        episodes_root: Optional[Path] = None,
    ):
        self.provider = provider
        self.cost_ctrl = cost_controller
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
        from apps.script_factory.providers.mock_provider import MockScriptAIProvider
        engine = cls(provider=MockScriptAIProvider(), cost_controller=CostController())
        return engine.run_qc(script=script, story_bible=story_bible)

    def run_qc(
        self,
        script: FullScript,
        story_bible: StoryBible,
        past_scripts: Optional[List[FullScript]] = None,
        model: Optional[str] = None,
        release_map: Optional[InformationReleaseMap] = None,
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
        rel_map = release_map or build_information_release_map(story_bible)
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
                            if str(num_val) not in calendar_years and str(num_val) not in all_text:
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
                elif "money" in fact.field.lower() or (("vnd" in val_lower or "triệu" in val_lower or "đồng" in val_lower) and len(val.split()) <= 5):
                    # Money conflict check
                    clean_money = re.sub(r"[^\d]", "", val)
                    clean_text_digits = re.sub(r"[^\d]", " ", all_text)
                    if clean_money and clean_money not in clean_text_digits and val_lower not in all_text.lower():
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
                    parts = [p.strip().lower() for p in re.split(r"[;,]", val) if p.strip()]
                    found = any(p in all_text.lower() for p in parts) if parts else (val_lower in all_text.lower())
                    if not found and len(val) > 25:
                        key_words = [w for w in re.findall(r"\b\w{3,}\b", val_lower) if w not in ["người", "những", "trong", "được", "không", "thực", "hiện"]]
                        match_count = sum(1 for kw in key_words if kw in all_text.lower())
                        found = (match_count / max(1, len(key_words))) >= 0.4
                    if not found:
                        fact_conflicts.append({
                            "fact_id": fact.fact_id,
                            "field": fact.field,
                            "expected": fact.value,
                            "type": "RELATIONSHIP_CONFLICT" if "cậu" in val_lower or "chú" in val_lower or "bác" in val_lower or "relat" in fact.field.lower() else "FACT_CONFLICT",
                            "description": f"Fact conflict: Expected '{fact.value}' for {fact.field} missing or contradicted."
                        })
                        revision_requests.append(f"Correct relationship/fact conflict: clarify that {fact.field} is {fact.value}.")

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
                "tha thứ", "bao dung", "chữa lành", "sau cánh cửa", "đằng sau cánh cửa",
                "mặt nạ", "buông bỏ", "bài học", "nhận ra rằng", "tình yêu thương",
                "tình thân", "sự thật dù", "mái ấm", "lòng người", "chiêm nghiệm",
                "hóa giải", "vết thương", "im lặng", "khoan dung",
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

        # 11. LEGAL CLAIM SAFETY AUDIT
        unsafe_legal_patterns = [
            (r"tòa\s+án\s+tuyên\s+bố\s+vô\s+hiệu\s+ngay\s+lập\s+tức", "tuyên bố pháp lý tức thời của tòa án"),
            (r"công\s+an\s+bắt\s+giữ\s+khẩn\s+cấp\s+ngay\s+tại", "thủ tục bắt giữ hình sự khẩn cấp không xác thực"),
            (r"di\s+chúc\s+miệng\s+mặc\s+nhiên\s+vô\s+giá\s+trị", "kết luận luật thừa kế cứng nhắc"),
            (r"tước\s+quyền\s+thừa\s+kế\s+ngay\s+tức\s+khắc", "kết luận tước quyền thừa kế pháp lý"),
            (r"khẳng\s+định\s+quyền\s+sở\s+hữu\s+hợp\s+pháp\s+tuyệt\s+đối", "khẳng định pháp lý tuyệt đối từ giấy tờ cũ"),
            (r"tờ\s+giấy\s+này\s+chứng\s+minh\s+hoàn\s+toàn\s+quyền\s+sở\s+hữu", "khẳng định quyền sở hữu pháp lý tuyệt đối"),
            (r"vô\s+hiệu\s+hóa\s+hoàn\s+toàn\s+về\s+mặt\s+pháp\s+lý\s+ngay\s+tại\s+chỗ", "kết luận pháp lý tại chỗ thiếu căn cứ"),
        ]
        for s in script.segments:
            for pat, desc in unsafe_legal_patterns:
                if re.search(pat, s.text, re.IGNORECASE):
                    evidence_issues.append({
                        "segment_id": s.id,
                        "excerpt": s.text[:100],
                        "rule": "LEGAL_CLAIM_SAFETY",
                        "severity": "HIGH",
                        "recommended_action": "Diễn đạt dưới góc độ tâm lý, tình cảm gia đình hoặc manh mối cần xác minh, tránh phán quyết pháp lý chủ quan.",
                        "message": f"Phân đoạn [{s.id}] đưa ra khẳng định pháp lý thiếu an toàn ({desc})."
                    })
                    logic_issues.append(f"[{s.id}] Unsafe legal claim: {desc}.")
                    revision_requests.append(f"Soften assertive legal claim in segment {s.id} to emotional/social narrative framing.")
                    break

        # 12. INTERNAL EPISODE ID != PUBLIC EPISODE NUMBER AUDIT (INTERNAL_EPISODE_ID_SPOKEN)
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
            target_seg = next((s for s in script.segments if s.delivery_profile == "REVEAL"), script.segments[-1] if script.segments else ScriptSegment(id="001"))
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

        # Compute status
        has_critical_failure = (
            any(
                c.get("type") in [
                    "TIMELINE_CONFLICT",
                    "MONEY_CONFLICT",
                    "RELATIONSHIP_CONFLICT",
                    "BLOCKED_PREMATURE_REVEAL",
                    "HOOK_FACT_CONTRADICTION",
                    "CHARACTER_FACT_VIOLATION",
                    "UNGROUNDED_CHARACTER_HALLUCINATION",
                    "CAUSAL_GAP",
                    "CHARACTER_KNOWLEDGE_CONTRADICTION",
                    "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                    "INTERNAL_EPISODE_ID_SPOKEN",
                    "FINAL_SCRIPT_TOPIC_DRIFT",
                    "INTERNAL_TEMPLATE_LEAKAGE",
                ]
                for c in fact_conflicts
            )
            or any(iss.get("severity") == "CRITICAL" for iss in evidence_issues)
        )
        has_hard_fail = any(iss.get("rule") in ("FINAL_SCRIPT_TOPIC_DRIFT", "INTERNAL_TEMPLATE_LEAKAGE") for iss in evidence_issues)
        has_issues = bool(fact_conflicts or logic_issues or repetition_issues or evidence_issues)

        if has_hard_fail:
            status = "FAIL"
        elif has_critical_failure or len(logic_issues) > 2 or any(iss.get("severity") == "HIGH" for iss in evidence_issues):
            status = "NEEDS_REVISION"
        elif has_issues:
            status = "NEEDS_REVISION"
        else:
            status = "PASS"

        melodrama_v2_score = max(0.0, 100.0 - len(cliche_hits) * 15.0 - len(severe_v2_hits) * 20.0)
        has_template_leak = any(iss.get("rule") in ("INTERNAL_TEMPLATE_LEAKAGE", "STORY_BIBLE_LEAKAGE", "INTERNAL_EPISODE_ID_SPOKEN", "FAKE_SERIAL_BREAK") for iss in evidence_issues)
        scores = {
            "hook": 95.0 if has_hook and not any(iss.get("rule") in ("GENERIC_HOOK_OPENING", "HOOK_FACT_CONTRADICTION") for iss in evidence_issues) else 60.0,
            "mystery": 92.0 if not any(iss.get("rule") in ("BLOCKED_PREMATURE_REVEAL", "EVIDENCE_DOES_NOT_PROVE_CLAIM") for iss in evidence_issues) else 50.0,
            "logic": 90.0 if not logic_issues and not any(iss.get("rule") in ("STORY_BIBLE_LEAKAGE", "INTERNAL_TEMPLATE_LEAKAGE", "CHARACTER_FACT_VIOLATION", "UNGROUNDED_CHARACTER_HALLUCINATION", "CAUSAL_GAP", "CHARACTER_KNOWLEDGE_CONTRADICTION", "EVIDENCE_DOES_NOT_PROVE_CLAIM", "FINAL_SCRIPT_TOPIC_DRIFT") for iss in evidence_issues) else 50.0,
            "twist": 96.0 if has_reveal and not any(iss.get("rule") == "CAUSAL_GAP" for iss in evidence_issues) else 60.0,
            "emotion": 93.0 if not any(iss.get("rule") in ("MELODRAMATIC_CLICHE_DENSITY", "MELODRAMA_DENSITY_V2") for iss in evidence_issues) else 68.0,
            "novelty": 94.0 if not repetition_issues else 68.0,
            "tts_readability": 40.0 if (has_hard_fail or has_template_leak) else 98.0,
            "melodrama_density_v2": melodrama_v2_score,
            "topic_adherence": script_topic_score,
        }

        report = QCReport(
            episode_id=script.episode_id,
            status=status,
            scores=scores,
            fact_conflicts=fact_conflicts,
            logic_issues=logic_issues,
            repetition_issues=repetition_issues,
            revision_requests=revision_requests,
            evidence_issues=evidence_issues,
            checked_at=time.time(),
        )

        self.save_qc_report(report)
        return report

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
) -> FullScript:
    """Applies targeted repairs to specific segments flagged by QC without regenerating the entire script."""
    seg_map = {s.id: s for s in script.segments}
    protag = (
        story_bible.protagonist.get("name", "nhân vật chính")
        if isinstance(story_bible.protagonist, dict)
        else str(story_bible.protagonist or "nhân vật chính")
    )

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
            seg.text = (
                f"Do hồ sơ hành chính thời điểm biến cố bị thất lạc, giấy xác nhận duy nhất còn lại mang tên người đã khuất, "
                f"cùng nguy cơ cú sốc tâm lý đe dọa tính mạng người thân nếu biết tin dữ ngay lúc đó, việc duy trì thỏa thuận "
                f"này là phương án bất khả kháng duy nhất để bảo toàn mái ấm."
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
    if has_ending_rep and len(script.segments) >= 6:
        # Keep narrative resolution concrete, compress redundant moralizing segments in the tail
        tail_start = max(0, len(script.segments) - 10)
        reflection_kept = False
        for idx in range(tail_start, len(script.segments) - 1):
            seg = script.segments[idx]
            if seg.delivery_profile in ("HOOK", "REVEAL"):
                continue
            if not reflection_kept and seg.delivery_profile in ("COMMENT", "NORMAL"):
                seg.text = story_bible.reflection_theme or "Đằng sau cánh cửa mỗi gia đình, sự thấu hiểu luôn bắt đầu từ khoảnh khắc chúng ta dám lắng nghe nhau."
                seg.delivery_profile = "COMMENT"
                reflection_kept = True
            else:
                # Convert redundant moralizing segments into concrete narrative transition details
                seg.delivery_profile = "NORMAL"
                seg.audience_address = False
                seg.text = f"Những tài liệu cũ được {protag} xếp lại gọn gàng vào ngăn tủ gỗ khi buổi chiều dần buông xuống."

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

    script.total_words = sum(len(s.text.split()) for s in script.segments)
    script.updated_at = time.time()
    return script
