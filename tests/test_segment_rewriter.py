import json

from apps.script_factory.models import FullScript, QCReport, ScriptSegment, StoryBible
from apps.script_factory.segment_rewriter import collect_flagged_segments, rewrite_flagged_segments


def _script():
    return FullScript(
        episode_id="EP_RW",
        title="Chiếc USB",
        host={"id": "MINH", "voice": "Binh"},
        segments=[
            ScriptSegment(id="001", text="Có những bí mật dù giấu kỹ đến đâu cũng sẽ lộ ra.", delivery_profile="HOOK"),
            ScriptSegment(id="002", text="Tuấn tìm thấy chiếc USB dưới chồng tài liệu."),
            ScriptSegment(id="003", text="Đó là một cái tát trời giáng vào mặt anh."),
            ScriptSegment(id="004", text="Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", delivery_profile="ENDING"),
        ],
    )


def _report():
    return QCReport(
        episode_id="EP_RW",
        status="NEEDS_REVISION",
        scores={},
        evidence_issues=[
            {"segment_id": "001", "rule": "GENERIC_HOOK_OPENING", "message": "Mở đầu sáo rỗng ('có những bí mật')."},
            {"segment_id": "002", "rule": "MELODRAMATIC_CLICHE_DENSITY", "message": "Sáo rỗng ('cái tát trời giáng')."},
            {"segment_id": "004", "rule": "PREMATURE_SIGNOFF", "message": "x"},
        ],
    )


def test_source_payoff_repair_can_complete_both_actors_in_next_paragraph():
    script=FullScript('NEW','Bữa cơm',{},adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'},'brief_hash':'test','analysis':{}},
        segments=[ScriptSegment('001',text='Hai cha con ngồi xuống bàn ăn với chiếc hộp cơm đã sửa.'),
                  ScriptSegment('002',text='Vy kể về bài dự án và hỏi cha về công việc. Cuộc nói chuyện bên mâm cơm kéo dài hơn ngày thường.'),
                  ScriptSegment('003',text='Cảm ơn khán giả đã lắng nghe, hẹn gặp lại.',delivery_profile='ENDING')])
    bible=StoryBible('NEW','Bữa cơm',{},ending='Hai cha con lần lượt kể chuyện vui và khó trong tuần.',adaptation_context=script.adaptation_context)
    qc=QCReport('NEW','NEEDS_REVISION',evidence_issues=[dict(rule='PAYOFF_NOT_COMPLETED',segment_id='001',
        source='SEMANTIC_REVIEW',blocking=True,message='Chưa có phần cha kể chuyện.',recommended_action='Cho cả hai thực hiện việc chia sẻ.')])
    original=script.segments[-1].text
    def call(system,prompt):
        assert 'Cảnh tiếp nối kết quả' in prompt and bible.ending in prompt
        return json.dumps({'segments':[{'id':'002','text':'Vy kể chuyện vui về bài dự án và nỗi lo phải tự xoay xở. Khải kể ông vui khi sửa được máy cho khách, nhưng khó vì công việc khiến cha con ít gặp nhau.'}]},ensure_ascii=False),1,1
    result,_,_,changed=rewrite_flagged_segments(script,bible,qc,call)
    assert changed=={'002'} and 'Khải kể' in result.segments[1].text
    assert result.segments[-1].text==original


def test_payoff_scope_expansion_excludes_signoff_and_unverified_findings():
    script=_script();script.adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'}}
    issue=dict(rule='PAYOFF_NOT_COMPLETED',segment_id='003',source='SEMANTIC_REVIEW',blocking=True,message='Thiếu hành động kết quả.')
    assert set(collect_flagged_segments(script,QCReport('NEW','NEEDS_REVISION',evidence_issues=[issue])))=={'003'}
    issue.update(segment_id='002',blocking=False)
    assert set(collect_flagged_segments(script,QCReport('NEW','NEEDS_REVISION',evidence_issues=[issue])))=={'002'}


def test_collect_maps_density_phrases_to_the_segments_containing_them():
    flagged = collect_flagged_segments(_script(), _report())
    assert set(flagged) == {"001", "003"}


def test_rewrite_applies_only_flagged_segments_and_rejects_signoffs():
    seen_prompts = []

    def fake_llm(system, prompt):
        seen_prompts.append(prompt)
        return json.dumps({"segments": [
            {"id": "001", "text": "Tuấn tìm thấy một chiếc USB dán nhãn báo cáo tài chính trên bàn của vợ."},
            {"id": "003", "text": "Cảm ơn quý vị đã lắng nghe. Xin chào và hẹn gặp lại."},
            {"id": "002", "text": "Đoạn không được yêu cầu sửa."},
        ]}, ensure_ascii=False), 10, 20

    script, tin, tout, rewritten = rewrite_flagged_segments(_script(), StoryBible(episode_id="EP_RW", title="t", protagonist={"name": "Tuấn"}), _report(), fake_llm)
    texts = {s.id: s.text for s in script.segments}
    assert texts["001"].startswith("Tuấn tìm thấy")
    assert texts["002"] == "Tuấn tìm thấy chiếc USB dưới chồng tài liệu."
    assert texts["003"] == "Đó là một cái tát trời giáng vào mặt anh."  # sign-off mid-script rejected
    assert (tin, tout) == (10, 20)
    assert rewritten == {"001"}
    assert len(seen_prompts) == 1


def test_misplaced_signoff_is_normalized_not_rejected():
    from apps.script_factory.providers.gemini_provider import _has_one_final_signoff, _normalize_final_signoff

    part2 = [
        {"text": "Tuấn đóng cửa lại.", "delivery_profile": "NORMAL"},
        {"text": "Anh bước đi. Cảm ơn quý vị đã lắng nghe.", "delivery_profile": "ENDING"},
        {"text": "Quý vị nghĩ sao về lựa chọn của Tuấn?", "delivery_profile": "COMMENT"},
    ]
    fixed = _normalize_final_signoff(part2)
    assert _has_one_final_signoff(fixed)
    assert fixed[1]["text"] == "Anh bước đi."
    assert fixed[-2]["text"].startswith("Quý vị nghĩ sao")


def test_final_rewrite_cannot_remove_existing_signoff():
    script=_script()
    old=script.segments[-1].text
    report=QCReport('EP_RW','NEEDS_REVISION',evidence_issues=[
        dict(segment_id='004',rule='REDUNDANT_CLOSING',message='Rút đoạn kết.')])
    def llm(system,prompt):
        assert 'Không xóa lời chào cuối' in prompt
        return json.dumps({'segments':[{'id':'004','text':'Tuấn khép cửa và bắt đầu cuộc sống mới trong căn phòng của mình.'}]}),1,2
    result,_,_,changed=rewrite_flagged_segments(script,StoryBible('EP_RW','t',{}),report,llm)
    assert result.segments[-1].text==old and not changed


def test_source_missing_signoff_can_be_written_only_at_final_id():
    script=_script();script.segments[-1].text='Tuấn xếp dụng cụ và chuẩn bị bắt đầu công việc cho ngày mai.'
    script.adaptation_context={'brief':{'adaptation_mode':'FICTION_FROM_THEME'},'brief_hash':'test',
                               'analysis':{'theme':'Trách nhiệm','conflict':'Nhận lỗi'}}
    bible=StoryBible('EP_RW','t',{},adaptation_context=script.adaptation_context)
    report=QCReport('EP_RW','NEEDS_REVISION',evidence_issues=[
        dict(segment_id='004',rule='MISSING_FINAL_SIGNOFF',message='Thiếu lời chào kết thật.')])
    def llm(system,prompt):
        assert 'MISSING_FINAL_SIGNOFF' in prompt
        return json.dumps({'segments':[{'id':'004','text':'Tuấn xếp dụng cụ cho ngày mai. Cảm ơn các bạn đã lắng nghe. Hẹn gặp lại.'}]}),1,2
    result,_,_,changed=rewrite_flagged_segments(script,bible,report,llm)
    assert changed=={'004'} and 'Hẹn gặp lại' in result.segments[-1].text


def test_parse_accepts_bare_array_and_wrapped_object():
    from apps.script_factory.segment_rewriter import parse_json_items

    assert parse_json_items('[{"id": "001", "text": "a"}]', "segments") == [{"id": "001", "text": "a"}]
    assert parse_json_items('```json\n{"segments": [{"id": "002"}]}\n```', "segments") == [{"id": "002"}]
    assert parse_json_items("không phải json", "segments") == []


def _long_closing():
    script = _script()
    script.segments[0].text = ('Tuấn đọc tài liệu rồi kiểm tra lại các khoản đã bàn giao. ' * 40).strip()
    script.segments[1].text = 'Tuấn ký biên bản và nhận chìa khóa căn phòng mới.'
    script.segments[2].text = 'Từ đó Tuấn hiểu rằng việc làm rõ trách nhiệm thật quan trọng. ' * 4
    script.segments.insert(3, ScriptSegment(id='003b', text='Anh nhận ra trách nhiệm cần được làm rõ từ đầu mỗi công việc. ' * 4))
    report = QCReport('EP_RW', 'NEEDS_REVISION', evidence_issues=[dict(rule='REDUNDANT_CLOSING',
        segment_id='003', related_segment_ids=['003b'], closing_after_segment_id='002',
        source='SEMANTIC_REVIEW', blocking=True, message='Hai đoạn kể lại cùng kết luận sau cảnh nhận chìa khóa.')])
    return script, report


def test_grounded_closing_repair_merges_block_without_touching_payoff_or_signoff():
    from apps.script_factory.segment_rewriter import revise_with_ai
    script, report = _long_closing()
    body = [s.text for s in script.segments[:2]]
    signoff = script.segments[-1].text
    calls = []
    reflection = 'Với Tuấn, chiếc chìa khóa ấy khép lại những ngày chờ đợi và mở ra một căn phòng của riêng anh.'
    def call(_system, prompt):
        calls.append(prompt)
        assert 'DUY NHẤT một đoạn' in prompt and 'closing_to_compress' in prompt
        return json.dumps({'reflection': reflection}, ensure_ascii=False), 10, 20
    result, inp, out = revise_with_ai(script, StoryBible('EP_RW','t',{'name':'Tuấn'}), report, call)
    assert len(calls) == 1 and (inp,out) == (10,20)
    assert [s.text for s in result.segments[:2]] == body and result.segments[-1].text == signoff
    assert result.segments[2].text == reflection and len(result.segments) == result.total_segments == 4
    assert [s.id for s in result.segments] == ['001','002','003','004']
    assert sum(len(s.text.split()) for s in result.segments[2:]) / result.total_words <= .08


def test_unanchored_style_warning_cannot_remove_closing_paragraphs():
    from apps.script_factory.segment_rewriter import _compress_verified_closing
    script, report = _long_closing()
    del report.evidence_issues[0]['closing_after_segment_id']
    before = script.to_dict()
    def call(*args):
        raise AssertionError('No grounded suffix, no block edit.')
    result, inp, out, changed = _compress_verified_closing(script, StoryBible('EP_RW','t',{}),report,call)
    assert result.to_dict() == before and not changed and (inp,out) == (0,0)


def test_invalid_ai_compression_preserves_all_existing_paragraphs():
    from apps.script_factory.segment_rewriter import _compress_verified_closing
    script, report = _long_closing()
    before = script.to_dict()
    responses = iter(['{"reflection":"quá ngắn"}',json.dumps({'reflection':'nhận xét '*200})])
    result, inp, out, changed = _compress_verified_closing(script, StoryBible('EP_RW','t',{}), report,
        lambda *args:(next(responses),10,20))
    assert result.to_dict() == before and not changed and (inp,out) == (20,40)


def test_parse_handles_trailing_commentary_and_extra_data():
    from apps.script_factory.segment_rewriter import parse_json_items_validated

    raw = '```json\n{"issues": [{"rule": "POV_VIOLATION", "segment_id": "001"}]}\n```\nHere is some trailing commentary.'
    items, is_valid, err = parse_json_items_validated(raw, "issues")
    assert is_valid is True
    assert len(items) == 1
    assert items[0]["rule"] == "POV_VIOLATION"


def test_deterministic_hook_template_does_not_overwrite_ai_rewrite():
    from apps.script_factory.script_qc import apply_targeted_repairs

    script = _script()
    script.segments[0].text = "Tuấn xoay chiếc USB trong tay, nhãn dán ghi báo cáo tài chính quý."
    report = _report()
    report.evidence_issues.append({"segment_id": "001", "rule": "HOOK_TOO_SLOW", "message": "x"})
    bible = StoryBible(episode_id="EP_RW", title="t", protagonist={"name": "Tuấn"}, clues=["một manh mối"])
    repaired = apply_targeted_repairs(script, bible, report, preserve_segment_ids={"001"})
    assert repaired.segments[0].text.startswith("Tuấn xoay chiếc USB")


def test_repair_context_includes_later_clue_channel_timeline_and_ending():
    from apps.script_factory.segment_rewriter import build_prompt
    bible = StoryBible(episode_id='EP_RW', title='t', protagonist={'name': 'Hoa'},
                       timeline=['Hoa witnessed the gate scene in May 2024'],
                       clues=['clue'] * 4 + ['Thu sent the recording by anonymous email'],
                       ending='Thu later told Hoa about the company response')
    prompt = build_prompt(_script(), bible, {'002': ['Fix the channel']})
    assert 'Thu sent the recording by anonymous email' in prompt
    assert 'Hoa witnessed the gate scene in May 2024' in prompt
    assert 'Thu later told Hoa about the company response' in prompt


def test_repeated_discovery_can_be_shortened_without_inventing_another_discovery():
    script = _script()
    script.segments[1].text = 'Hoa mở lại chiếc laptop, đọc lại bản nháp email đã xem, rồi một lần nữa phát hiện Thành đã lợi dụng Thu để giữ vị trí của mình.'
    report = QCReport('EP_RW', 'NEEDS_REVISION', evidence_issues=[
        {'segment_id':'002', 'rule':'REPEATED_DISCOVERY', 'message':'Email đã được đọc trước đó.'}])
    transition = 'Hoa đặt máy tính xuống, chờ Thành về.'
    def rewrite(_system, prompt):
        assert 'được rút ngắn thành câu nối mạch' in prompt
        return json.dumps({'segments':[{'id':'002', 'text':transition}]}), 1, 1
    result, _, _, rewritten = rewrite_flagged_segments(script, StoryBible('EP_RW', 't', {'name':'Hoa'}), report, rewrite)
    assert rewritten == {'002'} and result.segments[1].text == transition


def test_repeated_scene_dialogue_can_be_shortened_without_length_rejection():
    script = _script()
    script.segments[1].text = 'Khải hỏi nhân viên bán hàng: "Những hôm My nói phải kiểm kê muộn, chị ấy thường rời cửa hàng lúc nào và đi cùng với ai?"'
    report = QCReport('EP_RW', 'NEEDS_REVISION', evidence_issues=[
        {'segment_id': '002', 'rule': 'REPEATED_SCENE_DIALOGUE', 'message': 'Cảnh này lặp lại cuộc trò chuyện ở [001].'}
    ])
    short_transition = 'Khải chào người bán hàng rồi bước ra xe.'
    def rewrite(_system, prompt):
        return json.dumps({'segments': [{'id': '002', 'text': short_transition}]}), 1, 1
    result, _, _, rewritten = rewrite_flagged_segments(script, StoryBible('EP_RW', 't', {'name': 'Khải'}), report, rewrite)
    assert rewritten == {'002'} and result.segments[1].text == short_transition

