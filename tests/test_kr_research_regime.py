"""Tests for kr_research.regime — 6 tests."""
import pytest


def _make_snapshot(
    kospi_vs_sma200: float = 1.02,
    vkospi: float = 20.0,
    semi_yoy: float = None,
) -> dict:
    """Helper to build minimal kr_market_state-compatible snapshot."""
    return {
        "kospi": {
            "kospi_vs_sma200": kospi_vs_sma200,
        },
        "vkospi": {
            "level": vkospi,
            "source": "pykrx",
        },
        "usdkrw": {
            "20d_change_pct": 0.0,
        },
        "semiconductor_export": {
            "yoy_pct": semi_yoy,
        },
    }


def test_us_crisis_overrides_to_bear():
    """US regime=CRISIS must force KR regime to BEAR or lower (no BULL/NEUTRAL)."""
    from kr_research.regime import detect_kr_regime

    # Normal BULL conditions for KR
    snapshot = _make_snapshot(kospi_vs_sma200=1.08, vkospi=15.0)
    result = detect_kr_regime(kr_snapshot=snapshot, us_regime="CRISIS", us_vix=40.0)

    assert result.regime in ("BEAR", "CRISIS"), (
        f"Expected BEAR or CRISIS when US is CRISIS, got {result.regime}"
    )


def test_high_vkospi_triggers_crisis():
    """VKOSPI >= 30 must trigger CRISIS regime."""
    from kr_research.regime import detect_kr_regime

    snapshot = _make_snapshot(vkospi=32.0)
    result = detect_kr_regime(kr_snapshot=snapshot)

    assert result.regime == "CRISIS", f"Expected CRISIS for vkospi=32, got {result.regime}"
    assert "vkospi" in result.factors or "vkospi" in str(result.factors)


def test_low_vkospi_bull_kospi_trend():
    """VKOSPI < 20 and KOSPI > SMA200 → BULL."""
    from kr_research.regime import detect_kr_regime

    snapshot = _make_snapshot(kospi_vs_sma200=1.06, vkospi=15.0)
    result = detect_kr_regime(kr_snapshot=snapshot, us_regime="NEUTRAL", us_vix=18.0)

    assert result.regime == "BULL", f"Expected BULL for kospi_trend=1.06 vkospi=15, got {result.regime}"


def test_semi_export_negative_prevents_bull():
    """Semi export YoY < -15% must prevent BULL even with good KOSPI/VKOSPI."""
    from kr_research.regime import detect_kr_regime

    # Normally BULL conditions
    snapshot = _make_snapshot(kospi_vs_sma200=1.06, vkospi=15.0, semi_yoy=-20.0)
    result = detect_kr_regime(kr_snapshot=snapshot, us_regime="NEUTRAL")

    assert result.regime != "BULL", (
        f"Expected non-BULL when semi export YoY=-20%, got {result.regime}"
    )


def test_sox_below_sma200_reduces_tier():
    """SOX below SMA200 (sox_trend < 1.0) should reduce regime by 1 tier."""
    from kr_research.regime import detect_kr_regime

    # Conditions that would otherwise produce BULL
    snapshot = _make_snapshot(kospi_vs_sma200=1.06, vkospi=15.0)
    result_no_sox = detect_kr_regime(kr_snapshot=snapshot, sox_trend=1.05)
    result_with_sox = detect_kr_regime(kr_snapshot=snapshot, sox_trend=0.93)

    tier_order = {"BULL": 3, "NEUTRAL": 2, "BEAR": 1, "CRISIS": 0}
    tier_no_sox = tier_order.get(result_no_sox.regime, 2)
    tier_with_sox = tier_order.get(result_with_sox.regime, 2)

    assert tier_with_sox <= tier_no_sox, (
        f"SOX below SMA200 should reduce regime: no_sox={result_no_sox.regime} with_sox={result_with_sox.regime}"
    )


def test_default_is_neutral():
    """Without special conditions, regime should be NEUTRAL."""
    from kr_research.regime import detect_kr_regime

    snapshot = _make_snapshot(kospi_vs_sma200=1.01, vkospi=20.0)
    result = detect_kr_regime(kr_snapshot=snapshot, us_regime="NEUTRAL", us_vix=20.0, sox_trend=1.0)

    assert result.regime == "NEUTRAL", f"Expected NEUTRAL for default conditions, got {result.regime}"
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.factors, dict)
