import json
import pytest
from apps.script_factory.models import FullScript, ScriptSegment, StoryBible
from apps.script_factory.semantic_review import review_script_logic


def unfinished_setup(problem):
    script = FullScript(
        episode_id='UNRESOLVED',
        title='Bức thư bị bỏ quên',
        host={'id': 'MINH'},
        segments=[
            ScriptSegment(id='001', text='Lan nhận được phong bì niêm phong, bên trong hứa chứa lời giải thích về khoản tiền mất tích.', delivery_profile='HOOK'),
            ScriptSegment(id='002', text='Lan bước ra khỏi nhà và bắt đầu cuộc sống mới.'),
            ScriptSegment(id='003', text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile='ENDING'),
        ]
    )
    issue = {
        'rule': 'UNRESOLVED_SETUP',
        'segment_id': '001',
        'quote': script.segments[0].text,
        'problem': problem,
        'fix': 'Bổ sung cảnh đọc thư và giải thích khoản tiền.',
        'confidence': 'high'
    }
    calls = []
    def reviewer(system, prompt):
        calls.append(prompt)
        return json.dumps({'issues': [issue]}, ensure_ascii=False), 10, 20

    review = review_script_logic(script, StoryBible(episode_id=script.episode_id, title=script.title, protagonist={'name': 'Lan'}), reviewer)
    return review, len(calls)


@pytest.mark.parametrize('problem', [
    'Phong bì ở phân đoạn 001 bị lãng quên đến cuối truyện.',
    'Phong bì bị lãng quên; phân đoạn 002 kết thúc câu chuyện thay vì giải đáp nguồn tiền.',
])
def test_unresolved_setup_cannot_be_dropped_for_common_words_or_original_segment(problem):
    review, calls = unfinished_setup(problem)
    assert any(i['rule'] == 'UNRESOLVED_SETUP' for i in review['issues']), json.dumps(
        {'problem': problem, 'review': review, 'calls': calls}, ensure_ascii=False)


def test_unresolved_setup_counter_example_with_real_payoff():
    """Counter-example: When the script ACTUALLY has a payoff that verifies/answers the clue, finding can be dropped."""
    script = FullScript(
        episode_id='RESOLVED',
        title='Bức thư đã mở',
        host={'id': 'MINH'},
        segments=[
            ScriptSegment(id='001', text='Lan nhận được phong bì niêm phong, bên trong hứa chứa lời giải thích về khoản tiền mất tích.', delivery_profile='HOOK'),
            ScriptSegment(id='002', text='Mở chiếc phong bì niêm phong ra, Lan bàng hoàng đọc những dòng thú nhận của người chị về toàn bộ số tiền mất tích.'),
            ScriptSegment(id='003', text='Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.', delivery_profile='ENDING'),
        ]
    )
    issue = {
        'rule': 'UNRESOLVED_SETUP',
        'segment_id': '001',
        'quote': script.segments[0].text,
        'problem': 'Phong bì đã được giải quyết ở phân đoạn 002 bằng cảnh mở thư đọc thú nhận.',
        'fix': 'Không cần sửa.',
        'confidence': 'low'
    }
    def reviewer(system, prompt):
        return json.dumps({'issues': [issue]}, ensure_ascii=False), 10, 20

    review = review_script_logic(script, StoryBible(episode_id=script.episode_id, title=script.title, protagonist={'name': 'Lan'}), reviewer)
    # The payoff exists in 002 with open/read verbs ("mở", "đọc") and clue ("phong bì", "số tiền"), so the false finding is safely dropped.
    assert not any(i['rule'] == 'UNRESOLVED_SETUP' for i in review['issues'])
