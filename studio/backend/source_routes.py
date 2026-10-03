"""Studio source API; jobs use the same provider/generation services as Studio."""
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from typing import Optional, Literal

from apps.script_factory.source_intake import read_text, read_article, read_youtube, youtube_url, MAX_BYTES
from studio.backend.services.source_service import SourceService, current_context
from studio.backend.models import StageId, StageStatus


class IntakeRequest(BaseModel):
    text: str = Field(default='', max_length=100000)
    url: str = Field(default='', max_length=4096)
    language: str = Field(default='vi', pattern=r'^[a-z]{2}(?:-[A-Za-z]{2})?$')


class ConfirmRequest(BaseModel):
    text: str = Field(max_length=100000)
    expected_revision: int = Field(ge=1)


class DirectionsRequest(BaseModel):
    adaptation_mode: Literal['FACTUAL_RETELLING','FICTION_FROM_THEME','IMPROVE_OWN_SCRIPT']
    topic: str = Field(default='', max_length=500)
    narrative_style: str = Field(default='Đời sống', max_length=100)
    target_duration_sec: int = Field(default=1200, ge=60, le=3600)
    locked_elements: list[str] = Field(default_factory=list, max_length=30)
    allowed_changes: str = Field(default='Hook, cách kể, nhịp và cảnh; giữ các phần khóa.', max_length=3000)
    owned_script_confirmed: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None


class SelectRequest(BaseModel):
    direction_id: str
    generation_request_id: str


class GenerateRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None


def make_source_router(projects_dir, gen_srv, pm, job_srv):
    router = APIRouter(prefix='/api/projects/{project_id}')
    service = SourceService(projects_dir, gen_srv.get_provider, job_srv)

    def safe(call):
        try:
            return call()
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get('/sources')
    def state(project_id: str):
        return safe(lambda: service.state(project_id))

    @router.post('/sources')
    def intake(project_id: str, req: IntakeRequest):
        if bool(req.url.strip()) == bool(req.text.strip()):
            raise HTTPException(status_code=400, detail='Nhập một URL hoặc một văn bản.')
        if req.text.strip():
            return safe(lambda: {'source': service.add(project_id, read_text(req.text))})
        return safe(lambda: service.start(project_id, 'Đọc nguồn', req.model_dump(),
                    lambda: service.add(project_id, read_youtube(req.url, req.language) if youtube_url(req.url)
                                        else read_article(req.url), req.url)))

    @router.post('/sources/upload')
    async def upload(project_id: str, file: UploadFile = File(...)):
        body = await file.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise HTTPException(status_code=400, detail='File quá lớn.')
        try:
            text = body.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail='File phải là TXT/SRT/VTT UTF-8.')
        return safe(lambda: {'source': service.add(project_id, read_text(text, file.filename or 'input.txt'))})

    @router.get('/sources/{source_id}')
    def get(project_id: str, source_id: str):
        return safe(lambda: service.get(project_id, source_id))

    @router.post('/sources/{source_id}/confirm')
    def confirm(project_id: str, source_id: str, req: ConfirmRequest):
        return safe(lambda: service.confirm(project_id, source_id, req.text, req.expected_revision))

    @router.post('/sources/{source_id}/directions')
    def directions(project_id: str, source_id: str, req: DirectionsRequest):
        config = req.model_dump(exclude={'provider','model'})
        return safe(lambda: service.start(project_id, 'Phân tích và đề xuất ba hướng',
                    {'source_id':source_id, **req.model_dump()},
                    lambda: service.directions(project_id, source_id, config, req.provider, req.model)))

    @router.post('/adaptation/select')
    def select(project_id: str, req: SelectRequest):
        brief = safe(lambda: service.select(project_id, req.direction_id, req.generation_request_id))
        pm.rename_project(project_id, brief['direction']['title'])
        pm.update_stage_status(project_id, StageId.IDEA, StageStatus.APPROVED)
        return brief

    @router.get('/adaptation/jobs/{job_id}')
    def job(project_id: str, job_id: str):
        return safe(lambda: service.job(project_id, job_id))

    @router.post('/adaptation/generate/{stage}')
    def generate(project_id: str, stage: Literal['story','script','story-review','script-repair'], req: GenerateRequest):
        context = safe(lambda: current_context(service.project(project_id)))
        if not context:
            raise HTTPException(status_code=400, detail='Chưa chọn hướng từ nguồn.')
        if stage == 'script':
            p = pm.get_project(project_id)
            if not p or p.stage_statuses.get(StageId.STORY.value) != StageStatus.APPROVED:
                raise HTTPException(status_code=400, detail='Duyệt cốt truyện trước khi viết kịch bản.')
        def work():
            if stage == 'story':
                result = gen_srv.generate_story_bible(project_id, provider_id=req.provider, model_id=req.model)
                pm.update_stage_status(project_id, StageId.STORY, StageStatus.NEEDS_REVIEW)
            elif stage == 'story-review':
                result = gen_srv.repair_story_bible(project_id, provider_id=req.provider, model_id=req.model)
                pm.update_stage_status(project_id, StageId.STORY, StageStatus.NEEDS_REVIEW)
            elif stage == 'script':
                result = gen_srv.generate_full_script(project_id, provider_id=req.provider, model_id=req.model)
                pm.update_stage_status(project_id, StageId.SCRIPT, StageStatus.NEEDS_REVIEW)
            else:
                result = gen_srv.auto_repair_script(project_id, provider_id=req.provider, model_id=req.model)
                pm.update_stage_status(project_id, StageId.SCRIPT, StageStatus.NEEDS_REVIEW)
            return result
        label = {'story':'Tạo cốt truyện','script':'Viết kịch bản','story-review':'Kiểm tra / sửa cốt truyện','script-repair':'Kiểm tra / sửa kịch bản'}[stage]
        return safe(lambda: service.start(project_id, label, {'stage':stage,'brief_hash':context['brief_hash'],**req.model_dump()}, work))

    return router
