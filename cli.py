"""
Command-Line Interface for News Summarizer Agent.
Pure plain Python implementation supporting argument parsing and interactive prompting.
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent import PlainPythonNewsAgent
from src.llm.mock_llm import MockLLMClient
from src.llm.real_llm import RealLLMClient
from src.config import config


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="News Summarizer Agent - Concise, neutral news digests with verified sources."
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default=None,
        help="The news topic to summarize (e.g. 'electric vehicles in India')."
    )
    parser.add_argument(
        "-n", "--num-stories",
        type=int,
        default=5,
        choices=range(3, 11),
        metavar="[3-10]",
        help="Number of stories to include in the digest (default: 5, range: 3-10)."
    )
    parser.add_argument(
        "-t", "--time-range",
        type=str,
        default="7d",
        choices=["24h", "7d", "30d"],
        help="Time window for news search (default: 7d, choices: 24h, 7d, 30d)."
    )
    parser.add_argument(
        "--dry-run", "--mock",
        dest="dry_run",
        action="store_true",
        help="Run in offline mock mode using Fake LLM (zero API token or network cost)."
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    topic = args.topic
    if not topic:
        print("\n=============================================")
        print("         NEWS SUMMARIZER AGENT (CLI)        ")
        print("=============================================\n")
        try:
            topic = input("Enter a news topic: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

        if not topic:
            print("Error: Topic cannot be empty.")
            sys.exit(1)

    # Select LLM client
    if args.dry_run or not config.tavily_api_key:
        if not args.dry_run and not config.tavily_api_key:
            print("[INFO] No TAVILY_API_KEY detected in .env; switching to offline mock mode.\n")
        llm = MockLLMClient()
        agent = PlainPythonNewsAgent(llm=llm)

        def mock_search_tool(query: str, time_range: str = "7d", **kwargs):
            slug = query.replace(" ", "-").lower()[:30]
            return [
                {
                    "title": f"Recent Breakthroughs in {query}",
                    "url": f"https://verified-news.com/{slug}-story-1",
                    "snippet": f"Leading institutions announce major progress and field trials in {query}.",
                    "source": "verified-news.com",
                    "published_date": "2026-11-09"
                },
                {
                    "title": f"Industry Strategic Report: {query}",
                    "url": f"https://tech-monitor.org/{slug}-outlook-2",
                    "snippet": f"Global market report details rapid scaling, investments, and policies in {query}.",
                    "source": "tech-monitor.org",
                    "published_date": "2026-11-10"
                },
                {
                    "title": f"Commercial Deployment for {query}",
                    "url": f"https://energydaily.com/{slug}-commercial-3",
                    "snippet": f"First commercial scale units begin live operations this quarter.",
                    "source": "energydaily.com",
                    "published_date": "2026-11-10"
                }
            ]

        def mock_extract_tool(url: str, story_id: str = "1", fallback_snippet: str = "", **kwargs):
            return {
                "story_id": story_id,
                "url": url,
                "text": f"<article_data id='{story_id}' url='{url}'>\nDetailed coverage on recent developments: {fallback_snippet}\n</article_data>",
                "published_date": "2026-11-10",
                "is_fallback": False,
                "status": "extracted"
            }

        agent.tools["search_news"] = mock_search_tool
        agent.tools["extract_article"] = mock_extract_tool
    else:
        llm = RealLLMClient()
        agent = PlainPythonNewsAgent(llm=llm)

    print(f"\n[INFO] Starting Agent for topic: '{topic}'")
    print(f"[INFO] Stories: {args.num_stories} | Time Range: {args.time_range} | Mode: {'Mock' if isinstance(llm, MockLLMClient) else 'Live'}\n")

    digest = agent.run(
        topic=topic,
        num_stories=args.num_stories,
        time_range=args.time_range
    )

    print("\n" + "=" * 60)
    print("                     FINAL DIGEST                    ")
    print("=" * 60 + "\n")
    print(digest)
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()

