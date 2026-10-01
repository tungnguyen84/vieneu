"""Pytest configuration for test suite."""
import os

import pytest

os.environ["APP_ENV"] = "test"

_PROVIDER_ENV_VARS = (
    "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "LOCAL_LLM_URL",
)


@pytest.fixture(autouse=True)
def _isolate_provider_credentials(tmp_path, monkeypatch):
    """Never let a test read or overwrite the user's real AI provider settings.

    Credentials live in ~/.scc_studio/providers.enc; tests that save, delete or
    switch providers used to write that file directly and wiped real API keys.
    Real keys from .env are hidden as well, so no test silently calls a paid API;
    monkeypatch restores them (and anything a test exported) afterwards.
    """
    from studio.backend import credentials

    secrets_dir = tmp_path / "scc_studio_secrets"
    monkeypatch.setattr(credentials, "SECRETS_DIR", secrets_dir)
    monkeypatch.setattr(credentials, "SECRETS_FILE", secrets_dir / "providers.enc")
    for name in _PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
