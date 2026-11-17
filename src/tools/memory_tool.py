"""
Tool 4: manage_memory
Handles reading and writing to working scratchpad memory and persistent cross-task store.
"""

import json
import os
import re
import tempfile
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from src.config import config
from src.logger import logger


USER_DATA_ROOT = config.project_root / "memory" / "users"
_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
_USER_FILES = {"memory.json", "favorites.json", "ratings.json"}
_current_user_id: ContextVar[Optional[str]] = ContextVar(
    "news_summarizer_user_id",
    default=None
)


def is_valid_user_id(user_id: Any) -> bool:
    return isinstance(user_id, str) and _USER_ID_PATTERN.fullmatch(user_id) is not None


def validate_user_id(user_id: str) -> str:
    if not is_valid_user_id(user_id):
        raise ValueError("Invalid user ID.")
    return user_id


def set_current_user_id(user_id: Optional[str]) -> None:
    _current_user_id.set(validate_user_id(user_id) if user_id is not None else None)


def get_current_user_id() -> Optional[str]:
    return _current_user_id.get()


def user_data_dir(user_id: str) -> Path:
    directory = USER_DATA_ROOT / validate_user_id(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def user_data_file_path(user_id: str, filename: str) -> Path:
    if filename not in _USER_FILES:
        raise ValueError("Unsupported user data file.")
    return user_data_dir(user_id) / filename


def _memory_file_path(user_id: Optional[str] = None) -> Path:
    return (
        user_data_file_path(user_id, "memory.json")
        if user_id is not None else config.memory_path
    )


def write_json_atomic(filepath: Path, data: Any) -> None:
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{filepath.name}.",
        suffix=".tmp",
        dir=str(filepath.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as output_file:
            json.dump(data, output_file, indent=2, ensure_ascii=False)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary_path, filepath)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


class PersistentMemoryStore:
    def __init__(
        self,
        filepath: Path = config.memory_path,
        user_id: Optional[str] = None
    ):
        self.filepath = filepath
        self.user_id = validate_user_id(user_id) if user_id is not None else None
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {"history": [], "cache": {}}
        self._load()

    def _active_filepath(self, user_id: Optional[str] = None) -> Path:
        active_user_id = user_id if user_id is not None else self.user_id
        if active_user_id is None:
            active_user_id = get_current_user_id()
        return (
            _memory_file_path(active_user_id)
            if active_user_id is not None else self.filepath
        )

    def _load(self, user_id: Optional[str] = None) -> None:
        filepath = self._active_filepath(user_id)
        self._data = {"history": [], "cache": {}}
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as input_file:
                    loaded = json.load(input_file)
                if not isinstance(loaded, dict):
                    raise ValueError("Memory file must contain a JSON object")
                history = loaded.get("history", [])
                cache = loaded.get("cache", {})
                self._data = {
                    "history": (
                        [record for record in history if isinstance(record, dict)]
                        if isinstance(history, list) else []
                    ),
                    "cache": (
                        {
                            key: entry for key, entry in cache.items()
                            if isinstance(key, str) and isinstance(entry, dict)
                        }
                        if isinstance(cache, dict) else {}
                    )
                }
            except Exception as e:
                logger.log_error(0, "manage_memory", f"Failed to load memory file: {e}")
                self._data = {"history": [], "cache": {}}

    def _save(self, user_id: Optional[str] = None) -> None:
        try:
            write_json_atomic(self._active_filepath(user_id), self._data)
        except Exception as e:
            logger.log_error(0, "manage_memory", f"Failed to save memory file: {e}")

    def get_cache(
        self,
        cache_key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        self._load(user_id)
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
                self._save(user_id)
                return None
        except Exception:
            return None

    def set_cache(
        self,
        cache_key: str,
        data: Any,
        user_id: Optional[str] = None
    ) -> None:
        self._load(user_id)
        if "cache" not in self._data:
            self._data["cache"] = {}
        self._data["cache"][cache_key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        self._save(user_id)

    def append_history(
        self,
        task_record: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        self._load(user_id)
        if "history" not in self._data:
            self._data["history"] = []
        record = dict(task_record)
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._data["history"].append(record)
        self._save(user_id)

    def get_history(self, user_id: Optional[str] = None) -> list:
        self._load(user_id)
        return self._data.get("history", [])

    def clear_history(self, user_id: Optional[str] = None) -> None:
        self._load(user_id)
        self._data = {"history": [], "cache": {}}
        self._save(user_id)

    def delete_topic_history(
        self,
        topic: str,
        user_id: Optional[str] = None
    ) -> None:
        self._load(user_id)
        clean_topic = topic.strip().lower()
        if "history" in self._data:
            self._data["history"] = [
                h for h in self._data["history"]
                if str(h.get("topic", "")).strip().lower() != clean_topic
            ]
        if "cache" in self._data:
            keys_to_del = [k for k in self._data["cache"] if k.startswith(f"{clean_topic}::")]
            for k in keys_to_del:
                del self._data["cache"][k]
        self._save(user_id)


# Shared global memory instance and scratchpad
_store = PersistentMemoryStore()
_scratchpad: Dict[str, Any] = {}


def manage_memory(
    action: str,
    key: str,
    value: Any = None,
    user_id: Optional[str] = None
) -> Any:
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
    active_user_id = user_id if user_id is not None else get_current_user_id()
    if active_user_id is not None:
        active_user_id = validate_user_id(active_user_id)

    if action == "get_scratchpad":
        return _scratchpad.get(key)
    if action == "set_scratchpad":
        _scratchpad[key] = value
        return True
    if action == "clear_scratchpad":
        _scratchpad.clear()
        return True

    if active_user_id is not None:
        store = PersistentMemoryStore(user_id=active_user_id)
    else:
        store = _store

    if action == "get_cache":
        return store.get_cache(key, active_user_id)

    elif action == "set_cache":
        store.set_cache(key, value, active_user_id)
        return True

    elif action == "append_history":
        store.append_history(
            value if isinstance(value, dict) else {"record": value},
            active_user_id
        )
        return True

    elif action == "get_history":
        return store.get_history(active_user_id)

    elif action == "clear_history":
        store.clear_history(active_user_id)
        return True

    elif action == "delete_topic_history":
        store.delete_topic_history(key, active_user_id)
        return True

    else:
        raise ValueError(f"Unknown memory action: {action}")

