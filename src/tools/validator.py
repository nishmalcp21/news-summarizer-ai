"""
Tool 3: validate_link
Validates URL reachability (HTTP HEAD/GET check) and checks against domain blocklist.
"""

from typing import Optional
from urllib.parse import urlparse
import urllib.request
from src.config import config
from src.logger import logger


def validate_link(url: str, timeout: Optional[float] = None) -> bool:
    """
    Validates that a URL is well-formed, not on the blocklist, and reachable over HTTP/HTTPS.

    Args:
        url: The web URL to validate.
        timeout: Timeout in seconds for the probe.

    Returns:
        True if the link is reachable and permitted, False otherwise.
    """
    if not url or not isinstance(url, str):
        return False

    cleaned_url = url.strip()

    # 1. Check scheme
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in ("http", "https"):
        return False

    # 2. Check blocklist
    if config.is_domain_blocked(cleaned_url):
        logger.log_safety(f"URL domain is on the blocklist: {cleaned_url}")
        return False

    # 3. HTTP Reachability probe
    effective_timeout = timeout or config.request_timeout

    # Try httpx first if available, else urllib
    try:
        import httpx
        with httpx.Client(timeout=effective_timeout, follow_redirects=True) as client:
            try:
                response = client.head(cleaned_url)
                if response.status_code < 400:
                    return True
            except httpx.RequestError:
                pass

            # Some servers block HEAD; fallback to light GET
            response = client.get(cleaned_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            return response.status_code < 400

    except ImportError:
        # Plain standard library urllib fallback
        try:
            req = urllib.request.Request(
                cleaned_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                method="HEAD"
            )
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                return resp.status < 400
        except Exception:
            # Fallback to GET with 1 byte read
            try:
                req = urllib.request.Request(
                    cleaned_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                    return resp.status < 400
            except Exception as e:
                logger.log_error(0, "validate_link", f"Validation failed for {cleaned_url}: {e}")
                return False

