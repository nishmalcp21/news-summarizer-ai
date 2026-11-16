"""
Export and Favorites Management Module (Post-MVP Enhancement - PRD Section 13).
Supports saved favorite topics and in-memory digest exports.
"""

import json
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fpdf import FPDF

from src.config import PROJECT_ROOT


FAVORITES_FILE = PROJECT_ROOT / "memory" / "favorites.json"


def get_favorites() -> List[str]:
    """Retrieves list of saved favorite topics."""
    if not FAVORITES_FILE.exists():
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def add_favorite(topic: str) -> bool:
    """Adds a topic to favorites."""
    cleaned = topic.strip()
    if not cleaned:
        return False
    favs = get_favorites()
    if cleaned not in favs:
        favs.append(cleaned)
        FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, indent=2)
        return True
    return False


def remove_favorite(topic: str) -> bool:
    """Removes a topic from favorites."""
    cleaned = topic.strip()
    favs = get_favorites()
    if cleaned in favs:
        favs.remove(cleaned)
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, indent=2)
        return True
    return False


def export_to_json(digest_data: Dict[str, Any], filepath: Path) -> Path:
    """Exports structured digest data to a JSON file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(digest_data, f, indent=2, ensure_ascii=False)
    return filepath


def _executive_overview(digest_text: str) -> str:
    if "Quick summary:" in digest_text:
        overview = digest_text.split("Quick summary:", 1)[1]
        if "Key stories:" in overview:
            overview = overview.split("Key stories:", 1)[0]
        return overview.strip()
    return digest_text.strip()


def export_to_markdown(
    topic: str,
    digest_text: str,
    stories: List[Dict[str, Any]],
    digest_date: Optional[str] = None,
) -> str:
    """Builds a Markdown digest in memory."""
    digest_date = digest_date or date.today().isoformat()
    lines = [
        f"# {topic}",
        "",
        f"Date: {digest_date}",
        "",
        "## Executive Overview",
        "",
        _executive_overview(digest_text),
        "",
        "## Stories",
        "",
    ]

    for story in stories:
        title = story.get("title", "Untitled")
        outlet = story.get("source", "Unknown outlet")
        published_date = story.get("published_date", "Date unavailable")
        summary = story.get("summary", "")
        url = story.get("url", "")
        lines.extend([
            f"### **{title}**",
            "",
            f"**{outlet}** | {published_date}",
            "",
            summary,
            "",
            f"[Source]({url})" if url else "Source unavailable",
            "",
        ])
    return "\n".join(lines).strip() + "\n"


def export_to_text(
    topic: str,
    digest_text: str,
    stories: List[Dict[str, Any]],
    digest_date: Optional[str] = None,
) -> str:
    """Builds a plain-text digest in memory."""
    digest_date = digest_date or date.today().isoformat()
    lines = [
        topic,
        f"Date: {digest_date}",
        "",
        "EXECUTIVE OVERVIEW",
        _executive_overview(digest_text),
        "",
        "STORIES",
    ]
    for story in stories:
        lines.extend([
            "",
            story.get("title", "Untitled"),
            f"Outlet: {story.get('source', 'Unknown outlet')} | "
            f"Date: {story.get('published_date', 'Date unavailable')}",
            story.get("summary", ""),
            f"Source: {story.get('url', '')}",
        ])
    return "\n".join(lines).strip() + "\n"


def _pdf_safe_text(value: Any) -> str:
    replacements = str(value).translate(str.maketrans({
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
        "\u00a0": " ",
    }))
    normalized = unicodedata.normalize("NFKD", replacements)
    return normalized.encode("ascii", "ignore").decode("ascii")


class _DigestPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def export_to_pdf(
    topic: str,
    digest_text: str,
    stories: List[Dict[str, Any]],
    digest_date: Optional[str] = None,
) -> bytes:
    """Builds a PDF digest in memory using core fonts for Unicode safety."""
    digest_date = digest_date or date.today().isoformat()
    pdf = _DigestPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_title(_pdf_safe_text(f"News Digest: {topic}"))

    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 10, _pdf_safe_text(topic), new_x="LMARGIN")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, _pdf_safe_text(f"Date: {digest_date}"), new_x="LMARGIN")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 7, "Executive Overview", new_x="LMARGIN")
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(
        0, 6, _pdf_safe_text(_executive_overview(digest_text)), new_x="LMARGIN"
    )

    for story in stories:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(
            0, 7, _pdf_safe_text(story.get("title", "Untitled")), new_x="LMARGIN"
        )
        pdf.set_font("Helvetica", "", 10)
        outlet = story.get("source", "Unknown outlet")
        published_date = story.get("published_date", "Date unavailable")
        pdf.multi_cell(
            0, 6, _pdf_safe_text(f"{outlet} | {published_date}"), new_x="LMARGIN"
        )
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(
            0, 6, _pdf_safe_text(story.get("summary", "")), new_x="LMARGIN"
        )

        url = str(story.get("url", ""))
        if url:
            pdf.set_text_color(0, 80, 180)
            pdf.write(6, _pdf_safe_text(url), link=url)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(6)

    return bytes(pdf.output())

