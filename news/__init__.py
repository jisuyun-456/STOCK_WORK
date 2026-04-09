"""News module — yfinance 뉴스 수집 + Gemini 감성 분석."""

from news.fetcher import fetch_news, fetch_macro_news, fetch_all_news
from news.sentiment import SentimentResult, analyze_sentiment, analyze_all_sentiment

__all__ = [
    "fetch_news",
    "fetch_macro_news",
    "fetch_all_news",
    "SentimentResult",
    "analyze_sentiment",
    "analyze_all_sentiment",
]
