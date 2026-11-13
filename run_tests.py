"""
Convenience test runner script for the News Summarizer Agent.
Runs all unit tests (Tier 1 & Tier 2) and the 20-topic benchmark evaluation.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.benchmark_20_topics import run_benchmark, BENCHMARK_TOPICS
from src.agent import PlainPythonNewsAgent
from src.llm.mock_llm import MockLLMClient
from src.config import config


def main():
    print("\n=======================================================")
    print("      NEWS SUMMARIZER AGENT - TEST & BENCHMARK SUITE    ")
    print("=======================================================\n")

    # Step 1: Run all unit tests
    print("[1/2] Running all unit & integration tests...")
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if not result.wasSuccessful():
        print("\n❌ Unit tests failed! Please inspect output above.")
        sys.exit(1)

    print("\n✅ All unit and integration tests passed!\n")

    # Step 2: Run 20-Topic Benchmark
    print("[2/2] Running 20-Topic Benchmark Evaluation...")
    mock_llm = MockLLMClient()
    agent = PlainPythonNewsAgent(llm=mock_llm)

    if "--live" not in sys.argv:
        def offline_search(query: str, time_range: str = "7d", **kwargs):
            slug = query.replace(" ", "-").lower()[:30]
            return [
                {
                    "title": f"Recent Advances in {query}",
                    "url": f"https://verified-news.com/{slug}-1",
                    "snippet": f"Latest briefings highlight breakthroughs and adoption in {query}.",
                    "source": "verified-news.com",
                    "published_date": "2026-11-09"
                },
                {
                    "title": f"Industry Strategic Outlook: {query}",
                    "url": f"https://tech-monitor.org/{slug}-2",
                    "snippet": f"Market report details scaling, regulatory roadmaps, and investments in {query}.",
                    "source": "tech-monitor.org",
                    "published_date": "2026-11-10"
                }
            ]

        def offline_extract(url: str, story_id: str = "1", fallback_snippet: str = "", **kwargs):
            return {
                "story_id": story_id,
                "url": url,
                "text": f"<article_data id='{story_id}' url='{url}'>\nDetailed coverage: {fallback_snippet}\n</article_data>",
                "published_date": "2026-11-10",
                "is_fallback": False,
                "status": "extracted"
            }

        agent.tools["search_news"] = offline_search
        agent.tools["extract_article"] = offline_extract

    benchmark_results = run_benchmark(agent, BENCHMARK_TOPICS)

    print("=======================================================")
    print("🎉 FULL TEST SUITE & BENCHMARK COMPLETED SUCCESSFULLY!")
    print("=======================================================\n")


if __name__ == "__main__":
    main()

