import json
import pytest

from apps.script_factory.models import StoryBible, FullScript, ScriptSegment
from apps.script_factory.story_contract import age_facts, bible_age_conflicts, script_age_conflicts, payoff_obligations
from apps.script_factory.scene_outline import build_scene_outline, repeated_dialogue_pairs
from apps.script_factory.semantic_review import review_script_logic


def bible(age=5):
    return StoryBible(episode_id='TEST', title='Mùi nước hoa trên áo',
        protagonist={'name': 'Lan', 'description': f'Lan sống cùng chồng và con gái {age} tuổi.'},
        time_period='Hiện tại năm 2024. Con gái sinh năm 2021.',
        timeline=['Năm 2021: Con gái của Lan chào đời.'])


def script(*texts):
    return FullScript(episode_id='TEST', title='Test', host={},
        segments=[ScriptSegment(id=f'{i:03d}', text=t) for i, t in enumerate(texts, 1)])


def test_upstream_impossible_age_cannot_pass_to_writer():
    assert bible_age_conflicts(bible(5))
    assert not bible_age_conflicts(bible(3))
    assert not bible_age_conflicts(bible(2))  # birthday is unknown


@pytest.mark.parametrize('age,blocked', [('5', True), ('năm', True), ('3', False), ('ba', False), ('hai', False)])
def test_script_age_uses_calendar_not_judge_math(age, blocked):
    assert bool(list(script_age_conflicts(script(f'Lan sống cùng con gái {age} tuổi.'), bible(3)))) == blocked


@pytest.mark.parametrize('text', ['Năm 2026, con gái 5 tuổi.', 'Khi con gái 5 tuổi, Lan sẽ chuyển nhà.',
    'Lan nhớ lúc con gái 1 tuổi.', 'Lan nói: “Con gái 5 tuổi.”', 'Con gái không phải 5 tuổi.'])
def test_flashback_future_and_reported_claim_are_not_present_age(text):
    assert not list(script_age_conflicts(script(text), bible(3)))


def test_ambiguous_or_absent_present_year_is_not_guessed():
    b = bible()
    b.time_period = 'Gia đình chuyển nhà năm 2024, dự định trở lại năm 2028.'
    assert age_facts(b) == []
    b = bible()
    b.timeline.append('Năm 2020: Con gái của Lan chào đời.')
    assert age_facts(b) == []
    b = bible()
    b.time_period += ' Hai con gái sống cùng mẹ.'
    assert age_facts(b) == []


def test_named_cast_age_and_birth_year_are_checked():
    b = bible(3)
    b.protagonist = {'name': 'Lan', 'birth_year': 1992, 'age': 35}
    assert bible_age_conflicts(b)
    b.protagonist['age'] = 32
    assert not bible_age_conflicts(b)
    assert list(script_age_conflicts(script('Lan năm nay 35 tuổi.'), b))
    assert not list(script_age_conflicts(script('Lan chăm sóc mẹ 65 tuổi.'), b))


def payoff_bible():
    b = bible(3)
    b.narrative_skeleton = {'trigger': 'Chiếc áo có mùi nước hoa lạ.'}
    b.structured_clues = [{'clue': 'Mùi nước hoa trên áo', 'next_question': 'Mùi hương từ đâu?'}]
    return b


def grounded_response(s, b, resolved=True):
    checks = [{'category': c, 'verdict': 'PASS', 'reason': 'Đã đối chiếu nguyên văn kịch bản với cốt truyện.',
        'evidence': [{'segment_id': '001', 'quote': s.segments[0].text}]} for c in
        ['timeline', 'setup_payoff', 'evidence_scope', 'knowledge_source', 'vietnamese']]
    payoff = [{'id': o['id'], 'verdict': 'PASS', 'answer': 'Mai xác nhận mùi nước hoa từ chiếc áo cô mượn.',
        'setup': [{'segment_id': '001', 'quote': s.segments[0].text}],
        'resolution': [{'segment_id': '002', 'quote': s.segments[1].text}]} for o in payoff_obligations(b)]
    return {'issues': [], 'audit_checks': checks, **({'payoff_checks': payoff} if resolved else {})}


def test_broad_setup_pass_without_each_clue_answer_is_not_acceptance():
    b = payoff_bible()
    s = script('Lan nhận thấy áo của chồng có mùi nước hoa lạ.', 'Lan gấp chiếc áo rồi cất vào tủ.')
    def call(system, prompt):
        return json.dumps(grounded_response(s, b, False), ensure_ascii=False), 1, 1
    result = review_script_logic(s, b, call, _require_grounding=True)
    assert result['status'] == 'ERROR'
    assert not result['grounding_verified']


@pytest.mark.parametrize('invalid', ['missing', 'invented_quote', 'same_setup', 'duplicate'])
def test_payoff_attestation_requires_complete_later_anchored_answers(invalid):
    b = payoff_bible()
    s = script('Lan nhận thấy áo của chồng có mùi nước hoa lạ.', 'Mai nói: “Tôi mượn chiếc áo ấy tối hôm đó.”')
    response = grounded_response(s, b)
    if invalid == 'missing':
        response['payoff_checks'].pop()
    elif invalid == 'invented_quote':
        response['payoff_checks'][0]['resolution'][0]['quote'] = 'Lan đọc được tên người phụ nữ trên hóa đơn.'
    elif invalid == 'same_setup':
        response['payoff_checks'][0]['resolution'] = response['payoff_checks'][0]['setup']
    else:
        response['payoff_checks'][1] = response['payoff_checks'][0]
    def call(system, prompt):
        return json.dumps(response, ensure_ascii=False), 1, 1
    result = review_script_logic(s, b, call, _require_grounding=True)
    assert result['status'] == 'ERROR'


def test_real_payoffs_are_retained_for_both_independent_reviews():
    b = payoff_bible()
    s = script('Lan nhận thấy áo của chồng có mùi nước hoa lạ.', 'Mai nói: “Tôi mượn chiếc áo ấy tối hôm đó.”')
    def call(system, prompt):
        assert 'payoff_checks' in prompt
        return json.dumps(grounded_response(s, b), ensure_ascii=False), 1, 1
    result = review_script_logic(s, b, call, _require_grounding=True)
    assert result['status'] == 'RUN' and result['passes'] == 2 and result['grounding_verified']
    assert len(result['payoff_checks_second_pass']) == len(payoff_obligations(b))


def test_outline_cannot_silently_discard_clue_obligations():
    b = payoff_bible()
    scenes = [{'title': f'Cảnh {i}', 'action': f'Lan hỏi chuyện về chi tiết {i}', 'new_information': 'Một lời khai mới',
        'role':'HOOK' if i==1 else 'DEVELOPMENT', 'state_before':f'Chưa biết chi tiết {i}', 'state_after':f'Đã biết chi tiết {i}', 'listener_question':'Mùi hương từ đâu?',
        'consequence': 'Lan quyết định gặp Mai', 'part': 1 if i < 5 else 2, 'payoff_ids': [], 'payoff_action': ''}
        for i in range(1, 9)]
    calls = []
    def call(system, prompt):
        calls.append(prompt)
        return json.dumps({'scenes': scenes}, ensure_ascii=False), 1, 1
    assert build_scene_outline(b, call, require_contract=True) is None
    assert len(calls) == 2
    scenes[-1]['payoff_ids'] = [o['id'] for o in payoff_obligations(b)]
    scenes[-1]['payoff_action'] = 'Mai trả lời rõ vì sao mùi hương trên chiếc áo.'
    assert build_scene_outline(b, call, require_contract=True)


def test_verifying_project_with_witness_is_not_repeating_husband_question():
    s = script('Ngọc Anh hỏi: “Dạo này dự án bận lắm sao anh?” Hoàng nói: “Ừ, cũng chỉ là mấy việc phải xử lý thôi.”',
        'Hoàng nói: “Anh phải ở lại công ty xử lý dự án.”', *['Lan đi làm.']*4,
        'Ngọc Anh hỏi tiếp: “Những buổi làm việc muộn trong giai đoạn đó có thường xuyên không anh?” Tuấn trả lời: “Có. Hai người họ cùng xử lý nhiều phần việc vì tiến độ dự án.”')
    assert not repeated_dialogue_pairs(s.segments)
    s.segments[0].text = s.segments[-1].text
    assert ('001', '007') in repeated_dialogue_pairs(s.segments)


@pytest.mark.parametrize('second_valid', [True, False])
def test_invalid_story_repair_is_retried_before_any_artifact_mutation(second_valid):
    from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider.default_model = 'test-model'
    provider.last_used_model = 'test-model'
    provider.provider_name = 'openai_compatible'
    b = bible(5)
    before = b.to_dict()
    responses = ['The response could not be completed.', json.dumps({'protagonist': {
        **b.protagonist, 'description': 'Lan sống cùng chồng và con gái 3 tuổi.'}}, ensure_ascii=False) if second_valid else '{"protagonist":']
    calls = []
    def complete(messages, **kwargs):
        assert b.to_dict() == before
        calls.append(messages)
        return responses[len(calls)-1], 3, 4
    provider._call_chat_completion = complete
    if second_valid:
        result, in_tok, out_tok = provider.repair_story_bible(b, [{'rule': 'CHARACTER_IDENTITY_CONTRADICTION', 'target': 'protagonist', 'message': 'Tuổi sai'}])
        assert not bible_age_conflicts(result)
        assert (in_tok, out_tok) == (6, 8)
    else:
        with pytest.raises(ValueError, match='original draft was retained'):
            provider.repair_story_bible(b, [])
        assert b.to_dict() == before
    assert len(calls) == 2


def test_story_review_retries_paraphrased_quote_without_erasing_real_issue():
    from apps.script_factory.semantic_review import review_story_bible_logic
    b = bible(3)
    b.reveal_2 = 'Sau cuộc gọi, Lan nhận ra người phụ nữ trong ảnh là Mai.'
    calls = []
    def call(system, prompt):
        calls.append(prompt)
        issue = {'rule': 'POV_KNOWLEDGE_VIOLATION', 'field': 'reveal_2',
            'quote': 'Lan xác định người phụ nữ trong ảnh là Mai sau cuộc gọi' if len(calls)==1 else b.reveal_2,
            'problem': 'Gọi điện không cho biết khuôn mặt người trong ảnh.',
            'fix': 'Bổ sung nguồn xác nhận danh tính trước khi nhận ra.', 'confidence': 'high'}
        return json.dumps({'issues': [issue]}, ensure_ascii=False), 2, 3
    result = review_story_bible_logic(b, call)
    assert len(calls) == 2 and result['review_retries'] == 1
    assert result['status'] == 'RUN' and result['issues'][0]['rule'] == 'POV_KNOWLEDGE_VIOLATION'


def test_story_review_requires_grounded_clean_pass_and_audits_information_channels():
    from apps.script_factory.semantic_review import review_story_bible_logic
    b = bible(3)
    b.reveal_justifications = {'reveal_2': {'evidence_support': 'Sau cuộc gọi thoại, Lan biết mặt Mai trong ảnh.'}}
    def faulty(system, prompt):
        return json.dumps({'issues': []}), 1, 1
    result = review_story_bible_logic(b, faulty, _require_grounding=True)
    assert result['status'] == 'ERROR'
    def finding(system, prompt):
        return json.dumps({'issues': [{'rule': 'POV_KNOWLEDGE_VIOLATION',
            'field': 'reveal_justifications.reveal_2.evidence_support',
            'quote': b.reveal_justifications['reveal_2']['evidence_support'],
            'problem': 'Cuộc gọi thoại không truyền khuôn mặt.', 'fix': 'Xác thực bằng chú thích ảnh.', 'confidence': 'high'}]}, ensure_ascii=False), 1, 1
    result = review_story_bible_logic(b, finding, _require_grounding=True)
    assert result['issues'] and result['issues'][0]['rule'] == 'POV_KNOWLEDGE_VIOLATION'
    def good(system, prompt):
        checks = [{'category': c, 'verdict': 'PASS', 'reason': 'Đã kiểm tra nội dung và nguồn thông tin trong trường thực tế.',
            'evidence': [{'field': 'time_period', 'quote': b.time_period}]} for c in
            ['timeline', 'setup_payoff', 'evidence_scope', 'knowledge_source', 'vietnamese']]
        return json.dumps({'issues': [], 'audit_checks': checks}, ensure_ascii=False), 1, 1
    result = review_story_bible_logic(b, good, _require_grounding=True)
    assert result['passes'] == 2 and result['grounding_verified']


@pytest.mark.parametrize('text,blocked', [
    ('Trên đường về nhà, Lan đặt cuốn sổ và bức ảnh cạnh nhau trên bàn.', True),
    ('Trên đường về nhà, Lan nhớ mình đã đặt cuốn sổ trên bàn.', False),
    ('Trên đường về nhà, Lan quyết định sẽ đặt cuốn sổ trên bàn.', False),
    ('Trên đường về nhà, Lan dừng lại ở quán cà phê và đặt cuốn sổ trên bàn.', False),
    ('Trên đường về nhà, Lan gọi điện cho chồng.', False),
    ('Về tới nhà, Lan đặt cuốn sổ trên bàn.', False),
    ('Trên đường về nhà, Lan ngồi trên tàu và đặt cuốn sổ trên bàn gấp.', False),
])
def test_in_transit_actions_need_a_capable_established_location(text, blocked):
    from apps.script_factory.event_facts import scene_location_conflicts
    assert bool(list(scene_location_conflicts(script(text)))) == blocked


def test_script_review_repairs_evidence_format_without_rewriting_script():
    b = payoff_bible()
    s = script('Lan nhận thấy áo của chồng có mùi nước hoa lạ.', 'Mai nói: “Tôi mượn chiếc áo ấy tối hôm đó.”')
    before = s.to_dict()
    calls = []
    def call(system, prompt):
        calls.append(prompt)
        response = grounded_response(s, b)
        if len(calls) == 1:
            response['payoff_checks'][0]['resolution'][0]['quote'] = 'Mai xác nhận cô mượn áo của chồng Lan hôm trước'
        elif len(calls) == 2:
            assert 'actual_segment_text' in prompt and s.segments[1].text in prompt
        return json.dumps(response, ensure_ascii=False), 1, 1
    result = review_script_logic(s, b, call, _require_grounding=True)
    assert len(calls) == 3 and result['passes'] == 2 and result['grounding_verified']
    assert s.to_dict() == before
