"""
Unit tests for Phase 7 (Post-MVP Advanced Enhancements):
1. Themed section categorization (src/theming.py)
2. Favorite topics management (src/exporter.py)
3. HTML & JSON export functionality (src/exporter.py)
"""

import unittest
from pathlib import Path
import json
from src.theming import categorize_story, group_stories_by_theme, format_themed_digest
from src.exporter import add_favorite, remove_favorite, get_favorites, export_to_json, export_to_html
from src.config import PROJECT_ROOT


class TestPostMVP(unittest.TestCase):

    def test_01_thematic_categorization(self):
        """Verify automatic thematic section categorization."""
        tech_story = {
            "title": "Quantum Computing Breakthrough in Silicon Chips",
            "summary": "Researchers achieve 99.9% gate fidelity using optical qubits."
        }
        policy_story = {
            "title": "Parliament Approves New Clean Energy Subsidy Bill",
            "summary": "Government mandates 30% solar adoption for new industrial buildings."
        }
        business_story = {
            "title": "Automaker Reports Record Q3 Electric Vehicle Sales and Revenue",
            "summary": "Quarterly earnings beat Wall Street investor expectations."
        }

        self.assertEqual(categorize_story(tech_story), "Technology & Innovation")
        self.assertEqual(categorize_story(policy_story), "Policy & Regulation")
        self.assertEqual(categorize_story(business_story), "Business & Markets")

    def test_02_group_stories_by_theme(self):
        """Verify grouping of mixed stories into thematic clusters."""
        stories = [
            {"title": "New EV Battery Patent", "summary": "Breakthrough in solid state."},
            {"title": "EV Subsidy Law Enacted", "summary": "Government passes bill."},
            {"title": "EV Startup Raises $50M in Venture Investment", "summary": "Market expansion."}
        ]
        groups = group_stories_by_theme(stories)
        self.assertIn("Technology & Innovation", groups)
        self.assertIn("Policy & Regulation", groups)
        self.assertIn("Business & Markets", groups)

    def test_03_format_themed_digest(self):
        """Verify themed digest Markdown structure."""
        stories = [
            {
                "title": "Solid State Battery Patent",
                "summary": "Key patent approved.",
                "source": "TechDaily",
                "published_date": "Nov 10, 2026",
                "url": "https://example.com/battery"
            }
        ]
        output = format_themed_digest(
            topic="Battery Tech",
            date_range_str="Nov 03 to Nov 10, 2026 (UTC)",
            quick_summary="Advancements in energy storage.",
            stories=stories
        )
        self.assertIn("Themed Sections:", output)
        self.assertIn("Technology & Innovation", output)
        self.assertIn("Based on 1 sources", output)

    def test_04_favorites_manager(self):
        """Verify adding and removing favorite topics."""
        test_topic = "Commercial Space Mining 2026"
        # Add
        add_favorite(test_topic)
        self.assertIn(test_topic, get_favorites())
        # Remove
        remove_favorite(test_topic)
        self.assertNotIn(test_topic, get_favorites())

    def test_05_export_html_and_json(self):
        """Verify HTML and JSON export generation."""
        export_dir = PROJECT_ROOT / "memory" / "test_exports"
        json_path = export_dir / "digest.json"
        html_path = export_dir / "digest.html"

        sample_stories = [
            {
                "title": "Fusion Milestone",
                "summary": "Net energy gain sustained for 20 minutes.",
                "source": "ScienceReport",
                "published_date": "Nov 10, 2026",
                "url": "https://example.com/fusion"
            }
        ]

        # Export JSON
        export_to_json({"topic": "Fusion", "stories": sample_stories}, json_path)
        self.assertTrue(json_path.exists())
        loaded_json = json.loads(json_path.read_text("utf-8"))
        self.assertEqual(loaded_json["topic"], "Fusion")

        # Export HTML
        export_to_html("Fusion", "Nov 03 to Nov 10, 2026 (UTC)", "Breakthrough achieved.", sample_stories, html_path)
        self.assertTrue(html_path.exists())
        html_text = html_path.read_text("utf-8")
        self.assertIn("Topic: Fusion", html_text)
        self.assertIn("Fusion Milestone", html_text)

        # Cleanup test files
        if json_path.exists():
            json_path.unlink()
        if html_path.exists():
            html_path.unlink()
        if export_dir.exists():
            export_dir.rmdir()


if __name__ == "__main__":
    unittest.main()

