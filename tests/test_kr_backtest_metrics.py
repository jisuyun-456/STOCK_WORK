"""
tests/test_kr_backtest_metrics.py

Unit tests for kr_backtest/metrics.py
5 tests covering CAGR, MDD, Sharpe, Sortino, sector attribution.
"""

import math
import pytest

from kr_backtest.metrics import (
    compute_cagr,
    compute_mdd,
    compute_sector_attribution,
    compute_sharpe,
    compute_sortino,
)


def test_cagr_1yr_10pct():
    """CAGR of 10M → 11M over ~1 year should be ≈ 10%."""
    nav_history = [
        {"date": "2025-01-01", "nav": 10_000_000},
        {"date": "2026-01-01", "nav": 11_000_000},
    ]
    result = compute_cagr(nav_history)
    # 365/365.25 ≈ 0.9993, so result is slightly above 0.10
    assert abs(result - 0.10) < 0.001, f"Expected ~0.10, got {result}"


def test_mdd_correct_peak_to_trough():
    """MDD: peak=12M, trough=9M → MDD = -(12-9)/12 = -0.25."""
    nav_history = [
        {"date": "2025-01-01", "nav": 10_000_000},
        {"date": "2025-02-01", "nav": 12_000_000},
        {"date": "2025-03-01", "nav":  9_000_000},
        {"date": "2025-04-01", "nav": 11_000_000},
    ]
    result = compute_mdd(nav_history)
    assert abs(result - (-0.25)) < 0.001, f"Expected ≈ -0.25, got {result}"


def test_sharpe_positive_returns():
    """Sharpe should be > 0 for mostly positive returns."""
    # Mix of positive and some small negative, net positive
    returns = [0.01, -0.002, 0.008, 0.005, -0.001, 0.012, 0.003] * 20
    result = compute_sharpe(returns)
    assert result > 0, f"Expected positive Sharpe, got {result}"


def test_sortino_ignores_upside():
    """
    Sortino uses only downside std, so should be > Sharpe for same returns.
    downside_returns = [-0.01, -0.005], upside returns are not used in denominator.
    """
    returns = [0.02, -0.01, 0.03, -0.005, 0.01]
    sortino = compute_sortino(returns)
    sharpe = compute_sharpe(returns)
    assert sortino > 0
    assert sortino > sharpe  # downside std < total std → sortino > sharpe

    # Single negative return — should not crash
    returns_single_neg = [0.02, -0.01, 0.03, 0.01]
    result = compute_sortino(returns_single_neg)
    assert result > 0  # should still work consistently


def test_sector_attribution_sums():
    """Sector attribution should correctly sum PnL per sector."""
    trade_log = [
        # 반도체: BUY 5M, SELL 6M → net = -5M + 6M = +1M
        {"ticker": "005930", "side": "BUY",  "sector": "반도체", "net_cost_krw": 5_000_000},
        {"ticker": "005930", "side": "SELL", "sector": "반도체", "net_proceeds_krw": 6_000_000},
        # 이차전지: BUY 3M, SELL 2.5M → net = -3M + 2.5M = -0.5M
        {"ticker": "006400", "side": "BUY",  "sector": "이차전지", "net_cost_krw": 3_000_000},
        {"ticker": "006400", "side": "SELL", "sector": "이차전지", "net_proceeds_krw": 2_500_000},
    ]

    result = compute_sector_attribution(trade_log)

    assert "반도체" in result, "반도체 sector should be in result"
    assert "이차전지" in result, "이차전지 sector should be in result"

    assert abs(result["반도체"] - 1_000_000) < 1, (
        f"반도체 PnL expected 1_000_000, got {result['반도체']}"
    )
    assert abs(result["이차전지"] - (-500_000)) < 1, (
        f"이차전지 PnL expected -500_000, got {result['이차전지']}"
    )
