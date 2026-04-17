"""
kr_backtest/metrics.py

Pure financial metrics calculations for KR Backtest.
All functions are stateless and deterministic.
"""

import math
from datetime import date
from typing import Optional


def _parse_date(date_str: str) -> date:
    return date.fromisoformat(date_str)


def compute_cagr(nav_history: list[dict], risk_free_rate: float = 0.03) -> float:
    """
    CAGR = (final_nav / initial_nav) ^ (1/years) - 1

    nav_history: list of {"date": "YYYY-MM-DD", "nav": int/float}
    years = (last_date - first_date).days / 365.25
    Returns 0.0 if fewer than 2 records or years < 0.001.
    """
    if len(nav_history) < 2:
        return 0.0

    sorted_history = sorted(nav_history, key=lambda x: x["date"])
    initial_nav = float(sorted_history[0]["nav"])
    final_nav = float(sorted_history[-1]["nav"])

    first_date = _parse_date(sorted_history[0]["date"])
    last_date = _parse_date(sorted_history[-1]["date"])
    years = (last_date - first_date).days / 365.25

    if years < 0.001 or initial_nav <= 0:
        return 0.0

    return (final_nav / initial_nav) ** (1.0 / years) - 1.0


def compute_mdd(nav_history: list[dict]) -> float:
    """
    Maximum Drawdown = max(1 - nav / peak_nav) over time.

    Returns 0.0 if fewer than 2 records.
    Returns as a negative float (e.g., -0.15 for -15% drawdown).
    """
    if len(nav_history) < 2:
        return 0.0

    sorted_history = sorted(nav_history, key=lambda x: x["date"])
    peak = float(sorted_history[0]["nav"])
    max_drawdown = 0.0

    for entry in sorted_history:
        nav = float(entry["nav"])
        if nav > peak:
            peak = nav
        drawdown = (nav - peak) / peak  # negative when below peak
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    return max_drawdown  # already negative


def compute_sharpe(returns: list[float], risk_free_rate: float = 0.03) -> float:
    """
    Sharpe = (mean_return_annualized - risk_free_rate) / std_annualized

    returns: list of daily returns as decimals (e.g., 0.01 for 1%)
    Annualization factor: sqrt(252)
    Returns 0.0 if fewer than 2 returns or std == 0.
    """
    if len(returns) < 2:
        return 0.0

    n = len(returns)
    mean_daily = sum(returns) / n
    variance = sum((r - mean_daily) ** 2 for r in returns) / (n - 1)
    std_daily = math.sqrt(variance)

    if std_daily == 0.0:
        return 0.0

    annualized_mean = mean_daily * 252
    annualized_std = std_daily * math.sqrt(252)

    return (annualized_mean - risk_free_rate) / annualized_std


def compute_sortino(returns: list[float], risk_free_rate: float = 0.03) -> float:
    """
    Sortino = (mean_return_annualized - risk_free_rate) / downside_std_annualized

    downside_std = std of only the negative daily returns
    Annualization factor: sqrt(252)
    Returns 0.0 if no negative returns (all positive).
    """
    if len(returns) < 1:
        return 0.0

    negative_returns = [r for r in returns if r < 0]
    if not negative_returns:
        return 0.0

    n = len(returns)
    mean_daily = sum(returns) / n
    annualized_mean = mean_daily * 252

    # Downside deviation uses only negative returns
    nd = len(negative_returns)
    if nd < 2:
        # single negative return — use it as-is for std calculation
        downside_mean = sum(negative_returns) / nd
        if nd == 1:
            downside_variance = negative_returns[0] ** 2
        else:
            downside_variance = sum(r ** 2 for r in negative_returns) / (nd - 1)
    else:
        downside_mean = sum(negative_returns) / nd
        downside_variance = sum((r - downside_mean) ** 2 for r in negative_returns) / (nd - 1)

    downside_std_daily = math.sqrt(downside_variance)

    if downside_std_daily == 0.0:
        return 0.0

    annualized_downside_std = downside_std_daily * math.sqrt(252)

    return (annualized_mean - risk_free_rate) / annualized_downside_std


def compute_sector_attribution(trade_log: list[dict]) -> dict[str, float]:
    """
    Sum net_proceeds_krw (SELL) or -net_cost_krw (BUY) per sector.

    trade_log entries have:
      {"ticker", "side", "sector", "net_cost_krw" or "net_proceeds_krw"}
    Returns dict: {sector: total_pnl_krw}
    If "sector" key missing, use "Unknown".
    """
    result: dict[str, float] = {}

    for entry in trade_log:
        sector = entry.get("sector", "Unknown") or "Unknown"
        side = entry.get("side", "").upper()

        if side == "SELL":
            pnl = float(entry.get("net_proceeds_krw", 0))
        else:  # BUY
            pnl = -float(entry.get("net_cost_krw", 0))

        result[sector] = result.get(sector, 0.0) + pnl

    return result


def compare_vs_benchmark(
    nav_history: list[dict],
    benchmark_history: list[dict],
) -> dict:
    """
    Compare portfolio vs benchmark (e.g., KOSPI).

    Both have same format: [{"date": "YYYY-MM-DD", "nav": float}]
    Returns:
    {
        "portfolio_cagr": float,
        "benchmark_cagr": float,
        "alpha": float,           # portfolio_cagr - benchmark_cagr
        "excess_return_pct": float  # alpha * 100
    }
    """
    portfolio_cagr = compute_cagr(nav_history)
    benchmark_cagr = compute_cagr(benchmark_history)
    alpha = portfolio_cagr - benchmark_cagr

    return {
        "portfolio_cagr": portfolio_cagr,
        "benchmark_cagr": benchmark_cagr,
        "alpha": alpha,
        "excess_return_pct": alpha * 100.0,
    }
