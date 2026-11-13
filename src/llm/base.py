"""
Abstract Base Class for LLM Clients in the News Summarizer Agent.
Supports both Fake/Mock LLMs (Tier 1) and Real API providers (Tier 2).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple


class BaseLLMClient(ABC):

    @abstractmethod
    def rewrite_query(self, topic: str) -> List[str]:
        """Rewrite raw user topic into 1-3 targeted search queries."""
        pass

    @abstractmethod
    def summarize_article(self, story_id: str, article_text: str) -> str:
        """Summarize an article into 2-3 neutral sentences in own words."""
        pass

    @abstractmethod
    def synthesize_quick_summary(self, topic: str, story_summaries: List[Dict[str, Any]]) -> str:
        """Synthesize a 2-3 sentence overview covering the big picture."""
        pass

    @abstractmethod
    def decide_next_step(
        self,
        step: int,
        plan_steps: List[str],
        scratchpad: Dict[str, Any]
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        ReAct reasoning step:
        Returns:
            (thought: str, action: str, action_args: Dict[str, Any])
        """
        pass

