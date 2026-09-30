"""Data models for Sau Cánh Cửa Studio Desktop Production Pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StageId(str, Enum):
    IDEA = "01_idea"
    STORY = "02_story"
    SCRIPT = "03_script"
    AUDIO = "04_audio"
    VISUAL = "05_visual"
    FLOW = "06_flow"
    ASSETS = "07_assets"
    TIMELINE = "08_timeline"
    RENDER = "09_render"
    QC = "10_qc"


class StageStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    COMPLETE = "COMPLETE"
    STALE = "STALE"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NextAction(BaseModel):
    stage_id: StageId
    title: str
    description: str
    action_type: str
    button_label: str
    target_route: str


class ProjectMetadata(BaseModel):
    project_id: str
    title: str
    series_id: str = "SAU_CANH_CUA"
    episode_number: str = "EP003"
    created_at: float
    updated_at: float
    duration_sec: float = 0.0
    scene_count: int = 45
    image_count: int = 38
    video_count: int = 7
    stage_statuses: Dict[str, StageStatus] = Field(default_factory=dict)
    next_action: Optional[NextAction] = None
    is_archived: bool = False
    topic: Optional[str] = None
    selected_idea: Optional[Dict[str, Any]] = None


class ScriptSegment(BaseModel):
    segment_id: str
    speaker: str = "NARRATOR"
    delivery_profile: str = "SUSPENSE_COLD"
    text: str
    story_function: str = "SETUP"
    speed: float = 1.0
    pause_before: float = 0.0
    pause_after: float = 0.25
    estimated_duration_sec: float = 0.0
    qc_flags: List[str] = Field(default_factory=list)


class StoryBibleSection(BaseModel):
    premise: str = ""
    characters_summary: str = ""
    relationships: str = ""
    timeline_summary: str = ""
    mystery_core: str = ""
    reveal_1: str = ""
    reveal_2: str = ""
    emotional_payoff: str = ""
    fact_lock_items: List[str] = Field(default_factory=list)
    has_story_bible: bool = False
    selected_idea: Optional[Dict[str, Any]] = None
    clues: List[str] = Field(default_factory=list)
    reflection_theme: str = ""
    title: str = ""


class CharacterItem(BaseModel):
    character_id: str
    name: str
    identity_family_id: Optional[str] = None
    identity_role: Optional[str] = None
    depends_on_reference: Optional[str] = None
    use_identity_anchor: bool = False
    age: Optional[int] = None
    appearance_description: str = ""
    reference_required: bool = True
    reference_status: str = "NOT_GENERATED"
    reference_image_url: Optional[str] = None
    scene_appearances_count: int = 0


class PropItem(BaseModel):
    prop_id: str
    name: str
    continuity_critical: bool = True
    reference_required: bool = False
    reference_status: str = "NOT_REQUIRED"
    reference_image_url: Optional[str] = None
    depends_on_characters: List[str] = Field(default_factory=list)


class LocationItem(BaseModel):
    location_id: str
    name: str
    city_region: str = ""
    description: str = ""
    reference_image_url: Optional[str] = None
    scenes_count: int = 0


class SceneItem(BaseModel):
    scene_id: str
    order: int
    start_time: float
    end_time: float
    duration: float
    visual_mode: str = "IMAGE_ONLY"  # IMAGE_ONLY or VIDEO_RECOMMENDED
    video_recommended: bool = False
    video_value_score: int = 0
    narration_summary: str = ""
    image_prompt: str = ""
    video_prompt: Optional[str] = None
    visible_characters: List[str] = Field(default_factory=list)
    location_id: Optional[str] = None
    props: List[str] = Field(default_factory=list)
    overlay_text: Optional[str] = None
    asset_image_path: Optional[str] = None
    asset_video_path: Optional[str] = None
    is_video_fallback: bool = False
    motion_type: str = "KEN_BURNS_SLOW_PAN"


class JobItem(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    step_label: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    logs: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class FinalQCReport(BaseModel):
    overall_status: str = "PASS"  # PASS, WARNING, FAIL
    duration_sec: float = 0.0
    resolution: str = "1920x1080"
    fps: int = 30
    video_codec: str = "h264"
    audio_codec: str = "aac"
    av_sync_delta_ms: float = 0.0
    black_gap_detected: bool = False
    missing_scenes_count: int = 0
    static_hold_exceeded: bool = False
    integrated_loudness_lufs: float = -16.0
    true_peak_db: float = -1.0
    checks_summary: List[Dict[str, Any]] = Field(default_factory=list)
