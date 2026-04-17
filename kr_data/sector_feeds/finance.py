"""
Finance sector feed — 금융 (Banks, Insurance, Securities).
Key indicators: NIM trend, household debt growth.
Data: BOK ECOS API (requires free registration) as source.
"""
import logging

import pandas as pd

logger = logging.getLogger("kr_data.sector.finance")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_nim_trend() -> None:
    """
    Net Interest Margin trend from BOK ECOS.
    Requires ECOS API key registration at https://ecos.bok.or.kr/
    Returns None until API key is configured.
    """
    logger.debug(
        "NIM trend data requires BOK ECOS API key. "
        "Register at https://ecos.bok.or.kr/ and set ECOS_API_KEY env var."
    )
    return None


def _fetch_household_debt_growth() -> None:
    """
    Household debt growth rate from BOK ECOS.
    Requires ECOS API key. Returns None until configured.
    """
    logger.debug(
        "Household debt data requires BOK ECOS API key. Returning None."
    )
    return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        nim_trend: None               — NIM YoY change (BOK ECOS — requires API key)
        household_debt_growth: None   — Household debt growth rate (BOK ECOS)
        source: str
    """
    try:
        logger.warning(
            "Finance sector data (NIM trend, household debt growth) requires BOK ECOS API key. "
            "Register at https://ecos.bok.or.kr/ and configure ECOS_API_KEY. "
            "Returning None for ECOS-dependent indicators."
        )
        return {
            "nim_trend": _fetch_nim_trend(),
            "household_debt_growth": _fetch_household_debt_growth(),
            "source": "ecos_proxy",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    Returns 0.0 when data is unavailable.

    Future rules (when ECOS API configured):
        nim_trend > 0.05   → +0.3  (NIM expanding, bank profitability up)
        nim_trend < -0.05  → -0.3  (NIM compressing)
        household_debt_growth > 0.08  → -0.2  (systemic risk)
    """
    try:
        snap = fetch_snapshot()
        if not snap:
            return 0.0

        nim = snap.get("nim_trend")
        debt_growth = snap.get("household_debt_growth")

        if nim is None and debt_growth is None:
            logger.warning(
                "compute_sector_score: No finance data (ECOS API key required). "
                "Returning neutral score 0.0."
            )
            return 0.0

        base = 0.0
        if nim is not None:
            if nim > 0.05:
                base += 0.3
            elif nim < -0.05:
                base -= 0.3

        if debt_growth is not None and debt_growth > 0.08:
            base -= 0.2

        return _clamp(base)

    except Exception as exc:
        logger.error("compute_sector_score failed: %s", exc)
        return 0.0


def fetch_historical(start: str, end: str) -> pd.DataFrame:
    """
    Historical data for backtesting.
    Returns empty DataFrame (stub — ECOS API required).
    """
    logger.warning(
        "fetch_historical: finance historical data requires BOK ECOS API. "
        "Returning empty DataFrame."
    )
    return pd.DataFrame()
