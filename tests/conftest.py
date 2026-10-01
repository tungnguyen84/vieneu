"""Pytest configuration for test suite."""
import os

import pytest

os.environ["APP_ENV"] = "test"

_PROVIDER_ENV_VARS = (
    "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "LOCAL_LLM_URL",
)


@pytest.fixture(autouse=True, scope="session")
def _isolate_studio_database(tmp_path_factory):
    """Keep test projects/approvals out of the user's real studio_data.db.

    Session-scoped because some test modules create a project in one test and
    use it in the next; the whole run shares one throwaway database.
    """
    from studio.backend import db

    original = db.DB_FILE
    db.DB_FILE = tmp_path_factory.mktemp("studio_db") / "studio_data.db"
    db.init_db()
    # Same reference episodes the app registers on startup (EP003/EP011).
    from studio.backend.project_manager import ProjectManager

    ProjectManager().auto_migrate_pilots()
    yield
    db.DB_FILE = original


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
