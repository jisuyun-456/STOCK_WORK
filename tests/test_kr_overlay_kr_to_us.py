"""Tests for kr_overlay.kr_to_us — KR macro → US signal confidence adjustment."""
import copy
import pytest
from kr_overlay.kr_to_us import apply_kr_to_us_bias


def _sig(ticker: str, confidence: float = 0.60) -> dict:
    return {"ticker": ticker, "side": "BUY", "confidence": confidence,
            "strategy": "MOM", "reason": "test"}


def _kr_ctx(**kwargs) -> dict:
    """KR context with sensible defaults (no adjustment triggers)."""
    defaults = {
        "semi_export_yoy": 5.0,          # positive, no contraction
        "foreign_flow_20d_krw": 0,        # no outflow
        "sector_scores": {"content": 0.0},
    }
    defaults.update(kwargs)
    return defaults


class TestSemiExport:
    def test_semi_export_contraction_reduces_mu_confidence(self):
        """semi_export_yoy=-20 → MU confidence reduced by 0.20."""
        signals = [_sig("MU", 0.70)]
        result = apply_kr_to_us_bias(_kr_ctx(semi_export_yoy=-20.0), signals)
        assert len(result) == 1
        assert abs(result[0]["confidence"] - 0.50) < 1e-9

    def test_semi_export_contraction_does_not_affect_non_semi_ticker(self):
        """semi_export_yoy=-20 → non-semi ticker (AAPL) unchanged."""
        signals = [_sig("AAPL", 0.70)]
        result = apply_kr_to_us_bias(_kr_ctx(semi_export_yoy=-20.0), signals)
        assert abs(result[0]["confidence"] - 0.70) < 1e-9

    def test_semi_export_positive_no_reduction(self):
        """semi_export_yoy=+15 → MU confidence unchanged."""
        signals = [_sig("MU", 0.70)]
        result = apply_kr_to_us_bias(_kr_ctx(semi_export_yoy=15.0), signals)
        assert abs(result[0]["confidence"] - 0.70) < 1e-9

    def test_semi_export_at_threshold_no_reduction(self):
        """semi_export_yoy=-15.0 (exactly at threshold, not below) → no reduction."""
        signals = [_sig("MU", 0.70)]
        result = apply_kr_to_us_bias(_kr_ctx(semi_export_yoy=-15.0), signals)
        assert abs(result[0]["confidence"] - 0.70) < 1e-9

    def test_confidence_does_not_go_below_zero(self):
        """Large reduction clamped at 0.0."""
        signals = [_sig("MU", 0.10)]
        result = apply_kr_to_us_bias(_kr_ctx(semi_export_yoy=-30.0), signals)
        assert result[0]["confidence"] == 0.0


class TestForeignOutflow:
    def test_foreign_outflow_reduces_all_confidence(self):
        """foreign_flow=-15T KRW → all stocks reduced by 0.10."""
        signals = [_sig("AAPL", 0.70), _sig("MU", 0.80)]
        result = apply_kr_to_us_bias(
            _kr_ctx(foreign_flow_20d_krw=-15_000_000_000_000), signals
        )
        assert abs(result[0]["confidence"] - 0.60) < 1e-9
        assert abs(result[1]["confidence"] - 0.70) < 1e-9

    def test_foreign_inflow_no_reduction(self):
        """Positive foreign flow → no adjustment."""
        signals = [_sig("AAPL", 0.70)]
        result = apply_kr_to_us_bias(
            _kr_ctx(foreign_flow_20d_krw=5_000_000_000_000), signals
        )
        assert abs(result[0]["confidence"] - 0.70) < 1e-9

    def test_foreign_outflow_exactly_10T_no_reduction(self):
        """-10T exactly is NOT below threshold (< -10T required)."""
        signals = [_sig("AAPL", 0.70)]
        result = apply_kr_to_us_bias(
            _kr_ctx(foreign_flow_20d_krw=-10_000_000_000_000), signals
        )
        assert abs(result[0]["confidence"] - 0.70) < 1e-9


class TestKrContentBullish:
    def test_content_bullish_increases_nflx_confidence(self):
        """content_score=0.5 → NFLX confidence += 0.05."""
        signals = [_sig("NFLX", 0.60)]
        result = apply_kr_to_us_bias(
            _kr_ctx(sector_scores={"content": 0.5}), signals
        )
        assert abs(result[0]["confidence"] - 0.65) < 1e-9

    def test_content_score_below_threshold_no_boost(self):
        """content_score=0.2 → no boost."""
        signals = [_sig("NFLX", 0.60)]
        result = apply_kr_to_us_bias(
            _kr_ctx(sector_scores={"content": 0.2}), signals
        )
        assert abs(result[0]["confidence"] - 0.60) < 1e-9

    def test_content_boost_does_not_affect_non_content_ticker(self):
        """content_score=0.5 → AAPL (not in _KR_CONTENT_US_TICKERS) unchanged."""
        signals = [_sig("AAPL", 0.60)]
        result = apply_kr_to_us_bias(
            _kr_ctx(sector_scores={"content": 0.5}), signals
        )
        assert abs(result[0]["confidence"] - 0.60) < 1e-9

    def test_confidence_does_not_exceed_one(self):
        """Boost clamped at 1.0."""
        signals = [_sig("NFLX", 0.98)]
        result = apply_kr_to_us_bias(
            _kr_ctx(sector_scores={"content": 0.9}), signals
        )
        assert result[0]["confidence"] <= 1.0


class TestImmutability:
    def test_kr_to_us_does_not_mutate_input(self):
        """Original signal list and dicts must remain unchanged."""
        original_signals = [_sig("MU", 0.70), _sig("NFLX", 0.60)]
        deep_copy = copy.deepcopy(original_signals)

        apply_kr_to_us_bias(
            _kr_ctx(
                semi_export_yoy=-20.0,
                foreign_flow_20d_krw=-15_000_000_000_000,
                sector_scores={"content": 0.5},
            ),
            original_signals,
        )

        # Input list must equal the deep copy (not mutated)
        assert original_signals == deep_copy, "Input signals were mutated!"
