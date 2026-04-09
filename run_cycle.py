#!/usr/bin/env python3
"""Paper Trading Cycle -7-phase automated pipeline.

Usage:
    python run_cycle.py --phase all              # Run full cycle
    python run_cycle.py --phase all --dry-run    # Simulate without orders
    python run_cycle.py --phase data             # Data fetch only
    python run_cycle.py --phase signals          # Generate signals only
    python run_cycle.py --phase risk             # Risk validation only
    python run_cycle.py --phase execute          # Execute approved signals
    python run_cycle.py --phase report           # Generate report only

Phases:
    1. DATA      -fetch market data + Alpaca positions
    2. SIGNALS   -run strategy modules, generate signals
    3. RISK      -validate each signal through risk gates
    4. RESOLVE   -resolve conflicting signals (rule-based)
    5. EXECUTE   -submit orders to Alpaca Paper API
    6. REPORT    -update performance.json + daily report
    7. COMMIT    -(handled by GitHub Actions, not this script)
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
    """Fetch market data and current Alpaca positions."""
    print("[Phase 1: DATA] Fetching market data...")

    from strategies.momentum import fetch_momentum_data

    # Fetch price data for all strategies (momentum needs 252+ days)
    market_data = fetch_momentum_data(days=400)
    prices = market_data.get("prices")

    if prices is not None and not prices.empty:
        print(f"  Fetched {len(prices.columns)} symbols, {len(prices)} days")
    else:
        print("  WARNING: No price data fetched")

    # Try to fetch Alpaca positions (may fail if no .env)
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

    # Save snapshot metadata (not the full price data -too large)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)

    return market_data


# ─── Phase 2: SIGNALS ───────────────────────────────────────────────────

def phase_signals(market_data: dict) -> list:
    """Run all strategy modules and collect signals."""
    print("[Phase 2: SIGNALS] Running strategy modules...")

    from strategies.momentum import MomentumStrategy

    strategies = [
        MomentumStrategy(),
        # Phase 4 will add: ValueQualityStrategy(), QuantFactorStrategy(), LeveragedETFStrategy()
    ]

    all_signals = []
    for strat in strategies:
        signals = strat.generate_signals(market_data)
        print(f"  {strat.name}: {len(signals)} signals")
        for s in signals:
            print(f"    {s.symbol} {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f} -{s.reason}")
        all_signals.extend(signals)

    return all_signals


# ─── Phase 3: RISK ──────────────────────────────────────────────────────

def phase_risk(signals: list) -> list:
    """Validate each signal through risk gates."""
    print("[Phase 3: RISK] Validating signals...")

    from execution.risk_validator import validate_signal

    portfolios = load_portfolios()
    approved = []

    for signal in signals:
        strat_data = portfolios["strategies"].get(signal.strategy, {})
        capital = strat_data.get("allocated", 0)
        cash = strat_data.get("cash", 0)

        # Build current positions map for this strategy
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

    print(f"  Approved: {len(approved)} / {len(signals)}")
    return approved


# ─── Phase 4: RESOLVE ───────────────────────────────────────────────────

def phase_resolve(signals: list) -> list:
    """Resolve conflicting signals (same symbol, different strategies)."""
    print("[Phase 4: RESOLVE] Checking for conflicts...")

    # Group signals by symbol
    by_symbol: dict[str, list] = {}
    for s in signals:
        by_symbol.setdefault(s.symbol, []).append(s)

    resolved = []
    for symbol, group in by_symbol.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        # Conflict: multiple strategies want the same symbol
        buy_signals = [s for s in group if s.direction == Direction.BUY]
        sell_signals = [s for s in group if s.direction == Direction.SELL]

        if buy_signals and sell_signals:
            # BUY vs SELL conflict -pick higher confidence
            all_sorted = sorted(group, key=lambda s: s.confidence, reverse=True)
            winner = all_sorted[0]
            print(f"  CONFLICT {symbol}: {len(buy_signals)} BUY vs {len(sell_signals)} SELL → {winner.strategy} {winner.direction.value} (conf={winner.confidence:.2f})")
            resolved.append(winner)
        else:
            # Multiple strategies want same direction -allow all (different sub-portfolios)
            resolved.extend(group)

    from strategies.base_strategy import Direction
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


# ─── Phase 6: REPORT ────────────────────────────────────────────────────

def phase_report(signals: list, execution_results: list):
    """Update performance.json and generate daily report."""
    print("[Phase 6: REPORT] Generating report...")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    portfolios = load_portfolios()

    # Update NAV history (simplified -full version will use Alpaca positions)
    for code, strat in portfolios["strategies"].items():
        nav = strat["cash"]
        for sym, pos in strat.get("positions", {}).items():
            nav += pos.get("qty", 0) * pos.get("current", 0)

        strat.setdefault("nav_history", []).append({
            "date": today,
            "nav": round(nav, 2),
        })

    save_portfolios(portfolios)

    # Generate daily report markdown
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{today}-daily.md"

    lines = [
        f"# Daily Trading Report -{today}",
        "",
        "## Signals Generated",
        f"Total: {len(signals)}",
        "",
    ]

    for s in signals:
        lines.append(f"- **{s.symbol}** ({s.strategy}) {s.direction.value} {s.weight_pct:.0%} conf={s.confidence:.2f}")
        lines.append(f"  {s.reason}")

    lines.extend(["", "## Execution Results", ""])
    for r in execution_results:
        lines.append(f"- {r.get('symbol', '?')}: {r.get('status', '?')}")
        if r.get("error_reason"):
            lines.append(f"  Reason: {r['error_reason']}")

    lines.extend(["", "## Portfolio State", ""])
    for code, strat in portfolios["strategies"].items():
        nav_list = strat.get("nav_history", [])
        latest_nav = nav_list[-1]["nav"] if nav_list else strat["allocated"]
        lines.append(f"- **{code}** ({strat['name']}): NAV=${latest_nav:,.2f} / Allocated=${strat['allocated']:,.2f}")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report saved: {report_path}")


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Paper Trading Cycle")
    parser.add_argument("--phase", required=True, choices=["all", "data", "signals", "risk", "resolve", "execute", "report"])
    parser.add_argument("--dry-run", action="store_true", help="Simulate without placing real orders")
    args = parser.parse_args()

    print(f"=== Paper Trading Cycle -{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    # Import Direction here for phase_resolve
    from strategies.base_strategy import Direction

    if args.phase in ("all", "data"):
        market_data = phase_data()
        print()
    else:
        market_data = None

    if args.phase in ("all", "signals"):
        if market_data is None:
            from strategies.momentum import fetch_momentum_data
            market_data = fetch_momentum_data(days=400)
        signals = phase_signals(market_data)
        print()
    else:
        signals = []

    if args.phase in ("all", "risk"):
        approved = phase_risk(signals)
        print()
    else:
        approved = signals

    if args.phase in ("all", "resolve"):
        resolved = phase_resolve(approved)
        print()
    else:
        resolved = approved

    if args.phase in ("all", "execute"):
        results = phase_execute(resolved, dry_run=args.dry_run)
        print()
    else:
        results = []

    if args.phase in ("all", "report"):
        phase_report(resolved, results)
        print()

    print("=== Cycle Complete ===")


if __name__ == "__main__":
    main()
