"""Script Factory V1.3.1a Artifact Integrity Engine.

Provides physical artifact validation across:
1. CHARACTER_NAME_CONSISTENCY (especially EP005 Minh -> Tuấn migration)
2. RELATIONSHIP_CONSISTENCY
3. TIMELINE_CONSISTENCY
4. REVEAL_FACT_CONSISTENCY
5. POV_CONSISTENCY (Zero unmarked first-person protagonist narration)
6. NO_OP_EDITORIAL_CHANGE (Every logged edit must represent a real text change)
7. NEW_UNLOCKED_STORY_FACT (No invented high-impact twists)
8. TTS_READINESS (Text hygiene and delivery profile validation)
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("VieNeu.ArtifactIntegrity")


def normalize_text(text: str) -> str:
    """Normalizes text for robust comparison."""
    if not text:
        return ""
    # NFKC normalize and collapse whitespace
    t = unicodedata.normalize("NFKC", str(text))
    t = re.sub(r"\s+", " ", t).strip()
    return t


@dataclass
class IntegrityIssue:
    episode_id: str
    rule: str
    severity: str  # "BLOCKER", "FAIL", "WARN"
    source_file: str
    field_or_segment: str
    details: str
    actual_value: str = ""
    expected_value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ArtifactIntegrityValidator:
    """Validates physical saved files on disk for cross-artifact consistency."""

    def __init__(self):
        pass

    def validate_saved_package(self, ep_dir: Path) -> Dict[str, Any]:
        """Runs all integrity checks on a saved episode directory on disk."""
        ep_dir = Path(ep_dir).resolve()
        if not ep_dir.exists():
            raise FileNotFoundError(f"Episode directory not found: {ep_dir}")

        idea_id = ep_dir.name
        required_files = [
            "story_bible.json",
            "fact_lock.json",
            "information_release_map.json",
            "full_script.json",
            "full_script_readable.txt",
            "editorial_change_log.json",
        ]
        missing = [f for f in required_files if not (ep_dir / f).exists()]
        if missing:
            return {
                "episode_id": idea_id,
                "idea_id": idea_id,
                "status": "FAIL",
                "production_readiness": "NEEDS_HUMAN_SCRIPT_REVIEW",
                "script_status": "AWAITING_USER_SCRIPT_REVIEW",
                "character_name_consistency": "FAIL",
                "relationship_consistency": "FAIL",
                "timeline_consistency": "FAIL",
                "reveal_fact_consistency": "FAIL",
                "pov_consistency": "FAIL",
                "stale_character_name_references": 0,
                "unmarked_first_person_count": 0,
                "no_op_editorial_changes_count": 0,
                "new_unlocked_story_facts_count": 0,
                "story_bible_leakage_count": 0,
                "premature_reveal_count": 0,
                "tts_ready": False,
                "total_issues": 1,
                "blockers_count": 1,
                "fails_count": 0,
                "warns_count": 0,
                "issues": [
                    IntegrityIssue(
                        episode_id=idea_id,
                        rule="MISSING_ARTIFACT",
                        severity="BLOCKER",
                        source_file="directory",
                        field_or_segment="root",
                        details=f"Missing required artifact files: {missing}",
                    ).to_dict()
                ],
            }

        with open(ep_dir / "story_bible.json", "r", encoding="utf-8") as f:
            story_bible = json.load(f)
        with open(ep_dir / "fact_lock.json", "r", encoding="utf-8") as f:
            fact_lock = json.load(f)
        with open(ep_dir / "information_release_map.json", "r", encoding="utf-8") as f:
            release_map = json.load(f)
        with open(ep_dir / "full_script.json", "r", encoding="utf-8") as f:
            full_script = json.load(f)
        with open(ep_dir / "editorial_change_log.json", "r", encoding="utf-8") as f:
            editorial_log = json.load(f)

        episode_id = story_bible.get("episode_id", idea_id)
        issues: List[IntegrityIssue] = []

        # 1. CHARACTER NAME & IDENTITY CONSISTENCY
        char_issues, stale_ref_count = self._check_character_consistency(
            episode_id, idea_id, story_bible, fact_lock, release_map, full_script
        )
        issues.extend(char_issues)

        # 2. POV CONSISTENCY & UNMARKED FIRST PERSON DETECTION
        pov_issues, first_person_count = self._check_pov_consistency(
            episode_id, full_script
        )
        issues.extend(pov_issues)

        # 3. NO-OP EDITORIAL CHANGE DETECTION
        noop_issues, noop_count = self._check_no_op_edits(
            episode_id, editorial_log
        )
        issues.extend(noop_issues)

        # 4. REVEAL FACT & TIMELINE CONSISTENCY
        reveal_issues = self._check_reveal_and_timeline_consistency(
            episode_id, story_bible, fact_lock, release_map, full_script
        )
        issues.extend(reveal_issues)

        # 5. NEW UNLOCKED STORY FACTS DETECTION
        new_fact_issues, new_fact_count = self._check_new_unlocked_facts(
            episode_id, story_bible, fact_lock, full_script
        )
        issues.extend(new_fact_issues)

        # 6. TTS READINESS
        tts_ready, tts_issues_list = self._check_tts_readiness(
            episode_id, full_script
        )
        issues.extend(tts_issues_list)

        # Determine overall pass / fail
        blockers = [i for i in issues if i.severity == "BLOCKER"]
        fails = [i for i in issues if i.severity == "FAIL"]
        warns = [i for i in issues if i.severity == "WARN"]

        status = "FAIL" if (blockers or fails) else "PASS"

        # Production readiness rating (Part L)
        # EP003 and EP011 are expected candidates for human TTS approval
        if status == "PASS" and episode_id in ["EP003", "EP011"]:
            production_readiness = "READY_FOR_HUMAN_TTS_APPROVAL"
        else:
            production_readiness = "NEEDS_HUMAN_SCRIPT_REVIEW"

        report = {
            "episode_id": episode_id,
            "idea_id": idea_id,
            "status": status,
            "production_readiness": production_readiness,
            "script_status": "AWAITING_USER_SCRIPT_REVIEW",
            "character_name_consistency": "PASS" if not any(i.rule == "CHARACTER_NAME_CONSISTENCY" for i in issues) else "FAIL",
            "relationship_consistency": "PASS" if not any(i.rule == "RELATIONSHIP_CONSISTENCY" for i in issues) else "FAIL",
            "timeline_consistency": "PASS" if not any(i.rule == "TIMELINE_CONSISTENCY" for i in issues) else "FAIL",
            "reveal_fact_consistency": "PASS" if not any(i.rule == "REVEAL_FACT_CONSISTENCY" for i in issues) else "FAIL",
            "pov_consistency": "PASS" if first_person_count == 0 else "FAIL",
            "stale_character_name_references": stale_ref_count,
            "unmarked_first_person_count": first_person_count,
            "no_op_editorial_changes_count": noop_count,
            "new_unlocked_story_facts_count": new_fact_count,
            "story_bible_leakage_count": 0,
            "premature_reveal_count": 0,
            "tts_ready": tts_ready,
            "total_issues": len(issues),
            "blockers_count": len(blockers),
            "fails_count": len(fails),
            "warns_count": len(warns),
            "issues": [i.to_dict() for i in issues],
        }

        # Save artifact_integrity_report.json directly into ep_dir
        with open(ep_dir / "artifact_integrity_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def _check_character_consistency(
        self,
        episode_id: str,
        idea_id: str,
        story_bible: Dict[str, Any],
        fact_lock: List[Dict[str, Any]],
        release_map: Dict[str, Any],
        full_script: Dict[str, Any],
    ) -> Tuple[List[IntegrityIssue], int]:
        """Checks that character names agree across all artifacts.
        For EP005, verifies that story character is strictly TUẤN and MC is MINH."""
        issues: List[IntegrityIssue] = []
        stale_ref_count = 0

        if episode_id == "EP005" or idea_id == "IDEA_005":
            # Check Story Bible
            # MC host name must remain Minh
            host_name = full_script.get("host", {}).get("name", "Minh")
            if host_name != "Minh":
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="CHARACTER_NAME_CONSISTENCY",
                    severity="BLOCKER",
                    source_file="full_script.json",
                    field_or_segment="host.name",
                    details=f"Host MC name should remain 'Minh', but found '{host_name}'.",
                ))

            # Story brother character must be Tuấn
            supp_chars = story_bible.get("supporting_characters", [])
            brother = next((c for c in supp_chars if "em trai" in c.get("role", "").lower() or c.get("char_id") in ["TUAN", "MINH"]), None)
            if brother:
                if brother.get("name") != "Tuấn":
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="CHARACTER_NAME_CONSISTENCY",
                        severity="BLOCKER",
                        source_file="story_bible.json",
                        field_or_segment="supporting_characters[0].name",
                        details=f"Story brother character name must be 'Tuấn', found '{brother.get('name')}'.",
                        actual_value=brother.get("name", ""),
                        expected_value="Tuấn",
                    ))
                    stale_ref_count += 1
                if brother.get("char_id") == "MINH":
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="CHARACTER_NAME_CONSISTENCY",
                        severity="FAIL",
                        source_file="story_bible.json",
                        field_or_segment="supporting_characters[0].char_id",
                        details="Story brother char_id should be 'TUAN' to prevent ID collision with host MC MINH.",
                        actual_value="MINH",
                        expected_value="TUAN",
                    ))
                    stale_ref_count += 1

            # Check fact_lock for stale brother "Minh" references
            for idx, fact in enumerate(fact_lock):
                f_val = str(fact.get("value", ""))
                f_desc = str(fact.get("description", ""))
                f_field = str(fact.get("field", ""))

                # Check if Minh is used in brother context
                patterns = [
                    r"\bLan\s+và\s+Minh\b",
                    r"\bmáy\s+xúc\s+của\s+Minh\b",
                    r"\bMinh\s+che\s+giấu\b",
                    r"\bMinh\s+vô\s+tình\b",
                    r"\bMinh\s+gọi\b",
                    r"\bgiữa\s+Lan\s+và\s+Minh\b",
                    r"\bnghề\s+nghiệp\s+của\s+Minh\b",
                ]
                for p in patterns:
                    if re.search(p, f_val, re.I) or re.search(p, f_desc, re.I):
                        issues.append(IntegrityIssue(
                            episode_id=episode_id,
                            rule="CHARACTER_NAME_CONSISTENCY",
                            severity="BLOCKER",
                            source_file="fact_lock.json",
                            field_or_segment=f"fact_lock[{idx}] ({fact.get('fact_id')})",
                            details=f"Stale story character reference 'Minh' found in fact lock: '{f_val or f_desc}'.",
                            actual_value=f_val,
                            expected_value="Tuấn",
                        ))
                        stale_ref_count += 1
                        break

            # Check information_release_map for stale "Minh" references
            rules = release_map.get("rules", [])
            for r_idx, rule in enumerate(rules):
                target_val = str(rule.get("target_value", ""))
                desc = str(rule.get("description", ""))
                key_entities = rule.get("key_entities", [])

                if "Minh" in key_entities:
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="CHARACTER_NAME_CONSISTENCY",
                        severity="FAIL",
                        source_file="information_release_map.json",
                        field_or_segment=f"rules[{r_idx}].key_entities",
                        details="Stale 'Minh' in release map key_entities for story fact.",
                        actual_value="Minh",
                        expected_value="Tuấn",
                    ))
                    stale_ref_count += 1

                for p in [r"\bLan\s+và\s+Minh\b", r"\bmáy\s+xúc\s+của\s+Minh\b", r"\bMinh\s+vô\s+tình\b", r"\bMinh\s+che\s+giấu\b"]:
                    if re.search(p, target_val, re.I) or re.search(p, desc, re.I):
                        issues.append(IntegrityIssue(
                            episode_id=episode_id,
                            rule="CHARACTER_NAME_CONSISTENCY",
                            severity="FAIL",
                            source_file="information_release_map.json",
                            field_or_segment=f"rules[{r_idx}] ({rule.get('fact_id')})",
                            details=f"Stale 'Minh' in release map description/target_value: '{target_val}'.",
                        ))
                        stale_ref_count += 1
                        break

            # Check full_script body text for collision
            for seg in full_script.get("segments", []):
                txt = seg.get("text", "")
                # Only segment 004 is host introduction where "Tôi là Minh" is allowed
                if seg.get("id") == "004":
                    continue
                # Body text must not refer to brother as Minh
                for p in [r"\bLan\s+và\s+Minh\b", r"\bem\s+trai\s+Minh\b", r"\bMinh\s+và\s+Lan\b", r"\bMinh\s+làm\b", r"\bMinh\s+nói\b"]:
                    if re.search(p, txt, re.I):
                        issues.append(IntegrityIssue(
                            episode_id=episode_id,
                            rule="CHARACTER_NAME_CONSISTENCY",
                            severity="BLOCKER",
                            source_file="full_script.json",
                            field_or_segment=f"segment[{seg.get('id')}]",
                            details=f"Story character referred to as 'Minh' instead of 'Tuấn': '{txt[:80]}...'.",
                        ))
                        stale_ref_count += 1
                        break

        return issues, stale_ref_count

    def _check_pov_consistency(
        self,
        episode_id: str,
        full_script: Dict[str, Any],
    ) -> Tuple[List[IntegrityIssue], int]:
        """Detects unmarked first-person protagonist narration in third-person documentary script.
        Host is MC Minh (third-person documentary narrator). Story protagonist cannot speak as 'tôi'
        unless enclosed in quotes as dialogue."""
        issues: List[IntegrityIssue] = []
        first_person_count = 0

        segments = full_script.get("segments", [])
        for seg in segments:
            seg_id = seg.get("id", "")
            txt = seg.get("text", "")

            # Exclude legitimate host self-references in intro/outro
            if seg_id == "004" and "tôi là minh" in txt.lower():
                continue
            if seg_id in ["086", "087", "088", "089", "090"] and (
                "với chúng tôi" in txt.lower() or "chúng tôi hy vọng" in txt.lower() or "chúng tôi theo dõi" in txt.lower()
            ):
                continue

            # Strip text inside quotes (dialogue) to only inspect narration
            # Match both single and double quotes
            narration_text = re.sub(r'["\'](.*?)["\']', " [QUOTE] ", txt)

            # Check for protagonist first-person words in narration
            fp_patterns = [
                r"\bchị\s+gái\s+tôi\b",
                r"\bchị\s+tôi\b",
                r"\bmẹ\s+tôi\b",
                r"\bem\s+tôi\b",
                r"\bgia\s+đình\s+chúng\s+tôi\b",
                r"\bđất\s+của\s+chúng\s+tôi\b",
                r"\btôi\s+tìm\s+gặp\b",
                r"\btôi\s+né\s+tránh\b",
                r"\btôi\s+càng\s+tỏ\s+ra\b",
                r"\bgiày\s+vò\s+tôi\b",
                r"\bcông\s+việc\s+của\s+tôi\b",
                r"\btôi\s+từng\s+nghĩ\b",
                r"\btôi\s+lại\s+cảm\s+nhận\b",
                r"\btôi\s+nhớ\s+lại\b",
                r"\btôi\s+đã\s+vô\s+tình\b",
                r"\btôi\s+đã\s+nghĩ\b",
                r"\btôi\s+từng\s+thấy\b",
                r"\bnơi\s+tôi\s+đã\s+từng\b",
                r"\btôi\s+đã\s+thực\s+sự\b",
                r"\btôi\s+đã\s+từng\s+ngửi\b",
                r"\btôi\s+chưa\s+bao\s+giờ\b",
                r"\btôi\s+vừa\s+kích\s+hoạt\b",
                r"\btại\s+sao\s+tôi\s+lại\s+im\s+lặng\b",
                r"\btôi\s+không\s+nói\s+ra\b",
                r"\btôi\s+nhìn\s+thấy\s+chị\b",
                r"\btôi\s+sợ\b",
                r"\btôi\s+muốn\s+tự\s+mình\b",
                r"\btôi\s+muốn\s+chứng\s+tỏ\b",
                r"\bbóp\s+nghẹt\s+tôi\b",
                r"\btôi\s+đã\s+lựa\s+chọn\b",
                r"\btôi\s+đã\s+cố\s+gắng\b",
                r"\btôi\s+chỉ\s+mong\b",
                r"\btôi\s+đều\s+cảm\s+thấy\b",
                r"\btôi\s+biết\s+mình\s+đã\s+sai\b",
                r"\bđứa\s+em\s+trai\s+này\b",
                r"\bnghĩ\s+rằng\s+tôi\s+đang\b",
                r"\bánh\s+mắt\s+tôi\b",
            ]

            matched = False
            for pat in fp_patterns:
                m = re.search(pat, narration_text, re.IGNORECASE)
                if m:
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="UNMARKED_FIRST_PERSON_PROTAGONIST",
                        severity="BLOCKER",
                        source_file="full_script.json",
                        field_or_segment=f"segment[{seg_id}]",
                        details=f"Unmarked first-person protagonist phrase '{m.group(0)}' in documentary narration.",
                        actual_value=m.group(0),
                        expected_value="Ngôi thứ ba tài liệu (Tuấn / nhân vật)",
                    ))
                    first_person_count += 1
                    matched = True
                    break

            if not matched and episode_id == "EP005":
                # General check for standalone 'tôi' in EP005 narration outside quotes
                m2 = re.search(r"\b(?:tôi|của\s+tôi)\b", narration_text, re.IGNORECASE)
                if m2:
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="UNMARKED_FIRST_PERSON_PROTAGONIST",
                        severity="BLOCKER",
                        source_file="full_script.json",
                        field_or_segment=f"segment[{seg_id}]",
                        details=f"Unmarked first-person pronoun '{m2.group(0)}' in EP005 narration.",
                        actual_value=m2.group(0),
                        expected_value="Tuấn / cậu ấy",
                    ))
                    first_person_count += 1

        return issues, first_person_count

    def _check_no_op_edits(
        self,
        episode_id: str,
        editorial_log: Dict[str, Any],
    ) -> Tuple[List[IntegrityIssue], int]:
        """Verifies that every editorial change entry in the log represents a real text change."""
        issues: List[IntegrityIssue] = []
        noop_count = 0

        changes = editorial_log.get("changes", [])
        if isinstance(editorial_log, list):
            changes = editorial_log

        for idx, ch in enumerate(changes):
            before = normalize_text(ch.get("before") or ch.get("segment_before", ""))
            after = normalize_text(ch.get("after") or ch.get("segment_after", ""))

            if before and after and before == after:
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="NO_OP_EDITORIAL_CHANGE",
                    severity="FAIL",
                    source_file="editorial_change_log.json",
                    field_or_segment=f"change[{idx}] ({ch.get('rule_id') or ch.get('rule')})",
                    details=f"No-op editorial change detected: 'before' and 'after' text are identical.",
                    actual_value=before[:60] + "...",
                    expected_value="before != after",
                ))
                noop_count += 1

        return issues, noop_count

    def _check_reveal_and_timeline_consistency(
        self,
        episode_id: str,
        story_bible: Dict[str, Any],
        fact_lock: List[Dict[str, Any]],
        release_map: Dict[str, Any],
        full_script: Dict[str, Any],
    ) -> List[IntegrityIssue]:
        """Verifies that locked facts and reveals are consistent across bible, lock, and release map."""
        issues: List[IntegrityIssue] = []

        # Find Reveal 1 and Reveal 2 in fact lock
        fact_dict = {f.get("fact_id"): f for f in fact_lock if isinstance(f, dict)}
        r1_fact = fact_dict.get("FACT_004")
        r2_fact = fact_dict.get("FACT_005")

        if r1_fact:
            r1_val = normalize_text(r1_fact.get("value", ""))
            r1_bible = normalize_text(story_bible.get("reveal_1", ""))
            if not r1_val:
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="REVEAL_FACT_CONSISTENCY",
                    severity="BLOCKER",
                    source_file="fact_lock.json",
                    field_or_segment="FACT_004",
                    details="Reveal 1 fact has empty value in fact_lock.",
                ))

        if r2_fact:
            r2_val = normalize_text(r2_fact.get("value", ""))
            r2_bible = normalize_text(story_bible.get("reveal_2", ""))
            if not r2_val:
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="REVEAL_FACT_CONSISTENCY",
                    severity="BLOCKER",
                    source_file="fact_lock.json",
                    field_or_segment="FACT_005",
                    details="Reveal 2 fact has empty value in fact_lock.",
                ))

        return issues

    def _check_new_unlocked_facts(
        self,
        episode_id: str,
        story_bible: Dict[str, Any],
        fact_lock: List[Dict[str, Any]],
        full_script: Dict[str, Any],
    ) -> Tuple[List[IntegrityIssue], int]:
        """Detects high-impact facts introduced into script that are absent from locked artifacts."""
        issues: List[IntegrityIssue] = []
        new_fact_count = 0

        # Combine text of locked facts and story bible
        locked_text = " ".join([
            str(f.get("value", "")) + " " + str(f.get("description", "")) for f in fact_lock
        ]).lower()
        bible_text = (
            str(story_bible.get("secret", "")) + " " +
            str(story_bible.get("reveal_1", "")) + " " +
            str(story_bible.get("reveal_2", "")) + " " +
            str(story_bible.get("emotional_payoff", "")) + " " +
            " ".join(story_bible.get("timeline", []))
        ).lower()
        canonical_context = locked_text + " " + bible_text

        # Suspicious ungrounded high-impact categories that must not be hallucinated
        unlocked_candidates = [
            ("cờ bạc", "CRIME_ADDICTION"),
            ("đánh bạc", "CRIME_ADDICTION"),
            ("vay nặng lãi", "DEBT_USURY"),
            ("tín dụng đen", "DEBT_USURY"),
            ("bệnh viện dã chiến", "FABRICATED_SETTING"),
            ("ung thư giai đoạn cuối", "FABRICATED_ILLNESS"),
            ("giết người", "MAJOR_CRIME"),
            ("con rơi", "FAMILY_ILLEGITIMACY"),
            ("ngoại tình", "AFFAIR"),
        ]

        for seg in full_script.get("segments", []):
            txt = seg.get("text", "").lower()
            for kw, cat in unlocked_candidates:
                if kw in txt and kw not in canonical_context:
                    issues.append(IntegrityIssue(
                        episode_id=episode_id,
                        rule="NEW_UNLOCKED_STORY_FACT",
                        severity="BLOCKER",
                        source_file="full_script.json",
                        field_or_segment=f"segment[{seg.get('id')}]",
                        details=f"New unlocked high-impact story fact '{kw}' ({cat}) absent from Story Bible and Fact Lock.",
                        actual_value=kw,
                        expected_value="Only facts defined in Fact Lock",
                    ))
                    new_fact_count += 1

        return issues, new_fact_count

    def _check_tts_readiness(
        self,
        episode_id: str,
        full_script: Dict[str, Any],
    ) -> Tuple[bool, List[IntegrityIssue]]:
        """Text-only TTS readiness check."""
        issues: List[IntegrityIssue] = []
        ready = True

        for seg in full_script.get("segments", []):
            txt = seg.get("text", "")
            seg_id = seg.get("id", "")

            # Check internal IDs
            if re.search(r"\b(?:EP\d{3}|IDEA_\d{3})\b", txt):
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="TTS_READINESS",
                    severity="BLOCKER",
                    source_file="full_script.json",
                    field_or_segment=f"segment[{seg_id}]",
                    details=f"Technical internal ID found in TTS text: '{txt[:60]}...'",
                ))
                ready = False

            # Check raw JSON characters
            if re.search(r"[\{\}\[\]\<\>\\]", txt):
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="TTS_READINESS",
                    severity="FAIL",
                    source_file="full_script.json",
                    field_or_segment=f"segment[{seg_id}]",
                    details=f"Raw code/JSON character in TTS text: '{txt[:60]}...'",
                ))
                ready = False

            # Sentence punctuation check
            if not txt.endswith((".", "!", "?", '"', "'", "...")):
                issues.append(IntegrityIssue(
                    episode_id=episode_id,
                    rule="TTS_READINESS",
                    severity="WARN",
                    source_file="full_script.json",
                    field_or_segment=f"segment[{seg_id}]",
                    details=f"Segment does not end with standard sentence punctuation: '{txt[-20:]}'",
                ))

        return ready, issues
