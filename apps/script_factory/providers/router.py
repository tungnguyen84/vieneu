"""Model Router and Multi-Provider Dispatcher for Script Factory V1."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from apps.script_factory.providers.base import ScriptAIProvider
from apps.script_factory.providers.mock_provider import MockScriptAIProvider

logger = logging.getLogger("VieNeu.ModelRouter")


@dataclass
class RouterConfig:
    idea_model: str = "mock-model"
    planner_model: str = "mock-model"
    writer_model: str = "mock-model"
    qc_model: str = "mock-model"
    embedding_model: str = "mock-embedding"
    preferred_provider: str = "mock"


class ModelRouter:
    """Routes generation requests to configured AI providers."""

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self._providers: Dict[str, ScriptAIProvider] = {
            "mock": MockScriptAIProvider()
        }

    def register_provider(self, name: str, provider: ScriptAIProvider) -> None:
        self._providers[name.lower()] = provider

    def get_provider(self, task: str = "general") -> ScriptAIProvider:
        """Returns the appropriate provider based on environment and preference."""
        pref = self.config.preferred_provider.lower()
        if pref in self._providers:
            return self._providers[pref]

        # Check environment for real keys if requested
        if pref == "openai" and os.environ.get("OPENAI_API_KEY"):
            # Could instantiate real OpenAI adapter
            return self._providers.get("openai", self._providers["mock"])
        elif pref == "gemini" and os.environ.get("GEMINI_API_KEY"):
            return self._providers.get("gemini", self._providers["mock"])
        elif pref == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            return self._providers.get("anthropic", self._providers["mock"])

        # Default fallback is always Mock provider
        return self._providers["mock"]

    def get_model_for_task(self, task: str) -> str:
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
        return "default-model"
