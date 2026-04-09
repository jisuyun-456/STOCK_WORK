"""New York Times RSS news source adapter."""

from __future__ import annotations

from news.sources.base import NewsSource
from news.sources.rss import parse_rss_feed


class NYTSource(NewsSource):
    name = "nyt"
    rss_urls = [
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    ]
    paywall_domains = ["www.nytimes.com"]  # Paywall — use description only
    rate_limit_seconds = 1.0

    def fetch(self, max_articles: int = 20) -> list[dict]:
        articles: list[dict] = []

        for url in self.rss_urls:
            items = parse_rss_feed(url)
            for item in items[:max_articles]:
                # NYT is paywalled; RSS description is the best we get for free
                body = item.get("description", "")

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
