import json

import pytest

from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.narrative_design import scene_word_budgets, scene_batches, outline_design_errors, payment_payoff_missing, event_state_matches
from apps.script_factory.semantic_review import review_script_logic


def outline():
    roles = ['HOOK', 'SETUP', 'DEVELOPMENT', 'ESCALATION', 'DECISION', 'PAYOFF', 'REFLECTION', 'SIGNOFF']
    return [dict(no=i, role=role, action=f'Việc {i}', state_before=f'Trước {i}', state_after=f'Sau {i}',
                 listener_question='Việc tiếp theo có hệ quả gì?') for i, role in enumerate(roles, 1)]


@pytest.mark.parametrize('total', [810, 1620, 3240, 4050, 9720])
def test_budget_preserves_total_and_funds_events_instead_of_closing(total):
    scenes = outline()
    sizes = scene_word_budgets(scenes, total)
    assert sum(sizes) == total
    assert sum(sizes[-2:]) <= total * .08
    assert sizes[5] > sum(sizes[-2:])  # Actual payoff remains funded.
    groups = scene_batches(scenes, total)
    assert sum(b for _, b in groups) == total
    assert [s['no'] for group, _ in groups for s in group] == list(range(1, 9))
    assert all(s['word_budget'] == sizes[s['no']-1] for group, _ in groups for s in group)


def test_short_episode_funds_combined_reflection_and_signoff_without_padding():
    from apps.script_factory.narrative_design import validate_scene_assignment
    scenes = outline()[:-1]  # No separate SIGNOFF: reflection must close the show.
    sizes = scene_word_budgets(scenes, 810)
    assert sizes[-1] == 60 and sum(sizes) == 810
    assert sizes[-1] <= 810 * .08 and sizes[5] > sizes[-1]
    assigned = [{**s, 'word_budget': size} for s, size in zip(scenes, sizes)]
    segments = [dict(scene_no=s['no'], text=' '.join(['từ'] * (62 if s['role']=='REFLECTION' else size)))
                for s,size in zip(scenes,sizes)]
    validate_scene_assignment(segments, assigned)
    segments[-1]['text'] = ' '.join(['từ'] * 100)
    with pytest.raises(ValueError, match='vượt ngân sách'):
        validate_scene_assignment(segments, assigned)


@pytest.mark.parametrize('total', [100, 300, 810, 4050])
def test_closing_reservation_never_exceeds_cap_or_starves_body(total):
    sizes = scene_word_budgets(outline()[:-1], total)
    assert sum(sizes) == total and sizes[-1] <= int(total * .08)
    assert sizes[5] > sizes[-1]


def test_outline_rejects_same_event_and_no_state_change_before_writer():
    scenes = outline()
    assert not outline_design_errors(scenes)
    scenes[3]['action'] = scenes[2]['action']
    scenes[4]['state_after'] = scenes[4]['state_before']
    assert len(outline_design_errors(scenes)) == 2


def test_closing_can_preserve_completed_state_without_inventing_another_event():
    scenes = outline()
    for s in scenes[-2:]:
        s['state_after'] = s['state_before']
    assert not outline_design_errors(scenes)
    scenes[5]['state_after'] = scenes[5]['state_before']
    assert outline_design_errors(scenes) == ['Cảnh không đổi tình thế: 6']


@pytest.mark.parametrize('omit_second', [False, True])
def test_bound_ending_ids_preserve_bible_actions_and_require_complete_coverage(omit_second):
    bible = StoryBible(episode_id='NEW',title='Chìa khóa',protagonist={},
        ending='Lan ký hợp đồng bằng thu nhập của mình, nhận chiếc chìa khóa từ chủ nhà.')
    script = FullScript(episode_id='NEW',title='Chìa khóa',host={},segments=[
        ScriptSegment(id='001',text='Lan ký hợp đồng bằng thu nhập của mình.'),
        ScriptSegment(id='002',text='Lan nhận chiếc chìa khóa từ chủ nhà.')])
    data = payload(script,bible)
    data['payoff_checks'][0]['event_checks'] = [dict(required_action_id=f'ENDING_ACTION_{i+1}',
        actual_action=segment.text,state='COMPLETED',matches_required_event=True,
        reason='Hành động đã thực hiện đúng yêu cầu và nguồn lực.',
        evidence=[dict(segment_id=segment.id,quote=segment.text)]) for i,segment in enumerate(script.segments)]
    if omit_second: data['payoff_checks'][0]['event_checks'].pop()
    result = review_script_logic(script,bible,lambda *args:(json.dumps(data,ensure_ascii=False),1,1),_require_grounding=True)
    assert bool(result['grounding_verified']) is (not omit_second)
    if not omit_second:
        assert result['payoff_checks'][0]['event_checks'][1]['required_action'] == 'nhận chiếc chìa khóa từ chủ nhà.'
    else:
        assert any(e.get('missing_required_action_ids') == ['ENDING_ACTION_2'] for e in result['invalid_evidence'])


PROMISE = 'Lan dùng thu nhập tự kiếm để đóng phần học phí tiếp theo.'


@pytest.mark.parametrize('quote,missing', [
    ('Một phần được dành cho học phí tiếp theo, phần còn lại để duy trì sinh hoạt.', True),
    ('Lan sẽ đóng học phí tiếp theo bằng khoản thu nhập mới.', True),
    ('Lan chuẩn bị thanh toán học phí tiếp theo.', True),
    ('Lan đóng học phí lần đầu bằng tiền Quang hỗ trợ.', True),
    ('Lan đã đóng học phí tiếp theo bằng tiền từ đơn hàng thiết kế.', False),
    ('Lan thanh toán học phí tiếp theo tại quầy và nhận biên lai.', False),
])
def test_real_quote_of_plan_or_previous_payment_is_not_completed_payoff(quote, missing):
    assert bool(payment_payoff_missing(PROMISE, [{'evidence': [{'quote': quote}]}])) == missing


def test_factual_unfinished_plan_must_not_be_fabricated_to_satisfy_gate():
    assert payment_payoff_missing('Lan dự định đóng học phí tiếp theo.',
                                 [{'evidence': [{'quote': 'Lan dành tiền cho học phí tiếp theo.'}]}]) is None


@pytest.mark.parametrize('required,state,allowed', [
    ('Lan bàn giao chìa khóa căn hộ.', 'PLANNED', False),
    ('Lan bàn giao chìa khóa căn hộ.', 'COMPLETED', True),
    ('Lan dự định bàn giao chìa khóa.', 'PLANNED', True),
    ('Nguồn chưa cho biết kết quả.', 'UNKNOWN', True),
    ('Nguồn chưa cho biết kết quả.', 'COMPLETED', False),
])
def test_required_event_state_preserves_completed_planned_and_unknown(required, state, allowed):
    assert event_state_matches(required, state) == allowed


def payload(script, bible, last_event=None):
    ref = lambda i: {'segment_id': script.segments[i].id, 'quote': script.segments[i].text}
    data = {'issues': [], 'audit_checks': [dict(category=c, verdict='PASS', reason='Đã đọc các sự kiện trong toàn bộ tập.',
                  evidence=[ref(0)]) for c in ('timeline', 'setup_payoff', 'evidence_scope', 'knowledge_source', 'vietnamese')],
            'payoff_checks': [dict(id='ending', verdict='PASS', answer='Lan đã dùng tiền mới để hoàn tất việc học phí.',
                setup=[ref(0)], resolution=[ref(-1)], event_checks=[dict(required_action=bible.ending, actual_action=script.segments[-1].text,
                state='COMPLETED', matches_required_event=True, reason='Đã đối chiếu đúng nhân vật và khoản học phí.', evidence=[ref(-1)])])]}
    if last_event is not None:
        data['pacing_checks'] = [dict(category=c, verdict='PASS', reason='Đã kiểm tra phần kể và đoạn kết trên nội dung thật.',
             evidence=[ref(last_event), ref(-1)], last_new_event_segment_id=script.segments[last_event].id)
             for c in ('progression', 'closing')]
    return data


def test_false_ai_pass_on_authentic_earmark_quote_becomes_repairable_defect():
    bible = StoryBible(episode_id='NEW', title='Khoản tiền', protagonist={}, ending=PROMISE)
    script = FullScript(episode_id='NEW', title='Khoản tiền', host={}, segments=[
        ScriptSegment(id='001', text='Lan nhận tiền từ đơn hàng thiết kế đầu tiên.'),
        ScriptSegment(id='002', text='Một phần được dành cho học phí tiếp theo, phần còn lại để duy trì sinh hoạt.')])
    data = payload(script, bible)
    result = review_script_logic(script, bible, lambda *args: (json.dumps(data, ensure_ascii=False), 1, 1), _require_grounding=True)
    assert result['status'] == 'RUN'
    assert any(i['rule'] == 'PAYOFF_NOT_COMPLETED' for i in result['issues'])
    assert not result['grounding_verified']


def test_normal_labels_cannot_hide_long_post_event_closing():
    bible = StoryBible(episode_id='NEW', title='Kết quả', protagonist={}, ending='Lan nhận công việc mới tại cửa hàng.')
    script = FullScript(episode_id='NEW', title='Kết quả', host={}, segments=[
        ScriptSegment(id=f'{i:03}', text=('Lan nhận công việc mới tại cửa hàng.' if i == 14 else 'Lan nghĩ về những việc đã trải qua và ý nghĩa của lựa chọn.'))
        for i in range(1, 21)])
    data = payload(script, bible, last_event=13)
    result = review_script_logic(script, bible, lambda *args: (json.dumps(data, ensure_ascii=False), 1, 1), _require_grounding=True)
    assert any(i['rule'] == 'REDUNDANT_CLOSING' for i in result['issues'])
    assert not result['grounding_verified']


def test_complete_long_episode_needs_both_independent_content_pacing_reviews():
    bible = StoryBible(episode_id='NEW', title='Kết quả', protagonist={}, ending='Lan nhận công việc mới tại cửa hàng.')
    script = FullScript(episode_id='NEW', title='Kết quả', host={}, segments=[
        ScriptSegment(id=f'{i:03}', text=('Lan nhận công việc mới tại cửa hàng.' if i == 19 else 'Cảm ơn quý vị đã lắng nghe.' if i == 20 else f'Lan xác minh chi tiết số {i} và thay đổi bước kế tiếp.'))
        for i in range(1, 21)])
    data = payload(script, bible, last_event=18)
    result = review_script_logic(script, bible, lambda *args: (json.dumps(data, ensure_ascii=False), 1, 1), _require_grounding=True)
    assert result['status'] == 'RUN' and result['passes'] == 2 and result['grounding_verified']
    assert len(result['pacing_checks_second_pass']) == 2
    del data['pacing_checks']
    result = review_script_logic(script, bible, lambda *args: (json.dumps(data, ensure_ascii=False), 1, 1), _require_grounding=True)
    assert result['status'] == 'ERROR' and not result['grounding_verified']


def test_source_second_pass_has_distinct_continuity_task_and_preserves_canon():
    bible=StoryBible('NEW','Kết quả',{},ending='Lan nhận công việc mới tại cửa hàng.',
        adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME',
            'direction':{'point_of_view':'Ngôi thứ nhất'},'locked_elements':['Không đổi việc làm']},
            'brief_hash':'brief','analysis':{}})
    script=FullScript('NEW','Kết quả',{},segments=[ScriptSegment(id=f'{i:03}',
        text=bible.ending if i==19 else 'Cảm ơn quý vị đã lắng nghe.' if i==20 else f'Lan xử lý việc số {i} và nhận kết quả mới.')
        for i in range(1,21)])
    data=payload(script,bible,last_event=18); prompts=[]
    def call(system,prompt):
        prompts.append(prompt)
        return json.dumps(data,ensure_ascii=False),1,1
    result=review_script_logic(script,bible,call,_require_grounding=True)
    assert result['passes']==2 and result['grounding_verified']
    assert 'KIỂM TRA TRÌNH TỰ ĐỘC LẬP' not in prompts[0]
    assert 'KIỂM TRA TRÌNH TỰ ĐỘC LẬP' in prompts[1]
    assert 'TRƯỚC lúc tạo ra kết quả' in prompts[1]
    assert 'Không đổi việc làm' in prompts[1] and bible.ending in prompts[1]
    assert 'payoff_obligations' in prompts[1] and '"id": "ending"' in prompts[1]
    assert all(s.text in prompts[1] for s in script.segments)


def test_permitted_short_reflection_does_not_become_false_critical_closing():
    bible = StoryBible(episode_id='NEW', title='Kết quả', protagonist={})
    script = FullScript(episode_id='NEW', title='Kết quả', host={}, segments=[
        ScriptSegment(id=f'{i:03}', text=f'Lan kiểm tra chi tiết {i} rồi tiếp tục làm công việc tiếp theo.') for i in range(1, 21)])
    response = payload(script, bible, last_event=18)
    response['payoff_checks'] = []
    response['pacing_checks'][1]['verdict'] = 'FAIL'
    response['issues'] = [dict(rule='REDUNDANT_CLOSING', segment_id='020', quote=script.segments[-1].text,
        problem='Có một đoạn chiêm nghiệm.', fix='Rút phần kết.', confidence='high')]
    result = review_script_logic(script, bible, lambda *args:(json.dumps(response,ensure_ascii=False),1,1),_require_grounding=True)
    assert result['status']=='RUN' and result['grounding_verified']
    assert not result['issues']
    assert any(i['rule']=='REDUNDANT_CLOSING' and not i['blocking'] for i in result['advisories'])


@pytest.mark.parametrize('comparison', [False, True])
def test_event_repetition_needs_both_original_and_later_quotes(comparison):
    bible = StoryBible(episode_id='NEW', title='Việc lặp', protagonist={})
    script = FullScript(episode_id='NEW', title='Việc lặp', host={}, segments=[
        ScriptSegment(id='001', text='Lan mang chiếc quạt về tiệm để kiểm tra lại.'),
        ScriptSegment(id='002', text='Lan lại mang chiếc quạt về tiệm để kiểm tra lại.')])
    issue = dict(rule='REPEATED_EVENT_NO_CHANGE', segment_id='002', quote=script.segments[-1].text,
        problem='Mang về tiệm hai lần nhưng không có lần rời tiệm giữa hai đoạn.', fix='Chuyển sang kiểm tra lỗi.', confidence='high')
    if comparison:
        issue['comparison_evidence'] = [dict(segment_id='001',quote=script.segments[0].text)]
    result = review_script_logic(script,bible,lambda *args:(json.dumps({'issues':[issue]},ensure_ascii=False),1,1))
    assert bool(result['issues']) == comparison
    assert (result['status']=='RUN') == comparison


def test_incomplete_report_with_verified_defect_can_repair_but_not_approve():
    from types import SimpleNamespace
    from apps.script_factory.models import QCReport
    from studio.backend.services.generation_service import _revise_keeping_best
    script = FullScript(episode_id='NEW',title='Lặp',host={},segments=[ScriptSegment(id='001',text='Lan mở cùng chiếc hộp lần nữa.')])
    issue = dict(rule='REPEATED_EVENT_NO_CHANGE',segment_id='001',excerpt=script.segments[0].text,
                 source='SEMANTIC_REVIEW',severity='CRITICAL',blocking=True)
    qc = QCReport('NEW','NEEDS_REVISION',evidence_issues=[issue],semantic_review={'status':'ERROR','issues':[issue]})
    calls = []
    def repair(**kwargs):
        calls.append(1)
        candidate = kwargs['script']
        candidate.revision_round += 1
        candidate.segments[0].text = 'Lan đọc nội dung bên trong chiếc hộp.'
        return candidate, QCReport('NEW','PASS',semantic_review={'status':'RUN','passes':2,'grounding_verified':True})
    result, verdict = _revise_keeping_best(SimpleNamespace(auto_revise_and_recheck=repair),script,None,qc,3)
    assert calls == [1] and result.segments[0].text != script.segments[0].text and verdict.status=='PASS'
    qc.semantic_review['issues'] = []
    calls.clear()
    result, verdict = _revise_keeping_best(SimpleNamespace(auto_revise_and_recheck=repair),script,None,qc,3)
    assert not calls and result.segments[0].text == script.segments[0].text and verdict.status!='PASS'


@pytest.mark.parametrize('ids', [[2, 4], [2, 3, 2], [2], [True, 3], [None, 3]])
def test_batch_rejects_future_scene_reentry_or_omitted_scene(ids):
    from apps.script_factory.narrative_design import validate_scene_assignment
    with pytest.raises(ValueError):
        validate_scene_assignment([dict(scene_no=n,text='Một diễn biến mới.') for n in ids],
                                  [dict(no=2),dict(no=3)])


def test_batch_closing_limit_does_not_shorten_real_payoff():
    from apps.script_factory.narrative_design import validate_scene_assignment
    scenes=[dict(no=2,role='PAYOFF',word_budget=200),dict(no=3,role='REFLECTION',word_budget=30)]
    validate_scene_assignment([dict(scene_no=2,text='sự kiện '*100),dict(scene_no=3,text='chiêm nghiệm '*15)],scenes)
    with pytest.raises(ValueError,match='vượt ngân sách'):
        validate_scene_assignment([dict(scene_no=2,text='sự kiện '*100),dict(scene_no=3,text='chiêm nghiệm '*30)],scenes)
    with pytest.raises(ValueError, match='chỉ một đoạn'):
        validate_scene_assignment([dict(scene_no=2,text='sự kiện '*100),
            dict(scene_no=3,text='chiêm nghiệm'),dict(scene_no=3,text='bài học lặp')],scenes)


def test_reflection_and_goodbye_share_closing_ceiling_without_borrowing_from_payoff():
    from apps.script_factory.narrative_design import validate_scene_assignment
    scenes=[dict(no=1,role='PAYOFF',word_budget=352),dict(no=2,role='REFLECTION',word_budget=71),
            dict(no=3,role='SIGNOFF',word_budget=35)]
    segments=[dict(scene_no=1,text='từ '*352),dict(scene_no=2,text='từ '*43),dict(scene_no=3,text='từ '*52)]
    validate_scene_assignment(segments,scenes)  # 95 of 106 closing words, despite signoff >35.
    segments[1]['text']='từ '*100
    with pytest.raises(ValueError,match='vượt ngân sách chung 106'):
        validate_scene_assignment(segments,scenes)


def test_scene_numeric_strings_are_canonicalized_but_missing_ids_report_exact_item():
    from apps.script_factory.narrative_design import validate_scene_assignment
    segments=[dict(scene_no='02',text='Việc thứ hai.'),dict(scene_no='3',text='Việc thứ ba.')]
    validate_scene_assignment(segments,[dict(no=2),dict(no=3)])
    assert [s['scene_no'] for s in segments] == [2,3]
    segments[1].pop('scene_no')
    with pytest.raises(ValueError,match="'segment_index': 2, 'returned_scene_no': None"):
        validate_scene_assignment(segments,[dict(no=2),dict(no=3)])


def test_raw_closing_issue_repairs_entire_verified_tail_not_only_last_summary():
    bible=StoryBible(episode_id='NEW',title='Kết quả',protagonist={})
    script=FullScript(episode_id='NEW',title='Kết quả',host={},segments=[
        ScriptSegment(id=f'{i:03}',text=f'Lan xác nhận chi tiết {i} rồi tiếp tục làm công việc của mình.') for i in range(1,21)])
    data=payload(script,bible,last_event=13)
    data['payoff_checks']=[]
    data['issues']=[dict(rule='REDUNDANT_CLOSING',segment_id='019',quote=script.segments[18].text,
        problem='Kết kéo dài sau sự kiện 014.',fix='Rút nhận xét.',confidence='high')]
    result=review_script_logic(script,bible,lambda *args:(json.dumps(data,ensure_ascii=False),1,1),_require_grounding=True)
    issue=next(i for i in result['issues'] if i['rule']=='REDUNDANT_CLOSING')
    assert set(issue['related_segment_ids']) == {'015','016','017','018'}


def test_invalid_ending_clause_feedback_repairs_report_only():
    bible=StoryBible(episode_id='NEW',title='Kết quả',protagonist={},ending='Lan dùng chiếc hộp đã sửa để đựng món ăn nhỏ, rồi kể chuyện cuối tuần.')
    script=FullScript(episode_id='NEW',title='Kết quả',host={},segments=[
        ScriptSegment(id='001',text='Lan dùng chiếc hộp đã sửa để đựng món ăn nhỏ và kể chuyện cuối tuần.')])
    good=payload(script,bible)
    bad=json.loads(json.dumps(good))
    bad['payoff_checks'][0]['event_checks'][0]['required_action']='Cô dùng chiếc hộp đã sửa để đựng món ăn nhỏ.'
    responses=iter([bad,good,good])
    prompts=[]
    def call(system,prompt):
        prompts.append(prompt)
        return json.dumps(next(responses),ensure_ascii=False),1,1
    result=review_script_logic(script,bible,call,_require_grounding=True)
    assert result['status']=='RUN' and result['grounding_verified'] and result['passes']==2
    assert 'invalid_required_action' in prompts[1] and bible.ending in prompts[1]
    assert script.segments[0].text.endswith('và kể chuyện cuối tuần.')


def test_duration_deficit_uses_checked_scene_writer_once_not_hook_rewrite(monkeypatch):
    from types import SimpleNamespace
    from apps.script_factory.auto_revision import AutoRevisionManager
    from apps.script_factory.models import QCReport
    import apps.script_factory.adaptation as adaptation
    import apps.script_factory.scene_outline as planning
    context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'}}
    bible=StoryBible('NEW','Tập',{},adaptation_context=context)
    script=FullScript('NEW','Tập',{},segments=[ScriptSegment('001',text='Mở cảnh đã đúng.')],
                      writer_strategy='source_single_pass',scene_outline=outline(),generation_source='REAL_AI',generated_at=1)
    qc=QCReport('NEW','NEEDS_REVISION',evidence_issues=[dict(rule='SOURCE_DURATION_MISMATCH',segment_id='001')],
                semantic_review={'grounding_verified':True})
    calls=[]
    def write(provider, planned, model):
        calls.append((planned,model))
        assert planned.scene_outline == script.scene_outline and bible.scene_outline is None
        return FullScript('NEW','Tập',{},segments=[ScriptSegment('001',text='Bản mới đủ cảnh.')],
            writer_strategy='source_single_pass',generation_source='REAL_AI'),10,20
    monkeypatch.setattr(adaptation,'write_adapted_script',write)
    monkeypatch.setattr(planning,'outline_fulfills_contract',lambda *args:True)
    def local_rewrite(**kwargs):
        raise AssertionError('A global duration defect must not be sent to the hook rewriter.')
    provider=SimpleNamespace(provider_name='openai_compatible',default_model='auto',revise_script=local_rewrite)
    manager=AutoRevisionManager(provider,SimpleNamespace(check_budget_pre_flight=lambda **kwargs:None,
        record_operation=lambda **kwargs:None),SimpleNamespace(run_qc=lambda *args,**kwargs:qc))
    result,_=manager.auto_revise_and_recheck(script,bible,qc)
    assert len(calls)==1 and result.revision_round==1 and result.writer_strategy.endswith('_duration_rebalance')
    assert result.generated_at>1 and result.generation_request_id and result.requested_model=='auto'
    with pytest.raises(ValueError,match='một lần'):
        manager.auto_revise_and_recheck(result,bible,qc)
    assert len(calls)==1


@pytest.mark.parametrize('reverse', [False,True])
def test_source_answer_in_next_sentence_requires_real_quote_order(reverse):
    bible=StoryBible(episode_id='NEW',title='Bữa ăn cuối tuần',protagonist={},clues=['Nguồn gốc chiếc hộp cơm.'],
        ending='Lan kể chuyện cùng cha trong bữa cơm.',adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'},'brief_hash':'test','analysis':{}})
    script=FullScript(episode_id='NEW',title='Hộp cơm',host={},segments=[
        ScriptSegment(id='001',text='Lan nhìn thấy chiếc hộp cơm cũ. Đó là hộp cha dùng nấu bữa sáng cho Lan hồi nhỏ.'),
        ScriptSegment(id='002',text=bible.ending)])
    data=payload(script,bible)
    refs=[dict(segment_id='001',quote=q) for q in ['Lan nhìn thấy chiếc hộp cơm cũ.','Đó là hộp cha dùng nấu bữa sáng cho Lan hồi nhỏ.']]
    if reverse: refs.reverse()
    data['payoff_checks'].insert(0,dict(id='clue_1',verdict='PASS',answer='Hộp từng dùng để chuẩn bị bữa sáng cho Lan.',setup=[refs[0]],resolution=[refs[1]]))
    data['payoff_checks'].insert(0,dict(id='title_trigger',verdict='PASS',answer='Hai cha con ăn và trò chuyện cùng nhau.',
        setup=[dict(segment_id='001',quote=script.segments[0].text)],resolution=[dict(segment_id='002',quote=script.segments[1].text)]))
    result=review_script_logic(script,bible,lambda *args:(json.dumps(data,ensure_ascii=False),1,1),_require_grounding=True)
    assert bool(result['grounding_verified']) is (not reverse)
    assert (result['status']=='RUN') is (not reverse)


@pytest.mark.parametrize('change', ['none', 'unrelated', 'anchor', 'neighbor', 'story', 'stale_hash'])
def test_random_pass_cannot_erase_unchanged_grounded_defect(change):
    import copy
    from apps.script_factory.models import QCReport
    from apps.script_factory.semantic_review import retain_unresolved_findings, script_content_hash, story_bible_content_hash
    bible=StoryBible('NEW','Phòng mới',{},ending='Lan ký hợp đồng rồi nhận chìa khóa.')
    script=FullScript('NEW','Phòng mới',{},segments=[
        ScriptSegment(str(i).zfill(3),text=text) for i,text in enumerate([
            'Lan đọc bảng giá thuê phòng.', 'Lan mang dụng cụ đến ngõ.',
            'Lan chuyển vào phòng với chìa khóa mới.',
            'Sau đó Lan ký hợp đồng thuê phòng.', 'Chủ nhà giao chìa khóa sau khi ký.',
            'Lan sắp xếp bàn làm việc.', 'Cảm ơn khán giả đã lắng nghe.'],1)])
    issue=dict(rule='ACTION_SEQUENCE_INVERSION',segment_id='003',excerpt=script.segments[2].text,
               related_segment_ids=['004','005'],severity='CRITICAL',source='SEMANTIC_REVIEW',
               message='Chuyển vào trước khi ký và nhận chìa.',recommended_action='Sửa thứ tự sự kiện.')
    prior=QCReport('NEW','NEEDS_REVISION',semantic_review=dict(issues=[issue],
        script_hash=script_content_hash(script),story_hash=story_bible_content_hash(bible)))
    candidate=copy.deepcopy(script)
    if change=='unrelated': candidate.segments[-1].text='Cảm ơn bạn đã theo dõi chương trình.'
    if change=='anchor': candidate.segments[2].text='Lan chờ ký hợp đồng rồi nhận chìa khóa.'
    if change=='neighbor': candidate.segments[1].text='Lan nhớ lại ngày đã chuyển vào căn phòng.'
    if change=='story': bible.ending='Chủ nhà giao chìa trước khi ký hợp đồng.'
    if change=='stale_hash': prior.semantic_review['script_hash']='obsolete'
    report=retain_unresolved_findings(script,prior,candidate,QCReport('NEW','PASS'),bible)
    should_retain=change in ('none','unrelated')
    assert (report.status=='NEEDS_REVISION') is should_retain
    assert bool(report.evidence_issues) is should_retain
    if should_retain:
        assert report.evidence_issues[0]['retained_unresolved']
        assert report.semantic_review['retained_unresolved_count']==1


def test_unanchored_or_editorial_findings_are_not_retained():
    from apps.script_factory.models import QCReport
    from apps.script_factory.semantic_review import retain_unresolved_findings, script_content_hash, story_bible_content_hash
    bible=StoryBible('NEW','Tập',{})
    script=FullScript('NEW','Tập',{},segments=[ScriptSegment('001',text='Lan chờ chủ nhà bàn giao chiếc chìa khóa.')])
    prior=QCReport('NEW','NEEDS_REVISION',semantic_review=dict(script_hash=script_content_hash(script),
        story_hash=story_bible_content_hash(bible),issues=[
            dict(rule='ACTION_SEQUENCE_INVERSION',segment_id='001',excerpt='Lan chuyển vào khi chưa ký hợp đồng.'),
            dict(rule='GENERIC_PHILOSOPHICAL_HOOK',segment_id='001',excerpt=script.segments[0].text)]))
    assert retain_unresolved_findings(script,prior,script,QCReport('NEW','PASS'),bible).status=='PASS'


def test_grounded_source_defect_does_not_skip_independent_continuity_pass():
    bible=StoryBible('NEW','Tập',{},ending='Lan nhận tiền công sau khi bàn giao.',
                    adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'},'brief_hash':'test','analysis':{}})
    script=FullScript('NEW','Tập',{},segments=[
        ScriptSegment('001',text='Lan nhận tiền công sau khi bàn giao.'),
        ScriptSegment('002',text='Lan kể lại nguyên vẹn việc nhận tiền công sau khi bàn giao.')])
    first=payload(script,bible)
    first['issues']=[dict(rule='REPEATED_EVENT_NO_CHANGE',segment_id='002',quote=script.segments[1].text,
        comparison_evidence=[dict(segment_id='001',quote=script.segments[0].text)],
        problem='Kể lại cùng kết quả mà không đổi tình thế.',fix='Gộp phần lặp.',confidence='high')]
    prompts=[]
    def call(system,prompt):
        prompts.append(prompt)
        return json.dumps(first,ensure_ascii=False),1,1
    result=review_script_logic(script,bible,call,_require_grounding=True)
    assert result['status']=='RUN' and result['passes']==2 and len(prompts)==2
    assert 'KIỂM TRA TRÌNH TỰ ĐỘC LẬP' in prompts[1]
    assert len(result['issues'])==1


@pytest.mark.parametrize('invented_quote', [False, True])
def test_source_decision_responsibility_finding_requires_actual_story_quote(invented_quote):
    from apps.script_factory.semantic_review import review_story_bible_logic
    bible = StoryBible('NEW', 'Đơn hàng đầu tiên', {},
        timeline=['Khách xác nhận đặt toàn bộ số hàng do mình chọn.',
                  'Người giao tự chọn số hàng và chịu mọi thiệt hại vì làm dư.'],
        ending='Hai người kiểm tra lại thỏa thuận trước lần thử tiếp theo.',
        adaptation_context={'brief': {'adaptation_mode': 'FICTION_FROM_THEME'},
                            'brief_hash': 'test', 'analysis': {}})
    finding = dict(rule='UNFOUNDED_EVIDENCE_LEAP', field='timeline',
        quote='Người giao tự chọn số hàng và chịu mọi thiệt hại vì làm dư.',
        problem='Quy trách nhiệm tự chọn lượng trái với khách đã xác nhận lượng đó.',
        fix='Làm rõ quyết định và thỏa thuận từ thiết kế, không giả định ký gửi.', confidence='high')
    if invented_quote:
        finding['quote'] = 'Người giao đã ký thỏa thuận chịu rủi ro ký gửi.'
    calls = []
    def call(system, prompt):
        calls.append(prompt)
        return json.dumps({'issues': [finding]}, ensure_ascii=False), 1, 1
    original = bible.to_dict()
    review = review_story_bible_logic(bible, call)
    assert review['status'] == ('ERROR' if invented_quote else 'RUN')
    assert bool(review['issues']) is (not invented_quote)
    assert len(calls) == (2 if invented_quote else 1)
    assert bible.to_dict() == original  # QC does not rewrite the source of the contradiction.


def test_decision_policy_keeps_factual_limits_and_checks_repeated_agreement():
    from apps.script_factory.adaptation import writer_context
    from apps.script_factory.semantic_review import build_source_continuity_prompt
    from apps.script_factory.narrative_design import DECISION_OWNERSHIP_INSTRUCTION
    context = {'brief': {'adaptation_mode': 'FACTUAL_RETELLING'}, 'brief_hash': 'test',
               'analysis': {}, 'units': []}
    bible = StoryBible('NEW', 'Tập', {}, adaptation_context=context)
    script = FullScript('NEW', 'Tập', {}, segments=[ScriptSegment('001', text='Nguồn chưa cho biết ai chịu chi phí.')])
    generation = writer_context(context)
    review = build_source_continuity_prompt(script, bible)
    assert DECISION_OWNERSHIP_INSTRUCTION in generation and DECISION_OWNERSHIP_INSTRUCTION in review
    assert 'Factual giữ điều nguồn xác nhận và điều chưa rõ' in generation
    assert 'cam kết bồi hoàn khỏi bồi hoàn đã thực hiện' in generation
    assert 'trích cả quyết định và cách quy trách nhiệm' in review
    assert 'REPEATED_EVENT_NO_CHANGE' in review
