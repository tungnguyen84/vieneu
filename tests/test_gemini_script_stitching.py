import json

import pytest

from apps.script_factory.models import StoryBible
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider


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
    assert [segment.delivery_profile for segment in script.segments].count("ENDING") == 1
    assert script.segments[-1].delivery_profile == "ENDING"
    assert input_tokens == 30
    assert output_tokens == 60


def test_gemini_rejects_script_when_second_part_still_has_early_signoff(monkeypatch):
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

    with pytest.raises(RuntimeError, match="exactly one final sign-off"):
        provider.write_script(_bible(), {}, {})
