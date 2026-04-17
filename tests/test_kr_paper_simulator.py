"""Tests for kr_paper/simulator.py — T+2 settlement date and KR tax simulation."""

import pytest
from kr_paper.simulator import (
    settlement_date,
    simulate_buy,
    simulate_sell,
    apply_dividend,
)


def test_settlement_date_skips_weekends():
    """Friday 2026-04-17 + 2 business days → Tuesday 2026-04-21 (skips Sat+Sun)."""
    result = settlement_date("2026-04-17")
    assert result == "2026-04-21"


def test_simulate_buy_no_tax():
    """BUY order: gross_cost == net_cost (no buy tax in Korea)."""
    result = simulate_buy("005930", 10, 85000, "2026-04-17")
    assert result["gross_cost_krw"] == 850000
    assert result["net_cost_krw"] == 850000
    assert result["side"] == "BUY"
    assert result["status"] == "pending_settlement"


def test_simulate_sell_applies_trading_tax():
    """SELL order: 증권거래세 0.18% deducted from gross proceeds."""
    result = simulate_sell("005930", 10, 90000, 85000, "2026-04-17")
    assert result["gross_proceeds_krw"] == 900000
    assert result["trading_tax_krw"] == int(900000 * 0.0018)  # 1620
    assert result["trading_tax_krw"] == 1620
    assert result["net_proceeds_krw"] == 900000 - 1620  # 898380
    assert result["net_proceeds_krw"] == 898380


def test_simulate_sell_no_capital_gains_for_retail():
    """양도세는 일반 소액 투자자 유예 → capital_gains_tax_krw must be 0."""
    result = simulate_sell("005930", 10, 90000, 85000, "2026-04-17")
    assert result["capital_gains_tax_krw"] == 0


def test_apply_dividend_15_4_pct():
    """배당소득세 15.4%: tax = 15400, net = 84600 on 100000 gross."""
    result = apply_dividend("005930", 100000)
    assert result["tax_krw"] == int(100000 * 0.154)  # 15400
    assert result["tax_krw"] == 15400
    assert result["net_dividend_krw"] == 100000 - 15400  # 84600
    assert result["net_dividend_krw"] == 84600
