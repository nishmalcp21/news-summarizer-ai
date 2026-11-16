"""Tests for clearing the Streamlit chat and persistent history."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from src.llm.mock_llm import MockLLMClient
from src.tools.memory_tool import _store


class TestAppHistoryClear(unittest.TestCase):

    def test_clear_empties_session_and_history_file(self):
        previous_digest = MockLLMClient().synthesize_quick_summary("Previous topic", [])
        state = {
            "current_digest": previous_digest,
            "current_stories": [{"title": "A story"}],
            "current_topic": "Previous topic",
            "search_input": "Pending topic",
            "trigger_search": True,
            "chat_messages": [{"role": "assistant", "content": previous_digest}],
            "recent_chats": ["Previous topic"],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "task_history.json"
            history_path.write_text(
                json.dumps({
                    "history": [{"topic": "Previous topic"}],
                    "cache": {"previous topic::5::7d": {"data": "Previous digest"}},
                }),
                encoding="utf-8",
            )
            with patch.object(_store, "filepath", history_path):
                with patch.object(app.st, "session_state", state):
                    with patch.object(app.st, "rerun") as rerun:
                        app._clear_all_history()

            self.assertIsNone(state["current_digest"])
            self.assertEqual(state["current_stories"], [])
            self.assertEqual(state["current_topic"], "")
            self.assertEqual(state["search_input"], "")
            self.assertFalse(state["trigger_search"])
            self.assertEqual(state["chat_messages"], [])
            self.assertEqual(state["recent_chats"], [])
            self.assertEqual(json.loads(history_path.read_text(encoding="utf-8")), {
                "history": [],
                "cache": {},
            })
            rerun.assert_called_once_with()

    def test_clear_creates_or_repairs_history_file(self):
        state = {}
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "task_history.json"
            with patch.object(_store, "filepath", history_path):
                with patch.object(app.st, "session_state", state):
                    with patch.object(app.st, "rerun"):
                        app._clear_all_history()
                self.assertEqual(json.loads(history_path.read_text(encoding="utf-8")), {
                    "history": [],
                    "cache": {},
                })

                history_path.write_text("{corrupt json", encoding="utf-8")
                with patch.object(app.st, "session_state", state):
                    with patch.object(app.st, "rerun"):
                        app._clear_all_history()
                self.assertEqual(json.loads(history_path.read_text(encoding="utf-8")), {
                    "history": [],
                    "cache": {},
                })


if __name__ == "__main__":
    unittest.main()
