"""
Configuration module for the News Summarizer Agent.
Pure plain Python implementation with strict safety defaults.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Set

# Root directory of the project
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def load_env_file(filepath: Path) -> None:
    """Lightweight plain Python .env loader fallback if python-dotenv is not installed."""
    if not filepath.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(filepath)
    except ImportError:
        # Fallback manual parser
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k not in os.environ:
                    os.environ[k] = v

# Load .env file
load_env_file(PROJECT_ROOT / ".env")


def load_file_lines_as_set(filepath: Path) -> Set[str]:
    """Helper to load a file line by line into a lowercase set, ignoring comments."""
    items: Set[str] = set()
    if not filepath.exists():
        return items
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                items.add(cleaned.lower())
    return items


@dataclass
class Config:
    # API Keys
    tavily_api_key: str = field(default_factory=lambda: os.getenv("TAVILY_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "anthropic/claude-3-5-sonnet-20241022"))

    # Core Safety Constraints & Loop Limits
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_STEPS", "10")))
    request_timeout: float = field(default_factory=lambda: float(os.getenv("REQUEST_TIMEOUT_SECONDS", "5.0")))
    fetch_buffer_multiplier: int = field(default_factory=lambda: int(os.getenv("FETCH_BUFFER_MULTIPLIER", "2")))
    max_fetch_pages: int = field(default_factory=lambda: int(os.getenv("MAX_FETCH_PAGES", "20")))
    cache_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_MINUTES", "15")))
    default_timezone: str = field(default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "UTC"))

    # File Paths
    project_root: Path = PROJECT_ROOT
    blocklist_path: Path = PROJECT_ROOT / "blocklist.txt"
    stoplist_path: Path = PROJECT_ROOT / "stoplist.txt"
    memory_path: Path = PROJECT_ROOT / "memory" / "task_history.json"
    log_path: Path = PROJECT_ROOT / "logs" / "agent_audit.log"

    def __post_init__(self):
        # Ensure log and memory directories exist
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)

    def get_blocklist(self) -> Set[str]:
        """Returns the set of blocked domain names."""
        return load_file_lines_as_set(self.blocklist_path)

    def get_stoplist(self) -> Set[str]:
        """Returns the set of vague stoplist keywords."""
        return load_file_lines_as_set(self.stoplist_path)

    def is_topic_vague(self, topic: str) -> bool:
        """Checks if a given topic matches the vague topic stoplist."""
        cleaned = topic.strip().lower()
        stoplist = self.get_stoplist()
        return cleaned in stoplist

    def is_domain_blocked(self, url_or_domain: str) -> bool:
        """Checks if a domain is on the blocklist."""
        cleaned = url_or_domain.lower()
        for blocked in self.get_blocklist():
            if blocked in cleaned:
                return True
        return False


# Global default configuration instance
config = Config()

