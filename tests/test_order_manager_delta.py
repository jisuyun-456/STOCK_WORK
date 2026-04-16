"""Tests for BUY delta sizing in order_manager.

Verifies that execute_signal() and execute_signals() compute
trade_value = target - existing (delta), not just target.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from strategies.base_strategy import Signal, Direction
from execution.order_manager import execute_signal, execute_signals


def _make_signal(symbol: str = "AAPL", weight_pct: float = 0.10) -> Signal:
    return Signal(
        strategy="MOM",
        symbol=symbol,
        direction=Direction.BUY,
        weight_pct=weight_pct,
        confidence=0.8,
        reason="test",
    )


# ─────────────────────────────────────────────────────────────────────────────
# T1: 포지션 없음 → full target 매수
# ─────────────────────────────────────────────────────────────────────────────
def test_buy_no_existing_position_uses_full_target():
    """포지션 없을 때 trade_value = strategy_capital × weight_pct (delta = target)."""
    signal = _make_signal(weight_pct=0.10)
    capital = 10_000.0
    cash = 10_000.0

    result = execute_signal(
        signal,
        strategy_capital=capital,
        strategy_cash=cash,
        dry_run=True,
        current_positions={},          # 포지션 없음
    )

    assert result["status"] == "dry_run"
    # dry_run reason에 delta = $1000 (10% of 10k), existing = $0 반영
    assert "delta $1000.00" in result["error_reason"]
    assert "existing $0.00" in result["error_reason"]


# ─────────────────────────────────────────────────────────────────────────────
# T2: 포지션 5% 보유, target 10% → delta 5% 매수
# ─────────────────────────────────────────────────────────────────────────────
def test_buy_partial_position_uses_delta():
    """이미 $500 보유 시 target $1000 → delta $500만 매수."""
    signal = _make_signal(weight_pct=0.10)
    capital = 10_000.0
    cash = 10_000.0
    current_positions = {"AAPL": 500.0}   # 5% 보유

    result = execute_signal(
        signal,
        strategy_capital=capital,
        strategy_cash=cash,
        dry_run=True,
        current_positions=current_positions,
    )

    assert result["status"] == "dry_run"
    assert "delta $500.00" in result["error_reason"]
    assert "existing $500.00" in result["error_reason"]
    assert "target $1000.00" in result["error_reason"]


# ─────────────────────────────────────────────────────────────────────────────
# T3: 포지션 >= target → delta=0 → skipped
# ─────────────────────────────────────────────────────────────────────────────
def test_buy_already_at_target_skips():
    """target 이미 달성 시 already_at_target으로 skip."""
    signal = _make_signal(weight_pct=0.10)
    capital = 10_000.0
    cash = 10_000.0
    current_positions = {"AAPL": 1_200.0}   # 12% 보유 (target 10% 초과)

    result = execute_signal(
        signal,
        strategy_capital=capital,
        strategy_cash=cash,
        dry_run=True,
        current_positions=current_positions,
    )

    assert result["status"] == "skipped"
    assert result["error_reason"] == "already_at_target"


# ─────────────────────────────────────────────────────────────────────────────
# T4: execute_signals() — positions 스냅샷 조회 후 delta 적용
# ─────────────────────────────────────────────────────────────────────────────
def test_execute_signals_fetches_positions_for_delta():
    """execute_signals()가 get_positions()를 1회 호출하고 delta BUY를 처리."""
    signals = [
        _make_signal(symbol="AAPL", weight_pct=0.10),
        _make_signal(symbol="MSFT", weight_pct=0.10),
    ]
    strategy_allocations = {
        "MOM": {"capital": 10_000.0, "cash": 10_000.0},
    }
    mock_positions = [
        {"symbol": "AAPL", "market_value": 500.0},   # AAPL 5% 보유
        # MSFT 없음
    ]

    with patch("execution.order_manager.get_positions", return_value=mock_positions) as mock_get:
        results = execute_signals(signals, strategy_allocations, dry_run=True)

    # get_positions는 BUY 시그널 처리를 위해 정확히 1회 호출
    mock_get.assert_called_once()

    # AAPL: delta $500 (target $1000 - existing $500)
    aapl_result = next(r for r in results if r["symbol"] == "AAPL")
    assert aapl_result["status"] == "dry_run"
    assert "delta $500.00" in aapl_result["error_reason"]

    # MSFT: delta $1000 (no position)
    msft_result = next(r for r in results if r["symbol"] == "MSFT")
    assert msft_result["status"] == "dry_run"
    assert "delta $1000.00" in msft_result["error_reason"]
