"""MarketWatch RSS news source adapter."""

from __future__ import annotations

from news.sources.base import NewsSource
from news.sources.rss import parse_rss_feed


class MarketWatchSource(NewsSource):
    name = "marketwatch"
    rss_urls = [
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    ]
    paywall_domains = ["www.marketwatch.com"]  # Some articles are paywalled
    rate_limit_seconds = 1.0

    def fetch(self, max_articles: int = 20) -> list[dict]:
        articles: list[dict] = []
        per_feed = max(5, max_articles // len(self.rss_urls))

        for url in self.rss_urls:
            items = parse_rss_feed(url)
            for item in items[:per_feed]:
                # MarketWatch descriptions are usually rich enough
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
