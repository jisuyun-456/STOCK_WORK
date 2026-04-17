"""Tests for kr_paper/risk_gate.py — KR-specific risk checks."""
from datetime import datetime

import pytest

from kr_paper.risk_gate import (
    KRRiskCheckResult,
    check_circuit_breaker,
    check_price_limit,
    check_trading_halt,
    check_vi_cooldown,
    validate_kr_order,
)


def test_price_at_30pct_limit_rejected():
    """current_price above +30% upper limit → fail."""
    result = check_price_limit("005930", current_price=130001, base_price=100000)
    assert result.passed is False
    assert result.check_name == "price_limit"


def test_price_below_limit_passed():
    """current_price at base and within +29.999% → pass."""
    # Exactly at base price
    result = check_price_limit("005930", current_price=100000, base_price=100000)
    assert result.passed is True

    # 129999 is below the 130000 upper limit
    result2 = check_price_limit("005930", current_price=129999, base_price=100000)
    assert result2.passed is True


def test_trading_halt_rejected():
    """Halted ticker → fail; non-halted ticker → pass."""
    halted = {"005930"}

    result_halted = check_trading_halt("005930", halted)
    assert result_halted.passed is False
    assert result_halted.check_name == "trading_halt"

    result_ok = check_trading_halt("000660", halted)
    assert result_ok.passed is True


def test_vi_cooldown_rejects_within_2min():
    """VI cooldown: reject when now < expiry, pass when now >= expiry."""
    vi_active_until = {"005930": datetime(2026, 4, 17, 10, 5, 0)}

    # 1 minute before expiry → should fail
    result_before = check_vi_cooldown(
        "005930",
        vi_active_until,
        now=datetime(2026, 4, 17, 10, 4, 0),
    )
    assert result_before.passed is False
    assert result_before.check_name == "vi_cooldown"

    # 1 minute after expiry → should pass
    result_after = check_vi_cooldown(
        "005930",
        vi_active_until,
        now=datetime(2026, 4, 17, 10, 6, 0),
    )
    assert result_after.passed is True


def test_circuit_breaker_level1_blocks_buy():
    """CB level 1 blocks BUY but allows SELL; level 2 blocks all; level 0 passes."""
    result_buy_l1 = check_circuit_breaker(level=1, side="BUY")
    assert result_buy_l1.passed is False

    result_sell_l1 = check_circuit_breaker(level=1, side="SELL")
    assert result_sell_l1.passed is True

    result_sell_l2 = check_circuit_breaker(level=2, side="SELL")
    assert result_sell_l2.passed is False

    result_buy_l0 = check_circuit_breaker(level=0, side="BUY")
    assert result_buy_l0.passed is True
