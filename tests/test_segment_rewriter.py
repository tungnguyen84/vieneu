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


def test_parse_accepts_bare_array_and_wrapped_object():
    from apps.script_factory.segment_rewriter import parse_json_items

    assert parse_json_items('[{"id": "001", "text": "a"}]', "segments") == [{"id": "001", "text": "a"}]
    assert parse_json_items('```json\n{"segments": [{"id": "002"}]}\n```', "segments") == [{"id": "002"}]
    assert parse_json_items("không phải json", "segments") == []


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

