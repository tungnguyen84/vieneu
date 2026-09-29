"""FastAPI Application Server for Sau Cánh Cửa Studio."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from studio.backend.models import (
    CharacterItem,
    FinalQCReport,
    NextAction,
    ProjectMetadata,
    SceneItem,
    ScriptSegment,
    StageId,
    StageStatus,
    StoryBibleSection,
)
from studio.backend.credentials import (
    delete_provider_credentials,
    get_public_providers_status,
    save_provider_credentials,
    test_provider_connection,
)
from studio.backend.db import get_db_connection
from studio.backend.project_manager import ProjectManager
from studio.backend.services.asset_service import AssetService
from studio.backend.services.audio_service import AudioService
from studio.backend.services.flow_service import FlowService
from studio.backend.services.generation_service import GenerationService
from studio.backend.services.job_service import JobService
from studio.backend.services.qc_service import QCService
from studio.backend.services.render_service import RenderService
from studio.backend.services.script_service import ScriptService
from studio.backend.services.timeline_service import TimelineService
from studio.backend.services.visual_service import VisualService

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DIST_DIR = BASE_DIR / "studio-ui" / "dist"

app = FastAPI(title="Sau Cánh Cửa Studio API", version="1.0.0")

# Enable CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service Singletons
pm = ProjectManager()
script_srv = ScriptService()
audio_srv = AudioService()
visual_srv = VisualService()
flow_srv = FlowService()
asset_srv = AssetService()
timeline_srv = TimelineService()
render_srv = RenderService()
qc_srv = QCService()
job_srv = JobService()
gen_srv = GenerationService()


# ---------------- AI PROVIDER CREDENTIALS ----------------
@app.get("/api/ai/providers")
def get_providers_status():
    return get_public_providers_status()


class SaveProviderRequest(BaseModel):
    provider: str
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None


@app.post("/api/ai/save")
def save_provider(req: SaveProviderRequest):
    return save_provider_credentials(
        provider=req.provider,
        api_key=req.api_key,
        model=req.model,
        base_url=req.base_url
    )


class DeleteProviderRequest(BaseModel):
    provider: str


@app.post("/api/ai/delete")
def delete_provider(req: DeleteProviderRequest):
    return delete_provider_credentials(req.provider)


class TestProviderRequest(BaseModel):
    provider: str
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


@app.post("/api/ai/test")
def test_provider(req: TestProviderRequest):
    return test_provider_connection(
        provider=req.provider,
        api_key=req.api_key,
        model=req.model,
        base_url=req.base_url
    )


# ---------------- PROJECT ENDPOINTS ----------------
@app.get("/api/projects/next-id")
def get_next_id():
    return {"episode_id": pm.get_next_available_episode_id()}


class CreateProjectRequest(BaseModel):
    episode_id: Optional[str] = None
    title: str
    premise: Optional[str] = ""
    target_duration: Optional[int] = 1200
    category: Optional[str] = "Gia đình / Bí ẩn"


@app.post("/api/projects/create", response_model=ProjectMetadata)
def create_new_project(req: CreateProjectRequest):
    ep_id = req.episode_id or pm.get_next_available_episode_id()
    return pm.create_project(
        episode_id=ep_id,
        title=req.title,
        premise=req.premise or "",
        target_duration=req.target_duration or 1200,
        category=req.category or "Gia đình / Bí ẩn"
    )


@app.get("/api/projects", response_model=List[ProjectMetadata])
def list_projects():
    return pm.list_projects()


@app.get("/api/projects/{project_id}", response_model=ProjectMetadata)
def get_project(project_id: str):
    p = pm.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


class StageUpdateRequest(BaseModel):
    stage_id: StageId
    status: StageStatus


@app.post("/api/projects/{project_id}/stage", response_model=ProjectMetadata)
def update_stage(project_id: str, req: StageUpdateRequest):
    return pm.update_stage_status(project_id, req.stage_id, req.status)


@app.post("/api/projects/{project_id}/archive")
def export_archive(project_id: str, full: bool = False):
    zip_path = pm.export_archive(project_id, full=full)
    return {"archive_path": str(zip_path.relative_to(BASE_DIR)), "file_name": zip_path.name}


# ---------------- IDEAS ENDPOINTS ----------------
class GenerateIdeasRequest(BaseModel):
    direction: Optional[str] = ""
    count: Optional[int] = 5


@app.post("/api/projects/{project_id}/ideas/generate")
def generate_project_ideas(project_id: str, req: GenerateIdeasRequest):
    try:
        ideas = gen_srv.generate_ideas(project_id, count=req.count or 5, direction=req.direction or "")
        return {"ideas": ideas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SelectIdeaRequest(BaseModel):
    idea: Dict[str, Any]


@app.post("/api/projects/{project_id}/ideas/select")
def select_project_idea(project_id: str, req: SelectIdeaRequest):
    p = pm.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    selected = req.idea
    premise = selected.get("premise") or selected.get("hook") or ""
    title = selected.get("title")

    proj_dir = BASE_DIR / "projects" / project_id
    story_dir = proj_dir / "story"
    story_dir.mkdir(parents=True, exist_ok=True)
    with open(story_dir / "premise.txt", "w", encoding="utf-8") as f:
        f.write(f"Tiêu đề: {title}\nÝ tưởng: {premise}\nBí ẩn: {selected.get('core_mystery', '')}\nLật mở: {selected.get('possible_reveal', '')}\n")

    p_json = proj_dir / "project.json"
    if p_json.exists():
        with open(p_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        if title:
            data["title"] = title
        data["topic"] = premise
        with open(p_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    if title:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE projects SET title = ? WHERE project_id = ?", (title, project_id))
            conn.commit()

    return pm.update_stage_status(project_id, StageId.IDEA, StageStatus.APPROVED)



# ---------------- SCRIPT & STORY ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/story", response_model=StoryBibleSection)
def get_story(project_id: str):
    return script_srv.get_story_bible(project_id)


class GenerateStoryRequest(BaseModel):
    topic: Optional[str] = ""


@app.post("/api/projects/{project_id}/story/generate")
def generate_project_story(project_id: str, req: GenerateStoryRequest):
    try:
        res = gen_srv.generate_story_bible(project_id, topic=req.topic or "")
        pm.update_stage_status(project_id, StageId.STORY, StageStatus.NEEDS_REVIEW)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/story/approve")
def approve_project_story(project_id: str):
    return pm.update_stage_status(project_id, StageId.STORY, StageStatus.APPROVED)


@app.get("/api/projects/{project_id}/script", response_model=List[ScriptSegment])
def get_script(project_id: str):
    return script_srv.get_script_segments(project_id)


@app.get("/api/projects/{project_id}/script/full")
def get_script_full(project_id: str):
    return {"text": script_srv.get_full_script_text(project_id)}


class GenerateScriptRequest(BaseModel):
    force: Optional[bool] = False


@app.post("/api/projects/{project_id}/script/generate")
def generate_project_script(project_id: str, req: GenerateScriptRequest):
    try:
        p = pm.get_project(project_id)
        if not p:
            raise HTTPException(status_code=404, detail="Project not found")

        story_status = p.stage_statuses.get(StageId.STORY.value) or p.stage_statuses.get("02_story")
        if not req.force and story_status != StageStatus.APPROVED:
            bible_path = BASE_DIR / "projects" / project_id / "story" / "story_bible.json"
            if not bible_path.exists():
                raise HTTPException(status_code=400, detail="Story Bible chưa được duyệt hoặc chưa tồn tại. Vui lòng duyệt Story Bible trước khi tạo kịch bản!")

        res = gen_srv.generate_full_script(project_id)
        pm.update_stage_status(project_id, StageId.SCRIPT, StageStatus.NEEDS_REVIEW)
        return res
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/script/repair")
def repair_project_script(project_id: str):
    try:
        res = gen_srv.auto_repair_script(project_id)
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/projects/{project_id}/script/approve")
def approve_project_script(project_id: str):
    return pm.update_stage_status(project_id, StageId.SCRIPT, StageStatus.APPROVED)


@app.get("/api/projects/{project_id}/script/qc")
def get_script_qc_report(project_id: str):
    report = script_srv.get_script_qc(project_id)
    if not report:
        raise HTTPException(status_code=404, detail="QC report not found")
    return report


class ImportScriptTextRequest(BaseModel):
    text: str


@app.post("/api/projects/{project_id}/script/import-text")
def import_script_text(project_id: str, req: ImportScriptTextRequest):
    segs = script_srv.import_script_text(project_id, req.text)
    pm.update_stage_status(project_id, StageId.SCRIPT, StageStatus.NEEDS_REVIEW)
    return {"segments": segs, "count": len(segs)}


class UpdateSegmentRequest(BaseModel):
    segment_id: str
    text: str


@app.post("/api/projects/{project_id}/script/segment", response_model=ScriptSegment)
def update_script_segment(project_id: str, req: UpdateSegmentRequest):
    return script_srv.update_segment(project_id, req.segment_id, req.text)



# ---------------- AUDIO ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/audio")
def get_audio_info(project_id: str):
    return audio_srv.get_audio_info(project_id)


@app.get("/api/projects/{project_id}/audio/stream")
def stream_audio(project_id: str):
    p = audio_srv.get_audio_master_path(project_id)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="Audio master not found")
    media_type = "audio/wav" if p.suffix.lower() == ".wav" else "audio/mpeg"
    return FileResponse(path=str(p), media_type=media_type)


@app.post("/api/projects/{project_id}/audio/import")
def import_audio(project_id: str, file_path: str = Form(...)):
    return audio_srv.import_audio_file(project_id, file_path)


# ---------------- VISUAL PLAN ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/visual/scenes", response_model=List[SceneItem])
def get_scenes(project_id: str):
    return visual_srv.get_scenes(project_id)


@app.get("/api/projects/{project_id}/visual/characters", response_model=List[CharacterItem])
def get_characters(project_id: str):
    return visual_srv.get_characters(project_id)


@app.get("/api/projects/{project_id}/visual/identity-families")
def get_identity_families(project_id: str):
    return visual_srv.get_identity_families(project_id)


@app.get("/api/projects/{project_id}/visual/props")
def get_props(project_id: str):
    return visual_srv.get_props(project_id)


@app.get("/api/projects/{project_id}/visual/locations")
def get_locations(project_id: str):
    return visual_srv.get_locations(project_id)


class ToggleModeRequest(BaseModel):
    mode: str  # IMAGE_ONLY or VIDEO_RECOMMENDED


@app.post("/api/projects/{project_id}/visual/scenes/{scene_id}/mode", response_model=SceneItem)
def toggle_scene_mode(project_id: str, scene_id: str, req: ToggleModeRequest):
    return visual_srv.toggle_scene_mode(project_id, scene_id, req.mode)


# ---------------- GOOGLE FLOW ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/flow")
def get_flow_info(project_id: str):
    return flow_srv.get_export_info(project_id)


@app.post("/api/projects/{project_id}/flow/export")
def run_flow_export(project_id: str):
    res = flow_srv.run_export(project_id)
    pm.update_stage_status(project_id, StageId.FLOW, StageStatus.APPROVED)
    return res


# ---------------- ASSET ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/assets")
def get_assets(project_id: str):
    return asset_srv.get_assets_manifest(project_id)


class FallbackRequest(BaseModel):
    scene_id: str
    fallback: bool


@app.post("/api/projects/{project_id}/assets/fallback")
def set_fallback(project_id: str, req: FallbackRequest):
    fallbacks = asset_srv.set_scene_fallback(project_id, req.scene_id, req.fallback)
    return {"fallbacks": fallbacks}


@app.post("/api/projects/{project_id}/assets/import-zip")
def import_zip(project_id: str, zip_path: str = Form(...)):
    res = asset_srv.import_production_zip(project_id, zip_path)
    pm.update_stage_status(project_id, StageId.ASSETS, StageStatus.APPROVED)
    return res


# ---------------- TIMELINE ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/timeline")
def get_timeline(project_id: str):
    return timeline_srv.get_timeline_tracks(project_id)


# ---------------- RENDER & QC ENDPOINTS ----------------
@app.get("/api/projects/{project_id}/render")
def get_render_status(project_id: str):
    return render_srv.get_render_status(project_id)


@app.post("/api/projects/{project_id}/render/start")
def start_render(project_id: str):
    rid = render_srv.start_render(project_id)
    return {"render_id": rid, "status": "STARTED"}


@app.post("/api/projects/{project_id}/render/cancel")
def cancel_render(project_id: str):
    success = render_srv.cancel_render(project_id)
    return {"cancelled": success}


@app.get("/api/projects/{project_id}/qc", response_model=FinalQCReport)
def get_qc(project_id: str):
    return qc_srv.get_qc_report(project_id)


# ---------------- JOBS & SYSTEM ----------------
@app.get("/api/jobs")
def list_jobs(project_id: Optional[str] = None):
    return job_srv.list_jobs(project_id)


@app.get("/api/system/status")
def get_system_status():
    disk = shutil.disk_usage(str(BASE_DIR))
    free_gb = round(disk.free / (1024**3), 1)
    ffmpeg_path = shutil.which("ffmpeg") or "C:\\Users\\TPT\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-9.0-full_build\\bin\\ffmpeg.EXE"
    return {
        "ffmpeg_available": bool(ffmpeg_path and os.path.exists(ffmpeg_path)),
        "ffmpeg_path": ffmpeg_path,
        "free_disk_gb": free_gb,
        "active_jobs_count": 0,
        "studio_version": "1.0.0"
    }


# ---------------- STATIC UI MOUNT ----------------
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="static")
