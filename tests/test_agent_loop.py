"""
Tier 1 Tests for the Plain Python ReAct Agent Loop.
Tests:
1. End-to-end Think > Act > Look loop execution with MockLLMClient.
2. MAX_STEPS = 10 safety constraint enforcement.
3. 15-minute TTL caching across repeated runs.
4. 'Ask You First' human-in-the-loop safety prompt.
"""

import unittest
from unittest.mock import patch, MagicMock
from src.agent import PlainPythonNewsAgent
from src.llm.mock_llm import MockLLMClient
from src.config import Config


class TestAgentLoop(unittest.TestCase):

    def setUp(self):
        from src.tools.memory_tool import _store, _scratchpad
        _store._data = {"history": [], "cache": {}}
        _store._save()
        _scratchpad.clear()
        self.mock_llm = MockLLMClient()
        self.agent = PlainPythonNewsAgent(llm=self.mock_llm)

    def test_01_full_react_loop_execution(self):
        """Verify the full Think > Act > Look loop completes and builds a valid Markdown digest."""
        mock_search = MagicMock()
        mock_search.return_value = [
            {
                "title": "Major EV Policy Update",
                "url": "https://example.com/ev-policy",
                "snippet": "Government expands EV charging subsidy.",
                "source": "AutoDaily",
                "published_date": "2026-11-09"
            },
            {
                "title": "Battery Gigafactory Underway",
                "url": "https://example.com/battery-plant",
                "snippet": "New lithium-iron battery plant begins construction.",
                "source": "TechEnergy",
                "published_date": "2026-11-10"
            }
        ]

        mock_extract = MagicMock()
        mock_extract.return_value = {
            "story_id": "1",
            "url": "https://example.com/ev-policy",
            "text": "<article_data id='1'>Subsidies approved for 5000 new stations.</article_data>",
            "published_date": "2026-11-09",
            "is_fallback": False,
            "status": "extracted"
        }

        self.agent.tools["search_news"] = mock_search
        self.agent.tools["extract_article"] = mock_extract

        # Run agent
        topic = "Electric vehicles in India"
        digest = self.agent.run(topic=topic, num_stories=2, time_range="7d")

        # Assertions
        self.assertIn("Topic: Electric vehicles in India |", digest)
        self.assertIn("Quick summary:", digest)
        self.assertIn("Key stories:", digest)
        self.assertIn("Major EV Policy Update", digest)
        self.assertIn("Based on", digest)

    def test_02_max_steps_safety_boundary(self):
        """Verify MAX_STEPS prevents infinite loops when an action fails to advance."""
        test_cfg = Config(max_steps=5)
        failing_mock_llm = MockLLMClient(fail_step_limit=True)
        agent = PlainPythonNewsAgent(llm=failing_mock_llm, cfg=test_cfg)

        digest = agent.run(topic="Robotics in Medicine", num_stories=3, time_range="7d")
        # Ensure it synthesized an output cleanly after hitting max_steps without raising an error
        self.assertIsNotNone(digest)
        self.assertTrue(len(digest) > 0)

    def test_03_ttl_cache_between_runs(self):
        """Verify second identical request returns from 15-minute TTL cache without tool calls."""
        mock_search = MagicMock()
        mock_search.return_value = [
            {
                "title": "AI Chip Breakthrough",
                "url": "https://example.com/chip",
                "snippet": "New photonic neural processor demonstrated.",
                "source": "SemiconductorWeekly",
                "published_date": "2026-11-10"
            }
        ]
        self.agent.tools["search_news"] = mock_search

        topic = "Photonic AI Chips"
        # Run 1
        digest_1 = self.agent.run(topic=topic, num_stories=1, time_range="7d")
        initial_search_calls = mock_search.call_count

        # Run 2 (Identical topic and parameters)
        digest_2 = self.agent.run(topic=topic, num_stories=1, time_range="7d")

        # Should match and not call search tool again
        self.assertEqual(digest_1, digest_2)
        self.assertEqual(mock_search.call_count, initial_search_calls)

    def test_04_ask_you_first_confirmation(self):
        """Verify human confirmation is required for secondary searches."""
        confirmed = False
        def mock_callback(prompt: str) -> bool:
            nonlocal confirmed
            confirmed = True
            return True

        agent = PlainPythonNewsAgent(llm=self.mock_llm, human_confirm_callback=mock_callback)

        # Trigger internal confirmation check
        requires = agent._requires_human_confirmation("search_news", {"is_secondary_search": True})
        self.assertTrue(requires)

        # Trigger permission ask
        allowed = agent.planner.ask_permission("Run secondary search?")
        self.assertTrue(allowed)
        self.assertTrue(confirmed)


if __name__ == "__main__":
    unittest.main()
