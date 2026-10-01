import json

from apps.script_factory.models import ScriptSegment, StoryBible
from apps.script_factory.scene_outline import build_scene_outline, outline_block, repeated_dialogue_pairs


def _bible():
    return StoryBible(episode_id="EP_O", title="Chiếc chìa khóa", protagonist={"name": "Khải"})


def _scenes(n=10, split=4):
    return [{"no": i, "part": 1 if i <= split else 2, "title": f"Cảnh {i}", "action": f"Việc {i}",
             "new_information": f"Tin {i}", "segments": 5} for i in range(1, n + 1)]


def test_outline_marks_written_and_pending_scenes_per_part():
    scenes = build_scene_outline(_bible(), lambda s, p: (json.dumps({"scenes": _scenes()}), 1, 1))
    part2 = outline_block(scenes, 2)
    assert "Cảnh 1 [ĐÃ VIẾT Ở PHẦN 1" in part2
    assert "Cảnh 5 [VIẾT TRONG PHẦN NÀY]" in part2
    assert "Cảnh 5 [để PHẦN 2 viết" in outline_block(scenes, 1)


def test_unusable_outline_falls_back_to_none():
    assert build_scene_outline(_bible(), lambda s, p: ('{"scenes": []}', 1, 1)) is None
    one_part = [dict(s, part=1) for s in _scenes()]
    assert build_scene_outline(_bible(), lambda s, p: (json.dumps({"scenes": one_part}), 1, 1)) is None

    def boom(system, prompt):
        raise RuntimeError("quota")
    assert build_scene_outline(_bible(), boom) is None


def test_repeated_dialogue_detects_retold_scene_only():
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 12)]
    segs[1].text = 'Khải hỏi: "Những hôm My nói kiểm kê muộn, chị ấy thường ở lại đến mấy giờ?"'
    segs[8].text = 'Khải hỏi: "Những hôm My nói phải kiểm kê muộn, chị ấy thường rời cửa hàng lúc nào?"'
    segs[9].text = 'Hạnh nói: "Em sẽ kể anh nghe mọi chuyện em đã thấy ở cửa hàng."'
    assert repeated_dialogue_pairs(segs) == [("002", "009")]


def test_repeated_dialogue_ep2009_regression_not_flagged():
    """EP2009 audit regression: premise assumption vs reveal confession must NOT be flagged as repeated dialogue."""
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 70)]
    segs[1].text = '“Tôi đã nghĩ người phụ nữ đó là Linh Chi, vì cái tên ấy xuất hiện trong những câu chuyện công việc của anh nhiều nhất.”'
    segs[63].text = 'Anh nói: “Người đó là Thu Hà.”'
    assert repeated_dialogue_pairs(segs) == []


def test_repeated_dialogue_question_vs_answer_not_flagged():
    """Asking a question and subsequently answering/confessing in a later scene are different utterances."""
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 60)]
    segs[9].text = 'Khải hỏi: "Có phải anh đã chuyển tiền cho người phụ nữ đó không?"'
    segs[49].text = 'Anh đáp: "Tôi đã chuyển tiền cho người phụ nữ đó vào ngày hôm sau."'
    assert repeated_dialogue_pairs(segs) == []


def test_repeated_dialogue_negation_difference_not_flagged():
    """Opposite polarity statements (denial vs admission) must NOT be flagged."""
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 50)]
    segs[14].text = '"Tôi không bao giờ ký vào biên bản thỏa thuận đó."'
    segs[44].text = '"Tôi đã ký vào biên bản thỏa thuận đó ngay sau khi anh rời đi."'
    assert repeated_dialogue_pairs(segs) == []


def test_repeated_dialogue_valid_callback_not_flagged():
    """A valid callback / memory referencing earlier words must NOT be flagged as scene repetition."""
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 80)]
    segs[19].text = '"Chúng ta sẽ cùng nhau làm lại từ đầu."'
    segs[69].text = 'Tôi nhớ lại lời anh từng hứa: "Chúng ta sẽ cùng nhau làm lại từ đầu."'
    assert repeated_dialogue_pairs(segs) == []


def test_repeated_dialogue_short_courtesies_not_flagged():
    """Common short phrases with different objects must NOT be flagged."""
    segs = [ScriptSegment(id=f"{i:03d}", text=f"Diễn biến {i}.") for i in range(1, 50)]
    segs[4].text = '"Em có muốn uống một tách trà không?"'
    segs[39].text = '"Em có muốn uống một ly nước cam không?"'
    assert repeated_dialogue_pairs(segs) == []

