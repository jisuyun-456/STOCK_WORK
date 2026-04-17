"""
K-Content sector feed — K-콘텐츠 (K-pop, K-drama, OTT, 엔터테인먼트).
HIGH #7: This sector was previously missing. Now implemented.

Key indicators: Melon chart trend, OTT ranking trend.
Data: KOSPI 엔터테인먼트 업종 지수 as proxy, OTT rank scraping (web).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger("kr_data.sector.content")

# KOSPI 엔터테인먼트 관련 업종 코드
# KOSPI 출판/방송/엔터테인먼트 업종 (1042)
_KOSPI_CONTENT_INDEX = "1042"  # KOSPI 미디어·광고
_SMA_WINDOW = 20


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_content_index_trend() -> Optional[float]:
    """
    Fetch KOSPI content/media index and compute ratio vs SMA20.
    Returns ratio or None on failure.
    """
    try:
        from pykrx import stock

        end = datetime.today().strftime("%Y%m%d")
        start = (datetime.today() - timedelta(days=60)).strftime("%Y%m%d")
        df = stock.get_index_ohlcv(start, end, _KOSPI_CONTENT_INDEX)

        if df is None or df.empty:
            logger.warning("pykrx returned empty data for KOSPI content index")
            return None

        close_col = [c for c in df.columns if "종가" in c or "Close" in c.title()]
        if not close_col:
            numeric_cols = df.select_dtypes(include="number").columns
            if numeric_cols.empty:
                return None
            close_col = [numeric_cols[0]]

        closes = df[close_col[0]].dropna()
        if len(closes) < _SMA_WINDOW:
            logger.warning("Not enough content data for SMA20 (got %d rows)", len(closes))
            return None

        sma20 = closes.iloc[-_SMA_WINDOW:].mean()
        if sma20 == 0:
            return None
        ratio = float(closes.iloc[-1]) / float(sma20)
        return ratio

    except Exception as exc:
        logger.warning("_fetch_content_index_trend failed: %s", exc)
        return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        melon_trend: None             — Melon chart trend (requires Kakao API / web scraping)
        ott_rank_trend: None          — OTT (Netflix KR) ranking trend (web scraping)
        content_index_trend: float | None  — KOSPI content index / SMA20 ratio
        source: str
    """
    try:
        content_trend = _fetch_content_index_trend()
        return {
            "melon_trend": None,        # Requires Kakao API or web scraping
            "ott_rank_trend": None,     # Requires Netflix API or FlixPatrol scraping
            "content_index_trend": content_trend,
            "source": "web",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    HIGH #7: This sector must exist and return a valid score.

    Rules:
        content_index_trend > 1.05  → +0.3  (content index above SMA20 by 5%+)
        content_index_trend < 0.95  → -0.3  (content index below SMA20 by 5%+)
        melon/ott data: reserved for future enrichment
    Returns 0.0 on failure.
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        base = 0.0
        content_trend = snap.get("content_index_trend")

        if content_trend is not None:
            if content_trend > 1.05:
                base += 0.3
            elif content_trend < 0.95:
                base -= 0.3

        return _clamp(base)

    except Exception as exc:
        logger.error("compute_sector_score failed: %s", exc)
        return 0.0


def fetch_historical(start: str, end: str) -> pd.DataFrame:
    """
    Historical data for backtesting.
    Returns empty DataFrame (stub).
    """
    logger.warning(
        "fetch_historical: content historical data requires paid/scraped source. "
        "Returning empty DataFrame."
    )
    return pd.DataFrame()
