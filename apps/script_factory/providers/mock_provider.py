"""Test-Only Mock Provider Proxy.

PRODUCTION USE IS STRICTLY FORBIDDEN.
This provider is moved to tests/mocks/mock_script_provider.py.
"""
from __future__ import annotations

import os

if os.environ.get("APP_ENV") != "test" and os.environ.get("ALLOW_MOCK_AI") != "1":
    raise RuntimeError(
        "CRITICAL ARCHITECTURAL VIOLATION: MockScriptAIProvider was loaded in production runtime! "
        "Production must NEVER import, instantiate or fall back to mock creative data."
    )

try:
    from tests.mocks.mock_script_provider import MockScriptAIProvider
except ImportError:
    # If running in environment without tests folder
    raise RuntimeError("MockScriptAIProvider is test-only and not available in production.")

__all__ = ["MockScriptAIProvider"]
