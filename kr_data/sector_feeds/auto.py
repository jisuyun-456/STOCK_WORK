"""
Auto sector feed — 자동차.
Key indicators: US auto sales trend, UAW strike risk.
Data requires BEA/WardsAuto subscription for reliable figures.
"""
import logging

import pandas as pd

logger = logging.getLogger("kr_data.sector.auto")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        us_auto_sales_trend: None   — US auto SAAR trend (WardsAuto/BEA — paid/delayed)
        uaw_strike_risk: bool       — UAW/labor strike risk flag (default False)
        source: str
    """
    try:
        logger.warning(
            "Auto sector data (US auto sales SAAR) requires paid sources "
            "(WardsAuto, BEA FRED). Returning None for paid indicators."
        )
        return {
            "us_auto_sales_trend": None,
            "uaw_strike_risk": False,
            "source": "web",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    Returns 0.0 when paid data is unavailable.

    Future rules (when data available):
        us_auto_sales_trend > 1.03  → +0.3  (SAAR above 3% growth)
        uaw_strike_risk == True     → -0.2  (labor risk discount)
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        sales_trend = snap.get("us_auto_sales_trend")
        strike_risk = snap.get("uaw_strike_risk", False)

        if sales_trend is None:
            logger.warning(
                "compute_sector_score: No auto sales data (paid source required). "
                "Returning neutral score 0.0."
            )
            base = 0.0
        else:
            base = 0.0
            if sales_trend > 1.03:
                base += 0.3
            elif sales_trend < 0.97:
                base -= 0.2

        if strike_risk:
            base -= 0.2

        return _clamp(base)

    except Exception as exc:
        logger.error("compute_sector_score failed: %s", exc)
        return 0.0


def fetch_historical(start: str, end: str) -> pd.DataFrame:
    """
    Historical data for backtesting.
    Returns empty DataFrame (stub — paid source required).
    """
    logger.warning(
        "fetch_historical: auto historical data requires paid sources. "
        "Returning empty DataFrame."
    )
    return pd.DataFrame()
