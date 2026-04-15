#!/usr/bin/env python
# scripts/backtest.py
"""Walk-forward backtest CLI entry point.

Usage:
    python scripts/backtest.py --start 2020-01-01 --end 2025-12-31
    python scripts/backtest.py --start 2023-01-01 --end 2024-01-01 --no-cache
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "state" / "backtest_cache"

import sys
sys.path.insert(0, str(ROOT))

from scripts.backtest_data import fetch_historical
from scripts.backtest_core import run_walk_forward, StrategyResult, BacktestReport


def _result_to_dict(r: StrategyResult) -> dict:
    return {
        "total_return": round(r.total_return * 100, 2),
        "sharpe": round(r.sharpe, 3) if r.sharpe is not None else None,
        "mdd": round(r.mdd * 100, 2),
        "win_rate": round(r.win_rate * 100, 1),
        "alpha_vs_spy": round(r.alpha_vs_spy * 100, 2),
        "equity_curve": {
            d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d): round(float(v), 2)
            for d, v in r.equity_curve.items()
        },
        "trade_count": len(r.trades),
        "notes": r.notes,
    }


def write_report_json(report: BacktestReport, out_path: Path) -> None:
    data = {
        "config": {
            "start": report.start,
            "end": report.end,
            "train_days": 252,
            "oos_days": 126,
        },
        "regime_timeline": report.regime_timeline,
        "windows": [
            {
                "train_start": w.train_start.strftime("%Y-%m-%d"),
                "train_end": w.train_end.strftime("%Y-%m-%d"),
                "oos_start": w.oos_start.strftime("%Y-%m-%d"),
                "oos_end": w.oos_end.strftime("%Y-%m-%d"),
            }
            for w in report.windows
        ],
        "strategies": {k: _result_to_dict(v) for k, v in report.strategies.items()},
        "benchmarks": {k: _result_to_dict(v) for k, v in report.benchmarks.items()},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"  [backtest] Report saved → {out_path}")


def print_summary_table(report: BacktestReport) -> None:
    all_results = {**report.strategies, **report.benchmarks}
    print()
    print("=" * 80)
    print(f"  Walk-Forward Backtest Results: {report.start} → {report.end}")
    print(f"  Windows: {len(report.windows)}")
    print("=" * 80)
    print(f"{'Strategy':<12} {'Return%':>8} {'Sharpe':>8} {'MDD%':>8} {'Win%':>7} {'Alpha%':>8}")
    print("-" * 80)
    for name, r in all_results.items():
        prefix = "  " if name in report.strategies else "~ "
        sharpe_str = f"{r.sharpe:8.2f}" if r.sharpe is not None else "    None"
        print(
            f"{prefix + name:<12} "
            f"{r.total_return*100:>7.1f}% "
            f"{sharpe_str} "
            f"{r.mdd*100:>7.1f}% "
            f"{r.win_rate*100:>6.1f}% "
            f"{r.alpha_vs_spy*100:>7.1f}%"
        )
    print("=" * 80)
    print("  ~ = benchmark")
    print()


def main():
    ap = argparse.ArgumentParser(
        description="Walk-forward backtest for STOCK_WORK strategies"
    )
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--out", default="state/backtest_results.json")
    ap.add_argument("--no-cache", action="store_true", help="Skip cache, re-download data")
    args = ap.parse_args()

    cache_dir = None if args.no_cache else CACHE_DIR

    prices, spy, vix, ff5 = fetch_historical(args.start, args.end, cache_dir=cache_dir)

    if len(prices) == 0:
        print("ERROR: No price data fetched. Check dates or network connection.")
        sys.exit(1)

    print(f"  [backtest] Prices: {len(prices)} days × {len(prices.columns)} tickers")
    print(f"  [backtest] SPY: {len(spy)} days  |  VIX: {len(vix)} days  |  FF5: {len(ff5)} days")

    report = run_walk_forward(prices, spy, vix, ff5, capital=args.capital)

    out_path = ROOT / args.out
    write_report_json(report, out_path)
    print_summary_table(report)


if __name__ == "__main__":
    main()
