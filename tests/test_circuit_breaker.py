# tests/test_circuit_breaker.py
"""Unit tests for execution/circuit_breaker.py — all fail until implementation."""
import sys
import json
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from execution.circuit_breaker import (
    check_circuit_breaker, filter_signals_by_stage,
    load_lock, write_lock, clear_lock,
    Stage, CircuitBreakerState,
)
from strategies.base_strategy import Signal, Direction


# ── helpers ──────────────────────────────────────────────────────────────

def _mk_portfolios(nav_history: list[float]) -> dict:
    """Build minimal portfolios.json structure with synthetic NAV history."""
    dates = [f"2026-01-{i+1:02d}" for i in range(len(nav_history))]
    history = [{"date": d, "nav": n} for d, n in zip(dates, nav_history)]
    return {
        "strategies": {
            "TOTAL": {
                "nav_history": history,
                "allocated": nav_history[-1],
                "cash": nav_history[-1],
                "positions": {},
            }
        },
        "account_total": nav_history[-1],
    }


def _mk_signal(side: str = "buy", weight: float = 0.10) -> Signal:
    direction = Direction.BUY if side == "buy" else Direction.SELL
    return Signal("MOM", "AAPL", direction, weight, 0.9, "test")


# ── Stage computation ─────────────────────────────────────────────────────

def test_normal_when_no_loss():
    pf = _mk_portfolios([100.0, 100.0, 100.0])
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.NORMAL


def test_warning_at_minus_2pct_daily():
    pf = _mk_portfolios([100.0, 98.0])
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.WARNING


def test_caution_at_minus_3pct_daily():
    pf = _mk_portfolios([100.0, 96.9])
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.CAUTION


def test_halt_at_minus_5pct_weekly():
    # -5.1% over 5 days
    pf = _mk_portfolios([100.0, 100.0, 100.0, 100.0, 100.0, 94.9])
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.HALT


def test_emergency_at_minus_10pct_mdd():
    # Peak 110, drops to 98 → drawdown from peak = (98-110)/110 = -10.9%
    pf = _mk_portfolios([100.0, 110.0, 98.0])
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.EMERGENCY


def test_emergency_takes_priority_over_lower_stages():
    # Both -3% daily AND -10% MDD → EMERGENCY wins
    pf = _mk_portfolios([100.0, 110.0, 96.9])  # -12% from peak, -3% daily
    state = check_circuit_breaker(pf)
    assert state.stage == Stage.EMERGENCY


# ── Lock file ─────────────────────────────────────────────────────────────

def test_emergency_writes_lock(tmp_path):
    lock_file = tmp_path / "circuit_breaker.lock"
    pf = _mk_portfolios([100.0, 110.0, 98.0])
    with patch("execution.circuit_breaker.LOCK_PATH", lock_file):
        state = check_circuit_breaker(pf)
    assert state.stage == Stage.EMERGENCY
    assert lock_file.exists()
    data = json.loads(lock_file.read_text())
    assert data["stage"] == 4
    assert data["resolved"] == False


def test_sticky_lock_blocks_subsequent_call(tmp_path):
    lock_file = tmp_path / "circuit_breaker.lock"
    lock_data = {
        "stage": 4, "triggered_at": "2026-01-01T00:00:00Z",
        "trigger_value": -0.12, "trigger_metric": "portfolio_mdd",
        "reason": "mdd breach", "resolved": False
    }
    lock_file.write_text(json.dumps(lock_data))
    pf = _mk_portfolios([100.0, 100.0, 100.0])
    with patch("execution.circuit_breaker.LOCK_PATH", lock_file):
        state = check_circuit_breaker(pf)
    assert state.stage == Stage.EMERGENCY


def test_clear_lock_unblocks(tmp_path):
    lock_file = tmp_path / "circuit_breaker.lock"
    lock_data = {
        "stage": 4, "triggered_at": "2026-01-01T00:00:00Z",
        "trigger_value": -0.12, "trigger_metric": "portfolio_mdd",
        "reason": "mdd breach", "resolved": True  # resolved!
    }
    lock_file.write_text(json.dumps(lock_data))
    pf = _mk_portfolios([100.0, 100.0, 100.0])
    with patch("execution.circuit_breaker.LOCK_PATH", lock_file):
        state = check_circuit_breaker(pf)
    # resolved=True should unblock — stage recomputes from portfolios (NORMAL)
    assert state.stage == Stage.NORMAL


# ── Signal filtering ──────────────────────────────────────────────────────

def test_normal_passes_all_signals():
    signals = [_mk_signal("buy"), _mk_signal("sell")]
    kept, filtered = filter_signals_by_stage(signals, Stage.NORMAL)
    assert len(kept) == 2
    assert len(filtered) == 0


def test_warning_passes_all_signals():
    signals = [_mk_signal("buy"), _mk_signal("sell")]
    kept, filtered = filter_signals_by_stage(signals, Stage.WARNING)
    assert len(kept) == 2
    assert len(filtered) == 0


def test_caution_halves_buy_weights():
    buy = _mk_signal("buy", weight=0.10)
    sell = _mk_signal("sell", weight=0.50)
    kept, filtered = filter_signals_by_stage([buy, sell], Stage.CAUTION)
    assert len(kept) == 2
    buy_kept = next(s for s in kept if s.direction == Direction.BUY)
    sell_kept = next(s for s in kept if s.direction == Direction.SELL)
    assert abs(buy_kept.weight_pct - 0.05) < 1e-9
    assert abs(sell_kept.weight_pct - 0.50) < 1e-9  # sell unchanged


def test_halt_drops_buys_keeps_sells():
    signals = [_mk_signal("buy"), _mk_signal("sell")]
    kept, filtered = filter_signals_by_stage(signals, Stage.HALT)
    assert all(s.direction == Direction.SELL for s in kept)
    assert all(s.direction == Direction.BUY for s in filtered)


def test_emergency_drops_all():
    signals = [_mk_signal("buy"), _mk_signal("sell")]
    kept, filtered = filter_signals_by_stage(signals, Stage.EMERGENCY)
    assert len(kept) == 0
    assert len(filtered) == 2
