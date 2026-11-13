"""
Planner module for News Summarizer Agent.
Generates an explicit structured plan before the agent acts,
validates topics against vague stoplists, and handles human-in-the-loop triggers.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
from src.config import config
from src.logger import logger


@dataclass
class ExecutionPlan:
    topic: str
    num_stories: int
    time_range: str
    steps: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    aborted: bool = False
    abort_reason: Optional[str] = None
    requires_human_confirmation: bool = False
    confirmation_prompt: Optional[str] = None


class PreActionPlanner:
    def __init__(self, human_confirm_callback: Optional[Callable[[str], bool]] = None):
        """
        human_confirm_callback: Optional callable for 'Ask You First' safety prompts.
                                Defaults to standard console input().
        """
        self.human_confirm_callback = human_confirm_callback or self._default_console_confirm

    @staticmethod
    def _default_console_confirm(prompt: str) -> bool:
        """Default interactive console confirmation."""
        logger.log_safety(f"Prompting user: {prompt}")
        try:
            response = input(f"[CONFIRMATION REQUIRED] {prompt} (y/n): ").strip().lower()
            return response.startswith("y")
        except EOFError:
            return True

    def create_plan(self, topic: str, num_stories: int = 5, time_range: str = "7d") -> ExecutionPlan:
        """
        Analyzes the user input, checks the stoplist, and formulates a step-by-step plan.
        """
        clean_topic = (topic or "").strip()

        # 1. Topic validation: length check
        if len(clean_topic) < 2 or len(clean_topic) > 100:
            return ExecutionPlan(
                topic=clean_topic,
                num_stories=num_stories,
                time_range=time_range,
                aborted=True,
                abort_reason="Topic must be between 2 and 100 characters in length."
            )

        # 2. Topic validation: vague topic stoplist check (PRD Section 7.6)
        if config.is_topic_vague(clean_topic):
            logger.log_safety(f"Vague topic detected: '{clean_topic}' matched stoplist.")
            return ExecutionPlan(
                topic=clean_topic,
                num_stories=num_stories,
                time_range=time_range,
                aborted=True,
                abort_reason=(
                    f"'{clean_topic}' is too vague. Please enter a more specific topic "
                    f"(for example: 'electric vehicles in India', 'space exploration 2026', or 'quantum computing advances')."
                )
            )

        # 3. Target retrieval counts (up to 2x num_stories, capped at max_fetch_pages)
        target_candidates = min(num_stories * config.fetch_buffer_multiplier, config.max_fetch_pages)

        # 4. Formulate explicit pre-action plan
        plan_steps = [
            f"1. Check 15-minute TTL cache for topic '{clean_topic}'.",
            f"2. Formulate 1-3 targeted search queries for time range '{time_range}'.",
            f"3. Run Tavily news search and gather up to {target_candidates} candidate stories.",
            f"4. Filter candidates against domain blocklist and date requirements.",
            f"5. Extract readable text using trafilatura with security delimiters (fallback to search snippet if needed).",
            f"6. Generate 2-3 sentence neutral summaries for each candidate article by ID.",
            f"7. Cluster near-duplicate stories and select best source for each.",
            f"8. Synthesize 2-3 sentence Quick Summary and assemble code-verified Markdown digest."
        ]

        # Initial default query
        initial_queries = [clean_topic]

        return ExecutionPlan(
            topic=clean_topic,
            num_stories=num_stories,
            time_range=time_range,
            steps=plan_steps,
            search_queries=initial_queries,
            aborted=False
        )

    def ask_permission(self, action_description: str) -> bool:
        """Explicit safety hook to ask user permission before taking high-impact or ambiguous actions."""
        return self.human_confirm_callback(action_description)

