"""
Semiconductor sector feed — 반도체.
Proxy: pykrx KOSPI 반도체 지수 (코드 "1028") as SOX trend proxy.
Data: pykrx + web fallback.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger("kr_data.sector.semiconductor")

# KOSPI 반도체 업종 지수 코드 (한국거래소 업종코드)
_KOSPI_SEMI_INDEX = "1028"  # KOSPI 반도체
_SMA_WINDOW = 20


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_sox_trend() -> Optional[float]:
    """
    Fetch KOSPI semiconductor index and compute ratio vs SMA20.
    Returns ratio (e.g. 1.05 means 5% above SMA20), or None on failure.
    """
    try:
        from pykrx import stock

        end = datetime.today().strftime("%Y%m%d")
        start = (datetime.today() - timedelta(days=60)).strftime("%Y%m%d")
        df = stock.get_index_ohlcv(start, end, _KOSPI_SEMI_INDEX)

        if df is None or df.empty:
            logger.warning("pykrx returned empty data for KOSPI semiconductor index")
            return None

        close_col = [c for c in df.columns if "종가" in c or "Close" in c.title()]
        if not close_col:
            # fallback: use first numeric column
            numeric_cols = df.select_dtypes(include="number").columns
            if numeric_cols.empty:
                return None
            close_col = [numeric_cols[0]]

        closes = df[close_col[0]].dropna()
        if len(closes) < _SMA_WINDOW:
            logger.warning("Not enough data for SMA20 (got %d rows)", len(closes))
            return None

        sma20 = closes.iloc[-_SMA_WINDOW:].mean()
        if sma20 == 0:
            return None
        ratio = float(closes.iloc[-1]) / float(sma20)
        return ratio

    except Exception as exc:
        logger.warning("_fetch_sox_trend failed: %s", exc)
        return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot with key indicators.
    Returns {} on failure.

    Keys:
        dram_spot_usd: float | None  — DRAM spot price (USD, paid source → None)
        sox_trend: float | None      — KOSPI semi index / SMA20 ratio
        hbm_backlog: None            — HBM backlog (paid source)
        source: str
    """
    try:
        sox_trend = _fetch_sox_trend()
        return {
            "dram_spot_usd": None,   # Requires paid data source (DRAMeXchange)
            "sox_trend": sox_trend,
            "hbm_backlog": None,     # Requires paid data source
            "source": "pykrx+web",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    Rules:
        +0.3 if sox_trend > 1.05 (KOSPI semi index above SMA20 by 5%+)
        +0.2 if dram_spot_usd > 3.0 (currently always None → skipped)
    Returns 0.0 on failure.
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        base = 0.0
        sox_trend = snap.get("sox_trend")
        dram_spot_usd = snap.get("dram_spot_usd")

        if sox_trend is not None and sox_trend > 1.05:
            base += 0.3

        if dram_spot_usd is not None and dram_spot_usd > 3.0:
            base += 0.2

        return _clamp(base)

    except Exception as exc:
        logger.error("compute_sector_score failed: %s", exc)
        return 0.0


def fetch_historical(start: str, end: str) -> pd.DataFrame:
    """
    Historical data for backtesting.
    Returns empty DataFrame (real data requires paid source).
    """
    logger.warning(
        "fetch_historical: semiconductor historical data requires paid source. Returning empty DataFrame."
    )
    return pd.DataFrame()
