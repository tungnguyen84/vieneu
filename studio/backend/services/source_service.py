"""Revisioned source/brief persistence and bounded, restart-visible jobs."""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
import uuid
from pathlib import Path

from apps.script_factory.source_intake import checked_text, read_article, read_text, read_youtube, text_hash, youtube_url

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
MODES = {'FACTUAL_RETELLING', 'FICTION_FROM_THEME', 'IMPROVE_OWN_SCRIPT'}


def project_lock(project):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(Path(project).resolve()), threading.RLock())


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows does not allow replacement while another reader/AV holds the file.
    # Keep publication atomic and retry sharing violations, never truncate current data.
    for attempt in range(10):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02 * (attempt + 1))


def brief_hash(brief):
    return text_hash(json.dumps({k: v for k, v in brief.items() if k not in ('approved_at', 'status', 'stale_reason')},
                                sort_keys=True, ensure_ascii=False))


def current_context(project):
    """Reject draft/stale source or brief instead of silently using a saved snapshot."""
    project = Path(project)
    brief = read_json(project / 'adaptation' / 'brief.json')
    if not brief:
        return None
    if brief.get('status') != 'APPROVED':
        raise ValueError('Nguồn/định hướng đã thay đổi; xác nhận nguồn và chọn lại hướng trước khi viết.')
    source_id = brief.get('source_id', '')
    if not re.fullmatch(r'[a-f0-9]{32}', source_id):
        raise ValueError('Source ID không hợp lệ.')
    folder = project / 'sources' / source_id
    source = read_json(folder / 'source.json')
    text = (folder / 'extracted.txt').read_text(encoding='utf-8')
    if (source.get('status') != 'CONFIRMED' or source.get('content_hash') != text_hash(text)
            or brief.get('source_hash') != source.get('content_hash')
            or brief.get('source_revision') != source.get('revision')):
        raise ValueError('Nội dung nguồn không khớp revision đã chọn; cần phân tích/chọn hướng lại.')
    analysis = read_json(folder / 'analysis.json')
    if analysis.get('source_hash') != source['content_hash'] or analysis.get('source_revision') != source['revision']:
        raise ValueError('Phân tích không thuộc phiên bản nguồn hiện tại.')
    units = read_json(folder / 'units.json')['units']
    if text_hash('\n'.join(u['text'] for u in units)) != source['content_hash']:
        raise ValueError('Các đoạn nguồn không khớp nội dung đã xác nhận.')
    return {'brief': brief, 'brief_hash': brief_hash(brief), 'source': source,
            'analysis': analysis, 'units': units}


def assert_context(project, expected):
    if not expected:
        if (Path(project) / 'adaptation' / 'brief.json').exists():
            raise ValueError('Project đã chọn nguồn nhưng artifact thiếu lineage nguồn; cần tạo lại từ hướng đã chọn.')
        return
    actual = current_context(project)
    if not actual or actual['brief_hash'] != expected['brief_hash']:
        raise ValueError('Nguồn/brief đã thay đổi trong lúc AI chạy; không lưu kết quả cũ thành current.')


class SourceService:
    def __init__(self, projects_dir, provider_factory, job_sink=None):
        self.root = Path(projects_dir)
        self.providers = provider_factory
        self.job_sink = job_sink
        self.epoch = uuid.uuid4().hex
        self.slots = threading.BoundedSemaphore(2)

    def project(self, project_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', project_id):
            raise ValueError('Project ID không hợp lệ.')
        project = self.root / project_id
        if not (project / 'project.json').exists():
            raise ValueError('Project không tồn tại.')
        return project

    def folder(self, project_id, source_id):
        if not re.fullmatch(r'[a-f0-9]{32}', source_id):
            raise ValueError('Source ID không hợp lệ.')
        folder = self.project(project_id) / 'sources' / source_id
        if not (folder / 'source.json').exists():
            raise ValueError('Nguồn không tồn tại.')
        return folder

    def invalidate(self, project, reason):
        from studio.backend.services.artifact_lineage import mark_story_bible_stale, mark_full_script_stale, invalidate_script_approval
        brief_path = project / 'adaptation' / 'brief.json'
        brief = read_json(brief_path)
        if brief:
            brief.update(status='STALE', stale_reason=reason)
            write_json(brief_path, brief)
        mark_story_bible_stale(project.name, self.root, reason)
        mark_full_script_stale(project.name, self.root, reason)
        invalidate_script_approval(project.name, self.root)

    def add(self, project_id, data, input_url=None):
        project = self.project(project_id)
        source_id = uuid.uuid4().hex
        folder = project / 'sources' / source_id
        folder.mkdir(parents=True)
        text = checked_text(data['text'])
        meta = {k: v for k, v in data.items() if k not in ('text', 'units')}
        meta.update(source_id=source_id, input_url=input_url, revision=1, status='DRAFT',
                    content_hash=text_hash(text), retrieved_at=time.time(), word_count=len(text.split()))
        with project_lock(project):
            write_json(folder / 'source.json', meta)
            write_json(folder / 'units.json', {'units': data['units']})
            (folder / 'extracted.txt').write_text(text, encoding='utf-8')
        return self.get(project_id, source_id)

    def get(self, project_id, source_id):
        folder = self.folder(project_id, source_id)
        with project_lock(self.project(project_id)):
            return {**read_json(folder / 'source.json'), 'text': (folder / 'extracted.txt').read_text(encoding='utf-8'),
                    'units': read_json(folder / 'units.json').get('units', []),
                    'analysis': read_json(folder / 'analysis.json')}

    def state(self, project_id):
        project = self.project(project_id)
        with project_lock(project):
            sources = [read_json(p) for p in sorted((project / 'sources').glob('*/source.json'))]
            return {'sources': sources, 'brief': read_json(project / 'adaptation' / 'brief.json'),
                    'directions': read_json(project / 'adaptation' / 'directions.json'),
                    'jobs': sorted([self.job(project_id, p.stem) for p in (project / 'adaptation' / 'jobs').glob('*.json')],
                                   key=lambda j: j['started_at'])[-20:]}

    def confirm(self, project_id, source_id, text, expected_revision):
        project, folder = self.project(project_id), self.folder(project_id, source_id)
        text = checked_text(text)
        with project_lock(project):
            source = read_json(folder / 'source.json')
            if source['revision'] != expected_revision:
                raise ValueError('Nguồn đã được sửa ở nơi khác; tải lại trước khi xác nhận.')
            old_text = (folder / 'extracted.txt').read_text(encoding='utf-8')
            if old_text != text:
                history = folder / 'history' / str(source['revision'])
                write_json(history / 'source.json', source)
                (history / 'extracted.txt').write_text(old_text, encoding='utf-8')
                write_json(history / 'units.json', read_json(folder / 'units.json'))
                source['revision'] += 1
                source.update(content_hash=text_hash(text), extraction_method='user_corrected', word_count=len(text.split()))
                write_json(folder / 'units.json', {'units': read_text(text)['units']})
                (folder / 'extracted.txt').write_text(text, encoding='utf-8')
                self.invalidate(project, 'Nội dung nguồn đã sửa; cần phân tích và chọn hướng mới.')
            source.update(status='CONFIRMED', confirmed_at=time.time())
            write_json(folder / 'source.json', source)
        return self.get(project_id, source_id)

    def directions(self, project_id, source_id, config, provider_id=None, model_id=None):
        from apps.script_factory.adaptation import analyze_source, generate_directions
        project = self.project(project_id)
        mode = config.get('adaptation_mode')
        if mode not in MODES:
            raise ValueError('Chọn một trong ba chế độ sử dụng nguồn.')
        if not 60 <= int(config.get('target_duration_sec', 1200)) <= 3600:
            raise ValueError('Thời lượng phải trong 1–60 phút.')
        if mode == 'IMPROVE_OWN_SCRIPT' and not config.get('owned_script_confirmed'):
            raise ValueError('Xác nhận đây là kịch bản của bạn trước khi nâng cấp.')
        source = self.get(project_id, source_id)
        if source['status'] != 'CONFIRMED':
            raise ValueError('Cần kiểm tra và xác nhận nội dung nguồn trước.')
        provider = self.providers(provider_id=provider_id, model_id=model_id)
        if not getattr(provider, 'requires_grounded_review', False) or not callable(getattr(provider, 'complete_json', None)):
            raise ValueError('Chọn provider AI thật hỗ trợ JSON; không nghiệm thu nguồn bằng mock.')
        analysis = analyze_source(provider, source)
        directions = generate_directions(provider, source, analysis, config)
        with project_lock(project):
            current = self.get(project_id, source_id)
            if (current['content_hash'], current['revision']) != (source['content_hash'], source['revision']):
                raise ValueError('Nguồn đổi trong lúc phân tích; kết quả không được lưu.')
            self.invalidate(project, 'Cấu hình/hướng khai thác được tạo lại; cần chọn hướng mới.')
            write_json(self.folder(project_id, source_id) / 'analysis.json', analysis)
            data = {'source_id': source_id, 'source_revision': source['revision'], 'source_hash': source['content_hash'],
                    'config': config, **directions}
            write_json(project / 'adaptation' / 'directions.json', data)
        return data

    def select(self, project_id, direction_id, generation_request_id):
        project = self.project(project_id)
        with project_lock(project):
            data = read_json(project / 'adaptation' / 'directions.json')
            if data.get('generation_request_id') != generation_request_id:
                raise ValueError('Ba hướng đã thay đổi; tải lại trước khi chọn.')
            direction = next((d for d in data.get('directions', []) if d['direction_id'] == direction_id), None)
            if not direction:
                raise ValueError('Hướng không thuộc lần sinh hiện tại.')
            source = self.get(project_id, data['source_id'])
            if (source['revision'], source['content_hash'], source['status']) != (data['source_revision'], data['source_hash'], 'CONFIRMED'):
                raise ValueError('Hướng đã cũ vì nguồn thay đổi.')
            self.invalidate(project, 'Đã chọn hướng mới từ nguồn; tạo lại Story và Script.')
            brief = {**data['config'], 'source_id': data['source_id'], 'source_revision': data['source_revision'],
                     'source_hash': data['source_hash'], 'selected_direction_id': direction_id,
                     'direction': direction, 'directions_request_id': generation_request_id,
                     'status': 'APPROVED', 'approved_at': time.time()}
            write_json(project / 'adaptation' / 'brief.json', brief)
            meta = read_json(project / 'project.json')
            meta.update(title=direction['title'], target_duration=brief['target_duration_sec'],
                        adaptation_mode=brief['adaptation_mode'], topic=brief.get('topic', ''),
                        selected_idea={'idea_id': direction_id, 'title': direction['title'], 'premise': direction['hook']})
            meta.setdefault('stage_statuses', {}).update({'01_idea': 'APPROVED', '02_story': 'STALE', '03_script': 'STALE'})
            write_json(project / 'project.json', meta)
        return brief

    def job(self, project_id, job_id):
        with project_lock(self.project(project_id)):
            return self._job(project_id, job_id)

    def _job(self, project_id, job_id):
        if not re.fullmatch(r'[a-f0-9]{32}', job_id):
            raise ValueError('Job ID không hợp lệ.')
        path = self.project(project_id) / 'adaptation' / 'jobs' / (job_id + '.json')
        data = read_json(path)
        if not data:
            raise ValueError('Job không tồn tại.')
        if data['status'] == 'RUNNING' and data.get('epoch') != self.epoch:
            data.update(status='FAILED', error='Backend đã khởi động lại; giữ dữ liệu đã lưu và thử lại bước này.')
            write_json(path, data)
        return data

    def start(self, project_id, action, payload, work):
        project = self.project(project_id)
        key = text_hash(json.dumps({'action': action, 'payload': payload}, sort_keys=True, ensure_ascii=False))
        with project_lock(project):
            running = [j for j in self.state(project_id)['jobs'] if j['status'] == 'RUNNING']
            if running:
                if running[0]['key'] == key:
                    return running[0]
                raise ValueError('Project đang chạy một bước; chờ hoàn tất trước khi bắt đầu bước khác.')
            if not self.slots.acquire(blocking=False):
                raise ValueError('Đang có hai tác vụ; hãy thử lại khi một tác vụ hoàn tất.')
            job_id = uuid.uuid4().hex
            path = project / 'adaptation' / 'jobs' / (job_id + '.json')
            data = {'job_id': job_id, 'project_id': project_id, 'action': action, 'key': key,
                    'epoch': self.epoch, 'status': 'RUNNING', 'started_at': time.time(), 'step_label': action}
            try:
                write_json(path, data)
            except Exception:
                self.slots.release()
                raise
        def run():
            from studio.backend.services import live_log
            from studio.backend.models import JobStatus
            try:
                if self.job_sink:
                    self.job_sink.create_job(job_id, project_id, 'SOURCE_' + action, action)
                with live_log.project_scope(project_id, 'Nguồn: ' + action):
                    result = work()
                data.update(status='COMPLETED', result=result, completed_at=time.time())
                if self.job_sink:
                    self.job_sink.update_job(job_id, status=JobStatus.COMPLETED, progress=100, step_label='Hoàn tất')
            except Exception as exc:
                logging.getLogger('SCCStudio.Source').exception('Source job %s failed', job_id)
                data.update(status='FAILED', error=str(exc), completed_at=time.time())
                if self.job_sink:
                    self.job_sink.update_job(job_id, status=JobStatus.FAILED, error_message=str(exc))
            finally:
                try:
                    with project_lock(project):
                        write_json(path, data)
                finally:
                    self.slots.release()
        try:
            threading.Thread(target=run, daemon=True, name='source-' + job_id[:8]).start()
        except Exception as exc:
            self.slots.release()
            data.update(status='FAILED',error=str(exc),completed_at=time.time())
            with project_lock(project):
                write_json(path,data)
            raise
        return copy.deepcopy(data)
