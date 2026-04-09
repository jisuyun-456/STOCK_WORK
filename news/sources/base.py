"""Abstract base class for news source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod

import requests

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_BODY_MAX_CHARS = 3000
_REQUEST_TIMEOUT = 10


class NewsSource(ABC):
    """Abstract base for all news source adapters."""

    name: str = ""
    rss_urls: list[str] = []
    paywall_domains: list[str] = []
    rate_limit_seconds: float = 0.5

    @abstractmethod
    def fetch(self, max_articles: int = 20) -> list[dict]:
        """Fetch articles from this source.

        Returns:
            [{"title", "body", "url", "published", "source"}, ...]
        """

    def _scrape_body(self, url: str, max_chars: int = _BODY_MAX_CHARS) -> str:
        """Scrape article body from URL. Returns "" on any failure."""
        if not _BS4_AVAILABLE or not url:
            return ""

        # Skip known paywall domains
        for domain in self.paywall_domains:
            if domain in url:
                return ""

        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception:
            return ""

        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            body = self._extract_body(soup)
            return body[:max_chars]
        except Exception:
            return ""

    def _extract_body(self, soup: BeautifulSoup) -> str:
        """Extract article body from parsed HTML. Override for source-specific logic."""
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
        else:
            paragraphs = soup.find_all("p")
        return " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
