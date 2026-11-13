"""
Tool 1: search_news
Integrates with Tavily News Search API with date filters and plain Python retry loop.
"""

import time
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from src.config import config
from src.logger import logger


def map_time_range(time_range: str) -> str:
    """
    Map time_range to Tavily date filter string:
    '24h' -> 'd', '7d' -> 'w', '30d' -> 'm'. Default is 'w'.
    """
    cleaned = (time_range or "7d").strip().lower()
    mapping = {
        "24h": "d",
        "1d": "d",
        "7d": "w",
        "1w": "w",
        "30d": "m",
        "1m": "m"
    }
    return mapping.get(cleaned, "w")


def extract_domain(url: str) -> str:
    """Extract domain name from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


def search_news(
    query: str,
    time_range: str = "7d",
    max_results: int = 10,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search recent news articles using Tavily API with retry logic and domain filtering.

    Args:
        query: The search query string.
        time_range: '24h', '7d', or '30d'.
        max_results: Maximum results to retrieve from the API.
        api_key: Optional Tavily API key override.

    Returns:
        List of normalized candidate story dictionaries:
        [{
            "title": str,
            "url": str,
            "snippet": str,
            "source": str,
            "published_date": str
        }]
    """
    active_key = api_key or config.tavily_api_key
    if not active_key:
        raise ValueError(
            "Tavily API key is missing. Set TAVILY_API_KEY in your .env file or environment."
        )

    tavily_date_filter = map_time_range(time_range)
    max_retries = 3
    backoff_factor = 1.5

    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            # We import TavilyClient here so module loads even if dependency installation is deferred
            try:
                from tavily import TavilyClient
            except ImportError:
                raise ImportError(
                    "tavily-python is not installed. Run 'pip install tavily-python' to install it."
                )

            client = TavilyClient(api_key=active_key)
            response = client.search(
                query=query,
                topic="news",
                days=1 if tavily_date_filter == "d" else (7 if tavily_date_filter == "w" else 30),
                max_results=max_results,
                include_raw_content=False
            )

            raw_results = response.get("results", [])
            normalized_results: List[Dict[str, Any]] = []

            for item in raw_results:
                url = item.get("url", "").strip()
                if not url:
                    continue

                # Filter against blocklist
                if config.is_domain_blocked(url):
                    continue

                domain = extract_domain(url)
                title = item.get("title", "").strip() or "Untitled Story"
                snippet = item.get("content", "").strip() or item.get("snippet", "").strip()
                published_date = item.get("published_date", "") or item.get("date", "")

                normalized_results.append({
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "source": domain,
                    "published_date": str(published_date).strip()
                })

            return normalized_results

        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                sleep_time = backoff_factor ** attempt
                logger.log_error(0, "search_news", f"Attempt {attempt} failed: {e}. Retrying in {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            else:
                logger.log_error(0, "search_news", f"All {max_retries} attempts failed: {e}")

    raise RuntimeError(f"search_news failed after {max_retries} retries: {last_exception}")

