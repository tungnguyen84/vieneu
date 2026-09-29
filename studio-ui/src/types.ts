export type StageId =
  | '01_idea'
  | '02_story'
  | '03_script'
  | '04_audio'
  | '05_visual'
  | '06_flow'
  | '07_assets'
  | '08_timeline'
  | '09_render'
  | '10_qc';

export type StageStatus =
  | 'NOT_STARTED'
  | 'IN_PROGRESS'
  | 'NEEDS_REVIEW'
  | 'APPROVED'
  | 'COMPLETE'
  | 'STALE'
  | 'FAILED';

export interface NextAction {
  stage_id: StageId;
  title: string;
  description: string;
  action_type: string;
  button_label: string;
  target_route: string;
}

export interface ProjectMetadata {
  project_id: string;
  title: string;
  series_id: string;
  episode_number: string;
  created_at: number;
  updated_at: number;
  duration_sec: number;
  scene_count: number;
  image_count: number;
  video_count: number;
  stage_statuses: Record<string, StageStatus>;
  next_action?: NextAction;
  is_archived: boolean;
}

export interface ScriptSegment {
  segment_id: string;
  speaker: string;
  delivery_profile: string;
  text: string;
  story_function: string;
  estimated_duration_sec: number;
  qc_flags: string[];
}

export interface StoryBibleSection {
  premise: string;
  characters_summary: string;
  relationships: string;
  timeline_summary: string;
  mystery_core: string;
  reveal_1: string;
  reveal_2: string;
  emotional_payoff: string;
  fact_lock_items: string[];
}

export interface CharacterItem {
  character_id: string;
  name: string;
  identity_family_id?: string;
  identity_role?: string;
  depends_on_reference?: string;
  use_identity_anchor: boolean;
  age?: number;
  appearance_description: string;
  reference_required: boolean;
  reference_status: string;
  reference_image_url?: string;
  scene_appearances_count: number;
}

export interface PropItem {
  prop_id: string;
  name: string;
  continuity_critical: boolean;
  reference_required: boolean;
  reference_status: string;
  depends_on_characters: string[];
}

export interface LocationItem {
  location_id: string;
  name: string;
  city_region: string;
  description: string;
  scenes_count: number;
}

export interface SceneItem {
  scene_id: string;
  order: number;
  start_time: number;
  end_time: number;
  duration: number;
  visual_mode: 'IMAGE_ONLY' | 'VIDEO_RECOMMENDED';
  video_recommended: boolean;
  video_value_score: number;
  narration_summary: string;
  image_prompt: string;
  video_prompt?: string;
  visible_characters: string[];
  location_id?: string;
  props: string[];
  overlay_text?: string;
  motion_type: string;
}

export interface AssetSceneItem {
  scene_id: string;
  order: number;
  duration: number;
  visual_mode: string;
  video_recommended: boolean;
  has_image: boolean;
  image_path?: string;
  has_video: boolean;
  video_path?: string;
  is_fallback: boolean;
  video_value_score: number;
  status: string;
}

export interface FinalQCReport {
  overall_status: 'PASS' | 'WARNING' | 'FAIL';
  duration_sec: number;
  resolution: string;
  fps: number;
  video_codec: string;
  audio_codec: string;
  av_sync_delta_ms: number;
  black_gap_detected: boolean;
  missing_scenes_count: number;
  static_hold_exceeded: boolean;
  integrated_loudness_lufs: number;
  true_peak_db: number;
  checks_summary: Array<{
    id: string;
    name: string;
    value: string;
    status: string;
    required: string;
  }>;
}
