"""
Unit tests for Phase 2:
1. WorkingMemory and PersistentMemory
2. PreActionPlanner plan creation and stoplist validation
3. Human-in-the-loop 'Ask you first' hook
"""

import unittest
from src.memory import WorkingMemory, PersistentMemory
from src.planner import PreActionPlanner


class TestMemoryAndPlanner(unittest.TestCase):

    def test_01_working_memory_state(self):
        """Test WorkingMemory candidate tracking and step records."""
        mem = WorkingMemory(topic="Quantum Computing", num_stories=5, time_range="7d")
        self.assertEqual(mem.step_count, 0)
        self.assertFalse(mem.finished)

        # Add candidates avoiding duplicates
        mem.add_candidates([
            {"url": "https://a.com/1", "title": "A1"},
            {"url": "https://b.com/2", "title": "B2"}
        ])
        mem.add_candidates([
            {"url": "https://a.com/1", "title": "Duplicate A1"}
        ])
        self.assertEqual(len(mem.candidates), 2)

        # Record step
        mem.record_step(1, "Need to search", "search_news", {"query": "Quantum"}, "Found 2 results")
        self.assertEqual(mem.step_count, 1)
        self.assertEqual(len(mem.step_history), 1)

    def test_02_persistent_memory_cache(self):
        """Test PersistentMemory 15-minute TTL cache and task logging."""
        pm = PersistentMemory()
        topic = "Fusion Energy"
        digest_text = "Fusion energy breakthrough achieved in test facility."

        pm.save_cached_digest(topic, 5, "7d", digest_text)
        cached = pm.get_cached_digest(topic, 5, "7d")
        self.assertEqual(cached, digest_text)

        # Check different parameters return None
        self.assertIsNone(pm.get_cached_digest(topic, 3, "24h"))

        # Task logging
        pm.record_task_run(topic, 5, "7d", success=True, story_count=5)
        history = pm.get_history()
        self.assertTrue(any(h.get("topic") == topic for h in history))

    def test_03_planner_valid_topic(self):
        """Test PreActionPlanner generates an explicit numbered plan for valid topic."""
        planner = PreActionPlanner()
        plan = planner.create_plan("electric vehicles in India", num_stories=5, time_range="7d")
        self.assertFalse(plan.aborted)
        self.assertGreaterEqual(len(plan.steps), 5)
        self.assertEqual(plan.topic, "electric vehicles in India")

    def test_04_planner_vague_topic_aborted(self):
        """Test PreActionPlanner aborts vague topic from stoplist."""
        planner = PreActionPlanner()
        for vague in ["news", "today", "latest", "updates"]:
            plan = planner.create_plan(vague)
            self.assertTrue(plan.aborted)
            self.assertIn("too vague", plan.abort_reason)

    def test_05_planner_human_confirm_callback(self):
        """Test human confirmation hook ('Ask you first')."""
        confirmed = False
        def mock_confirm(prompt: str) -> bool:
            nonlocal confirmed
            confirmed = True
            return True

        planner = PreActionPlanner(human_confirm_callback=mock_confirm)
        result = planner.ask_permission("Perform secondary search round?")
        self.assertTrue(result)
        self.assertTrue(confirmed)


if __name__ == "__main__":
    unittest.main()

