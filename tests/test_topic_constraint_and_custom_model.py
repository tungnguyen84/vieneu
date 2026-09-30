"""Unit and Integration tests for Topic Hard Constraint and Custom Model Input."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from apps.script_factory.cost_control import CostController
from apps.script_factory.idea_generator import IdeaGenerator
from apps.script_factory.models import IdeaItem, StoryBible
from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider
from apps.script_factory.providers.mock_provider import MockScriptAIProvider
from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider
from apps.script_factory.story_planner import StoryPlanner
from apps.script_factory.topic_intent import TopicIntent, extract_topic_intent
from studio.backend.credentials import (
    get_public_providers_status,
    save_provider_credentials,
    test_provider_connection as run_test_provider_connection,
)
from studio.backend.services.generation_service import GenerationService, get_configured_ai_provider


def test_user_topic_has_priority_over_series_default():
    """1. User topic must override default series themes and be enforced as authoritative constraint."""
    user_topic = "Bí mật ngoại tình công sở"
    intent = extract_topic_intent(user_topic)

    assert intent.original_topic == user_topic
    assert any("ngoại tình" in el for el in intent.required_semantic_elements)
    assert "công sở" in intent.context.lower()

    # Verify Gemini provider prompt formatting
    provider = GeminiScriptAIProvider(api_key="TEST_FAKE_KEY")
    with patch.object(provider, "_call_generate_content") as mock_call:
        mock_call.return_value = (
            json.dumps([{
                "working_title": "Góc khuất văn phòng",
                "hook": "Trưởng phòng phát hiện bằng chứng ngoại tình công sở giữa hai đồng nghiệp.",
                "protagonist": "Bảo Nam",
                "relationship": "Đồng nghiệp",
                "central_secret": "Mối quan hệ ngoại tình công sở vụng trộm kéo dài 2 năm",
                "mystery_question": "Ai là người gửi email nặc danh tống tiền?",
                "false_lead": "Nghi ngờ kế toán trưởng",
                "clue_1": "Hóa đơn khách sạn gần công ty",
                "clue_2": "Camera an ninh tầng 8",
                "clue_3": "Tin nhắn trong điện thoại phụ",
                "reveal_1": "Bản hợp đồng dự án bị rò rỉ",
                "reveal_2": "Vụ ngoại tình thực chất là bình phong che giấu việc bảo vệ nhân chứng",
                "emotional_payoff": "Sự thấu hiểu và tha thứ",
                "reflection_theme": "Ranh giới đạo đức",
                "hook_archetype": "MESSAGE",
                "twist_archetype": "Workplace betrayal",
                "curiosity": 9.0,
                "emotional_potential": 8.5,
                "mystery_potential": 8.8,
                "logical_plausibility": 9.0,
                "long_form_potential": 8.5
            }]),
            100,
            200
        )

        ideas, _, _ = provider.generate_ideas(
            count=1,
            existing_ideas=[],
            diversity_categories=["Workplace"],
            hook_archetypes=["MESSAGE"],
            user_topic=user_topic,
            topic_intent=intent,
        )

        # Ensure call prompt contained authoritative user topic directive
        call_kwargs = mock_call.call_args[1]
        system_instruction = call_kwargs["system_instruction"]
        prompt = call_kwargs["prompt"]
        assert f"CHỦ ĐỀ BẮT BUỘC TỪ NGƯỜI DÙNG: '{user_topic}'" in system_instruction
        assert "USER TOPIC IS AUTHORITATIVE" in system_instruction
        assert f"Bám sát chủ đề '{user_topic}'" in prompt

        assert len(ideas) == 1
        assert ideas[0].original_user_topic == user_topic
        assert ideas[0].topic_adherence_score >= 85.0


def test_topic_intent_persisted(tmp_path: Path):
    """2. TopicIntent must be persisted in IdeaItem, StoryBible, and project.json."""
    user_topic = "Bí mật ngoại tình công sở"
    intent = extract_topic_intent(user_topic)

    idea = IdeaItem(
        idea_id="IDEA_TEST_001",
        working_title="Hợp đồng bóng tối",
        hook="Phát hiện dấu hiệu ngoại tình công sở.",
        protagonist="Hoàng",
        relationship="Đồng nghiệp",
        central_secret="Bí mật ngoại tình công sở",
        mystery_question="Ai đứng sau?",
        false_lead="Nghi ngờ đồng nghiệp A",
        clue_1="Hóa đơn",
        clue_2="Camera",
        clue_3="Email",
        reveal_1="Hé lộ nhân chứng",
        reveal_2="Chân tướng",
        emotional_payoff="Hóa giải",
        reflection_theme="Suy ngẫm",
        hook_archetype="MESSAGE",
        twist_archetype="Workplace",
        original_user_topic=user_topic,
        topic_intent=intent.to_dict(),
        topic_adherence_score=95.0
    )

    d = idea.to_dict()
    assert d["original_user_topic"] == user_topic
    assert d["topic_intent"]["original_topic"] == user_topic
    assert d["topic_adherence_score"] == 95.0

    restored = IdeaItem.from_dict(d)
    assert restored.original_user_topic == user_topic
    assert restored.topic_intent["primary_theme"] == intent.primary_theme
    assert restored.topic_adherence_score == 95.0


def test_topic_adherence_rejects_drift():
    """3. Topic adherence calculates score accurately and flags or repairs drift below 85."""
    user_topic = "Bí mật ngoại tình công sở"
    intent = extract_topic_intent(user_topic)

    # Compliant content: workplace + infidelity
    good_idea = {
        "title": "Bí mật phòng họp",
        "hook": "Phát hiện mối quan hệ ngoại tình công sở giữa sếp và nhân viên.",
        "central_secret": "Vụ ngoại tình công sở giấu kín 3 năm.",
        "relationship": "Sếp và cấp dưới"
    }
    score_good = intent.calculate_adherence_score(good_idea)
    assert score_good >= 85.0

    # Unrelated content: family inheritance
    bad_idea = {
        "title": "Bức di chúc của người cha",
        "hook": "Hai anh em tranh chấp mảnh đất hương hỏa ở quê nhà.",
        "central_secret": "Người cha để lại hai bản di chúc giả.",
        "relationship": "Hai anh em ruột"
    }
    score_bad = intent.calculate_adherence_score(bad_idea)
    assert score_bad < 50.0


def test_idea_diversity_without_topic_drift():
    """4. Multiple ideas under same topic maintain distinct plots while all adhering to topic >= 85."""
    user_topic = "Bí mật ngoại tình công sở"
    provider = MockScriptAIProvider()
    ideas, _, _ = provider.generate_ideas(
        count=5,
        existing_ideas=[],
        diversity_categories=[],
        hook_archetypes=[],
        user_topic=user_topic
    )

    assert len(ideas) == 5
    titles = [i.working_title for i in ideas]
    assert len(set(titles)) == 5  # All unique titles

    for idea in ideas:
        assert idea.original_user_topic == user_topic
        assert idea.topic_adherence_score is not None
        assert idea.topic_adherence_score >= 85.0
        # Check topic presence in content
        combined_text = f"{idea.working_title} {idea.hook} {idea.central_secret}".lower()
        assert "ngoại tình" in combined_text or "công sở" in combined_text


def test_story_planner_preserves_original_topic(tmp_path: Path):
    """5. StoryPlanner preserves original_user_topic, topic_intent, topic_adherence on StoryBible."""
    user_topic = "Bí mật ngoại tình công sở"
    intent = extract_topic_intent(user_topic)

    idea = IdeaItem(
        idea_id="IDEA_002",
        working_title="Tập 2: Ngoại tình công sở",
        hook="Dấu vết ngoại tình tại văn phòng.",
        protagonist="Khánh",
        relationship="Đồng nghiệp",
        central_secret="Bí mật ngoại tình công sở",
        mystery_question="Ai đã chụp lén?",
        false_lead="Nghi ngờ bảo vệ",
        clue_1="Ảnh chụp mờ",
        clue_2="Lịch họp bất thường",
        clue_3="Sao kê tài chính",
        reveal_1="Không phải tống tiền mà là bảo vệ bí mật công ty",
        reveal_2="Mối quan hệ giả lập để phát hiện gián điệp thương mại",
        emotional_payoff="Giải tỏa hiểu lầm",
        reflection_theme="Lòng tin nơi công sở",
        hook_archetype="MESSAGE",
        twist_archetype="Workplace",
        original_user_topic=user_topic,
        topic_intent=intent.to_dict(),
        topic_adherence_score=96.0
    )

    provider = MockScriptAIProvider()
    cost_ctrl = CostController(log_file=tmp_path / "costs.jsonl")
    planner = StoryPlanner(provider=provider, cost_controller=cost_ctrl, episodes_root=tmp_path / "episodes")

    bible = planner.create_story_bible_from_idea(idea=idea, episode_id="EP002")

    assert bible.original_user_topic == user_topic
    assert bible.topic_intent == intent.to_dict()
    assert bible.topic_adherence == 96.0

    # Ensure saved JSON file also retained the fields
    saved_json = tmp_path / "episodes" / "EP002" / "story_bible.json"
    assert saved_json.exists()
    with open(saved_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["original_user_topic"] == user_topic
    assert data["topic_intent"]["original_topic"] == user_topic
    assert data["topic_adherence"] == 96.0


def test_custom_model_id_saved(tmp_path: Path):
    """6. Arbitrary custom model ID is persisted accurately."""
    custom_model = "gemini-1.5-pro-custom-preview-2026"
    with patch("studio.backend.credentials.SECRETS_FILE", tmp_path / "providers.enc"):
        res = save_provider_credentials(
            provider="gemini",
            api_key="TEST_CUSTOM_KEY",
            model_id=custom_model,
            set_as_default=True
        )
        assert res["status"] == "saved"
        gemini_info = res["providers"]["gemini"]
        assert gemini_info["model"] == custom_model
        assert gemini_info["model_id"] == custom_model


def test_custom_model_used_for_real_request(tmp_path: Path):
    """7. GenerationService creates provider with exact custom model ID."""
    custom_model = "gemini-ultra-special-v2"
    with patch("studio.backend.credentials.SECRETS_FILE", tmp_path / "providers.enc"):
        save_provider_credentials(
            provider="gemini",
            api_key="TEST_CUSTOM_KEY",
            model_id=custom_model,
            set_as_default=True
        )

        prov = get_configured_ai_provider()
        assert prov.provider_name == "gemini"
        assert prov.default_model == custom_model


def test_custom_model_no_silent_fallback():
    """8. Testing connection or calling custom model fails loudly without silent fallback."""
    provider = GeminiScriptAIProvider(api_key="INVALID_TEST_KEY", default_model="custom-nonexistent-model-xyz")

    # When testing connection with non-existent model, test_provider_connection returns clear failure
    test_res = run_test_provider_connection(
        provider="gemini",
        api_key="INVALID_TEST_KEY",
        model="custom-nonexistent-model-xyz"
    )
    assert test_res["success"] is False
    assert test_res["model"] == "custom-nonexistent-model-xyz"

    # Direct generate call with unknown model and allow_fallback=False must not fallback silently
    with pytest.raises(Exception):
        provider._call_generate_content(
            prompt="Hello",
            model="custom-nonexistent-model-xyz",
            allow_fallback=False
        )


def test_custom_model_supported_openai_compatible(tmp_path: Path):
    """9. Custom model is supported across OpenAI and OpenAI-Compatible providers."""
    custom_openai_model = "deepseek-ai/DeepSeek-V3-preview"
    prov = OpenAICompatibleProvider(
        api_key="TEST_KEY",
        default_model=custom_openai_model,
        base_url="https://api.deepseek.com/v1",
        provider_name="openai_compatible"
    )
    assert prov.default_model == custom_openai_model
    assert prov.provider_name == "openai_compatible"

    # Save and check credentials persistence
    with patch("studio.backend.credentials.SECRETS_FILE", tmp_path / "providers.enc"):
        res = save_provider_credentials(
            provider="openai_compatible",
            api_key="TEST_KEY",
            model_id=custom_openai_model,
            base_url="https://api.deepseek.com/v1",
        )
        assert res["providers"]["openai_compatible"]["model"] == custom_openai_model
