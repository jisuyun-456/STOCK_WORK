"""실적발표 D-Day 리스크 플래그.

Primary: yfinance ticker.calendar (무료, API 키 불필요)
Fallback: FMP /v3/earning_calendar (유료 플랜 필요, 403 시 자동 스킵)

Usage:
    from fundamentals.earnings import get_earnings_risk
    risk = get_earnings_risk(["AAPL", "MSFT"])
    # {"AAPL": 2, "MSFT": 14}  → AAPL 실적발표 2일 후
"""

from __future__ import annotations

import os
from datetime import date, timedelta

_BASE = "https://financialmodelingprep.com/api/v3"
_FMP_KEY = os.environ.get("FMP_API_KEY", "")


def _get_via_yfinance(symbols: list[str]) -> dict[str, int]:
    """yfinance ticker.calendar → 다음 실적발표 날짜."""
    try:
        import yfinance as yf
    except ImportError:
        return {}

    today = date.today()
    result: dict[str, int] = {}

    for sym in symbols:
        try:
            cal = yf.Ticker(sym).calendar
            if cal is None:
                continue
            # calendar는 dict 또는 DataFrame 형태로 반환
            if hasattr(cal, "get"):
                earn_date_val = cal.get("Earnings Date")
            elif hasattr(cal, "iloc"):
                # DataFrame인 경우 첫 번째 행
                earn_date_val = cal.iloc[0].get("Earnings Date") if not cal.empty else None
            else:
                earn_date_val = None

            if earn_date_val is None:
                continue

            # Earnings Date가 리스트일 수 있음 (범위)
            if isinstance(earn_date_val, (list, tuple)) and earn_date_val:
                earn_date_val = earn_date_val[0]

            import pandas as pd
            earn_dt = pd.to_datetime(earn_date_val).date()
            days = (earn_dt - today).days
            if days >= 0:
                result[sym] = days
        except Exception:
            continue

    return result


def _get_via_fmp(symbols: list[str]) -> dict[str, int]:
    """FMP earning_calendar → 유료 플랜 전용, 403 시 빈 dict 반환."""
    if not _FMP_KEY:
        return {}
    try:
        import requests
    except ImportError:
        return {}

    today = date.today()
    from_dt = today.strftime("%Y-%m-%d")
    to_dt = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    url = f"{_BASE}/earning_calendar?from={from_dt}&to={to_dt}&apikey={_FMP_KEY}"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}

    sym_set = {s.upper() for s in symbols}
    result: dict[str, int] = {}
    for item in data:
        sym = (item.get("symbol") or "").upper()
        if sym not in sym_set:
            continue
        date_str = item.get("date") or item.get("reportDate") or ""
        if not date_str:
            continue
        try:
            earn_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        days = (earn_date - today).days
        if days >= 0:
            if sym not in result or days < result[sym]:
                result[sym] = days

    return result


def get_earnings_risk(symbols: list[str]) -> dict[str, int]:
    """종목별 다음 실적발표까지 남은 일수. yfinance 우선, FMP fallback.

    Returns:
        {symbol: days_to_earnings}  (없으면 딕셔너리에 미포함)
    """
    result = _get_via_yfinance(symbols)

    # yfinance에서 누락된 종목만 FMP로 재시도
    missing = [s for s in symbols if s not in result]
    if missing:
        fmp_result = _get_via_fmp(missing)
        result.update(fmp_result)

    return result
