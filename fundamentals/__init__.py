"""펀더멘털 분석 레이어 — 월스트리트 이벤트 리스크 데이터.

모든 함수는 실패 시 빈 dict/fallback 반환 (no-op graceful degradation).
비용: FMP 무료 티어 2 calls/cycle, yfinance 무료.
"""

from __future__ import annotations

import io
import sys

# Windows cp949 fix (run_cycle.py 외부에서 직접 호출 시 대비)
def _fix_enc() -> None:
    for _name in ("stdout", "stderr"):
        _s = getattr(sys, _name)
        if hasattr(_s, "buffer"):
            _enc = (getattr(_s, "encoding", None) or "").lower().replace("-", "")
            if _enc in ("cp949", "euckr", "mskr"):
                setattr(sys, _name, io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace"))

_fix_enc()

from .analyst import get_analyst_consensus
from .earnings import get_earnings_risk
from .economic import get_economic_blackouts
from .insider import get_insider_signals


def collect_all(symbols: list[str]) -> dict:
    """Phase 1.6에서 호출. 전체 펀더멘털 데이터를 한 번에 수집.

    Returns:
        {
            "earnings_blackout": {symbol: days_to_earnings},
            "economic_blackout": {"FOMC": days, "CPI": days, ...},
            "analyst": {symbol: {"rec_mean": ..., "target_price": ..., "analyst_count": ...}},
            "insider": {symbol: {"buy_30d": ..., "sell_30d": ..., "net_30d": ...}},
        }
    """
    print(f"  [fundamentals] 수집 시작: {len(symbols)} 종목")

    earnings = get_earnings_risk(symbols)
    economic = get_economic_blackouts()
    analyst = get_analyst_consensus(symbols)
    insider = get_insider_signals(symbols)

    # 블랙아웃 경고 출력
    for event, days in economic.items():
        if days <= 3:
            print(f"  ⚠️  {event} {days}일 후 발표 — 포지션 관리 주의")

    # 실적 임박 종목 경고
    for sym, days in earnings.items():
        if days <= 3:
            print(f"  ⚠️  {sym} 실적발표 D-{days} — 포지션 50% 축소 권고")

    print(
        f"  [fundamentals] 완료: earnings={len(earnings)}종목, "
        f"economic={list(economic.keys())}, analyst={len(analyst)}종목, insider={len(insider)}종목"
    )

    return {
        "earnings_blackout": earnings,
        "economic_blackout": economic,
        "analyst": analyst,
        "insider": insider,
    }
