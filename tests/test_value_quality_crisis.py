"""tests/test_value_quality_crisis.py

VAL 전략의 CRISIS 레짐 gate 통과율 개선 검증.
핵심: 필터 통과 종목이 2개뿐일 때도 weight_pct <= 20%(position_pct cap) 유지.

pytest tests/test_value_quality_crisis.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _make_strategy(max_positions: int = 5, position_pct: float = 0.20):
    """ValueQualityStrategy 인스턴스를 config mock으로 생성."""
    cfg = {
        "max_positions": max_positions,
        "position_pct": position_pct,
        "pe_threshold_neutral": 20,
        "roe_threshold_neutral": 0.12,
    }
    with patch("config.loader.load_strategy_params", return_value={"value_quality": cfg}):
        from strategies.value_quality import ValueQualityStrategy
        return ValueQualityStrategy()


def _make_fundamentals(symbols: list[str], pe=12.0, roe=0.18, fcf=0.07) -> dict:
    """fund_data mock: 모든 종목이 CRISIS 필터를 통과하는 지표."""
    return {
        sym: {"pe": pe, "roe": roe, "fcf_yield": fcf, "symbol": sym}
        for sym in symbols
    }


def _generate_signals(strategy, symbols: list[str], pe=12.0, roe=0.18, fcf=0.07):
    """strategy.generate_signals 를 최소 market_data로 실행.

    fundamentals를 market_data에 직접 주입하여 외부 API 호출 차단.
    """
    from strategies.value_quality import Direction

    fund_data = _make_fundamentals(symbols, pe, roe, fcf)
    strategy.regime = "CRISIS"
    result = strategy.generate_signals(
        market_data={"fundamentals": fund_data, "prices": None},
        current_positions={},
    )
    return [s for s in result if s.direction == Direction.BUY]


# ─── 테스트 ───────────────────────────────────────────────────────────────────

class TestCrisisWeightCap:
    """CRISIS 필터 통과 종목 수에 무관하게 weight ≤ position_pct 유지."""

    def test_two_symbols_weight_is_capped(self):
        """2개 통과 시 weight = 1/max_positions (0.20), 50% 아님."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        sigs = _generate_signals(strat, ["VZ", "CI"])
        assert len(sigs) == 2
        for s in sigs:
            assert s.weight_pct <= 0.20, f"{s.symbol}: weight={s.weight_pct} > 0.20"

    def test_one_symbol_weight_is_capped(self):
        """1개 통과 시에도 weight = 0.20."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        sigs = _generate_signals(strat, ["VZ"])
        assert len(sigs) == 1
        assert sigs[0].weight_pct <= 0.20

    def test_five_symbols_weight_is_twenty_percent(self):
        """max_positions까지 통과 시 weight = 0.20."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        syms = ["VZ", "CI", "JNJ", "PFE", "MRK"]
        sigs = _generate_signals(strat, syms)
        assert len(sigs) >= 1  # 최소 1개 이상 시그널
        for s in sigs:
            assert s.weight_pct <= 0.20, f"{s.symbol}: weight={s.weight_pct} > 0.20"

    def test_weight_never_exceeds_position_pct(self):
        """통과 종목 수가 1~10개 어디서든 weight ≤ position_pct."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        for n in range(1, 11):
            syms = [f"SYM{i}" for i in range(n)]
            sigs = _generate_signals(strat, syms)
            buy_sigs = sigs
            for s in buy_sigs:
                assert s.weight_pct <= 0.20, (
                    f"n={n}: {s.symbol} weight={s.weight_pct} > 0.20"
                )


class TestPositionPctConfig:
    """strategy_params.json의 position_pct가 올바르게 읽히는지."""

    def test_position_pct_loaded_from_config(self):
        strat = _make_strategy(max_positions=5, position_pct=0.15)
        assert strat.position_pct == pytest.approx(0.15)

    def test_position_pct_default_equals_inverse_max_positions(self):
        """position_pct 미설정 시 기본값 = 1/max_positions."""
        cfg = {"max_positions": 5, "pe_threshold_neutral": 20, "roe_threshold_neutral": 0.12}
        with patch("config.loader.load_strategy_params", return_value={"value_quality": cfg}):
            from strategies.value_quality import ValueQualityStrategy
            strat = ValueQualityStrategy()
        assert strat.position_pct == pytest.approx(1.0 / 5)

    def test_stricter_position_pct_honored(self):
        """position_pct=0.15 < 1/max_positions(0.20) → 0.15 적용."""
        strat = _make_strategy(max_positions=5, position_pct=0.15)
        sigs = _generate_signals(strat, ["VZ", "CI", "JNJ"])
        for s in sigs:
            assert s.weight_pct <= 0.15


class TestGatePassSimulation:
    """수정 후 risk_validator position_limit 체크 통과 시뮬."""

    def test_weight_under_strategy_position_limit(self):
        """VAL position_limit = 0.25 → weight 0.20 ≤ 0.25 → PASS."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        sigs = _generate_signals(strat, ["VZ", "CI"])
        position_limit = 0.25  # risk_validator STRATEGY_POSITION_LIMITS["VAL"]
        for s in sigs:
            assert s.weight_pct <= position_limit, (
                f"{s.symbol}: weight={s.weight_pct} > position_limit={position_limit}"
            )

    def test_weight_under_sector_concentration_limit(self):
        """VAL sector_limit = 0.30 → 단일 종목 0.20 ≤ 0.30 → PASS."""
        strat = _make_strategy(max_positions=5, position_pct=0.20)
        sigs = _generate_signals(strat, ["VZ", "CI"])
        sector_limit = 0.30
        for s in sigs:
            assert s.weight_pct <= sector_limit
