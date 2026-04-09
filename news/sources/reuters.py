"""Reuters RSS news source adapter."""

from __future__ import annotations

from news.sources.base import NewsSource
from news.sources.rss import parse_rss_feed


class ReutersSource(NewsSource):
    name = "reuters"
    rss_urls = [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/USmarkets",
    ]
    paywall_domains: list[str] = []
    rate_limit_seconds = 1.0

    def fetch(self, max_articles: int = 20) -> list[dict]:
        articles: list[dict] = []
        per_feed = max(5, max_articles // len(self.rss_urls))

        for url in self.rss_urls:
            items = parse_rss_feed(url)
            for item in items[:per_feed]:
                body = item.get("description", "")
                # Reuters often blocks body scraping; use description as body
                if not body:
                    body = self._scrape_body(item.get("url", ""))

                articles.append({
                    "title": item.get("title", ""),
                    "body": body,
                    "url": item.get("url", ""),
                    "published": item.get("published", ""),
                    "source": self.name,
                })

            if len(articles) >= max_articles:
                break

        return articles[:max_articles]
