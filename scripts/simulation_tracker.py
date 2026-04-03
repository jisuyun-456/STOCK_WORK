"""
시뮬레이션 포트폴리오 트래커
- portfolio_state.json 초기화 / P&L 업데이트 / 요약 반환
- CLI: python simulation_tracker.py init   → 최초 포트폴리오 설정
       python simulation_tracker.py status → 현재 현황 출력
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import yfinance as yf
from datetime import datetime, date
from pathlib import Path

# 포트폴리오 구성 (확정)
PORTFOLIO_DEFINITION = [
    {
        "symbol": "PLTR",
        "allocation": 7000,
        "thesis_short": "정부/기업 AI 플랫폼 독점, 미-이란 분쟁 수혜, 흑자 전환 완료",
    },
    {
        "symbol": "RKLB",
        "allocation": 5000,
        "thesis_short": "우주 경제 유일한 공개 순수주, Neutron 재사용 로켓 임박",
    },
    {
        "symbol": "HIMS",
        "allocation": 4000,
        "thesis_short": "텔레헬스 + GLP-1 비만약 복제약, 헬스케어 유통 파괴자",
    },
    {
        "symbol": "APLD",
        "allocation": 3000,
        "thesis_short": "AI 데이터센터 순수주, CoreWeave 대비 극도 저평가",
    },
    {
        "symbol": "IONQ",
        "allocation": 1000,
        "thesis_short": "퀀텀 컴퓨팅 복권, AWS/Azure/Google 파트너십, 소액 베팅",
    },
]

TOTAL_CAPITAL = 20000
STATE_FILE = Path(__file__).parent.parent / "docs" / "simulation" / "portfolio_state.json"


def _get_current_price(symbol: str) -> float | None:
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def load_state() -> dict | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def init_portfolio() -> dict:
    """최초 1회: 당일 종가로 진입가 설정 + portfolio_state.json 생성"""
    start_date = str(date.today())
    positions = []

    print("포트폴리오 초기화 중...", file=sys.stderr)
    for item in PORTFOLIO_DEFINITION:
        symbol = item["symbol"]
        print(f"  → {symbol} 진입가 조회 중...", file=sys.stderr)
        price = _get_current_price(symbol)
        if price is None:
            print(f"  ⚠️ {symbol} 가격 조회 실패 — 1.0으로 임시 설정", file=sys.stderr)
            price = 1.0
        shares = item["allocation"] / price
        positions.append({
            "symbol": symbol,
            "shares": round(shares, 6),
            "entry_price": round(price, 4),
            "allocation": item["allocation"],
            "thesis_short": item["thesis_short"],
        })
        print(f"  ✅ {symbol}: 진입가 ${price:.2f}, {shares:.4f}주", file=sys.stderr)

    state = {
        "start_date": start_date,
        "total_capital": TOTAL_CAPITAL,
        "positions": positions,
        "daily_snapshots": [
            {
                "date": start_date,
                "total_value": TOTAL_CAPITAL,
                "daily_return_pct": 0.0,
                "cumulative_return_pct": 0.0,
            }
        ],
    }
    save_state(state)
    print(f"\n✅ 포트폴리오 초기화 완료 → {STATE_FILE}", file=sys.stderr)
    return state


def update_portfolio(state: dict) -> dict:
    """당일 종가로 P&L 업데이트 + daily_snapshots 누적"""
    today = str(date.today())

    # 이미 오늘 업데이트됐으면 스킵
    if state["daily_snapshots"] and state["daily_snapshots"][-1]["date"] == today:
        print(f"  ⚠️ {today} 이미 업데이트됨 — 스킵", file=sys.stderr)
        return state

    total_value = 0.0
    for pos in state["positions"]:
        price = _get_current_price(pos["symbol"])
        if price is None:
            # 전일 가격 재사용
            price = pos.get("last_price", pos["entry_price"])
        pos["last_price"] = round(price, 4)
        pos["current_value"] = round(pos["shares"] * price, 2)
        pos["return_pct"] = round(
            (price - pos["entry_price"]) / pos["entry_price"] * 100, 2
        )
        total_value += pos["current_value"]

    prev_value = state["daily_snapshots"][-1]["total_value"] if state["daily_snapshots"] else TOTAL_CAPITAL
    daily_return = (total_value - prev_value) / prev_value * 100 if prev_value else 0
    cumulative_return = (total_value - TOTAL_CAPITAL) / TOTAL_CAPITAL * 100

    state["daily_snapshots"].append({
        "date": today,
        "total_value": round(total_value, 2),
        "daily_return_pct": round(daily_return, 2),
        "cumulative_return_pct": round(cumulative_return, 2),
    })

    save_state(state)
    return state


def get_portfolio_summary(state: dict) -> dict:
    """리포트용 포트폴리오 요약 반환"""
    if not state:
        return {"error": "포트폴리오 미초기화"}

    latest = state["daily_snapshots"][-1] if state["daily_snapshots"] else {}
    total_value = latest.get("total_value", TOTAL_CAPITAL)
    cumulative_return = latest.get("cumulative_return_pct", 0.0)
    daily_return = latest.get("daily_return_pct", 0.0)

    positions = state.get("positions", [])
    best = max(positions, key=lambda p: p.get("return_pct", 0), default={})
    worst = min(positions, key=lambda p: p.get("return_pct", 0), default={})

    return {
        "start_date": state.get("start_date", ""),
        "total_capital": state.get("total_capital", TOTAL_CAPITAL),
        "total_value": total_value,
        "cumulative_return_pct": cumulative_return,
        "daily_return_pct": daily_return,
        "best_performer": {
            "symbol": best.get("symbol", ""),
            "return_pct": best.get("return_pct", 0),
        },
        "worst_performer": {
            "symbol": worst.get("symbol", ""),
            "return_pct": worst.get("return_pct", 0),
        },
        "positions": [
            {
                "symbol": p["symbol"],
                "entry_price": p["entry_price"],
                "current_price": p.get("last_price", p["entry_price"]),
                "return_pct": p.get("return_pct", 0.0),
                "current_value": p.get("current_value", p["allocation"]),
                "allocation": p["allocation"],
                "thesis_short": p["thesis_short"],
            }
            for p in positions
        ],
        "days_running": len(state["daily_snapshots"]),
    }


def run_daily_update() -> dict:
    """일일 리포트에서 호출: 상태 로드 → 업데이트 → 요약 반환"""
    state = load_state()
    if state is None:
        print("  ⚠️ portfolio_state.json 없음 — 자동 초기화", file=sys.stderr)
        state = init_portfolio()
    else:
        state = update_portfolio(state)
    return get_portfolio_summary(state)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "init":
        state = init_portfolio()
        summary = get_portfolio_summary(state)
        print(f"\n📊 포트폴리오 현황 ({summary['start_date']} 기준)")
        for p in summary["positions"]:
            print(f"  {p['symbol']:6s} | 진입가 ${p['entry_price']:.2f} | {p['allocation']}달러 배분")

    elif cmd == "status":
        state = load_state()
        if state is None:
            print("포트폴리오 미초기화. 'python simulation_tracker.py init' 실행하세요.")
            sys.exit(1)
        summary = get_portfolio_summary(state)
        print(f"\n📊 시뮬레이션 포트폴리오 현황")
        print(f"  시작일: {summary['start_date']} ({summary['days_running']}일째)")
        print(f"  총 평가액: ${summary['total_value']:,.2f} (초기 ${summary['total_capital']:,.0f})")
        print(f"  누적 수익률: {summary['cumulative_return_pct']:+.2f}%")
        print(f"  당일 수익률: {summary['daily_return_pct']:+.2f}%")
        print(f"\n  종목별 현황:")
        for p in summary["positions"]:
            sign = "+" if p["return_pct"] >= 0 else ""
            print(f"  {p['symbol']:6s} | 진입 ${p['entry_price']:.2f} → 현재 ${p['current_price']:.2f} | {sign}{p['return_pct']:.2f}%")

    elif cmd == "update":
        state = load_state()
        if state is None:
            print("포트폴리오 미초기화. 먼저 init을 실행하세요.")
            sys.exit(1)
        state = update_portfolio(state)
        summary = get_portfolio_summary(state)
        print(f"✅ 업데이트 완료 | 총 평가액: ${summary['total_value']:,.2f} | 누적: {summary['cumulative_return_pct']:+.2f}%")

    else:
        print(f"Usage: python simulation_tracker.py [init|status|update]")
        sys.exit(1)


if __name__ == "__main__":
    main()
