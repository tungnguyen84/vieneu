"""Source intake, revision races and grounded-mode contracts (no live TTS)."""
import json
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.script_factory.source_intake import read_text, subtitle_units, public_address, youtube_url, read_youtube
from apps.script_factory.adaptation import analyze_source, writer_context, source_review, write_adapted_script
from apps.script_factory.models import StoryBible, FullScript, ScriptSegment
from studio.backend.services.source_service import SourceService, current_context, assert_context, read_json

TEXT = 'Lan làm việc ở một cửa hàng nhỏ. Cô kiểm tra sổ thu chi mỗi tối. Một lần cô tìm thấy khoản tiền bị ghi nhầm. Lan hỏi người quản lý và sửa lại sổ. Cuối tháng cửa hàng đối chiếu và xác nhận số tiền đúng.'


def test_source_quotes_allow_case_unicode_but_reject_paraphrase():
    from apps.script_factory.adaptation import _quote
    import unicodedata
    text='Đây là câu chuyện về một đội ngũ học cách làm việc từ mục đích chung.'
    assert _quote(unicodedata.normalize('NFD','Đội ngũ học cách làm việc từ mục đích chung.'), text)
    assert not _quote('Đội ngũ hiểu cách làm việc từ mục đích chung.', text)
    assert not _quote('Đội ngũ học cách... mục đích chung.', text)


def test_source_ref_id_correction_requires_unique_verbatim_quote_and_records_original():
    from apps.script_factory.adaptation import canonicalize_source_refs,validate_refs
    units=[{'unit_id':'U0001','text':'Lan sửa đúng khoản thu trong cuốn sổ.'},
           {'unit_id':'U0002','text':'Hạnh kiểm tra lại hóa đơn.'}]
    refs=[{'unit_id':'U0002','quote':'Lan sửa đúng khoản thu trong cuốn sổ.'}]
    assert not validate_refs(refs,units)
    canonicalize_source_refs(refs,units)
    assert validate_refs(refs,units) and refs[0]['reported_unit_id']=='U0002' and refs[0]['unit_id']=='U0001'
    absent=[{'unit_id':'U0002','quote':'Lan lấy tiền để bù vào sổ.'}]
    canonicalize_source_refs(absent,units)
    assert not validate_refs(absent,units) and absent[0]['unit_id']=='U0002'
    ambiguous=[{'unit_id':'missing','quote':units[0]['text']}]
    canonicalize_source_refs(ambiguous,units+[{'unit_id':'U0003','text':units[0]['text']}])
    assert ambiguous[0]['unit_id']=='missing'


def test_story_source_evidence_is_atomic_and_covers_canon():
    from apps.script_factory.adaptation import source_artifact
    bible=StoryBible(episode_id='EPNEW', title='Cửa hàng nhỏ', protagonist={'name':'Lan','description':'Lan làm việc ở cửa hàng.'},
                    supporting_characters=[{'name':'Hạnh','description':'Hạnh quản lý cửa hàng.'}],
                    timeline=['Lan kiểm tra khoản tiền ghi nhầm.'], causal_chains=[{'cause':'Sổ ghi nhầm khoản thu.'}])
    items=source_artifact(bible)
    assert items['supporting_characters.0.description']=='Hạnh quản lý cửa hàng.'
    assert items['protagonist.name']=='Lan'
    assert items['timeline.0']=='Lan kiểm tra khoản tiền ghi nhầm.'
    assert items['causal_chains.0.cause']=='Sổ ghi nhầm khoản thu.'
    assert 'supporting_characters' not in items


class Provider:
    provider_name = 'openai_compatible'
    default_model = 'test-real-interface'
    requires_grounded_review = True
    def __init__(self, responses): self.responses = iter(responses); self.prompts = []
    def complete_json(self, system, prompt, model=None):
        self.prompts.append(prompt)
        return json.dumps(next(self.responses), ensure_ascii=False), 10, 10


@pytest.fixture
def service(tmp_path):
    (tmp_path / 'EPNEW').mkdir()
    (tmp_path / 'EPNEW' / 'project.json').write_text(json.dumps({'project_id':'EPNEW','stage_statuses':{}}))
    return SourceService(tmp_path, lambda **kw: None)


def confirmed(service):
    source = service.add('EPNEW', read_text(TEXT))
    return service.confirm('EPNEW', source['source_id'], source['text'], 1)


def selected(service):
    from studio.backend.services.source_service import write_json
    source = confirmed(service)
    folder = service.folder('EPNEW',source['source_id'])
    write_json(folder/'analysis.json',{'theme':'Công sở','source_hash':source['content_hash'],'source_revision':1})
    data={'source_id':source['source_id'],'source_hash':source['content_hash'],'source_revision':1,'generation_request_id':'request1',
          'config':{'adaptation_mode':'FICTION_FROM_THEME','target_duration_sec':300,'topic':'Công sở','locked_elements':[]},
          'directions':[{'direction_id':'DIRECTION_1','title':'Một sự lựa chọn','hook':'Một sự lựa chọn khó'}]}
    write_json(service.project('EPNEW')/'adaptation'/'directions.json',data)
    service.select('EPNEW','DIRECTION_1','request1')
    return source,current_context(service.project('EPNEW'))


def test_legacy_artifact_cannot_bypass_selected_source(service):
    assert_context(service.project('EPNEW'), None)
    selected(service)
    with pytest.raises(ValueError,match='thiếu lineage'):
        assert_context(service.project('EPNEW'),None)


def test_factual_review_covers_every_segment_in_each_bounded_pass(service):
    from apps.script_factory.adaptation import valid_source_review
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},adaptation_context=context)
    script=FullScript(episode_id='EPNEW',title='Tập',host={},segments=[ScriptSegment(id=f'{i:03}',text=TEXT) for i in range(1,12)])
    checks=[{'item_id':s.id,'artifact_quote':'Lan làm việc ở một cửa hàng nhỏ.', 'classification':'FACT','verdict':'PASS',
             'evidence_refs':[{'unit_id':'U0001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}]} for s in script.segments]
    modes=[{'key':k,'verdict':'PASS','reason':'Toàn bộ thông tin có nguồn trích dẫn phù hợp.',
            'source_evidence':[{'unit_id':'U0001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}],
            'artifact_evidence':[{'item_id':'001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}]} for k in ['attribution','no_invented_events','honest_ending']]
    provider=Provider([{'checks':checks[:10]},{'checks':checks[10:]},{'mode_checks':modes}]*2)
    review=source_review(provider,bible,script)
    assert valid_source_review(bible,review,script)
    assert len(provider.prompts)==6
    first_batch = json.JSONDecoder().raw_decode(provider.prompts[0].split('\nDATA: ',1)[1])[0]
    second_batch = json.JSONDecoder().raw_decode(provider.prompts[1].split('\nDATA: ',1)[1])[0]
    assert set(first_batch['artifact']) == {f'{i:03}' for i in range(1,11)}
    assert set(second_batch['artifact']) == {'011'}
    assert TEXT in first_batch['whole_work_context']  # context remains available
    assert all(len(r['checks'])==11 and len(r['fact_check_requests'])==2 for r in review['reviews'])
    incomplete=source_review(Provider([{'checks':checks[:9]}]*2),bible,script)
    assert incomplete['status']=='ERROR' and incomplete['passes']==0


def test_indexed_story_quote_is_anchored_to_actual_list_field():
    from apps.script_factory.semantic_review import review_story_bible_logic
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},
                    structured_clues=[{'clue':'Lan thấy cuốn sổ cũ trên bàn.','what_it_proves':'Một khoản tiền chưa được giải thích.'}])
    response={'issues':[{'rule':'UNRESOLVED_SETUP','field':'structured_clues[0].what_it_proves',
                        'quote':'Một khoản tiền chưa được giải thích.', 'problem':'Chưa có cảnh giải thích khoản tiền.',
                        'fix':'Bổ sung giải thích trong hồi kết.','confidence':'high'}]}
    result=review_story_bible_logic(bible,lambda *args:(json.dumps(response,ensure_ascii=False),1,1))
    assert result['status']=='RUN' and len(result['issues'])==1 and not result['dropped_unanchored']


@pytest.mark.parametrize('field,quote,valid',[
    ('key_scenes','Lan kiểm tra từng hóa đơn trong cuốn sổ.',True),
    ('key_scenes','Lan bù khoản thiếu bằng tiền của mình.',False),
    ('nonexistent_scene','Lan kiểm tra từng hóa đơn trong cuốn sổ.',False),
])
def test_source_story_audit_resolves_real_skeleton_alias_only(service,field,quote,valid):
    from apps.script_factory.semantic_review import review_story_bible_logic
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},
                    narrative_skeleton={'key_scenes':[{'action':'Lan kiểm tra từng hóa đơn trong cuốn sổ.'}]},
                    adaptation_context=context)
    response={'issues':[],'audit_checks':[
        {'category':category,'verdict':'PASS','reason':'Đã kiểm tra tình huống trong cảnh theo cốt truyện.',
         'evidence':[{'field':field,'quote':quote}]}
        for category in ('timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese')]}
    result=review_story_bible_logic(bible,lambda *args:(json.dumps(response,ensure_ascii=False),1,1),_require_grounding=True)
    assert (result['status']=='RUN')==valid
    if valid:
        assert result['passes']==2 and result['grounding_verified']
        assert result['audit_checks'][0]['evidence'][0]['field']=='narrative_skeleton.key_scenes'
        assert result['audit_checks'][0]['evidence'][0]['reported_field']=='key_scenes'


@pytest.mark.parametrize('variant', ['unique', 'ambiguous', 'paraphrase', 'invented_field'])
def test_source_skeleton_alias_resolves_only_one_exact_leaf(service, variant):
    from apps.script_factory.semantic_review import review_story_bible_logic, story_bible_content_hash
    _, context = selected(service)
    quote = 'Lan chủ động làm dư ngoài số lượng khách đã xác nhận.'
    skeleton = {'task_design': {'choice_cost': 'Lan mất tiền nguyên liệu do tự làm thêm.'},
                'key_scenes': [{'decision': quote}]}
    if variant == 'ambiguous':
        skeleton['concrete_instance'] = {'decision': quote}
    bible = StoryBible('EPNEW', 'Đơn đầu tiên', {}, narrative_skeleton=skeleton, adaptation_context=context)
    before = story_bible_content_hash(bible)
    ref = {'field': 'task_design', 'quote': quote}
    if variant == 'paraphrase': ref['quote'] = 'Lan đã chủ động làm dư ngoài số khách xác nhận.'
    if variant == 'invented_field': ref['field'] = 'nonexistent_scene'
    checks = [dict(category=c, verdict='PASS', reason='Đã đối chiếu quyết định và hậu quả được kể trong cảnh.',
        evidence=[ref.copy()]) for c in ('timeline', 'setup_payoff', 'evidence_scope', 'knowledge_source', 'vietnamese')]
    review = review_story_bible_logic(bible, lambda *a: (json.dumps({'issues': [], 'audit_checks': checks}, ensure_ascii=False), 1, 1), _require_grounding=True)
    assert (review['status'] == 'RUN') is (variant == 'unique')
    assert story_bible_content_hash(bible) == before
    if variant == 'unique':
        evidence = review['audit_checks'][0]['evidence'][0]
        assert evidence['field'] == 'narrative_skeleton.key_scenes[0].decision'
        assert evidence['reported_field'] == 'task_design' and evidence['quote'] == quote


def test_source_metadata_records_gemini_actual_fallback():
    from apps.script_factory.adaptation import metadata
    provider=SimpleNamespace(provider_name='gemini',default_model='requested',last_used_model='fallback')
    data=metadata(provider,'parent','explicit-request')
    assert data['requested_model']=='explicit-request' and data['actual_model']=='fallback'
    assert data['parent_generation_request_id']=='parent'


def test_life_hook_not_required_to_contain_mystery_keywords():
    from apps.script_factory.story_logic_v3 import ScriptProseQCV3Engine
    segments=[ScriptSegment(id='001',text='Lan vừa khóa cửa thì thấy tiền trong ngăn kéo ít hơn con số bàn giao. Cô cầm ví rồi dừng lại.')]
    bible=SimpleNamespace(adaptation_context={'brief':{'adaptation_mode':'IMPROVE_OWN_SCRIPT'}})
    auditor=ScriptProseQCV3Engine()
    assert not auditor._check_hook_pacing(segments,bible)
    assert auditor._check_hook_pacing(segments)


def test_source_single_pass_outline_keeps_payoffs_without_two_part_requirement(service):
    from apps.script_factory.scene_outline import build_scene_outline
    from apps.script_factory.story_contract import payoff_obligations
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},
                    ending='Lan sửa sổ và cùng chủ cửa hàng ký bàn giao.',adaptation_context=context)
    scenes=[{'title':f'Cảnh {i}','action':f'Lan kiểm tra mục {i} trong sổ cuối ca.',
             'role':'HOOK' if i==1 else 'PAYOFF' if i==8 else 'DEVELOPMENT',
             'state_before':f'Chưa xác minh mục {i}', 'state_after':f'Đã xác minh mục {i}', 'listener_question':'Khoản lệch do đâu?',
             'new_information':f'Một chi tiết mới {i}.','consequence':'Lan thực hiện bước kiểm tra tiếp theo.',
             'payoff_ids':[o['id'] for o in payoff_obligations(bible)] if i==8 else [],
             'payoff_action':'Lan sửa sổ và cùng chủ cửa hàng ký bàn giao.' if i==8 else ''}
            for i in range(1,9)]
    call=lambda *args:(json.dumps({'scenes':scenes},ensure_ascii=False),1,1)
    assert len(build_scene_outline(bible,call,require_contract=True))==8
    scenes[-1]['payoff_ids']=[]
    assert build_scene_outline(bible,call,require_contract=True) is None
    scenes[-1]['payoff_ids']=[o['id'] for o in payoff_obligations(bible)]
    bible.adaptation_context=None
    assert build_scene_outline(bible,call) is None  # native two-call contract retained


def test_source_prop_guard_distinguishes_idioms_but_keeps_real_object_gate(service):
    from apps.script_factory.story_qc import StoryQCEngine
    from apps.script_factory.story_contract import physical_prop_mention
    for prop,text in [('khăn','khó khăn'),('ảnh','ảnh hưởng'),('thư','thư viện'),('ví','ví dụ'),('hộp','hộp thoại')]:
        start=text.index(prop)
        assert not physical_prop_mention(prop,text,start,start+len(prop))
        real='Lan lấy chiếc '+prop+' trên bàn.'
        start=real.index(prop)
        assert physical_prop_mention(prop,real,start,start+len(prop))
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Bảng công việc',protagonist={'name':'An'},
                    timeline=['An hỏi người sử dụng về các bước thao tác.'],ending='An hoàn thành bản thử nghiệm.',
                    narrative_skeleton={'trigger':'An đối mặt với khó khăn khi người dùng không hiểu thao tác.'},
                    adaptation_context=context)
    assert 'UNRESOLVED_CORE_PROP' not in StoryQCEngine().audit_story_bible(bible).rule_codes
    bible.narrative_skeleton['trigger']='An tìm thấy chiếc khăn tay trên bàn.'
    assert 'UNRESOLVED_CORE_PROP' in StoryQCEngine().audit_story_bible(bible).rule_codes


def test_private_ip_and_mixed_dns_are_rejected():
    for addresses in [['127.0.0.1'], ['10.1.1.1'], ['::1'], ['1.1.1.1','192.168.1.1']]:
        with patch('socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6,'',(ip,443)) for ip in addresses]):
            with pytest.raises(ValueError): public_address('https://example.com/article')


@pytest.mark.parametrize('url',['file:///x','http://localhost:8765','http://a:b@example.com','https://example.com:5000'])
def test_unsafe_url_scheme_credentials_and_ports(url):
    with pytest.raises(ValueError): public_address(url)


def test_redirect_destination_rechecked_and_connection_pinned():
    from apps.script_factory.source_intake import fetch_public
    response=SimpleNamespace(status=302,getheader=lambda name,default=None:'http://127.0.0.1/' if name=='Location' else default)
    connection=SimpleNamespace(sock=None,request=lambda *a,**k:None,getresponse=lambda:response,close=lambda:None)
    def dns(host,*a,**k):
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1' if host=='example.com' else '127.0.0.1',80))]
    with patch('socket.getaddrinfo',side_effect=dns), patch('socket.create_connection') as connect, patch('http.client.HTTPConnection',return_value=connection):
        with pytest.raises(ValueError): fetch_public('http://example.com/a')
        assert connect.call_args.args[0] == ('1.1.1.1',80)
        assert connect.call_count == 1


def test_rolling_subtitles_dedup_only_adjacent_overlap():
    text='WEBVTT\n\n00:00.000 --> 00:01.000\nLan mở sổ để kiểm tra\n\n00:00.800 --> 00:02.000\nđể kiểm tra số tiền\n\n00:20.000 --> 00:22.000\nLan mở sổ để kiểm tra'
    units=subtitle_units(text)
    assert [u['text'] for u in units] == ['Lan mở sổ để kiểm tra','số tiền','Lan mở sổ để kiểm tra']
    assert units[-1]['start_sec']==20


def test_youtube_single_video_only():
    assert youtube_url('https://youtu.be/abcdefghijk?list=playlist')=='https://www.youtube.com/watch?v=abcdefghijk'
    assert youtube_url('https://www.youtube.com/shorts/abcdefghijk')=='https://www.youtube.com/watch?v=abcdefghijk'
    for url in ['https://youtube.com/@channel/videos','https://youtube.com/playlist?list=x']:
        with pytest.raises(ValueError):youtube_url(url)


def test_youtube_no_captions_does_not_generate_fake_transcript():
    with patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'title':'Video','duration':60}))):
        with pytest.raises(ValueError,match='không tự nhận dạng'):read_youtube('https://youtu.be/abcdefghijk')


def test_manual_captions_preferred_in_requested_language():
    info={'title':'Video','subtitles':{'vi':[{'ext':'vtt','url':'https://example.com/manual'}]},
          'automatic_captions':{'vi':[{'ext':'vtt','url':'https://example.com/auto'}]},'duration':50}
    captions='WEBVTT\n\n00:00.000 --> 00:30.000\n'+TEXT
    with patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(info))), patch('apps.script_factory.source_intake.fetch_public',return_value=(captions.encode(),'text/vtt','url')) as fetch:
        data=read_youtube('https://youtu.be/abcdefghijk')
        assert data['caption_kind']=='MANUAL'; assert fetch.call_args.args[0].endswith('/manual')


def test_revision_preserves_original_and_invalidates_brief(service):
    source,context=selected(service)
    new=service.confirm('EPNEW',source['source_id'],TEXT+' Sau đó Lan về nhà.',1)
    assert new['revision']==2
    assert (service.folder('EPNEW',source['source_id'])/'history'/'1'/'extracted.txt').read_text(encoding='utf-8')==TEXT
    with pytest.raises(ValueError):assert_context(service.project('EPNEW'),context)


def test_metadata_confirmation_without_content_change_keeps_lineage(service):
    source,context=selected(service)
    service.confirm('EPNEW',source['source_id'],TEXT,1)
    assert_context(service.project('EPNEW'),context)


def test_stale_revision_and_selection_rejected(service):
    source,context=selected(service)
    with pytest.raises(ValueError):service.confirm('EPNEW',source['source_id'],TEXT,9)
    with pytest.raises(ValueError):service.select('EPNEW','DIRECTION_1','wrong-request')
    assert_context(service.project('EPNEW'),context)


def test_tampered_source_units_do_not_pass(service):
    from studio.backend.services.source_service import write_json
    source,context=selected(service)
    write_json(service.folder('EPNEW',source['source_id'])/'units.json',{'units':[{'unit_id':'U0001','text':'Changed content'}]})
    with pytest.raises(ValueError):current_context(service.project('EPNEW'))


def test_source_path_cannot_escape_workspace(service):
    with pytest.raises(ValueError):service.project('../EPNEW')
    with pytest.raises(ValueError):service.folder('EPNEW','../project.json')


def test_concurrent_jobs_idempotent_and_restart_failed(service):
    started,finish=threading.Event(),threading.Event()
    def work():started.set();finish.wait(2);return {'done':True}
    first=service.start('EPNEW','intake',{'url':'a'},work);started.wait(1)
    second=service.start('EPNEW','intake',{'url':'a'},work)
    assert first['job_id']==second['job_id']
    with pytest.raises(ValueError):service.start('EPNEW','intake',{'url':'b'},work)
    restart=SourceService(service.root,lambda **kw:None)
    assert restart.job('EPNEW',first['job_id'])['status']=='FAILED'
    finish.set()


def test_job_start_failure_releases_capacity_and_thread_failure_is_retryable(service):
    with patch('studio.backend.services.source_service.write_json',side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError):service.start('EPNEW','intake',{'url':'a'},lambda:None)
    assert service.slots.acquire(False) and service.slots.acquire(False)
    service.slots.release();service.slots.release()
    with patch('threading.Thread.start',side_effect=RuntimeError('thread unavailable')):
        with pytest.raises(RuntimeError):service.start('EPNEW','intake',{'url':'a'},lambda:None)
    assert service.state('EPNEW')['jobs'][0]['status']=='FAILED'
    assert service.slots.acquire(False) and service.slots.acquire(False)
    service.slots.release();service.slots.release()


def test_analysis_rejects_misquoted_source_then_retries(service):
    source=confirmed(service)
    bad={'theme':'Công sở','claims':[{'claim_id':'C1','statement':'Lan kiểm tra sổ','support_status':'SUPPORTED','evidence_refs':[{'unit_id':'U0001','quote':'Lan nhặt được chiếc ví'}]}]}
    good=json.loads(json.dumps(bad));good['claims'][0]['evidence_refs'][0]['quote']='Lan làm việc ở một cửa hàng nhỏ.'
    provider=Provider([bad,good]);result=analyze_source(provider,source)
    assert result['source_hash']==source['content_hash'];assert len(provider.prompts)==2


def test_analysis_locates_exact_cross_caption_quotes_without_retry():
    # The production failure: complete sentences span U0007/U0008 and U0010/U0011.
    units = [
        {'unit_id':'U0007','text':'Level 1 sinh viên market đỉ. Bạn sinh ra ở một'},
        {'unit_id':'U0008','text':'tỉnh nhỏ miền Bắc, nhà thì nghèo mà có đến tận sáu cái miệng trầu trực ăn.'},
        {'unit_id':'U0010','text':'Bố mẹ làm ruộng và vất vả. Bạn'},
        {'unit_id':'U0011','text':'là con gái cả trong nhà, nhìn bố mẹ vất vả và ba đứa em sơ xác.'}]
    refs = [{'unit_id':'U0008','quote':'Bạn sinh ra ở một tỉnh nhỏ miền Bắc, nhà thì nghèo'},
            {'unit_id':'U0011','quote':'Bạn là con gái cả trong nhà'}]
    payload = {'theme':'Góc khuất nghề nghiệp','claims':[{'claim_id':'C001',
        'statement':'Nguồn kể hoàn cảnh gia đình.', 'support_status':'ATTRIBUTED_CLAIM',
        'evidence_refs':refs}]}
    source = {'units':units, 'content_hash':'current-hash', 'revision':1}
    provider = Provider([payload])
    result = analyze_source(provider, source)
    actual = result['claims'][0]['evidence_refs']
    from apps.script_factory.adaptation import validate_refs
    assert validate_refs(actual, units)
    assert [r['unit_id'] for r in actual] == ['U0007','U0008','U0010','U0011']
    assert actual[0]['original_quote'] == refs[0]['quote']
    assert actual[2]['original_quote'] == refs[1]['quote']
    assert actual[0]['source_span_unit_ids'] == ['U0007','U0008']
    assert len(provider.prompts) == 1
    assert result['source_hash'] == 'current-hash'


@pytest.mark.parametrize('quote,units', [
    ('Bạn sinh ra ở một tỉnh nhỏ miền Nam', [
        {'unit_id':'U1','text':'Bạn sinh ra ở một'}, {'unit_id':'U2','text':'tỉnh nhỏ miền Bắc.'}]),
    ('Bạn sinh ra ở một tỉnh nhỏ miền Bắc', [
        {'unit_id':'U1','text':'Bạn sinh ra ở một'}, {'unit_id':'U2','text':'Ngày khác đã tới.'},
        {'unit_id':'U3','text':'tỉnh nhỏ miền Bắc.'}]),
    ('Bạn sinh ra ở một tỉnh nhỏ miền Bắc', [
        {'unit_id':'U1','text':'Bạn sinh ra ở một'}, {'unit_id':'U2','text':'tỉnh nhỏ miền Bắc.'},
        {'unit_id':'U3','text':'Bạn sinh ra ở một'}, {'unit_id':'U4','text':'tỉnh nhỏ miền Bắc.'}]),
])
def test_analysis_still_rejects_invented_noncontiguous_or_ambiguous_caption_evidence(quote, units):
    payload = {'theme':'Nghề nghiệp','claims':[{'claim_id':'C1','statement':'Lời kể',
        'support_status':'ATTRIBUTED_CLAIM','evidence_refs':[{'unit_id':'U2','quote':quote}]}]}
    provider = Provider([payload, payload])
    with pytest.raises(ValueError, match='evidence_refs không khớp'):
        analyze_source(provider, {'units':units, 'content_hash':'hash', 'revision':1})
    assert len(provider.prompts) == 2
    assert 'Các đoạn gốc để sửa' in provider.prompts[1]


def test_analysis_corrects_unique_wrong_unit_id():
    units = [{'unit_id':'U1','text':'Lan kiểm tra lại sổ thu chi.'},
             {'unit_id':'U2','text':'Hạnh mang hàng tới cửa hàng.'}]
    provider = Provider([{'theme':'Cửa hàng','claims':[{'claim_id':'C1',
        'statement':'Lan kiểm tra sổ.', 'support_status':'ATTRIBUTED_CLAIM',
        'evidence_refs':[{'unit_id':'U2','quote':units[0]['text']}]}]}])
    result = analyze_source(provider, {'units':units, 'content_hash':'hash', 'revision':1})
    assert result['claims'][0]['evidence_refs'][0]['unit_id'] == 'U1'
    assert result['claims'][0]['evidence_refs'][0]['reported_unit_id'] == 'U2'
    assert len(provider.prompts) == 1


def test_analysis_expands_unique_short_cue_fragment_but_keeps_strict_quote_gate():
    from apps.script_factory.adaptation import canonicalize_source_refs, validate_refs
    units = [{'unit_id':'U0016','text':'Bạn đỗ vào một trường ở Hà'},
             {'unit_id':'U0017','text':'Nội, ngành marketing. Bạn chọn ngành này không phải vì đam mê.'}]
    refs = [{'unit_id':'U0017','quote':'Nội, ngành marketing.'}]
    assert not validate_refs(refs, units)
    canonicalize_source_refs(refs, units)
    assert validate_refs(refs, units)
    assert refs[0]['original_quote'] == 'Nội, ngành marketing.'
    assert refs[0]['quote'] == units[1]['text']
    for ref, source_units in [
        ({'unit_id':'U0016','quote':'Nội, ngành marketing.'}, units),
        ({'unit_id':'U0017','quote':'Nội, ngành kỹ thuật.'}, units),
        ({'unit_id':'U0017','quote':'Nội, ngành marketing.'}, units + [dict(units[1],unit_id='U0018')]),
        ({'unit_id':'U0017','quote':'ngành marketing.'}, units),
    ]:
        bad = [ref]
        canonicalize_source_refs(bad, source_units)
        assert not validate_refs(bad, source_units)


def test_fiction_writer_does_not_receive_original_transcript(service):
    source,context=selected(service)
    prompt=writer_context(context)
    assert TEXT not in prompt;assert 'source_units' not in prompt;assert 'Công sở' in prompt


def test_factual_writer_preserves_source_context(service):
    source,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    assert TEXT in writer_context(context);assert 'Không bịa thoại' in writer_context(context)


@pytest.mark.parametrize('bad_words',[400,1054])
def test_source_writer_retries_duration_mismatch_and_keeps_real_lineage(service,bad_words):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},
                    adaptation_context=context,generation_request_id='parent-story')
    bad={'segments':[{'text':'từ '*bad_words,'delivery_profile':'ENDING'}]}
    good={'segments':[{'text':'từ '*50,'delivery_profile':'NORMAL'} for _ in range(15)]
                       +[{'text':'từ '*55+'Hẹn gặp lại quý vị.','delivery_profile':'ENDING'}]}
    provider=Provider([bad,good])
    script,_,_=write_adapted_script(provider,bible)
    assert script.total_words==810 and len(provider.prompts)==2
    assert str(bad_words) in provider.prompts[1] and '810' in provider.prompts[1]
    assert script.parent_generation_request_id=='parent-story'
    assert script.host['voice_id']=='020' and script.prompt_version.endswith('-writer-v14-causal-decisions')


def test_source_writer_fails_after_bounded_duration_retry(service):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},adaptation_context=context)
    bad={'segments':[{'text':'từ '*1054,'delivery_profile':'ENDING'}]}
    provider=Provider([bad,bad])
    with pytest.raises(ValueError,match='sau một lần thử lại'):
        write_adapted_script(provider,bible)
    assert len(provider.prompts)==2


def test_source_writer_normalizes_reflection_labels_without_editing_text(service):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},
                    adaptation_context=context,generation_request_id='current-story')
    segments=[{'text':'diễn biến '*25,'delivery_profile':'normal'} for _ in range(14)]
    segments += [{'text':'Lan ghi lại khoản thu đúng. ' * 10,'delivery_profile':' ENDING '},
                 {'text':'Cảm ơn bạn đã theo dõi. Hẹn gặp lại trong tập sau. ' * 4,'delivery_profile':'comment'}]
    expected=[s['text'] for s in segments]
    provider=Provider([{'segments':segments}])
    script,_,_=write_adapted_script(provider,bible)
    assert [s.text for s in script.segments]==expected
    assert [s.delivery_profile for s in script.segments][-2:]==['COMMENT','ENDING']
    assert sum(s.delivery_profile=='ENDING' for s in script.segments)==1
    assert len(provider.prompts)==1 and script.parent_generation_request_id=='current-story'


@pytest.mark.parametrize('last_profile,last_text',[
    ('NORMAL','Lan còn đang đi đến cửa hàng.'),
    ('ENDING','Cảm ơn bạn đã theo dõi. Hẹn gặp lại trong tập sau.'),
])
def test_source_writer_cannot_hide_real_early_goodbye_and_reports_budget_too(service,last_profile,last_text):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={},adaptation_context=context)
    bad={'segments':[{'text':'Cảm ơn bạn đã theo dõi. Hẹn gặp lại trong tập sau.','delivery_profile':'ENDING'},
                     {'text':last_text,'delivery_profile':last_profile}]}
    provider=Provider([bad,bad])
    with pytest.raises(ValueError,match='sau một lần thử lại'):
        write_adapted_script(provider,bible)
    assert 'lời chào kết thật trước cuối tập' in provider.prompts[1]
    assert 'từ/2 đoạn' in provider.prompts[1] and '810' in provider.prompts[1]
    assert len(provider.prompts)==2


def test_source_writer_missing_ending_without_goodbye_is_not_relabelled(service):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={},adaptation_context=context)
    bad={'segments':[{'text':'từ '*810,'delivery_profile':'NORMAL'}]}
    provider=Provider([bad,bad])
    with pytest.raises(ValueError,match='đúng một ENDING'):
        write_adapted_script(provider,bible)
    assert len(provider.prompts)==2


def test_writer_retries_label_only_close_before_publishing_real_provider_prose(service):
    _,context=selected(service)
    bible=StoryBible('EPNEW','Tập',{},adaptation_context=context)
    bad={'segments':[{'text':'diễn biến '*400+'Lan cất cuốn sổ sau buổi học.', 'delivery_profile':'ENDING'}]}
    good={'segments':[{'text':bad['segments'][0]['text']+' Hẹn gặp lại quý vị.', 'delivery_profile':'ENDING'}]}
    provider=Provider([bad,good])
    result,_,_=write_adapted_script(provider,bible)
    assert len(provider.prompts)==2 and 'nhãn ENDING không đủ' in provider.prompts[1]
    assert result.segments[-1].text==good['segments'][0]['text']
    assert 'Hẹn gặp lại' not in bad['segments'][0]['text']  # No mechanical template insertion.


def test_source_repair_preserves_natural_close_and_never_inserts_broadcast_template(service):
    from apps.script_factory.script_qc import apply_targeted_repairs
    from apps.script_factory.adaptation import source_closing_issues
    from apps.script_factory.models import QCReport
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={},adaptation_context=context)
    script=FullScript(episode_id='EPNEW',title='Tập',host={},adaptation_context=context,segments=[
        ScriptSegment(id='001',text='Lan thực sự đóng khoản học phí bằng công sức của mình.'),
        ScriptSegment(id='002',text='Cảm ơn các bạn đã theo dõi. Hẹn gặp lại trong tập sau.',delivery_profile='ENDING')])
    original=[s.text for s in script.segments]
    repaired=apply_targeted_repairs(script,bible,QCReport(episode_id='EPNEW',status='NEEDS_REVISION'),allow_prose_templates=False)
    assert [s.text for s in repaired.segments]==original and len(repaired.segments)==2
    assert not source_closing_issues(repaired)
    repaired.segments[-1].text='Lan đặt cuốn sổ cạnh tài liệu học nghề.'
    apply_targeted_repairs(repaired,bible,QCReport(episode_id='EPNEW',status='NEEDS_REVISION'),allow_prose_templates=False)
    assert len(repaired.segments)==2
    assert 'MISSING_FINAL_SIGNOFF' in {i['rule'] for i in source_closing_issues(repaired)}


def test_source_closing_repair_targets_real_segment_and_skips_review_failure(service):
    from apps.script_factory.adaptation import source_closing_issues
    from apps.script_factory.segment_rewriter import collect_flagged_segments
    from apps.script_factory.models import QCReport
    _,context=selected(service)
    script=FullScript(episode_id='EPNEW',title='Tập',host={},adaptation_context=context,segments=[
        ScriptSegment(id='001',text='Lan kiểm tra khoản thu và đóng học phí.'),
        ScriptSegment(id='002',text='Lan cất cuốn sổ. Cảm ơn các bạn đã theo dõi, hẹn gặp lại.',delivery_profile='COMMENT'),
        ScriptSegment(id='003',text='Cảm ơn quý vị đã lắng nghe. Xin chào và hẹn gặp lại.',delivery_profile='ENDING')])
    issues=source_closing_issues(script)
    assert len(issues)==1 and issues[0]['rule']=='DUPLICATE_SIGNOFF' and issues[0]['segment_id']=='002'
    qc=QCReport(episode_id='EPNEW',status='NEEDS_REVISION',evidence_issues=issues+[
        {'rule':'SEMANTIC_REVIEW_FAILED','segment_id':'001','severity':'CRITICAL','message':'Quote sai ở review.'}])
    flagged=collect_flagged_segments(script,qc)
    assert set(flagged)=={'002'}
    script.adaptation_context=None
    assert '002' not in collect_flagged_segments(script,qc)  # native deterministic broadcast repair retained


def test_long_source_writer_allocates_contiguous_scenes_and_one_final_closure(service):
    _,context=selected(service);context['brief']['target_duration_sec']=1200
    bible=StoryBible(episode_id='EPNEW',title='Tập dài',protagonist={},adaptation_context=context,
                    generation_request_id='same-story',scene_outline=[{'no':i,'title':f'Cảnh {i}',
                    'action':f'Việc {i}','new_information':f'Tin {i}','consequence':f'Kết quả {i}',
                    'segments':5} for i in range(1,9)])
    parts=[{'segments':[{'text':f'cụm{i} '*810,'delivery_profile':'NORMAL'}]} for i in range(4)]
    parts[-1]['segments'][0]['delivery_profile']='ENDING'
    parts[-1]['segments'][0]['text']='cụm3 '*805+'Hẹn gặp lại quý vị.'
    provider=Provider(parts)
    script,inp,out=write_adapted_script(provider,bible)
    assert script.total_words==3240 and script.writer_strategy=='source_scene_batches'
    assert inp==40 and out==40 and script.parent_generation_request_id=='same-story'
    assert len(provider.prompts)==4
    for i,prompt in enumerate(provider.prompts):
        group=json.loads(prompt.split('CẢNH ĐƯỢC GIAO: ')[1].split('\nPHẦN TRƯỚC')[0])
        assert [s['no'] for s in group]==[2*i+1,2*i+2]
        assert ('không lời chào kết' if i<3 else 'Cụm cuối giải quyết cảnh được giao') in prompt
    assert 'cụm0' in provider.prompts[-1]  # continuity context carries actual accepted prose
    assert TEXT not in provider.prompts[-1]  # fiction writer never gets the transcript


def test_long_source_writer_does_not_publish_or_continue_after_failed_batch(service):
    _,context=selected(service);context['brief']['target_duration_sec']=1200
    bible=StoryBible(episode_id='EPNEW',title='Tập dài',protagonist={},adaptation_context=context,
                    scene_outline=[{'no':i,'title':'Cảnh','action':'Việc','new_information':'Tin','segments':5} for i in range(1,9)])
    premature={'segments':[{'text':'Cảm ơn bạn đã theo dõi. Hẹn gặp lại trong tập sau.','delivery_profile':'ENDING'}]}
    provider=Provider([premature,premature])
    with pytest.raises(ValueError,match='lời chào kết thật trước cuối tập'):
        write_adapted_script(provider,bible)
    assert len(provider.prompts)==2


def test_long_source_writer_requires_outline_before_any_completion(service):
    _,context=selected(service);context['brief']['target_duration_sec']=1200
    provider=Provider([])
    with pytest.raises(ValueError,match='dàn cảnh'):
        write_adapted_script(provider,StoryBible(episode_id='EPNEW',title='Tập dài',protagonist={},adaptation_context=context))
    assert not provider.prompts


def test_production_batch_retries_out_of_scope_scene_before_appending(service):
    _,context=selected(service)
    context['brief']['target_duration_sec']=1200
    scenes=[dict(no=i,title=f'Cảnh {i}',action=f'Sự kiện riêng {i}',new_information=f'Dữ kiện {i}',
                 consequence=f'Hệ quả {i}',state_before=f'Tình thế trước {i}',state_after=f'Tình thế sau {i}',
                 listener_question=f'Câu hỏi {i}',segments=3,role='HOOK' if i==1 else 'SIGNOFF' if i==8 else 'DEVELOPMENT')
            for i in range(1,9)]
    scenes[-1]['action']='FUTURE_SIGNOFF_ACTION'
    class ScopedProvider(Provider):
        def __init__(self): self.prompts=[]
        def complete_json(self,system,prompt,model=None):
            self.prompts.append(prompt)
            group=json.JSONDecoder().raw_decode(prompt.split('\nCẢNH ĐƯỢC GIAO: ',1)[1])[0]
            segments=[dict(scene_no=s['no'],text='diễn biến '* (s['word_budget']//2),
                           delivery_profile='ENDING' if s['role']=='SIGNOFF' else 'NORMAL') for s in group]
            for item in segments:
                if item['delivery_profile']=='ENDING':
                    item['text']=' '.join(item['text'].split()[:-5])+' Hẹn gặp lại quý vị.'
            if len(self.prompts)==1:
                segments[0]['scene_no']=8
            return json.dumps({'segments':segments},ensure_ascii=False),10,10
    provider=ScopedProvider()
    bible=StoryBible(episode_id='NEW',title='Tập dài',protagonist={},adaptation_context=context,scene_outline=scenes)
    script,_,_=write_adapted_script(provider,bible)
    assert 'scene_no' in provider.prompts[1] and 'thuộc đúng cảnh được giao' in provider.prompts[1]
    assert 'FUTURE_SIGNOFF_ACTION' not in provider.prompts[0]
    assert len(script.segments)==8 and script.prompt_version.endswith('writer-v14-causal-decisions')


def test_known_scene_roles_normalize_delivery_without_changing_or_approving_prose():
    from apps.script_factory.adaptation import normalize_source_delivery_profiles, source_closing_issues
    items=[dict(text='Lan làm rõ phần việc mình phụ trách.',delivery_profile=role)
           for role in ['SETUP','DEVELOPMENT','ESCALATION','DECISION','PAYOFF','REFLECTION','SIGNOFF','UNSUPPORTED']]
    originals=[s['text'] for s in items]
    normalize_source_delivery_profiles(items)
    assert [s['delivery_profile'] for s in items]==['NORMAL']*5+['COMMENT','COMMENT','UNSUPPORTED']
    assert [s['text'] for s in items]==originals
    script=FullScript('NEW','t',{},segments=[ScriptSegment(id='001',text=items[0]['text'],delivery_profile='ENDING')])
    assert 'MISSING_FINAL_SIGNOFF' in {i['rule'] for i in source_closing_issues(script)}


def test_ten_minute_writer_scopes_duration_and_single_reflection_close(service):
    _,context=selected(service)
    context['brief']['target_duration_sec']=600
    roles=['HOOK','SETUP','DEVELOPMENT','ESCALATION','DECISION','PAYOFF','REFLECTION']
    scenes=[dict(no=i,role=role,title=f'Cảnh {i}',action=f'Việc riêng {i}',
                 state_before=f'Trước {i}',state_after=f'Sau {i}',listener_question=f'Hỏi {i}',
                 new_information=f'Tin {i}',segments=3,consequence=f'Kết {i}')
            for i,role in enumerate(roles,1)]
    class ScopedProvider(Provider):
        def __init__(self): self.prompts=[]
        def complete_json(self,system,prompt,model=None):
            self.prompts.append(prompt)
            group=json.JSONDecoder().raw_decode(prompt.split('\nCẢNH ĐƯỢC GIAO: ',1)[1])[0]
            items=[dict(scene_no=s['no'],text='diễn biến '*(s['word_budget']//2),
                        delivery_profile='ENDING' if s['role']=='REFLECTION' else 'NORMAL') for s in group]
            for item in items:
                if item['delivery_profile']=='ENDING':
                    item['text']=' '.join(item['text'].split()[:-5])+' Hẹn gặp lại quý vị.'
            return json.dumps({'segments':items},ensure_ascii=False),10,10
    provider=ScopedProvider()
    bible=StoryBible('NEW','Tập mười phút',{},adaptation_context=context,scene_outline=scenes,
                    narrative_skeleton={'concrete_instance':{'obstacle':'TASK_MECHANISM_SENTINEL'},
                                        'key_scenes':[{'action':'FUTURE_SCENE_SENTINEL'}]})
    script,_,_=write_adapted_script(provider,bible)
    assert script.writer_strategy=='source_scene_batches'
    assert len(provider.prompts)>=3
    assert 'trả đúng 1 item' in provider.prompts[-1]
    assert 'gộp một lời chào ngắn' in provider.prompts[-1]
    assert 1377<=script.total_words<=1863
    assert len(script.segments)==len(scenes)
    assert all('TASK_MECHANISM_SENTINEL' in p for p in provider.prompts)
    assert all('FUTURE_SCENE_SENTINEL' not in p for p in provider.prompts)


def test_short_production_writer_rejects_multiple_reflections_before_publication(service):
    _,context=selected(service)
    context['brief']['target_duration_sec']=300
    roles=['HOOK','DEVELOPMENT','PAYOFF','REFLECTION','SIGNOFF']
    scenes=[dict(no=i,role=role,title=f'Cảnh {i}',action=f'Việc {i}',new_information=f'Tin {i}',
                 segments=3,consequence=f'Kết {i}') for i,role in enumerate(roles,1)]
    class WholeProvider(Provider):
        def __init__(self): self.prompts=[]
        def complete_json(self,system,prompt,model=None):
            self.prompts.append(prompt)
            group=json.JSONDecoder().raw_decode(prompt.split('CẢNH VÀ NGÂN SÁCH: ',1)[1])[0]
            segments=[dict(scene_no=s['no'],text='diễn biến '* (s['word_budget']//2),
                          delivery_profile='ENDING' if s['role']=='SIGNOFF' else 'NORMAL') for s in group]
            for item in segments:
                if item['delivery_profile']=='ENDING':
                    item['text']=' '.join(item['text'].split()[:-5])+' Hẹn gặp lại quý vị.'
            if len(self.prompts)==1:
                segments.insert(-1,dict(scene_no=4,text='bài học đã nói '*8,delivery_profile='COMMENT'))
            return json.dumps({'segments':segments},ensure_ascii=False),10,10
    provider=WholeProvider()
    script,_,_=write_adapted_script(provider,StoryBible('NEW','Tập ngắn',{},adaptation_context=context,scene_outline=scenes))
    assert len(provider.prompts)==2 and 'chỉ một đoạn' in provider.prompts[1]
    assert len(script.segments)==5 and script.writer_strategy=='source_single_pass'


def test_short_whole_script_with_sole_reflection_has_one_combined_final_item(service):
    _,context=selected(service);context['brief']['target_duration_sec']=300
    roles=['HOOK','DEVELOPMENT','PAYOFF','REFLECTION']
    scenes=[dict(no=i,role=role,title=f'Cảnh {i}',action=f'Việc {i}',new_information=f'Tin {i}',
                 segments=3,consequence=f'Kết {i}') for i,role in enumerate(roles,1)]
    class WholeProvider(Provider):
        def complete_json(self,system,prompt,model=None):
            assert 'phần khép lại trả đúng 1 item' in prompt
            assert 'đây là ngoại lệ cho quy tắc REFLECTION dùng COMMENT' in prompt
            group=json.JSONDecoder().raw_decode(prompt.split('CẢNH VÀ NGÂN SÁCH: ',1)[1])[0]
            items=[dict(scene_no=s['no'],text='diễn biến '*(s['word_budget']//2),
                        delivery_profile='ENDING' if s['role']=='REFLECTION' else 'NORMAL') for s in group]
            items[-1]['text']=' '.join(items[-1]['text'].split()[:-5])+' Hẹn gặp lại quý vị.'
            return json.dumps({'segments':items},ensure_ascii=False),10,10
    script,_,_=write_adapted_script(WholeProvider([]),StoryBible('NEW','t',{},adaptation_context=context,scene_outline=scenes))
    assert len(script.segments)==4 and script.segments[-1].delivery_profile=='ENDING'


def test_closing_json_split_coalesces_without_altering_words_or_hiding_bad_signoffs():
    from apps.script_factory.adaptation import normalize_source_closing_segments
    scenes=[dict(no=2,role='REFLECTION',word_budget=60)]
    parts=[dict(scene_no=2,text='Vy đặt chiếc hộp cơm lên bàn.',delivery_profile='COMMENT'),
           dict(scene_no='2',text='Cảm ơn quý vị đã lắng nghe. Hẹn gặp lại.',delivery_profile='ENDING')]
    original=' '.join(s['text'] for s in parts)
    normalize_source_closing_segments(parts,scenes)
    assert len(parts)==1 and parts[0]['text']==original and parts[0]['delivery_profile']=='ENDING'
    for first in ['Hẹn gặp lại.', 'từ '*70]:
        invalid=[dict(scene_no=2,text=first,delivery_profile='COMMENT'),
                 dict(scene_no=2,text='Hẹn gặp lại.',delivery_profile='ENDING')]
        normalize_source_closing_segments(invalid,scenes)
        assert len(invalid)==2  # No hidden early goodbye or over-budget text.


def test_closing_budget_is_a_ceiling_not_a_quota_to_pad(service):
    _,context=selected(service);context['brief']['target_duration_sec']=600
    roles=['HOOK','DEVELOPMENT','ESCALATION','PAYOFF','SIGNOFF']
    scenes=[dict(no=i,role=role,title=f'Cảnh {i}',action=f'Việc {i}',
                 new_information=f'Tin {i}',segments=3,consequence=f'Kết {i}') for i,role in enumerate(roles,1)]
    class ProviderWithBriefGoodbye(Provider):
        def complete_json(self,system,prompt,model=None):
            self.prompts.append(prompt)
            group=json.JSONDecoder().raw_decode(prompt.split('\nCẢNH ĐƯỢC GIAO: ',1)[1])[0]
            items=[dict(scene_no=s['no'],text='Hẹn gặp lại.' if s['role']=='SIGNOFF' else 'diễn biến '*(s['word_budget']//2),
                        delivery_profile='ENDING' if s['role']=='SIGNOFF' else 'NORMAL') for s in group]
            return json.dumps({'segments':items},ensure_ascii=False),10,10
    provider=ProviderWithBriefGoodbye([])
    script,_,_=write_adapted_script(provider,StoryBible('NEW','t',{},adaptation_context=context,scene_outline=scenes))
    assert script.segments[-1].text=='Hẹn gặp lại.'
    assert len(provider.prompts)==3 and 1377<=script.total_words<=1863


def test_source_location_contradiction_requires_both_real_scene_quotes(service):
    from apps.script_factory.semantic_review import review_script_logic
    _,context=selected(service)
    bible=StoryBible('NEW','t',{},adaptation_context=context)
    script=FullScript('NEW','t',{},segments=[
        ScriptSegment(id='001',text='Khách đến cửa hàng nhận chiếc quạt. Lan đặt quạt lên quầy.'),
        ScriptSegment(id='002',text='Trước khi rời khỏi nhà khách, Lan trao hóa đơn cho anh.')])
    issue=dict(rule='OBJECT_CONTINUITY_CONTRADICTION',segment_id='002',quote=script.segments[1].text,
               comparison_evidence=[dict(segment_id='001',quote=script.segments[0].text)],
               problem='Cùng lần bàn giao nhưng nơi gặp chuyển từ cửa hàng sang nhà khách.',
               fix='Giữ địa điểm cửa hàng cho lần bàn giao đã kể.',confidence='high')
    checks=[dict(category=category,verdict='PASS',reason='Đã đối chiếu nội dung thực của hai cảnh.',
                 evidence=[dict(segment_id='001',quote=script.segments[0].text)])
            for category in ['timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese']]
    def run(finding):
        def call(system,prompt):
            assert 'hai địa điểm mâu thuẫn trong cùng lần gặp/bàn giao' in prompt.lower()
            return json.dumps(dict(issues=[finding],audit_checks=checks),ensure_ascii=False),1,1
        return review_script_logic(script,bible,call,_require_grounding=True)
    result=run(issue)
    assert result['issues'][0]['blocking'] and result['issues'][0]['related_segment_ids']==['001']
    assert not result.get('grounding_verified')  # A verified defect never authorizes approval.
    for comparison in [[], [dict(segment_id='001',quote='Lan đến nhà khách bàn giao quạt.')]]:
        invalid=run({**issue,'comparison_evidence':comparison})
        assert not invalid['issues'] and not invalid['grounding_verified'] and invalid['status']=='ERROR'


def test_source_mode_ref_normalization_preserves_failure_and_rejects_paraphrase(service):
    from apps.script_factory.adaptation import validate_source_mode_checks, source_review_keys
    _,context=selected(service)
    context['units']=[{'unit_id':'U0001','text':'Lan kiểm tra khoản tiền ghi nhầm trong sổ.'},
                      {'unit_id':'U0002','text':'Hà cùng Lan lập kế hoạch chi tiêu.'}]
    checks=[{'key':key,'verdict':'FAIL','reason':'Có phần nội dung lặp lại cần sửa đúng theo nguồn.',
             'source_evidence':[{'unit_id':'U0002','quote':'Lan kiểm tra khoản tiền ghi nhầm trong sổ.'}],
             'artifact_evidence':[{'item_id':'001','quote':'Lan kiểm tra khoản tiền ghi nhầm trong sổ.'}]}
            for key in source_review_keys(context)]
    validate_source_mode_checks(checks,context,{'001':context['units'][0]['text']})
    assert all(c['verdict']=='FAIL' and c['source_evidence'][0]['reported_unit_id']=='U0002' for c in checks)
    checks[0]['source_evidence']=[{'unit_id':'U0001','quote':'Lan tìm thấy khoản tiền bị nhập sai.'}]
    with pytest.raises(ValueError,match='original_structure.*source_evidence') as exc:
        validate_source_mode_checks(checks,context,{'001':context['units'][0]['text']})
    assert 'actual_unit_text' in str(exc.value) and context['units'][0]['text'] in str(exc.value)


def test_missing_source_reference_gets_real_context_feedback_without_accepting_absence(service):
    from apps.script_factory.adaptation import validate_source_mode_checks, source_review_keys
    _,context=selected(service)
    context['units']=[{'unit_id':'U0001','text':'Lan kiểm tra khoản tiền ghi nhầm trong sổ.'}]
    checks=[dict(key=k,verdict='PASS',reason='Nguồn không có lời thoại nên không sao chép câu thoại.',
        source_evidence=[],artifact_evidence=[dict(item_id='001',quote='Lan kiểm tra khoản tiền ghi nhầm trong sổ.')])
        for k in source_review_keys(context)]
    with pytest.raises(ValueError,match='Ví dụ cách COPY') as error:
        validate_source_mode_checks(checks,context,{'001':context['units'][0]['text']})
    assert 'U0001' in str(error.value) and context['units'][0]['text'] in str(error.value)


def test_source_review_range_id_requires_unique_quote_inside_valid_range(service):
    from apps.script_factory.semantic_review import review_script_logic
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={},adaptation_context=context)
    script=FullScript(episode_id='EPNEW',title='Tập',host={},segments=[
        ScriptSegment(id='001',text='Lan mở lại cuốn sổ để kiểm tra học phí.'),
        ScriptSegment(id='002',text='Hà gọi lại cho Lan để hỏi về việc học.'),
        ScriptSegment(id='003',text='Lan sửa bản thiết kế và gửi lại cho khách hàng.')])
    def result(reported,quote,bible=bible):
        finding={'rule':'REPEATED_DISCOVERY','segment_id':reported,'quote':quote,
                 'problem':'Cùng một việc bị kể lại ở cuối cảnh.','fix':'Viết hệ quả mới.','confidence':'high'}
        return review_script_logic(script,bible,lambda *a:(json.dumps({'issues':[finding]}),5,7))
    review=result('001-002',script.segments[0].text)
    issue=review['issues'][0]
    assert review['status']=='RUN' and issue['blocking'] and issue['segment_id']=='001'
    assert issue['reported_segment_id']=='001-002' and issue['related_segment_ids']==['002']
    for reported,quote in [('001-002',script.segments[2].text),('001-004',script.segments[0].text),
                           ('001-002','Lan kiểm tra số tiền học phí trong sổ.')]:
        invalid=result(reported,quote)
        assert invalid['status']=='ERROR' and not invalid['issues']
    script.segments[1].text=script.segments[0].text
    assert result('001-002',script.segments[0].text)['status']=='ERROR'
    native=StoryBible(episode_id='EPNEW',title='Tập',protagonist={})
    assert result('001-002',script.segments[0].text,bible=native)['status']=='ERROR'


def test_models_round_trip_source_context(service):
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},adaptation_context=context)
    assert StoryBible.from_dict(bible.to_dict()).adaptation_context==context
    script=FullScript(episode_id='EPNEW',title='Tập',host={'name':'Minh'},adaptation_context=context)
    assert FullScript.from_dict(script.to_dict()).adaptation_context==context


def test_profile_qc_does_not_require_reveal_or_three_audience_questions(service):
    from apps.script_factory.script_qc import ScriptQCEngine
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ thu chi',protagonist={'name':'Lan'},ending='Lan sửa lại sổ.',adaptation_context=context)
    script=FullScript(episode_id='EPNEW',title='Sổ thu chi',host={'name':'Minh'},segments=[ScriptSegment(id='001',text=TEXT,delivery_profile='HOOK'),ScriptSegment(id='002',text='Xin chào và hẹn gặp lại.',delivery_profile='ENDING')])
    report=ScriptQCEngine.audit_script(script,bible)
    assert not any('Missing REVEAL' in x for x in report.logic_issues)
    assert not any('Audience interaction count' in x for x in report.repetition_issues)
    assert report.status!='PASS'  # source reviewer is unavailable, do not weaken gate


def test_source_review_incomplete_coverage_fail_closed(service):
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    bible=StoryBible(episode_id='EPNEW',title='Sổ thu chi',protagonist={'name':'Lan'},adaptation_context=context)
    script=FullScript(episode_id='EPNEW',title='Tập',host={},segments=[ScriptSegment(id='001',text=TEXT)])
    provider=Provider([{'checks':[],'mode_checks':[]},{'checks':[],'mode_checks':[]}])
    result=source_review(provider,bible,script)
    assert result['status']=='ERROR';assert result['passes']==0


def test_source_edit_during_analysis_cannot_save_current(service):
    source=confirmed(service)
    analysis={'theme':'Công sở','generation_request_id':'a','source_hash':source['content_hash'],'source_revision':1}
    def edit(*args):
        service.confirm('EPNEW',source['source_id'],TEXT+' Lan nghỉ một ngày.',1)
        return {'directions':[]}
    service.providers=lambda **kw:SimpleNamespace(requires_grounded_review=True,complete_json=lambda *a:None)
    with patch('apps.script_factory.adaptation.analyze_source',return_value=analysis),patch('apps.script_factory.adaptation.generate_directions',side_effect=edit):
        with pytest.raises(ValueError,match='Nguồn đổi'):service.directions('EPNEW',source['source_id'],{'adaptation_mode':'FICTION_FROM_THEME','target_duration_sec':300})
    assert not (service.project('EPNEW')/'adaptation'/'directions.json').exists()


def test_source_script_cannot_silently_rewrite_approved_story(service):
    from studio.backend.services.generation_service import GenerationService
    from studio.backend.services.source_service import write_json
    _,context=selected(service)
    bible=StoryBible(episode_id='EPNEW',title='Sổ cuối ca',protagonist={'name':'Lan'},adaptation_context=context)
    story=service.project('EPNEW')/'story/story_bible.json'
    write_json(story,bible.to_dict())
    project=service.project('EPNEW')/'project.json'
    meta=read_json(project);meta['stage_statuses']['02_story']='APPROVED';write_json(project,meta)
    from studio.backend.services.artifact_lineage import story_content_hash
    before=story_content_hash(read_json(story))
    manager=object.__new__(GenerationService)
    manager.get_provider=lambda **kw:SimpleNamespace(provider_name='openai_compatible',default_model='test')
    report=SimpleNamespace(status='FAIL',rule_codes=['UNRESOLVED_SETUP'],logic_issues=['Ending lacks the promised answer.'],
        to_dict=lambda:{'status':'FAIL','rule_codes':['UNRESOLVED_SETUP'],'logic_issues':['Ending lacks the promised answer.']})
    with patch('studio.backend.services.generation_service.PROJECTS_DIR',service.root), \
         patch('apps.script_factory.story_qc.StoryQCEngine.audit_story_bible',return_value=report), \
         patch('apps.script_factory.story_qc.StoryQCEngine.repair_story_bible') as repair:
        with pytest.raises(ValueError,match='không tự thay cốt truyện'):
            manager.generate_full_script('EPNEW')
    repair.assert_not_called()
    assert story_content_hash(read_json(story))==before and not (service.project('EPNEW')/'script/full_script.json').exists()
    assert read_json(story)['story_qc_report']['status']=='FAIL'
    assert read_json(service.project('EPNEW')/'story_bible.json')['story_qc_report']['status']=='FAIL'
    assert read_json(project)['stage_statuses']['02_story']=='NEEDS_REVIEW'


@pytest.mark.parametrize('verdict', ['FAIL', 'ERROR'])
def test_source_auto_repair_checks_story_before_rewriting_prose(service, verdict):
    from studio.backend.services.generation_service import GenerationService
    from studio.backend.services.source_service import write_json
    from studio.backend.services.artifact_lineage import story_content_hash
    _, context = selected(service)
    bible = StoryBible('EPNEW', 'Đơn hàng', {'name': 'Lan'}, adaptation_context=context,
                      generation_request_id='story-request', generation_source='REAL_AI')
    story = service.project('EPNEW') / 'story/story_bible.json'
    write_json(story, bible.to_dict())
    before = story_content_hash(read_json(story))
    script = FullScript('EPNEW', 'Đơn hàng', {}, segments=[ScriptSegment('001', text=TEXT)],
                        generation_source='REAL_AI', generation_request_id='script-request')
    original = {**script.to_dict(), 'source_story_generation_request_id': bible.generation_request_id,
                'source_story_content_hash': before}
    script_path = service.project('EPNEW') / 'script/full_script.json'
    write_json(script_path, original)
    manager = object.__new__(GenerationService)
    manager.get_provider = lambda **kw: SimpleNamespace(provider_name='openai_compatible', default_model='test')
    report = SimpleNamespace(status=verdict, rule_codes=['UNFOUNDED_EVIDENCE_LEAP'],
        logic_issues=['Quy trách nhiệm mâu thuẫn với quyết định đã xác nhận.'],
        to_dict=lambda: {'status': verdict, 'rule_codes': ['UNFOUNDED_EVIDENCE_LEAP']})
    with patch('studio.backend.services.generation_service.PROJECTS_DIR', service.root), \
         patch('apps.script_factory.story_qc.StoryQCEngine.audit_story_bible', return_value=report), \
         patch('apps.script_factory.story_qc.StoryQCEngine.repair_story_bible') as story_repair, \
         patch('studio.backend.services.generation_service.ScriptQCEngine') as script_qc:
        with pytest.raises(ValueError, match='Mở Cốt truyện'):
            manager.auto_repair_script('EPNEW')
    story_repair.assert_not_called()
    script_qc.assert_not_called()
    assert story_content_hash(read_json(story)) == before
    assert read_json(story)['story_qc_report']['status'] == verdict
    assert read_json(service.project('EPNEW') / 'story_bible.json')['story_qc_report']['status'] == verdict
    saved = read_json(script_path)
    assert saved['segments'] == original['segments'] and saved['generation_request_id'] == 'script-request'
    assert saved['artifact_status'] == 'STALE'
    assert read_json(service.project('EPNEW') / 'project.json')['stage_statuses']['02_story'] == 'NEEDS_REVIEW'


def test_saved_review_cannot_be_reused_after_script_edit(service):
    from apps.script_factory.adaptation import source_artifact, source_review_keys, valid_source_review
    _, context = selected(service)
    bible = StoryBible(episode_id='EPNEW', title='Sổ thu chi', protagonist={'name':'Lan'}, adaptation_context=context)
    script = FullScript(episode_id='EPNEW', title='Tập', host={}, segments=[ScriptSegment(id='001',text=TEXT)])
    payload = {'checks':[], 'mode_checks':[
        {'key':key, 'verdict':'PASS','reason':'Câu chuyện khác, giữ chủ đề kiểm tra sổ sách.',
         'source_evidence':[{'unit_id':'U0001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}],
         'artifact_evidence':[{'item_id':'001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}]}
        for key in source_review_keys(context)]}
    review = source_review(Provider([payload,payload]), bible, script)
    assert valid_source_review(bible, review, script)
    assert len(source_artifact(bible, script)) == 1
    assert all(r['prompt_version'] == review['version'] for r in review['reviews'])
    old_policy_review = {**review, 'version': 'source-adaptation-v1'}
    assert not valid_source_review(bible, old_policy_review, script)
    script.segments[0].text += ' Một người khác bước vào.'
    assert not valid_source_review(bible, review, script)


def test_own_review_requires_each_lock_and_failed_lock_blocks(service):
    from apps.script_factory.adaptation import source_review_keys, valid_source_review
    _, context = selected(service)
    context['brief'].update(adaptation_mode='IMPROVE_OWN_SCRIPT',locked_elements=['Lan sửa đúng sổ.','Cuối tháng xác nhận số tiền.'])
    bible = StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},adaptation_context=context)
    script = FullScript(episode_id='EPNEW',title='Tập',host={},segments=[ScriptSegment(id='001',text=TEXT)])
    payload = {'checks':[], 'mode_checks':[
        {'key':key,'verdict':'FAIL' if key=='lock_2' else 'PASS','reason':'Đối chiếu canon và nội dung đã khóa của tác phẩm.',
         'source_evidence':[{'unit_id':'U0001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}],
         'artifact_evidence':[{'item_id':'001','quote':'Lan làm việc ở một cửa hàng nhỏ.'}]}
        for key in source_review_keys(context)]}
    review = source_review(Provider([payload,payload]),bible,script)
    assert review['passes']==2 and len(review['issues'])==2
    assert not valid_source_review(bible,review,script)
    payload['mode_checks']=payload['mode_checks'][1:]
    review=source_review(Provider([payload,payload]),bible,script)
    assert review['status']=='ERROR'


def test_source_api_intake_confirm_upload_and_validation(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from studio.backend.source_routes import make_source_router
    app=FastAPI()
    app.include_router(make_source_router(service.root,SimpleNamespace(get_provider=lambda **kw:None),None,None))
    client=TestClient(app)
    assert client.post('/api/projects/EPNEW/sources',json={'text':TEXT,'url':'https://example.com'}).status_code==400
    response=client.post('/api/projects/EPNEW/sources',json={'text':TEXT})
    assert response.status_code==200
    sid=response.json()['source']['source_id']
    assert client.post(f'/api/projects/EPNEW/sources/{sid}/confirm',json={'text':TEXT,'expected_revision':9}).status_code==400
    assert client.post(f'/api/projects/EPNEW/sources/{sid}/confirm',json={'text':TEXT,'expected_revision':1}).json()['status']=='CONFIRMED'
    assert client.post('/api/projects/EPNEW/sources/upload',files={'file':('bad.txt',b'\xff','text/plain')}).status_code==400
    assert client.post('/api/projects/EPNEW/sources/upload',files={'file':('story.txt',TEXT.encode(),'text/plain')}).status_code==200
    assert client.post('/api/projects/EPNEW/adaptation/generate/story',json={}).status_code==400


def test_windows_atomic_publication_retries_reader_sharing_violation(tmp_path):
    from pathlib import Path
    from studio.backend.services.source_service import write_json
    real_replace=Path.replace
    attempts=[]
    def busy_once(path,target):
        attempts.append(path)
        if len(attempts)==1: raise PermissionError('WinError 5 reader sharing')
        return real_replace(path,target)
    target=tmp_path/'job.json'
    with patch.object(Path,'replace',busy_once):write_json(target,{'status':'COMPLETED'})
    assert read_json(target)['status']=='COMPLETED' and len(attempts)==2


def test_story_schema_retry_reports_all_bad_lists_and_preserves_metadata(service):
    from apps.script_factory.adaptation import create_bible
    _,context=selected(service)
    bad={'title':'Cuốn sổ cuối ca','protagonist':{'name':'Lan'},'ending':'Lan sửa đúng sổ và về nhà.',
         'timeline':['Lan kiểm tra sổ rồi sửa lại.'],'relationships':['Lan và Hạnh'], 'critical_facts':['Lan sửa sổ.']}
    good={**bad,'relationships':[],'critical_facts':[], 'narrative_skeleton':{
        'concrete_task':'Đối chiếu khoản tiền ghi nhầm trong sổ thu chi.',
        'concrete_instance':{'person':'Lan', 'wanted_outcome':'Bàn giao khoản thu cuối ca cho Hạnh.',
                             'first_attempt':'Lan đếm tiền trong ngăn kéo và so với hóa đơn.',
                             'obstacle':'Sổ tổng kết ghi một hóa đơn thanh toán sai trạng thái.',
                             'decision':'Lan báo lỗi của mình thay vì lấy tiền riêng bù.',
                             'cost':'Lan chịu trách nhiệm về việc nhập sai.',
                             'result':'Lan và Hạnh sửa đúng trạng thái rồi ký bàn giao.'},
        'task_design':{'task_object':'Khoản thu ghi nhầm trong sổ cuối ca.',
                       'observed_problem':'Bảng tổng kết không khớp số tiền trong ngăn kéo.',
                       'stakes':'Lan sợ chủ cửa hàng mất niềm tin.',
                       'choice_cost':'Lan chấp nhận báo lỗi do mình nhập sai.',
                       'change_action':'Lan sửa trạng thái thanh toán rồi ký bàn giao với Hạnh.',
                       'observable_result':'Số tiền và bảng tổng kết khớp, cả hai ký bàn giao.'},
        'key_scenes':[{'action':'Lan đối chiếu hóa đơn với số tiền trong ngăn kéo.',
                       'obstacle':'Một hóa đơn ghi sai trạng thái thanh toán.',
                       'decision':'Lan báo lỗi cho chủ cửa hàng thay vì bù tiền.',
                       'consequence':'Hạnh cùng Lan sửa đúng khoản thu trong sổ.'} for _ in range(3)]}}
    # Untrusted model output cannot choose the mode, provenance or approval.
    good.update(adaptation_context={'brief':{'adaptation_mode':'FACTUAL_RETELLING'}},
                generation_source='MOCK',generation_request_id='injected-request',artifact_status='APPROVED')
    provider=Provider([bad,good])
    bible=create_bible(provider,'EPNEW',context)
    assert 'relationships phải' in provider.prompts[-1] and 'critical_facts phải' in provider.prompts[-1]
    assert bible.requested_model==provider.default_model and bible.actual_model==provider.default_model
    assert StoryBible.from_dict(bible.to_dict()).parent_generation_request_id=='request1'
    assert bible.adaptation_context['brief']['adaptation_mode']=='FICTION_FROM_THEME'
    assert bible.generation_source=='REAL_AI' and bible.generation_request_id!='injected-request'
    assert read_json(service.project('EPNEW')/'project.json')['stage_statuses']['03_script']=='STALE'


@pytest.mark.parametrize('alias', ['what_it_does_NOT_prove','what_it_does_not_prove'])
def test_story_clue_field_alias_and_resolved_question_preserve_evidence(service,alias):
    from apps.script_factory.adaptation import create_bible
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    clue={'clue':'Hóa đơn ghi tổng số tiền.', 'what_it_proves':'Số tiền ghi trên hóa đơn.',
          alias:'Không chứng minh tiền đã được thanh toán.', 'next_question':''}
    data={'title':'Hóa đơn','protagonist':{'name':'Lan'},'ending':'Nguồn chưa xác nhận thanh toán.',
          'timeline':['Lan đọc hóa đơn.'],'structured_clues':[clue]}
    provider=Provider([data])
    bible=create_bible(provider,'EPNEW',context)
    assert len(provider.prompts)==1
    assert bible.structured_clues==[{**{k:v for k,v in clue.items() if k!=alias},
        'what_it_does_NOT_prove':'Không chứng minh tiền đã được thanh toán.'}]


@pytest.mark.parametrize('bad_clue', [
    {'clue':'Hóa đơn ghi tổng số tiền.','what_it_proves':'Số tiền ghi trên hóa đơn.'},
    {'clue':'Hóa đơn ghi tổng số tiền.','what_it_proves':'Số tiền ghi trên hóa đơn.',
     'what_it_does_NOT_prove':'Không chứng minh thanh toán.','what_it_does_not_prove':'Đã thanh toán.','next_question':''}])
def test_story_clue_rejects_missing_limits_or_conflicting_aliases(service,bad_clue):
    from apps.script_factory.adaptation import create_bible
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    data={'title':'Hóa đơn','protagonist':{'name':'Lan'},'ending':'Nguồn chưa xác nhận thanh toán.',
          'timeline':['Lan đọc hóa đơn.'],'structured_clues':[bad_clue]}
    provider=Provider([data,data])
    with pytest.raises(ValueError,match=r'structured_clues\[0\]'):
        create_bible(provider,'EPNEW',context)
    assert 'structured_clues[0]' in provider.prompts[-1]


def test_factual_outline_does_not_force_action_or_80_segments(service):
    from apps.script_factory.story_contract import payoff_obligations
    from apps.script_factory.scene_outline import build_scene_outline
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},ending='Nguồn chưa cho biết kết quả.',adaptation_context=context)
    assert 'Không bịa' in payoff_obligations(bible)[0]['question']
    prompts=[]
    def call(system,prompt):
        prompts.append(system)
        return json.dumps({'scenes':[{'no':i,'part':1 if i<5 else 2,'title':str(i),'action':f'Trình bày sự kiện {i} có nguồn','new_information':'Thông tin mới có nguồn','consequence':'Cách hiểu thay đổi', 'role':'HOOK' if i==1 else 'PAYOFF' if i==8 else 'DEVELOPMENT', 'state_before':f'Chưa đọc sự kiện {i}', 'state_after':f'Đã đọc sự kiện {i}', 'listener_question':'Nguồn xác nhận gì?', 'payoff_ids':['ending'],'payoff_action':'Nguồn chưa cho biết kết quả'} for i in range(1,9)]}),1,1
    assert build_scene_outline(bible,call,require_contract=True)
    assert 'dài khoảng 80' not in prompts[0]


def test_short_story_metadata_quote_retries_report_without_changing_story(service):
    from apps.script_factory.semantic_review import review_story_bible_logic, story_bible_content_hash
    _, context = selected(service)
    bible = StoryBible(episode_id='EPNEW', title='Phòng nhỏ', protagonist={'name':'Lan'},
        time_period='Đương đại', timeline=['Lan sửa chiếc quạt rồi bàn giao thiết bị cho khách hàng.'],
        adaptation_context=context)
    before = story_bible_content_hash(bible)
    calls = []
    def call(system, prompt):
        calls.append(prompt)
        evidence = {'field':'time_period','quote':'Đương đại'} if len(calls)==1 else {
            'field':'timeline','quote':bible.timeline[0]}
        checks = [dict(category=c, verdict='PASS', reason='Đã đọc và đối chiếu các sự kiện cụ thể trong cốt truyện.',
            evidence=[evidence]) for c in ('timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese')]
        return json.dumps({'issues':[],'audit_checks':checks},ensure_ascii=False), 1, 1
    result = review_story_bible_logic(bible, call, _require_grounding=True)
    assert result['status']=='RUN' and result['passes']==2 and result['grounding_verified']
    assert len(calls)==3 and 'BỎ reference' in calls[1]
    assert story_bible_content_hash(bible)==before


@pytest.mark.parametrize('provider_class', ['openai','gemini'])
def test_source_repair_providers_pass_actual_issues(service,provider_class):
    from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
    from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider
    _,context=selected(service)
    cls=OpenAICompatibleProvider if provider_class=='openai' else GeminiScriptAIProvider
    provider=object.__new__(cls)
    bible=StoryBible(episode_id='EPNEW',title='Tập',protagonist={'name':'Lan'},adaptation_context=context)
    issues=[{'rule':'UNRESOLVED_SETUP','message':'Chi tiết chưa được giải thích.'}]
    with patch('apps.script_factory.adaptation.create_bible',return_value=bible) as create:
        result,_,_=provider.repair_story_bible(bible,issues)
    assert result is bible and create.call_args.args[3]['issues']==issues


def test_factual_story_prompt_and_prop_gate_use_source_profile(service):
    from apps.script_factory.story_qc import StoryQCEngine
    from apps.script_factory.semantic_review import build_story_bible_prompt
    _,context=selected(service);context['brief']['adaptation_mode']='FACTUAL_RETELLING'
    bible=StoryBible(episode_id='EPNEW',title='Tủ quần áo miễn phí',protagonist={'name':'Tổ hợp cộng đồng'},
                    timeline=['Tủ quần áo miễn phí phục vụ người cần đồ.'],
                    narrative_skeleton={'trigger':'Chiếc áo được trao cho người cần đồ.'},
                    ending='Nguồn chưa cho biết việc mở rộng.',adaptation_context=context)
    prompt=build_story_bible_prompt(bible)
    assert 'Nhân vật gửi thư (góc nhìn duy nhất)' not in prompt
    report=StoryQCEngine().audit_story_bible(bible)
    assert 'UNRESOLVED_CORE_PROP' not in report.rule_codes
    assert 'CAUSAL_GAP' not in report.rule_codes
    before=bible.to_dict()
    repaired=StoryQCEngine().repair_story_bible(bible,report)
    for key in ('causal_chains','knowledge_ledger','structured_clues','reveal_justifications'):
        assert repaired.to_dict()[key]==before[key]
    bible.adaptation_context=None
    assert 'CAUSAL_GAP' in StoryQCEngine().audit_story_bible(bible).rule_codes
