"""
Code-enforced Markdown digest builder.
Ensures source URLs, titles, dates, and source names come directly from verified search metadata
and are never hallucinated by the LLM. Strictly follows PRD Section 7.4.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from src.tools.validator import validate_link
from src.logger import logger


def calculate_date_range_str(time_range: str, tz_name: str = "UTC") -> str:
    """
    Calculate the absolute human-readable date range string.
    E.g. 'Nov 3 to Nov 10, 2026 (UTC)'.
    """
    now = datetime.now(timezone.utc)
    days_back = 7
    cleaned = (time_range or "7d").strip().lower()
    if cleaned in ("24h", "1d"):
        days_back = 1
    elif cleaned in ("30d", "1m"):
        days_back = 30

    start_date = now - timedelta(days=days_back)
    start_str = start_date.strftime("%b %d")
    end_str = now.strftime("%b %d, %Y")
    return f"{start_str} to {end_str} ({tz_name})"


def build_markdown_digest(
    topic: str,
    time_range: str,
    quick_summary: str,
    stories: List[Dict[str, Any]],
    timezone_name: str = "UTC",
    verify_links_before_output: bool = True
) -> str:
    """
    Assembles the final digest in Markdown.
    PRD 7.4 Format:
    Topic: <topic> | <Date Range> (<Timezone>)

    Quick summary:
    <2-3 sentences>

    Key stories:
    1. <Title>
       <Summary>
       Source: <Source> | <Date> | <URL>

    Based on N sources.
    """
    date_range_str = calculate_date_range_str(time_range, timezone_name)

    # Filter verified stories
    valid_stories: List[Dict[str, Any]] = []
    for story in stories:
        url = story.get("url", "").strip()
        if not url:
            continue

        if verify_links_before_output:
            # Code-enforced link integrity check
            if not validate_link(url):
                logger.log_safety(f"Dropping story with invalid or unreachable link: {url}")
                continue

        valid_stories.append(story)

    num_sources = len(valid_stories)

    lines: List[str] = [
        f"Topic: {topic.strip()} | {date_range_str}",
        "",
        "Quick summary:",
        quick_summary.strip(),
        "",
        "Key stories:"
    ]

    if not valid_stories:
        lines.append("No verified recent news stories were found for this topic and time range.")
    else:
        for idx, story in enumerate(valid_stories, 1):
            title = story.get("title", "Untitled Story").strip()
            summary = story.get("summary", "").strip()
            source = story.get("source", "Unknown Source").strip()
            pub_date = story.get("published_date", "").strip() or "Recent"
            url = story.get("url", "").strip()

            # Format each story block
            lines.append(f"{idx}. {title}")
            lines.append(f"   {summary}")
            lines.append(f"   Source: {source} | {pub_date} | {url}")
            lines.append("")

    lines.append(f"Based on {num_sources} sources.")
    return "\n".join(lines)

