"""FOMC/CPI/PPI/PMI/NFP 발표일 블랙아웃 관리.

Primary: FMP /v3/economic_calendar (유료 플랜 전용)
Fallback-1: FRED API (FRED_API_KEY 필요, 무료)
Fallback-2: 빈 dict + 경고 출력 (graceful degradation)

Usage:
    from fundamentals.economic import get_economic_blackouts
    blackouts = get_economic_blackouts()
    # {"FOMC": 1, "CPI": 4, "PMI": 7}

비용: FMP Pro 플랜($29/mo) 또는 FRED_API_KEY(무료 등록).
현재 FMP 무료 티어 → FRED 시도 → 빈 dict 반환.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

_BASE = "https://financialmodelingprep.com/api/v3"
_FMP_KEY = os.environ.get("FMP_API_KEY", "")
_FRED_KEY = os.environ.get("FRED_API_KEY", "")

_EVENT_MAP = {
    "FOMC": ["fomc", "federal open market", "fed rate", "federal funds rate"],
    "CPI": ["cpi", "consumer price index"],
    "PPI": ["ppi", "producer price index"],
    "PMI": ["pmi", "purchasing managers", "ism manufacturing", "ism services"],
    "NFP": ["nonfarm payroll", "non-farm payroll", "nfp", "employment situation"],
}

# FRED Series ID → 이벤트 유형 매핑 (economic indicators release calendar)
_FRED_SERIES = {
    "FEDFUNDS": "FOMC",    # Federal Funds Rate (FOMC 결정일 근처 업데이트)
    "CPIAUCSL": "CPI",     # Consumer Price Index
    "PPIACO": "PPI",       # Producer Price Index
    "PAYEMS": "NFP",       # Nonfarm Payrolls
}


def _get_via_fmp() -> dict[str, int] | None:
    """FMP economic calendar. 실패(403 포함) 시 None 반환."""
    if not _FMP_KEY:
        return None
    try:
        import requests
    except ImportError:
        return None

    today = date.today()
    from_dt = today.strftime("%Y-%m-%d")
    to_dt = (today + timedelta(days=60)).strftime("%Y-%m-%d")
    url = f"{_BASE}/economic_calendar?from={from_dt}&to={to_dt}&apikey={_FMP_KEY}"

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 403:
            return None  # 유료 플랜 필요 — fallback으로 전환
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    result: dict[str, int] = {}
    today_d = date.today()
    for item in data:
        event_name = (item.get("event") or item.get("name") or "").lower()
        date_str = item.get("date") or ""
        if not date_str:
            continue
        try:
            event_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        days = (event_date - today_d).days
        if days < 0:
            continue
        for key, keywords in _EVENT_MAP.items():
            if any(kw in event_name for kw in keywords):
                if key not in result or days < result[key]:
                    result[key] = days
                break

    return result


def _get_via_fred() -> dict[str, int]:
    """FRED API로 다음 주요 경제 지표 발표일 조회.

    FRED_API_KEY 환경변수 필요. https://fred.stlouisfed.org/docs/api/api_key.html (무료)
    """
    if not _FRED_KEY:
        return {}
    try:
        import requests
    except ImportError:
        return {}

    today = date.today()
    to_dt = (today + timedelta(days=60)).strftime("%Y-%m-%d")
    result: dict[str, int] = {}

    for series_id, event_key in _FRED_SERIES.items():
        if event_key in result:
            continue  # 이미 찾은 이벤트 스킵
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={_FRED_KEY}&file_type=json"
            f"&observation_start={today.strftime('%Y-%m-%d')}&observation_end={to_dt}"
            f"&limit=5&sort_order=asc"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            if obs:
                first_date = date.fromisoformat(obs[0]["date"])
                days = (first_date - today).days
                if days >= 0:
                    result[event_key] = days
        except Exception:
            continue

    return result


def get_economic_blackouts() -> dict[str, int]:
    """다음 주요 경제 이벤트까지 남은 일수.

    Returns:
        {"FOMC": 1, "CPI": 4, ...}
        FMP Pro 또는 FRED_API_KEY 없으면 빈 dict (graceful degradation).
    """
    # 1. FMP Pro 시도
    fmp_result = _get_via_fmp()
    if fmp_result is not None:
        return fmp_result

    # 2. FRED fallback
    if _FRED_KEY:
        fred_result = _get_via_fred()
        if fred_result:
            return fred_result

    # 3. 둘 다 없으면 안내 메시지 출력 후 빈 dict
    if not _FRED_KEY:
        print(
            "  [fundamentals/economic] FOMC/CPI blackout inactive."
            " Set FRED_API_KEY to activate (free: https://fred.stlouisfed.org/docs/api/api_key.html)"
        )
    return {}
