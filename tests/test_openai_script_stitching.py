import json

import pytest

from apps.script_factory.models import StoryBible
from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider


@pytest.fixture(autouse=True)
def _no_scene_outline(monkeypatch):
    """These tests script the exact sequence of part-1/part-2 model replies;
    the single-pass and scene-outline calls are covered by tests/test_scene_outline.py and tests/test_single_pass_writer.py."""
    for module in ("apps.script_factory.providers.gemini_provider", "apps.script_factory.providers.openai_provider"):
        monkeypatch.setattr(f"{module}.build_scene_outline", lambda *args, **kwargs: None)
        monkeypatch.setattr(f"{module}.write_single_pass", lambda *args, **kwargs: (None, 0, 0))



def _segment(index: int, text: str | None = None, profile: str = "NORMAL") -> dict:
    return {
        "id": f"{index:03d}",
        "speaker": "MINH",
        "text": text or f"Chi tiết cụ thể thứ {index} tiếp tục mạch xác minh của Hoàng.",
        "delivery_profile": profile,
        "importance": "normal",
        "audience_address": False,
        "speed": 1.0,
    }


def _part(start: int, count: int = 35) -> list[dict]:
    return [_segment(index) for index in range(start, start + count)]


def _bible() -> StoryBible:
    return StoryBible(
        episode_id="EP_OPENAI_STITCH",
        title="Những ca tăng không có trong lịch",
        protagonist={"name": "Hoàng", "age": 35, "description": "Người gửi thư"},
        secret="Linh che giấu mối quan hệ tình cảm bí mật với đồng nghiệp.",
        mystery_question="Những ca tăng của Linh đang che giấu điều gì?",
        false_lead="Hoàng nghĩ Linh chịu áp lực dự án.",
        reveal_1="Người Linh gặp là một đồng nghiệp cùng cơ quan.",
        reveal_2="Linh thừa nhận mối quan hệ đã vượt qua ranh giới đồng nghiệp.",
        emotional_payoff="Hai người đối diện hậu quả bằng một cuộc trò chuyện thẳng thắn.",
        reflection_theme="Niềm tin cần sự thành thật.",
        ending="Hoàng và Linh cùng chịu trách nhiệm cho lựa chọn của mình.",
        original_user_topic="Linh ngoại tình với đồng nghiệp và lấy lý do tăng ca để che giấu.",
    )


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(api_key="fake", base_url="https://example.invalid/v1", default_model="auto")


def test_openai_compatible_retries_part_one_that_closes_early(monkeypatch):
    bad_part_one = _part(1)
    bad_part_one[-1] = _segment(
        35,
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
        "ENDING",
    )
    good_part_one = _part(1)
    good_part_two = _part(36)
    good_part_two[-1] = _segment(
        70,
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
        "ENDING",
    )
    responses = iter([bad_part_one, good_part_one, good_part_two])
    calls = []

    def fake_call(messages, **_kwargs):
        calls.append(messages[-1]["content"])
        return json.dumps({"segments": next(responses)}, ensure_ascii=False), 10, 20

    provider = _provider()
    monkeypatch.setattr(provider, "_call_chat_completion", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.openai_provider.time.sleep", lambda _seconds: None)

    script, input_tokens, output_tokens = provider.write_script(_bible(), {}, {})

    assert len(calls) == 3
    assert "YÊU CẦU SỬA BẮT BUỘC" in calls[1]
    assert len(script.segments) == 70
    assert script.writer_strategy == "two_pass_seamed"
    assert [s.delivery_profile for s in script.segments].count("ENDING") == 1
    assert script.segments[-1].delivery_profile == "ENDING"
    assert input_tokens == 30
    assert output_tokens == 60


def test_openai_compatible_normalizes_sender_thanks_before_final_signoff(monkeypatch):
    part_one = _part(1)
    part_two = _part(36)
    part_two[-2] = _segment(69, "Cảm ơn Hoàng đã gửi lá thư chân thành về chương trình.", "ENDING")
    part_two[-1] = _segment(
        70,
        "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại.",
        "ENDING",
    )
    responses = iter([part_one, part_two])

    def fake_call(_messages, **_kwargs):
        return json.dumps({"segments": next(responses)}, ensure_ascii=False), 10, 20

    provider = _provider()
    monkeypatch.setattr(provider, "_call_chat_completion", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.openai_provider.time.sleep", lambda _seconds: None)

    script, _, _ = provider.write_script(_bible(), {}, {})

    assert script.writer_strategy == "two_pass_seamed"
    assert script.segments[-2].delivery_profile == "COMMENT"
    assert script.segments[-1].delivery_profile == "ENDING"
    assert [s.delivery_profile for s in script.segments].count("ENDING") == 1


def test_openai_compatible_rejects_empty_second_part_after_retry(monkeypatch):
    responses = iter([_part(1), [], []])

    def fake_call(_messages, **_kwargs):
        return json.dumps({"segments": next(responses)}, ensure_ascii=False), 10, 20

    provider = _provider()
    monkeypatch.setattr(provider, "_call_chat_completion", fake_call)
    monkeypatch.setattr("apps.script_factory.providers.openai_provider.time.sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="only 0 valid Part 2 segments"):
        provider.write_script(_bible(), {}, {})
