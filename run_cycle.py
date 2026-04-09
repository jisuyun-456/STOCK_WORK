#!/usr/bin/env python3
"""Paper Trading Cycle -9-phase automated pipeline (Phase 2.5 Research Overlay).

Usage:
    python run_cycle.py --phase all              # Run full cycle
    python run_cycle.py --phase all --dry-run    # Simulate without orders
    python run_cycle.py --phase data             # Data fetch only
    python run_cycle.py --phase signals          # Generate signals only
    python run_cycle.py --phase research         # Research overlay only
    python run_cycle.py --phase risk             # Risk validation only
    python run_cycle.py --phase execute          # Execute approved signals
    python run_cycle.py --phase report           # Generate report only

    --research-mode {full|selective|skip}         # Research depth (default: full)
    --no-cache                                    # Bypass research cache

Phases:
    1.   DATA      -fetch market data + Alpaca positions
    2.   SIGNALS   -run strategy modules, generate signals
    2.5  RESEARCH  -Research Division 5-agent parallel analysis (NEW)
    3.   RISK      -validate each signal through risk gates
    3.5  APPEAL    -Risk-FAIL signals → Research appeal (NEW)
    4.   RESOLVE   -resolve conflicting signals (rule-based)
    5.   EXECUTE   -submit orders to Alpaca Paper API
    6.   REPORT    -update performance.json + daily report
    7.   COMMIT    -(handled by GitHub Actions, not this script)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
STATE_DIR = ROOT / "state"
PORTFOLIOS_PATH = STATE_DIR / "portfolios.json"
PERFORMANCE_PATH = STATE_DIR / "performance.json"
SNAPSHOT_PATH = STATE_DIR / "snapshot.json"
REPORTS_DIR = ROOT / "reports" / "daily"


def load_portfolios() -> dict:
    with open(PORTFOLIOS_PATH) as f:
        return json.load(f)


def save_portfolios(data: dict):
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(PORTFOLIOS_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─── Phase 1: DATA ──────────────────────────────────────────────────────

def phase_data() -> dict:
    """Fetch all market data for 4 strategies + news."""
    print("[Phase 1: DATA] Fetching market data...")

    from strategies.momentum import fetch_momentum_data

    market_data = fetch_momentum_data(days=400)
    prices = market_data.get("prices")

    if prices is not None and not prices.empty:
        print(f"  Fetched {len(prices.columns)} symbols, {len(prices)} days")
    else:
        print("  WARNING: No price data fetched")

    alpaca_positions = []
    try:
        from execution.alpaca_client import get_positions, get_account_info
        alpaca_positions = get_positions()
        account = get_account_info()
        print(f"  Alpaca account: ${account['equity']:,.2f} equity, mode={account['mode']}")
    except Exception as e:
        print(f"  Alpaca connection skipped: {e}")

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_count": len(prices.columns) if prices is not None else 0,
        "days_count": len(prices) if prices is not None else 0,
        "alpaca_positions": alpaca_positions,
    }

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    # VAL: FMP + yfinance 재무 데이터
    try:
        from strategies.value_quality import fetch_value_data
        val_data = fetch_value_data()
        market_data["fundamentals"] = val_data.get("fundamentals", {})
        print(f"  VAL data: {len(market_data['fundamentals'])} stocks")
    except Exception as e:
        print(f"  VAL data fetch failed: {e}")
        market_data["fundamentals"] = {}

    # QNT: Kenneth French 팩터 데이터
    try:
        from strategies.quant_factor import fetch_factor_data
        qnt_data = fetch_factor_data()
        market_data["factors"] = qnt_data.get("factors")
        market_data["qnt_prices"] = qnt_data.get("prices")  # QNT 전용 가격 추가
        print(f"  QNT factor data: {'loaded' if market_data['factors'] is not None else 'failed'}")
    except Exception as e:
        print(f"  QNT factor fetch failed: {e}")
        market_data["factors"] = None

    # LEV: 레버리지 ETF 가격
    try:
        from strategies.leveraged_etf import fetch_leveraged_data
        lev_data = fetch_leveraged_data()
        market_data["leveraged"] = lev_data
        lev_prices = lev_data.get('prices')
        etf_count = len(lev_prices.columns) if lev_prices is not None and hasattr(lev_prices, 'columns') else 0
        print(f"  LEV data: {etf_count} ETFs")
    except Exception as e:
        print(f"  LEV data fetch failed: {e}")
        market_data["leveraged"] = {"prices": None}

    # 뉴스 수집 (종목 리스트는 나중에 결정 — 여기서는 매크로만)
    try:
        from news.fetcher import fetch_macro_news
        market_data["news"] = {"_MACRO": fetch_macro_news()}
        print(f"  Macro news: {len(market_data['news']['_MACRO'])} articles")
    except Exception as e:
        print(f"  News fetch failed: {e}")
        market_data["news"] = {}

    return market_data


# ─── Phase 1.5: REGIME ──────────────────────────────────────────────────

def phase_regime(market_data: dict) -> tuple:
    """Phase 1.5: Regime Detection + Dynamic Allocation."""
    print("[Phase 1.5: REGIME] Detecting market regime...")

    # 뉴스 감성 분석
    news_sentiment_score = 0.0
    try:
        from news.sentiment import analyze_sentiment
        macro_news = market_data.get("news", {}).get("_MACRO", [])
        if macro_news:
            result = analyze_sentiment("_MACRO", macro_news)
            news_sentiment_score = result.score
            print(f"  News sentiment: {news_sentiment_score:+.2f} ({result.summary})")
        else:
            print("  News sentiment: 0.00 (no macro news)")
    except Exception as e:
        print(f"  News sentiment failed: {e} (using 0.0)")

    # 확장된 Regime Detection
    try:
        from research.consensus import detect_regime_enhanced
        regime_info = detect_regime_enhanced(news_sentiment_score)
    except Exception as e:
        print(f"  Regime detection failed: {e}")
        from research.models import RegimeDetection
        regime_info = RegimeDetection(
            regime="NEUTRAL", sp500_vs_sma200=1.0, vix_level=20.0,
            reasoning=f"Fallback: {e}", timestamp=datetime.now(timezone.utc).isoformat()
        )

    # 동적 배분
    from strategies.regime_allocator import allocate

    portfolios = load_portfolios()
    total = portfolios.get("account_total", 100000)
    allocations = allocate(regime_info.regime, total)

    print(f"  Regime: {regime_info.regime} | VIX: {regime_info.vix_level}")
    print(f"  Allocations: {', '.join(f'{k}=${v:,.0f}' for k, v in allocations.items())}")

    return regime_info, allocations


# ─── Phase 2: SIGNALS ───────────────────────────────────────────────────

def phase_signals(market_data: dict, regime: str = "NEUTRAL", allocations: dict = None) -> list:
    """Run all strategy modules and collect signals."""
    print("[Phase 2: SIGNALS] Running strategy modules...")

    from strategies.momentum import MomentumStrategy
    from strategies.value_quality import ValueQualityStrategy
    from strategies.quant_factor import QuantFactorStrategy
    from strategies.leveraged_etf import LeveragedETFStrategy

    strategies = [
        MomentumStrategy(),
        ValueQualityStrategy(),
        QuantFactorStrategy(),
        LeveragedETFStrategy(),
    ]

    all_signals = []
    for strat in strategies:
        # 배분 $1 미만이면 사실상 0으로 스킵 (부동소수점 비교 회피)
        if allocations and allocations.get(strat.name, 0) < 1.0:
            print(f"  {strat.name}: SKIPPED (regime={regime}, allocation=$0)")
            continue

        # Regime 정보 주입
        strat.regime = regime

        signals = strat.generate_signals(market_data)
        print(f"  {strat.name}: {len(signals)} signals")
        for s in signals:
            print(f"    {s.symbol} {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f} — {s.reason}")
        all_signals.extend(signals)

    return all_signals


# ─── Phase 2.5: RESEARCH (NEW) ──────────────────────────────────────────

def phase_research(signals: list, market_data: dict, research_mode: str, no_cache: bool):
    """Run Research Overlay -5-agent parallel analysis + confidence adjustment."""
    from research.overlay import run_research_overlay

    portfolios = load_portfolios()
    adjusted_signals, regime, verdicts = run_research_overlay(
        signals=signals,
        market_data=market_data,
        portfolio_state=portfolios,
        research_mode=research_mode,
        no_cache=no_cache,
    )
    return adjusted_signals, regime, verdicts


# ─── Phase 3: RISK ──────────────────────────────────────────────────────

def phase_risk(signals: list) -> tuple[list, list, list]:
    """Validate each signal through risk gates.

    Returns:
        (approved, failed_signals, failed_details)
    """
    print("[Phase 3: RISK] Validating signals...")

    from execution.risk_validator import validate_signal

    portfolios = load_portfolios()
    approved = []
    failed_signals = []
    failed_details = []

    for signal in signals:
        strat_data = portfolios["strategies"].get(signal.strategy, {})
        capital = strat_data.get("allocated", 0)
        cash = strat_data.get("cash", 0)

        current_positions = {}
        for sym, pos in strat_data.get("positions", {}).items():
            current_positions[sym] = pos.get("qty", 0) * pos.get("current", 0)

        trade_value = capital * signal.weight_pct

        passed, results = validate_signal(
            symbol=signal.symbol,
            side=signal.direction.value,
            trade_value=trade_value,
            strategy_capital=capital,
            strategy_cash=cash,
            current_positions=current_positions,
        )

        status = "PASS" if passed else "FAIL"
        failed_checks = [r.check_name for r in results if not r.passed]
        print(f"  {signal.symbol} ({signal.strategy}): {status}", end="")
        if failed_checks:
            print(f" -failed: {', '.join(failed_checks)}")
        else:
            print()

        if passed:
            approved.append(signal)
        else:
            failed_signals.append(signal)
            failed_details.append({
                "symbol": signal.symbol,
                "strategy": signal.strategy,
                "failed_checks": failed_checks,
            })

    print(f"  Approved: {len(approved)} / {len(signals)}")
    return approved, failed_signals, failed_details


# ─── Phase 3.5: APPEAL (NEW) ────────────────────────────────────────────

def phase_appeal(failed_signals: list, failed_details: list,
                 research_verdicts: dict, market_data: dict, regime):
    """Appeal loop: Risk-FAIL signals get Research Division re-review."""
    from research.overlay import run_appeal

    portfolios = load_portfolios()
    appealed = run_appeal(
        failed_signals=failed_signals,
        risk_results=failed_details,
        research_verdicts=research_verdicts,
        market_data=market_data,
        portfolio_state=portfolios,
        regime=regime,
    )
    return appealed


# ─── Phase 4: RESOLVE ───────────────────────────────────────────────────

def phase_resolve(signals: list) -> list:
    """Resolve conflicting signals (same symbol, different strategies)."""
    print("[Phase 4: RESOLVE] Checking for conflicts...")

    from strategies.base_strategy import Direction

    by_symbol: dict[str, list] = {}
    for s in signals:
        by_symbol.setdefault(s.symbol, []).append(s)

    resolved = []
    for symbol, group in by_symbol.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        buy_signals = [s for s in group if s.direction == Direction.BUY]
        sell_signals = [s for s in group if s.direction == Direction.SELL]

        if buy_signals and sell_signals:
            all_sorted = sorted(group, key=lambda s: s.confidence, reverse=True)
            winner = all_sorted[0]
            print(f"  CONFLICT {symbol}: {len(buy_signals)} BUY vs {len(sell_signals)} SELL → {winner.strategy} {winner.direction.value} (conf={winner.confidence:.2f})")
            resolved.append(winner)
        else:
            resolved.extend(group)

    print(f"  Resolved: {len(resolved)} signals")
    return resolved


# ─── Phase 5: EXECUTE ───────────────────────────────────────────────────

def phase_execute(signals: list, dry_run: bool = False) -> list:
    """Submit orders to Alpaca."""
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"[Phase 5: EXECUTE] Submitting orders ({mode})...")

    from execution.order_manager import execute_signals

    portfolios = load_portfolios()
    allocations = {}
    for code, strat in portfolios["strategies"].items():
        allocations[code] = {
            "capital": strat["allocated"],
            "cash": strat["cash"],
        }

    results = execute_signals(signals, allocations, dry_run=dry_run)

    for r in results:
        symbol = r.get("symbol", "?")
        status = r.get("status", "?")
        print(f"  {symbol}: {status}")

    return results


# ─── Phase 5.5: REBALANCE (NEW) ────────────────────────────────────────

def phase_rebalance(market_data: dict, dry_run: bool = False) -> tuple[list, list]:
    """Check rebalancing schedules, generate rebalance orders if triggered."""
    from scripts.rebalancer import run_rebalance_check

    portfolios = load_portfolios()
    result = run_rebalance_check(portfolios, market_data, dry_run=dry_run)

    if result["rebalanced"] and not dry_run:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for code in result["rebalanced"]:
            portfolios["strategies"][code]["last_rebalance"] = today
        save_portfolios(portfolios)

    return result.get("signals", []), result.get("rebalanced", [])


# ─── Phase 6: REPORT ────────────────────────────────────────────────────

def phase_report(signals: list, execution_results: list, regime=None, rebalanced_strategies: list = None):
    """Update performance.json, generate daily report + dashboard."""
    print("[Phase 6: REPORT] Generating report...")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    portfolios = load_portfolios()

    # Update NAV history (deduplicate: keep only one entry per date)
    for code, strat in portfolios["strategies"].items():
        nav = strat["cash"]
        for sym, pos in strat.get("positions", {}).items():
            nav += pos.get("qty", 0) * pos.get("current", 0)

        nav_history = strat.setdefault("nav_history", [])
        # Full dedup: remove all entries with today's date, then append once
        nav_history[:] = [h for h in nav_history if h.get("date") != today]
        nav_history.append({"date": today, "nav": round(nav, 2)})

    save_portfolios(portfolios)

    # ─── Performance Calculator ───
    trade_log = []
    try:
        from scripts.performance_calculator import (
            load_existing_performance, load_trade_log,
            fetch_benchmark_prices, build_daily_snapshot, append_and_save,
            generate_strategy_monthly_report,
        )

        benchmark_prices = fetch_benchmark_prices()
        trade_log = load_trade_log()
        existing_perf = load_existing_performance()

        regime_str = _extract_regime_str(regime)
        snapshot = build_daily_snapshot(
            portfolios, regime_str, len(signals),
            benchmark_prices, rebalanced_strategies or [],
        )
        performance_data = append_and_save(existing_perf, snapshot, portfolios, trade_log)

        # Monthly strategy reports (all strategies)
        strategy_report_dir = ROOT / "reports" / "strategy"
        for code, strat in portfolios["strategies"].items():
            generate_strategy_monthly_report(
                code, strat["name"], performance_data, trade_log, strategy_report_dir,
            )
    except Exception as e:
        print(f"  [perf] Performance calculation failed: {e}")
        import traceback; traceback.print_exc()
        performance_data = {}
        benchmark_prices = {}

    # ─── Paper Dashboard ───
    try:
        from scripts.dashboard_generator import generate_paper_dashboard
        regime_str = _extract_regime_str(regime)
        if not trade_log:
            trade_log = load_trade_log()
        generate_paper_dashboard(
            performance_data, portfolios, trade_log, regime_str,
            output_path=str(ROOT / "docs" / "paper_dashboard.html"),
        )
    except Exception as e:
        print(f"  [dashboard] Paper dashboard failed: {e}")

    # ─── Daily Report Markdown ───
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today}-daily.md"

    regime_str = _extract_regime_str(regime)
    regime_reasoning = _extract_regime_reasoning(regime)

    lines = [f"# Daily Trading Report — {today}", ""]

    if regime_str:
        lines.extend([f"## Market Regime: {regime_str}", f"{regime_reasoning}", ""])

    # Performance Summary Table
    strats = performance_data.get("strategies", {})
    total_info = strats.get("TOTAL", {})
    lines.extend([
        "## Performance Summary",
        "",
        "| Strategy | NAV | Today | Total | MDD | Sharpe | Trades |",
        "|----------|-----|-------|-------|-----|--------|--------|",
    ])
    for code in ["MOM", "VAL", "QNT", "LEV"]:
        m = strats.get(code, {})
        lines.append(
            f"| {code} | ${m.get('current_nav', 0):,.0f} | "
            f"{m.get('daily_return_pct', 0):+.2f}% | "
            f"{m.get('total_return_pct', 0):+.2f}% | "
            f"{m.get('mdd_pct', 0):.2f}% | "
            f"{m.get('sharpe_ratio', 'N/A')} | "
            f"{m.get('trade_count', 0)} |"
        )
    lines.append(
        f"| **TOTAL** | **${total_info.get('current_nav', 0):,.0f}** | | "
        f"**{total_info.get('total_return_pct', 0):+.2f}%** | | | |"
    )
    spy_r = total_info.get("spy_return_pct", 0)
    qqq_r = total_info.get("qqq_return_pct", 0)
    lines.append(f"| SPY | | | {spy_r:+.2f}% | | | |")
    lines.append(f"| QQQ | | | {qqq_r:+.2f}% | | | |")
    lines.append("")

    # Signals
    lines.extend(["## Signals Generated", f"Total: {len(signals)}", ""])
    for s in signals:
        lines.append(f"- **{s.symbol}** ({s.strategy}) {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f}")
        lines.append(f"  {s.reason}")

    # Execution
    lines.extend(["", "## Execution Results", ""])
    for r in execution_results:
        lines.append(f"- {r.get('symbol', '?')}: {r.get('status', '?')}")
        if r.get("error_reason"):
            lines.append(f"  Reason: {r['error_reason']}")

    # Rebalances
    if rebalanced_strategies:
        lines.extend(["", "## Rebalances", ""])
        for code in rebalanced_strategies:
            lines.append(f"- **{code}** rebalanced")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report saved: {report_path}")


def _extract_regime_str(regime) -> str:
    if regime is None:
        return "UNKNOWN"
    if hasattr(regime, 'regime'):
        return regime.regime
    if isinstance(regime, str):
        return regime
    return "UNKNOWN"


def _extract_regime_reasoning(regime) -> str:
    if regime and hasattr(regime, 'reasoning'):
        return getattr(regime, 'reasoning', '')
    return ''


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cycle (Phase 2.5)")
    parser.add_argument("--phase", required=True,
                        choices=["all", "data", "signals", "research", "risk", "resolve", "rebalance", "execute", "report"])
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing real orders")
    parser.add_argument("--research-mode", default=None, choices=["full", "selective", "skip"],
                        help="Research overlay depth (default: full, dry-run default: selective)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass research cache")
    args = parser.parse_args()

    # Default research mode: selective for dry-run, full otherwise
    research_mode = args.research_mode
    if research_mode is None:
        research_mode = "selective" if args.dry_run else "full"

    print(f"=== Paper Trading Cycle -{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'} | Research: {research_mode}")
    print()

    from strategies.base_strategy import Direction

    # Phase 1: DATA
    if args.phase in ("all", "data"):
        market_data = phase_data()
        print()
    else:
        market_data = None

    # Phase 1.5: REGIME (NEW)
    regime_info = None
    allocations = None
    if args.phase in ("all",):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        regime_info, allocations = phase_regime(market_data)
        regime = regime_info.regime if regime_info else "NEUTRAL"
        print()
    else:
        regime = "NEUTRAL"

    # Phase 2: SIGNALS
    if args.phase in ("all", "signals"):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        signals = phase_signals(market_data, regime=regime, allocations=allocations)
        print()
    else:
        signals = []

    # Phase 2.5: RESEARCH
    research_verdicts = {}
    if args.phase in ("all", "research"):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        signals, _research_regime, research_verdicts = phase_research(
            signals, market_data, research_mode, args.no_cache
        )
        print()

    # Phase 3: RISK
    failed_signals = []
    failed_details = []
    if args.phase in ("all", "risk"):
        approved, failed_signals, failed_details = phase_risk(signals)
        print()
    else:
        approved = signals

    # Phase 3.5: APPEAL
    if args.phase in ("all",) and failed_signals and research_mode != "skip":
        appealed = phase_appeal(
            failed_signals, failed_details, research_verdicts, market_data, regime
        )
        approved.extend(appealed)
        print()

    # Phase 4: RESOLVE
    if args.phase in ("all", "resolve"):
        resolved = phase_resolve(approved)
        print()
    else:
        resolved = approved

    # Phase 5.5: REBALANCE (NEW)
    rebalanced_strategies = []
    if args.phase in ("all", "rebalance"):
        if market_data is None:
            market_data = phase_data()  # Full data fetch (LEV/VAL/QNT need their own data)
        rebalance_signals, rebalanced_strategies = phase_rebalance(market_data, dry_run=args.dry_run)
        resolved = resolved + rebalance_signals
        print()

    # Phase 5: EXECUTE
    if args.phase in ("all", "execute"):
        results = phase_execute(resolved, dry_run=args.dry_run)
        print()
    else:
        results = []

    # Phase 6: REPORT
    if args.phase in ("all", "report"):
        phase_report(resolved, results, regime=regime_info, rebalanced_strategies=rebalanced_strategies)
        print()

    print("=== Cycle Complete ===")


if __name__ == "__main__":
    main()
