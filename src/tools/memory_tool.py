"""
Tool 4: manage_memory
Handles reading and writing to working scratchpad memory and persistent cross-task store.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from src.config import config
from src.logger import logger


class PersistentMemoryStore:
    def __init__(self, filepath: Path = config.memory_path):
        self.filepath = filepath
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {"history": [], "cache": {}}
        self._load()

    def _load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("Memory file must contain a JSON object")
                self._data = loaded
            except Exception as e:
                logger.log_error(0, "manage_memory", f"Failed to load memory file: {e}")
                self._data = {"history": [], "cache": {}}

    def _save(self) -> None:
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.log_error(0, "manage_memory", f"Failed to save memory file: {e}")

    def get_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        self._load()
        entry = self._data.get("cache", {}).get(cache_key)
        if not entry:
            return None

        # Check TTL (15 minutes default)
        cached_time_str = entry.get("timestamp")
        if not cached_time_str:
            return None

        try:
            cached_dt = datetime.fromisoformat(cached_time_str)
            now = datetime.now(timezone.utc)
            diff_minutes = (now - cached_dt).total_seconds() / 60.0
            if diff_minutes <= config.cache_ttl_minutes:
                return entry.get("data")
            else:
                # Expired
                del self._data["cache"][cache_key]
                self._save()
                return None
        except Exception:
            return None

    def set_cache(self, cache_key: str, data: Any) -> None:
        self._load()
        if "cache" not in self._data:
            self._data["cache"] = {}
        self._data["cache"][cache_key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        self._save()

    def append_history(self, task_record: Dict[str, Any]) -> None:
        self._load()
        if "history" not in self._data:
            self._data["history"] = []
        task_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._data["history"].append(task_record)
        self._save()

    def get_history(self) -> list:
        self._load()
        return self._data.get("history", [])

    def clear_history(self) -> None:
        self._load()
        self._data = {"history": [], "cache": {}}
        self._save()

    def delete_topic_history(self, topic: str) -> None:
        self._load()
        clean_topic = topic.strip().lower()
        if "history" in self._data:
            self._data["history"] = [
                h for h in self._data["history"]
                if h.get("topic", "").strip().lower() != clean_topic
            ]
        if "cache" in self._data:
            keys_to_del = [k for k in self._data["cache"] if k.startswith(f"{clean_topic}::")]
            for k in keys_to_del:
                del self._data["cache"][k]
        self._save()


# Shared global memory instance and scratchpad
_store = PersistentMemoryStore()
_scratchpad: Dict[str, Any] = {}


def manage_memory(action: str, key: str, value: Any = None) -> Any:
    """
    Interface tool for accessing working memory scratchpad and persistent cross-task memory.

    Actions:
        - 'get_cache': Returns cached result for key if within 15-minute TTL, else None.
        - 'set_cache': Saves result for key in TTL cache.
        - 'append_history': Appends task run record to persistent history.
        - 'get_history': Returns all previous task runs.
        - 'get_scratchpad': Reads value from working scratchpad for the current agent session.
        - 'set_scratchpad': Writes value to working scratchpad for current agent session.
    """
    action = action.lower().strip()

    if action == "get_cache":
        return _store.get_cache(key)

    elif action == "set_cache":
        _store.set_cache(key, value)
        return True

    elif action == "append_history":
        _store.append_history(value if isinstance(value, dict) else {"record": value})
        return True

    elif action == "get_history":
        return _store.get_history()

    elif action == "clear_history":
        _store.clear_history()
        return True

    elif action == "delete_topic_history":
        _store.delete_topic_history(key)
        return True

    elif action == "get_scratchpad":
        return _scratchpad.get(key)

    elif action == "set_scratchpad":
        _scratchpad[key] = value
        return True

    elif action == "clear_scratchpad":
        _scratchpad.clear()
        return True

    else:
        raise ValueError(f"Unknown memory action: {action}")

