"""
Unit tests for formatter and deduplication:
1. calculate_date_range_str
2. build_markdown_digest
3. deduplicate_stories
"""

import unittest
from src.formatter import calculate_date_range_str, build_markdown_digest
from src.deduplication import deduplicate_stories, calculate_jaccard_similarity, normalize_title


class TestFormatterAndDeduplication(unittest.TestCase):

    def test_01_date_range_calculation(self):
        """Verify date range string formatting."""
        range_7d = calculate_date_range_str("7d", "UTC")
        self.assertIn("(UTC)", range_7d)
        self.assertIn("to", range_7d)

    def test_02_build_markdown_digest_format(self):
        """Verify digest strictly matches PRD Section 7.4."""
        topic = "Electric vehicles in India"
        quick_summary = "EV sales continued to rise this week. Charging infrastructure remains a key priority."
        stories = [
            {
                "title": "New Budget EV Launched",
                "summary": "Major automaker unveiled a budget EV for first-time buyers.",
                "source": "AutoNews",
                "published_date": "Nov 8, 2026",
                "url": "https://example.com/budget-ev"
            },
            {
                "title": "Fast Chargers Expand",
                "summary": "Network added 500 fast chargers across Tier-2 cities.",
                "source": "TechDaily",
                "published_date": "Nov 9, 2026",
                "url": "https://example.com/chargers"
            }
        ]

        digest = build_markdown_digest(
            topic=topic,
            time_range="7d",
            quick_summary=quick_summary,
            stories=stories,
            verify_links_before_output=False
        )

        self.assertIn("Topic: Electric vehicles in India |", digest)
        self.assertIn("Quick summary:\n" + quick_summary, digest)
        self.assertIn("Key stories:", digest)
        self.assertIn("1. New Budget EV Launched", digest)
        self.assertIn("Source: AutoNews | Nov 8, 2026 | https://example.com/budget-ev", digest)
        self.assertIn("Based on 2 sources.", digest)

    def test_03_deduplication(self):
        """Verify URL and title similarity deduplication."""
        stories = [
            {"url": "https://a.com/story1", "title": "Tesla expands factory in Texas", "text": "Short"},
            {"url": "https://a.com/story1", "title": "Duplicate URL", "text": "Short"},
            {"url": "https://b.com/story2", "title": "Tesla expands its Texas factory", "text": "Much longer article text"},
            {"url": "https://c.com/story3", "title": "Unrelated news about solar power", "text": "Solar power"}
        ]

        deduped = deduplicate_stories(stories, similarity_threshold=0.5)
        # Should cluster the two Texas factory stories and remove duplicate URL
        self.assertEqual(len(deduped), 2)
        urls = [s["url"] for s in deduped]
        self.assertIn("https://c.com/story3", urls)


if __name__ == "__main__":
    unittest.main()

