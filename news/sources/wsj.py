"""Wall Street Journal RSS news source adapter."""

from __future__ import annotations

from news.sources.base import NewsSource
from news.sources.rss import parse_rss_feed


class WSJSource(NewsSource):
    name = "wsj"
    rss_urls = [
        "https://feeds.content.dowjones.io/public/rss/mktw_mktnews",
    ]
    paywall_domains = ["www.wsj.com"]  # Full paywall — description only
    rate_limit_seconds = 1.0

    def fetch(self, max_articles: int = 20) -> list[dict]:
        articles: list[dict] = []

        for url in self.rss_urls:
            items = parse_rss_feed(url)
            for item in items[:max_articles]:
                # WSJ is fully paywalled; only RSS description available
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
