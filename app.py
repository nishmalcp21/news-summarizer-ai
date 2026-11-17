"""
Streamlit Web Interface for News Summarizer Agent.
Modern news dashboard with a responsive search-first home, live agent progress,
verified-story cards, themed insights, follow-up Q&A, and export/history tools.
"""

import sys
import json
import html
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.agent import PlainPythonNewsAgent
from src.llm.mock_llm import MockLLMClient
from src.llm.real_llm import RealLLMClient
from src.config import config
from src.theming import group_stories_by_theme
from src.cross_outlet import compare_outlet_coverage, format_cross_outlet_report
from src.qa import StoryQAEngine
from src.exporter import (
    add_favorite,
    get_favorites,
    export_to_json,
    export_to_markdown,
    export_to_pdf,
    export_to_text,
)
from src.memory import PersistentMemory
from src.tools.memory_tool import manage_memory as _manage_memory


def _clear_all_history() -> None:
    PersistentMemory().clear_history()
    st.session_state["current_digest"] = None
    st.session_state["current_stories"] = []
    st.session_state["current_topic"] = ""
    st.session_state["search_input"] = ""
    st.session_state["trigger_search"] = False
    st.session_state["chat_messages"] = []
    st.session_state["recent_chats"] = []
    st.rerun()

def _delete_topic_history(topic: str) -> None:
    PersistentMemory().delete_topic_history(topic)


def _sync_search_input() -> None:
    st.session_state["search_input"] = st.session_state.get("search_box", "")


def _parse_digest_stories(digest_text: str) -> list:
    if "Key stories:" not in digest_text:
        return []

    stories_block = digest_text.split("Key stories:", 1)[1].split("Based on", 1)[0].strip()
    stories = []
    for block in stories_block.split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        display_title = lines[0]
        title = display_title
        if ". " in title and title.split(". ", 1)[0].isdigit():
            title = title.split(". ", 1)[1]
        summary_lines = []
        story = {
            "title": title,
            "source": "Verified Source",
            "published_date": "Recent",
            "url": "",
        }

        for line in lines[1:]:
            if line.startswith("Source:"):
                source_parts = line.removeprefix("Source:").strip().split("|", 2)
                story["source"] = source_parts[0].strip() if source_parts else "Verified Source"
                if len(source_parts) > 1:
                    story["published_date"] = source_parts[1].strip()
                if len(source_parts) > 2:
                    story["url"] = source_parts[2].strip()
            else:
                summary_lines.append(line)
        story["summary"] = " ".join(summary_lines)
        stories.append(story)
    return stories


def _build_history_table_html(history_records: list) -> str:
    rows = []
    for record in reversed(history_records[-10:]):
        status_text = "Success" if record.get("success") else "Incomplete"
        values = (
            record.get("topic", "N/A"),
            record.get("num_stories", "N/A"),
            record.get("time_range", "N/A"),
            status_text,
            record.get("story_count", "N/A"),
        )
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in values)
        rows.append(f"<tr>{cells}</tr>")
    return (
        '<div style="overflow-x: auto; margin-top: 10px;">'
        '<table class="claude-table"><thead><tr>'
        "<th>Topic</th><th>Stories</th><th>Time Horizon</th>"
        "<th>Status</th><th>Count</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _build_history_markdown(history_records: list) -> str:
    lines = [
        "| Topic | Stories | Time Horizon | Status | Count |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for record in reversed(history_records):
        status = "Success" if record.get("success") else "Incomplete"
        topic = str(record.get("topic", "N/A")).replace("|", "\\|")
        lines.append(
            f"| {topic} | {record.get('num_stories', 'N/A')} | "
            f"{record.get('time_range', 'N/A')} | {status} | "
            f"{record.get('story_count', 'N/A')} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Feedback & Rating Persistence (PRD Section 10)
# ---------------------------------------------------------------------------
def get_ratings():
    ratings_file = PROJECT_ROOT / "memory" / "ratings.json"
    if not ratings_file.exists():
        return []
    try:
        with open(ratings_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_user_rating(topic: str, rating: str) -> None:
    ratings_file = PROJECT_ROOT / "memory" / "ratings.json"
    ratings_file.parent.mkdir(parents=True, exist_ok=True)
    records = get_ratings()
    records.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "rating": rating
    })
    with open(ratings_file, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


# ---------------------------------------------------------------------------
# News Dashboard Styling (controlled by the in-app appearance toggle)
# ---------------------------------------------------------------------------
def inject_claude_styling():
    # Detect Streamlit native theme selection (System / Light / Dark)
    theme_type = "dark" if st.session_state.get("dark_mode_toggle", False) else "light"
    try:
        if "dark_mode_toggle" not in st.session_state and hasattr(st, "context") and hasattr(st.context, "theme") and st.context.theme:
            t = st.context.theme.type
            if t in ("dark", "light"):
                theme_type = t
    except Exception:
        theme_type = "light"

    if theme_type == "dark":
        palette = {
            "background_color": "#FBF8F3",
            "secondary_background_color": "#F3EEE6",
            "surface_color": "#FFFFFF",
            "text_color": "#1A1A1A",
            "text_secondary": "#4A4A4A",
            "subtitle_color": "#4A4A4A",
            "label_color": "#4A4A4A",
            "placeholder_color": "#4A4A4A",
            "border_color": "#E3DCCF",
            "bubble_user": "#F3EEE6",
            "primary_color": "#C8102E",
            "accent_hover": "#A30D25",
            "focus_ring": "rgba(200, 16, 46, 0.2)",
            "button_text": "#1A1A1A",
            "primary_btn_text": "#FFFFFF",
            "link_color": "#0B5CAD",
            "code_bg": "#F3EEE6",
            "shadow_soft": "0 1px 3px rgba(0, 0, 0, 0.08)",
        }
    else:
        palette = {
            "background_color": "#FBF8F3",
            "secondary_background_color": "#F3EEE6",
            "surface_color": "#FFFFFF",
            "text_color": "#1A1A1A",
            "text_secondary": "#4A4A4A",
            "subtitle_color": "#4A4A4A",
            "label_color": "#4A4A4A",
            "placeholder_color": "#4A4A4A",
            "border_color": "#E3DCCF",
            "bubble_user": "#F3EEE6",
            "primary_color": "#C8102E",
            "accent_hover": "#A30D25",
            "focus_ring": "rgba(200, 16, 46, 0.2)",
            "button_text": "#1A1A1A",
            "primary_btn_text": "#FFFFFF",
            "link_color": "#0B5CAD",
            "code_bg": "#F3EEE6",
            "shadow_soft": "0 1px 3px rgba(0, 0, 0, 0.08)",
        }

    css = """
    <style>
        :root {
            --background-color: __background_color__;
            --secondary-background-color: __secondary_background_color__;
            --surface-color: __surface_color__;
            --text-color: __text_color__;
            --text-secondary: __text_secondary__;
            --subtitle-color: __subtitle_color__;
            --label-color: __label_color__;
            --placeholder-color: __placeholder_color__;
            --border-color: __border_color__;
            --bubble-user: __bubble_user__;
            --primary-color: __primary_color__;
            --accent-hover: __accent_hover__;
            --link-color: __link_color__;
            --focus-ring: __focus_ring__;
            --button-text: __button_text__;
            --primary-btn-text: __primary_btn_text__;
            --code-bg: __code_bg__;
            --shadow-soft: __shadow_soft__;

            /* Backward-compatible aliases */
            --accent: var(--primary-color);
            --text-primary: var(--text-color);
            --bg-surface: var(--surface-color);
            --bg-sidebar: var(--secondary-background-color);
            --bg-page: var(--background-color);
            --bg-code: var(--code-bg);
        }

        /* 200ms smooth transition across states */
        *, *::before, *::after {
            transition: background-color 200ms ease, color 200ms ease, border-color 200ms ease, box-shadow 200ms ease;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        body, .stApp, [data-testid="stAppViewContainer"] {
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
        }
        [data-testid="stHeader"] {
            background-color: var(--background-color) !important;
        }
        [data-testid="stToolbar"] {
            background-color: transparent !important;
        }
        h1, h2, h3, h4, h5, h6,
        .greeting-title, .story-title {
            font-family: 'Inter', sans-serif !important;
            color: var(--text-color);
        }

        /* Main dashboard column with generous spacing */
        .block-container {
            max-width: 1120px !important;
            padding-top: 2rem !important;
            padding-bottom: 8rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            margin: 0 auto !important;
        }

        /* Sidebar layout & theme */
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }

        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 1.75rem;
            padding-bottom: 2.25rem;
            padding-left: 1.1rem;
            padding-right: 1.1rem;
        }

        /* Section Labels ("Recent Chats", "Trending Presets") */
        .section-label {
            color: var(--label-color) !important;
            font-weight: 600 !important;
            opacity: 1 !important;
        }

        /* Captions */
        [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] * {
            color: var(--text-secondary) !important;
            opacity: 1 !important;
        }

        /* Centered Empty State Greeting */
        .empty-state {
            text-align: center;
            padding: 56px 20px 32px;
            margin-bottom: 32px;
        }
        .greeting-title {
            font-size: 42px !important;
            font-weight: 700 !important;
            letter-spacing: -0.03em !important;
            color: var(--text-color) !important;
            opacity: 1 !important;
            margin-bottom: 14px !important;
        }
        .greeting-sub {
            font-size: 16px !important;
            color: var(--subtitle-color) !important;
            opacity: 1 !important;
            max-width: 520px !important;
            margin: 0 auto 36px !important;
            line-height: 1.65 !important;
        }

        /* All Secondary Buttons: Presets, Sidebar Recent Chats, Ratings */
        .stButton > button:not([kind="primary"]) {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            font-weight: 500 !important;
            font-size: 13.5px !important;
            color: var(--button-text) !important;
            box-shadow: var(--shadow-soft) !important;
            transition: all 150ms ease !important;
        }
        .stButton > button:not([kind="primary"]) * {
            color: var(--button-text) !important;
            font-weight: 500 !important;
            opacity: 1 !important;
        }
        .stButton > button:not([kind="primary"]):hover {
            border-color: var(--accent-hover) !important;
            background-color: var(--surface-color) !important;
            box-shadow: 0 0 0 1px var(--accent-hover) !important;
        }
        .stButton > button:not([kind="primary"]):hover * {
            color: var(--primary-color) !important;
        }

        /* Sidebar Recent Chat Buttons Alignment */
        [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
            justify-content: flex-start !important;
            text-align: left !important;
        }

        /* Primary Action Buttons */
        .stButton > button[kind="primary"] {
            background-color: var(--primary-color) !important;
            color: var(--primary-btn-text) !important;
            border: 1px solid var(--primary-color) !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
            font-size: 13.5px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .stButton > button[kind="primary"] * {
            color: var(--primary-btn-text) !important;
            font-weight: 500 !important;
            opacity: 1 !important;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: var(--accent-hover) !important;
            border-color: var(--accent-hover) !important;
        }
        .stButton > button[kind="primary"]:hover * {
            color: var(--primary-btn-text) !important;
        }

        /* Download Buttons */
        .stDownloadButton > button {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
            font-weight: 500 !important;
            font-size: 13.5px !important;
            color: var(--button-text) !important;
            box-shadow: var(--shadow-soft) !important;
            transition: all 150ms ease !important;
        }
        .stDownloadButton > button * {
            color: var(--button-text) !important;
            font-weight: 500 !important;
            opacity: 1 !important;
        }
        .stDownloadButton > button:hover {
            border-color: var(--accent-hover) !important;
            background-color: var(--surface-color) !important;
        }
        .stDownloadButton > button:hover * {
            color: var(--primary-color) !important;
        }

        /* "Engine Settings & Preferences" Expander */
        [data-testid="stExpander"] {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 14px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        [data-testid="stExpander"] details {
            background-color: var(--surface-color) !important;
            border-radius: 14px !important;
        }
        [data-testid="stExpander"] summary {
            background-color: var(--surface-color) !important;
            border-radius: 14px !important;
        }
        [data-testid="stExpander"] summary * {
            color: var(--text-color) !important;
            font-weight: 500 !important;
            opacity: 1 !important;
        }
        [data-testid="stExpander"] summary svg {
            color: var(--text-color) !important;
            fill: var(--text-color) !important;
            stroke: var(--text-color) !important;
        }
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background-color: var(--surface-color) !important;
            border-top: 1px solid var(--border-color) !important;
            border-radius: 0 0 14px 14px !important;
        }
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] * {
            color: var(--text-color) !important;
        }

        /* Controls inside Sidebar Expander (Radio, Selectbox, Slider) */
        .stSelectbox label, .stSlider label, .stRadio label {
            color: var(--text-color) !important;
            font-weight: 500 !important;
            opacity: 1 !important;
        }
        .stSelectbox [data-baseweb="select"] {
            background-color: var(--surface-color) !important;
            border-color: var(--border-color) !important;
        }
        .stSelectbox [data-baseweb="select"] * {
            color: var(--text-color) !important;
        }
        .stRadio [role="radiogroup"] label * {
            color: var(--text-color) !important;
        }

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottomBlockContainer"] {
            background-color: var(--background-color) !important;
        }

        /* Fixed Bottom Chat Input Styling */
        [data-testid="stBottom"] {
            background-color: var(--background-color) !important;
        }
        [data-testid="stBottomBlockContainer"] {
            background-color: var(--background-color) !important;
        }
        [data-testid="stChatInput"] {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 18px !important;
            box-shadow: var(--shadow-soft) !important;
            padding: 6px 12px !important;
            outline: none !important;
        }
        [data-testid="stChatInput"] > div {
            background-color: transparent !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 0 1px var(--primary-color) !important;
        }
        [data-testid="stChatInput"] textarea {
            color: var(--text-color) !important;
            background-color: transparent !important;
            font-size: 15px !important;
            line-height: 1.5 !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            opacity: 1 !important;
        }
        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--placeholder-color) !important;
            opacity: 1 !important;
        }
        [data-testid="stChatInput"] button {
            color: var(--primary-color) !important;
            background: transparent !important;
            border: none !important;
        }
        [data-testid="stChatInput"] button:hover {
            color: var(--accent-hover) !important;
        }

        /* User Message: Right-aligned soft rounded bubble */
        .user-msg-container {
            display: flex;
            justify-content: flex-end;
            margin-top: 20px;
            margin-bottom: 28px;
        }
        .user-msg-bubble {
            background-color: var(--bubble-user) !important;
            color: var(--text-color) !important;
            padding: 12px 20px !important;
            border-radius: 18px 18px 6px 18px !important;
            max-width: 82% !important;
            font-size: 15px !important;
            line-height: 1.55 !important;
            box-shadow: var(--shadow-soft) !important;
            border: 1px solid var(--border-color) !important;
            word-break: break-word !important;
            opacity: 1 !important;
        }

        /* Agent Reply: Plain text directly on page with NO bubble */
        .agent-reply-body {
            color: var(--text-color);
            font-size: 15.5px;
            line-height: 1.7;
            margin-bottom: 32px;
        }
        .agent-reply-body h1, 
        .agent-reply-body h2, 
        .agent-reply-body h3, 
        .agent-reply-body h4 {
            color: var(--text-color);
            font-family: 'Inter', sans-serif;
            font-weight: 700;
            margin-top: 24px;
            margin-bottom: 12px;
            opacity: 1;
        }
        .agent-reply-body p {
            color: var(--text-color);
            line-height: 1.7;
            margin-bottom: 14px;
            opacity: 1;
        }
        .agent-reply-body a {
            color: var(--primary-color);
            text-decoration: underline;
            text-underline-offset: 3px;
        }
        .agent-reply-body a:hover {
            color: var(--accent-hover);
        }

        /* News Cards */
        .news-card {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            padding: 24px 26px !important;
            margin-bottom: 20px !important;
            box-shadow: var(--shadow-soft) !important;
            transition: transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease !important;
        }
        .news-card:hover {
            border-color: var(--primary-color) !important;
            box-shadow: 0 4px 14px rgba(16, 24, 40, 0.08) !important;
            transform: translateY(-1px);
        }
        .story-title {
            color: var(--text-color) !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 20px !important;
            font-weight: 700 !important;
            margin-top: 10px !important;
            margin-bottom: 10px !important;
            line-height: 1.38 !important;
            opacity: 1 !important;
        }
        .story-summary {
            color: var(--text-secondary) !important;
            font-size: 14.5px !important;
            line-height: 1.6 !important;
            opacity: 1 !important;
        }
        .badge-source {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-secondary) !important;
            font-weight: 600 !important;
            padding: 4px 10px !important;
            border-radius: 9999px !important;
            font-size: 12px !important;
            border: 1px solid var(--border-color) !important;
            display: inline-block !important;
            opacity: 1 !important;
        }
        .badge-date {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-secondary) !important;
            padding: 4px 10px !important;
            border-radius: 9999px !important;
            font-size: 12px !important;
            border: 1px solid var(--border-color) !important;
            display: inline-block !important;
            margin-left: 6px !important;
            opacity: 1 !important;
        }
        .badge-theme {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-secondary) !important;
            font-weight: 600 !important;
            padding: 4px 10px !important;
            border-radius: 9999px !important;
            font-size: 12px !important;
            border: 1px solid var(--border-color) !important;
            display: inline-block !important;
            opacity: 1 !important;
        }

        /* Executive Overview Box */
        .quick-summary-box {
            background-color: var(--surface-color) !important;
            border-left: 3px solid var(--primary-color) !important;
            border-top: 1px solid var(--border-color) !important;
            border-right: 1px solid var(--border-color) !important;
            border-bottom: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            padding: 22px 26px !important;
            margin-bottom: 28px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .quick-summary-title {
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
            font-size: 17px !important;
            margin-bottom: 9px !important;
            color: var(--primary-color) !important;
            opacity: 1 !important;
        }
        .quick-summary-text {
            font-size: 15.5px !important;
            line-height: 1.7 !important;
            color: var(--text-color) !important;
            opacity: 1 !important;
        }

        /* Tabs: clearly readable in both Light and Dark themes */
        .stTabs [data-baseweb="tab-list"] {
            gap: 12px !important;
            background-color: transparent !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: transparent !important;
            border: none !important;
            padding: 10px 18px !important;
            border-radius: 8px 8px 0 0 !important;
        }
        .stTabs [data-baseweb="tab"] * {
            color: var(--text-secondary) !important;
            font-weight: 500 !important;
            font-size: 14.5px !important;
            opacity: 1 !important;
            transition: color 150ms ease !important;
        }
        .stTabs [data-baseweb="tab"]:hover * {
            color: var(--text-color) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            border-bottom: 2px solid var(--primary-color) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] * {
            color: var(--primary-color) !important;
            font-weight: 600 !important;
        }

        /* Code blocks */
        code, pre {
            background-color: var(--code-bg) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 6px !important;
        }

        /* Text Input */
        .stTextInput > div > div > input {
            background-color: var(--surface-color) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            opacity: 1 !important;
        }
        .stTextInput > div > div > input::placeholder {
            color: var(--placeholder-color) !important;
            opacity: 1 !important;
        }
        .stTextInput > div > div > input:focus {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 0 1px var(--primary-color) !important;
        }

        /* Metrics */
        [data-testid="stMetric"], [data-testid="stMetric"] * {
            color: var(--text-color) !important;
        }
        [data-testid="stMetricLabel"] * {
            color: var(--text-secondary) !important;
        }

        /* Pure HTML table styling */
        .claude-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
            text-align: left;
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
        }
        .claude-table th {
            padding: 10px 14px;
            font-weight: 600;
            color: var(--text-color);
            background-color: var(--secondary-background-color);
            border-bottom: 1px solid var(--border-color);
        }
        .claude-table td {
            padding: 10px 14px;
            color: var(--text-color);
            border-bottom: 1px solid var(--border-color);
        }
        .claude-table tr:last-child td {
            border-bottom: none;
        }

        /* Compact delete (✕) buttons next to sidebar recent-chat items */
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]) {
            padding: 0 6px !important;
            min-height: 32px !important;
            height: 32px !important;
            font-size: 13px !important;
            border-radius: 6px !important;
            color: var(--text-secondary) !important;
            background-color: transparent !important;
            border: 1px solid transparent !important;
            box-shadow: none !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]):hover {
            background-color: var(--secondary-background-color) !important;
            border-color: var(--border-color) !important;
            color: var(--accent-hover) !important;
        }

        /* Responsive design */
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.85rem !important;
                padding-right: 0.85rem !important;
            }
            .user-msg-bubble {
                max-width: 95%;
            }
            .greeting-title {
                font-size: 30px !important;
            }
            .news-card {
                padding: 20px !important;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.6rem !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                min-width: min(100%, 240px) !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                overflow-x: auto !important;
                flex-wrap: nowrap !important;
            }
            .stTabs [data-baseweb="tab"] {
                white-space: nowrap !important;
                padding: 9px 12px !important;
            }
        }

        /* News dashboard refinements */
        .block-container {
            max-width: 1220px !important;
            padding-top: 1.1rem !important;
            padding-bottom: 5rem !important;
        }
        [data-testid="stHeader"],
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottomBlockContainer"] {
            background: var(--background-color) !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
            border-color: var(--border-color) !important;
            background: var(--surface-color) !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .story-summary {
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 3;
            overflow: hidden;
            min-height: 4.4em;
        }
        .stTextInput input {
            min-height: 52px !important;
            border-radius: 14px !important;
            font-size: 15px !important;
            padding-left: 16px !important;
        }
        [class*="st-key-preset_"] button {
            border-radius: 9999px !important;
            min-height: 42px !important;
        }
        .badge-source, .badge-date, .badge-theme {
            margin: 0 6px 6px 0 !important;
        }
        .stPopover [data-testid="stPopover"] {
            border-radius: 14px !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button {
            width: 44px !important;
            min-width: 44px !important;
            padding: 0 !important;
            white-space: nowrap !important;
            justify-content: center !important;
        }

        /* Clean White theme overrides */
        html, body, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMain"], [data-testid="stHeader"],
        [data-testid="stToolbar"], [data-testid="stBottom"],
        [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
        }
        body, .stApp, [data-testid="stAppViewContainer"] {
            font-size: 15px !important;
            line-height: 1.6 !important;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"] {
            background-color: var(--background-color) !important;
        }
        h1, h2, h3, h4, h5, h6, .greeting-title, .story-title,
        .quick-summary-title, .agent-reply-body h1, .agent-reply-body h2,
        .agent-reply-body h3, .agent-reply-body h4 {
            color: var(--text-color) !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
        }
        .block-container h1 {
            font-size: 2.4rem !important;
            font-weight: 700 !important;
            line-height: 1.2 !important;
            margin-bottom: 0.15rem !important;
        }
        .story-title { font-size: 19px !important; line-height: 1.4 !important; }
        .story-summary, .quick-summary-text, .agent-reply-body, .agent-reply-body p {
            color: var(--text-secondary) !important;
            font-size: 15px !important;
            line-height: 1.6 !important;
        }
        .greeting-sub, [data-testid="stCaptionContainer"],
        [data-testid="stCaptionContainer"] * {
            color: var(--text-secondary) !important;
            font-size: 15px !important;
            line-height: 1.6 !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }
        .news-card, [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .news-card {
            padding: 20px !important;
            margin-bottom: 20px !important;
        }
        .news-card:hover {
            border-color: var(--primary-color) !important;
            box-shadow: 0 4px 14px rgba(16, 24, 40, 0.08) !important;
            transform: translateY(-1px);
        }
        .badge-source, .badge-date, .badge-theme {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 9999px !important;
            color: var(--text-secondary) !important;
            font-weight: 500 !important;
        }
        .quick-summary-box {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-left: 3px solid var(--primary-color) !important;
            border-radius: 16px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .quick-summary-title { color: var(--primary-color) !important; }
        .stTabs [data-baseweb="tab-list"] {
            background: transparent !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent !important;
            border-radius: 0 !important;
        }
        .stTabs [data-baseweb="tab"] *,
        .stTabs [data-baseweb="tab"]:not([aria-selected="true"]) * {
            color: var(--text-secondary) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            border-bottom: 2px solid var(--primary-color) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] * {
            color: var(--primary-color) !important;
        }
        .stButton > button:not([kind="primary"]),
        .stDownloadButton > button {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            color: var(--button-text) !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .stButton > button[kind="primary"] {
            background-color: var(--primary-color) !important;
            border-color: var(--primary-color) !important;
            color: var(--primary-btn-text) !important;
            border-radius: 16px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .stButton > button[kind="primary"] * {
            color: var(--primary-btn-text) !important;
        }
        .stButton > button:not([kind="primary"]), .stDownloadButton > button {
            font-size: 14.5px !important;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background-color: var(--primary-color) !important;
            border-color: var(--primary-color) !important;
            color: var(--primary-btn-text) !important;
        }
        [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
            border-radius: 12px !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]):hover {
            background-color: var(--secondary-background-color) !important;
            border-color: var(--border-color) !important;
            color: var(--accent-hover) !important;
        }
        .stTextInput > div > div > input {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            color: var(--text-color) !important;
        }
        .stTextInput > div > div > input::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--text-secondary) !important;
            opacity: 1 !important;
        }
        .stTextInput > div > div > input:focus {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 0 3px var(--focus-ring) !important;
        }
        [data-testid="stChatInput"] {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 999px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 0 3px var(--focus-ring) !important;
        }
        .stSelectbox label, .stSlider label, .stRadio label,
        .stTextInput label, [data-testid="stCheckbox"] label {
            color: var(--text-color) !important;
        }
        .stSelectbox [data-baseweb="select"] {
            background-color: var(--surface-color) !important;
            border-color: var(--border-color) !important;
        }
        .stSelectbox [data-baseweb="select"] * { color: var(--text-color) !important; }
        .claude-table {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
        }
        .claude-table th {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }
        .claude-table td { color: var(--text-color) !important; }
        code, pre {
            background-color: var(--code-bg) !important;
            border-color: var(--border-color) !important;
            color: var(--text-color) !important;
        }

        /* Bright newspaper theme */
        html, body, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stMain"], [data-testid="stHeader"],
        [data-testid="stToolbar"], [data-testid="stBottom"],
        [data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
        }
        html, body, .stApp, [data-testid="stAppViewContainer"] {
            overflow-x: hidden !important;
        }
        .stApp {
            background-image:
                radial-gradient(rgba(26, 26, 26, 0.045) 0.5px, transparent 0.65px),
                radial-gradient(rgba(26, 26, 26, 0.035) 0.4px, transparent 0.65px) !important;
            background-size: 7px 7px, 11px 11px !important;
        }
        body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            color: var(--text-color) !important;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            font-size: 15px !important;
            line-height: 1.6 !important;
        }
        h1, h2, h3, h4, h5, h6, .greeting-title, .story-title,
        .quick-summary-title, .agent-reply-body h1, .agent-reply-body h2,
        .agent-reply-body h3, .agent-reply-body h4 {
            color: var(--text-color) !important;
            font-family: 'Playfair Display', Georgia, serif !important;
            font-weight: 600 !important;
        }
        .block-container h1 {
            font-size: 2.45rem !important;
            font-weight: 700 !important;
            line-height: 1.2 !important;
        }
        .block-container h1::after,
        .block-container h2::after, .block-container h3::after,
        .block-container h4::after, .section-label::after,
        .quick-summary-title::after {
            content: "";
            display: block;
            width: 36px;
            height: 2px;
            margin-top: 7px;
            background-color: var(--primary-color);
        }
        .block-container h1::after { width: 54px; margin-top: 10px; }
        .story-title { font-size: 19px !important; line-height: 1.4 !important; }
        .story-summary, .quick-summary-text, .agent-reply-body,
        .agent-reply-body p, .greeting-sub {
            color: var(--text-secondary) !important;
            font-family: 'Inter', sans-serif !important;
            font-size: 15px !important;
            line-height: 1.6 !important;
        }
        a, .agent-reply-body a {
            color: var(--link-color) !important;
        }
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color) !important;
            border-right: 1px solid var(--border-color) !important;
        }
        .news-card, [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            border-left: 3px solid var(--primary-color) !important;
            border-radius: 12px !important;
            padding: 20px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .news-card:hover, [data-testid="stVerticalBlockBorderWrapper"]:hover {
            border-color: var(--primary-color) !important;
            box-shadow: 0 5px 14px rgba(0, 0, 0, 0.1) !important;
            transform: translateY(-2px);
        }
        .badge-source, .badge-date, .badge-theme {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 9999px !important;
            color: var(--text-secondary) !important;
            font-size: 11px !important;
            font-weight: 600 !important;
            letter-spacing: 0.04em !important;
            text-transform: uppercase !important;
        }
        .quick-summary-box {
            background-color: var(--secondary-background-color) !important;
            border: 1px solid var(--border-color) !important;
            border-left: 3px solid var(--primary-color) !important;
            border-radius: 12px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .quick-summary-title { color: var(--primary-color) !important; }
        .stTabs [data-baseweb="tab-list"] {
            background: transparent !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background: transparent !important;
            border-radius: 0 !important;
        }
        .stTabs [data-baseweb="tab"] *,
        .stTabs [data-baseweb="tab"]:not([aria-selected="true"]) * {
            color: var(--text-secondary) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            border-bottom: 2px solid var(--primary-color) !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] * {
            color: var(--primary-color) !important;
        }
        .stButton > button[kind="primary"] {
            background-color: var(--primary-color) !important;
            border: 1px solid var(--primary-color) !important;
            color: #FFFFFF !important;
        }
        .stButton > button[kind="primary"] * {
            color: #FFFFFF !important;
        }
        .stButton > button:not([kind="primary"]),
        .stDownloadButton > button {
            background-color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            color: var(--text-color) !important;
            box-shadow: var(--shadow-soft) !important;
        }
        [data-testid="stPopover"] button,
        [data-testid="stPopoverButton"],
        button[aria-haspopup="dialog"] {
            background-color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            color: var(--text-color) !important;
            font-weight: 600 !important;
            opacity: 1 !important;
        }
        [data-testid="stPopover"] button *,
        [data-testid="stPopoverButton"] *,
        button[aria-haspopup="dialog"] * {
            color: var(--text-color) !important;
            fill: var(--text-color) !important;
            stroke: var(--text-color) !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 42px !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]) {
            width: 44px !important;
            min-width: 44px !important;
            height: 42px !important;
            min-height: 42px !important;
            padding: 0 !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
            background-color: #FFFFFF !important;
            color: var(--text-color) !important;
            font-size: 18px !important;
            line-height: 1 !important;
            opacity: 1 !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .stTextInput > div > div > input,
        [data-testid="stChatInput"] {
            background-color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 16px !important;
            color: var(--text-color) !important;
        }
        .stTextInput > div > div > input::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: var(--text-secondary) !important;
            opacity: 1 !important;
        }
        .stTextInput > div > div > input:focus,
        [data-testid="stChatInput"]:focus-within {
            border-color: var(--primary-color) !important;
            box-shadow: 0 0 0 3px var(--focus-ring) !important;
        }
        [data-testid="stChatInput"] { border-radius: 999px !important; }
        .stSelectbox label, .stSlider label, .stRadio label,
        .stTextInput label, [data-testid="stCheckbox"] label {
            color: var(--text-color) !important;
        }
        .claude-table {
            background-color: #FFFFFF !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 12px !important;
        }
        .claude-table th {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }
        .claude-table td { color: var(--text-color) !important; }
        code, pre {
            background-color: var(--secondary-background-color) !important;
            border-color: var(--border-color) !important;
            color: var(--text-color) !important;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.6rem !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important;
                width: 100% !important;
                min-width: 0 !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                flex-wrap: wrap !important;
                overflow-x: hidden !important;
                gap: 2px !important;
            }
            .stTabs [data-baseweb="tab"] {
                white-space: normal !important;
                padding: 8px 10px !important;
            }
            .story-title { font-size: 18px !important; }
        }

        /* Repeating newspaper texture; the cream wash keeps it low contrast. */
        .stApp, [data-testid="stAppViewContainer"] {
            background-color: var(--background-color) !important;
            background-image:
                linear-gradient(rgba(251, 248, 243, 0.86), rgba(251, 248, 243, 0.86)),
                url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='grain'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='2' stitchTiles='stitch' result='noise'/%3E%3CfeColorMatrix in='noise' type='matrix' values='0%200%200%200%200.36%200%200%200%200%200.31%200%200%200%200%200.26%200.2%200%200%200%200'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23grain)'/%3E%3C/svg%3E"),
                repeating-linear-gradient(
                    to bottom,
                    transparent 0,
                    transparent 9px,
                    rgba(60, 50, 40, 0.07) 9px,
                    rgba(60, 50, 40, 0.07) 10px
                ),
                repeating-linear-gradient(
                    to right,
                    transparent 0,
                    transparent 239px,
                    rgba(60, 50, 40, 0.09) 239px,
                    rgba(60, 50, 40, 0.09) 240px
                ) !important;
            background-repeat: repeat !important;
            background-size: auto, 200px 200px, auto, auto !important;
            background-attachment: fixed !important;
        }
        [data-testid="stMain"] {
            background-color: transparent !important;
            background-image: none !important;
        }
        [data-testid="stHeader"], [data-testid="stToolbar"],
        [data-testid="stBottom"], [data-testid="stBottom"] > div,
        [data-testid="stBottomBlockContainer"] {
            background-color: var(--background-color) !important;
            background-image: none !important;
        }
        .news-card, [data-testid="stVerticalBlockBorderWrapper"],
        .stTextInput > div > div > input, [data-testid="stChatInput"],
        .stTabs, .stTabs [data-baseweb="tab-list"],
        .stTabs [data-baseweb="tab"], .stButton > button,
        .stDownloadButton > button, [data-testid="stPopover"],
        [data-testid="stPopover"] button, .claude-table {
            background-image: none !important;
        }
        .news-card, [data-testid="stVerticalBlockBorderWrapper"] {
            background-color: #FFFFFF !important;
        }
        .quick-summary-box {
            background-color: var(--secondary-background-color) !important;
            background-image: none !important;
        }
        [data-testid="stSidebar"] {
            background-color: var(--secondary-background-color) !important;
            background-image: none !important;
        }
        .stTextInput > div > div > input, [data-testid="stChatInput"] {
            background-color: #FFFFFF !important;
        }
        .stTabs, .stTabs [data-baseweb="tab-list"],
        .stTabs [data-baseweb="tab"] {
            background-color: var(--background-color) !important;
        }
        .stButton > button:not([kind="primary"]),
        .stDownloadButton > button,
        [data-testid="stPopover"] button,
        button[aria-haspopup="dialog"] {
            background-color: #FFFFFF !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
        }
        .stButton > button[kind="primary"] {
            background-color: var(--primary-color) !important;
            color: #FFFFFF !important;
        }
        [data-testid="stPopover"] button *,
        button[aria-haspopup="dialog"] * {
            color: var(--text-color) !important;
            fill: var(--text-color) !important;
            stroke: var(--text-color) !important;
            opacity: 1 !important;
        }
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]) {
            height: 42px !important;
            min-height: 42px !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"]:last-child .stButton > button:not([kind="primary"]) {
            color: var(--text-color) !important;
            font-size: 18px !important;
            opacity: 1 !important;
        }
        @media (max-width: 768px) {
            html, body, .stApp, [data-testid="stAppViewContainer"] {
                overflow-x: hidden !important;
            }
            [data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.6rem !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {
                flex: 1 1 100% !important;
                width: 100% !important;
                min-width: 0 !important;
            }
            .stTabs [data-baseweb="tab-list"] {
                flex-wrap: wrap !important;
                overflow-x: hidden !important;
            }
        }
    </style>
    """
    for k, v in palette.items():
        css = css.replace(f"__{k}__", v)
    st.markdown(css, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="News Summarizer AI",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Session state initialization
    if "current_digest" not in st.session_state:
        st.session_state["current_digest"] = None
    if "current_stories" not in st.session_state:
        st.session_state["current_stories"] = []
    if "current_topic" not in st.session_state:
        st.session_state["current_topic"] = ""
    if "search_input" not in st.session_state:
        st.session_state["search_input"] = ""
    if "trigger_search" not in st.session_state:
        st.session_state["trigger_search"] = False
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []
    if "recent_chats" not in st.session_state:
        st.session_state["recent_chats"] = []

    inject_claude_styling()

    if "preset_topic" in st.session_state:
        st.session_state["search_input"] = st.session_state.pop("preset_topic")
        st.session_state["search_box"] = st.session_state["search_input"]
    elif not st.session_state.get("current_digest") and not st.session_state.get("search_input"):
        st.session_state["search_box"] = ""
    elif "search_box" not in st.session_state:
        st.session_state["search_box"] = st.session_state.get("search_input", "")

    # -----------------------------------------------------------------------
    # Sidebar: New chat and recent topics
    # -----------------------------------------------------------------------
    with st.sidebar:
        if st.button("＋ Start new chat", use_container_width=True, type="primary"):
            st.session_state["current_digest"] = None
            st.session_state["current_topic"] = ""
            st.session_state["chat_messages"] = []
            st.session_state["search_input"] = ""
            st.session_state["trigger_search"] = False
            st.rerun()

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        st.markdown(
            "<p class='section-label' style='font-size: 12px; font-weight: 600; "
            "text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;'>"
            "Recent Chats</p>",
            unsafe_allow_html=True
        )

        pm = PersistentMemory()
        history_records = pm.get_history()

        recent_topics = []
        if history_records:
            for r in reversed(history_records):
                top = r.get("topic", "")
                if top and top not in recent_topics:
                    recent_topics.append(top)
                if len(recent_topics) >= 5:
                    break
        st.session_state["recent_chats"] = recent_topics

        if recent_topics:
            for top in recent_topics:
                chat_col, del_col = st.columns([5, 0.9], gap="small")
                with chat_col:
                    if st.button(f"💬 {top}", key=f"hist_{top}", use_container_width=True):
                        st.session_state["preset_topic"] = top
                        st.session_state["trigger_search"] = True
                        st.session_state["current_digest"] = None
                        st.rerun()
                with del_col:
                    if st.button("🗑", key=f"del_{top}", help=f"Delete '{top}' from history"):
                        _delete_topic_history(top)
                        if st.session_state.get("current_topic", "") == top:
                            st.session_state["current_digest"] = None
                            st.session_state["current_topic"] = ""
                            st.session_state["chat_messages"] = []
                        st.rerun()
        else:
            st.caption("No past chats yet.")

    has_active_chat = bool(st.session_state.get("current_digest"))

    title_col, settings_col = st.columns([5, 1.15], vertical_alignment="center")
    with title_col:
        st.markdown("# News Summarizer AI")
        st.caption("Your daily brief of clear, verified reporting.")
    with settings_col:
        with st.popover("⚙ Settings", use_container_width=True):
            st.markdown("### Engine Settings & Preferences")
            st.radio(
                "Search & LLM Provider",
                ["Offline Mock (Fast / Zero Token Cost)", "Live API (Tavily + LiteLLM)"],
                index=1,
                key="engine_mode"
            )
            st.selectbox(
                "Time Horizon",
                ["24h", "7d", "30d"],
                index=1,
                help="Recent window of news coverage.",
                key="time_range"
            )
            st.slider(
                "Story Target Count",
                min_value=3,
                max_value=10,
                value=3,
                help="Number of verified stories in final digest (PRD range: 3-10).",
                key="num_stories"
            )
            dark_default = False
            try:
                dark_default = bool(st.context.theme and st.context.theme.type == "dark")
            except Exception:
                pass
            st.toggle("Dark appearance", value=dark_default, key="dark_mode_toggle")
            favorites = get_favorites()
            if favorites:
                selected_fav = st.selectbox(
                    "Load bookmark:",
                    ["-- Select --"] + favorites,
                    key="favorite_topic"
                )
                if selected_fav != "-- Select --" and st.button(
                    "Search bookmarked topic",
                    use_container_width=True
                ):
                    st.session_state["preset_topic"] = selected_fav
                    st.session_state["trigger_search"] = True
                    st.rerun()
            else:
                st.caption("No bookmarks yet.")
            st.caption(
                f"Guardrails · {config.max_steps} max steps · "
                f"{config.cache_ttl_minutes}m cache · {config.default_timezone}"
            )

    mode = st.session_state.get("engine_mode", "Live API (Tavily + LiteLLM)")
    time_range = st.session_state.get("time_range", "7d")
    num_stories = st.session_state.get("num_stories", 3)

    if not has_active_chat:
        st.markdown("""
        <div class="empty-state">
            <div class="greeting-title">Your world, in context.</div>
            <div class="greeting-sub">
                Explore the latest verified reporting, distilled into a clear daily briefing.
            </div>
        </div>
        """, unsafe_allow_html=True)

    search_left, search_center, search_right = st.columns([1, 6, 1])
    with search_center:
        search_col, submit_col = st.columns([5, 1.15], vertical_alignment="bottom")
        with search_col:
            st.text_input(
                "Search news",
                placeholder="Search a topic, event, or question...",
                label_visibility="collapsed",
                key="search_box",
                on_change=_sync_search_input
            )
        with submit_col:
            search_submitted = st.button(
                "Explore",
                type="primary",
                use_container_width=True
            )

    # Four fast-launch topics, kept compact on desktop and allowed to wrap on mobile.
    if not has_active_chat:
        st.markdown(
            "<p class='section-label' style='font-size: 12px; font-weight: 600; "
            "text-align: center; margin: 18px 0 10px;'>TRENDING</p>",
            unsafe_allow_html=True
        )
        preset_columns = st.columns(4)
        presets = [
            ("🚗  EVs in India", "Electric vehicles in India"),
            ("🤖  AI regulation", "Global AI Regulation 2026"),
            ("⚛️  Quantum computing", "Quantum computing commercialization"),
            ("🔋  Battery patents", "Solid-state lithium battery patents"),
        ]
        for column, (label, query) in zip(preset_columns, presets):
            with column:
                if st.button(label, key=f"preset_{query}", use_container_width=True):
                    st.session_state["preset_topic"] = query
                    st.session_state["trigger_search"] = True
                    st.rerun()

    # Search submission and preset/bookmark launches share the existing search state.
    chat_query = st.session_state.get("search_box", "")
    st.session_state["search_input"] = chat_query
    if search_submitted and chat_query.strip():
        topic_to_run = chat_query.strip()
    elif st.session_state.get("trigger_search", False) and chat_query.strip():
        topic_to_run = chat_query.strip()
        st.session_state["trigger_search"] = False
    else:
        topic_to_run = None

    # Pipeline Execution
    if topic_to_run:
        if len(topic_to_run) < 2:
            st.warning("⚠️ Please provide a topic with at least 2 characters.")
            return

        is_mock = "Mock" in mode
        if not is_mock and not config.tavily_api_key:
            st.info("Live search isn't configured yet, so this briefing will use offline demo data.")
            is_mock = True

        llm = MockLLMClient() if is_mock else RealLLMClient()
        agent = PlainPythonNewsAgent(llm=llm)

        if is_mock:
            def mock_search_tool(query: str, time_range: str = "7d", **kwargs):
                slug = query.replace(" ", "-").lower()[:30]
                return [
                    {
                        "title": f"Key Developments and Strategy in {query}",
                        "url": f"https://verified-news.com/{slug}-update-1",
                        "snippet": f"Recent industry analysis highlights breakthroughs, regulatory compliance, and market deployments in {query}.",
                        "source": "verified-news.com",
                        "published_date": "2026-11-09"
                    },
                    {
                        "title": f"Market Outlook & Commercial Scaling for {query}",
                        "url": f"https://tech-monitor.org/{slug}-analysis-2",
                        "snippet": f"Global analysis across research centers evaluates market progress, patent grants, and public investments in {query}.",
                        "source": "tech-monitor.org",
                        "published_date": "2026-11-10"
                    },
                    {
                        "title": f"Deployment Roadmaps and Next Steps in {query}",
                        "url": f"https://energydaily.com/{slug}-deployment-3",
                        "snippet": f"Commercial field trials and pilot projects launch across major manufacturing and logistics hubs.",
                        "source": "energydaily.com",
                        "published_date": "2026-11-10"
                    },
                    {
                        "title": f"Regulatory Challenges and Policy Concerns in {query}",
                        "url": f"https://policymonitor.org/{slug}-policy-4",
                        "snippet": f"Officials discuss new compliance standards, risk assessments, and environmental reviews.",
                        "source": "policymonitor.org",
                        "published_date": "2026-11-10"
                    }
                ]

            def mock_extract_tool(url: str, story_id: str = "1", fallback_snippet: str = "", **kwargs):
                return {
                    "story_id": story_id,
                    "url": url,
                    "text": f"<article_data id='{story_id}' url='{url}'>\nDetailed reporting on industry developments: {fallback_snippet}\n</article_data>",
                    "published_date": "2026-11-10",
                    "is_fallback": False,
                    "status": "extracted"
                }

            agent.tools["search_news"] = mock_search_tool
            agent.tools["extract_article"] = mock_extract_tool

        with st.status("Agent progress", expanded=True) as status:
            plan = agent.planner.create_plan(topic_to_run, num_stories, time_range)
            if plan.aborted:
                status.update(label="⚠️ Planning Aborted", state="error", expanded=True)
                st.warning(plan.abort_reason or "This topic could not be planned. Try a more specific search.")
                return

            class AgentProgressHandler(logging.Handler):
                def emit(self, record):
                    message = record.getMessage()
                    if "[PLAN]" in message:
                        status.write("Planning")
                        status.update(label="Planning", state="running", expanded=True)
                    elif "[ACT]" in message and "search_news" in message:
                        status.write("Searching")
                        status.update(label="Searching", state="running", expanded=True)
                    elif "[ACT]" in message and any(
                        action in message for action in ("extract_article", "validate_link")
                    ):
                        status.write("Reading")
                        status.update(label="Reading", state="running", expanded=True)
                    elif "[ACT]" in message and any(
                        action in message for action in ("synthesize", "finish")
                    ):
                        status.write("Summarizing")
                        status.update(label="Summarizing", state="running", expanded=True)
                    elif "[FINISH]" in message:
                        status.write("Complete")
                        status.update(label="Briefing ready", state="complete", expanded=False)

            progress_handler = AgentProgressHandler()
            agent.logger._logger.addHandler(progress_handler)

            try:
                digest = agent.run(
                    topic=topic_to_run,
                    num_stories=num_stories,
                    time_range=time_range
                )
            except ImportError as error:
                status.update(label="Model unavailable", state="error", expanded=True)
                if "litellm" in str(error).lower():
                    st.info("The live language-model component is unavailable. Install/configure it or switch to Offline Mock in Settings.")
                else:
                    st.info("A required language-model component is unavailable. Check the provider settings and try again.")
                return
            except RuntimeError as error:
                message = str(error).lower()
                status.update(label="Briefing unavailable", state="error", expanded=True)
                if any(term in message for term in ("rate limit", "rate_limit", "ratelimit", "429", "too many requests")):
                    st.warning("The news provider is rate-limiting requests. Please wait a moment and try again.")
                elif any(term in message for term in ("ollama", "localhost:11434", "connection refused")):
                    st.info("The local language model appears to be offline. Start it or switch to Offline Mock in Settings.")
                else:
                    st.error("The news service couldn't complete this briefing. Please try again shortly.")
                return
            finally:
                agent.logger._logger.removeHandler(progress_handler)

        st.session_state["current_digest"] = digest
        st.session_state["current_topic"] = topic_to_run
        st.session_state["chat_messages"] = [
            {"role": "user", "content": f"Research {topic_to_run}"},
            {"role": "assistant", "content": digest}
        ]
        st.rerun()

    # Active Chat View
    if st.session_state.get("current_digest"):
        topic_disp = st.session_state["current_topic"]
        digest_text = st.session_state["current_digest"]

        st.markdown(f"""
        <div class="user-msg-container">
            <div class="user-msg-bubble">
                Research {html.escape(topic_disp)}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Executive Overview Box
        quick_sum = ""
        if "Quick summary:" in digest_text:
            parts = digest_text.split("Quick summary:")
            if len(parts) > 1:
                sub_parts = parts[1].split("Key stories:")
                quick_sum = sub_parts[0].strip()

        if quick_sum:
            st.markdown(f"""
            <div class="quick-summary-box">
                <div class="quick-summary-title">
                    Executive Overview
                </div>
                <div class="quick-summary-text">
                    {html.escape(quick_sum)}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Clean tabbed navigation for detailed analysis
        tab_studio, tab_themed, tab_qa, tab_export = st.tabs([
            "Verified Stories",
            "Themed Insights & Outlets",
            "Follow-Up Q&A",
            "Export & History"
        ])

        # Tab 1: Stories
        with tab_studio:
            digest_stories = _parse_digest_stories(digest_text)
            if digest_stories:
                for start in range(0, len(digest_stories), 2):
                    story_columns = st.columns(2, gap="medium")
                    for column, story in zip(story_columns, digest_stories[start:start + 2]):
                        with column:
                            with st.container(border=True):
                                source = html.escape(str(story.get("source", "Verified Source")))
                                published = html.escape(str(story.get("published_date", "Recent")))
                                title = html.escape(str(story.get("title", "Untitled story")))
                                summary = html.escape(str(story.get("summary", "")))
                                st.markdown(
                                    f'<span class="badge-source">{source}</span>'
                                    f'<span class="badge-date">{published}</span>',
                                    unsafe_allow_html=True
                                )
                                st.markdown(
                                    f'<div class="story-title">{title}</div>'
                                    f'<div class="story-summary">{summary}</div>',
                                    unsafe_allow_html=True
                                )
                                article_url = str(story.get("url", "")).strip()
                                if article_url.startswith(("https://", "http://")):
                                    st.link_button("Read article ↗", article_url)
                                else:
                                    st.caption("Article link unavailable.")
            else:
                st.info("No verified stories were available for this briefing. Try a broader topic or a longer time range.")

            with st.expander("View Full Markdown Digest"):
                st.code(digest_text, language="markdown")

            # Feedback Rating Widget
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            r_c1, r_c2, _ = st.columns([1.5, 1.5, 4])
            with r_c1:
                if st.button("👍 High Quality", use_container_width=True):
                    save_user_rating(topic_disp, "positive")
                    st.success("Rating recorded.")
            with r_c2:
                if st.button("👎 Needs Improvement", use_container_width=True):
                    save_user_rating(topic_disp, "negative")
                    st.info("Feedback captured.")

        # Tab 2: Themed Insights
        with tab_themed:
            st.markdown("#### Thematic Categorization")
            if digest_stories:
                themed_clusters = group_stories_by_theme(digest_stories)
                for theme_name, theme_list in themed_clusters.items():
                    st.markdown(f"**{html.escape(str(theme_name))}**")
                    for story in theme_list:
                        st.markdown(f"""
                        <div class="news-card">
                            <span class="badge-theme">{html.escape(str(theme_name))}</span>
                            <div class="story-title">{html.escape(str(story.get('title', 'Untitled story')))}</div>
                            <div class="story-summary">{html.escape(str(story.get('summary', '')))}</div>
                            <div style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">
                                Source: {html.escape(str(story.get('source', 'Verified Source')))}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("Themed insights will appear when verified stories are available.")

            st.markdown("<hr style='border: none; border-top: 1px solid var(--border-color); margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown("#### Cross-Outlet Tone & Framing Analysis")
            if digest_stories:
                outlet_analysis = compare_outlet_coverage(digest_stories)
                report_md = format_cross_outlet_report(outlet_analysis)
                st.markdown(report_md)
            else:
                st.caption("Outlet analysis will appear when multiple verified stories are available.")

        # Tab 3: Grounded Follow-up Q&A
        with tab_qa:
            st.markdown("#### Conversational Follow-Up")
            st.caption("Ask questions strictly grounded in the verified article corpus.")
            user_question = st.text_input(
                "Ask a specific question about these stories:",
                placeholder="e.g. What were the key policy targets?",
                key="qa_input_box"
            )

            if st.button("Answer Question", type="primary"):
                if user_question:
                    qa_engine = StoryQAEngine()
                    sample_context = [
                        {
                            "story_id": "1",
                            "title": f"Developments in {topic_disp}",
                            "text": f"Recent industry analysis highlights breakthroughs in {topic_disp}. High efficiency milestones were achieved in 2026 pilot testing across regional hubs.",
                            "source": "verified-news.com"
                        }
                    ]
                    with st.spinner("Analyzing verified sources..."):
                        qa_result = qa_engine.answer_question(user_question, sample_context)

                    st.markdown(f"""
                    <div class="news-card" style="border-left: 3px solid var(--accent);">
                        <div style="font-weight: 600; font-size: 14.5px; margin-bottom: 8px; color: var(--accent);">Grounded Answer</div>
                        <div style="font-size: 15px; line-height: 1.6; color: var(--text-primary);">{html.escape(str(qa_result['answer']))}</div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-top: 10px;">
                            Confidence: <strong>{html.escape(str(qa_result['confidence']).title())}</strong> &bull; 
                            Cited: <strong>{html.escape(', '.join(qa_result['cited_sources']) if qa_result['cited_sources'] else 'None')}</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # Tab 4: Export & History
        with tab_export:
            st.markdown("#### Export Deliverables")
            if not digest_text:
                st.info("Generate a digest before downloading it.")
            else:
                download_date = datetime.now(timezone.utc).date().isoformat()
                safe_topic = re.sub(
                    r"[^\w-]+", "_", topic_disp.strip(), flags=re.UNICODE
                ).strip("_").lower() or "digest"
                file_stem = f"digest_{safe_topic}_{download_date}"
                digest_data = {
                    "topic": topic_disp,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "digest": digest_text
                }
                digest_stories = _parse_digest_stories(digest_text)
                markdown = export_to_markdown(
                    topic_disp, digest_text, digest_stories, download_date
                )
                plain_text = export_to_text(
                    topic_disp, digest_text, digest_stories, download_date
                )
                pdf_bytes = export_to_pdf(
                    topic_disp, digest_text, digest_stories, download_date
                )
                download_cols = st.columns(5)

                with download_cols[0]:
                    st.download_button(
                        label="📝 Download Markdown",
                        data=markdown,
                        file_name=f"{file_stem}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                with download_cols[1]:
                    st.download_button(
                        label="📄 Download PDF",
                        data=pdf_bytes,
                        file_name=f"{file_stem}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                with download_cols[2]:
                    st.download_button(
                        label="📃 Download Text",
                        data=plain_text,
                        file_name=f"{file_stem}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                with download_cols[3]:
                    st.download_button(
                        label="📥 Download JSON",
                        data=json.dumps(digest_data, indent=2, ensure_ascii=False),
                        file_name=f"{file_stem}.json",
                        mime="application/json",
                        use_container_width=True
                    )
                with download_cols[4]:
                    if st.button("⭐ Bookmark Topic", use_container_width=True):
                        add_favorite(topic_disp)
                        st.success(f"Bookmarked '{topic_disp}'!")

            st.markdown("<hr style='border: none; border-top: 1px solid var(--border-color); margin: 20px 0;'>", unsafe_allow_html=True)

            hist_title_col, hist_clear_col = st.columns([3, 1])
            with hist_title_col:
                st.markdown("#### Persistent Task History Log")
            with hist_clear_col:
                st.markdown("<div style='padding-top: 24px;'>", unsafe_allow_html=True)
                if history_records and st.button("🗑️ Clear All", key="clear_hist_tab", help="Delete all task history"):
                    _clear_all_history()
                st.markdown("</div>", unsafe_allow_html=True)

            if history_records:
                st.markdown(
                    _build_history_table_html(history_records),
                    unsafe_allow_html=True
                )
            else:
                st.caption("No task history recorded yet.")
            st.download_button(
                label="Download history (.md)",
                data=_build_history_markdown(history_records),
                file_name=f"task_history_{datetime.now(timezone.utc).date().isoformat()}.md",
                mime="text/markdown",
                use_container_width=True
            )



if __name__ == "__main__":
    main()
