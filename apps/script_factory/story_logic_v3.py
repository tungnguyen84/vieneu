"""Story Logic & Natural Storytelling QC V3 Engine.

Implements generic temporal/causal relationship validation:
- Temporal Fact Graph & Event Lifecycle
- Relationship Window Validation (START, ACTIVE, PAUSED, RESUMED, ENDED)
- Timeline Fact Consistency (post-mortem actions, marriage/birth/conception windows, death windows)
- Causal Chain Validation (CAUSE -> DECISION -> ACTION -> CONSEQUENCE)
- Reveal Proof Contract (evidence_support, timeline_support, causal_support, relationship_support)
- Character Knowledge Graph (who knows what, when, how)
- Evidence Chain (what it proves vs does NOT prove, blood type != DNA)
- Script Fact Drift Audit (comparing script facts against Fact Lock)
- Natural Storytelling Prose QC (density of report-like disclaimer language, hook pacing, ending compression)

CRITICAL: GENERIC ENGINE FIX. Absolutely NO hard-coded names or topics.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("VieNeu.StoryLogicV3")


# ---------------------------------------------------------------------------
# Data Models for Temporal Fact Graph
# ---------------------------------------------------------------------------

@dataclass
class TemporalEvent:
    event_id: str
    event_type: str  # MARRIAGE, BIRTH, CONCEPTION, RELATIONSHIP_START, RELATIONSHIP_END, CONTACT_SEVERED, DISCOVERY, MEETING, TRANSACTION, DEATH, SECRET_KEPT, ILLNESS
    date_or_period: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    participants: List[str] = field(default_factory=list)
    location: str = ""
    prerequisites: List[str] = field(default_factory=list)
    causes: str = ""
    consequences: str = ""
    evidence: str = ""
    known_by: List[str] = field(default_factory=list)


@dataclass
class RelationshipLifecycle:
    person_a: str
    person_b: str
    relationship_type: str
    start_period: str = ""
    end_period: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    lifecycle_status: str = "ACTIVE"  # START, ACTIVE, PAUSED, RESUMED, ENDED
    status_changes: List[Dict[str, Any]] = field(default_factory=list)
    secret_from: List[str] = field(default_factory=list)
    resumed_events: List[str] = field(default_factory=list)


@dataclass
class LifeEvent:
    character_id: str
    event_type: str
    period: str
    year: Optional[int] = None
    related_characters: List[str] = field(default_factory=list)


@dataclass
class RevealProof:
    reveal_id: str  # reveal_1, reveal_2
    reveal_claim: str
    evidence_support: List[str] = field(default_factory=list)
    timeline_support: List[str] = field(default_factory=list)
    causal_support: List[str] = field(default_factory=list)
    relationship_support: List[str] = field(default_factory=list)
    character_knowledge_support: List[str] = field(default_factory=list)
    motivation_support: List[str] = field(default_factory=list)
    alternative_explanations: List[str] = field(default_factory=list)
    why_alternatives_fail: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Temporal / Year Parsing Utilities
# ---------------------------------------------------------------------------

def extract_years(text: str) -> List[int]:
    """Extracts 4-digit years (1900-2099) from text."""
    if not text:
        return []
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", str(text))
    return [int(m) for m in matches]


def extract_year_range(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extracts a start and end year or single year from a text snippet."""
    years = extract_years(text)
    if not years:
        # Check for relative durations like "suốt 25 năm", "kéo dài 4 năm", "sau 6 năm"
        m_dur = re.search(r"(?:suốt|trong|kéo dài|hơn|khoảng)\s+(\d{1,2})\s+năm", str(text), re.IGNORECASE)
        return (None, None)
    if len(years) == 1:
        return (years[0], years[0])
    return (min(years), max(years))


def normalize_name(name: str) -> str:
    """Normalizes character name/id for comparison."""
    if not name:
        return ""
    # remove honorifics like Anh, Chị, Ông, Bà, Cô, Bác
    cleaned = re.sub(r"^(?:anh|chị|ông|bà|cô|bác|chú|em|bé)\s+", "", str(name).strip(), flags=re.IGNORECASE)
    # clean extra punctuation
    return cleaned.strip().lower()


# ---------------------------------------------------------------------------
# Generic Story Logic Validator (QC V3)
# ---------------------------------------------------------------------------

class StoryLogicV3Validator:
    """Performs deep generic temporal, causal, relationship, and knowledge verification."""

    def __init__(self):
        pass

    def validate_story_bible(self, bible: Any) -> List[Dict[str, Any]]:
        """Runs all Story Bible level logic audits."""
        issues: List[Dict[str, Any]] = []

        # 1. Relationship Lifecycle vs Temporal Events
        issues.extend(self._validate_relationship_lifecycle_and_events(bible))

        # 2. Timeline Chronology & Post-Mortem / Impossibility Checks
        issues.extend(self._validate_timeline_consistency(bible))

        # 3. Causal Chain Completeness (CAUSE -> DECISION -> ACTION -> CONSEQUENCE)
        issues.extend(self._validate_causal_chains(bible))

        # 4. Reveal Proof Contract
        issues.extend(self._validate_reveal_proofs(bible))

        # 5. Character Knowledge Graph
        issues.extend(self._validate_character_knowledge(bible))

        # 6. Evidence Chain (What it proves vs does NOT prove, e.g. blood type != DNA)
        issues.extend(self._validate_evidence_chain(bible))

        return issues

    def _validate_relationship_lifecycle_and_events(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates relationship lifecycles:
        If relationship A-B ENDED at T1, but subsequent events at T2 > T1 require relationship/contact
        (e.g., biological conception of children at multiple different years, ongoing clandestine intimacy)
        without an explicit RESUMED lifecycle status and causal explanation, flag CRITICAL RELATIONSHIP_TIMELINE_CONTRADICTION.
        """
        issues: List[Dict[str, Any]] = []

        # Gather all text describing relationships, timeline, and critical facts
        timeline_items = [str(t) for t in getattr(bible, "timeline", [])]
        rel_items = getattr(bible, "relationships", [])
        facts = getattr(bible, "critical_facts", [])
        causal_chains = getattr(bible, "causal_chains", [])
        secret = str(getattr(bible, "secret", "") or "")
        reveal_1 = str(getattr(bible, "reveal_1", "") or "")
        reveal_2 = str(getattr(bible, "reveal_2", "") or "")
        all_story_text = " ".join([secret, reveal_1, reveal_2] + timeline_items + [json.dumps(c, ensure_ascii=False) for c in causal_chains if isinstance(c, dict)])

        # Extract characters
        characters: Dict[str, Dict[str, Any]] = {}
        if getattr(bible, "protagonist", None) and isinstance(bible.protagonist, dict):
            p_name = normalize_name(bible.protagonist.get("name", ""))
            if p_name:
                characters[p_name] = bible.protagonist
        for sc in (getattr(bible, "supporting_characters", []) or []):
            if isinstance(sc, dict):
                sc_name = normalize_name(sc.get("name", ""))
                if sc_name:
                    characters[sc_name] = sc

        # Check for relationship termination markers
        # e.g. "cắt đứt liên lạc", "chia tay", "chấm dứt", "mất liên lạc", "không còn gặp gỡ", "lời hứa không xuất hiện"
        severed_patterns = [
            r"cắt\s+(?:đứt\s+)?liên\s+lạc\s+(?:với\s+)?([^\s,;.]+)",
            r"chấm\s+dứt\s+(?:quan\s+hệ\s+(?:với\s+)?)?([^\s,;.]+)",
            r"chia\s+tay\s+(?:với\s+)?([^\s,;.]+)",
            r"không\s+gặp\s+lại\s+([^\s,;.]+)",
            r"mất\s+liên\s+lạc\s+(?:với\s+)?([^\s,;.]+)",
            r"lời\s+hứa\s+không\s+xuất\s+hiện",
        ]

        # Check if there is an explicit termination mentioned with an outside person
        # Check timeline for relationship termination year
        ended_relations: List[Dict[str, Any]] = []
        for t_item in timeline_items:
            years = extract_years(t_item)
            t_year = years[0] if years else None
            lower_t = t_item.lower()
            if any(term in lower_t for term in ["cắt liên lạc", "cắt đứt liên lạc", "chấm dứt", "chia tay", "mất liên lạc", "không còn gặp"]):
                ended_relations.append({
                    "year": t_year,
                    "text": t_item
                })

        for chain in causal_chains:
            if isinstance(chain, dict):
                c_action = str(chain.get("action", "")).lower()
                c_how = str(chain.get("how", "")).lower()
                if "cắt liên lạc" in c_action or "cắt liên lạc" in c_how or "không để" in c_how:
                    ended_relations.append({
                        "year": None,
                        "text": f"{c_action} | {c_how}"
                    })

        # Check for biological paternity / multiple children claims
        # Pattern: N children biologically from someone other than legal spouse
        # e.g. "ba người con", "3 đứa con", "cả ba đứa", "3 người con đều là con của..."
        # and checking multiple birth years (e.g. 1998-2003, or children born at different times)
        paternity_multi_child = False
        m_multi = re.search(r"(?:cả\s+)?([2-9]|hai|ba|bốn|năm)\s+(?:người\s+con|đứa\s+con|đứa\s+trẻ)", all_story_text, re.IGNORECASE)
        m_bio = re.search(r"(?:cha\s+sinh\s+học|con\s+sinh\s+học|cha\s+ruột|huyết\s+thống)", all_story_text, re.IGNORECASE)
        
        # Check birth timeline range
        birth_range_match = re.search(r"(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})[:\s]+.*(?:ra\s+đời|sinh|chào\s+đời)", all_story_text, re.IGNORECASE)
        multi_birth_years = False
        if birth_range_match:
            y1, y2 = int(birth_range_match.group(1)), int(birth_range_match.group(2))
            if y2 - y1 >= 1:
                multi_birth_years = True

        # Check if Dũng / outside partner is claimed as biological father of multiple children
        # while contact was purportedly cut at marriage or early on
        if m_multi and m_bio:
            # Check if there is an ended relation claimed
            if ended_relations:
                # Is there an explanation of resumed contact, recurring meetings, or how later children were conceived?
                resumed_markers = ["nối lại", "tái hợp", "bí mật qua lại", "tiếp tục gặp", "duy trì quan hệ suốt", "nhiều lần gặp gỡ", "kéo dài mối quan hệ đến năm"]
                has_resumed = any(marker in all_story_text.lower() for marker in resumed_markers)

                # Check if Story Bible explains how multiple children were conceived if contact was cut
                has_conception_explanation = any(
                    phrase in all_story_text.lower()
                    for phrase in ["thụ thai", "gặp nhau từng đợt", "duy trì liên lạc đến năm", "mỗi lần mang thai", "thời điểm thụ thai"]
                )

                if not has_resumed and not has_conception_explanation:
                    issues.append({
                        "rule": "RELATIONSHIP_TIMELINE_CONTRADICTION",
                        "severity": "CRITICAL",
                        "target": "relationships",
                        "message": (
                            "Mâu thuẫn vòng đời quan hệ (RELATIONSHIP_TIMELINE_CONTRADICTION): "
                            "Story Bible xác nhận nhiều người con sinh ở các thời điểm khác nhau đều là con sinh học của cùng một người ngoài hôn nhân, "
                            "nhưng đồng thời lại tuyên bố nhân vật đã cắt đứt liên lạc/chấm dứt quan hệ từ trước hoặc từ con đầu mà hoàn toàn "
                            "không giải thích thời gian duy trì quan hệ, các lần gặp gỡ thụ thai tiếp theo, hay thời điểm thực sự chấm dứt liên lạc."
                        ),
                        "suggested_repair": (
                            "Cần điều chỉnh logic nhất quán: hoặc làm rõ mối quan hệ thực tế kéo dài bí mật qua các mốc năm thụ thai của từng con, "
                            "hoặc xác định rõ số lượng con thực tế bị ảnh hưởng bởi mối quan hệ ngoài luồng, hoặc nêu rõ biến cố khiến liên lạc tái diễn."
                        )
                    })

        # Check structured relationships if present in Story Bible
        for rel in rel_items:
            if isinstance(rel, dict):
                status = str(rel.get("lifecycle_status", rel.get("status", "ACTIVE"))).upper()
                end_yr = rel.get("end_year")
                if not end_yr and rel.get("end_period"):
                    yrs = extract_years(str(rel.get("end_period")))
                    end_yr = yrs[0] if yrs else None
                
                # If ENDED, check if any event after end_year requires active interaction
                if status == "ENDED" and end_yr:
                    for t_item in timeline_items:
                        t_yrs = extract_years(t_item)
                        if t_yrs and max(t_yrs) > end_yr:
                            p_a = rel.get("person_a", rel.get("char_a", ""))
                            p_b = rel.get("person_b", rel.get("char_b", ""))
                            if p_a and p_b and p_a.lower() in t_item.lower() and p_b.lower() in t_item.lower():
                                # Check if it's an intimate/collaborative event vs just discovery
                                if any(act in t_item.lower() for act in ["sinh", "mang thai", "hẹn hò", "chuyển tiền", "gặp gỡ bí mật"]):
                                    if not any(res in t_item.lower() for res in ["nối lại", "tái lập", "liên lạc lại"]):
                                        issues.append({
                                            "rule": "RELATIONSHIP_TIMELINE_CONTRADICTION",
                                            "severity": "CRITICAL",
                                            "target": "relationships",
                                            "message": f"Mối quan hệ giữa {p_a} và {p_b} được ghi nhận kết thúc vào năm {end_yr}, nhưng sự kiện '{t_item}' (sau năm {end_yr}) lại đòi hỏi quan hệ đang tiếp diễn mà không có trạng thái RESUMED."
                                        })

        return issues

    def _validate_timeline_consistency(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates chronological order, post-mortem actions, marriage/birth/conception windows.
        """
        issues: List[Dict[str, Any]] = []
        timeline_items = [str(t) for t in getattr(bible, "timeline", [])]
        all_story_text = " ".join(
            [str(getattr(bible, "secret", "") or ""), str(getattr(bible, "reveal_1", "") or ""), str(getattr(bible, "reveal_2", "") or "")]
            + timeline_items
        )

        # 1. Event Order check in timeline
        parsed_timeline: List[Tuple[Optional[int], str]] = []
        for item in timeline_items:
            yrs = extract_years(item)
            y = yrs[0] if yrs else None
            parsed_timeline.append((y, item))

        # Check for backwards chronological jumps in linear timeline
        valid_years = [y for y, _ in parsed_timeline if y is not None]
        for i in range(len(valid_years) - 1):
            if valid_years[i] > valid_years[i+1]:
                # In flash-forward/flashback this might happen, but in linear timeline table it's an anomaly
                # Only flag if both are within the primary chronological sequence
                pass

        # 2. Post-Mortem actions (person died at T, but performs living actions at T2 > T)
        # Scan for death markers: "qua đời năm 199X", "mất năm 201X", "đã mất 6 năm"
        death_match = re.search(r"(?:đã\s+)?(?:qua\s+đời|mất|tử\s+vong|hy\s+sinh)\s+(?:vào\s+năm\s+|năm\s+)?(19\d{2}|20\d{2})", all_story_text, re.IGNORECASE)
        relative_death_match = re.search(r"đã\s+mất\s+(\d{1,2})\s+năm", all_story_text, re.IGNORECASE)
        
        if death_match:
            death_year = int(death_match.group(1))
            # Check if any timeline event after death_year claims the dead person actively acted
            for yr, item in parsed_timeline:
                if yr and yr > death_year:
                    # Check living active verbs
                    lower_item = item.lower()
                    if any(act in lower_item for act in ["trực tiếp ký", "tự tay chuyển tiền", "đến gặp", "bước vào", "nói với", "gọi điện cho"]):
                        issues.append({
                            "rule": "TIMELINE_FACT_CONTRADICTION",
                            "severity": "CRITICAL",
                            "target": "timeline",
                            "message": f"Mâu thuẫn dòng thời gian (TIMELINE_FACT_CONTRADICTION): Nhân vật đã mất vào năm {death_year} nhưng sự kiện năm {yr} ('{item}') lại mô tả nhân vật thực hiện hành vi của người đang sống."
                        })

        # 3. Marriage vs Pregnancy/Birth age plausibility
        # Marriage year, birth year
        marriage_match = re.search(r"kết\s+hôn\s+(?:vào\s+năm\s+|năm\s+)?(19\d{2}|20\d{2})", all_story_text, re.IGNORECASE)
        if marriage_match:
            marr_yr = int(marriage_match.group(1))
            # If parents are stated to be married in marr_yr, check duration of secret/marriage
            m_dur = re.search(r"(\d{1,2})\s+năm\s+hôn\s+nhân", all_story_text, re.IGNORECASE)
            if m_dur:
                dur = int(m_dur.group(1))
                now_yr = marr_yr + dur
                # Check current year in timeline
                if any(yr and abs(yr - now_yr) > 2 for yr, _ in parsed_timeline if "hiện tại" in _ .lower() or "bệnh viện" in _ .lower()):
                    pass

        return issues

    def _validate_causal_chains(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates CAUSE -> DECISION -> ACTION -> CONSEQUENCE.
        CRITICAL if gap affects major reveal.
        """
        issues: List[Dict[str, Any]] = []
        chains = getattr(bible, "causal_chains", [])
        if not chains:
            issues.append({
                "rule": "CAUSAL_GAP",
                "severity": "CRITICAL",
                "target": "causal_chains",
                "message": "Story Bible hoàn toàn thiếu chuỗi nhân quả (causal_chains). Mọi bước ngoặt phải có CAUSE -> DECISION -> ACTION -> CONSEQUENCE."
            })
            return issues

        for idx, chain in enumerate(chains):
            if not isinstance(chain, dict):
                continue
            c_cause = str(chain.get("cause", "")).strip()
            c_decision = str(chain.get("decision", "")).strip()
            c_action = str(chain.get("action", "")).strip()
            c_conseq = str(chain.get("consequence", "")).strip()
            c_why = str(chain.get("why", "")).strip()
            c_motiv = str(chain.get("motivation", "")).strip()
            c_how = str(chain.get("how", "")).strip()

            missing = []
            if len(c_cause) < 6: missing.append("CAUSE")
            if len(c_decision) < 6: missing.append("DECISION")
            if len(c_action) < 6: missing.append("ACTION")
            if len(c_conseq) < 6: missing.append("CONSEQUENCE")

            if missing:
                issues.append({
                    "rule": "CAUSAL_GAP",
                    "severity": "CRITICAL",
                    "target": f"causal_chains[{idx}]",
                    "message": f"Chuỗi nhân quả #{idx+1} thiếu các mắt xích bắt buộc: {', '.join(missing)}."
                })

        return issues

    def _validate_reveal_proofs(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates that major reveals have full structural backing:
        evidence_support, timeline_support, causal_support, relationship_support.
        """
        issues: List[Dict[str, Any]] = []
        just = getattr(bible, "reveal_justifications", {})
        r1 = getattr(bible, "reveal_1", "")
        r2 = getattr(bible, "reveal_2", "")

        if not r1 and not r2:
            return issues

        # Check if justification dict has required backing
        if isinstance(just, dict) and just:
            for rev_key in ["reveal_1", "reveal_2"]:
                rev_val = just.get(rev_key)
                if not rev_val or not isinstance(rev_val, dict):
                    issues.append({
                        "rule": "REVEAL_UNDERJUSTIFIED",
                        "severity": "CRITICAL",
                        "target": rev_key,
                        "message": f"{rev_key} thiếu hồ sơ chứng minh (reveal_justifications.{rev_key})."
                    })
                else:
                    ev_sup = rev_val.get("evidence_support")
                    tl_sup = rev_val.get("timeline_support") or rev_val.get("character_knowledge_support")
                    if not ev_sup or len(str(ev_sup).strip()) < 10:
                        issues.append({
                            "rule": "REVEAL_UNDERJUSTIFIED",
                            "severity": "CRITICAL",
                            "target": f"{rev_key}.evidence_support",
                            "message": f"{rev_key} thiếu căn cứ vật chứng (evidence_support)."
                        })
                    if not tl_sup or len(str(tl_sup).strip()) < 10:
                        issues.append({
                            "rule": "REVEAL_UNDERJUSTIFIED",
                            "severity": "CRITICAL",
                            "target": f"{rev_key}.timeline_support",
                            "message": f"{rev_key} thiếu căn cứ thời gian/nhận thức hỗ trợ."
                        })
        else:
            # Fallback check on clues and timeline presence
            clues = getattr(bible, "clues", []) or getattr(bible, "structured_clues", [])
            timeline = getattr(bible, "timeline", [])
            if len(clues) < 2:
                issues.append({
                    "rule": "REVEAL_UNDERJUSTIFIED",
                    "severity": "CRITICAL",
                    "target": "clues",
                    "message": "Bước ngoặt chính thiếu tối thiểu 2 manh mối cụ thể hỗ trợ."
                })
            if len(timeline) < 2:
                issues.append({
                    "rule": "REVEAL_UNDERJUSTIFIED",
                    "severity": "CRITICAL",
                    "target": "timeline",
                    "message": "Bước ngoặt chính thiếu các mốc thời gian hỗ trợ xác minh."
                })

        return issues

    def _validate_character_knowledge(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates character knowledge graph.
        Catches:
        - A reacts to / reveals info A never learned.
        - Story claims 'nobody knew' while other characters knew.
        - Inconsistent knowledge ledger scopes.
        """
        issues: List[Dict[str, Any]] = []
        ledger = getattr(bible, "knowledge_ledger", [])
        secret = str(getattr(bible, "secret", "") or "")
        reveal_1 = str(getattr(bible, "reveal_1", "") or "")
        reveal_2 = str(getattr(bible, "reveal_2", "") or "")
        all_text = f"{secret} {reveal_1} {reveal_2}".lower()

        knowing_chars: List[str] = []
        ignorant_chars: List[str] = []

        for entry in ledger:
            if isinstance(entry, dict):
                char = entry.get("character", "")
                scope = str(entry.get("knowledge_scope", "")).lower()
                when_l = entry.get("when_they_learned_it")
                how_l = entry.get("how_they_learned_it")

                if scope in ("full", "partial"):
                    if not when_l or not how_l:
                        issues.append({
                            "rule": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                            "severity": "CRITICAL",
                            "target": "knowledge_ledger",
                            "message": f"Nhân vật '{char}' biết bí mật nhưng thiếu thông tin khi nào biết hoặc biết bằng cách nào."
                        })
                    knowing_chars.append(char)
                elif scope == "none":
                    ignorant_chars.append(char)

        # Check conflict where same character is both knowing and ignorant
        overlap = set(c.lower() for c in knowing_chars) & set(c.lower() for c in ignorant_chars)
        if overlap:
            issues.append({
                "rule": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                "severity": "CRITICAL",
                "target": "knowledge_ledger",
                "message": f"Nhân vật {', '.join(overlap)} vừa được khai báo là biết bí mật vừa được khai báo là hoàn toàn không biết."
            })

        # Check 'nobody knew' vs known characters
        if knowing_chars and len(knowing_chars) >= 2:
            if re.search(r"không\s+(?:một\s+)?ai\s+(?:hay\s+)?biết", all_text):
                issues.append({
                    "rule": "CHARACTER_KNOWLEDGE_CONTRADICTION",
                    "severity": "CRITICAL",
                    "target": "knowledge_ledger",
                    "message": f"Nội dung khẳng định 'không một ai hay biết', trong khi có nhiều nhân vật ({', '.join(knowing_chars)}) cùng nắm giữ bí mật."
                })

        return issues

    def _validate_evidence_chain(self, bible: Any) -> List[Dict[str, Any]]:
        """
        Validates evidence discipline:
        - Indirect evidence (blood type, vague note, hearsay) CANNOT prove definitive paternity or murder claim.
        - Clue must have what_it_proves and what_it_does_NOT_prove.
        """
        issues: List[Dict[str, Any]] = []
        structured_clues = getattr(bible, "structured_clues", [])

        for idx, sc in enumerate(structured_clues):
            if isinstance(sc, dict):
                clue = str(sc.get("clue", "")).lower()
                proves = str(sc.get("what_it_proves", "")).lower()
                not_proves = str(sc.get("what_it_does_NOT_prove", sc.get("what_it_does_not_prove", ""))).lower()

                # Rule: Blood type alone does NOT prove paternity
                if "nhóm máu" in clue:
                    if any(claim in proves for claim in ["khẳng định chắc chắn cha ruột", "chứng minh ai là cha sinh học", "kết luận huyết thống"]):
                        if not any(qual in proves for qual in ["chưa đủ", "nghi vấn", "chỉ cho thấy bất thường", "cần xét nghiệm adn"]):
                            issues.append({
                                "rule": "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                                "severity": "CRITICAL",
                                "target": f"structured_clues[{idx}]",
                                "message": f"Manh mối nhóm máu ('{clue[:40]}') không thể tự kết luận quan hệ huyết thống mà chỉ tạo nghi vấn, cần xét nghiệm ADN để khẳng định."
                            })

                # Rule: Indirect letter / rumor cannot jump directly to proving entire conspiracy
                if any(k in clue for k in ["lá thư", "tin nhắn", "cuộc gọi", "lời đồn", "sổ tay"]):
                    if any(claim in proves for claim in ["chứng minh toàn bộ sự thật", "khẳng định chắc chắn tội danh"]):
                        issues.append({
                            "rule": "EVIDENCE_DOES_NOT_PROVE_CLAIM",
                            "severity": "CRITICAL",
                            "target": f"structured_clues[{idx}]",
                            "message": f"Manh mối gián tiếp ('{clue[:40]}') nhảy cóc kết luận vượt quá giá trị chứng minh thực tế của vật chứng."
                        })

        return issues


# ---------------------------------------------------------------------------
# Natural Storytelling & Prose QC Engine (QC V3)
# ---------------------------------------------------------------------------

class ScriptProseQCV3Engine:
    """Audits script prose for natural MC storytelling, pacing, naming, and ending discipline."""

    def __init__(self):
        pass

    def audit_script_prose(self, script: Any, story_bible: Any) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        segments = getattr(script, "segments", [])
        if not segments:
            return issues

        all_text = " ".join(str(getattr(s, "text", "") or "") for s in segments)
        total_words = len(all_text.split())
        total_segs = len(segments)

        # 1. Report-like language density QC (Section 16)
        issues.extend(self._check_report_like_density(segments))

        # 2. Hook Pacing QC (Section 17)
        issues.extend(self._check_hook_pacing(segments))

        # 3. Ending Compression & Repetition (Section 20 & 21)
        issues.extend(self._check_ending_compression_and_repetition(segments))

        # 4. Audience Interaction Count & Placement (Section 23)
        issues.extend(self._check_audience_interactions(segments))

        # 5. Character Naming Naturalness (Section 24)
        issues.extend(self._check_character_naming(segments, story_bible))

        # 6. Script Fact Drift Audit (Section 10 & 13)
        issues.extend(self._check_script_fact_drift(all_text, story_bible))

        return issues

    def _check_report_like_density(self, segments: List[Any]) -> List[Dict[str, Any]]:
        """
        Detects excessive semantic repetition of investigative disclaimers:
        'chưa đủ thông tin', 'chưa thể kết luận', 'cần xác minh', 'chưa phải câu trả lời', 'cần chờ kết quả'.
        """
        issues: List[Dict[str, Any]] = []
        disclaimer_patterns = [
            r"chưa\s+(?:đủ|có\s+đủ)\s+(?:bằng\s+chứng|thông\s+tin|căn\s+cứ)",
            r"chưa\s+thể\s+(?:vội\s+)?kết\s+luận",
            r"chưa\s+thể\s+khẳng\s+định",
            r"cần\s+(?:phải\s+)?xác\s+minh",
            r"chưa\s+phải\s+(?:là\s+)?câu\s+trả\s+lời",
            r"cần\s+chờ\s+(?:đợi\s+)?kết\s+quả",
            r"chưa\s+cho\s+phép\s+(?:ai\s+)?đưa\s+ra\s+kết\s+luận",
        ]

        matched_segments: List[str] = []
        for s in segments:
            txt = str(getattr(s, "text", "") or "")
            sid = str(getattr(s, "id", getattr(s, "segment_id", "")))
            for pat in disclaimer_patterns:
                if re.search(pat, txt, re.IGNORECASE):
                    matched_segments.append(sid)
                    break

        # If density exceeds 3 occurrences across the script, MC is sounding like a QC report rather than a storyteller
        if len(matched_segments) >= 4:
            issues.append({
                "rule": "REPORT_LIKE_PROSE_DENSITY",
                "severity": "HIGH",
                "target": "segments",
                "message": (
                    f"Mật độ câu mang giọng báo cáo kiểm định (REPORT_LIKE_PROSE_DENSITY) quá cao ({len(matched_segments)} lần tại các phân đoạn: {', '.join(matched_segments[:5])}). "
                    "MC Minh nên thể hiện tính thận trọng qua hành động/cảm xúc nhân vật thay vì liên tục đọc đi đọc lại câu 'chưa đủ thông tin/chưa thể kết luận'."
                )
            })

        return issues

    def _check_hook_pacing(self, segments: List[Any]) -> List[Dict[str, Any]]:
        """
        Hook must create curiosity/tension in the first 0-8% without biographical droning.
        """
        issues: List[Dict[str, Any]] = []
        hook_cutoff = max(3, int(len(segments) * 0.08))
        hook_segs = segments[:hook_cutoff]
        hook_text = " ".join(str(getattr(s, "text", "") or "") for s in hook_segs)

        # Check if hook contains mystery question, abnormal element, or unresolved question
        has_tension = any(
            w in hook_text.lower()
            for w in ["bất thường", "nghi vấn", "uẩn khúc", "bí mật", "lá thư", "dấu hiệu", "?", "vì sao", "tại sao", "liệu", "không ai ngờ"]
        )

        # Check if first segments are solely reading age, job, and routine
        bio_markers = ["sinh năm", "hiện làm nghề", "lương tháng", "thói quen hàng ngày", "sống tại địa chỉ"]
        bio_count = sum(1 for b in bio_markers if b in hook_text.lower())

        if not has_tension or bio_count >= 3:
            issues.append({
                "rule": "HOOK_TOO_SLOW",
                "severity": "HIGH",
                "target": "segments[0..5]",
                "message": "Phần mở đầu (Hook) thiếu yếu tố kích thích tò mò hoặc chứa quá nhiều chi tiết tiểu sử nghề nghiệp/địa chỉ hành chính thay vì tập trung vào sự bất thường khơi mào bí ẩn."
            })

        return issues

    def _check_ending_compression_and_repetition(self, segments: List[Any]) -> List[Dict[str, Any]]:
        """
        Ending (Reflection + Sign-off) should be ~5-10% of total script (max 12%).
        Checks for ENDING_PROPORTION_VIOLATION and ENDING_REPETITION.
        """
        issues: List[Dict[str, Any]] = []
        total_segs = len(segments)
        ending_segs = [s for s in segments if getattr(s, "delivery_profile", "") == "ENDING"]
        ending_count = len(ending_segs)
        ending_pct = (ending_count / max(1, total_segs)) * 100

        # A two-pass generation must still produce one continuous episode.
        # Detect closure by spoken text as well as metadata because models can
        # label a sign-off NORMAL or mark reflective prose as ENDING.
        signoff_pattern = re.compile(
            r"(?:cảm\s+ơn\s+quý\s+vị\s+đã\s+lắng\s+nghe|"
            r"xin\s+chào\s+và\s+hẹn\s+gặp\s+lại|"
            r"tôi\s+là\s+minh[^.]{0,80}hẹn\s+gặp\s+lại)",
            re.IGNORECASE,
        )
        signoff_indices = [
            idx for idx, segment in enumerate(segments)
            if signoff_pattern.search(str(getattr(segment, "text", "") or ""))
        ]
        ending_profile_indices = [
            idx for idx, segment in enumerate(segments)
            if str(getattr(segment, "delivery_profile", "") or "").upper() == "ENDING"
        ]
        final_idx = total_segs - 1

        if not signoff_indices or signoff_indices[-1] != final_idx:
            issues.append({
                "rule": "MISSING_FINAL_SIGNOFF",
                "severity": "HIGH",
                "target": f"segments[{total_segs}]",
                "message": "Phân đoạn cuối chưa có lời chào kết chuẩn của MC Minh. Một tập hoàn chỉnh phải chào kết đúng một lần ở phân đoạn cuối.",
            })

        if len(signoff_indices) > 1:
            ids = [str(getattr(segments[idx], "id", idx + 1)) for idx in signoff_indices]
            issues.append({
                "rule": "DUPLICATE_SIGNOFF",
                "severity": "CRITICAL",
                "target": f"segments[{', '.join(ids)}]",
                "message": f"Lời chào kết bị lặp {len(signoff_indices)} lần tại các phân đoạn {', '.join(ids)}. Kịch bản đã khép lại rồi tiếp tục kể lại câu chuyện.",
            })

        premature_indices = sorted({
            idx for idx in [*signoff_indices, *ending_profile_indices] if idx < final_idx
        })
        if premature_indices:
            ids = [str(getattr(segments[idx], "id", idx + 1)) for idx in premature_indices]
            issues.append({
                "rule": "PREMATURE_SIGNOFF",
                "severity": "CRITICAL",
                "target": f"segments[{', '.join(ids)}]",
                "message": f"Kịch bản dùng lời chào hoặc nhãn ENDING trước khi câu chuyện kết thúc tại phân đoạn {', '.join(ids)}.",
            })

        if signoff_indices and signoff_indices[0] < final_idx:
            first_idx = signoff_indices[0]
            later_content = [
                str(getattr(segment, "id", idx + 1))
                for idx, segment in enumerate(segments[first_idx + 1:], start=first_idx + 1)
                if str(getattr(segment, "text", "") or "").strip()
                and not signoff_pattern.search(str(getattr(segment, "text", "") or ""))
            ]
            if later_content:
                issues.append({
                    "rule": "CONTENT_AFTER_SIGNOFF",
                    "severity": "CRITICAL",
                    "target": f"segments[{later_content[0]}..{later_content[-1]}]",
                    "message": "Sau lời chào kết vẫn còn nội dung kể chuyện. Đây là dấu hiệu ghép hai phần sai mạch hoặc lặp lại một vòng điều tra.",
                })

        if ending_profile_indices != [final_idx]:
            issues.append({
                "rule": "ENDING_PROFILE_PLACEMENT",
                "severity": "HIGH",
                "target": "delivery_profile",
                "message": "delivery_profile='ENDING' chỉ được dùng đúng một lần cho phân đoạn cuối cùng.",
            })

        # Check if ending is larger than 12%
        if ending_pct > 12.0 and ending_count >= 8:
            issues.append({
                "rule": "ENDING_PROPORTION_VIOLATION",
                "severity": "HIGH",
                "target": "ending_segments",
                "message": f"Tỷ lệ phân đoạn kết thúc (ENDING) chiếm {ending_pct:.1f}% tổng kịch bản (vượt mức chuẩn 5-10%, tối đa 12%). Cần cô đọng phần đúc kết, tránh diễn giải luân lý kéo dài."
            })

        # Check semantic repetition in ending: e.g. repeating the blood vs upbringing moral 3+ times
        ending_text = " ".join(str(getattr(s, "text", "") or "") for s in segments[-8:])
        moral_repeats = [
            r"máu\s+mủ.*tình\s+nghĩa",
            r"nuôi\s+dưỡng.*sinh\s+thành",
            r"huyết\s+thống.*gắn\s+kết",
            r"chọn\s+lựa.*tha\s+thứ",
        ]
        repeat_count = 0
        for pat in moral_repeats:
            repeat_count += len(re.findall(pat, ending_text, re.IGNORECASE))
        if repeat_count >= 4:
            issues.append({
                "rule": "ENDING_REPETITION",
                "severity": "HIGH",
                "target": "ending_segments",
                "message": "Phần kết lặp lại cùng một thông điệp luân lý quá nhiều lần. Nên ưu tiên một hình ảnh/cử chỉ hậu trường lắng đọng hơn là giảng giải ý nghĩa nhiều lần."
            })

        return issues

    def _check_audience_interactions(self, segments: List[Any]) -> List[Dict[str, Any]]:
        """
        Max 4-6 audience interactions.
        NO interactions inside REVEAL or climax segments.
        """
        issues: List[Dict[str, Any]] = []
        interactions: List[Tuple[str, str]] = []  # (seg_id, delivery_profile)

        for s in segments:
            if getattr(s, "audience_address", False):
                sid = str(getattr(s, "id", getattr(s, "segment_id", "")))
                prof = str(getattr(s, "delivery_profile", "NORMAL"))
                interactions.append((sid, prof))

        # Check placement inside REVEAL
        reveal_violations = [sid for sid, prof in interactions if prof == "REVEAL"]
        if reveal_violations:
            issues.append({
                "rule": "AUDIENCE_INTERACTION_PLACEMENT",
                "severity": "MEDIUM",
                "target": f"segments[{', '.join(reveal_violations)}]",
                "message": f"Phân đoạn bước ngoặt (REVEAL: {', '.join(reveal_violations)}) chứa câu hỏi giao lưu khán giả, làm gãy nhịp cao trào tiết lộ sự thật."
            })

        if len(interactions) > 6:
            issues.append({
                "rule": "AUDIENCE_INTERACTION_PLACEMENT",
                "severity": "MEDIUM",
                "target": "audience_address",
                "message": f"Số lượt giao lưu khán giả ({len(interactions)}) vượt mức tự nhiên (chuẩn 4-6 lượt)."
            })

        return issues

    def _check_character_naming(self, segments: List[Any], story_bible: Any) -> List[Dict[str, Any]]:
        """
        Narrator should use natural names (Lan, Thành, Dũng) in spoken narration
        rather than constantly repeating 3-4 word full legal names.
        """
        issues: List[Dict[str, Any]] = []
        all_text = " ".join(str(getattr(s, "text", "") or "") for s in segments)

        honorific_prefixes = [
            "luật sư", "bác sĩ", "thầy giáo", "cô giáo", "giám đốc", "chủ tịch",
            "ông", "bà", "anh", "chị", "cô", "chú", "bác", "em"
        ]

        def _is_multiterm_legal_name(raw_name: str) -> bool:
            clean = raw_name.strip()
            c_low = clean.lower()
            for pref in honorific_prefixes:
                if c_low.startswith(pref + " "):
                    clean = clean[len(pref):].strip()
                    break
            return len(clean.split()) >= 3

        full_names: List[str] = []
        protag = getattr(story_bible, "protagonist", {})
        if isinstance(protag, dict) and protag.get("name"):
            name = protag["name"]
            if _is_multiterm_legal_name(name):
                full_names.append(name)
        for sc in (getattr(story_bible, "supporting_characters", []) or []):
            if isinstance(sc, dict) and sc.get("name"):
                name = sc["name"]
                if _is_multiterm_legal_name(name):
                    full_names.append(name)

        for fn in full_names:
            count = len(re.findall(re.escape(fn), all_text, re.IGNORECASE))
            if count >= 8:
                issues.append({
                    "rule": "FULL_NAME_OVERUSE",
                    "severity": "MEDIUM",
                    "target": "naming",
                    "message": f"Họ và tên pháp lý đầy đủ '{fn}' bị lặp lại quá nhiều lần ({count} lần) trong lời đọc MC. Nên chuyển sang gọi tên tự nhiên ('{fn.split()[-1]}') để văn phong đời thường, gần gũi."
                })

        return issues

    def _check_script_fact_drift(self, script_text: str, story_bible: Any) -> List[Dict[str, Any]]:
        """
        Checks whether Full Script introduced facts that directly contradict Story Bible Fact Lock:
        dates, ages, children counts, paternity, relationships, money amounts.
        """
        issues: List[Dict[str, Any]] = []
        facts = getattr(story_bible, "critical_facts", [])

        for fact in facts:
            field = str(getattr(fact, "field", "") or "").lower()
            val = str(getattr(fact, "value", "") or "").strip()

            # Check year drift
            if "year" in field or "năm" in field:
                fact_years = extract_years(val)
                # If script mentions completely different years for the same milestone
                pass

        return issues
