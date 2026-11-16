"""
Memory systems for the News Summarizer Agent in plain Python:
1. WorkingMemory: Short-term scratchpad tracking in-flight state, candidates, and step history.
2. PersistentMemory: Cross-task long-term store for 15-min TTL caching and query history.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from src.tools.memory_tool import manage_memory, _store


@dataclass
class WorkingMemory:
    """Working scratchpad memory for a single agent session."""
    topic: str
    num_stories: int = 5
    time_range: str = "7d"
    plan_steps: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    extracted_articles: List[Dict[str, Any]] = field(default_factory=list)
    step_history: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    finished: bool = False
    final_digest: Optional[str] = None
    abort_reason: Optional[str] = None

    def record_step(self, step: int, thought: str, action: str, action_args: Any, observation: Any) -> None:
        self.step_count = step
        self.step_history.append({
            "step": step,
            "thought": thought,
            "action": action,
            "args": action_args,
            "observation": observation
        })

    def add_candidates(self, new_candidates: List[Dict[str, Any]]) -> None:
        # Avoid duplicate URLs in candidate list
        existing_urls = {c["url"] for c in self.candidates}
        for c in new_candidates:
            if c["url"] not in existing_urls:
                self.candidates.append(c)
                existing_urls.add(c["url"])

    def add_extracted_article(self, article_data: Dict[str, Any]) -> None:
        self.extracted_articles.append(article_data)

    def mark_finished(self, digest: str) -> None:
        self.finished = True
        self.final_digest = digest

    def mark_aborted(self, reason: str) -> None:
        self.finished = True
        self.abort_reason = reason


class PersistentMemory:
    """Manages cross-task persistent cache and task execution logs."""

    @staticmethod
    def _make_cache_key(topic: str, num_stories: int, time_range: str) -> str:
        clean_topic = topic.strip().lower()
        return f"{clean_topic}::{num_stories}::{time_range.lower()}"

    def get_cached_digest(self, topic: str, num_stories: int, time_range: str) -> Optional[str]:
        cache_key = self._make_cache_key(topic, num_stories, time_range)
        cached = manage_memory("get_cache", cache_key)
        return cached if isinstance(cached, str) else None

    def save_cached_digest(self, topic: str, num_stories: int, time_range: str, digest: str) -> None:
        cache_key = self._make_cache_key(topic, num_stories, time_range)
        manage_memory("set_cache", cache_key, digest)

    def record_task_run(self, topic: str, num_stories: int, time_range: str, success: bool, story_count: int) -> None:
        record = {
            "topic": topic,
            "num_stories": num_stories,
            "time_range": time_range,
            "success": success,
            "story_count": story_count
        }
        manage_memory("append_history", "record", record)

    def get_history(self) -> List[Dict[str, Any]]:
        return manage_memory("get_history", "all")

    def clear_history(self) -> None:
        """Clear task history and cached digests from the persistent store."""
        manage_memory("clear_history", "all")

    def delete_topic_history(self, topic: str) -> None:
        manage_memory("delete_topic_history", topic)

