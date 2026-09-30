"""Model Router and Multi-Provider Dispatcher for Script Factory V1."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.providers.gemini_provider import GeminiScriptAIProvider, _get_api_key

logger = logging.getLogger("VieNeu.ModelRouter")


@dataclass
class RouterConfig:
    idea_model: str = "gemini-2.5-flash"
    planner_model: str = "gemini-2.5-flash"
    writer_model: str = "gemini-2.5-flash"
    qc_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    preferred_provider: str = "gemini"


class ModelRouter:
    """Routes generation requests to configured AI providers."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self._providers: Dict[str, ScriptAIProvider] = {}
        # Check if Gemini API key exists
        gemini_key = _get_api_key()
        if gemini_key:
            self._providers["gemini"] = GeminiScriptAIProvider(
                api_key=gemini_key,
                default_model=self.config.idea_model,
                embedding_model=self.config.embedding_model,
            )

    def register_provider(self, name: str, provider: ScriptAIProvider) -> None:
        self._providers[name.lower()] = provider

    def get_provider(self, task: str = "general") -> ScriptAIProvider:
        """Returns the appropriate real AI provider based on environment and preference."""
        pref = self.config.preferred_provider.lower()
        if pref in self._providers:
            return self._providers[pref]

        # Check environment for real keys if requested
        gemini_key = _get_api_key()
        if gemini_key:
            if "gemini" not in self._providers:
                self._providers["gemini"] = GeminiScriptAIProvider(api_key=gemini_key)
            return self._providers["gemini"]

        if os.environ.get("APP_ENV") == "test" or os.environ.get("ALLOW_MOCK_AI") == "1":
            if "mock" in self._providers:
                return self._providers["mock"]
            from tests.mocks.mock_script_provider import MockScriptAIProvider
            mock_p = MockScriptAIProvider()
            self._providers["mock"] = mock_p
            return mock_p

        raise RuntimeError(
            "AI generation failed: No valid AI provider credentials found. "
            "Please configure your GEMINI_API_KEY in Settings."
        )

    def get_connection_status(self) -> Dict[str, Any]:
        """Returns clear status for UI: Provider, Model, Connection Status."""
        provider = self.get_provider()
        model = self.get_model_for_task("idea")
        if provider.provider_name == "mock":
            return {
                "provider": "Mock Provider",
                "model": "mock-model",
                "status": "MOCK PROVIDER — NOT FOR PRODUCTION",
                "is_mock": True,
            }
        return {
            "provider": provider.provider_name.upper(),
            "model": model,
            "status": "CONNECTED (Ready for Pilot)",
            "is_mock": False,
        }

    def get_model_for_task(self, task: str) -> str:
        provider = self.get_provider()
        if provider.provider_name == "mock":
            return "mock-model"
        if task == "idea":
            return self.config.idea_model
        elif task == "planner":
            return self.config.planner_model
        elif task == "writer":
            return self.config.writer_model
        elif task == "qc":
            return self.config.qc_model
        elif task == "embedding":
            return self.config.embedding_model
        return self.config.idea_model
