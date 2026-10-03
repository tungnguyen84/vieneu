from apps.script_factory.models import StoryBible
from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
from apps.script_factory.single_pass_writer import MIN_SEGMENTS, parse_tagged_lines, write_single_pass

SIGNOFF = "Cảm ơn quý vị đã lắng nghe. Tôi là Minh. Xin chào và hẹn gặp lại."


def _episode(body_lines: int = 80, ended: bool = True) -> str:
    lines = ['[HOOK] "Em không biết nên bắt đầu từ đâu." Hoàng viết như vậy.',
             "[NORMAL] Chào mừng quý vị và các bạn đến với Sau Cánh Cửa."]
    lines += [
        f"[NORMAL] Chi tiết cụ thể thứ {i} tiếp tục mạch xác minh của Hoàng, khi anh đứng trong căn bếp nhỏ "
        "nhìn chiếc áo khoác màu be và nhớ lại từng lời vợ nói tối hôm trước."
        for i in range(body_lines)
    ]
    if ended:
        lines += ["[QUESTION] Nếu là bạn, bạn sẽ hỏi thẳng hay im lặng?", f"[ENDING] {SIGNOFF}"]
    return "\n".join(lines)


def test_parse_tagged_lines_maps_tags_and_joins_wrapped_lines():
    raw = (
        "```\n"
        "[HOOK] Câu mở đầu.\n"
        "- [mystery] Một điều lạ.\n"
        "dòng bị xuống hàng\n"
        "\n"
        "[QUESTION] Bạn sẽ làm gì?\n"
        "[REVEAL] Sự thật.\n"
        "[ENDING] Chào.\n"
        "```"
    )
    segments = parse_tagged_lines(raw)
    assert [s["delivery_profile"] for s in segments] == ["HOOK", "MYSTERY", "COMMENT", "REVEAL", "ENDING"]
    assert segments[1]["text"] == "Một điều lạ. dòng bị xuống hàng"
    assert segments[2]["audience_address"] is True
    assert segments[3]["audience_address"] is False


def test_parse_tagged_lines_ignores_preamble_before_first_tag():
    segments = parse_tagged_lines("Dưới đây là kịch bản:\n[HOOK] Câu mở đầu.")
    assert [s["text"] for s in segments] == ["Câu mở đầu."]


def test_write_single_pass_returns_segments_and_tokens():
    segments, in_tok, out_tok = write_single_pass(lambda system, prompt: (_episode(), 11, 22), "sys", "prompt")
    assert segments is not None and len(segments) >= MIN_SEGMENTS
    assert segments[-1]["delivery_profile"] == "ENDING"
    assert (in_tok, out_tok) == (11, 22)


def test_write_single_pass_falls_back_when_truncated():
    calls = []

    def cut_off(system, prompt):
        calls.append(prompt)
        return _episode(ended=False), 5, 6

    segments, in_tok, out_tok = write_single_pass(cut_off, "sys", "prompt")
    assert segments is None
    assert len(calls) == 1
    assert (in_tok, out_tok) == (5, 6)


def test_write_single_pass_expands_a_complete_but_short_episode():
    replies = iter([(_episode(40), 5, 6), (_episode(), 7, 8)])
    prompts = []

    def call(system, prompt):
        prompts.append(prompt)
        return next(replies)

    segments, in_tok, out_tok = write_single_pass(call, "sys", "prompt")
    assert segments is not None and len(segments) >= MIN_SEGMENTS
    assert "BẢN NHÁP TRƯỚC" in prompts[1] and "QUÁ NGẮN" in prompts[1]
    assert (in_tok, out_tok) == (12, 14)


def test_write_single_pass_falls_back_when_still_short_after_expansion():
    segments, _, _ = write_single_pass(lambda system, prompt: (_episode(20), 1, 1), "sys", "prompt")
    assert segments is None


def test_write_single_pass_falls_back_on_call_error():
    def boom(system, prompt):
        raise RuntimeError("proxy down")

    assert write_single_pass(boom, "sys", "prompt") == (None, 0, 0)


def _bible() -> StoryBible:
    return StoryBible(
        episode_id="EP_SINGLE",
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


def test_openai_provider_writes_whole_episode_in_one_call(monkeypatch):
    monkeypatch.setattr("apps.script_factory.providers.openai_provider.build_scene_outline",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("outline must not run")))
    calls = []

    def fake_call(messages, **kwargs):
        calls.append(kwargs)
        return _episode(), 100, 200

    provider = OpenAICompatibleProvider(api_key="fake", base_url="https://example.invalid/v1", default_model="auto")
    monkeypatch.setattr(provider, "_call_chat_completion", fake_call)

    script, in_tok, out_tok = provider.write_script(_bible(), {}, {})

    assert len(calls) == 1 and calls[0]["response_json"] is False
    assert [s.id for s in script.segments[:3]] == ["001", "002", "003"]
    assert script.segments[-1].delivery_profile == "ENDING"
    assert [s.delivery_profile for s in script.segments].count("ENDING") == 1
    assert (in_tok, out_tok) == (100, 200)


def test_gemini_provider_writes_whole_episode_in_one_call(monkeypatch):
    from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider

    monkeypatch.setattr("apps.script_factory.providers.gemini_provider.build_scene_outline",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("outline must not run")))
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        return _episode(), 100, 200

    provider = GeminiScriptAIProvider(api_key="fake")
    monkeypatch.setattr(provider, "_call_generate_content", fake_call)

    script, in_tok, out_tok = provider.write_script(_bible(), {}, {})

    assert len(calls) == 1 and calls[0]["response_json"] is False
    assert script.segments[-1].delivery_profile == "ENDING"
    assert (in_tok, out_tok) == (100, 200)


ENDING = ("Hoàng chuyển sang sống tại căn phòng thuê gần công ty trong thời gian ly thân. Anh tự tay đưa Mai đi học "
          "mỗi sáng, cùng Lan trao đổi lịch chăm sóc con bằng những cuộc nói chuyện có kiểm soát. Câu chuyện kết thúc "
          "bằng hành động Hoàng cất chiếc áo khoác vào một chiếc hộp riêng.")


def _episode_without_resolution() -> str:
    lines = [f"[NORMAL] Cảnh thứ {i}: Hoàng quan sát vợ thật kỹ trong căn bếp nhỏ, nhớ lại từng lời cô nói tối hôm trước "
             "và tự hỏi điều gì đang thay đổi trong ngôi nhà của mình suốt những tháng qua." for i in range(80)]
    lines += ["[COMMENT] Sự phản bội lớn dần từ những khoảng im lặng.",
              "[QUESTION] Còn bạn, bạn sẽ chọn sự thật hay sự bình yên?", f"[ENDING] {SIGNOFF}"]
    return "\n".join(lines)


def test_write_single_pass_inserts_missing_resolution_before_closing():
    resolution = "\n".join([
        "[NORMAL] Hoàng chuyển sang căn phòng thuê gần công ty trong thời gian ly thân.",
        "[NORMAL] Mỗi sáng anh vẫn tự tay đưa Mai đi học như trước.",
        "[NORMAL] Anh và Lan trao đổi lịch chăm sóc con bằng những cuộc nói chuyện có kiểm soát.",
        "[NORMAL] Ngày dọn đi, Hoàng cất chiếc áo khoác vào một chiếc hộp riêng.",
        "[COMMENT] Một lời chiêm nghiệm thừa.",
    ])
    replies = iter([(_episode_without_resolution(), 1, 1), (resolution, 2, 2)])
    prompts = []

    def call(system, prompt):
        prompts.append(prompt)
        return next(replies)

    segments, in_tok, out_tok = write_single_pass(call, "sys", "prompt", ending=ENDING)
    assert "BỎ QUA PHẦN GIẢI QUYẾT" in prompts[1]
    texts = [s["text"] for s in segments]
    assert texts[80].startswith("Hoàng chuyển sang căn phòng thuê")
    assert texts[83].startswith("Ngày dọn đi")
    assert "Một lời chiêm nghiệm thừa." not in texts
    assert [s["delivery_profile"] for s in segments[-3:]] == ["COMMENT", "COMMENT", "ENDING"]
    assert (in_tok, out_tok) == (3, 3)


def test_write_single_pass_keeps_delivered_resolution():
    calls = []

    def call(system, prompt):
        calls.append(prompt)
        return _episode(), 1, 1

    write_single_pass(call, "sys", "prompt", ending="")
    assert len(calls) == 1


def test_write_single_pass_keeps_complete_episode_slightly_under_target():
    """EP2009: a coherent 78-line, 1,879-word episode was discarded for a seamed two-part one."""
    segments, _, _ = write_single_pass(lambda system, prompt: (_episode(60), 1, 1), "sys", "prompt")
    assert segments is not None and len(segments) == 64


def test_write_single_pass_prunes_distant_story_restart():
    """When a model echoes draft 1 and then draft 2, or restarts the story,
    write_single_pass detects the restart and extracts the complete draft."""
    first_draft = [
        '[HOOK] "Lúc 2 giờ sáng, chuông điện thoại reo dồn dập." Vân viết.',
        '[NORMAL] Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.',
    ] + [f"[NORMAL] Chi tiết bước đi số {i} của Vân khi theo dõi sự việc." for i in range(50)] + [
        '[REVEAL] Hóa ra người chồng đang che giấu một mối quan hệ khác.',
        '[COMMENT] Lời chiêm nghiệm về niềm tin trong hôn nhân.',
        '[QUESTION] Bạn sẽ làm gì khi phát hiện sự thật?',
    ]
    second_draft = [
        '[HOOK] "Lúc 2 giờ sáng, chuông điện thoại reo dồn dập." Vân viết lại.',
        '[NORMAL] Chào mừng quý vị và các bạn đến với Sau Cánh Cửa.',
    ] + [f"[NORMAL] Chi tiết bước đi số {i} mở rộng sâu sắc hơn của Vân khi theo dõi sự việc." for i in range(55)] + [
        '[REVEAL] Hóa ra người chồng đang che giấu một mối quan hệ khác tại công sở.',
        '[COMMENT] Lời chiêm nghiệm về niềm tin trong hôn nhân gia đình.',
        '[QUESTION] Bạn sẽ làm gì khi đối diện sự thật?',
        f'[ENDING] {SIGNOFF}',
    ]
    combined_raw = "\n".join(first_draft + second_draft)
    segments, _, _ = write_single_pass(lambda sys, prompt: (combined_raw, 10, 20), "sys", "prompt")
    assert segments is not None
    assert len(segments) == len(second_draft)
    assert segments[-1]["delivery_profile"] == "ENDING"
    assert sum(1 for s in segments if "Chào mừng quý vị" in s["text"]) == 1

