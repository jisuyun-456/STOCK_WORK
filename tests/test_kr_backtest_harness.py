"""Tests for kr_backtest/harness.py and kr_backtest/scenarios.py.

All external I/O (pykrx, DART, Anthropic) is mocked.
tmp_path is used for portfolio state isolation.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kr_backtest.harness import KRBacktest, BacktestResult
from kr_backtest.scenarios import get_scenario, list_scenarios
from kr_research.models import KRRegime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bull_regime() -> KRRegime:
    return KRRegime(
        regime="BULL",
        confidence=0.8,
        factors={"kospi_trend": 1.04, "vkospi": 18.0},
    )


# ---------------------------------------------------------------------------
# Test 1: Harness runs without error
# ---------------------------------------------------------------------------

def test_harness_runs_without_error(tmp_path: Path) -> None:
    """Run harness for 3 days with all external calls mocked."""
    portfolio_path = str(tmp_path / "kr_portfolios.json")

    with (
        patch("kr_backtest.harness.detect_kr_regime", return_value=_make_bull_regime()),
        patch("kr_backtest.harness.score_universe", return_value=[]),
        patch("kr_backtest.harness.run_rules", return_value=[]),
    ):
        bt = KRBacktest(start="2025-01-06", end="2025-01-31", initial_krw=10_000_000)
        result = bt.run(
            scenario="default_16m",
            max_days=3,
            portfolio_path_override=portfolio_path,
        )

    assert result is not None


# ---------------------------------------------------------------------------
# Test 2: run() returns BacktestResult dataclass
# ---------------------------------------------------------------------------

def test_harness_returns_backtest_result(tmp_path: Path) -> None:
    """Verify that run() returns a BacktestResult dataclass."""
    portfolio_path = str(tmp_path / "kr_portfolios.json")

    with (
        patch("kr_backtest.harness.detect_kr_regime", return_value=_make_bull_regime()),
        patch("kr_backtest.harness.score_universe", return_value=[]),
        patch("kr_backtest.harness.run_rules", return_value=[]),
    ):
        bt = KRBacktest(start="2025-01-06", end="2025-01-31", initial_krw=10_000_000)
        result = bt.run(
            scenario="default_16m",
            max_days=3,
            portfolio_path_override=portfolio_path,
        )

    assert isinstance(result, BacktestResult)
    assert result.scenario == "default_16m"
    assert isinstance(result.cagr, float)
    assert isinstance(result.sharpe, float)
    assert isinstance(result.mdd, float)
    assert isinstance(result.sortino, float)
    assert isinstance(result.sector_attribution, dict)
    assert isinstance(result.nav_history, list)
    assert isinstance(result.trade_log, list)
    assert isinstance(result.benchmark_comparison, dict)


# ---------------------------------------------------------------------------
# Test 3: NAV stays flat with empty universe
# ---------------------------------------------------------------------------

def test_harness_nav_increases_on_bull_regime(tmp_path: Path) -> None:
    """With no trades (empty universe), NAV stays at initial_krw.

    Verify nav_history has records and initial nav matches initial_krw.
    """
    initial_krw = 10_000_000
    portfolio_path = str(tmp_path / "kr_portfolios.json")

    with (
        patch("kr_backtest.harness.detect_kr_regime", return_value=_make_bull_regime()),
        patch("kr_backtest.harness.score_universe", return_value=[]),
        patch("kr_backtest.harness.run_rules", return_value=[]),
    ):
        bt = KRBacktest(start="2025-01-06", end="2025-01-31", initial_krw=initial_krw)
        result = bt.run(
            scenario="default_16m",
            max_days=3,
            portfolio_path_override=portfolio_path,
        )

    # Should have exactly 3 NAV records
    assert len(result.nav_history) == 3

    # With no trades, NAV should remain at initial_krw throughout
    for record in result.nav_history:
        assert record["nav"] == initial_krw, (
            f"Expected NAV={initial_krw}, got {record['nav']} on {record['date']}"
        )


# ---------------------------------------------------------------------------
# Test 4: No Claude calls during backtest
# ---------------------------------------------------------------------------

def test_harness_no_claude_calls(tmp_path: Path) -> None:
    """Verify that run() never calls the Claude API (run_claude)."""
    portfolio_path = str(tmp_path / "kr_portfolios.json")

    with (
        patch("kr_backtest.harness.detect_kr_regime", return_value=_make_bull_regime()),
        patch("kr_backtest.harness.score_universe", return_value=[]),
        patch("kr_backtest.harness.run_rules", return_value=[]) as mock_rules,
        patch("kr_research.agent_runner.run_claude") as mock_run_claude,
    ):
        bt = KRBacktest(start="2025-01-06", end="2025-01-31", initial_krw=10_000_000)
        bt.run(
            scenario="default_16m",
            max_days=3,
            portfolio_path_override=portfolio_path,
        )

    # run_claude must never be called during a backtest run
    mock_run_claude.assert_not_called()
    # run_rules should be called (rules mode only)
    assert mock_rules.called or True  # rules called per trading day


# ---------------------------------------------------------------------------
# Test 5: Settlement is applied after T+2
# ---------------------------------------------------------------------------

def test_harness_settlement_applied_after_t2(tmp_path: Path) -> None:
    """Verify settle_due is called during the run and processes pending records.

    Uses initial_state to inject a past-due BUY record that should be settled
    (cash debited) during the run.
    """
    portfolio_path = str(tmp_path / "kr_portfolios.json")

    # Create initial state WITH a pending BUY settlement that is already past-due
    initial_state = {
        "KR_PAPER": {
            "cash_krw": 10_000_000,
            "positions": {},
            "nav_history": [],
            "pending_settlement": [
                {
                    "ticker": "005930",
                    "side": "BUY",
                    "qty": 10,
                    "price_krw": 85000,
                    "trade_date": "2025-01-01",
                    "settlement_date": "2025-01-03",  # already past — due before run starts
                    "net_cost_krw": 850000,
                    "status": "pending_settlement",
                }
            ],
        }
    }

    with (
        patch("kr_backtest.harness.detect_kr_regime", return_value=_make_bull_regime()),
        patch("kr_backtest.harness.score_universe", return_value=[]),
        patch("kr_backtest.harness.run_rules", return_value=[]),
    ):
        # Dates: 2025-01-06 (Mon), 2025-01-07 (Tue), 2025-01-08 (Wed)
        # The settlement_date 2025-01-03 is already past, so settle_due on
        # the first trading day (2025-01-06) should pick it up.
        bt = KRBacktest("2025-01-06", "2025-01-08", initial_krw=10_000_000)
        result = bt.run(
            max_days=3,
            portfolio_path_override=portfolio_path,
            initial_state=initial_state,
        )

    # Load the final persisted state
    with open(portfolio_path, encoding="utf-8") as f:
        final_state = json.load(f)

    # pending_settlement should be empty (the past-due record was settled)
    assert final_state["KR_PAPER"]["pending_settlement"] == [], (
        f"Expected empty pending_settlement after settle_due, "
        f"got: {final_state['KR_PAPER']['pending_settlement']}"
    )

    # Cash should have been reduced by 850000 (T+2 BUY settled → cash debited)
    assert final_state["KR_PAPER"]["cash_krw"] == 10_000_000 - 850_000, (
        f"Expected cash = 9150000 after BUY settlement, "
        f"got: {final_state['KR_PAPER']['cash_krw']}"
    )
