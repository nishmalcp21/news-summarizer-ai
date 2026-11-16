"""Offline tests for digest exports and the task-history table."""

import unittest

import app
import src.exporter as exporter
from src.llm.mock_llm import MockLLMClient


class TestDigestExports(unittest.TestCase):

    def setUp(self):
        self.topic = "Battery research"
        mock_llm = MockLLMClient()
        quick_summary = mock_llm.synthesize_quick_summary(self.topic, [])
        self.digest_text = (
            f"Topic: {self.topic}\n\n"
            f"Quick summary:\n{quick_summary}\n\n"
            "Key stories:\n"
            "1. New battery cells reach a milestone\n"
            "The team reported improved storage performance.\n"
            "Source: Example News | 2026-11-15 | https://example.com/battery\n\n"
            "Based on 1 sources."
        )
        self.stories = app._parse_digest_stories(self.digest_text)

    def test_history_table_is_unindented_and_escapes_topics(self):
        table_html = app._build_history_table_html([
            {
                "topic": "<Research & Development>",
                "num_stories": 2,
                "time_range": "7d",
                "success": True,
                "story_count": 2,
            }
        ])

        self.assertTrue(table_html.startswith("<div"))
        self.assertNotRegex(table_html, r"(?m)^\s+<")
        self.assertIn('class="claude-table"', table_html)
        self.assertIn("&lt;Research &amp; Development&gt;", table_html)

    def test_markdown_text_and_pdf_exports_are_generated(self):
        markdown = exporter.export_to_markdown(
            self.topic, self.digest_text, self.stories, "2026-11-16"
        )
        plain_text = exporter.export_to_text(
            self.topic, self.digest_text, self.stories, "2026-11-16"
        )
        pdf_bytes = exporter.export_to_pdf(
            self.topic, self.digest_text, self.stories, "2026-11-16"
        )

        self.assertTrue(markdown.strip())
        self.assertIn("New battery cells reach a milestone", markdown)
        self.assertIn("https://example.com/battery", markdown)
        self.assertTrue(plain_text.strip())
        self.assertIn("Example News", plain_text)
        self.assertIn("https://example.com/battery", plain_text)
        self.assertTrue(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_html_export_has_been_removed(self):
        self.assertFalse(hasattr(exporter, "export_to_html"))


if __name__ == "__main__":
    unittest.main()
