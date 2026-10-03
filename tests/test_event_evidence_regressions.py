import json
import pytest

from apps.script_factory.models import FullScript, ScriptSegment, StoryBible, LockedFact
from apps.script_factory.timeline_qc import audit_event_timeline, audit_evidence_scope
from apps.script_factory.vietnamese_cleaner import clean_garbled_vietnamese, find_garbled_vietnamese_issues
from apps.script_factory.semantic_review import review_script_logic

def make_script(*texts):
    return FullScript(episode_id='AUDIT', title='Audit', host={'id':'MINH'},
        segments=[ScriptSegment(id=f'{i:03}', text=t) for i,t in enumerate(texts,1)])

def make_bible(*timeline):
    return StoryBible(episode_id='AUDIT', title='Audit', protagonist={'name':'Lan'}, timeline=list(timeline))

def test_event_years_are_bound_to_the_correct_character():
    bible=make_bible('Năm 2018: Minh hiến thận cho em trai.', 'Năm 2019: Lan hiến thận cho chị gái.')
    conflicts,_,_=audit_event_timeline(make_script('Lan hiến thận cho chị gái vào năm 2019.'),bible)
    assert not conflicts, conflicts

def test_spoken_wrong_year_is_a_timeline_conflict():
    bible=make_bible('Năm 2019: Lan hiến thận cho chị gái.')
    conflicts,_,_=audit_event_timeline(make_script('Lan hiến thận cho chị gái vào năm hai nghìn không trăm mười tám.'),bible)
    assert conflicts, 'Incorrect event year in spoken Vietnamese escaped the auditor'

def test_negated_wrong_date_is_not_a_contradiction():
    bible=make_bible('Năm 2019: Lan hiến thận cho chị gái.')
    conflicts,_,_=audit_event_timeline(make_script('Lan không hiến thận vào năm 2018. Cô hiến thận vào năm 2019.'),bible)
    assert not conflicts, conflicts

@pytest.mark.parametrize('text', ['Lan đứng cách cửa 10 m và nhìn thấy chiếc xe.', 'Cô cân 5 g đường để pha trà.'])
def test_valid_units_followed_by_words_are_preserved(text):
    assert clean_garbled_vietnamese(text)==text
    assert not find_garbled_vietnamese_issues(text)

def test_routine_health_paper_does_not_establish_donor_identity():
    script=make_script('Ngọc cầm tờ giấy khám sức khỏe tổng quát, chỉ có số đo chiều cao.',
        'Cô mở cuốn sổ ghi chép lịch trình điều trị, chỉ có giờ tái khám của cha.',
        'Cuốn sổ tay chính thức xác nhận chính Nam là người đã hiến thận cứu cha.')
    issues,_=audit_evidence_scope(script,make_bible())
    assert issues, 'Unrelated health paper bypassed the evidence guard'

def test_absolute_photo_claim_with_name_must_be_detected():
    script=make_script('Bức ảnh chứng minh Hoàng Nam hoàn toàn không phải là kẻ vô cảm hay thực dụng ích kỷ.')
    issues,_=audit_evidence_scope(script,make_bible())
    assert issues, 'Inserting the character name defeated photo evidence validation'

def test_opening_envelope_without_reading_is_not_verified_payoff():
    script=make_script('Lan nhận được phong bì niêm phong, bên trong hứa chứa lời giải thích về khoản tiền mất tích.',
        'Lan mở phong bì, cất bức thư vào ngăn kéo mà không đọc.',
        'Lan rời nhà. Cảm ơn quý vị đã lắng nghe.')
    issue={'rule':'UNRESOLVED_SETUP','segment_id':'001','quote':script.segments[0].text,
        'problem':'Phong bì đã mở ở phân đoạn 002, nhưng nội dung về khoản tiền mất tích vẫn bị giấu.',
        'fix':'Làm rõ đáp án về tiền mất tích.','confidence':'high'}
    def reviewer(system,prompt):
        return json.dumps({'issues':[issue]},ensure_ascii=False),10,20
    review=review_script_logic(script,make_bible(),reviewer)
    assert any(i['rule']=='UNRESOLVED_SETUP' for i in review['issues']),review

def test_real_review_cannot_pass_with_empty_issues_and_no_reading_evidence():
    script=make_script('Lan mở thư rồi đọc lời thú nhận về khoản tiền mất tích.')
    def reviewer(system,prompt):
        return json.dumps({'issues':[]}),10,20
    review=review_script_logic(script,make_bible(),reviewer,_require_grounding=True)
    assert review['status']=='ERROR'
    assert not review.get('grounding_verified')

def test_both_grounded_review_passes_are_required():
    script=make_script('Lan mở thư rồi đọc lời thú nhận về khoản tiền mất tích.')
    def reviewer(system,prompt):
        checks=[{'category':c,'verdict':'PASS','reason':'Đã đối chiếu với nội dung cụ thể trong đoạn và Story Bible.',
            'evidence':[{'segment_id':'001','quote':script.segments[0].text}]} for c in ['timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese']]
        return json.dumps({'issues':[],'audit_checks':checks},ensure_ascii=False),10,20
    review=review_script_logic(script,make_bible(),reviewer,_require_grounding=True)
    assert review['status']=='RUN' and review['passes']==2
    assert review['grounding_verified']
    assert len(review['audit_checks_second_pass'])==5

def test_misquoted_reading_evidence_is_not_accepted():
    script=make_script('Lan mở thư rồi đọc lời thú nhận về khoản tiền mất tích.')
    def reviewer(system,prompt):
        checks=[{'category':c,'verdict':'PASS','reason':'Đã đối chiếu với nội dung cụ thể trong đoạn và Story Bible.',
            'evidence':[{'segment_id':'001','quote':'Lan nhận được ba mươi triệu đồng.'}]} for c in ['timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese']]
        return json.dumps({'issues':[],'audit_checks':checks},ensure_ascii=False),10,20
    review=review_script_logic(script,make_bible(),reviewer,_require_grounding=True)
    assert review['status']=='ERROR'


def test_opening_and_vaguely_checking_truth_does_not_erase_a_finding():
    script=make_script('Lan nhận được phong bì niêm phong từ người lạ.',
        'Lan mở phong bì niêm phong ra và đối chiếu sự thật.')
    issue={'rule':'UNRESOLVED_SETUP','segment_id':'001','quote':script.segments[0].text,
        'problem':'Chi tiết phong bì niêm phong đã được giải quyết ở phân đoạn [002]',
        'fix':'Cần kể nội dung trả lời câu hỏi trong phong bì.','confidence':'medium'}
    def reviewer(system,prompt):
        return json.dumps({'issues':[issue]},ensure_ascii=False),10,20
    review=review_script_logic(script,make_bible(),reviewer)
    assert any(i['rule']=='UNRESOLVED_SETUP' for i in review['issues'])


def transplant_bible(operation_year):
    bible=make_bible('Năm 2020: Cha Lan suy thận và cần ghép thận.',
        f'Năm {operation_year}: Lan hiến thận cho cha.')
    bible.critical_facts=[LockedFact('TRANSPLANT','duration','4 năm (2020–2024)',
        description='Thời gian kể từ ca ghép thận')]
    return bible


def test_story_bible_conflict_is_blocked_before_script_writing():
    from apps.script_factory.event_facts import bible_timeline_conflicts
    assert bible_timeline_conflicts(transplant_bible(2022))
    assert not bible_timeline_conflicts(transplant_bible(2020))


@pytest.mark.parametrize('duration,should_fail',[('hai',True),('bốn',False),('4',False)])
def test_relative_transplant_duration_matches_locked_fact(duration,should_fail):
    script=make_script(f'Cha Lan được ghép thận cách đây {duration} năm.')
    conflicts,_,_=audit_event_timeline(script,transplant_bible(2020))
    assert bool(conflicts)==should_fail


@pytest.mark.parametrize('variant',['missing_knowledge','duplicate_pass_for_fail','invalid_finding'])
def test_grounded_pass_cannot_hide_incomplete_or_conflicting_checks(variant):
    script=make_script('Lan mở thư rồi đọc lời thú nhận về khoản tiền mất tích.')
    checks=[{'category':c,'verdict':'PASS','reason':'Đã đối chiếu nội dung và nguồn thông tin trước cảnh này.',
        'evidence':[{'segment_id':'001','quote':script.segments[0].text}]} for c in
        ['timeline','setup_payoff','evidence_scope','knowledge_source','vietnamese']]
    issues=[]
    if variant=='missing_knowledge':
        checks=[c for c in checks if c['category']!='knowledge_source']
    elif variant=='duplicate_pass_for_fail':
        checks.append({**checks[0],'verdict':'FAIL'})
    else:
        issues=[{'rule':'UNRESOLVED_SETUP','segment_id':'999','quote':'Đây không phải trích dẫn hợp lệ.',
            'problem':'Một lỗi khách quan bị trích sai đoạn.','confidence':'high'}]
    def reviewer(system,prompt):
        return json.dumps({'issues':issues,'audit_checks':checks},ensure_ascii=False),10,20
    review=review_script_logic(script,make_bible(),reviewer,_require_grounding=True)
    assert review['status']=='ERROR' and not review.get('grounding_verified')
