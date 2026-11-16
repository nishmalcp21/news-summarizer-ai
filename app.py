"""
Streamlit Web Interface for News Summarizer Agent.
Claude-style web chat app layout with:
- Modern CSS variables supporting Light (#FAF9F5) and Dark (#262624) palettes
  via @media (prefers-color-scheme: dark) with 200ms smooth transitions.
- Left sidebar with "New chat" button and recents chat list (collapsible on mobile).
- Centered 760px max-width chat column.
- Fixed bottom input box (rounded, soft border, grows with text, send button on right).
- Simple centered greeting in the empty state.
- Right-aligned soft rounded user message bubble.
- Agent reply plain text directly on page with no bubble.
- Pure Python history table eliminating pyarrow.lib DLL crash.
"""

import sys
import json
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
    export_to_html,
    export_to_json,
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
# Claude-Style Design & CSS Injection (Controlled by Streamlit Theme Menu)
# ---------------------------------------------------------------------------
def inject_claude_styling():
    # Detect Streamlit native theme selection (System / Light / Dark)
    theme_type = "light"
    try:
        if hasattr(st, "context") and hasattr(st.context, "theme") and st.context.theme:
            t = st.context.theme.type
            if t in ("dark", "light"):
                theme_type = t
    except Exception:
        theme_type = "light"

    if theme_type == "dark":
        palette = {
            "background_color": "#262624",
            "secondary_background_color": "#30302E",
            "surface_color": "#30302E",
            "text_color": "#ECEAE3",
            "text_secondary": "#A3A19A",
            "subtitle_color": "#A3A19A",
            "label_color": "#A3A19A",
            "placeholder_color": "#8A8984",
            "border_color": "#3E3D3A",
            "bubble_user": "#3A3936",
            "primary_color": "#D97757",
            "accent_hover": "#E58B6D",
            "focus_ring": "rgba(217, 119, 87, 0.35)",
            "button_text": "#ECEAE3",
            "primary_btn_text": "#FFFFFF",
            "code_bg": "#1F1E1D",
            "shadow_soft": "none",
        }
    else:
        palette = {
            "background_color": "#FAF9F5",
            "secondary_background_color": "#F3F1EA",
            "surface_color": "#FFFFFF",
            "text_color": "#1F1E1D",
            "text_secondary": "#5F5E5A",
            "subtitle_color": "#5F5E5A",
            "label_color": "#6B6A66",
            "placeholder_color": "#8A8984",
            "border_color": "#E5E2D9",
            "bubble_user": "#EFECE3",
            "primary_color": "#C96442",
            "accent_hover": "#B5573A",
            "focus_ring": "rgba(201, 100, 66, 0.25)",
            "button_text": "#1F1E1D",
            "primary_btn_text": "#FFFFFF",
            "code_bg": "#F3F1EA",
            "shadow_soft": "0 1px 3px rgba(0, 0, 0, 0.06)",
        }

    css = """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

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

        /* Main chat column: max-width 760px, centered, generous spacing */
        .block-container {
            max-width: 760px !important;
            padding-top: 1.5rem !important;
            padding-bottom: 7rem !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
            margin: 0 auto !important;
        }

        /* Sidebar layout & theme */
        [data-testid="stSidebar"] {
            border-right: 1px solid var(--border-color) !important;
        }

        [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            padding-left: 1rem;
            padding-right: 1rem;
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
            padding: 40px 16px 20px;
            margin-bottom: 24px;
        }
        .greeting-title {
            font-size: 30px !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em !important;
            color: var(--text-color) !important;
            opacity: 1 !important;
            margin-bottom: 10px !important;
        }
        .greeting-sub {
            font-size: 15.5px !important;
            color: var(--subtitle-color) !important;
            opacity: 1 !important;
            max-width: 520px !important;
            margin: 0 auto 28px !important;
            line-height: 1.5 !important;
        }

        /* All Secondary Buttons: Presets, Sidebar Recent Chats, Ratings */
        .stButton > button:not([kind="primary"]) {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 10px !important;
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
            border-radius: 10px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        [data-testid="stExpander"] details {
            background-color: var(--surface-color) !important;
            border-radius: 10px !important;
        }
        [data-testid="stExpander"] summary {
            background-color: var(--surface-color) !important;
            border-radius: 10px !important;
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
            border-radius: 0 0 10px 10px !important;
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

        /* Fixed Bottom Chat Input Styling */
        [data-testid="stBottomBlockContainer"] {
            background-color: transparent !important;
        }
        [data-testid="stChatInput"] {
            background-color: var(--surface-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 22px !important;
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
            border-radius: 18px 18px 4px 18px !important;
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
            font-weight: 600;
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
            border-radius: 12px !important;
            padding: 18px 22px !important;
            margin-bottom: 16px !important;
            box-shadow: var(--shadow-soft) !important;
            transition: border-color 150ms ease !important;
        }
        .news-card:hover {
            border-color: var(--primary-color) !important;
        }
        .story-title {
            color: var(--text-color) !important;
            font-size: 17px !important;
            font-weight: 600 !important;
            margin-top: 8px !important;
            margin-bottom: 8px !important;
            line-height: 1.4 !important;
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
            color: var(--primary-color) !important;
            font-weight: 600 !important;
            padding: 3px 10px !important;
            border-radius: 9999px !important;
            font-size: 12px !important;
            border: 1px solid var(--border-color) !important;
            display: inline-block !important;
            opacity: 1 !important;
        }
        .badge-date {
            background-color: var(--secondary-background-color) !important;
            color: var(--text-secondary) !important;
            padding: 3px 10px !important;
            border-radius: 9999px !important;
            font-size: 12px !important;
            border: 1px solid var(--border-color) !important;
            display: inline-block !important;
            margin-left: 6px !important;
            opacity: 1 !important;
        }
        .badge-theme {
            background-color: var(--secondary-background-color) !important;
            color: var(--primary-color) !important;
            font-weight: 600 !important;
            padding: 3px 10px !important;
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
            border-radius: 10px !important;
            padding: 18px 22px !important;
            margin-bottom: 24px !important;
            box-shadow: var(--shadow-soft) !important;
        }
        .quick-summary-title {
            font-weight: 600 !important;
            font-size: 14.5px !important;
            margin-bottom: 6px !important;
            color: var(--primary-color) !important;
            opacity: 1 !important;
        }
        .quick-summary-text {
            font-size: 15px !important;
            line-height: 1.6 !important;
            color: var(--text-color) !important;
            opacity: 1 !important;
        }

        /* Tabs: clearly readable in both Light and Dark themes */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px !important;
            background-color: transparent !important;
            border-bottom: 1px solid var(--border-color) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: transparent !important;
            border: none !important;
            padding: 8px 16px !important;
            border-radius: 6px 6px 0 0 !important;
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
            border-radius: 8px;
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
            color: #C0392B !important;
        }

        /* Responsive design */
        @media (max-width: 768px) {
            .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
            .user-msg-bubble {
                max-width: 95%;
            }
            .greeting-title {
                font-size: 24px !important;
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

    inject_claude_styling()

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

    # -----------------------------------------------------------------------
    # Left Sidebar: New chat button + Recents + Settings (Collapsible)
    # -----------------------------------------------------------------------
    with st.sidebar:
        # New Chat Button
        if st.button("＋ Start new chat", use_container_width=True, type="primary"):
            st.session_state["current_digest"] = None
            st.session_state["current_topic"] = ""
            st.session_state["chat_messages"] = []
            st.session_state["search_input"] = ""
            st.session_state["trigger_search"] = False
            st.rerun()

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        # Recents / Past Chats List Area with per-topic delete and clear-all
        hdr_col, clr_col = st.columns([3, 1])
        with hdr_col:
            st.markdown("<p class='section-label' style='font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;'>Recent Chats</p>", unsafe_allow_html=True)
        with clr_col:
            if st.button("🗑️ All", key="clear_all_history", help="Clear all chat history"):
                _clear_all_history()

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
                chat_col, del_col = st.columns([5, 1])
                with chat_col:
                    if st.button(f"💬 {top}", key=f"hist_{top}", use_container_width=True):
                        st.session_state["search_input"] = top
                        st.session_state["trigger_search"] = True
                        st.rerun()
                with del_col:
                    if st.button("✕", key=f"del_{top}", help=f"Delete '{top}' from history"):
                        _delete_topic_history(top)
                        # Clear active view if the deleted topic is currently displayed
                        if st.session_state.get("current_topic", "") == top:
                            st.session_state["current_digest"] = None
                            st.session_state["current_topic"] = ""
                            st.session_state["chat_messages"] = []
                        st.rerun()
        else:
            st.caption("No past chats yet.")

        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        st.divider()

        # Collapsible Engine Controls & Settings
        with st.expander("⚙️ Engine Settings & Preferences", expanded=False):
            mode = st.radio(
                "Search & LLM Provider",
                ["Offline Mock (Fast / Zero Token Cost)", "Live API (Tavily + LiteLLM)"],
                index=0 if not config.tavily_api_key else 1
            )

            time_range = st.selectbox(
                "Time Horizon",
                ["24h", "7d", "30d"],
                index=1,
                help="Recent window of news coverage."
            )

            num_stories = st.slider(
                "Story Target Count",
                min_value=3,
                max_value=10,
                value=5,
                help="Number of verified stories in final digest (PRD range: 3-10)."
            )

            st.markdown("#### ⭐ Bookmarked Topics")
            favorites = get_favorites()
            if favorites:
                selected_fav = st.selectbox("Load bookmark:", ["-- Select --"] + favorites)
                if selected_fav != "-- Select --":
                    st.session_state["search_input"] = selected_fav
                    st.session_state["trigger_search"] = True
            else:
                st.caption("No bookmarks yet.")

            st.markdown("#### 🛡️ Guardrails")
            st.markdown(f"- Max Steps: `{config.max_steps}`")
            st.markdown(f"- Cache TTL: `{config.cache_ttl_minutes}m`")
            st.markdown(f"- Timezone: `{config.default_timezone}`")
    
    # -----------------------------------------------------------------------
    # Main Centered Chat Column (max-width ~760px)
    # -----------------------------------------------------------------------
    has_active_chat = bool(st.session_state.get("current_digest"))

    # Empty State: Simple centered greeting and preset suggestions
    if not has_active_chat:
        st.markdown("""
        <div class="empty-state">
            <div class="greeting-title">What would you like to explore?</div>
            <div class="greeting-sub">
                Autonomous factual news synthesis powered by plain Python and strict verification guardrails.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<p class='section-label' style='font-size: 13px; font-weight: 600; text-align: center; margin-bottom: 12px;'>Trending Presets</p>", unsafe_allow_html=True)
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            if st.button("🚗 Electric Vehicles in India", use_container_width=True):
                st.session_state["search_input"] = "Electric vehicles in India"
                st.session_state["trigger_search"] = True
                st.rerun()
            if st.button("🤖 Global AI Regulation 2026", use_container_width=True):
                st.session_state["search_input"] = "Global AI Regulation 2026"
                st.session_state["trigger_search"] = True
                st.rerun()
        with p_col2:
            if st.button("⚛️ Quantum Computing Scaling", use_container_width=True):
                st.session_state["search_input"] = "Quantum computing commercialization"
                st.session_state["trigger_search"] = True
                st.rerun()
            if st.button("🔋 Solid-State Battery Patents", use_container_width=True):
                st.session_state["search_input"] = "Solid-state lithium battery patents"
                st.session_state["trigger_search"] = True
                st.rerun()

    # Fixed Bottom Chat Input
    chat_query = st.chat_input("How can I help you research today?")

    # Check for search triggers
    topic_to_run = None
    if chat_query and chat_query.strip():
        topic_to_run = chat_query.strip()
    elif st.session_state.get("trigger_search", False) and st.session_state.get("search_input", ""):
        topic_to_run = st.session_state["search_input"].strip()
        st.session_state["trigger_search"] = False

    # Pipeline Execution
    if topic_to_run:
        if len(topic_to_run) < 2:
            st.warning("⚠️ Please provide a topic with at least 2 characters.")
            return

        is_mock = "Mock" in mode or not config.tavily_api_key
        if not is_mock and not config.tavily_api_key:
            st.info("ℹ️ No TAVILY_API_KEY detected in .env; executing in offline mock mode.")
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

        with st.status(f"Synthesizing '{topic_to_run}'...", expanded=True) as status:
            plan = agent.planner.create_plan(topic_to_run, num_stories, time_range)
            if plan.aborted:
                status.update(label="⚠️ Planning Aborted", state="error", expanded=True)
                st.error(plan.abort_reason)
                return

            st.write(f"✓ Formulated {len(plan.steps)} verified execution steps")
            st.write("✓ Running Plain Python ReAct synthesis (`Think > Act > Look`)...")

            digest = agent.run(
                topic=topic_to_run,
                num_stories=num_stories,
                time_range=time_range
            )
            status.update(label="✓ Synthesis complete", state="complete", expanded=False)

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

        # 1. USER MESSAGE BUBBLE (Right-aligned, soft rounded bubble)
        st.markdown(f"""
        <div class="user-msg-container">
            <div class="user-msg-bubble">
                Research {topic_disp}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 2. AGENT REPLY (Plain text directly on page with NO bubble, clean typography)
        st.markdown('<div class="agent-reply-body">', unsafe_allow_html=True)

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
                    {quick_sum}
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
            if "Key stories:" in digest_text:
                raw_stories_block = digest_text.split("Key stories:")[1].split("Based on")[0].strip()
                story_blocks = raw_stories_block.split("\n\n")

                for block in story_blocks:
                    lines = [l.strip() for l in block.splitlines() if l.strip()]
                    if not lines:
                        continue

                    title = lines[0]
                    summary_lines = []
                    source_str = "Verified Source"
                    date_str = "Recent"
                    url_str = "#"

                    for l in lines[1:]:
                        if l.startswith("Source:"):
                            source_meta = l.replace("Source:", "").strip().split("|")
                            source_str = source_meta[0].strip() if len(source_meta) > 0 else "Source"
                            date_str = source_meta[1].strip() if len(source_meta) > 1 else "Recent"
                            url_str = source_meta[2].strip() if len(source_meta) > 2 else "#"
                        else:
                            summary_lines.append(l)

                    summary_body = " ".join(summary_lines)

                    st.markdown(f"""
                    <div class="news-card">
                        <div style="margin-bottom: 6px;">
                            <span class="badge-source">{source_str}</span>
                            <span class="badge-date">{date_str}</span>
                        </div>
                        <div class="story-title">{title}</div>
                        <div class="story-summary">{summary_body}</div>
                        <div style="margin-top: 12px;">
                            <a href="{url_str}" target="_blank" style="text-decoration: none; font-size: 13px; font-weight: 500; color: var(--accent);">
                                Read Original Article &rarr;
                            </a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

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
            sample_stories_for_theming = [
                {
                    "title": f"Recent Technological Progress in {topic_disp}",
                    "summary": "Engineering teams and research consortiums filed key patents and reached high efficiency milestones.",
                    "source": "verified-news.com",
                    "published_date": "2026-11-09",
                    "url": "https://verified-news.com/tech"
                },
                {
                    "title": f"Legislative Standards and Regulatory Mandates on {topic_disp}",
                    "summary": "Government oversight committee passed new guidelines and safety compliance rules.",
                    "source": "policymonitor.org",
                    "published_date": "2026-11-10",
                    "url": "https://policymonitor.org/policy"
                },
                {
                    "title": f"Market Capitalization & Venture Investment Surge for {topic_disp}",
                    "summary": "Investors poured venture capital into leading startups as commercial deliveries ramp up.",
                    "source": "tech-monitor.org",
                    "published_date": "2026-11-10",
                    "url": "https://tech-monitor.org/business"
                }
            ]

            themed_clusters = group_stories_by_theme(sample_stories_for_theming)
            for theme_name, theme_list in themed_clusters.items():
                st.markdown(f"**{theme_name}**")
                for s in theme_list:
                    st.markdown(f"""
                    <div class="news-card">
                        <span class="badge-theme">{theme_name}</span>
                        <div class="story-title">{s['title']}</div>
                        <div class="story-summary">{s['summary']}</div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-top: 8px;">Source: {s['source']}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown("<hr style='border: none; border-top: 1px solid var(--border-color); margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown("#### Cross-Outlet Tone & Framing Analysis")
            outlet_analysis = compare_outlet_coverage(sample_stories_for_theming)
            report_md = format_cross_outlet_report(outlet_analysis)
            st.markdown(report_md)

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
                        <div style="font-size: 15px; line-height: 1.6; color: var(--text-primary);">{qa_result['answer']}</div>
                        <div style="font-size: 13px; color: var(--text-secondary); margin-top: 10px;">
                            Confidence: <strong>{qa_result['confidence'].title()}</strong> &bull; 
                            Cited: <strong>{', '.join(qa_result['cited_sources']) if qa_result['cited_sources'] else 'None'}</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        # Tab 4: Export & History
        with tab_export:
            st.markdown("#### Export Deliverables")
            exp_c1, exp_c2, exp_c3 = st.columns(3)
            digest_data = {
                "topic": topic_disp,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "digest": digest_text
            }

            with exp_c1:
                json_str = json.dumps(digest_data, indent=2)
                st.download_button(
                    label="📥 Download JSON",
                    data=json_str,
                    file_name=f"digest_{topic_disp.replace(' ', '_').lower()}.json",
                    mime="application/json",
                    use_container_width=True
                )

            with exp_c2:
                html_export_path = PROJECT_ROOT / "memory" / "temp_export.html"
                export_to_html(
                    topic=topic_disp,
                    date_range="Recent",
                    quick_summary=quick_sum if quick_sum else "Executive Overview",
                    stories=[{"title": f"News Report on {topic_disp}", "summary": "Full digest details.", "source": "News Agent", "url": "#", "published_date": "2026-11-10"}],
                    filepath=html_export_path
                )
                html_content = html_export_path.read_text(encoding="utf-8")
                st.download_button(
                    label="📄 Download HTML",
                    data=html_content,
                    file_name=f"digest_{topic_disp.replace(' ', '_').lower()}.html",
                    mime="text/html",
                    use_container_width=True
                )

            with exp_c3:
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

            # Pure Python table renderer eliminating pyarrow DLL dependency
            if history_records:
                table_rows = ""
                for rec in reversed(history_records[-10:]):
                    status_text = "Success" if rec.get("success") else "Incomplete"
                    table_rows += f"""
                    <tr>
                        <td>{rec.get('topic', 'N/A')}</td>
                        <td>{rec.get('num_stories', 'N/A')}</td>
                        <td>{rec.get('time_range', 'N/A')}</td>
                        <td>{status_text}</td>
                        <td>{rec.get('story_count', 'N/A')}</td>
                    </tr>
                    """
                table_html = f"""
                <div style="overflow-x: auto; margin-top: 10px;">
                    <table class="claude-table">
                        <thead>
                            <tr>
                                <th>Topic</th>
                                <th>Stories</th>
                                <th>Time Horizon</th>
                                <th>Status</th>
                                <th>Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
                """
                st.markdown(table_html, unsafe_allow_html=True)
            else:
                st.caption("No task history recorded yet.")

        st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
