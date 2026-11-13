"""
Unit tests for Phase 8:
1. StoryQAEngine grounded Q&A (src/qa.py)
2. Cross-outlet comparison & tone orientation (src/cross_outlet.py)
"""

import unittest
from src.qa import StoryQAEngine
from src.cross_outlet import analyze_tone, compare_outlet_coverage, format_cross_outlet_report


class TestQAAndCrossOutlet(unittest.TestCase):

    def setUp(self):
        self.qa = StoryQAEngine()
        self.sample_articles = [
            {
                "story_id": "1",
                "title": "Consortium Launches $500M Solid-State Battery Initiative",
                "text": "Automotive giants committed $500M to build a new pilot battery plant in Ohio. Mass manufacturing is targeted for 2028.",
                "source": "AutoDaily",
                "url": "https://autodaily.com/battery-plant"
            },
            {
                "story_id": "2",
                "title": "Experts Warn of Delays and Supply Chain Bottlenecks in Battery Scale-Up",
                "text": "Critical mineral shortages pose significant risk and obstacle to meeting 2028 battery timelines. Industry analysts express skepticism.",
                "source": "MiningMonitor",
                "url": "https://miningmonitor.com/battery-bottlenecks"
            }
        ]

    def test_01_qa_engine_grounded_answer(self):
        """Verify Q&A engine extracts factual answers from article text."""
        res = self.qa.answer_question("Where is the pilot battery plant located?", self.sample_articles)
        self.assertIn("Ohio", res["answer"])
        self.assertEqual(res["confidence"], "grounded")

    def test_02_qa_engine_refusal_when_absent(self):
        """Verify Q&A engine refuses to hallucinate facts absent from the text."""
        res = self.qa.answer_question("Who is the CEO of the company in Ohio?", self.sample_articles)
        self.assertIn("do not contain", res["answer"])
        self.assertEqual(res["confidence"], "low")

    def test_03_tone_analysis(self):
        """Verify tone classification (Optimistic vs Critical vs Neutral)."""
        opt_text = "Consortium achieves historic breakthrough and record growth in solar milestone."
        crit_text = "Serious risk, obstacle, and threat of delay warning causes concern for investors."
        neutral_text = "The committee met on Tuesday at 10 AM to review quarterly documentation."

        self.assertIn("Optimistic", analyze_tone(opt_text))
        self.assertIn("Critical", analyze_tone(crit_text))
        self.assertIn("Neutral", analyze_tone(neutral_text))

    def test_04_cross_outlet_comparison(self):
        """Verify cross-outlet comparison matrix and Markdown table."""
        comparison = compare_outlet_coverage(self.sample_articles)
        self.assertEqual(len(comparison["outlets_compared"]), 2)
        self.assertIn("AutoDaily", comparison["outlets_compared"])
        self.assertIn("MiningMonitor", comparison["outlets_compared"])

        report = format_cross_outlet_report(comparison)
        self.assertIn("Cross-Outlet Coverage Comparison", report)
        self.assertIn("AutoDaily", report)
        self.assertIn("MiningMonitor", report)


if __name__ == "__main__":
    unittest.main()

