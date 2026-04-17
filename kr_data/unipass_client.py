"""UNIPASS (Korea Customs Service) export statistics client.

Provides:
  - fetch_semiconductor_export_yoy(): IC (HS 8542) export YoY % [HIGH #4]
  - fetch_export_by_category(hs_code): generic export amount by HS code

All responses are disk-cached via KRCache with a 6-hour TTL.

HIGH #4 fix: semiconductor export YoY fetched from real UNIPASS API (not null).
If UNIPASS_API_KEY is not set or the API call fails, functions return None.
"""
import logging
import os
import requests

from kr_data.retry import retry_with_backoff
from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.unipass")
_cache = KRCache()
_TTL = 3600 * 6  # 6 hours


def _get_api_key() -> str | None:
    return os.environ.get("UNIPASS_API_KEY")


@retry_with_backoff
def _unipass_get_raw(hs_code: str, bgn_dt: str, end_dt: str) -> list[dict]:
    """UNIPASS customs export API. HS code 85** = semiconductor.

    Raises on failure (for retry decorator).
    """
    key = _get_api_key()
    if not key:
        raise ValueError("UNIPASS_API_KEY not set")
    url = "https://unipass.customs.go.kr/ext/rest/expImpStatService/retrieveExpImpStat"
    params = {
        "crkyCn": key,
        "imexTp": "1",      # export
        "strtDt": bgn_dt,
        "endDt": end_dt,
        "hsSgn": hs_code,
        "hsSgnSrt": "6",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", {}).get("data", [])


def fetch_semiconductor_export_yoy() -> "dict | None":
    """Real semiconductor export YoY from UNIPASS (HS 8542 = IC).

    HIGH #4 fix: returns live data from UNIPASS API, not None.

    Returns
    -------
    dict or None
        {"yoy_pct": 12.5, "latest_month": "202603", "source": "unipass"}
        or None if API fails / key missing.
    """
    from datetime import datetime

    cache_key = "unipass_semi_yoy"
    cached = _cache.get(cache_key, _TTL)
    if cached is not None:
        return cached
    try:
        now = datetime.now()
        this_year = now.strftime("%Y%m")
        last_year = (now.replace(year=now.year - 1)).strftime("%Y%m")
        curr = _unipass_get_raw("8542", this_year, this_year)
        prev = _unipass_get_raw("8542", last_year, last_year)
        if not curr or not prev:
            return None
        curr_val = float(curr[0].get("expAmt", 0))
        prev_val = float(prev[0].get("expAmt", 1))
        yoy_pct = (curr_val - prev_val) / prev_val * 100
        result = {
            "yoy_pct": round(yoy_pct, 2),
            "latest_month": this_year,
            "source": "unipass",
        }
        _cache.set(cache_key, result)
        return result
    except Exception as e:
        _logger.warning("fetch_semiconductor_export_yoy failed: %s", e)
        return None


def fetch_export_by_category(hs_code: str) -> "dict | None":
    """Generic export statistics by HS code.

    Parameters
    ----------
    hs_code:
        HS code string, e.g. "8542" for ICs.

    Returns
    -------
    dict or None
        {"hs_code": ..., "latest_month": ..., "amount": ...} or None.
    """
    from datetime import datetime

    cache_key = f"unipass_export_{hs_code}"
    cached = _cache.get(cache_key, _TTL)
    if cached is not None:
        return cached
    try:
        month = datetime.now().strftime("%Y%m")
        rows = _unipass_get_raw(hs_code, month, month)
        if not rows:
            return None
        result = {
            "hs_code": hs_code,
            "latest_month": month,
            "amount": float(rows[0].get("expAmt", 0)),
        }
        _cache.set(cache_key, result)
        return result
    except Exception as e:
        _logger.warning("fetch_export_by_category(%s) failed: %s", hs_code, e)
        return None
