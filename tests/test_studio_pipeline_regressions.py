"""Regressions for the production gates and engine integration found in the audit."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.semantic_review import build_prompt, review_script_logic
from apps.script_factory.topic_intent import extract_topic_intent
from studio.backend.services import audio_service as audio_module
from studio.backend.services import render_service as render_module
from studio.backend.services import qc_service as qc_module
from studio.backend.services.artifact_lineage import require_current_full_script, validate_full_script
from studio.backend.services.audio_service import AudioService
from studio.backend.services.audio_timing import measure_segment_timeline
from studio.backend.services.qc_service import QCService
from studio.backend.services.visual_service import _compose_scene_image_prompt, _compose_scene_video_prompt
from tests.test_studio_audio_flow import _add_real_lineage


def project_fixture(tmp_path):
    root = tmp_path / "projects"
    project = root / "EP_REG"
    script = _add_real_lineage(project, {"episode_id": "EP_REG", "segments": [
        {"id": "001", "speaker": "MINH", "text": "Phương đọc lá thư trên bàn.", "delivery_profile": "HOOK"},
        {"id": "002", "speaker": "MINH", "text": "Cảm ơn quý vị đã lắng nghe.", "delivery_profile": "ENDING"},
    ]})
    (project / "script/full_script.json").write_text(json.dumps(script), encoding="utf-8")
    return root, project


def test_story_change_during_script_generation_cannot_bind_to_new_lineage(tmp_path):
    from studio.backend.services.generation_service import _assert_story_snapshot
    from studio.backend.services.artifact_lineage import story_content_hash
    story = {"generation_request_id": "old-request", "secret": "An affair"}
    path = tmp_path / "story.json"
    path.write_text(json.dumps(story), encoding='utf-8')
    original_hash = story_content_hash(story)
    _assert_story_snapshot(path, original_hash, 'old-request')
    # Same request ID, different content is also a mismatch.
    path.write_text(json.dumps({**story, 'secret': 'A different plot'}), encoding='utf-8')
    with pytest.raises(ValueError, match='lineage'):
        _assert_story_snapshot(path, original_hash, 'old-request')


def test_quality_draft_has_repair_label_but_stale_lineage_requires_regeneration(tmp_path):
    root, project = project_fixture(tmp_path)
    path = project / 'script/full_script.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['artifact_status'] = 'NEEDS_REVISION'
    path.write_text(json.dumps(data), encoding='utf-8')
    status = validate_full_script('EP_REG', root)
    assert status['artifact_status'] == 'NEEDS_REVISION'
    assert 'CẦN SỬA' in status['status_label']
    assert not status['audio_gate_allowed']
    data['source_story_generation_request_id'] = 'old-story'
    path.write_text(json.dumps(data), encoding='utf-8')
    status = validate_full_script('EP_REG', root)
    assert status['artifact_status'] == 'STALE'
    assert 'REGENERATE REQUIRED' in status['status_label']


def test_auto_repair_rejects_old_story_script_before_using_provider(tmp_path, monkeypatch):
    from studio.backend.services import generation_service as module
    root, project = project_fixture(tmp_path)
    path = project / 'script/full_script.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['source_story_generation_request_id'] = 'old-story'
    data.update(title='Lá thư', host={'id': 'MINH'})
    path.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setattr(module, 'PROJECTS_DIR', root)
    service = object.__new__(module.GenerationService)
    service.get_provider = lambda **_: pytest.fail('Provider must not rewrite a stale lineage')
    with pytest.raises(ValueError, match='STALE'):
        service.auto_repair_script('EP_REG')
    assert json.loads(path.read_text(encoding='utf-8')) == data


def test_affair_topic_cannot_pass_when_truth_is_siblings():
    story = StoryBible(episode_id="EP_REG", title="Ngoại tình công sở", protagonist={"name": "Thanh"},
                       secret="Mối quan hệ giữa Tuấn và An không phải là tình nhân mà là anh em cùng cha khác mẹ.",
                       reveal_1="Đồng nghiệp hẹn hò sau giờ làm.", reveal_2="An là em gái của Tuấn.",
                       clues=["Tin nhắn thân mật ở công sở", "Cuộc hẹn riêng với đồng nghiệp"])
    report = extract_topic_intent("Bí mật ngoại tình công sở").evaluate_content_adherence(story, stage="story_bible")
    assert report["status"] == "FAIL" and report["score"] <= 40


@pytest.mark.parametrize('truth', [
    'Hoàn toàn không có chuyện yêu đương vụng trộm; hai người là anh em.',
    'Quốc không hề ngoại tình; anh chỉ thỏa thuận bồi thường bí mật.',
    'Tuấn không có mối quan hệ ngoại tình; cuộc gọi bị cắt ghép.',
])
def test_idea_truth_cannot_negate_requested_affair(truth):
    idea = {'working_title': 'Bí mật công sở', 'central_secret': truth, 'reveal_1': truth,
            'clue_1': 'Tin nhắn ngoại tình với đồng nghiệp ở công sở'}
    report = extract_topic_intent('Bí mật ngoại tình công sở').evaluate_content_adherence(idea, stage='idea')
    assert report['status'] == 'FAIL' and report['score'] <= 40
    assert 'truth_negates_requested_affair' in report['drift_terms']


def test_affair_topic_prompt_preserves_truth_but_allows_explicit_misunderstanding():
    assert 'đây là ngoại tình thật' in extract_topic_intent('Bí mật ngoại tình công sở').to_prompt_constraint()
    assert 'đây là ngoại tình thật' not in extract_topic_intent('Hiểu lầm ngoại tình công sở').to_prompt_constraint()


def test_final_idea_reveal_cannot_reverse_affair_into_fake_evidence():
    idea = {'working_title': 'Cuộc hẹn ở công sở', 'central_secret': 'Ngân đang ngoại tình với Hoàng.',
            'reveal_1': 'Ngân thừa nhận quan hệ vụng trộm với đồng nghiệp.',
            'reveal_2': 'Sự thật là Ngân không hề ngoại tình; họ dựng màn kịch để điều tra tham nhũng.',
            'clue_1': 'Tin nhắn hẹn hò với đồng nghiệp ở công sở'}
    assert extract_topic_intent('Bí mật ngoại tình công sở').evaluate_content_adherence(idea, stage='idea')['status'] == 'FAIL'


def test_affair_false_lead_can_identify_a_different_real_partner():
    idea = {'working_title': 'Cuộc hẹn công sở', 'central_secret': 'Việt đang ngoại tình công sở.',
            'reveal_1': 'Việt không ngoại tình với cô nhân viên sở hữu chiếc thẻ tên.',
            'reveal_2': 'Mối quan hệ bất chính thực sự là giữa Việt và bà Phó Chủ tịch công ty.',
            'clue_1': 'Tin nhắn thân mật với đồng nghiệp trong văn phòng'}
    report = extract_topic_intent('Bí mật ngoại tình công sở').evaluate_content_adherence(idea, stage='idea')
    assert report['status'] == 'PASS' and 'truth_negates_requested_affair' not in report['drift_terms']


def test_stale_story_is_not_returned_as_current_after_selecting_another_idea(tmp_path, monkeypatch):
    from studio.backend.services import script_service as module
    project = tmp_path / 'EP_REG'; (project / 'story').mkdir(parents=True)
    (project / 'project.json').write_text(json.dumps({'selected_idea': {
        'idea_id': 'NEW', 'title': 'Ý tưởng mới', 'hook': 'Hook mới',
    }}), encoding='utf-8')
    (project / 'story/story_bible.json').write_text(json.dumps({
        'episode_id': 'EP_REG', 'title': 'Bản cũ', 'protagonist': {'name': 'Hương'},
        'secret': 'Bí mật cũ', 'source_idea_id': 'OLD', 'story_qc_report': {'status': 'PASS'},
    }), encoding='utf-8')
    monkeypatch.setattr(module, 'PROJECTS_DIR', tmp_path)
    section = module.ScriptService().get_story_bible('EP_REG')
    assert not section.has_story_bible and section.title == 'Ý tưởng mới'
    assert section.mystery_core.startswith('STALE')
    assert module.ScriptService().get_story_qc('EP_REG')['status'] == 'FAIL'


def test_explicit_zero_pause_is_part_of_script_identity():
    from apps.script_factory.semantic_review import script_content_hash
    script = FullScript(episode_id='EP_REG', title='Thư', host={}, segments=[ScriptSegment(id='001', text='Lá thư trên bàn.')])
    initial = script_content_hash(script)
    script.segments[0].pause_after = 0.0
    assert script_content_hash(script) != initial
    assert script_content_hash(script) == script_content_hash(script.to_dict())


def test_nested_story_qc_target_repairs_the_actual_schema_field():
    from apps.script_factory.models import story_bible_repair_targets_clause
    prompt = story_bible_repair_targets_clause([{'target': 'reveal_1.evidence_support', 'rule': 'REVEAL_PROOF_OVERCLAIM'}])
    assert 'TRƯỜNG ĐANG BỊ LỖI CẦN VIẾT LẠI: reveal_justifications.' in prompt


@pytest.mark.parametrize('evidence,blocked', [
    ('Lời thừa nhận của Thành sau khi Hoa đọc tin nhắn.', False),
    ('Lời thừa nhận cùng biên lai chuyển tiền và thỏa thuận đã ký mà Hoa trực tiếp đọc.', False),
])
def test_story_proof_gate_recognizes_real_documents(evidence, blocked):
    from apps.script_factory.story_qc import StoryQCEngine
    bible = StoryBible(episode_id='EP_REG', title='Thư', protagonist={'name': 'Hoa'},
                       reveal_1='Thành thừa nhận ngoại tình.', reveal_justifications={
                           'reveal_1': {'evidence_support': evidence},
                       })
    report = StoryQCEngine().audit_story_bible(bible)
    assert ('REVEAL_PROOF_OVERCLAIM' in report.rule_codes) is blocked


@pytest.mark.parametrize("raw", ['{"secret":"Đã sửa"} Giải thích {khác}', '```json\n{"secret":"Đã sửa"}\n```', '{"secret":"Đã sửa\nDòng thứ hai"}'])
def test_story_patch_json_decoder_preserves_complete_object(raw):
    from apps.script_factory.json_response import parse_json_response
    assert parse_json_response(raw)["secret"].startswith("Đã sửa")


def test_story_patch_json_decoder_rejects_truncated_outer_document():
    from apps.script_factory.json_response import parse_json_response
    assert parse_json_response('{"secret":"cũ", "nested": {"ending":"mới"}') is None


def test_story_reviewer_failure_never_triggers_creative_rewrite():
    from apps.script_factory.story_qc import StoryQCEngine, StoryBibleQCReport
    calls = []
    engine = StoryQCEngine(provider=SimpleNamespace(repair_story_bible=lambda *args: calls.append(args)))
    bible = StoryBible(episode_id='EP_REG', title='Thư trên bàn', protagonist={'name': 'Hương'}, secret='Bản thảo cần giữ')
    report = StoryBibleQCReport('EP_REG', 'FAIL', issues=[{'rule': 'SEMANTIC_REVIEW_FAILED', 'severity': 'CRITICAL'}])
    assert engine.repair_story_bible(bible, report) is bible
    assert bible.secret == 'Bản thảo cần giữ' and not calls


@pytest.mark.parametrize('verdict', ['PASS', 'FAIL'])
def test_qc_only_recheck_preserves_story_aliases_and_script_lineage(tmp_path, monkeypatch, verdict):
    from apps.script_factory.story_qc import StoryQCEngine, StoryBibleQCReport
    from studio.backend.services import generation_service as module
    project = tmp_path / 'EP_REG'
    (project / 'story').mkdir(parents=True)
    bible = StoryBible(episode_id='EP_REG', title='Lá thư', protagonist={'name': 'Hương'},
                       generation_request_id='original-request', secret='Bí mật công sở')
    data = {**bible.to_dict(), 'premise': 'Ý tưởng gốc', 'characters': [{'name': 'Hương'}], 'fact_lock': []}
    (project / 'story/story_bible.json').write_text(json.dumps(data), encoding='utf-8')
    calls = []
    monkeypatch.setattr(module, 'PROJECTS_DIR', tmp_path)
    monkeypatch.setattr(module.GenerationService, 'get_provider', lambda *a, **kw: SimpleNamespace())
    monkeypatch.setattr(StoryQCEngine, 'audit_story_bible', lambda *a: StoryBibleQCReport('EP_REG', verdict))
    monkeypatch.setattr(StoryQCEngine, 'repair_story_bible', lambda _, value, *a: value)
    monkeypatch.setattr(module, 'mark_full_script_stale', lambda *a: calls.append('stale'))
    monkeypatch.setattr(module, 'invalidate_script_approval', lambda *a: calls.append('invalidate'))
    result = module.GenerationService().repair_story_bible('EP_REG')
    assert not result['story_changed']
    assert result['story_bible']['premise'] == data['premise']
    assert result['story_bible']['characters'] == data['characters']
    assert calls == ([] if verdict == 'PASS' else ['invalidate'])


def test_story_planner_persists_replacement_returned_by_repair(tmp_path, monkeypatch):
    from apps.script_factory.story_qc import StoryBibleQCReport
    from apps.script_factory.story_planner import StoryPlanner
    planner = StoryPlanner(SimpleNamespace(), SimpleNamespace(), tmp_path)
    old = StoryBible(episode_id='EP_REG', title='Cũ', protagonist={'name': 'Hương'}, secret='Cũ')
    new = StoryBible(episode_id='EP_REG', title='Mới', protagonist={'name': 'Hương'}, secret='Đã sửa')
    reports = iter([StoryBibleQCReport('EP_REG', 'FAIL'), StoryBibleQCReport('EP_REG', 'PASS')])
    monkeypatch.setattr(planner.story_qc, 'audit_story_bible', lambda _bible: next(reports))
    monkeypatch.setattr(planner.story_qc, 'repair_story_bible', lambda *args, **kwargs: new)
    assert planner.validate_story_bible(old, auto_repair=True).status == 'PASS'
    assert old.secret == 'Đã sửa' and old.story_qc_report['status'] == 'PASS'


def test_invalid_gemini_patch_does_not_mint_provenance(monkeypatch):
    from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider
    provider = GeminiScriptAIProvider(api_key='test')
    monkeypatch.setattr(provider, '_call_generate_content', lambda **kwargs: ('{"secret":', 1, 1))
    bible = StoryBible(episode_id='EP_REG', title='Cũ', protagonist={'name': 'Hương'}, secret='Cũ', generation_request_id='old-request')
    with pytest.raises(ValueError, match='invalid JSON'):
        provider.repair_story_bible(bible, [])
    assert bible.secret == 'Cũ' and bible.generation_request_id == 'old-request'


def test_story_semantic_verdict_requires_two_passes_and_current_content():
    from apps.script_factory.semantic_review import review_story_bible_logic, valid_story_semantic_review
    bible = StoryBible(episode_id='EP_REG', title='Thư', protagonist={'name': 'Hương'}, secret='Sự thật trong thư')
    calls = []
    def complete(*args):
        calls.append(args)
        return '{"issues":[]}', 1, 1
    review = review_story_bible_logic(bible, complete)
    assert len(calls) == 2 and valid_story_semantic_review(bible, review)
    bible.secret = 'Sự thật đã thay đổi'
    assert not valid_story_semantic_review(bible, review)


def test_affair_admission_does_not_require_invented_documents_but_identity_does():
    from apps.script_factory.story_qc import StoryQCEngine
    story = StoryBible(episode_id='EP_REG', title='Cuộc gặp', protagonist={'name':'Hoa'},
        secret='Thành ngoại tình.', reveal_1='Thành thừa nhận ngoại tình.',
        reveal_2='Thành là cha ruột của đứa trẻ.', reveal_justifications={
            'reveal_1': {'evidence_support':'Lời thú nhận của Thành.', 'motivation_support':'Bị đối chất.', 'timeline_support':'Sau cuộc gặp.'},
            'reveal_2': {'evidence_support':'Lời thú nhận của Thành.', 'motivation_support':'Bị đối chất.', 'character_knowledge_support':'Hoa nghe trực tiếp.'}})
    report = StoryQCEngine().audit_story_bible(story)
    proof = [i for i in report.issues if i['rule'] == 'REVEAL_PROOF_OVERCLAIM']
    assert [i['target'] for i in proof] == ['reveal_2.evidence_support']


def test_failed_repair_keeps_the_draft_and_failing_verdict():
    from apps.script_factory.models import QCReport
    from studio.backend.services.generation_service import _revise_keeping_best
    script = FullScript(episode_id='EP_REG', title='Thư', host={'id':'MINH'}, segments=[ScriptSegment(id='001', text='Bản thảo còn lỗi.')])
    def fail(**kwargs):
        raise RuntimeError('provider unavailable')
    qc = QCReport(episode_id='EP_REG', status='FAIL', evidence_issues=[{'rule':'TEST_FAILURE'}])
    result, verdict = _revise_keeping_best(SimpleNamespace(auto_revise_and_recheck=fail), script, None, qc, 3)
    assert result.segments[0].text == script.segments[0].text and verdict.status == 'FAIL'


def test_unavailable_reviewer_cannot_replace_a_tested_draft():
    from apps.script_factory.models import QCReport
    from studio.backend.services.generation_service import _revise_keeping_best
    script = FullScript(episode_id='EP_REG', title='Thư', host={'id':'MINH'},
                        segments=[ScriptSegment(id='001', text='Bản đã kiểm tra.')])
    tested = QCReport('EP_REG', 'FAIL', evidence_issues=[
        {'rule':'POV', 'severity':'CRITICAL'}, {'rule':'REPETITION', 'severity':'CRITICAL'}],
        semantic_review={'status':'FAIL'})
    def repair(**kwargs):
        candidate = kwargs['script']
        candidate.revision_round += 1
        candidate.segments[0].text = 'Bản sửa chưa kiểm tra được.'
        return candidate, QCReport('EP_REG', 'FAIL', evidence_issues=[
            {'rule':'SEMANTIC_REVIEW_FAILED', 'severity':'CRITICAL'}],
            semantic_review={'status':'ERROR'})
    result, verdict = _revise_keeping_best(SimpleNamespace(auto_revise_and_recheck=repair), script, None, tested, 3)
    assert result.segments[0].text == 'Bản đã kiểm tra.'
    assert result.revision_round == 1 and verdict is tested


def test_production_repair_never_invents_prose_or_mutates_approved_story():
    from apps.script_factory.models import QCReport
    from apps.script_factory.segment_rewriter import revise_with_ai
    from apps.script_factory.script_qc import apply_targeted_repairs
    story = StoryBible(episode_id='EP_REG', title='Thư', protagonist={'name':'Hoa'}, secret='Sự thật đã khóa')
    before = story.to_dict()
    text = 'Hoa chưa hiểu vì sao Thành giấu cuộc gặp.'
    script = FullScript(episode_id='EP_REG', title='Thư', host={'id':'MINH'}, segments=[
        ScriptSegment(id='001', text=text), ScriptSegment(id='002', text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile='ENDING')])
    qc = QCReport('EP_REG', 'FAIL', fact_conflicts=[{'type':'CAUSAL_GAP', 'segment_id':'001'}])
    result = apply_targeted_repairs(script, story, qc, allow_prose_templates=False)
    assert result.segments[0].text == text and story.to_dict() == before
    def unavailable(*args):
        raise RuntimeError('AI unavailable')
    with pytest.raises(RuntimeError, match='AI unavailable'):
        revise_with_ai(script, story, qc, unavailable)


def test_natural_dialogue_sentences_are_not_malformed():
    from apps.script_factory.script_qc import ScriptQCEngine
    story = StoryBible(episode_id='EP_REG', title='Thư', protagonist={'name':'Hoa'})
    script = FullScript(episode_id='EP_REG', title='Thư', host={'id':'MINH'}, segments=[
        ScriptSegment(id='001', text='Thu nói: “Em xin lỗi chị. Em đã hiểu chuyện xảy ra.”')])
    report = ScriptQCEngine().run_qc(script, story)
    assert not any(i['rule'] == 'MALFORMED_VIETNAMESE_PROSE' for i in report.evidence_issues)


@pytest.mark.parametrize('kind', ['story', 'script'])
@pytest.mark.parametrize('worsens', [False, True])
def test_repair_tracks_changed_problems_and_keeps_best_tested_draft(monkeypatch, kind, worsens):
    from apps.script_factory.models import QCReport
    from apps.script_factory.story_qc import StoryQCEngine, StoryBibleQCReport
    from studio.backend.services.generation_service import _revise_keeping_best
    calls = []
    def issues(round_number):
        if round_number == 3 and not worsens:
            return []
        count = 3 if worsens and round_number > 1 else (2 if worsens and round_number == 0 else 1)
        return [{'rule': f'PROBLEM_{round_number}', 'target': 'secret', 'severity': 'CRITICAL'}] * count
    if kind == 'story':
        bible = StoryBible(episode_id='EP_REG', title='Thư', protagonist={'name': 'Hoa'}, secret='0')
        def audit(value):
            problems = issues(int(value.secret))
            return StoryBibleQCReport('EP_REG', 'FAIL' if problems else 'PASS', issues=problems)
        def repair(value, _issues):
            calls.append(value.secret)
            value.secret = str(int(value.secret) + 1)
            return value, 1, 1
        engine = StoryQCEngine(provider=SimpleNamespace(repair_story_bible=repair))
        monkeypatch.setattr(engine, 'audit_story_bible', audit)
        result = engine.repair_story_bible(bible, audit(bible))
        assert result.secret == ('1' if worsens else '3')
        assert result.story_qc_report['status'] == ('FAIL' if worsens else 'PASS')
    else:
        script = FullScript(episode_id='EP_REG', title='Thư', host={'id': 'MINH'}, segments=[ScriptSegment(id='001', text='0')])
        def audit(value):
            problems = issues(value.revision_round)
            return QCReport('EP_REG', 'FAIL' if problems else 'PASS', evidence_issues=problems)
        def repair(**kwargs):
            value = kwargs['script']
            calls.append(value.revision_round)
            value.revision_round += 1
            value.segments[0].text = str(value.revision_round)
            return value, audit(value)
        result, verdict = _revise_keeping_best(SimpleNamespace(auto_revise_and_recheck=repair), script, None, audit(script), 3)
        assert result.segments[0].text == ('1' if worsens else '3')
        assert verdict.status == ('FAIL' if worsens else 'PASS')
    assert len(calls) == 3


def test_gemini_completion_keeps_all_response_text_parts(monkeypatch):
    from apps.script_factory.providers import gemini_provider as module
    from contextlib import nullcontext
    response = {"candidates": [{"content": {"parts": [
        {"text": "internal reasoning", "thought": True}, {"text": '{"secret":'}, {"text": '"Đã sửa"}'},
    ]}}]}
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *_args, **_kwargs: nullcontext(
        SimpleNamespace(read=lambda: json.dumps(response).encode("utf-8"))))
    raw, _, _ = module.GeminiScriptAIProvider(api_key="test")._call_generate_content("x", allow_fallback=False)
    assert json.loads(raw) == {"secret": "Đã sửa"}


def test_gemini_keeps_successful_fallback_for_next_part_but_honors_explicit_model(monkeypatch):
    import io
    import urllib.error
    from contextlib import nullcontext
    from apps.script_factory.providers import gemini_provider as module
    calls = []
    monkeypatch.setattr(module, '_MODEL_LAST_SUCCESS', {})
    def request(req, **kwargs):
        model = req.full_url.split('/models/')[1].split(':')[0]
        calls.append(model)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 503, 'overloaded', {}, io.BytesIO(b'overloaded'))
        return nullcontext(SimpleNamespace(read=lambda: b'{"candidates":[{"content":{"parts":[{"text":"[]"}]}}]}'))
    monkeypatch.setattr(module.urllib.request, 'urlopen', request)
    monkeypatch.setattr(module, '_is_blocked', lambda *a: False)
    monkeypatch.setattr(module, '_block', lambda *a: None)
    provider = module.GeminiScriptAIProvider(api_key='test', default_model='gemini-3.8-flash')
    provider._call_generate_content('first')
    provider._call_generate_content('second')
    provider._call_generate_content('explicit', model='gemini-2.5-flash')
    assert calls == ['gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.7-flash', 'gemini-2.5-flash']


def test_new_ui_operation_prefers_recent_working_fallback_after_primary_failure(monkeypatch):
    import io
    import urllib.error
    from contextlib import nullcontext
    from apps.script_factory.providers import gemini_provider as module
    calls = []
    def request(req, **_):
        model = req.full_url.split('/models/')[1].split(':')[0]
        calls.append(model)
        if model == 'gemini-3.8-flash':
            raise urllib.error.HTTPError(req.full_url, 503, 'overloaded', {}, io.BytesIO(b'overloaded'))
        return nullcontext(SimpleNamespace(read=lambda: b'{"candidates":[{"content":{"parts":[{"text":"[]"}]}}]}'))
    monkeypatch.setattr(module, '_MODEL_LAST_SUCCESS', {})
    monkeypatch.setattr(module, '_is_blocked', lambda *_: False)
    monkeypatch.setattr(module, '_block', lambda *_: None)
    monkeypatch.setattr(module.urllib.request, 'urlopen', request)
    module.GeminiScriptAIProvider(api_key='recent-test')._call_generate_content('first', model='gemini-2.5-flash')
    module.GeminiScriptAIProvider(api_key='recent-test', default_model='gemini-3.8-flash')._call_generate_content('next')
    assert calls == ['gemini-2.5-flash', 'gemini-3.8-flash', 'gemini-2.5-flash']


def test_story_review_accepts_grounded_character_identity_finding():
    from apps.script_factory.semantic_review import review_story_bible_logic
    story = StoryBible(episode_id="EP_REG", title="Lá thư", protagonist={"name": "Thanh"},
                       timeline=["Bà Mai là mẹ Tuấn, đã mất năm 2010."],
                       supporting_characters=[{"name": "Bà Mai", "role": "Mẹ Thanh, còn sống"}])
    finding = {"issues": [{"rule": "CHARACTER_IDENTITY_CONTRADICTION", "field": "timeline",
                           "quote": "Bà Mai là mẹ Tuấn", "problem": "Mẹ Thanh bị biến thành mẹ Tuấn", "confidence": "high"}]}
    result = review_story_bible_logic(story, lambda *_: (json.dumps(finding, ensure_ascii=False), 1, 1))
    assert result["status"] == "RUN" and result["issues"][0]["rule"] == "CHARACTER_IDENTITY_CONTRADICTION"


def test_stored_story_pass_cannot_hide_new_topic_failure(tmp_path, monkeypatch):
    from studio.backend.services import script_service as script_module
    monkeypatch.setattr(script_module, "PROJECTS_DIR", tmp_path)
    path = tmp_path / "EP_REG/story/story_bible.json"; path.parent.mkdir(parents=True)
    story = StoryBible(episode_id="EP_REG", title="t", protagonist={"name": "Thanh"},
                       original_user_topic="Bí mật ngoại tình công sở", story_qc_report={"status": "PASS"},
                       secret="Mối quan hệ không phải là tình nhân mà là anh em cùng cha khác mẹ.")
    path.write_text(json.dumps(story.to_dict()), encoding="utf-8")
    result = script_module.ScriptService().get_story_qc("EP_REG")
    assert result["status"] == "FAIL"
    assert "STORY_BIBLE_TOPIC_DRIFT" in result["rule_codes"]


@pytest.mark.parametrize("mutation", ["qc_hash", "semantic", "semantic_hash", "review_version", "story_hash", "unknown_status"])
def test_missing_or_mismatched_review_blocks_audio_and_script_approval(tmp_path, mutation):
    root, project = project_fixture(tmp_path)
    path = project / "script/qc_report.json"
    qc = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "qc_hash":
        qc.pop("script_content_hash")
    elif mutation == "semantic":
        qc.pop("semantic_review")
    else:
        key = {"semantic_hash": "script_hash", "unknown_status": "status"}.get(mutation, mutation)
        qc["semantic_review"][key] = "invalid"
    path.write_text(json.dumps(qc), encoding="utf-8")
    assert not validate_full_script("EP_REG", root)["audio_gate_allowed"]
    with pytest.raises(ValueError):
        require_current_full_script("EP_REG", root, require_approved=False)


def test_missing_approval_hash_blocks_audio(tmp_path):
    root, project = project_fixture(tmp_path)
    for filename, key in [("script/full_script.json", "approved_content_hash"), ("project.json", "approved_script_content_hash")]:
        path = project / filename
        data = json.loads(path.read_text(encoding="utf-8")); data.pop(key)
        path.write_text(json.dumps(data), encoding="utf-8")
    assert not validate_full_script("EP_REG", root)["audio_gate_allowed"]


@pytest.mark.parametrize("raw", ['{"issues": ["bad finding"]}', '{"issues":[{"rule":"BAD","segment_id":"001","quote":"invented evidence which is absent"}]}'])
def test_unusable_semantic_findings_never_produce_clean_run(raw):
    script = FullScript(episode_id="EP_REG", title="Lá thư", host={"id": "MINH"}, segments=[ScriptSegment(id="001", text="Phương mở lá thư trên bàn.")])
    review = review_script_logic(script, StoryBible(episode_id="EP_REG", title="Lá thư", protagonist={"name": "Phương"}), lambda *_: (raw, 1, 1))
    assert review["status"] == "ERROR"


def test_reviewer_sees_story_and_checks_action_and_knowledge_progression():
    bible = StoryBible(episode_id="EP_REG", title="Vết mực", protagonist={"name": "Phương"}, timeline=["Cửa mở trước cuộc gặp"], knowledge_ledger=[{"known": "ký khống"}])
    prompt = build_prompt(FullScript(episode_id="EP_REG", title="Vết mực", host={"id": "MINH"}), bible)
    for text in ["ACTION_SEQUENCE_INVERSION", "KNOWLEDGE_STATE_REGRESSION", "ký khống", "Vết mực"]:
        assert text in prompt


def test_timing_uses_wav_samples_and_max_gap_not_word_count(tmp_path):
    selected = tmp_path / "selected"; selected.mkdir()
    sf.write(selected / "001.wav", np.zeros(48000, dtype=np.float32), 48000)
    sf.write(selected / "002.wav", np.zeros(96000, dtype=np.float32), 48000)
    segments = [
        {"id": "001", "text": "long " * 300, "pause_before": .2, "pause_after": .3},
        {"id": "002", "text": "short", "pause_before": .7, "pause_after": .4},
    ]
    events, frames = measure_segment_timeline(tmp_path, segments, {}, 48000)
    assert events[0]["speech_start_sample"] == 9600
    assert events[1]["speech_start_sec"] == pytest.approx(1.9)
    assert events[1]["speech_end_sec"] == pytest.approx(3.9)
    assert frames == 206400


def test_partial_synthesis_does_not_replace_full_episode(tmp_path, monkeypatch):
    root, project = project_fixture(tmp_path)
    monkeypatch.setattr(audio_module, "PROJECTS_DIR", root)
    audio = project / "audio"; audio.mkdir()
    master = audio / "narration_dry.wav"; master.write_bytes(b"existing full master")
    report = audio / "generation_report.json"; report.write_text('{"existing":true}')
    service = AudioService()
    monkeypatch.setattr(service, "_get_engine", lambda: SimpleNamespace(sample_rate=48000))
    monkeypatch.setattr(service, "list_voices", lambda: {"voices": [{"voice_id": "020"}]})

    def synth(engine, work, segment, character):
        (work / "selected").mkdir(exist_ok=True)
        sf.write(work / "selected" / f"{segment['id']}.wav", np.zeros(4800, dtype=np.float32), 48000)
        return True, "ok", {"selected_file": f"selected/{segment['id']}.wav"}

    def assemble(**kwargs):
        from apps.audio_director import build_dialogue_timeline
        wave, _, _ = build_dialogue_timeline(kwargs["project_dir"], kwargs["segments"], kwargs["project_state"])
        target = kwargs["project_dir"] / "preview.wav"; sf.write(target, wave, 48000)
        return True, "ok", str(target), None

    monkeypatch.setattr(audio_module, "generate_single_segment_takes", synth)
    monkeypatch.setattr(audio_module, "build_master_audio", assemble)
    response = service.generate_narration("EP_REG", "020", segment_ids=["001"])
    assert response["preview"] and not response["generation"]["full_episode"]
    assert master.read_bytes() == b"existing full master"
    assert json.loads(report.read_text()) == {"existing": True}


def test_audio_without_content_binding_cannot_be_approved(tmp_path, monkeypatch):
    root, project = project_fixture(tmp_path)
    monkeypatch.setattr(audio_module, "PROJECTS_DIR", root)
    (project / "audio").mkdir()
    sf.write(project / "audio/narration.wav", np.zeros(48000, dtype=np.float32), 48000)
    with pytest.raises(ValueError, match="STALE"):
        AudioService().require_current_audio("EP_REG")


def test_visual_prompts_preserve_declared_cast_in_ending():
    prompt = _compose_scene_image_prompt(44, "Phương quyết định ly hôn và buông bỏ.", ["PHUONG"], "Căn hộ", "ENDING",
                                        {"PHUONG": {"name": "Phương", "gender": "FEMALE"}})
    assert "Vietnamese woman" in prompt and "Vietnamese man" not in prompt
    video = _compose_scene_video_prompt(44, "Phương quay lưng.", ["PHUONG"], "Căn hộ", "ENDING")["full_prompt"]
    assert "Hùng" not in video and "Thanh" not in video


def metadata(audio=True):
    streams = [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                "r_frame_rate": "30/1", "start_time": "0", "duration": "2"}]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac", "start_time": "0", "duration": "2"})
    return {"streams": streams, "format": {"duration": "2"}}


def test_no_video_qc_has_no_fabricated_measurements(monkeypatch):
    service = QCService(); monkeypatch.setattr(service, "find_project_video_path", lambda _: None)
    report = service.get_qc_report("EP_REG")
    assert report.overall_status == "NOT_RUN" and report.integrated_loudness_lufs is None
    assert report.av_sync_delta_ms is None and report.black_gap_detected is None


@pytest.mark.parametrize("with_audio", [False, True])
def test_missing_audio_or_failed_measurement_cannot_pass(tmp_path, monkeypatch, with_audio):
    path = tmp_path / "video.mp4"; path.write_bytes(b"test")
    service = QCService()
    monkeypatch.setattr(service, "_probe_video_file", lambda _: metadata(with_audio))
    monkeypatch.setattr(service, "_inspect_signal", lambda _: (_ for _ in ()).throw(RuntimeError("ffmpeg failed")))
    report = service.get_qc_report("EP_REG", path)
    assert report.overall_status == "FAIL"
    assert report.integrated_loudness_lufs is None and report.true_peak_db is None


def test_ffmpeg_error_is_not_converted_to_default_loudness(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg", stderr="failed")
    monkeypatch.setattr(qc_module.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        QCService()._measure_audio_loudness(Path("bad.mp4"))


def test_render_adapter_uses_current_plan_and_rejects_old_output(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(render_module, "PROJECTS_DIR", tmp_path / "projects")
    project = tmp_path / "projects/EP_REG"; (project / "assets").mkdir(parents=True)
    audio = project / "voice.wav"; sf.write(audio, np.zeros(96000, dtype=np.float32), 48000)
    scenes = []
    for index in (1, 2):
        Image.new("RGB", (128, 128), "blue").save(project / "assets" / f"SC_{index:03d}.png")
        scenes.append({"scene_id": f"SC_{index:03d}", "start_time": index - 1, "end_time": index,
                       "source_segments": [f"{index:03d}"], "image_motion": {"type": "SLOW_PUSH_IN"}})
    from studio.backend.services.artifact_files import file_sha256
    path = project / "visual_plan.json"; path.write_text(json.dumps({"scenes": scenes, "audio_sha256": file_sha256(audio)}))
    plan = render_module.RenderService()._build_project_plan("EP_REG", path, audio, None)
    assert len(plan.scenes) == 2 and plan.episode_id == "EP_REG"
    assert plan.scenes[1].start_sec == 1 and plan.scenes[1].segment_start == "002"
    assert plan.scenes[0].image_motion == "SLOW_PUSH_IN"
    (project / "assets/SC_002.png").unlink()
    with pytest.raises(FileNotFoundError, match="SC_002"):
        render_module.RenderService()._build_project_plan("EP_REG", path, audio, None)


def test_independent_continuity_review_can_block_an_initial_clean_verdict():
    script = FullScript(episode_id="EP_REG", title="Lá thư", host={"id": "MINH"}, segments=[
        ScriptSegment(id="001", text="Anh đã đọc email và biết kế hoạch ký khống."),
        ScriptSegment(id="002", text="Anh vẫn tưởng chỉ có một mối quan hệ vụng trộm."),
    ])
    answers = iter(['{"issues":[]}', json.dumps({"issues": [{
        "rule": "KNOWLEDGE_STATE_REGRESSION", "segment_id": "002", "related_segment_ids": ["001"],
        "quote": "Anh vẫn tưởng chỉ có một mối quan hệ vụng trộm", "confidence": "high",
        "problem": "Quên chứng cứ đã biết", "fix": "Kể đúng trạng thái hiểu biết",
    }]}, ensure_ascii=False)])
    result = review_script_logic(script, StoryBible(episode_id="EP_REG", title="Lá thư", protagonist={"name": "Anh"}),
                                 lambda *_: (next(answers), 1, 1))
    assert result["passes"] == 2
    assert result["issues"][0]["rule"] == "KNOWLEDGE_STATE_REGRESSION"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_real_assembler_accepts_the_studio_adapter_plan(tmp_path, monkeypatch):
    """Real FFmpeg/assembler integration; synthetic media, no TTS acceptance claim."""
    from PIL import Image
    from apps.visual_engine.final_auto_assembler import assemble_full_episode
    from studio.backend.services.artifact_files import file_sha256
    monkeypatch.setattr(render_module, "PROJECTS_DIR", tmp_path / "projects")
    project = tmp_path / "projects/EP_RENDER"; (project / "assets").mkdir(parents=True)
    sr = 48000
    audio = project / "voice.wav"
    sf.write(audio, .12 * np.sin(2 * np.pi * 220 * np.arange(2 * sr) / sr), sr)
    scenes = []
    rng = np.random.default_rng(5)
    for i in range(2):
        Image.fromarray(rng.integers(20, 230, (180, 320, 3), dtype=np.uint8)).save(project / "assets" / f"SC_{i+1:03d}.png")
        scenes.append({"scene_id": f"SC_{i+1:03d}", "start_time": i, "end_time": i + 1,
                       "source_segments": [f"{i+1:03d}"], "image_motion": "SLOW_PUSH_IN"})
    plan_file = project / "visual_plan.json"
    plan_file.write_text(json.dumps({"scenes": scenes, "audio_sha256": file_sha256(audio)}))
    plan = render_module.RenderService()._build_project_plan("EP_RENDER", plan_file, audio, None)
    output, qc = assemble_full_episode(plan=plan, output_mp4_path=project / "render/final.mp4", cache_dir=project / "cache")
    probe = QCService()._probe_video_file(output)
    assert {s["codec_type"] for s in probe["streams"]} == {"audio", "video"}
    assert float(probe["format"]["duration"]) == pytest.approx(2, abs=.04)
    assert qc["scene_count"] == 2 and qc["audio_streams_count"] == 1
