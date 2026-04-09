"""Performance Calculator — 전략별/전체 성과 메트릭 계산 + performance.json 관리.

Metrics:
  - Total Return %, Daily Return %
  - Maximum Drawdown (MDD)
  - Sharpe Ratio (annualized, Rf=4%)
  - Win Rate (from trade_log.jsonl)
  - Benchmark comparison (SPY, QQQ)
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

# ─── Paths ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
STATE_DIR = ROOT / "state"
PERFORMANCE_PATH = STATE_DIR / "performance.json"
TRADE_LOG_PATH = STATE_DIR / "trade_log.jsonl"

RISK_FREE_RATE = 0.04  # 연 4%


# ─── File I/O ────────────────────────────────────────────────────────────

def load_existing_performance() -> dict:
    """Load performance.json or return empty scaffold."""
    if PERFORMANCE_PATH.exists():
        with open(PERFORMANCE_PATH) as f:
            return json.load(f)
    return {}


def load_trade_log() -> list[dict]:
    """Load all entries from trade_log.jsonl."""
    entries = []
    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    return entries


# ─── Benchmark ───────────────────────────────────────────────────────────

def fetch_benchmark_prices() -> dict[str, float]:
    """Fetch current SPY and QQQ prices via yfinance."""
    prices = {}
    for ticker in ["SPY", "QQQ"]:
        try:
            info = yf.Ticker(ticker).fast_info
            prices[ticker] = float(info["last_price"])
        except Exception as e:
            print(f"  [perf] WARNING: {ticker} price fetch failed: {e}")
            prices[ticker] = 0.0
    return prices


# ─── Metric Computation ─────────────────────────────────────────────────

def compute_strategy_metrics(
    strategy_code: str,
    nav_history: list[dict],
    initial_nav: float,
    trade_entries: list[dict],
) -> dict:
    """Compute performance metrics for a single strategy.

    Args:
        strategy_code: MOM/VAL/QNT/LEV
        nav_history: [{date, nav}, ...] from portfolios.json
        initial_nav: starting NAV (allocated amount)
        trade_entries: trade_log entries filtered for this strategy

    Returns:
        {current_nav, total_return_pct, daily_return_pct, mdd_pct,
         sharpe_ratio, win_rate, trade_count, peak_nav}
    """
    if not nav_history:
        return _empty_metrics(initial_nav)

    navs = [h["nav"] for h in nav_history]
    current_nav = navs[-1]

    # Total return
    total_return_pct = ((current_nav / initial_nav) - 1) * 100 if initial_nav > 0 else 0.0

    # Daily return (vs previous day)
    daily_return_pct = 0.0
    if len(navs) >= 2 and navs[-2] > 0:
        daily_return_pct = ((navs[-1] / navs[-2]) - 1) * 100

    # MDD
    mdd_pct = _compute_mdd(navs)

    # Sharpe (need >= 20 observations)
    sharpe_ratio = _compute_sharpe(navs)

    # Trade counts
    filled_trades = [t for t in trade_entries if t.get("status") == "filled"]
    trade_count = len(filled_trades)
    dry_run_count = len([t for t in trade_entries if t.get("status") == "dry_run"])
    win_rate = _compute_win_rate(filled_trades)

    peak_nav = max(navs) if navs else initial_nav

    return {
        "current_nav": round(current_nav, 2),
        "total_return_pct": round(total_return_pct, 4),
        "daily_return_pct": round(daily_return_pct, 4),
        "mdd_pct": round(mdd_pct, 4),
        "sharpe_ratio": round(sharpe_ratio, 2) if sharpe_ratio is not None else None,
        "win_rate": round(win_rate, 2) if win_rate is not None else None,
        "trade_count": trade_count,
        "dry_run_count": dry_run_count,
        "peak_nav": round(peak_nav, 2),
    }


def _empty_metrics(initial_nav: float) -> dict:
    return {
        "current_nav": initial_nav,
        "total_return_pct": 0.0,
        "daily_return_pct": 0.0,
        "mdd_pct": 0.0,
        "sharpe_ratio": None,
        "win_rate": None,
        "trade_count": 0,
        "peak_nav": initial_nav,
    }


def _compute_mdd(navs: list[float]) -> float:
    """Compute Maximum Drawdown (%). Returns negative number."""
    if len(navs) < 2:
        return 0.0
    peak = navs[0]
    mdd = 0.0
    for nav in navs:
        if nav > peak:
            peak = nav
        dd = ((nav - peak) / peak) * 100 if peak > 0 else 0.0
        if dd < mdd:
            mdd = dd
    return mdd


def _compute_sharpe(navs: list[float]) -> float | None:
    """Compute annualized Sharpe ratio. Returns None if < 20 observations."""
    if len(navs) < 20:
        return None

    daily_returns = []
    for i in range(1, len(navs)):
        if navs[i - 1] > 0:
            daily_returns.append(navs[i] / navs[i - 1] - 1)

    if len(daily_returns) < 20:
        return None

    mean_ret = sum(daily_returns) / len(daily_returns)
    rf_daily = RISK_FREE_RATE / 252
    excess = mean_ret - rf_daily

    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
    std_ret = math.sqrt(variance)

    if std_ret == 0:
        return None

    return (excess / std_ret) * math.sqrt(252)


def _compute_win_rate(filled_trades: list[dict]) -> float | None:
    """Win rate from filled trades only (sell with positive pnl)."""
    if not filled_trades:
        return None
    wins = sum(1 for t in filled_trades if t.get("side") == "sell" and t.get("pnl", 0) > 0)
    sells = sum(1 for t in filled_trades if t.get("side") == "sell")
    return (wins / sells * 100) if sells > 0 else None


# ─── Daily Snapshot ──────────────────────────────────────────────────────

def build_daily_snapshot(
    portfolios: dict,
    regime: str,
    signals_count: int,
    benchmark_prices: dict,
    rebalances: list[str],
) -> dict:
    """Build one entry for the daily[] array in performance.json."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    strategy_navs = {}
    total_nav = 0.0
    for code, strat in portfolios.get("strategies", {}).items():
        nav = strat.get("cash", 0)
        for sym, pos in strat.get("positions", {}).items():
            nav += pos.get("qty", 0) * pos.get("current", 0)
        strategy_navs[code] = round(nav, 2)
        total_nav += nav

    return {
        "date": today,
        "total_nav": round(total_nav, 2),
        "strategy_navs": strategy_navs,
        "benchmark_prices": benchmark_prices,
        "regime": regime,
        "signals_count": signals_count,
        "rebalances": rebalances,
    }


def append_and_save(
    existing: dict,
    new_daily_entry: dict,
    portfolios: dict,
    trade_log: list[dict],
) -> dict:
    """Append daily entry, recompute aggregates, save performance.json.

    Duplicate-date protection: updates existing entry if same date found.
    """
    today = new_daily_entry["date"]

    # Initialize scaffold if empty
    if not existing:
        benchmark_prices = new_daily_entry.get("benchmark_prices", {})
        existing = {
            "schema_version": 1,
            "inception_date": today,
            "benchmarks": {
                "SPY": {"inception_price": benchmark_prices.get("SPY", 0)},
                "QQQ": {"inception_price": benchmark_prices.get("QQQ", 0)},
            },
            "strategies": {},
            "daily": [],
        }

    daily = existing.setdefault("daily", [])

    # Duplicate-date guard: update if already exists
    found = False
    for i, entry in enumerate(daily):
        if entry.get("date") == today:
            daily[i] = new_daily_entry
            found = True
            break
    if not found:
        daily.append(new_daily_entry)

    # Recompute strategy aggregates
    strategies_agg = {}
    for code, strat in portfolios.get("strategies", {}).items():
        nav_history = strat.get("nav_history", [])
        initial_nav = strat.get("allocated", 0)
        strat_trades = [t for t in trade_log if t.get("strategy") == code]

        metrics = compute_strategy_metrics(code, nav_history, initial_nav, strat_trades)
        metrics["last_rebalance"] = strat.get("last_rebalance")
        strategies_agg[code] = metrics

    # Total metrics
    total_initial = portfolios.get("account_total", 100000)
    total_current = sum(m["current_nav"] for m in strategies_agg.values())
    total_return_pct = ((total_current / total_initial) - 1) * 100 if total_initial > 0 else 0.0

    # Benchmark returns since inception
    inception_spy = existing.get("benchmarks", {}).get("SPY", {}).get("inception_price", 0)
    inception_qqq = existing.get("benchmarks", {}).get("QQQ", {}).get("inception_price", 0)
    current_spy = new_daily_entry.get("benchmark_prices", {}).get("SPY", 0)
    current_qqq = new_daily_entry.get("benchmark_prices", {}).get("QQQ", 0)

    spy_return_pct = ((current_spy / inception_spy) - 1) * 100 if inception_spy > 0 else 0.0
    qqq_return_pct = ((current_qqq / inception_qqq) - 1) * 100 if inception_qqq > 0 else 0.0

    strategies_agg["TOTAL"] = {
        "initial_nav": total_initial,
        "current_nav": round(total_current, 2),
        "total_return_pct": round(total_return_pct, 4),
        "spy_return_pct": round(spy_return_pct, 4),
        "qqq_return_pct": round(qqq_return_pct, 4),
        "alpha_vs_spy": round(total_return_pct - spy_return_pct, 4),
    }

    existing["strategies"] = strategies_agg

    # Save
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PERFORMANCE_PATH, "w") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"  [perf] performance.json updated: total NAV=${total_current:,.2f}, return={total_return_pct:+.2f}%")
    return existing


# ─── Sparkline SVG Path ──────────────────────────────────────────────────

def build_sparkline_path(nav_history: list[dict], width: int = 120, height: int = 30) -> str:
    """Convert nav_history to SVG path string for inline sparkline."""
    if len(nav_history) < 2:
        return ""
    values = [h["nav"] for h in nav_history[-30:]]
    min_v, max_v = min(values), max(values)
    if min_v == max_v:
        return f"M 0 {height // 2} L {width} {height // 2}"
    points = []
    for i, v in enumerate(values):
        x = i / (len(values) - 1) * width
        y = (1 - (v - min_v) / (max_v - min_v)) * height
        points.append(f"{x:.1f} {y:.1f}")
    return "M " + " L ".join(points)


# ─── Strategy Monthly Report ────────────────────────────────────────────

def generate_strategy_monthly_report(
    strategy_code: str,
    strategy_name: str,
    performance_data: dict,
    trade_log: list[dict],
    output_dir: Path,
) -> Path | None:
    """Generate reports/strategy/{CODE}-monthly.md for current month."""
    today = datetime.now(timezone.utc)
    month_str = today.strftime("%Y-%m")

    strat_metrics = performance_data.get("strategies", {}).get(strategy_code, {})
    strat_trades = [t for t in trade_log if t.get("strategy") == strategy_code
                    and t.get("ts", "").startswith(month_str)]

    if not strat_metrics:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{strategy_code}-{month_str}.md"

    lines = [
        f"# {strategy_name} ({strategy_code}) — {month_str} Monthly Report",
        "",
        "## Performance Summary",
        f"- **Current NAV:** ${strat_metrics.get('current_nav', 0):,.2f}",
        f"- **Total Return:** {strat_metrics.get('total_return_pct', 0):+.2f}%",
        f"- **MDD:** {strat_metrics.get('mdd_pct', 0):.2f}%",
        f"- **Sharpe Ratio:** {strat_metrics.get('sharpe_ratio', 'N/A')}",
        f"- **Trade Count (this month):** {len(strat_trades)}",
        f"- **Last Rebalance:** {strat_metrics.get('last_rebalance', 'Never')}",
        "",
    ]

    if strat_trades:
        lines.extend([
            "## Trades This Month",
            "| Date | Symbol | Side | Weight | Confidence | Status |",
            "|------|--------|------|--------|------------|--------|",
        ])
        for t in strat_trades[-20:]:
            ts = t.get("ts", "")[:10]
            lines.append(
                f"| {ts} | {t.get('symbol', '')} | {t.get('side', '')} "
                f"| {t.get('weight_pct', 0):.0%} | {t.get('confidence', 0):.2f} "
                f"| {t.get('status', '')} |"
            )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ─── Standalone Test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Performance Calculator Test ===")

    portfolios_path = STATE_DIR / "portfolios.json"
    if not portfolios_path.exists():
        print("portfolios.json not found")
        exit(1)

    with open(portfolios_path) as f:
        portfolios = json.load(f)

    trade_log = load_trade_log()
    print(f"Trade log: {len(trade_log)} entries")

    benchmark_prices = fetch_benchmark_prices()
    print(f"Benchmarks: SPY=${benchmark_prices.get('SPY', 0):.2f}, QQQ=${benchmark_prices.get('QQQ', 0):.2f}")

    snapshot = build_daily_snapshot(portfolios, "NEUTRAL", 0, benchmark_prices, [])
    print(f"Snapshot: total_nav=${snapshot['total_nav']:,.2f}")

    existing = load_existing_performance()
    result = append_and_save(existing, snapshot, portfolios, trade_log)
    print(f"Saved. Strategies: {list(result.get('strategies', {}).keys())}")
