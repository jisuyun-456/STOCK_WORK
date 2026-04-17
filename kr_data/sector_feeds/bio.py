"""
Bio sector feed — 바이오 (Biotech / Pharma).
Data: pykrx KOSPI 바이오 업종 지수 as BIOS trend proxy.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger("kr_data.sector.bio")

# KOSPI 의약품/바이오 업종 지수 코드
_KOSPI_BIO_INDEX = "1009"  # KOSPI 의약품
_SMA_WINDOW = 20


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_bios_trend() -> Optional[float]:
    """
    Fetch KOSPI bio/pharma index and compute ratio vs SMA20.
    Returns ratio (e.g. 1.03 means 3% above SMA20), or None on failure.
    """
    try:
        from pykrx import stock

        end = datetime.today().strftime("%Y%m%d")
        start = (datetime.today() - timedelta(days=60)).strftime("%Y%m%d")
        df = stock.get_index_ohlcv(start, end, _KOSPI_BIO_INDEX)

        if df is None or df.empty:
            logger.warning("pykrx returned empty data for KOSPI bio index")
            return None

        close_col = [c for c in df.columns if "종가" in c or "Close" in c.title()]
        if not close_col:
            numeric_cols = df.select_dtypes(include="number").columns
            if numeric_cols.empty:
                return None
            close_col = [numeric_cols[0]]

        closes = df[close_col[0]].dropna()
        if len(closes) < _SMA_WINDOW:
            logger.warning("Not enough bio data for SMA20 (got %d rows)", len(closes))
            return None

        sma20 = closes.iloc[-_SMA_WINDOW:].mean()
        if sma20 == 0:
            return None
        ratio = float(closes.iloc[-1]) / float(sma20)
        return ratio

    except Exception as exc:
        logger.warning("_fetch_bios_trend failed: %s", exc)
        return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        fda_pdufa_count_30d: None  — FDA PDUFA decisions in next 30d (paid/web scraping)
        bios_trend: float | None   — KOSPI bio index / SMA20 ratio
        source: str
    """
    try:
        bios_trend = _fetch_bios_trend()
        return {
            "fda_pdufa_count_30d": None,  # Requires web scraping of FDA calendar
            "bios_trend": bios_trend,
            "source": "web",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    Rules:
        bios_trend > 1.05  → +0.3  (bio index above SMA20 by 5%+)
        bios_trend < 0.95  → -0.3  (bio index below SMA20 by 5%+)
    Returns 0.0 on failure.
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        base = 0.0
        bios_trend = snap.get("bios_trend")

        if bios_trend is not None:
            if bios_trend > 1.05:
                base += 0.3
            elif bios_trend < 0.95:
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
        "fetch_historical: bio historical data requires paid source. Returning empty DataFrame."
    )
    return pd.DataFrame()
