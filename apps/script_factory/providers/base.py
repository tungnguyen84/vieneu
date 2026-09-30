"""Abstract Base Class for Script Factory AI Providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from apps.script_factory.models import FullScript, IdeaItem, QCReport, StoryBible


class ScriptAIProvider(ABC):
    """Abstract interface for LLM / Embedding providers in Script Factory."""

    provider_name: str = "base"

    @abstractmethod
    def generate_ideas(
        self,
        count: int,
        existing_ideas: List[IdeaItem],
        diversity_categories: List[str],
        hook_archetypes: List[str],
        model: Optional[str] = None,
        user_topic: Optional[str] = None,
        topic_intent: Optional[Any] = None,
    ) -> Tuple[List[IdeaItem], int, int]:
        """Generates premise ideas. Returns (ideas_list, input_tokens, output_tokens)."""
        pass

    @abstractmethod
    def create_story_bible(
        self,
        idea: IdeaItem,
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        """Expands an idea into a full Story Bible with locked facts."""
        pass

    def repair_story_bible(
        self,
        story_bible: StoryBible,
        qc_issues: List[str],
        series_bible: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Tuple[StoryBible, int, int]:
        """Repairs a Story Bible via AI without local templates."""
        return story_bible, 0, 0

    @abstractmethod
    def write_script(
        self,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        """Writes a full 80-100 segment script adhering to locked facts and delivery profiles."""
        pass

    @abstractmethod
    def review_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        story_formula: Dict[str, Any],
        series_bible: Dict[str, Any],
        model: Optional[str] = None,
    ) -> Tuple[QCReport, int, int]:
        """Performs deep multi-dimensional QC evaluation."""
        pass

    @abstractmethod
    def revise_script(
        self,
        script: FullScript,
        story_bible: StoryBible,
        qc_report: QCReport,
        model: Optional[str] = None,
    ) -> Tuple[FullScript, int, int]:
        """Applies targeted revisions strictly to sections requested by QC."""
        pass

    @abstractmethod
    def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """Generates vector embedding for novelty/similarity calculation."""
        pass
