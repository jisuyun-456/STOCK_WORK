"""KRX KIND (Korea Investor Relations Network) public disclosure client.

Provides:
  - fetch_investment_alerts(date): investment warning/caution/danger list
  - fetch_trading_halts(date): trading halt list
  - fetch_unusual_filings(): query disclosures (조회공시)

No authentication required for basic public disclosures.
All responses are disk-cached via KRCache with a 1-hour TTL.
"""
import logging
import requests

from kr_data.retry import retry_with_backoff
from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.kind")
_cache = KRCache()
_TTL = 3600  # 1 hour

_KIND_BASE = "https://kind.krx.co.kr/disclosure"


@retry_with_backoff
def _kind_get_raw(path: str, params: dict) -> list[dict]:
    """Raw KIND API call. Raises on failure (for retry decorator)."""
    url = f"{_KIND_BASE}/{path}"
    resp = requests.get(
        url,
        params=params,
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("list", data.get("result", []))


def fetch_investment_alerts(date: str) -> list[dict]:
    """KRX investment alerts (투자주의/경고/위험).

    Parameters
    ----------
    date:
        Date string in "YYYYMMDD" format.

    Returns
    -------
    list[dict]
        Each element has keys: [ticker, corp_name, alert_type, date].
        Returns [] on failure.
    """
    cache_key = f"kind_alerts_{date}"
    cached = _cache.get(cache_key, _TTL)
    if cached is not None:
        return cached.get("alerts", [])
    try:
        rows = _kind_get_raw(
            "investWarning.do",
            {"searchDate": date, "pageSize": "100"},
        )
        alerts = [
            {
                "ticker": r.get("isu_cd", ""),
                "corp_name": r.get("isu_nm", ""),
                "alert_type": r.get("invst_wrn_tp_nm", ""),
                "date": date,
            }
            for r in rows
        ]
    except Exception as e:
        _logger.warning("fetch_investment_alerts(%s) failed: %s", date, e)
        return []
    _cache.set(cache_key, {"alerts": alerts})
    return alerts


def fetch_trading_halts(date: str) -> list[dict]:
    """KRX trading halts (거래정지).

    Parameters
    ----------
    date:
        Date string in "YYYYMMDD" format.

    Returns
    -------
    list[dict]
        Each element has keys: [ticker, corp_name, halt_reason, date].
        Returns [] on failure.
    """
    cache_key = f"kind_halts_{date}"
    cached = _cache.get(cache_key, _TTL)
    if cached is not None:
        return cached.get("halts", [])
    try:
        rows = _kind_get_raw(
            "tradingHalt.do",
            {"searchDate": date, "pageSize": "100"},
        )
        halts = [
            {
                "ticker": r.get("isu_cd", ""),
                "corp_name": r.get("isu_nm", ""),
                "halt_reason": r.get("halt_rsn_nm", ""),
                "date": date,
            }
            for r in rows
        ]
    except Exception as e:
        _logger.warning("fetch_trading_halts(%s) failed: %s", date, e)
        return []
    _cache.set(cache_key, {"halts": halts})
    return halts


def fetch_unusual_filings() -> list[dict]:
    """조회공시 (unusual/query disclosures).

    Returns
    -------
    list[dict]
        Each element has keys: [ticker, corp_name, content].
        Returns [] on failure.
    """
    cache_key = "kind_unusual"
    cached = _cache.get(cache_key, _TTL)
    if cached is not None:
        return cached.get("filings", [])
    try:
        rows = _kind_get_raw("inquiry.do", {"pageSize": "50"})
        filings = [
            {
                "ticker": r.get("isu_cd", ""),
                "corp_name": r.get("isu_nm", ""),
                "content": r.get("inqr_cn", ""),
            }
            for r in rows
        ]
    except Exception as e:
        _logger.warning("fetch_unusual_filings failed: %s", e)
        return []
    _cache.set(cache_key, {"filings": filings})
    return filings
