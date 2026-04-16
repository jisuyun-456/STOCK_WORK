"""Tests for _sync_alpaca_positions multi-strategy position split.

Verifies that when multiple strategies buy the same symbol,
the Alpaca position is split proportionally (not last-write-wins).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# We test the internal helper directly by patching its dependencies
# _sync_alpaca_positions is a module-level function in run_cycle.py


def _make_portfolios(strategies: list[str]) -> dict:
    """Build a minimal portfolios dict with given strategy codes."""
    return {
        "account_total": 100_000.0,
        "account_total_history": [],
        "strategies": {
            code: {
                "allocated": 25_000.0,
                "cash": 25_000.0,
                "positions": {},
                "nav_history": [],
            }
            for code in strategies
        },
    }


def _make_trade_log_lines(entries: list[dict]) -> str:
    """Serialize trade log entries to JSONL."""
    return "\n".join(json.dumps(e) for e in entries) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# T1: 단일 전략 소유 → 기존 동작 유지 (전략에 전액 배정)
# ─────────────────────────────────────────────────────────────────────────────
def test_single_owner_assigned_fully():
    """단일 전략이 AAPL 보유 → 해당 전략에 전액 배정."""
    portfolios = _make_portfolios(["MOM", "QNT"])
    alpaca_positions = [
        {"symbol": "AAPL", "qty": 10.0, "avg_entry_price": 100.0,
         "current_price": 110.0, "market_value": 1100.0,
         "unrealized_pl": 100.0, "unrealized_plpc": 0.1},
    ]
    trade_log = _make_trade_log_lines([
        {"ts": "2026-04-16T10:00:00Z", "symbol": "AAPL", "strategy": "MOM",
         "side": "buy", "status": "filled", "qty": 1000.0},
    ])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(trade_log)
        log_path = Path(f.name)

    try:
        from run_cycle import _sync_alpaca_positions
        with (
            patch("execution.alpaca_client.get_positions", return_value=alpaca_positions),
            patch("execution.alpaca_client.get_account_info", return_value={"cash": 24_000.0, "equity": 101_000.0}),
            patch("run_cycle.STATE_DIR", log_path.parent),
        ):
            log_path.rename(log_path.parent / "trade_log.jsonl")
            result = _sync_alpaca_positions(portfolios)
    finally:
        (log_path.parent / "trade_log.jsonl").unlink(missing_ok=True)

    assert "AAPL" in result["strategies"]["MOM"]["positions"]
    assert "AAPL" not in result["strategies"]["QNT"]["positions"]
    assert result["strategies"]["MOM"]["positions"]["AAPL"]["qty"] == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# T2: 두 전략이 같은 심볼 보유 → notional 비례 분할
# ─────────────────────────────────────────────────────────────────────────────
def test_two_owners_split_proportionally():
    """MOM $1000 + QNT $500 매수 → Alpaca AAPL 2:1 비율 분할."""
    portfolios = _make_portfolios(["MOM", "QNT"])
    alpaca_positions = [
        {"symbol": "AAPL", "qty": 12.0, "avg_entry_price": 100.0,
         "current_price": 125.0, "market_value": 1500.0,
         "unrealized_pl": 300.0, "unrealized_plpc": 0.25},
    ]
    trade_log = _make_trade_log_lines([
        {"ts": "2026-04-16T10:00:00Z", "symbol": "AAPL", "strategy": "MOM",
         "side": "buy", "status": "filled", "qty": 1000.0},
        {"ts": "2026-04-16T10:05:00Z", "symbol": "AAPL", "strategy": "QNT",
         "side": "buy", "status": "filled", "qty": 500.0},
    ])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(trade_log)
        log_path = Path(f.name)

    try:
        from run_cycle import _sync_alpaca_positions
        with (
            patch("execution.alpaca_client.get_positions", return_value=alpaca_positions),
            patch("execution.alpaca_client.get_account_info", return_value={"cash": 23_500.0, "equity": 101_500.0}),
            patch("run_cycle.STATE_DIR", log_path.parent),
        ):
            log_path.rename(log_path.parent / "trade_log.jsonl")
            result = _sync_alpaca_positions(portfolios)
    finally:
        (log_path.parent / "trade_log.jsonl").unlink(missing_ok=True)

    mom_pos = result["strategies"]["MOM"]["positions"].get("AAPL")
    qnt_pos = result["strategies"]["QNT"]["positions"].get("AAPL")

    assert mom_pos is not None, "MOM should have AAPL position"
    assert qnt_pos is not None, "QNT should have AAPL position"

    # MOM: 1000/(1000+500) = 2/3, QNT: 500/1500 = 1/3
    assert abs(mom_pos["market_value"] - 1000.0) < 1.0   # ~$1000
    assert abs(qnt_pos["market_value"] - 500.0) < 1.0    # ~$500
    assert abs(mom_pos["qty"] + qnt_pos["qty"] - 12.0) < 0.01  # total qty preserved


# ─────────────────────────────────────────────────────────────────────────────
# T3: 한 전략이 SELL 후 → SELL한 전략은 holder에서 제외
# ─────────────────────────────────────────────────────────────────────────────
def test_sold_strategy_excluded_from_holders():
    """MOM이 AAPL을 팔고 QNT만 보유 → QNT에 전액 배정."""
    portfolios = _make_portfolios(["MOM", "QNT"])
    alpaca_positions = [
        {"symbol": "AAPL", "qty": 5.0, "avg_entry_price": 100.0,
         "current_price": 110.0, "market_value": 550.0,
         "unrealized_pl": 50.0, "unrealized_plpc": 0.1},
    ]
    trade_log = _make_trade_log_lines([
        {"ts": "2026-04-14T10:00:00Z", "symbol": "AAPL", "strategy": "MOM",
         "side": "buy", "status": "filled", "qty": 1000.0},
        {"ts": "2026-04-15T10:00:00Z", "symbol": "AAPL", "strategy": "QNT",
         "side": "buy", "status": "filled", "qty": 500.0},
        {"ts": "2026-04-16T10:00:00Z", "symbol": "AAPL", "strategy": "MOM",
         "side": "sell", "status": "filled", "qty": 10.0},
    ])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(trade_log)
        log_path = Path(f.name)

    try:
        from run_cycle import _sync_alpaca_positions
        with (
            patch("execution.alpaca_client.get_positions", return_value=alpaca_positions),
            patch("execution.alpaca_client.get_account_info", return_value={"cash": 24_500.0, "equity": 100_550.0}),
            patch("run_cycle.STATE_DIR", log_path.parent),
        ):
            log_path.rename(log_path.parent / "trade_log.jsonl")
            result = _sync_alpaca_positions(portfolios)
    finally:
        (log_path.parent / "trade_log.jsonl").unlink(missing_ok=True)

    # MOM sold — should not hold AAPL
    assert "AAPL" not in result["strategies"]["MOM"]["positions"]
    # QNT still holds — should get full position
    assert "AAPL" in result["strategies"]["QNT"]["positions"]
    assert result["strategies"]["QNT"]["positions"]["AAPL"]["qty"] == 5.0


# ─────────────────────────────────────────────────────────────────────────────
# T4: qty=0 (dry_run) → equal split fallback
# ─────────────────────────────────────────────────────────────────────────────
def test_zero_notional_falls_back_to_equal_split():
    """qty=0인 dry_run 엔트리 → equal split (1/n)."""
    portfolios = _make_portfolios(["MOM", "QNT"])
    alpaca_positions = [
        {"symbol": "TSLA", "qty": 4.0, "avg_entry_price": 200.0,
         "current_price": 200.0, "market_value": 800.0,
         "unrealized_pl": 0.0, "unrealized_plpc": 0.0},
    ]
    trade_log = _make_trade_log_lines([
        {"ts": "2026-04-16T10:00:00Z", "symbol": "TSLA", "strategy": "MOM",
         "side": "buy", "status": "dry_run", "qty": 0},
        {"ts": "2026-04-16T10:05:00Z", "symbol": "TSLA", "strategy": "QNT",
         "side": "buy", "status": "dry_run", "qty": 0},
    ])

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(trade_log)
        log_path = Path(f.name)

    try:
        from run_cycle import _sync_alpaca_positions
        with (
            patch("execution.alpaca_client.get_positions", return_value=alpaca_positions),
            patch("execution.alpaca_client.get_account_info", return_value={"cash": 25_000.0, "equity": 100_800.0}),
            patch("run_cycle.STATE_DIR", log_path.parent),
        ):
            log_path.rename(log_path.parent / "trade_log.jsonl")
            result = _sync_alpaca_positions(portfolios)
    finally:
        (log_path.parent / "trade_log.jsonl").unlink(missing_ok=True)

    mom_pos = result["strategies"]["MOM"]["positions"].get("TSLA")
    qnt_pos = result["strategies"]["QNT"]["positions"].get("TSLA")

    assert mom_pos is not None
    assert qnt_pos is not None
    # Equal split: each gets 50%
    assert abs(mom_pos["market_value"] - 400.0) < 1.0
    assert abs(qnt_pos["market_value"] - 400.0) < 1.0
