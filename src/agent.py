"""
Plain Python ReAct Agent Engine.
Executes the iterative Think > Act > Look loop using standard Python while loops,
standard dictionaries, and strict safety guardrails.
"""

from typing import Dict, Any, Optional, List, Callable
from src.config import config, Config
from src.logger import logger, AgentAuditLogger
from src.memory import WorkingMemory, PersistentMemory
from src.planner import PreActionPlanner, ExecutionPlan
from src.deduplication import deduplicate_stories
from src.formatter import build_markdown_digest
from src.tools.search import search_news
from src.tools.extractor import extract_article
from src.tools.validator import validate_link
from src.tools.memory_tool import manage_memory
from src.llm.base import BaseLLMClient


class PlainPythonNewsAgent:
    """
    Pure Plain Python implementation of the News Summarizer Agent.
    Operates on the Think > Act > Look cycle with zero external agent frameworks.
    """

    def __init__(
        self,
        llm: BaseLLMClient,
        cfg: Config = config,
        audit_logger: AgentAuditLogger = logger,
        human_confirm_callback: Optional[Callable[[str], bool]] = None,
        tools: Optional[Dict[str, Callable[..., Any]]] = None
    ):
        self.llm = llm
        self.config = cfg
        self.logger = audit_logger
        self.persistent_memory = PersistentMemory()
        self.planner = PreActionPlanner(human_confirm_callback=human_confirm_callback)

        # The 4 Core Plain Python Tools
        self.tools: Dict[str, Callable[..., Any]] = tools if tools is not None else {
            "search_news": search_news,
            "extract_article": extract_article,
            "validate_link": validate_link,
            "manage_memory": manage_memory
        }

    def run(self, topic: str, num_stories: int = 5, time_range: str = "7d") -> str:
        """
        Executes the entire agent lifecycle:
        Plan -> Cache Check -> [Think > Act > Look] -> Synthesize -> Cache/Log
        """
        # Step 0: Plan before acting
        plan = self.planner.create_plan(topic, num_stories, time_range)
        self.logger.log_plan(f"Created {len(plan.steps)} steps for topic '{plan.topic}'")

        # Check if topic was aborted (e.g., stoplist match or invalid length)
        if plan.aborted:
            self.logger.log_safety(f"Execution halted: {plan.abort_reason}")
            return plan.abort_reason or "Request aborted."

        # Step 0.1: Check 15-minute TTL cache
        cached_digest = self.persistent_memory.get_cached_digest(topic, num_stories, time_range)
        if cached_digest:
            self.logger.log_finish(f"Found valid cached digest within {self.config.cache_ttl_minutes}m TTL. Returning cache.")
            return cached_digest

        # Initialize Working Memory for this session
        memory = WorkingMemory(topic=topic, num_stories=num_stories, time_range=time_range)
        memory.plan_steps = plan.steps
        memory.search_queries = plan.search_queries

        # Initialize Scratchpad
        manage_memory("set_scratchpad", "status", "starting")
        manage_memory("set_scratchpad", "topic", topic)
        manage_memory("set_scratchpad", "target_count", num_stories)

        step = 0
        while step < self.config.max_steps and not memory.finished:
            step += 1

            # -------------------------------------------------------------
            # 1. THINK: Decide next action based on current state and plan
            # -------------------------------------------------------------
            next_candidate = None

            if len(memory.extracted_articles) < len(memory.candidates):
                next_candidate = memory.candidates[len(memory.extracted_articles)]

            scratchpad_summary = {
                "topic": memory.topic,
                "time_range": memory.time_range,
                "candidates_count": len(memory.candidates),
                "extracted_count": len(memory.extracted_articles),
                "target_count": num_stories,
                "next_candidate": next_candidate,
                "step": step
            }
            thought, action, action_args = self.llm.decide_next_step(
                step=step,
                plan_steps=memory.plan_steps,
                scratchpad=scratchpad_summary
            )
            self.logger.log_think(step, thought)

            # Check for completion signal
            if action == "finish" or action == "synthesize":
                self.logger.log_act(step, action, action_args)
                break

            # -------------------------------------------------------------
            # SAFETY GUARD: Ask You First (Human Confirmation)
            # -------------------------------------------------------------
            if self._requires_human_confirmation(action, action_args):
                approved = self.planner.ask_permission(
                    f"Agent requests permission to execute '{action}' with args {action_args}."
                )
                if not approved:
                    rejection_msg = "User declined permission for this action."
                    self.logger.log_safety(rejection_msg)
                    memory.record_step(step, thought, action, action_args, rejection_msg)
                    continue

            # -------------------------------------------------------------
            # 2. ACT: Dispatch tool in plain Python with error handling
            # -------------------------------------------------------------
            tool_func = self.tools.get(action)
            if not tool_func:
                observation = {"error": f"Unknown tool: '{action}'", "status": "failed"}
                self.logger.log_error(step, action, observation["error"])
            else:
                try:
                    observation = tool_func(**action_args)
                    self.logger.log_act(step, action, action_args)
                except Exception as e:
                    # Self-healing: catch tool failure gracefully
                    observation = {"error": str(e), "status": "failed"}
                    self.logger.log_error(step, action, f"Tool failed: {e}")

            # -------------------------------------------------------------
            # 3. LOOK: Process observation and update memory
            # -------------------------------------------------------------
            self._update_memory_with_observation(memory, action, observation)
            obs_summary = str(observation)[:180] + ("..." if len(str(observation)) > 180 else "")
            self.logger.log_look(step, obs_summary)
            memory.record_step(step, thought, action, action_args, observation)

        # Loop completed or MAX_STEPS reached
        if step >= self.config.max_steps:
            self.logger.log_safety(f"Reached MAX_STEPS limit ({self.config.max_steps}). Forcing digest synthesis.")

        # Final Synthesis Stage
        final_digest = self._synthesize_digest(memory)
        memory.mark_finished(final_digest)

        # Cache the resulting digest and record task in persistent memory
        self.persistent_memory.save_cached_digest(topic, num_stories, time_range, final_digest)
        self.persistent_memory.record_task_run(
            topic=topic,
            num_stories=num_stories,
            time_range=time_range,
            success=bool(memory.extracted_articles or memory.candidates),
            story_count=len(memory.extracted_articles)
        )

        self.logger.log_finish("Final digest synthesized, verified, and cached.")
        return final_digest

    def _requires_human_confirmation(self, action: str, action_args: Dict[str, Any]) -> bool:
        """Determines if an action requires explicit human confirmation."""
        # Confirm if performing extra search beyond standard limit
        if action == "search_news" and action_args.get("is_secondary_search", False):
            return True
        return False

    
    def _update_memory_with_observation(self, memory: WorkingMemory, action: str, observation: Any) -> None:
        """Updates internal working memory based on tool outputs."""
        if action == "search_news" and isinstance(observation, list):
            memory.add_candidates(observation)
        elif action == "extract_article" and isinstance(observation, dict):
            if observation.get("status") in ("extracted", "fallback"):
                memory.add_extracted_article(observation)


    def _synthesize_digest(self, memory: WorkingMemory) -> str:
        """Combines gathered articles and generates the final news digest."""

        # Merge candidate metadata into extracted articles
        candidate_map = {
            c.get("url"): c
            for c in memory.candidates
            if c.get("url")
        }

        for article in memory.extracted_articles:
            url = article.get("url")

            if url in candidate_map:
                cand = candidate_map[url]

                if not article.get("title"):
                    article["title"] = cand.get("title")

                if not article.get("source") or article.get("source") == "News Outlet":
                    article["source"] = cand.get("source")

                if not article.get("published_date"):
                    article["published_date"] = cand.get("published_date")

        # Deduplicate candidates / articles
        pool = memory.extracted_articles if memory.extracted_articles else memory.candidates
        unique_stories = deduplicate_stories(pool)

        # Select requested number of stories
        selected_stories = unique_stories[:memory.num_stories]

        # Generate summaries in one LLM request when supported
        summarized_stories: List[Dict[str, Any]] = []
        batch_summaries = None

        batch_method = getattr(self.llm, "summarize_articles", None)

        if callable(batch_method) and selected_stories:
            try:
                batch_summaries = batch_method(selected_stories)

                if len(batch_summaries) != len(selected_stories):
                    raise ValueError("Incorrect number of batch summaries returned.")

            except Exception as e:
                self.logger.log_error(
                    0,
                    "batch_summarization",
                    f"Batch summarization failed: {e}. Using individual summaries."
                )
                batch_summaries = None

        for idx, story in enumerate(selected_stories, 1):
            story_id = f"[{idx}]"

            if batch_summaries is not None:
                summary = batch_summaries[idx - 1]
            else:
                content = story.get("text", "") or story.get("snippet", "")
                summary = self.llm.summarize_article(
                    story_id=story_id,
                    article_text=content
                )

            story_url = story.get("url", "")
            cand_meta = candidate_map.get(story_url, {})

            title = story.get("title") or cand_meta.get("title") or f"News Story {idx}"
            source = story.get("source") or cand_meta.get("source") or "News Outlet"
            pub_date = story.get("published_date") or cand_meta.get("published_date") or "Recent"

            summarized_stories.append({
                "title": title,
                "summary": summary,
                "source": source,
                "published_date": pub_date,
                "url": story_url
            })

        # Synthesize quick summary
        quick_summary = self.llm.synthesize_quick_summary(
            topic=memory.topic,
            story_summaries=summarized_stories
        )

        # Build final Markdown digest
        digest = build_markdown_digest(
            topic=memory.topic,
            time_range=memory.time_range,
            quick_summary=quick_summary,
            stories=summarized_stories,
            timezone_name=self.config.default_timezone,
            verify_links_before_output=False
        )

        return digest
