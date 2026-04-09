"""News source adapters for RSS-based crawling."""

from news.sources.reuters import ReutersSource
from news.sources.ap import APSource
from news.sources.cnbc import CNBCSource
from news.sources.marketwatch import MarketWatchSource
from news.sources.nyt import NYTSource
from news.sources.wsj import WSJSource

ALL_SOURCES = [
    ReutersSource,
    APSource,
    CNBCSource,
    MarketWatchSource,
    NYTSource,
    WSJSource,
]

__all__ = [
    "ALL_SOURCES",
    "ReutersSource",
    "APSource",
    "CNBCSource",
    "MarketWatchSource",
    "NYTSource",
    "WSJSource",
]
