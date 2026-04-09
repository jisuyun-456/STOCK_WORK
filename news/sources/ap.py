"""Associated Press RSS news source adapter."""

from __future__ import annotations

from news.sources.base import NewsSource
from news.sources.rss import parse_rss_feed


class APSource(NewsSource):
    name = "ap"
    rss_urls = [
        "https://rsshub.app/apnews/topics/business",
        "https://rsshub.app/apnews/topics/technology",
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
