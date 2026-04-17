"""
Shipbuilding sector feed — 조선.
Key indicators: newbuild price index, order backlog (Clarksons — paid source).
Returns 0.0 score when data unavailable.
"""
import logging

import pandas as pd

logger = logging.getLogger("kr_data.sector.shipbuilding")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        newbuild_price_idx: None  — Clarksons newbuild price index (paid)
        order_backlog: None       — Clarksons order backlog in CGT (paid)
        source: str
    Note:
        Clarksons Research requires a paid subscription.
        See: https://www.clarksons.net/
    """
    try:
        logger.warning(
            "Shipbuilding data (Clarksons newbuild price index, order backlog) "
            "requires a paid Clarksons Research subscription. "
            "Returning None for paid indicators."
        )
        return {
            "newbuild_price_idx": None,
            "order_backlog": None,
            "source": "clarksons_proxy",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    Returns 0.0 when paid data is unavailable.
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        newbuild = snap.get("newbuild_price_idx")
        backlog = snap.get("order_backlog")

        if newbuild is None and backlog is None:
            logger.warning(
                "compute_sector_score: No shipbuilding data available (paid source required). "
                "Returning neutral score 0.0."
            )
            return 0.0

        # Future: implement rule-based scoring when data available
        return _clamp(0.0)

    except Exception as exc:
        logger.error("compute_sector_score failed: %s", exc)
        return 0.0


def fetch_historical(start: str, end: str) -> pd.DataFrame:
    """
    Historical data for backtesting.
    Returns empty DataFrame (stub — paid source required).
    """
    logger.warning(
        "fetch_historical: shipbuilding historical data requires Clarksons paid source. "
        "Returning empty DataFrame."
    )
    return pd.DataFrame()
