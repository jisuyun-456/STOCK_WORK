"""Tests for phase_regime allocation update bug.

Bug: `if cash_amount > 0` guard prevented portfolios.json update
in BULL/NEUTRAL regimes where CASH=0, leaving GRW at allocated=$0.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _make_portfolios_bear() -> dict:
    """Simulate portfolios.json stuck in BEAR allocation."""
    return {
        "account_total": 100_000.0,
        "account_total_history": [],
        "inception": {"total": 100_000.0, "strategies": {
            "MOM": 5_000.0, "VAL": 15_000.0, "QNT": 10_000.0,
            "LEV": 25_000.0, "LEV_ST": 25_000.0, "GRW": 0.0,
        }},
        "strategies": {
            "MOM":    {"allocated": 5_000.0,  "cash": 5_000.0,  "positions": {}, "nav_history": []},
            "VAL":    {"allocated": 15_000.0, "cash": 15_000.0, "positions": {}, "nav_history": []},
            "QNT":    {"allocated": 10_000.0, "cash": 10_000.0, "positions": {}, "nav_history": []},
            "LEV":    {"allocated": 25_000.0, "cash": 25_000.0, "positions": {}, "nav_history": []},
            "LEV_ST": {"allocated": 25_000.0, "cash": 25_000.0, "positions": {}, "nav_history": []},
            "GRW":    {"allocated": 0.0,      "cash": 0.0,      "positions": {}, "nav_history": []},
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# T1: BULL regime (CASH=0) → GRW allocated이 올바르게 설정됨
# ─────────────────────────────────────────────────────────────────────────────
def test_bull_regime_updates_grw_allocated():
    """BULL regime (CASH=0%)에서 phase_regime이 GRW allocated를 업데이트해야 한다."""
    from run_cycle import phase_regime
    from research.models import RegimeDetection
    from datetime import datetime, timezone

    portfolios = _make_portfolios_bear()

    mock_regime = RegimeDetection(
        regime="BULL", sp500_vs_sma200=1.05, vix_level=18.0,
        reasoning="mock BULL", timestamp=datetime.now(timezone.utc).isoformat(),
    )

    with (
        patch("run_cycle.load_portfolios", return_value=portfolios),
        patch("run_cycle.save_portfolios") as mock_save,
        patch("research.consensus.detect_regime_enhanced", return_value=mock_regime),
        patch("news.sentiment.analyze_sentiment", side_effect=Exception("skip")),
        patch("research.polymarket.fetch_macro_markets", side_effect=Exception("skip")),
    ):
        regime_info, allocations = phase_regime(market_data={"news_trigger": {"active": False}})

    # save_portfolios should have been called
    assert mock_save.called, "BULL regime에서도 save_portfolios 호출돼야 함"

    # GRW must be funded now
    saved_portfolios = mock_save.call_args[0][0]
    grw = saved_portfolios["strategies"]["GRW"]
    assert grw["allocated"] > 0, f"GRW allocated should be > 0, got {grw['allocated']}"

    # BULL allocation: GRW = 12.5% of 100k = $12,500
    from strategies.regime_allocator import REGIME_ALLOCATIONS
    expected_grw = REGIME_ALLOCATIONS["BULL"]["GRW"] * 100_000.0
    assert abs(grw["allocated"] - expected_grw) < 100.0, (
        f"GRW allocated expected ~${expected_grw:,.0f}, got ${grw['allocated']:,.0f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T2: NEUTRAL regime (CASH=0) → 동일하게 업데이트
# ─────────────────────────────────────────────────────────────────────────────
def test_neutral_regime_updates_all_strategies():
    """NEUTRAL regime에서도 모든 전략 allocated가 업데이트됨."""
    from run_cycle import phase_regime
    from research.models import RegimeDetection
    from datetime import datetime, timezone

    portfolios = _make_portfolios_bear()

    mock_regime = RegimeDetection(
        regime="NEUTRAL", sp500_vs_sma200=1.01, vix_level=22.0,
        reasoning="mock NEUTRAL", timestamp=datetime.now(timezone.utc).isoformat(),
    )

    with (
        patch("run_cycle.load_portfolios", return_value=portfolios),
        patch("run_cycle.save_portfolios") as mock_save,
        patch("research.consensus.detect_regime_enhanced", return_value=mock_regime),
        patch("news.sentiment.analyze_sentiment", side_effect=Exception("skip")),
        patch("research.polymarket.fetch_macro_markets", side_effect=Exception("skip")),
    ):
        regime_info, allocations = phase_regime(market_data={"news_trigger": {"active": False}})

    assert mock_save.called
    saved = mock_save.call_args[0][0]["strategies"]

    from strategies.regime_allocator import REGIME_ALLOCATIONS
    total = 100_000.0
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST", "GRW"]:
        expected = REGIME_ALLOCATIONS["NEUTRAL"].get(code, 0) * total
        actual = saved[code]["allocated"]
        assert abs(actual - expected) < 100.0, (
            f"{code}: expected ~${expected:,.0f}, got ${actual:,.0f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# T3: CRISIS regime (CASH=27.5%) → 기존 동작 유지 (GRW=0)
# ─────────────────────────────────────────────────────────────────────────────
def test_crisis_regime_still_works():
    """CRISIS regime에서도 save_portfolios 호출, GRW=0 유지."""
    from run_cycle import phase_regime
    from research.models import RegimeDetection
    from datetime import datetime, timezone

    portfolios = _make_portfolios_bear()

    mock_regime = RegimeDetection(
        regime="CRISIS", sp500_vs_sma200=0.92, vix_level=45.0,
        reasoning="mock CRISIS", timestamp=datetime.now(timezone.utc).isoformat(),
    )

    with (
        patch("run_cycle.load_portfolios", return_value=portfolios),
        patch("run_cycle.save_portfolios") as mock_save,
        patch("research.consensus.detect_regime_enhanced", return_value=mock_regime),
        patch("news.sentiment.analyze_sentiment", side_effect=Exception("skip")),
        patch("research.polymarket.fetch_macro_markets", side_effect=Exception("skip")),
    ):
        regime_info, allocations = phase_regime(market_data={"news_trigger": {"active": False}})

    assert mock_save.called
    saved = mock_save.call_args[0][0]["strategies"]

    from strategies.regime_allocator import REGIME_ALLOCATIONS
    grw_expected = REGIME_ALLOCATIONS["CRISIS"].get("GRW", 0) * 100_000.0  # 0
    assert abs(saved["GRW"]["allocated"] - grw_expected) < 1.0
