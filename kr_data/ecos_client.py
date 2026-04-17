"""ECOS (Economic Statistics System) client — Bank of Korea open API.

Provides:
  - fetch_base_rate(start, end): BOK base rate time series [HIGH #3]
  - fetch_current_account(start, end): current account balance
  - fetch_money_supply(start, end): M2 money supply

All responses are disk-cached via KRCache with a 6-hour TTL.

HIGH #3 fix: base rate is fetched from the real ECOS API (not hardcoded 3.00%).
If ECOS_API_KEY is not set or the API call fails, functions return None.
"""
import logging
import os
import requests

from kr_data.retry import retry_with_backoff
from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.ecos")
_cache = KRCache()
_ECOS_BASE = "https://ecos.bok.or.kr/api"
_TTL = 3600 * 6  # 6 hours


def _get_api_key() -> str | None:
    return os.environ.get("ECOS_API_KEY")


@retry_with_backoff
def _ecos_get_raw(stat_code: str, cycle: str, start: str, end: str, item_code: str = "") -> list[dict]:
    """Raw ECOS API call. Raises on failure (for retry)."""
    key = _get_api_key()
    if not key:
        raise ValueError("ECOS_API_KEY not set")
    url = (
        f"{_ECOS_BASE}/StatisticSearch/{key}/json/kr/1/100"
        f"/{stat_code}/{cycle}/{start}/{end}/{item_code}"
    )
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("StatisticSearch", {}).get("row", [])


def fetch_base_rate(start: str = "202001", end: str = None) -> "pd.DataFrame | None":
    """BOK base rate (HIGH #3: real API, not hardcoded 3.00%).

    stat_code="722Y001", item_code="0101000", cycle="M" (monthly)

    Parameters
    ----------
    start:
        Start month in "YYYYMM" format. Default "202001".
    end:
        End month in "YYYYMM" format. Default: current month.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns [date, rate] or None if API fails / key missing.
    """
    import pandas as pd
    from datetime import datetime

    end = end or datetime.now().strftime("%Y%m")
    cache_key = f"ecos_base_rate_{start}_{end}"
    cached = _cache.get_df(cache_key, _TTL)
    if cached is not None:
        return cached
    try:
        rows = _ecos_get_raw("722Y001", "M", start, end, "0101000")
        if not rows:
            return None
        df = pd.DataFrame([
            {"date": r["TIME"], "rate": float(r["DATA_VALUE"])}
            for r in rows
        ])
        _cache.set_df(cache_key, df)
        return df
    except Exception as e:
        _logger.warning("fetch_base_rate failed: %s", e)
        return None


def fetch_current_account(start: str = "202001", end: str = None) -> "pd.DataFrame | None":
    """Current account balance.

    stat_code="301Y013", cycle="M"

    Parameters
    ----------
    start:
        Start month in "YYYYMM" format. Default "202001".
    end:
        End month in "YYYYMM" format. Default: current month.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns [date, value_billion_usd] or None.
    """
    import pandas as pd
    from datetime import datetime

    end = end or datetime.now().strftime("%Y%m")
    cache_key = f"ecos_current_account_{start}_{end}"
    cached = _cache.get_df(cache_key, _TTL)
    if cached is not None:
        return cached
    try:
        rows = _ecos_get_raw("301Y013", "M", start, end)
        if not rows:
            return None
        df = pd.DataFrame([
            {"date": r["TIME"], "value_billion_usd": float(r["DATA_VALUE"])}
            for r in rows
        ])
        _cache.set_df(cache_key, df)
        return df
    except Exception as e:
        _logger.warning("fetch_current_account failed: %s", e)
        return None


def fetch_money_supply(start: str = "202001", end: str = None) -> "pd.DataFrame | None":
    """M2 money supply.

    stat_code="101Y004", cycle="M"

    Parameters
    ----------
    start:
        Start month in "YYYYMM" format. Default "202001".
    end:
        End month in "YYYYMM" format. Default: current month.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns [date, m2_billion_krw] or None.
    """
    import pandas as pd
    from datetime import datetime

    end = end or datetime.now().strftime("%Y%m")
    cache_key = f"ecos_m2_{start}_{end}"
    cached = _cache.get_df(cache_key, _TTL)
    if cached is not None:
        return cached
    try:
        rows = _ecos_get_raw("101Y004", "M", start, end)
        if not rows:
            return None
        df = pd.DataFrame([
            {"date": r["TIME"], "m2_billion_krw": float(r["DATA_VALUE"])}
            for r in rows
        ])
        _cache.set_df(cache_key, df)
        return df
    except Exception as e:
        _logger.warning("fetch_money_supply failed: %s", e)
        return None
