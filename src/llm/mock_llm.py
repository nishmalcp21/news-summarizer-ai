"""
Tier 1: Fake LLM Client for testing in plain Python.
Provides deterministic responses for query rewriting, step decisions,
article summarization, and quick summary synthesis without network or API costs.
"""

from typing import List, Dict, Any, Tuple
from src.llm.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Deterministic Mock LLM client for Tier 1 testing."""

    def __init__(self, mode: str = "normal", fail_step_limit: bool = False):
        """
        mode: 'normal' for standard progression, or custom mode.
        fail_step_limit: If True, continuously returns non-finishing actions to test MAX_STEPS.
        """
        self.mode = mode
        self.fail_step_limit = fail_step_limit
        self.recorded_calls: List[Dict[str, Any]] = []

    def rewrite_query(self, topic: str) -> List[str]:
        self.recorded_calls.append({"method": "rewrite_query", "topic": topic})
        return [
            f"{topic} recent developments",
            f"{topic} news updates"
        ]

    def summarize_article(self, story_id: str, article_text: str) -> str:
        self.recorded_calls.append({"method": "summarize_article", "story_id": story_id})
        # Extract first 150 characters for a realistic deterministic summary
        snippet = article_text.replace("\n", " ").strip()[:160]
        return f"Summary for {story_id}: Key developments were reported regarding the topic. {snippet}."

    def synthesize_quick_summary(self, topic: str, story_summaries: List[Dict[str, Any]]) -> str:
        self.recorded_calls.append({
            "method": "synthesize_quick_summary",
            "topic": topic,
            "count": len(story_summaries)
        })
        return (
            f"Recent reports on {topic} show sustained momentum across key sectors. "
            f"Industry stakeholders and policymakers are focusing on scalable growth and infrastructure."
        )

    def decide_next_step(
        self,
        step: int,
        plan_steps: List[str],
        scratchpad: Dict[str, Any]
    ) -> Tuple[str, str, Dict[str, Any]]:
        self.recorded_calls.append({
            "method": "decide_next_step",
            "step": step,
            "scratchpad": scratchpad
        })

        if self.fail_step_limit:
            # Continually dispatch dummy actions to hit MAX_STEPS limit
            return (
                f"Step {step}: Need more information.",
                "manage_memory",
                {"action": "set_scratchpad", "key": f"step_{step}", "value": "ping"}
            )

        candidates_count = scratchpad.get("candidates_count", 0)
        extracted_count = scratchpad.get("extracted_count", 0)
        target_count = scratchpad.get("target_count", 5)

        # ReAct step sequence:
        # Step 1: Search news
        if candidates_count == 0:
            return (
                "Need to gather recent news candidates from search.",
                "search_news",
                {"query": "electric vehicles in India", "time_range": "7d"}
            )

        # Step 2: Extract candidate article
        elif extracted_count < min(2, candidates_count):
            return (
                f"Need to extract content for candidate {extracted_count + 1}.",
                "extract_article",
                {
                    "url": "https://example.com/story-1",
                    "story_id": str(extracted_count + 1),
                    "fallback_snippet": "New budget EV launched with 300km range."
                }
            )

        # Step 3: Finish and synthesize
        else:
            return (
                "Sufficient articles gathered. Ready to synthesize digest.",
                "synthesize",
                {}
            )

