"""Data Models for VieNeu Script Factory V1."""
from __future__ import annotations

import time
from dataclasses import fields, asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ApprovalStatus(str, Enum):
    DRAFT = "DRAFT"
    QC_RUNNING = "QC_RUNNING"
    NEEDS_REVISION = "NEEDS_REVISION"
    QC_PASS = "QC_PASS"
    APPROVED = "APPROVED"
    PRODUCTION_READY = "PRODUCTION_READY"
    BLOCKED_DUPLICATE = "BLOCKED_DUPLICATE"
    USER_REVIEW_REQUIRED = "USER_REVIEW_REQUIRED"
    AWAITING_USER_REVIEW = "AWAITING_USER_REVIEW"
    STORY_BIBLE_CHANGED = "STORY_BIBLE_CHANGED"
    # Script Factory V1.2 Status Pipeline
    NEEDS_NOVELTY_REWRITE = "NEEDS_NOVELTY_REWRITE"
    NEEDS_LOGIC_REWRITE = "NEEDS_LOGIC_REWRITE"
    NEEDS_GENRE_REWRITE = "NEEDS_GENRE_REWRITE"
    BLOCKED_NARRATIVE_DUPLICATE = "BLOCKED_NARRATIVE_DUPLICATE"
    BLOCKED_IMPLAUSIBLE = "BLOCKED_IMPLAUSIBLE"
    USER_APPROVED = "USER_APPROVED"
    USER_REJECTED = "USER_REJECTED"
    # Full Script Pilot 02 Statuses
    AWAITING_USER_SCRIPT_REVIEW = "AWAITING_USER_SCRIPT_REVIEW"
    NEEDS_HUMAN_SCRIPT_FIX = "NEEDS_HUMAN_SCRIPT_FIX"


class DeliveryProfile(str, Enum):
    HOOK = "HOOK"
    NORMAL = "NORMAL"
    MYSTERY = "MYSTERY"
    REVEAL = "REVEAL"
    COMMENT = "COMMENT"
    ENDING = "ENDING"


@dataclass
class NarrativeSkeleton:
    trigger: str = ""
    initial_suspicion: str = ""
    investigation_method: str = ""
    evidence_chain: List[str] = field(default_factory=list)
    reveal_mechanism: str = ""
    second_reveal_mechanism: str = ""
    emotional_resolution: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> NarrativeSkeleton:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class LockedFact:
    fact_id: str
    field: str
    value: str
    description: str = ""
    status: str = "LOCKED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LockedFact:
        return cls(**data)


@dataclass
class IdeaItem:
    idea_id: str
    working_title: str
    hook: str
    protagonist: str
    relationship: str
    central_secret: str
    mystery_question: str
    false_lead: str
    clue_1: str
    clue_2: str
    clue_3: str
    reveal_1: str
    reveal_2: str
    emotional_payoff: str
    reflection_theme: str
    hook_archetype: str
    twist_archetype: str
    estimated_strength: Optional[float] = None
    status: str = "DRAFT"
    novelty_score: Optional[float] = None
    premise_similarity: Optional[float] = None
    twist_similarity: Optional[float] = None
    hook_similarity: Optional[float] = None
    closest_episode: str = ""
    curiosity: Optional[float] = None
    emotional_potential: Optional[float] = None
    mystery_potential: Optional[float] = None
    logical_plausibility: Optional[float] = None
    long_form_potential: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    # V1.2 Story Quality Hardening Fields
    narrative_skeleton: Optional[Dict[str, Any]] = None
    narrative_skeleton_similarity: Optional[float] = None
    plausibility_score: Optional[float] = None
    plausibility_issues: List[str] = field(default_factory=list)
    required_explanations: List[str] = field(default_factory=list)
    skeptical_viewer_questions: List[str] = field(default_factory=list)
    logic_issues: List[str] = field(default_factory=list)
    clues_causality: List[Dict[str, Any]] = field(default_factory=list)
    reveal_qc: Dict[str, float] = field(default_factory=dict)
    false_lead_strength: Optional[float] = None
    coincidence_count: int = 0
    genre_fit_score: Optional[float] = None
    vietnamese_social_fit_score: Optional[float] = None
    emotional_device: str = ""
    has_death_or_tragedy: bool = False
    title_strength: Optional[float] = None
    title_specificity: Optional[float] = None
    title_curiosity_gap: Optional[float] = None
    locked_fields: List[str] = field(default_factory=list)
    selected_for_pilot: bool = False
    original_user_topic: Optional[str] = None
    topic_intent: Optional[Dict[str, Any]] = None
    topic_adherence_score: Optional[float] = None
    generation_request_id: Optional[str] = None
    prompt_version: Optional[str] = None
    generation_source: Optional[str] = None
    model_name: Optional[str] = None
    provider_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IdeaItem:
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class StoryBible:
    episode_id: str
    title: str
    protagonist: Dict[str, Any]
    supporting_characters: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    timeline: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    money_facts: List[Dict[str, Any]] = field(default_factory=list)
    critical_facts: List[LockedFact] = field(default_factory=list)
    secret: str = ""
    false_lead: str = ""
    clues: List[str] = field(default_factory=list)
    reveal_1: str = ""
    reveal_2: str = ""
    emotional_payoff: str = ""
    reflection_theme: str = ""
    ending: str = ""
    source_idea_id: str = ""
    time_period: str = ""
    mystery_question: str = ""
    narrative_skeleton: Optional[Dict[str, Any]] = None
    public_episode_number: Optional[int] = None
    causal_chains: List[Dict[str, Any]] = field(default_factory=list)
    knowledge_ledger: List[Dict[str, Any]] = field(default_factory=list)
    structured_clues: List[Dict[str, Any]] = field(default_factory=list)
    reveal_justifications: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    reveal_proofs: List[Dict[str, Any]] = field(default_factory=list)
    story_qc_report: Optional[Dict[str, Any]] = None
    original_user_topic: Optional[str] = None
    topic_intent: Optional[Dict[str, Any]] = None
    topic_adherence: Optional[Dict[str, Any] | float] = None
    status: str = "DRAFT"
    generation_source: Optional[str] = None
    generation_request_id: Optional[str] = None
    prompt_version: Optional[str] = None
    model_name: Optional[str] = None
    provider_name: Optional[str] = None
    generated_at: Optional[float] = None
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    last_modified_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["critical_facts"] = [f.to_dict() if isinstance(f, LockedFact) else f for f in self.critical_facts]
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StoryBible:
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        facts = [LockedFact.from_dict(f) if isinstance(f, dict) else f for f in data.get("critical_facts", [])]
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        filtered["critical_facts"] = facts
        if not filtered.get("secret") and data.get("premise"):
            filtered["secret"] = data.get("premise", "")
        return cls(**filtered)



# Identity and lineage stay fixed when an AI repair returns a revised Story Bible.
_STORY_BIBLE_PROTECTED_FIELDS = {
    "episode_id", "title", "source_idea_id", "public_episode_number", "original_user_topic",
    "topic_intent", "topic_adherence", "status", "story_qc_report", "generation_source",
    "generation_request_id", "prompt_version", "model_name", "provider_name", "generated_at",
    "approved_by", "approved_at", "last_modified_at",
}


def story_bible_repair_targets_clause(issues: List[Dict[str, Any]]) -> str:
    """Names the flagged Story Bible fields so a repair actually rewrites them.

    Repair prompts list structural fields to complete; without this, models
    return those and leave the flagged field (e.g. ``ending``) untouched.
    """
    known = {f.name for f in fields(StoryBible)} - _STORY_BIBLE_PROTECTED_FIELDS
    targets: List[str] = []
    for issue in issues or []:
        target = str(issue.get("target", "")) if isinstance(issue, dict) else ""
        if target in known and target not in targets:
            targets.append(target)
    # Returning the whole Story Bible is long enough that some models refuse or
    # truncate it ("too large for one message"); a patch of changed fields is
    # short and is applied by ``apply_story_bible_patch``.
    output_rule = (
        "\n\nĐỊNH DẠNG TRẢ VỀ: CHỈ một JSON object chứa các trường bạn đã sửa hoặc bổ sung (dùng đúng tên trường "
        "như Story Bible hiện tại). KHÔNG lặp lại các trường không thay đổi, KHÔNG viết lời giải thích ngoài JSON."
    )
    if not targets:
        return output_rule
    names = ", ".join(targets)
    return (
        f"\n\nTRƯỜNG ĐANG BỊ LỖI CẦN VIẾT LẠI: {names}.\n"
        f"JSON trả về BẮT BUỘC chứa các trường {names} với nội dung ĐÃ SỬA (khác bản hiện tại) để khắc phục đúng "
        "các lỗi nhắm vào chúng; giữ nguyên ý chính và kết cục của câu chuyện."
        + output_rule
    )


def apply_story_bible_patch(bible: "StoryBible", patch: Dict[str, Any]) -> "StoryBible":
    """Applies every plot field an AI repair returned, in place.

    Providers used to copy a hand-picked subset of fields, so a fix to e.g.
    ``ending`` was silently dropped and the same QC issue came back every round.
    Empty values and values whose shape does not match the field are ignored.
    """
    if not isinstance(patch, dict):
        return bible
    for f in fields(bible):
        name = f.name
        if name in _STORY_BIBLE_PROTECTED_FIELDS or name not in patch:
            continue
        value = patch[name]
        if value in (None, "", [], {}):
            continue
        current = getattr(bible, name)
        if name == "critical_facts":
            if not isinstance(value, list):
                continue
            value = [
                LockedFact(
                    fact_id=str(item.get("fact_id") or f"FACT_{index + 1:03d}"),
                    field=str(item.get("field", "fact")),
                    value=str(item.get("value", "")),
                    description=str(item.get("description", "")),
                    status="LOCKED",
                )
                for index, item in enumerate(value)
                if isinstance(item, dict)
            ]
            if not value:
                continue
        elif current not in (None, "", [], {}) and not isinstance(value, type(current)):
            continue
        setattr(bible, name, value)
    return bible

@dataclass
class ScriptSegment:
    id: str
    speaker: str = "MINH"
    text: str = ""
    delivery_profile: str = "NORMAL"
    importance: str = "normal"
    audience_address: bool = False
    speed: float = 1.0
    pause_before: float = 0.05
    pause_after: float = 0.25
    director_note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ScriptSegment:
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


@dataclass
class FullScript:
    episode_id: str
    title: str
    host: Dict[str, Any]
    segments: List[ScriptSegment] = field(default_factory=list)
    total_segments: int = 0
    total_words: int = 0
    status: str = "DRAFT"
    revision_round: int = 0
    generation_source: Optional[str] = None
    generation_request_id: Optional[str] = None
    prompt_version: Optional[str] = None
    model_name: Optional[str] = None
    provider_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["segments"] = [s.to_dict() if isinstance(s, ScriptSegment) else s for s in self.segments]
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FullScript:
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        segs = [ScriptSegment.from_dict(s) if isinstance(s, dict) else s for s in data.get("segments", [])]
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        filtered["segments"] = segs
        return cls(**filtered)



@dataclass
class QCReport:
    episode_id: str
    status: str  # "PASS", "NEEDS_REVISION", "FAIL"
    scores: Dict[str, float] = field(default_factory=dict)
    fact_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    logic_issues: List[str] = field(default_factory=list)
    repetition_issues: List[str] = field(default_factory=list)
    revision_requests: List[str] = field(default_factory=list)
    evidence_issues: List[Dict[str, Any]] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)
    qc_version: Optional[str] = None
    semantic_review: Optional[Dict[str, Any]] = None
    script_content_hash: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QCReport:
        import dataclasses
        valid_keys = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
