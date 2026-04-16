"""Tests for LEV weight_pct meaning unification.

After Task1 fix, order_manager handles delta for all BUY signals.
LEV rebalance BUY must send weight_pct = target_weight (not delta/capital).
"""

from __future__ import annotations

import pytest

from strategies.base_strategy import Direction
from strategies.leveraged_etf import LeveragedETFStrategy


def _make_lev(regime: str = "NEUTRAL", capital: float = 25_000.0) -> LeveragedETFStrategy:
    strat = LeveragedETFStrategy()
    strat.regime = regime
    strat.allocated_capital = capital
    return strat


# ─────────────────────────────────────────────────────────────────────────────
# T1: 리밸런스 BUY → weight_pct = target_weight (not delta/capital)
# ─────────────────────────────────────────────────────────────────────────────
def test_rebalance_buy_weight_pct_is_target_weight():
    """NEUTRAL: TQQQ target=50%, currently at $5k (weight=22%), capital=$25k.
    deviation = 0.50 - 0.227 = 0.273 > REBALANCE_BAND → rebalance triggered.
    delta = $12,500 - $5,000 = $7,500.
    OLD (broken): weight_pct = 7500/25000 = 0.30
    NEW (correct): weight_pct = 0.50 (target_weight)
    """
    capital = 25_000.0
    lev = _make_lev("NEUTRAL", capital=capital)
    current_positions = {
        "TQQQ": {"qty": 25,  "current": 200.0, "market_value": 5_000.0},   # 22.7% (below 50%)
        "SPY":  {"qty": 136, "current": 125.0, "market_value": 17_000.0},  # 77.3% (above 50%)
    }

    signals = lev.generate_signals(market_data={}, current_positions=current_positions)
    buy_signals = [s for s in signals if s.direction == Direction.BUY and s.symbol == "TQQQ"]

    assert len(buy_signals) == 1, "TQQQ가 target 미달이므로 BUY 시그널 1개 생성"
    tqqq_buy = buy_signals[0]

    # target_weight for TQQQ in NEUTRAL = 0.50 (from _REGIME_MIX)
    from strategies.leveraged_etf import _REGIME_MIX
    expected_target = _REGIME_MIX["NEUTRAL"]["TQQQ"]

    assert tqqq_buy.weight_pct == pytest.approx(expected_target, abs=1e-4), (
        f"weight_pct should be target_weight={expected_target}, got {tqqq_buy.weight_pct}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T2: 신규 진입 (no existing position) → weight_pct = target_weight (기존 동작 유지)
# ─────────────────────────────────────────────────────────────────────────────
def test_new_entry_buy_weight_pct_is_target_weight():
    """신규 진입 시 weight_pct = target_weight — Task1 이전부터 올바른 동작."""
    capital = 25_000.0
    lev = _make_lev("NEUTRAL", capital=capital)
    current_positions = {}  # 포지션 없음

    signals = lev.generate_signals(market_data={}, current_positions=current_positions)
    buy_signals = [s for s in signals if s.direction == Direction.BUY]

    assert len(buy_signals) > 0

    from strategies.leveraged_etf import _REGIME_MIX
    target_mix = _REGIME_MIX["NEUTRAL"]

    for sig in buy_signals:
        expected = target_mix.get(sig.symbol, 0.0)
        assert sig.weight_pct == pytest.approx(expected, abs=1e-4), (
            f"{sig.symbol}: weight_pct={sig.weight_pct} != target={expected}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# T3: SELL은 여전히 liquidation_ratio — 변경 없음
# ─────────────────────────────────────────────────────────────────────────────
def test_rebalance_sell_weight_pct_is_liquidation_ratio():
    """NEUTRAL: SPY target=50%, currently holding $17k → 초과분 매도.
    delta = -$4,500, liquidation = 4500/17000 ≈ 0.2647
    weight_pct = liquidation_ratio (order_manager SELL branch에서 사용)
    """
    capital = 25_000.0
    lev = _make_lev("NEUTRAL", capital=capital)
    current_positions = {
        "SPY":  {"qty": 136, "current": 125.0, "market_value": 17_000.0},  # 77% (above 50%)
        "TQQQ": {"qty": 25,  "current": 200.0, "market_value": 5_000.0},   # 22% (below 50%)
    }

    signals = lev.generate_signals(market_data={}, current_positions=current_positions)
    sell_signals = [s for s in signals if s.direction == Direction.SELL and s.symbol == "SPY"]

    assert len(sell_signals) == 1
    spy_sell = sell_signals[0]

    from strategies.leveraged_etf import _REGIME_MIX
    target_weight = _REGIME_MIX["NEUTRAL"]["SPY"]  # 0.50
    target_value = capital * target_weight          # $12,500
    current_value = 17_000.0
    expected_liquidation = abs(target_value - current_value) / current_value  # 4500/17000

    assert spy_sell.weight_pct == pytest.approx(expected_liquidation, abs=1e-4)
    assert 0 < spy_sell.weight_pct <= 1.0
