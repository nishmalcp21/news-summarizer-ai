"""
Core Tools for the News Summarizer Agent in Plain Python.
Includes: search_news, extract_article, validate_link, and manage_memory.
"""

from .search import search_news
from .extractor import extract_article
from .validator import validate_link
from .memory_tool import manage_memory

__all__ = ["search_news", "extract_article", "validate_link", "manage_memory"]

