"""
Tool 2: extract_article
Extracts readable text from URLs using trafilatura with strict timeouts,
fallback to search snippets, and untrusted delimiter sandboxing.
"""
from urllib.request import Request, urlopen
from typing import Dict, Any, Optional
from src.config import config
from src.logger import logger

MAX_HTML_BYTES = 2 * 1024 * 1024


def extract_article(
    url: str,
    story_id: str = "1",
    fallback_snippet: str = "",
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """
    Extract readable text and published date from a URL.
    Falls back gracefully to search snippet if URL fetch fails or is empty.

    Args:
        url: The web page URL to extract.
        story_id: Unique ID string for this candidate (e.g. '1', '2').
        fallback_snippet: Snippet from search result to use if fetch fails.
        timeout: Request timeout in seconds.

    Returns:
        Dict containing:
        {
            "story_id": str,
            "url": str,
            "text": str,                      # Extracted text wrapped in security tags
            "published_date": str,            # Date extracted or fallback
            "is_fallback": bool,              # True if snippet fallback was used
            "status": "extracted" | "fallback" | "failed"
        }
    """
    effective_timeout = timeout or config.request_timeout

    try:
        import trafilatura
    except ImportError:
        # Fallback if trafilatura is not installed
        return _make_fallback_result(story_id, url, fallback_snippet, "trafilatura not installed")

    try:
        request = Request(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
)

        with urlopen(request, timeout=effective_timeout) as response:
            downloaded = response.read(MAX_HTML_BYTES + 1)[:MAX_HTML_BYTES].decode(
                "utf-8",
                errors="replace"
            )
        if not downloaded:
            logger.log_error(0, "extract_article", f"Fetch returned empty HTML for {url}. Using snippet fallback.")
            return _make_fallback_result(story_id, url, fallback_snippet, "empty HTML")

        # Extract main text
        extracted_text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False
        )

        # Extract metadata for date if needed
        metadata = trafilatura.extract_metadata(downloaded)
        extracted_date = metadata.date if metadata and metadata.date else ""

        if not extracted_text or len(extracted_text.strip()) < 80:
            logger.log_error(0, "extract_article", f"Extracted text too short for {url}. Using snippet fallback.")
            return _make_fallback_result(story_id, url, fallback_snippet, "text too short or paywalled", extracted_date)

        # Truncate to safe length (approx 1,500 words / 6,000 characters)
        truncated_text = extracted_text.strip()[:6000]

        # Wrap in unambiguous security delimiters (PRD 7.5: Fetched text is data, never instructions)
        sandboxed_content = (
            f"<article_data id=\"{story_id}\" url=\"{url}\">\n"
            f"{truncated_text}\n"
            f"</article_data>"
        )

        return {
            "story_id": story_id,
            "url": url,
            "text": sandboxed_content,
            "published_date": extracted_date,
            "is_fallback": False,
            "status": "extracted"
        }

    except Exception as e:
        logger.log_error(0, "extract_article", f"Extraction failed for {url}: {e}. Using snippet fallback.")
        return _make_fallback_result(story_id, url, fallback_snippet, str(e))


def _make_fallback_result(
    story_id: str,
    url: str,
    snippet: str,
    reason: str,
    date: str = ""
) -> Dict[str, Any]:
    """Helper to build standard snippet fallback response."""
    safe_snippet = snippet.strip() if snippet else "No snippet available."
    flagged_text = (
        f"<article_data id=\"{story_id}\" url=\"{url}\" note=\"summary based on snippet only\">\n"
        f"{safe_snippet}\n"
        f"</article_data>"
    )
    return {
        "story_id": story_id,
        "url": url,
        "text": flagged_text,
        "published_date": date,
        "is_fallback": True,
        "status": "fallback" if snippet else "failed"
    }

