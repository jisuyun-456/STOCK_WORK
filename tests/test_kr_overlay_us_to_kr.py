"""Tests for kr_overlay.us_to_kr — US context → KR regime correction."""
import pytest
from kr_overlay.us_to_kr import apply_us_to_kr_bias


def _ctx(**kwargs) -> dict:
    """Build a minimal US context with sensible defaults (all conditions NOT met)."""
    defaults = {
        "us_regime": "NEUTRAL",
        "nasdaq_sma200_ratio": 1.05,   # above SMA200
        "vix": 18.0,                   # calm
        "dxy_sma200_ratio": 1.00,      # no strong dollar
        "sox_sma200_ratio": 1.05,      # semi above SMA200
    }
    defaults.update(kwargs)
    return defaults


class TestUsCrisis:
    def test_us_crisis_caps_kr_at_bear(self):
        """US regime=CRISIS + KR=BULL → must output BEAR (not BULL)."""
        corrected, bias = apply_us_to_kr_bias("BULL", _ctx(us_regime="CRISIS"))
        assert corrected == "BEAR", f"Expected BEAR, got {corrected}"

    def test_us_crisis_does_not_upgrade_already_crisis(self):
        """US CRISIS + KR already BEAR → stays BEAR."""
        corrected, _ = apply_us_to_kr_bias("BEAR", _ctx(us_regime="CRISIS"))
        assert corrected == "BEAR"


class TestNasdaqVix:
    def test_nasdaq_below_sma200_high_vix_caps_neutral(self):
        """NASDAQ below SMA200 + VIX > 25 + KR=BULL → NEUTRAL."""
        corrected, bias = apply_us_to_kr_bias(
            "BULL", _ctx(nasdaq_sma200_ratio=0.95, vix=28.0)
        )
        assert corrected == "NEUTRAL", f"Expected NEUTRAL, got {corrected}"

    def test_nasdaq_below_sma200_low_vix_no_cap(self):
        """NASDAQ below SMA200 but VIX <= 25 → no cap (BULL stays BULL)."""
        corrected, _ = apply_us_to_kr_bias(
            "BULL", _ctx(nasdaq_sma200_ratio=0.95, vix=20.0)
        )
        assert corrected == "BULL"

    def test_nasdaq_above_sma200_high_vix_no_cap(self):
        """NASDAQ above SMA200 even with high VIX → no cap."""
        corrected, _ = apply_us_to_kr_bias(
            "BULL", _ctx(nasdaq_sma200_ratio=1.02, vix=30.0)
        )
        assert corrected == "BULL"


class TestSoxBias:
    def test_sox_below_sma200_adds_semi_negative_bias(self):
        """SOX below SMA200 → bias['semiconductor'] == -0.15."""
        _, bias = apply_us_to_kr_bias("NEUTRAL", _ctx(sox_sma200_ratio=0.95))
        assert "semiconductor" in bias
        assert abs(bias["semiconductor"] - (-0.15)) < 1e-9

    def test_sox_above_sma200_no_semi_bias(self):
        """SOX above SMA200 → no semiconductor key in bias."""
        _, bias = apply_us_to_kr_bias("NEUTRAL", _ctx(sox_sma200_ratio=1.05))
        assert bias.get("semiconductor", 0.0) == 0.0


class TestStrongDollar:
    def test_strong_dollar_adds_export_positive_bias(self):
        """DXY > SMA200 * 1.05 → bias['export'] == +0.05."""
        _, bias = apply_us_to_kr_bias("NEUTRAL", _ctx(dxy_sma200_ratio=1.07))
        assert "export" in bias
        assert abs(bias["export"] - 0.05) < 1e-9

    def test_weak_dollar_no_export_bias(self):
        """DXY at parity → no export bias."""
        _, bias = apply_us_to_kr_bias("NEUTRAL", _ctx(dxy_sma200_ratio=1.00))
        assert bias.get("export", 0.0) == 0.0


class TestNoCorrection:
    def test_no_correction_when_conditions_not_met(self):
        """All normal conditions → regime unchanged, empty bias."""
        corrected, bias = apply_us_to_kr_bias("BULL", _ctx())
        assert corrected == "BULL"
        assert bias == {}

    def test_neutral_regime_unchanged_normal(self):
        corrected, bias = apply_us_to_kr_bias("NEUTRAL", _ctx())
        assert corrected == "NEUTRAL"
        assert bias == {}

    def test_bear_regime_unchanged_normal(self):
        corrected, bias = apply_us_to_kr_bias("BEAR", _ctx())
        assert corrected == "BEAR"
        assert bias == {}
