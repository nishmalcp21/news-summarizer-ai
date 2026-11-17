import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from src.exporter import add_favorite, get_favorites
from src.memory import PersistentMemory
from src.tools.memory_tool import (
    get_current_user_id,
    set_current_user_id,
    user_data_file_path,
)


class TestUserIsolation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user_data_root_patch = patch(
            "src.tools.memory_tool.USER_DATA_ROOT",
            Path(self.temp_dir.name)
        )
        self.user_data_root_patch.start()
        set_current_user_id(None)

    def tearDown(self):
        set_current_user_id(None)
        self.user_data_root_patch.stop()
        self.temp_dir.cleanup()

    def test_histories_favorites_and_ratings_are_per_user(self):
        first_user = "visitor_one"
        second_user = "visitor_two"
        first_memory = PersistentMemory(user_id=first_user)
        second_memory = PersistentMemory(user_id=second_user)

        first_memory.record_task_run("First topic", 3, "7d", True, 3)
        second_memory.record_task_run("Second topic", 3, "7d", True, 2)
        add_favorite("First bookmark", user_id=first_user)
        add_favorite("Second bookmark", user_id=second_user)
        app.save_user_rating("First topic", "positive", user_id=first_user)
        app.save_user_rating("Second topic", "negative", user_id=second_user)

        self.assertEqual(
            [record["topic"] for record in first_memory.get_history()],
            ["First topic"]
        )
        self.assertEqual(
            [record["topic"] for record in second_memory.get_history()],
            ["Second topic"]
        )
        self.assertEqual(get_favorites(user_id=first_user), ["First bookmark"])
        self.assertEqual(get_favorites(user_id=second_user), ["Second bookmark"])
        self.assertEqual(app.get_ratings(user_id=first_user)[0]["topic"], "First topic")
        self.assertEqual(app.get_ratings(user_id=second_user)[0]["topic"], "Second topic")

    def test_clearing_history_only_affects_current_user(self):
        first_memory = PersistentMemory(user_id="visitor_one")
        second_memory = PersistentMemory(user_id="visitor_two")
        first_memory.record_task_run("First topic", 3, "7d", True, 3)
        second_memory.record_task_run("Second topic", 3, "7d", True, 2)

        first_memory.clear_history()

        self.assertEqual(first_memory.get_history(), [])
        self.assertEqual(
            [record["topic"] for record in second_memory.get_history()],
            ["Second topic"]
        )

    def test_current_user_context_is_used_by_default(self):
        set_current_user_id("visitor_one")
        PersistentMemory().record_task_run("First topic", 3, "7d", True, 3)
        add_favorite("First bookmark")
        app.save_user_rating("First topic", "positive")

        set_current_user_id("visitor_two")
        self.assertEqual(PersistentMemory().get_history(), [])
        self.assertEqual(get_favorites(), [])
        self.assertEqual(app.get_ratings(), [])

    def test_invalid_query_id_is_replaced_and_valid_id_is_reused(self):
        query_params = {"uid": "../x"}
        session_state = {}
        with patch("app.secrets.token_urlsafe", return_value="fresh_user_01"):
            new_user_id = app._resolve_user_id(query_params, session_state)

        self.assertEqual(new_user_id, "fresh_user_01")
        self.assertEqual(query_params["uid"], new_user_id)
        self.assertEqual(session_state["user_id"], new_user_id)
        self.assertEqual(get_current_user_id(), new_user_id)

        with self.assertRaises(ValueError):
            user_data_file_path("../x", "memory.json")

        with patch("app.secrets.token_urlsafe", side_effect=AssertionError):
            reused_user_id = app._resolve_user_id(query_params, session_state)
        self.assertEqual(reused_user_id, new_user_id)

    def test_corrupt_user_files_are_treated_as_empty(self):
        user_id = "visitor_corrupt"
        for filename in ("memory.json", "favorites.json", "ratings.json"):
            user_data_file_path(user_id, filename).write_text(
                "{invalid json",
                encoding="utf-8"
            )

        with patch("src.tools.memory_tool.logger.log_error"):
            self.assertEqual(PersistentMemory(user_id=user_id).get_history(), [])
            self.assertEqual(get_favorites(user_id=user_id), [])
            self.assertEqual(app.get_ratings(user_id=user_id), [])


if __name__ == "__main__":
    unittest.main()
