"""News analysis triggers.

뉴스 수집/감성 분석을 실제로 수행해야 하는 3가지 조건을 판단한다:
1) FOMC week      — 연준 발표일 ±2 캘린더일
2) Earnings week  — 보유 종목 ±3일 내 실적 발표 (yfinance .calendar)
3) SEC 8-K filing — 보유 종목 최근 48h 내 8-K 신규 제출 (SEC EDGAR Atom RSS)

모든 로직은 API 키를 요구하지 않으며 GitHub Actions CI/CD에서도 동작한다.
트리거가 없으면 뉴스 수집 자체를 스킵하여 불필요한 RSS 호출을 방지한다.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests
import yfinance as yf


# ─── FOMC 일정 (Federal Reserve 공식 발표 기준) ─────────────────────────────
# 출처: federalreserve.gov > Monetary Policy > FOMC Meeting calendars
# 각 회의는 이틀 진행되며 '발표일(second day)' = statement release 날짜.
FOMC_MEETING_DATES: list[date] = [
    # 2025
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    # 2026
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
]

FOMC_WINDOW_DAYS: int = 2       # ±2 캘린더일
EARNINGS_WINDOW_DAYS: int = 3   # ±3 캘린더일
SEC_8K_LOOKBACK_HOURS: int = 48

# SEC EDGAR 요구: 식별 가능한 User-Agent (10 req/sec 제한)
_SEC_UA = "STOCK_WORK research-bot (github.com/user/stock-work)"

# 모듈 전역 CIK 캐시 (프로세스 1회 로드)
_CIK_CACHE: dict[str, str] = {}


# ─── 트리거 1: FOMC week ─────────────────────────────────────────────────────

def is_fomc_week(today: Optional[date] = None) -> bool:
    """오늘이 FOMC 발표일 ±FOMC_WINDOW_DAYS 이내이면 True."""
    today = today or datetime.now(timezone.utc).date()
    return any(abs((today - m).days) <= FOMC_WINDOW_DAYS for m in FOMC_MEETING_DATES)


# ─── 트리거 2: Earnings week ─────────────────────────────────────────────────

def is_earnings_week(
    symbols: list[str],
    today: Optional[date] = None,
) -> tuple[bool, list[str]]:
    """보유 종목 중 ±EARNINGS_WINDOW_DAYS 내 실적 발표가 있는 종목 반환.

    yfinance .calendar 는 dict 또는 DataFrame 을 반환할 수 있으므로 둘 다 지원.
    실패/데이터 없음은 보수적으로 False 처리 (잘못된 트리거 방지).

    Returns:
        (triggered: bool, matched_symbols: list[str])
    """
    today = today or datetime.now(timezone.utc).date()
    hits: list[str] = []

    for sym in symbols:
        try:
            cal = yf.Ticker(sym).calendar
            ed = None

            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
            else:
                # DataFrame 형태
                try:
                    ed = cal.loc["Earnings Date"].iloc[0]
                except Exception:
                    ed = None

            if ed is None:
                continue

            candidates = ed if isinstance(ed, (list, tuple)) else [ed]

            for d in candidates:
                try:
                    if hasattr(d, "date"):
                        d = d.date()
                    if abs((d - today).days) <= EARNINGS_WINDOW_DAYS:
                        hits.append(sym)
                        break
                except Exception:
                    continue

        except Exception:
            continue

    return (len(hits) > 0, hits)


# ─── 트리거 3: SEC 8-K ───────────────────────────────────────────────────────

def _load_cik_cache() -> None:
    """SEC EDGAR company_tickers.json 에서 Ticker→CIK 매핑을 로드한다 (1회 캐시)."""
    global _CIK_CACHE
    if _CIK_CACHE:
        return
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": _SEC_UA},
            timeout=10,
        )
        r.raise_for_status()
        for row in r.json().values():
            ticker = row.get("ticker", "").upper()
            cik = str(row.get("cik_str", "")).zfill(10)
            if ticker:
                _CIK_CACHE[ticker] = cik
    except Exception as exc:
        print(f"[triggers] SEC CIK 캐시 로드 실패: {exc}")


def _cik_for(symbol: str) -> Optional[str]:
    """Ticker → 10자리 zero-padded CIK. 없으면 None."""
    _load_cik_cache()
    return _CIK_CACHE.get(symbol.upper())


def has_8k_filing(
    symbols: list[str],
    lookback_hours: int = SEC_8K_LOOKBACK_HOURS,
    now: Optional[datetime] = None,
) -> tuple[bool, list[str]]:
    """보유 종목 중 최근 lookback_hours 내 8-K 공시가 있는 종목 반환.

    SEC EDGAR 공개 Atom 피드(무료, 키 불필요)를 종목별로 조회한다.
    SEC Rate limit: 10 req/sec. 네트워크 실패 시 보수적으로 False 처리.

    Returns:
        (triggered: bool, matched_symbols: list[str])
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)
    hits: list[str] = []

    for sym in symbols:
        cik = _cik_for(sym)
        if not cik:
            continue

        url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik}&type=8-K"
            "&dateb=&owner=include&count=10&output=atom"
        )
        try:
            r = requests.get(
                url,
                headers={"User-Agent": _SEC_UA},
                timeout=10,
            )
            r.raise_for_status()

            for m in re.finditer(r"<updated>([^<]+)</updated>", r.text):
                try:
                    ts_str = m.group(1).strip().replace("Z", "+00:00")
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        hits.append(sym)
                        break
                except Exception:
                    continue

        except Exception as exc:
            print(f"[triggers] {sym} 8-K 조회 실패 (skip): {exc}")
            continue

    return (len(hits) > 0, hits)


# ─── 통합 판정 ───────────────────────────────────────────────────────────────

def should_analyze_news(
    symbols: list[str],
    today: Optional[date] = None,
) -> tuple[bool, str]:
    """3가지 트리거를 단락평가(short-circuit)로 순서대로 평가한다.

    하나라도 True 이면 즉시 (True, reason) 반환.
    reason 은 run_cycle 로그 및 news_trigger 상태에 기록된다.

    순서: FOMC (가장 빠름, 네트워크 없음) → Earnings → 8-K (가장 느림)

    Returns:
        (should_run: bool, reason: str)
        reason 예시: "fomc_week", "earnings:AAPL,MSFT", "8k:NVDA", "no_trigger"
    """
    today = today or datetime.now(timezone.utc).date()

    # 1) FOMC (네트워크 없음, 즉시)
    if is_fomc_week(today):
        return True, "fomc_week"

    if not symbols:
        return False, "no_trigger"

    # 2) Earnings (yfinance)
    earn_hit, earn_syms = is_earnings_week(symbols, today)
    if earn_hit:
        return True, f"earnings:{','.join(earn_syms[:5])}"

    # 3) SEC 8-K (네트워크 최대 len(symbols) * 1 req)
    k8_hit, k8_syms = has_8k_filing(symbols)
    if k8_hit:
        return True, f"8k:{','.join(k8_syms[:5])}"

    return False, "no_trigger"
