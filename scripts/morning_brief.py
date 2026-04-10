#!/usr/bin/env python3
"""Morning Brief -- 한 커맨드로 전체 현황 파악.

Usage:
    python scripts/morning_brief.py

출력:
    - Alpaca 계정 잔고 + 전체 P&L
    - 레짐 상태 (BULL/NEUTRAL/BEAR/CRISIS)
    - 전략별 포지션 요약
    - 오늘의 경제 이벤트 (FOMC/CPI 등)
    - 실적발표 임박 보유 종목 (D-7 이내)
    - 애널리스트 SELL 등급 보유 종목
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date
from pathlib import Path

# Windows cp949 fix
if hasattr(sys.stdout, "buffer"):
    _enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    if _enc in ("cp949", "euckr", "mskr"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
STATE_DIR = ROOT / "state"

# .env 로드 (환경변수 자동 적용)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass
PORTFOLIOS_PATH = STATE_DIR / "portfolios.json"
PERFORMANCE_PATH = STATE_DIR / "performance.json"
REGIME_PATH = STATE_DIR / "regime_state.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main() -> None:
    today = date.today().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"  MORNING BRIEF  {today}")
    print(f"{'='*60}")

    # ── 1. Alpaca 계정 잔고 ──────────────────────────────────────────────────
    portfolios = _load_json(PORTFOLIOS_PATH)
    account_total = portfolios.get("account_total", 0)
    _section("1. Alpaca 계좌")
    print(f"  실제 잔고:   ${account_total:,.2f}")
    print(f"  최종 업데이트: {portfolios.get('last_updated', 'N/A')}")

    # 전체 미실현 P&L 계산 (전략별 포지션 합산)
    total_unreal = 0.0
    total_pos = 0
    for code, strat in portfolios.get("strategies", {}).items():
        for pos in strat.get("positions", {}).values():
            total_unreal += pos.get("unrealized_pl", 0)
            total_pos += 1
    pnl_sign = "+" if total_unreal >= 0 else ""
    print(f"  미실현 P&L:  {pnl_sign}${total_unreal:,.2f}  (보유 포지션 {total_pos}개)")

    # ── 2. 레짐 상태 ─────────────────────────────────────────────────────────
    regime_state = _load_json(REGIME_PATH)
    _section("2. 시장 레짐")
    regime = regime_state.get("regime", "UNKNOWN")
    since = regime_state.get("since", "N/A")
    consec = regime_state.get("consecutive_cycles", 0)
    regime_icon = {"BULL": "📈", "NEUTRAL": "➡️", "BEAR": "📉", "CRISIS": "🚨"}.get(regime, "?")
    print(f"  현재 레짐: {regime_icon} {regime}  (since {since}, {consec} cycles)")

    # ── 3. 전략별 포지션 요약 ─────────────────────────────────────────────────
    _section("3. 전략별 포지션")
    for code, strat in portfolios.get("strategies", {}).items():
        positions = strat.get("positions", {})
        cash = strat.get("cash", 0)
        allocated = strat.get("allocated", 0)
        strat_unreal = sum(p.get("unrealized_pl", 0) for p in positions.values())
        sign = "+" if strat_unreal >= 0 else ""
        print(f"  {code:4s} | {len(positions):2d}개 포지션 | "
              f"현금=${cash:>10,.2f} | P&L={sign}${strat_unreal:,.2f}")

    # ── 4. 경제 이벤트 캘린더 ────────────────────────────────────────────────
    _section("4. 경제 이벤트 (다음 14일)")
    try:
        sys.path.insert(0, str(ROOT))
        from fundamentals.economic import get_economic_blackouts
        blackouts = get_economic_blackouts()
        if blackouts:
            for event, days in sorted(blackouts.items(), key=lambda x: x[1]):
                if days <= 14:
                    flag = " *** BUY BLOCKED ***" if event == "FOMC" and days <= 2 else \
                           " * position reduce" if days <= 3 else ""
                    print(f"  {event:6s}: D-{days:2d}{flag}")
        else:
            print("  (경제 캘린더 비활성 -- .env 에 FRED_API_KEY 추가 시 활성화)")
    except Exception as e:
        print(f"  (경제 캘린더 조회 실패: {e})")

    # ── 5. 실적발표 임박 보유 종목 ───────────────────────────────────────────
    _section("5. 실적발표 임박 보유 종목 (D-7 이내)")
    try:
        from fundamentals.earnings import get_earnings_risk
        held_symbols = []
        for strat in portfolios.get("strategies", {}).values():
            held_symbols.extend(strat.get("positions", {}).keys())
        held_symbols = list(set(held_symbols))

        if held_symbols:
            earn_risk = get_earnings_risk(held_symbols)
            upcoming = {s: d for s, d in earn_risk.items() if d <= 7}
            if upcoming:
                for sym, days in sorted(upcoming.items(), key=lambda x: x[1]):
                    warn = " *** 포지션 50% 축소 권고 ***" if days <= 3 else " * 주의"
                    print(f"  {sym:6s}: D-{days}{warn}")
            else:
                print("  D-7 이내 실적발표 종목 없음")
        else:
            print("  보유 포지션 없음")
    except Exception as e:
        print(f"  (실적 캘린더 조회 실패: {e})")

    # ── 6. 애널리스트 SELL 등급 보유 종목 ───────────────────────────────────
    _section("6. 애널리스트 SELL 등급 보유 종목")
    try:
        from fundamentals.analyst import get_analyst_consensus
        if held_symbols:
            analyst_data = get_analyst_consensus(held_symbols)
            sell_stocks = {
                s: d for s, d in analyst_data.items()
                if d.get("rec_mean", 3.0) >= 4.0 and d.get("analyst_count", 0) >= 5
            }
            if sell_stocks:
                for sym, d in sorted(sell_stocks.items(), key=lambda x: -x[1].get("rec_mean", 0)):
                    print(f"  {sym:6s}: rec={d['rec_mean']:.1f}/5.0"
                          f"  target=${d.get('target_price', 0):,.0f}"
                          f"  N={d.get('analyst_count', 0)}")
            else:
                print("  SELL 등급 보유 종목 없음")
    except Exception as e:
        print(f"  (애널리스트 조회 실패: {e})")

    print(f"\n{'='*60}")
    print(f"  완료  |  python run_cycle.py --phase all --dry-run 으로 시그널 확인")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
