export type AdaptationMode = 'FACTUAL_RETELLING' | 'FICTION_FROM_THEME' | 'IMPROVE_OWN_SCRIPT';
export interface SourceUnit { unit_id: string; text: string; start_sec?: number; end_sec?: number }
export interface SourceDocument {
  source_id: string; title: string; text: string; revision: number; status: string;
  source_type: string; content_hash: string; word_count: number; input_url?: string;
  resolved_url?: string; author_or_channel?: string; published_at?: string;
  caption_kind?: string; extraction_method: string; limitations: string[]; units: SourceUnit[];
}
export interface Direction {
  direction_id: string; title: string; hook: string; point_of_view: string; want: string;
  conflict: string; hard_choice: string; development: string; ending: string; source_fit: string;
}
export interface SourceConfig {
  adaptation_mode: AdaptationMode; topic: string; narrative_style: string; target_duration_sec: number;
  locked_elements: string[]; allowed_changes: string; owned_script_confirmed: boolean;
}
export interface Directions { generation_request_id: string; source_id: string; source_hash: string; config: SourceConfig; directions: Direction[] }
export interface Brief extends SourceConfig { status: string; source_id: string; selected_direction_id: string; direction: Direction }
export interface SourceJob { job_id: string; status: string; step_label: string; action: string; error?: string; result?: unknown }
export interface SourceState { sources: SourceDocument[]; brief?: Brief; directions?: Directions; jobs: SourceJob[] }

export async function sourceRequest<T>(projectId: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Không thực hiện được bước này');
  return data;
}

export async function waitSourceJob(projectId: string, job: SourceJob, onStatus?: (s: string) => void): Promise<unknown> {
  let current = job;
  while (current.status === 'RUNNING') {
    onStatus?.(current.step_label);
    await new Promise(resolve => setTimeout(resolve, 1500));
    current = await sourceRequest<SourceJob>(projectId, `/adaptation/jobs/${job.job_id}`);
  }
  if (current.status !== 'COMPLETED') throw new Error(current.error || 'Tác vụ chưa hoàn tất');
  return current.result;
}

// Existing Story/Script views keep their API contract, while source generations
// use persisted jobs and can be resumed from the Sources workspace after reload.
export async function generateWithSource(projectId: string, stage: 'story' | 'script' | 'story-review' | 'script-repair', options: RequestInit): Promise<Response> {
  const state = await sourceRequest<SourceState>(projectId, '/sources');
  const legacyPath = stage === 'story-review' ? 'story/repair' : stage === 'script-repair' ? 'script/repair' : `${stage}/generate`;
  if (!state.brief?.source_id) return fetch(`/api/projects/${projectId}/${legacyPath}`, options);
  try {
    const job = await sourceRequest<SourceJob>(projectId, `/adaptation/generate/${stage}`, JSON.parse(String(options.body || '{}')));
    const data = await waitSourceJob(projectId, job);
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
  } catch (e) {
    return new Response(JSON.stringify({ detail: e instanceof Error ? e.message : 'Lỗi tạo nội dung từ nguồn' }), { status: 400 });
  }
}
