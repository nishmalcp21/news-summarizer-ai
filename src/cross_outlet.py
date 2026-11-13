"""
Cross-Outlet Coverage Comparison Engine (PRD Section 13).
Analyzes how different media outlets framed the same event,
identifying consensus facts, distinct angles, and tone balance.
"""

from typing import List, Dict, Any
import re


def analyze_tone(text: str) -> str:
    """Calculates factual, optimistic, critical, or neutral tone orientation."""
    lowered = text.lower()
    optimistic_words = {"breakthrough", "record", "growth", "boost", "surge", "gain", "advances", "success", "milestone"}
    critical_words = {"risk", "concern", "obstacle", "delay", "challenge", "criticism", "slump", "threat", "warning"}

    opt_count = sum(1 for w in optimistic_words if w in lowered)
    crit_count = sum(1 for w in critical_words if w in lowered)

    if opt_count > crit_count and opt_count >= 2:
        return "Optimistic / Growth-focused"
    elif crit_count > opt_count and crit_count >= 2:
        return "Critical / Risk-focused"
    elif opt_count > 0 and crit_count > 0:
        return "Balanced / Mixed"
    return "Neutral / Factual"


def compare_outlet_coverage(stories: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compares coverage across multiple outlets.
    Returns:
        {
            "outlets_compared": List[str],
            "common_keywords": List[str],
            "outlet_breakdown": List[Dict[str, Any]],
            "overall_tone_balance": str
        }
    """
    if not stories:
        return {
            "outlets_compared": [],
            "common_keywords": [],
            "outlet_breakdown": [],
            "overall_tone_balance": "No data"
        }

    outlets = []
    breakdowns = []
    tone_counts = {}

    for s in stories:
        outlet_name = s.get("source") or "Unknown"
        title = s.get("title", "")
        content = s.get("summary", "") or s.get("text", "") or s.get("snippet", "")
        tone = analyze_tone(f"{title} {content}")

        tone_counts[tone] = tone_counts.get(tone, 0) + 1
        outlets.append(outlet_name)

        breakdowns.append({
            "outlet": outlet_name,
            "headline": title,
            "tone": tone,
            "url": s.get("url", "")
        })

    # Overall consensus tone
    dominant_tone = max(tone_counts, key=tone_counts.get) if tone_counts else "Neutral"

    return {
        "outlets_compared": list(set(outlets)),
        "story_count": len(stories),
        "outlet_breakdown": breakdowns,
        "overall_tone_balance": dominant_tone
    }


def format_cross_outlet_report(comparison: Dict[str, Any]) -> str:
    """Formats comparison results into clean Markdown."""
    outlets = ", ".join(comparison.get("outlets_compared", []))
    lines = [
        "### 📊 Cross-Outlet Coverage Comparison",
        f"- **Outlets Analyzed**: {outlets or 'None'}",
        f"- **Overall Tone Orientation**: {comparison.get('overall_tone_balance')}",
        "",
        "| Outlet | Headline Angle | Tone Orientation |",
        "|---|---|---|"
    ]

    for item in comparison.get("outlet_breakdown", []):
        outlet = item.get("outlet", "Unknown")
        headline = item.get("headline", "Untitled")
        tone = item.get("tone", "Neutral")
        lines.append(f"| **{outlet}** | {headline} | {tone} |")

    return "\n".join(lines)

