"""EUPHORIA (5th regime) tests — allocator, consensus detection, HMM score."""
import pytest
from strategies.regime_allocator import (
    REGIME_ALLOCATIONS,
    allocate,
    get_regime_description,
    generate_regime_exit_signals,
)


class TestEuphoriaAllocator:
    def test_euphoria_in_regime_allocations(self):
        assert "EUPHORIA" in REGIME_ALLOCATIONS

    def test_euphoria_weights_sum_to_one(self):
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        assert abs(sum(weights.values()) - 1.0) < 1e-6

    def test_euphoria_has_required_strategies(self):
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        for key in ("MOM", "VAL", "QNT", "LEV", "LEV_ST", "CASH"):
            assert key in weights

    def test_euphoria_lev_fixed(self):
        """LEV + LEV_ST는 모든 레짐에서 0.50 고정."""
        weights = REGIME_ALLOCATIONS["EUPHORIA"]
        assert abs(weights["LEV"] + weights["LEV_ST"] - 0.50) < 1e-6

    def test_euphoria_cash_greater_than_bull(self):
        """과매수 리스크 축소 — BULL(0%)보다 CASH 비율이 높아야 한다."""
        assert REGIME_ALLOCATIONS["EUPHORIA"]["CASH"] > REGIME_ALLOCATIONS["BULL"]["CASH"]

    def test_euphoria_mom_less_than_bull(self):
        """과매수 시장에서 모멘텀 추격 억제."""
        assert REGIME_ALLOCATIONS["EUPHORIA"]["MOM"] < REGIME_ALLOCATIONS["BULL"]["MOM"]

    def test_allocate_euphoria_returns_amounts(self):
        result = allocate("EUPHORIA", 100_000)
        total = sum(result.values())
        assert abs(total - 100_000) < 1.0  # rounding tolerance

    def test_euphoria_description_exists(self):
        desc = get_regime_description("EUPHORIA")
        assert "EUPHORIA" in desc or "과열" in desc or "과매수" in desc

    def test_euphoria_severity_equals_bull(self):
        """EUPHORIA → BEAR 전환 시 exit signal 발생해야 한다 (severity 0)."""
        portfolios = {
            "strategies": {
                "MOM": {"positions": {"AAPL": {"qty": 10, "avg_cost": 150.0}}}
            }
        }
        signals = generate_regime_exit_signals("BEAR", "EUPHORIA", portfolios)
        assert len(signals) > 0

    def test_euphoria_to_bull_no_exit_signal(self):
        """EUPHORIA → BULL 전환은 리스크 감소이므로 exit signal 없음."""
        signals = generate_regime_exit_signals("BULL", "EUPHORIA", {})
        assert signals == []


class TestEuphoriaConsensus:
    """detect_regime, detect_regime_enhanced EUPHORIA 분기 단위 테스트."""

    def _make_hist(self, n=252, trend="euphoria"):
        """yfinance hist DataFrame 모의 생성."""
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2024-01-01", periods=n, freq="B")
        if trend == "euphoria":
            # 강한 상승 추세: SMA200 < SMA50 < current
            prices = np.linspace(400, 560, n)  # SPY 40% 상승
        elif trend == "bear":
            prices = np.linspace(500, 380, n)
        else:
            prices = np.full(n, 480.0)
        return pd.DataFrame({"Close": prices}, index=dates)

    def test_detect_regime_euphoria_conditions(self):
        """EUPHORIA: VIX<15 + RSI≥75 + SPY>SMA50>SMA200 시 EUPHORIA 반환."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_hist(trend="euphoria")
        result = _classify_regime_from_data(hist, vix_level=12.0)
        assert result == "EUPHORIA"

    def test_detect_regime_no_euphoria_high_vix(self):
        """VIX ≥ 15이면 EUPHORIA 아님 → BULL 또는 NEUTRAL."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_hist(trend="euphoria")
        result = _classify_regime_from_data(hist, vix_level=18.0)
        assert result != "EUPHORIA"

    def test_detect_regime_no_euphoria_low_rsi(self):
        """RSI < 75이면 EUPHORIA 아님 (횡보 추세)."""
        from research.consensus import _classify_regime_from_data

        # 횡보 데이터는 RSI < 75
        hist = self._make_hist(trend="neutral")
        result = _classify_regime_from_data(hist, vix_level=12.0)
        assert result != "EUPHORIA"

    def test_regime_multipliers_has_euphoria(self):
        from research.consensus import REGIME_MULTIPLIERS
        assert "EUPHORIA" in REGIME_MULTIPLIERS

    def test_get_regime_weights_euphoria(self):
        from research.consensus import get_regime_weights
        weights = get_regime_weights("EUPHORIA")
        assert abs(sum(weights.values()) - 1.0) < 1e-6


class TestEuphoriaHMM:
    def test_regime_scores_has_euphoria(self):
        from research.regime_hmm import _REGIME_SCORES
        assert "EUPHORIA" in _REGIME_SCORES

    def test_euphoria_score_equals_bull(self):
        """EUPHORIA는 BULL과 같은 점수(1.0) — HMM 연속 스코어링 일관성."""
        from research.regime_hmm import _REGIME_SCORES
        assert _REGIME_SCORES["EUPHORIA"] == _REGIME_SCORES["BULL"]

    def test_score_from_regime_prob_includes_euphoria(self):
        """score_from_regime_prob이 EUPHORIA 확률을 올바르게 반영한다."""
        from research.regime_hmm import score_from_regime_prob
        # EUPHORIA 100% → score = 1.0
        state_probs = {"EUPHORIA": 1.0, "BULL": 0.0, "NEUTRAL": 0.0, "BEAR": 0.0, "CRISIS": 0.0}
        score = score_from_regime_prob(state_probs, state_to_regime={})
        assert abs(score - 1.0) < 1e-6

    def test_score_mixed_euphoria_bull(self):
        """EUPHORIA 50% + BULL 50% → score ≈ 1.0 (둘 다 최고점)."""
        from research.regime_hmm import score_from_regime_prob
        state_probs = {"EUPHORIA": 0.5, "BULL": 0.5}
        score = score_from_regime_prob(state_probs, state_to_regime={})
        assert abs(score - 1.0) < 1e-6
