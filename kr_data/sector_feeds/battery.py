"""
Battery sector feed — 이차전지 (2차전지 / EV Battery).
HIGH #12: China PMI influences battery score.
China PMI fetched from public NBS source; graceful fallback to None.
"""
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger("kr_data.sector.battery")


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _fetch_china_pmi() -> Optional[float]:
    """
    Fetch China NBS Manufacturing PMI from public sources.
    Tries multiple fallback endpoints.
    Returns float PMI value, or None on failure.

    This function is intentionally separate (module-level) so tests can patch it:
        with patch.object(battery, '_fetch_china_pmi', return_value=52.5):
    """
    # Attempt 1: Try FRED (St. Louis Fed) China PMI series via public URL
    try:
        import requests

        # FRED does not require API key for some series via their public JSON endpoint
        # China NBS Manufacturing PMI is available as CHPMINDXM on FRED
        fred_url = (
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CHPMINDXM"
        )
        resp = requests.get(fred_url, timeout=8)
        if resp.status_code == 200 and resp.text.strip():
            lines = resp.text.strip().split("\n")
            # CSV: date,value — take last non-empty data row
            for line in reversed(lines[1:]):  # skip header
                parts = line.strip().split(",")
                if len(parts) == 2 and parts[1] not in ("", "."):
                    pmi_val = float(parts[1])
                    logger.info("China PMI from FRED: %.1f", pmi_val)
                    return pmi_val
    except Exception as exc:
        logger.debug("FRED PMI fetch failed: %s", exc)

    # Attempt 2: Stooq public CSV for China PMI proxy
    try:
        import requests

        stooq_url = "https://stooq.com/q/d/l/?s=chnpmim.mo&i=m"
        resp = requests.get(stooq_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and resp.text.strip():
            lines = resp.text.strip().split("\n")
            for line in reversed(lines[1:]):
                parts = line.strip().split(",")
                if len(parts) >= 5 and parts[4] not in ("", "null"):
                    pmi_val = float(parts[4])  # Close column
                    logger.info("China PMI from Stooq: %.1f", pmi_val)
                    return pmi_val
    except Exception as exc:
        logger.debug("Stooq PMI fetch failed: %s", exc)

    logger.warning(
        "China PMI unavailable from all public sources. "
        "Consider a paid data subscription for reliable PMI data."
    )
    return None


def _fetch_ev_sales_trend() -> Optional[float]:
    """
    EV sales trend proxy — returns None (paid data source).
    Placeholder for future integration.
    """
    logger.debug("EV sales trend requires paid data source. Returning None.")
    return None


def fetch_snapshot() -> dict:
    """
    Current state snapshot.
    Returns {} on total failure.

    Keys:
        lithium_spot_cny: None   — Lithium spot price (paid: SMM/Fastmarkets)
        china_pmi: float | None  — China NBS Manufacturing PMI
        ev_sales_trend: None     — EV sales YoY trend (paid)
        source: str
    """
    try:
        china_pmi = _fetch_china_pmi()
        ev_sales_trend = _fetch_ev_sales_trend()
        return {
            "lithium_spot_cny": None,   # Requires paid source (SMM/Fastmarkets)
            "china_pmi": china_pmi,
            "ev_sales_trend": ev_sales_trend,
            "source": "web",
        }
    except Exception as exc:
        logger.error("fetch_snapshot failed: %s", exc)
        return {}


def compute_sector_score() -> float:
    """
    Normalized sector score -1.0 ~ +1.0.
    HIGH #12: China PMI is the primary driver.

    Rules:
        china_pmi > 50.0 (expansion)  → +0.25
        china_pmi < 49.0 (contraction) → -0.25
        49.0 <= china_pmi <= 50.0      → 0.0 (neutral)
    Returns 0.0 on failure.
    """
    try:
        pmi = _fetch_china_pmi()
        base = 0.0

        if pmi is not None:
            if pmi > 50.0:
                base += 0.25
            elif pmi < 49.0:
                base -= 0.25

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
        "fetch_historical: battery historical data requires paid source. Returning empty DataFrame."
    )
    return pd.DataFrame()
