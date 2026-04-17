"""
Chemical sector feed — 화학.
Key indicators: ethylene-naphtha spread, BDI trend.
Both require paid/subscription data sources.
"""
import logging

import pandas as pd

logger = logging.getLogger("kr_data.sector.chemical")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_bdi_trend() -> None:
    """
    Baltic Dry Index trend — requires paid subscription (Baltic Exchange).
    Free proxy endpoints are unreliable. Returns None.
    """
    logger.debug(
        "BDI data requires Baltic Exchange subscription. Returning None."
    )
    return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        ethylene_naphtha_spread: None  — Ethylene-naphtha margin (ICIS/Platts — paid)
        bdi_trend: None                — BDI ratio vs SMA20 (Baltic Exchange — paid)
        source: str
    """
    try:
        logger.warning(
            "Chemical sector data (ethylene-naphtha spread, BDI) requires paid sources "
            "(ICIS, Platts, Baltic Exchange). Returning None for paid indicators."
        )
        return {
            "ethylene_naphtha_spread": None,
            "bdi_trend": None,
            "source": "web_proxy",
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

        spread = snap.get("ethylene_naphtha_spread")
        bdi = snap.get("bdi_trend")

        if spread is None and bdi is None:
            logger.warning(
                "compute_sector_score: No chemical data available (paid source required). "
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
        "fetch_historical: chemical historical data requires paid sources. "
        "Returning empty DataFrame."
    )
    return pd.DataFrame()
