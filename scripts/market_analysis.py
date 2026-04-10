#!/usr/bin/env python3
"""Market Analysis -- 포트폴리오 종합 리포트 (매크로 + 미국/글로벌 시장 + 개별 종목).

사용자가 "35개 종목 분석해줘" 시 이 스크립트가 종합 리포트 출력.
매매 결정 참고용 데이터만 제공 (체결은 사용자 승인 후 별도 수행).

Usage:
    python scripts/market_analysis.py                     # 보유 전 종목 + 매크로
    python scripts/market_analysis.py --symbols AAPL NVDA # 특정 종목만
    python scripts/market_analysis.py --no-sentiment      # Gemini 분석 건너뛰기 (빠름)
"""

from __future__ import annotations

import argparse
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
PORTFOLIOS_PATH = STATE_DIR / "portfolios.json"

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# sys.path에 ROOT 추가
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════
# 유틸리티
# ═══════════════════════════════════════════════════════════════════

def _section(title: str, icon: str = "") -> None:
    bar = "═" * 70
    print(f"\n{bar}")
    print(f"  {icon} {title}")
    print(f"{bar}")


def _subsection(title: str) -> None:
    print(f"\n  ── {title} " + "─" * (60 - len(title)))


def _load_portfolios() -> dict:
    try:
        return json.loads(PORTFOLIOS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_price_change(ticker_sym: str, period: str = "5d") -> dict:
    """yfinance로 단기/장기 등락률 조회."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker_sym).history(period="260d", auto_adjust=True)
        if hist.empty:
            return {"current": None, "chg_1d": None, "chg_5d": None, "chg_1m": None, "sma200_ratio": None}
        current = float(hist["Close"].iloc[-1])
        chg_1d = (current / float(hist["Close"].iloc[-2]) - 1) * 100 if len(hist) >= 2 else None
        chg_5d = (current / float(hist["Close"].iloc[-6]) - 1) * 100 if len(hist) >= 6 else None
        chg_1m = (current / float(hist["Close"].iloc[-22]) - 1) * 100 if len(hist) >= 22 else None
        sma200 = float(hist["Close"].tail(200).mean()) if len(hist) >= 200 else None
        sma200_ratio = (current / sma200 - 1) * 100 if sma200 else None
        return {
            "current": current,
            "chg_1d": chg_1d,
            "chg_5d": chg_5d,
            "chg_1m": chg_1m,
            "sma200_ratio": sma200_ratio,
        }
    except Exception as e:
        return {"current": None, "chg_1d": None, "chg_5d": None, "chg_1m": None, "sma200_ratio": None, "error": str(e)}


def _fmt_pct(val) -> str:
    if val is None:
        return "  N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _fmt_price(val) -> str:
    if val is None:
        return "N/A"
    if val >= 1000:
        return f"${val:,.2f}"
    return f"${val:.2f}"


# ═══════════════════════════════════════════════════════════════════
# SECTION 1: 글로벌 매크로
# ═══════════════════════════════════════════════════════════════════

def section_macro() -> None:
    _section("SECTION 1: 글로벌 매크로 지표", "🌍")

    macro_tickers = [
        ("^TNX",  "10Y 국채 금리"),
        ("^VIX",  "VIX 공포지수"),
        ("DX-Y.NYB", "달러 인덱스"),
        ("CL=F",  "WTI 원유"),
        ("GC=F",  "금 선물"),
        ("BTC-USD", "비트코인"),
    ]

    for sym, name in macro_tickers:
        data = _get_price_change(sym)
        curr = _fmt_price(data["current"]) if data["current"] else "N/A"
        chg1d = _fmt_pct(data["chg_1d"])
        chg5d = _fmt_pct(data["chg_5d"])
        print(f"  {name:15s} ({sym:10s})  {curr:>12s}  1d:{chg1d:>8s}  5d:{chg5d:>8s}")

    _subsection("경제 이벤트 캘린더")
    try:
        from fundamentals.economic import get_economic_blackouts
        blackouts = get_economic_blackouts()
        if blackouts:
            for event, days in sorted(blackouts.items(), key=lambda x: x[1]):
                if days <= 30:
                    alert = ""
                    if event == "FOMC" and days <= 2:
                        alert = "  ⚠️ BUY 전면 차단"
                    elif event == "CPI" and days <= 1:
                        alert = "  ⚠️ 포지션 30% 축소"
                    elif days <= 3:
                        alert = "  * 주의"
                    print(f"    {event:6s}: D-{days:2d}{alert}")
        else:
            print("    (캘린더 비활성)")
    except Exception as e:
        print(f"    (조회 실패: {e})")


# ═══════════════════════════════════════════════════════════════════
# SECTION 2: 미국 시장 개요
# ═══════════════════════════════════════════════════════════════════

def section_us_market() -> None:
    _section("SECTION 2: 미국 시장 개요", "🇺🇸")

    _subsection("주요 지수")
    us_indices = [
        ("SPY", "S&P 500"),
        ("QQQ", "Nasdaq 100"),
        ("IWM", "Russell 2000 (소형주)"),
        ("DIA", "Dow Jones 30"),
    ]
    for sym, name in us_indices:
        data = _get_price_change(sym)
        curr = _fmt_price(data["current"])
        chg1d = _fmt_pct(data["chg_1d"])
        chg1m = _fmt_pct(data["chg_1m"])
        sma200 = _fmt_pct(data["sma200_ratio"])
        print(f"  {name:25s} ({sym})  {curr:>10s}  1d:{chg1d:>8s}  1m:{chg1m:>8s}  vs.SMA200:{sma200:>8s}")

    _subsection("섹터 ETF (강/약)")
    sectors = [
        ("XLK", "Technology"),
        ("XLF", "Financials"),
        ("XLV", "Healthcare"),
        ("XLE", "Energy"),
        ("XLI", "Industrials"),
        ("XLY", "Cons. Discretionary"),
        ("XLP", "Cons. Staples"),
        ("XLU", "Utilities"),
        ("XLB", "Materials"),
        ("XLRE", "Real Estate"),
    ]
    sector_perfs = []
    for sym, name in sectors:
        data = _get_price_change(sym)
        chg5d = data["chg_5d"]
        sector_perfs.append((sym, name, chg5d))

    # 5일 수익률 정렬
    sector_perfs.sort(key=lambda x: x[2] if x[2] is not None else -999, reverse=True)
    for sym, name, chg5d in sector_perfs:
        chg5d_str = _fmt_pct(chg5d)
        bar = ""
        if chg5d is not None:
            n = int(abs(chg5d))
            bar = ("█" * min(n, 10)) if chg5d >= 0 else ("▓" * min(n, 10))
        print(f"    {name:22s} ({sym:5s})  5d:{chg5d_str:>8s}  {bar}")

    _subsection("시스템 레짐")
    regime_path = STATE_DIR / "regime_state.json"
    try:
        r = json.loads(regime_path.read_text(encoding="utf-8"))
        regime = r.get("regime", "?")
        since = r.get("since", "?")
        consec = r.get("consecutive_cycles", 0)
        print(f"    현재: {regime}  (since {since}, {consec} cycles)")
    except Exception:
        print("    (레짐 파일 없음)")


# ═══════════════════════════════════════════════════════════════════
# SECTION 3: 글로벌 시장
# ═══════════════════════════════════════════════════════════════════

def section_global() -> None:
    _section("SECTION 3: 글로벌 시장", "🌐")

    global_tickers = [
        ("FEZ",  "유럽 Stoxx 50"),
        ("EWJ",  "일본 Nikkei"),
        ("FXI",  "중국 FTSE25"),
        ("EWY",  "한국 KOSPI"),
        ("EEM",  "이머징 마켓"),
        ("EFA",  "선진국 (미국 제외)"),
    ]
    for sym, name in global_tickers:
        data = _get_price_change(sym)
        curr = _fmt_price(data["current"])
        chg1d = _fmt_pct(data["chg_1d"])
        chg5d = _fmt_pct(data["chg_5d"])
        chg1m = _fmt_pct(data["chg_1m"])
        print(f"  {name:22s} ({sym:4s})  {curr:>10s}  1d:{chg1d:>8s}  5d:{chg5d:>8s}  1m:{chg1m:>8s}")


# ═══════════════════════════════════════════════════════════════════
# SECTION 4: 35개 보유 종목 상세
# ═══════════════════════════════════════════════════════════════════

def section_holdings(symbols: list[str], portfolios: dict, analyze_sentiment: bool = False) -> list[dict]:
    _section(f"SECTION 4: 보유 종목 {len(symbols)}개 상세", "📊")

    # 각 종목의 포지션 정보 수집
    position_info: dict[str, dict] = {}
    for strat_code, strat in portfolios.get("strategies", {}).items():
        for sym, pos in strat.get("positions", {}).items():
            position_info[sym] = {**pos, "strategy": strat_code}

    # 펀더멘털 수집 (일괄)
    print("  펀더멘털 수집 중...")
    try:
        from fundamentals import collect_all as fund_collect
        fund_data = fund_collect(symbols)
    except Exception as e:
        print(f"  [warning] fundamentals 실패: {e}")
        fund_data = {"earnings_blackout": {}, "analyst": {}, "insider": {}}

    earnings_blackout = fund_data.get("earnings_blackout", {})
    analyst_data = fund_data.get("analyst", {})
    insider_data = fund_data.get("insider", {})

    results: list[dict] = []

    print(f"\n  {'Sym':5s} {'Strat':5s} {'Price':>10s} {'1d':>8s} {'1m':>8s} {'P&L':>10s} "
          f"{'Earn':>6s} {'Rec':>5s} {'Ins':>6s}  Action")
    print("  " + "─" * 100)

    for sym in symbols:
        pos = position_info.get(sym, {})
        strat = pos.get("strategy", "?")
        price_data = _get_price_change(sym)
        current = price_data["current"]
        chg_1d = price_data["chg_1d"]
        chg_1m = price_data["chg_1m"]
        unreal_pl = pos.get("unrealized_pl", 0)

        days_earn = earnings_blackout.get(sym, 99)
        ana = analyst_data.get(sym, {})
        rec_mean = ana.get("rec_mean", 3.0)
        ins = insider_data.get(sym, {})
        ins_net = ins.get("net_30d", 0)

        # 종합 판단
        flags: list[str] = []
        if days_earn <= 3:
            flags.append(f"🔴실적D-{days_earn}")
        elif days_earn <= 7:
            flags.append(f"🟡실적D-{days_earn}")
        if rec_mean >= 4.0 and ana.get("analyst_count", 0) >= 5:
            flags.append(f"📉Rec{rec_mean:.1f}")
        if ins_net <= -3:
            flags.append(f"🔻Ins{ins_net}")
        if price_data["sma200_ratio"] and price_data["sma200_ratio"] < -5:
            flags.append("📉<SMA200")

        action = "HOLD"
        if days_earn <= 3:
            action = "REDUCE 50%"
        elif rec_mean >= 4.0 and ana.get("analyst_count", 0) >= 5:
            action = "REVIEW SELL"
        elif ins_net <= -3:
            action = "CAUTION"
        elif len(flags) >= 2:
            action = "CAUTION"

        print(f"  {sym:5s} {strat:5s} {_fmt_price(current):>10s} "
              f"{_fmt_pct(chg_1d):>8s} {_fmt_pct(chg_1m):>8s} "
              f"${unreal_pl:>+8.2f} "
              f"{'D-'+str(days_earn) if days_earn<99 else '   -':>6s} "
              f"{rec_mean:>5.1f} "
              f"{ins_net:>+6d}  "
              f"{action}  {' '.join(flags)}")

        results.append({
            "symbol": sym,
            "strategy": strat,
            "current": current,
            "chg_1d": chg_1d,
            "chg_1m": chg_1m,
            "unrealized_pl": unreal_pl,
            "days_to_earnings": days_earn,
            "rec_mean": rec_mean,
            "insider_net": ins_net,
            "sma200_ratio": price_data["sma200_ratio"],
            "action": action,
            "flags": flags,
        })

    return results


# ═══════════════════════════════════════════════════════════════════
# SECTION 5: 매매 권고 요약
# ═══════════════════════════════════════════════════════════════════

def section_recommendations(results: list[dict]) -> None:
    _section("SECTION 5: 매매 권고 요약", "🎯")

    reduce_list = [r for r in results if r["action"] == "REDUCE 50%"]
    review_list = [r for r in results if r["action"] == "REVIEW SELL"]
    caution_list = [r for r in results if r["action"] == "CAUTION"]
    hold_list = [r for r in results if r["action"] == "HOLD"]

    if reduce_list:
        print("\n  🔴 REDUCE 50% (실적발표 임박, 이벤트 리스크)")
        for r in reduce_list:
            print(f"    {r['symbol']:5s} {r['strategy']}  "
                  f"D-{r['days_to_earnings']}  P&L=${r['unrealized_pl']:+.2f}")

    if review_list:
        print("\n  📉 REVIEW SELL (애널리스트 SELL 컨센서스)")
        for r in review_list:
            print(f"    {r['symbol']:5s} {r['strategy']}  "
                  f"rec={r['rec_mean']:.1f}  P&L=${r['unrealized_pl']:+.2f}")

    if caution_list:
        print("\n  🟡 CAUTION (2개 이상 경고 신호)")
        for r in caution_list:
            print(f"    {r['symbol']:5s} {r['strategy']}  "
                  f"P&L=${r['unrealized_pl']:+.2f}  flags={','.join(r['flags'])}")

    if hold_list:
        print(f"\n  ✅ HOLD 정상 보유: {len(hold_list)}종목")
        print("    " + ", ".join(r["symbol"] for r in hold_list))

    # 통계
    total_pnl = sum(r["unrealized_pl"] for r in results)
    winners = [r for r in results if r["unrealized_pl"] > 0]
    losers = [r for r in results if r["unrealized_pl"] < 0]
    print(f"\n  📈 통계: 총 미실현 P&L ${total_pnl:+.2f}  "
          f"(수익 {len(winners)}종목, 손실 {len(losers)}종목)")


# ═══════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Market Analysis Report")
    parser.add_argument("--symbols", nargs="*", help="분석할 종목 (미지정 시 보유 전 종목)")
    parser.add_argument("--no-macro", action="store_true", help="매크로 섹션 건너뛰기")
    parser.add_argument("--no-global", action="store_true", help="글로벌 시장 섹션 건너뛰기")
    parser.add_argument("--no-sentiment", action="store_true", help="Gemini 뉴스 분석 건너뛰기")
    args = parser.parse_args()

    today = date.today().strftime("%Y-%m-%d")
    print(f"\n╔{'═'*68}╗")
    print(f"║  MARKET ANALYSIS REPORT   {today:>40}  ║")
    print(f"╚{'═'*68}╝")

    # 포트폴리오 로드
    portfolios = _load_portfolios()
    account_total = portfolios.get("account_total", 0)

    # 대상 종목 결정
    if args.symbols:
        symbols = [s.upper() for s in args.symbols]
    else:
        symbols = sorted(set(
            sym
            for strat in portfolios.get("strategies", {}).values()
            for sym in strat.get("positions", {})
        ))

    print(f"\n  Alpaca 잔고: ${account_total:,.2f}")
    print(f"  분석 종목: {len(symbols)}개")
    print(f"  실행 시각: {date.today().strftime('%Y-%m-%d')}")

    if not args.no_macro:
        section_macro()

    if not args.no_macro:
        section_us_market()

    if not args.no_global:
        section_global()

    results = section_holdings(symbols, portfolios, analyze_sentiment=not args.no_sentiment)
    section_recommendations(results)

    print(f"\n{'═'*70}")
    print("  완료. 매수/매도 결정 후 Claude Code에 지시 → Alpaca 체결")
    print(f"{'═'*70}\n")


if __name__ == "__main__":
    main()
