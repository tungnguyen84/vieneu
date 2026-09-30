"""Tests for Multi-Provider Configuration, Selection, and Dynamic Routing."""
import os
import pytest
from unittest.mock import patch, MagicMock

from apps.script_factory.models import IdeaItem, StoryBible
from apps.script_factory.providers.openai_provider import OpenAICompatibleProvider, _parse_json_safe
from apps.script_factory.providers.anthropic_provider import AnthropicScriptAIProvider
from studio.backend.credentials import (
    get_public_providers_status,
    save_provider_credentials,
    set_default_provider,
)
from studio.backend.services.generation_service import get_configured_ai_provider, GenerationService


def test_set_default_provider_persists_and_reports():
    """Verifies set_default_provider updates default and reports is_default on provider entries."""
    # Set to gemini
    res1 = set_default_provider(provider_id="gemini", model_id="gemini-2.5-flash")
    assert res1["default_provider"] == "gemini"
    status1 = get_public_providers_status()
    assert status1["default_provider"] == "gemini"
    assert status1["providers"]["gemini"]["is_default"] is True

    # Switch to openai_compatible
    res2 = set_default_provider(provider_id="openai_compatible", model_id="deepseek-chat")
    assert res2["default_provider"] == "openai_compatible"
    status2 = get_public_providers_status()
    assert status2["default_provider"] == "openai_compatible"
    assert status2["providers"]["openai_compatible"]["is_default"] is True
    assert status2["providers"]["gemini"]["is_default"] is False

    # Switch back to gemini
    set_default_provider(provider_id="gemini")


def test_get_configured_ai_provider_resolution():
    """Verifies get_configured_ai_provider respects explicit overrides and default settings."""
    os.environ["APP_ENV"] = "test"

    # Explicit provider override
    p_openai = get_configured_ai_provider(provider_id="openai_compatible", model_id="my-custom-model")
    assert isinstance(p_openai, OpenAICompatibleProvider)
    assert p_openai.default_model == "my-custom-model"

    p_gemini = get_configured_ai_provider(provider_id="gemini", model_id="gemini-2.5-pro")
    assert p_gemini.default_model == "gemini-2.5-pro"


def test_openai_compatible_json_parser_robustness():
    """Verifies _parse_json_safe strips markdown code fences and handles trailing commas."""
    fenced_json = "```json\n{\"ideas\": [{\"working_title\": \"Bí mật\", \"id\": 1,}]}\n```"
    parsed = _parse_json_safe(fenced_json)
    assert parsed is not None
    assert "ideas" in parsed
    assert parsed["ideas"][0]["working_title"] == "Bí mật"

    raw_array = "[{\"id\": \"001\", \"text\": \"Lời dẫn 1\",}]"
    parsed_arr = _parse_json_safe(raw_array)
    assert isinstance(parsed_arr, list)
    assert parsed_arr[0]["id"] == "001"


def test_openai_compatible_call_fallback_on_response_format_error():
    """Verifies _call_chat_completion falls back automatically if response_format returns HTTP 400."""
    import urllib.error
    provider = OpenAICompatibleProvider(api_key="test-key", base_url="http://mock-llm.local/v1")

    call_count = 0
    def mock_urlopen(req, timeout=None):
        nonlocal call_count
        call_count += 1
        payload = os.environ.get("_LAST_PAYLOAD", "")
        import json
        req_data = json.loads(req.data.decode("utf-8"))
        if "response_format" in req_data:
            # Simulate endpoint that does not support response_format (HTTP 400)
            fp = MagicMock()
            fp.read.return_value = b'{"error": "response_format is not supported by model"}'
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=fp
            )
        # Second call without response_format succeeds
        resp_mock = MagicMock()
        resp_mock.read.return_value = json.dumps({
            "choices": [{"message": {"content": "{\"status\": \"ok\"}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}
        }).encode("utf-8")
        resp_mock.__enter__.return_value = resp_mock
        return resp_mock

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        content, in_t, out_t = provider._call_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            response_json=True
        )
        assert content == "{\"status\": \"ok\"}"
        assert call_count == 2  # 1st failed with response_format, 2nd succeeded without


def test_server_set_default_endpoint():
    """Verifies POST /api/ai/set-default endpoint via TestClient."""
    from fastapi.testclient import TestClient
    from studio.backend.server import app

    client = TestClient(app)
    resp = client.post("/api/ai/set-default", json={"provider": "gemini", "model": "gemini-2.5-flash"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_provider"] == "gemini"
