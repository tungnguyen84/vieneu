from apps.script_factory.models import ScriptSegment
from apps.script_factory.script_craft import hedge_segment_ids, trim_overlong_closing, voice_reference_block


def _seg(i, text, profile="NORMAL", audience=False):
    return ScriptSegment(id=f"{i:03d}", text=text, delivery_profile=profile, audience_address=audience)


def test_voice_reference_block_contains_principles_and_aired_sample():
    block = voice_reference_block()
    assert "NGHỀ KỂ CHUYỆN" in block
    assert "MẪU GIỌNG KỂ" in block
    assert "KHÔNG dùng lại nhân vật" in block


def test_trim_keeps_story_and_one_reflection_one_question_and_signoff():
    segs = [_seg(i, f"Diễn biến {i}.") for i in range(1, 21)]
    segs.append(_seg(21, "Lan thừa nhận mọi chuyện.", "REVEAL"))
    segs.append(_seg(22, "Quân pha cho vợ một cốc nước và ngồi nghe."))
    segs.append(_seg(23, "Bài học thứ nhất về niềm tin.", "COMMENT"))
    segs.append(_seg(24, "Bài học thứ hai về sự im lặng.", "COMMENT"))
    segs.append(_seg(25, "Còn bạn, bạn sẽ làm gì?", "COMMENT", audience=True))
    segs.append(_seg(26, "Một lời cảm ơn gửi tới quý vị đã lắng nghe câu chuyện hôm nay.", "COMMENT"))
    segs.append(_seg(27, "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"))
    texts = [s.text for s in trim_overlong_closing(segs)]
    assert "Quân pha cho vợ một cốc nước và ngồi nghe." in texts
    assert "Bài học thứ nhất về niềm tin." not in texts
    assert "Bài học thứ hai về sự im lặng." in texts
    assert "Còn bạn, bạn sẽ làm gì?" in texts
    assert not any(t.startswith("Một lời cảm ơn") for t in texts)
    assert texts[-1].startswith("Cảm ơn quý vị đã lắng nghe")


def test_hedging_is_detected():
    segs = [_seg(1, "Quân biết những tin nhắn đó chưa đủ để kết luận."), _seg(2, "Anh mở điện thoại.")]
    assert hedge_segment_ids(segs) == ["001"]


def test_trim_overlong_closing_keeps_resolution_lines_labelled_comment():
    from apps.script_factory.script_craft import trim_overlong_closing

    body = [{"text": f"Tối hôm ấy Hoàng và Lan nói chuyện về Mai lần thứ {i}.", "delivery_profile": "NORMAL"} for i in range(30)]
    body[25]["delivery_profile"] = "REVEAL"
    closing = [
        {"text": "Ngày dọn đồ đi, Hoàng cất chiếc áo khoác vào một chiếc hộp.", "delivery_profile": "COMMENT"},
        {"text": "Anh không mở chiếc hộp ấy ra nữa.", "delivery_profile": "COMMENT"},
        {"text": "Có những bí mật được che đậy bằng sự im lặng.", "delivery_profile": "COMMENT"},
        {"text": "Sự phản bội lớn dần từ những khoảng im lặng.", "delivery_profile": "COMMENT"},
        {"text": "Còn bạn, bạn sẽ chọn điều gì?", "delivery_profile": "COMMENT", "audience_address": True},
        {"text": "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "delivery_profile": "ENDING"},
    ]
    out = trim_overlong_closing(body + closing)
    texts = [s["text"] for s in out]
    assert "Ngày dọn đồ đi, Hoàng cất chiếc áo khoác vào một chiếc hộp." in texts
    assert "Anh không mở chiếc hộp ấy ra nữa." in texts
    assert "Có những bí mật được che đậy bằng sự im lặng." not in texts
    assert [s["delivery_profile"] for s in out[30:32]] == ["NORMAL", "NORMAL"]
    assert len(out) == len(body) + 5
