"""
Theming and Categorization Module (Post-MVP Enhancement - PRD Section 13).
Automatically clusters stories into intuitive thematic sections:
- Technology & Innovation
- Policy & Regulation
- Business & Markets
- General Updates
"""

from typing import List, Dict, Any


THEME_KEYWORDS = {
    "Technology & Innovation": [
        "tech", "technology", "battery", "breakthrough", "chip", "research",
        "quantum", "ai", "artificial intelligence", "software", "hardware", "solar",
        "robot", "prototype", "developer", "patent", "innovation", "discovery"
    ],
    "Policy & Regulation": [
        "policy", "government", "regulation", "law", "court", "ban", "subsidy",
        "parliament", "congress", "ministry", "official", "rules", "compliance",
        "mandate", "tax", "incentive", "treaty", "bill", "legal"
    ],
    "Business & Markets": [
        "market", "stock", "shares", "earnings", "investment", "investor", "revenue",
        "merger", "acquisition", "consortium", "sales", "quarterly", "profit",
        "automaker", "startup", "venture", "commercial", "enterprise", "cost"
    ]
}


def categorize_story(story: Dict[str, Any]) -> str:
    """Classifies a story into a thematic category based on headline and summary text."""
    combined_text = (
        story.get("title", "") + " " +
        story.get("summary", "") + " " +
        story.get("snippet", "")
    ).lower()

    scores = {theme: 0 for theme in THEME_KEYWORDS}
    for theme, keywords in THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in combined_text:
                scores[theme] += 1

    best_theme = max(scores, key=scores.get)
    if scores[best_theme] > 0:
        return best_theme
    return "General Updates"


def group_stories_by_theme(stories: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Groups a list of stories into a dictionary keyed by theme."""
    themed_groups: Dict[str, List[Dict[str, Any]]] = {}

    for story in stories:
        theme = categorize_story(story)
        if theme not in themed_groups:
            themed_groups[theme] = []
        themed_groups[theme].append(story)

    return themed_groups


def format_themed_digest(
    topic: str,
    date_range_str: str,
    quick_summary: str,
    stories: List[Dict[str, Any]]
) -> str:
    """Renders a themed Markdown digest grouped by sections."""
    groups = group_stories_by_theme(stories)

    lines = [
        f"Topic: {topic.strip()} | {date_range_str}",
        "",
        "Quick summary:",
        quick_summary.strip(),
        "",
        "Themed Sections:"
    ]

    total_sources = len(stories)

    for theme, theme_stories in groups.items():
        lines.append(f"\n### 📌 {theme}")
        for idx, story in enumerate(theme_stories, 1):
            title = story.get("title", "Untitled Story").strip()
            summary = story.get("summary", "").strip()
            source = story.get("source", "Unknown Source").strip()
            pub_date = story.get("published_date", "").strip() or "Recent"
            url = story.get("url", "").strip()

            lines.append(f"{idx}. {title}")
            lines.append(f"   {summary}")
            lines.append(f"   Source: {source} | {pub_date} | {url}")
            lines.append("")

    lines.append(f"\nBased on {total_sources} sources across {len(groups)} themed sections.")
    return "\n".join(lines)

