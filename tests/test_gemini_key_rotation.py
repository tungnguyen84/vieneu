import io
import json
import urllib.error

import pytest

from apps.script_factory.providers import gemini_provider as gp

PER_DAY_429 = json.dumps({"error": {"code": 429, "details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}})
PER_MINUTE_429 = json.dumps({"error": {"code": 429, "details": [{"retryDelay": "37s"}]}})


def _ok(text="ok"):
    body = json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4}})

    class _Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(body.encode("utf-8"))


def _http_error(url, code, body):
    return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(body.encode("utf-8")))


@pytest.fixture
def calls(monkeypatch):
    """Routes fake responses by (model, key) and records the call order."""
    monkeypatch.setattr(gp, "_QUOTA_BLOCKS", {})
    monkeypatch.setattr(gp.time, "sleep", lambda _s: None)
    routes = {}
    seen = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        model = url.split("/models/")[1].split(":")[0]
        key = url.split("key=")[1]
        seen.append((model, key))
        outcome = routes.get((model, key), routes.get((model, "*"), (404, "{}")))
        if outcome == "ok":
            return _ok(f"{model}|{key}")
        raise _http_error(url, *outcome)

    monkeypatch.setattr(gp.urllib.request, "urlopen", fake_urlopen)
    return routes, seen


def test_rotates_keys_on_same_model_before_degrading(calls):
    routes, seen = calls
    routes[("gemini-3.8-flash", "K1")] = (429, PER_DAY_429)
    routes[("gemini-3.8-flash", "K2")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1", "K2"], default_model="gemini-3.8-flash")
    text, _, _ = provider._call_generate_content(prompt="x")
    assert text == "gemini-3.8-flash|K2"
    assert provider.last_used_key_index == 1
    # The exhausted key/model pair is skipped on the next call.
    provider._call_generate_content(prompt="x")
    assert seen.count(("gemini-3.8-flash", "K1")) == 1


def test_falls_back_down_the_flash_chain_when_all_keys_exhausted(calls):
    routes, _ = calls
    routes[("gemini-3.8-flash", "*")] = (429, PER_DAY_429)
    routes[("gemini-3.7-flash", "*")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1", "K2"], default_model="gemini-3.8-flash")
    text, _, _ = provider._call_generate_content(prompt="x")
    assert text.startswith("gemini-3.7-flash|")


def test_review_calls_never_use_lite_models(calls):
    routes, _ = calls
    for model in gp.GEMINI_FLASH_CHAIN:
        routes[(model, "*")] = (429, PER_DAY_429)
    for model in gp.GEMINI_LITE_CHAIN:
        routes[(model, "*")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1"], default_model="gemini-3.8-flash")
    with pytest.raises(RuntimeError):
        provider._call_generate_content(prompt="x", allow_lite_models=False)
    text, _, _ = provider._call_generate_content(prompt="x")  # writing may still use lite
    assert "lite" in text


def test_invalid_key_is_dropped_for_every_model(calls):
    routes, seen = calls
    routes[("gemini-3.8-flash", "BAD")] = (400, '{"error": {"status": "INVALID_ARGUMENT", "message": "API key not valid"}}')
    routes[("gemini-3.8-flash", "GOOD")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["BAD", "GOOD"], default_model="gemini-3.8-flash")
    provider._call_generate_content(prompt="x")
    assert gp._is_blocked("BAD", "gemini-2.5-flash")


def test_quota_block_durations():
    now = 1_000_000.0
    assert gp._quota_block_until(PER_MINUTE_429, now) == now + 38
    assert gp._quota_block_until(PER_DAY_429, now) > now + 60
    assert gp._quota_block_until('{"error": {"code": 429}}', now) == now + 600


def test_error_messages_never_contain_keys(calls):
    routes, _ = calls
    for model in [*gp.GEMINI_FLASH_CHAIN, *gp.GEMINI_LITE_CHAIN]:
        routes[(model, "*")] = (500, '{"error": "boom for key SECRETKEY123"}')
    provider = gp.GeminiScriptAIProvider(api_keys=["SECRETKEY123"], default_model="gemini-3.8-flash")
    with pytest.raises(RuntimeError) as exc:
        provider._call_generate_content(prompt="x")
    assert "SECRETKEY123" not in str(exc.value)


def test_overloaded_model_is_skipped_for_all_keys_without_waiting(calls):
    routes, seen = calls
    routes[("gemini-3.8-flash", "*")] = (503, '{"error": {"code": 503, "status": "UNAVAILABLE"}}')
    routes[("gemini-3.7-flash", "*")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1", "K2", "K3"], default_model="gemini-3.8-flash")
    text, _, _ = provider._call_generate_content(prompt="x")
    assert text == "gemini-3.7-flash|K1"
    assert seen.count(("gemini-3.8-flash", "K1")) == 1
    assert ("gemini-3.8-flash", "K2") not in seen


def test_hanging_model_is_parked_after_one_timeout(monkeypatch, calls):
    routes, seen = calls
    original = gp.urllib.request.urlopen

    def hang_on_38(req, timeout=None):
        if "/models/gemini-3.8-flash:" in req.full_url:
            seen.append(("gemini-3.8-flash", "timeout"))
            raise TimeoutError("The read operation timed out")
        return original(req, timeout=timeout)

    monkeypatch.setattr(gp.urllib.request, "urlopen", hang_on_38)
    routes[("gemini-3.7-flash", "*")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1", "K2"], default_model="gemini-3.8-flash")
    text, _, _ = provider._call_generate_content(prompt="x")
    assert text.startswith("gemini-3.7-flash")
    assert seen.count(("gemini-3.8-flash", "timeout")) == 1


def test_review_sticks_to_the_model_that_judged_last(calls):
    routes, seen = calls
    routes[("gemini-3.8-flash", "*")] = (503, "{}")
    routes[("gemini-3.7-flash", "*")] = "ok"
    provider = gp.GeminiScriptAIProvider(api_keys=["K1"], default_model="gemini-3.8-flash")
    provider.complete_json("s", "p")
    gp._QUOTA_BLOCKS.clear()  # 3.8 recovers, but the judge should not change mid-job
    routes[("gemini-3.8-flash", "*")] = "ok"
    text, _, _ = provider.complete_json("s", "p")
    assert text.startswith("gemini-3.7-flash")
