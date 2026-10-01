import json

import pytest

from apps.script_factory.models import StoryBible
from apps.script_factory.narrative_continuity import has_repeated_narrative_block
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider


@pytest.fixture(autouse=True)
def _no_scene_outline(monkeypatch):
    """These tests script the exact sequence of part-1/part-2 model replies;
    the single-pass and scene-outline calls are covered by tests/test_scene_outline.py and tests/test_single_pass_writer.py."""
    for module in ("apps.script_factory.providers.gemini_provider", "apps.script_factory.providers.openai_provider"):
        monkeypatch.setattr(f"{module}.build_scene_outline", lambda *args, **kwargs: None)
        monkeypatch.setattr(f"{module}.write_single_pass", lambda *args, **kwargs: (None, 0, 0))



def _segment(segment_id: str, text: str, profile: str = "NORMAL") -> dict:
    return {
        "id": segment_id,
        "speaker": "MINH",
        "text": text,
        "delivery_profile": profile,
        "importance": "normal",
        "audience_address": False,
        "speed": 1.0,
    }


def _bible() -> StoryBible:
    return StoryBible(
        episode_id="EP_STITCH",
        title="Dấu vết kỹ thuật số",
        protagonist={"name": "Nam", "age": 35, "description": "Người gửi thư"},
        secret="Một sự thật chỉ được mở ra ở phần sau.",
        mystery_question="Điều gì đang bị che giấu?",
        false_lead="Nam hiểu sai dấu hiệu đầu tiên.",
        reveal_1="Chứng cứ thứ hai thay đổi hướng điều tra.",
        reveal_2="Chuỗi bằng chứng làm rõ toàn bộ sự thật.",
        emotional_payoff="Nam đối diện sự thật trong bình tĩnh.",
        reflection_theme="Niềm tin cần được xây lại bằng sự thành thật.",
        ending="Hai người cùng chịu trách nhiệm cho lựa chọn của mình.",
    )


def test_gemini_retries_part_one_when_it_signs_off_early(monkeypatch):
    provider = GeminiScriptAIProvider(api_key="fake")
    responses = iter([
        [
            _segment("001", "Nam bắt đầu tìm hiểu dấu hiệu lạ.", "HOOK"),
            _segment("002", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
        ],
        [
            _segment("001", "Nam bắt đầu tìm hiểu dấu hiệu lạ.", "HOOK"),
            _segment("002", "Anh mở hồ sơ và tiếp tục đối chiếu từng mốc thời gian.", "MYSTERY"),
        ],
        [
            _segment("003", "Một chứng cứ mới giúp Nam hiểu đúng sự việc.", "REVEAL"),
            _segment("004", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
        ],
    ])
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs["prompt"])
        return json.dumps(next(responses), ensure_ascii=False), 10, 20

    monkeypatch.setattr(provider, "_call_generate_content", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.gemini_provider.time.sleep", lambda _seconds: None)

    script, input_tokens, output_tokens = provider.write_script(_bible(), {}, {})

    assert len(calls) == 3
    assert "YÊU CẦU SỬA BẮT BUỘC" in calls[1]
    assert script.writer_strategy == "two_pass_seamed"
    assert [segment.delivery_profile for segment in script.segments].count("ENDING") == 1
    assert script.segments[-1].delivery_profile == "ENDING"
    assert input_tokens == 30
    assert output_tokens == 60


def test_gemini_normalizes_signoff_when_second_part_still_has_early_signoff(monkeypatch):
    provider = GeminiScriptAIProvider(api_key="fake")
    valid_part_one = [
        _segment("001", "Nam bắt đầu tìm hiểu dấu hiệu lạ.", "HOOK"),
        _segment("002", "Anh tiếp tục đối chiếu hồ sơ.", "MYSTERY"),
    ]
    invalid_part_two = [
        _segment("003", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
        _segment("004", "Sau đó Nam lại tiếp tục điều tra.", "MYSTERY"),
        _segment("005", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
    ]
    responses = iter([valid_part_one, invalid_part_two, invalid_part_two])

    def fake_call(**_kwargs):
        return json.dumps(next(responses), ensure_ascii=False), 10, 20

    monkeypatch.setattr(provider, "_call_generate_content", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.gemini_provider.time.sleep", lambda _seconds: None)

    script, _in, _out = provider.write_script(_bible(), {}, {})
    assert script.writer_strategy == "two_pass_seamed"
    texts = [segment.text for segment in script.segments]
    signoffs = [i for i, text in enumerate(texts) if "hẹn gặp lại" in text]
    assert signoffs == [len(texts) - 1]
    assert [s.delivery_profile for s in script.segments].count("ENDING") == 1
    assert "Sau đó Nam lại tiếp tục điều tra." in texts


def test_gemini_retries_part_two_when_it_restarts_part_one(monkeypatch):
    provider = GeminiScriptAIProvider(api_key="fake")
    investigation = [
        _segment("005", "Hoàng gọi cho Thảo hỏi lịch công tác cuối tuần và các cuộc họp buổi tối."),
        _segment("006", "Thảo xem hồ sơ rồi xác nhận công ty không có dự án khẩn trong ngày hôm ấy."),
        _segment("007", "Cô nói Lan thường đi riêng với cấp trên trực tiếp sau giờ làm tại văn phòng."),
        _segment("008", "Hoàng ngồi bên bàn chờ Lan về để hỏi thẳng những lần vắng nhà không rõ lý do."),
    ]
    part_one = [
        _segment("001", "Lá thư mở đầu bằng một dấu hiệu bất thường trong gia đình.", "HOOK"),
        _segment("002", "Hoàng ghi lại từng mốc giờ xuất hiện trong lịch sinh hoạt."),
        _segment("003", "Anh so sánh lịch đó với những lần Lan báo tăng ca."),
        _segment("004", "Một khoảng trống cuối tuần khiến anh quyết định kiểm tra."),
        *investigation,
        *[_segment(f"{i:03d}", f"Chi tiết độc lập thứ {i} mở ra một hướng xác minh khác trong câu chuyện.") for i in range(9, 21)],
    ]
    bad_part_two = [
        _segment("021", "Hoàng gọi lại cho Thảo để hỏi lịch công tác cuối tuần và cuộc họp buổi tối."),
        _segment("022", "Sau khi xem hồ sơ, Thảo xác nhận công ty không có dự án khẩn trong ngày đó."),
        _segment("023", "Lan thường đi riêng với cấp trên trực tiếp sau giờ làm tại văn phòng, cô nói."),
        _segment("024", "Hoàng ngồi bên bàn đợi Lan về để hỏi những lần vắng nhà không rõ lý do."),
        *[_segment(f"{i:03d}", f"Diễn biến phần hai riêng biệt thứ {i} đưa sự việc tới kết luận.") for i in range(25, 37)],
        _segment("037", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
    ]
    good_part_two = [
        *[_segment(f"{i:03d}", f"Chứng cứ mới riêng biệt thứ {i} nối tiếp trực tiếp hành động cuối phần trước.") for i in range(21, 37)],
        _segment("037", "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.", "ENDING"),
    ]
    responses = iter([part_one, bad_part_two, good_part_two])
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs["prompt"])
        return json.dumps(next(responses), ensure_ascii=False), 10, 20

    monkeypatch.setattr(provider, "_call_generate_content", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.gemini_provider.time.sleep", lambda _seconds: None)

    script, _, _ = provider.write_script(_bible(), {}, {})
    assert script.writer_strategy == "two_pass_seamed"

    assert len(calls) == 3
    assert "kể lại một chuỗi sự kiện" in calls[-1]
    assert not has_repeated_narrative_block(script.segments)
