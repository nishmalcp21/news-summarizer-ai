"""
Unit tests for the 4 core tools in plain Python:
1. search_news
2. extract_article
3. validate_link
4. manage_memory
"""

import unittest
from unittest.mock import patch, MagicMock
from src.tools.search import search_news, map_time_range
from src.tools.extractor import extract_article
from src.tools.validator import validate_link
from src.tools.memory_tool import manage_memory
from src.config import config


class TestTools(unittest.TestCase):

    def test_01_map_time_range(self):
        """Verify time range mapping for Tavily."""
        self.assertEqual(map_time_range("24h"), "d")
        self.assertEqual(map_time_range("7d"), "w")
        self.assertEqual(map_time_range("30d"), "m")
        self.assertEqual(map_time_range("unknown"), "w")

    @patch("src.tools.search.config.is_domain_blocked")
    def test_02_search_news_mocked(self, mock_is_blocked):
        """Verify search_news normalizes results and filters blocked domains."""
        import sys
        mock_is_blocked.side_effect = lambda url: "blocked.com" in url

        mock_tavily_response = {
            "results": [
                {
                    "title": "Clean Energy Advances in 2026",
                    "url": "https://trustednews.com/clean-energy",
                    "content": "Solar and wind capacity hit new record highs.",
                    "published_date": "2026-11-08"
                },
                {
                    "title": "Shocking Clickbait",
                    "url": "https://blocked.com/bad-article",
                    "content": "You will not believe this clickbait.",
                    "published_date": "2026-11-09"
                }
            ]
        }

        mock_tavily_module = MagicMock()
        mock_client = MagicMock()
        mock_client.search.return_value = mock_tavily_response
        mock_tavily_module.TavilyClient.return_value = mock_client

        with patch.dict(sys.modules, {"tavily": mock_tavily_module}):
            results = search_news(query="Clean Energy", time_range="7d", api_key="dummy_key")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "Clean Energy Advances in 2026")
            self.assertEqual(results[0]["source"], "trustednews.com")
            self.assertEqual(results[0]["published_date"], "2026-11-08")

    def test_03_extract_article_fallback(self):
        """Verify extract_article falls back safely to snippet on invalid/empty URLs."""
        res = extract_article(
            url="https://non-existent-site-xyz-123.com/story",
            story_id="1",
            fallback_snippet="Fallback text about EV market."
        )
        self.assertEqual(res["story_id"], "1")
        self.assertTrue(res["is_fallback"])
        self.assertIn("summary based on snippet only", res["text"])
        self.assertIn("<article_data id=\"1\"", res["text"])

    def test_04_validate_link_blocklist(self):
        """Verify validate_link blocks known blocklisted domains immediately."""
        self.assertFalse(validate_link("https://buzzfeed.com/test-article"))
        self.assertFalse(validate_link("ftp://invalid-scheme.com/file"))
        self.assertFalse(validate_link(""))

    def test_05_manage_memory(self):
        """Verify manage_memory scratchpad, TTL cache, and task history."""
        # 1. Scratchpad test
        manage_memory("set_scratchpad", "active_candidates", ["url1", "url2"])
        val = manage_memory("get_scratchpad", "active_candidates")
        self.assertEqual(val, ["url1", "url2"])

        # 2. Cache test
        test_cache_key = "test_topic_7d_5"
        test_digest = "Digest text here"
        manage_memory("set_cache", test_cache_key, test_digest)
        cached = manage_memory("get_cache", test_cache_key)
        self.assertEqual(cached, test_digest)

        # 3. History test
        manage_memory("append_history", "record", {"topic": "AI Agents", "stories": 5})
        history = manage_memory("get_history", "all")
        self.assertTrue(len(history) >= 1)


if __name__ == "__main__":
    unittest.main()
