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

# FRED Release ID → 이벤트 유형 매핑
# https://api.stlouisfed.org/fred/releases (전체 목록 조회 가능)
_FRED_RELEASES = {
    10:  "CPI",   # Consumer Price Index (CPI)
    31:  "PPI",   # Producer Price Index (PPI)
    50:  "NFP",   # Employment Situation (Nonfarm Payrolls)
    183: "FOMC",  # FOMC (Federal Open Market Committee)
    33:  "PMI",   # ISM Manufacturing PMI
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
    """FRED release/dates API로 다음 주요 경제 지표 발표 예정일 조회.

    사용 엔드포인트: /fred/release/dates?release_id={id}
    → 예정된 발표일 목록을 가져와 오늘 이후 가장 가까운 날짜 반환.
    """
    if not _FRED_KEY:
        return {}
    try:
        import requests
    except ImportError:
        return {}

    today = date.today()
    from_dt = today.strftime("%Y-%m-%d")
    to_dt = (today + timedelta(days=90)).strftime("%Y-%m-%d")
    result: dict[str, int] = {}

    for release_id, event_key in _FRED_RELEASES.items():
        url = (
            f"https://api.stlouisfed.org/fred/release/dates"
            f"?release_id={release_id}&api_key={_FRED_KEY}&file_type=json"
            f"&realtime_start={from_dt}&realtime_end={to_dt}"
            f"&include_release_dates_with_no_data=true"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            dates_list = resp.json().get("release_dates", [])
            for entry in dates_list:
                date_str = entry.get("date", "")
                if not date_str:
                    continue
                try:
                    rel_date = date.fromisoformat(date_str)
                except ValueError:
                    continue
                days = (rel_date - today).days
                if days >= 0:
                    if event_key not in result or days < result[event_key]:
                        result[event_key] = days
                    break  # 가장 가까운 날짜만 필요
        except Exception as e:
            print(f"  [fundamentals/economic] FRED release {release_id} 조회 실패: {e}")
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
