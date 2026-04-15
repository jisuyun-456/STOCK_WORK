# tests/test_regime_stability.py
"""Regime stability filter tests: 3-bar hold + flicker suppression."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from strategies.regime_allocator import allocate, REGIME_ALLOCATIONS


# ── allocate() flicker_suppression ────────────────────────────────────────────

def test_allocate_default_no_flicker_matches_weights():
    alloc = allocate("BULL", 100_000.0)
    assert abs(alloc["MOM"] - 15_000.0) < 0.5  # BULL MOM=0.15 (GRW 추가로 재배분)
    assert abs(alloc["LEV"] - 25_000.0) < 0.5
    assert abs(alloc["CASH"] - 0.0) < 0.5


def test_allocate_flicker_halves_risk_and_boosts_cash():
    alloc = allocate("BULL", 100_000.0, flicker_suppression=True)
    # All non-CASH strategies halved
    assert abs(alloc["MOM"] - 7_500.0) < 0.5   # BULL MOM=0.15, halved=7500
    assert abs(alloc["LEV"] - 12_500.0) < 0.5
    assert abs(alloc["LEV_ST"] - 12_500.0) < 0.5
    # BULL CASH=0, non-CASH total=100%, diverted = 100k * 1.0 * 0.5 = 50k
    assert abs(alloc["CASH"] - 50_000.0) < 0.5


def test_allocate_flicker_preserves_total_capital():
    for regime in ("BULL", "NEUTRAL", "BEAR", "CRISIS"):
        alloc = allocate(regime, 100_000.0, flicker_suppression=True)
        total = sum(alloc.values())
        expected = sum(REGIME_ALLOCATIONS[regime].values()) * 100_000.0
        assert abs(total - expected) < 1.0, f"{regime}: total {total:.2f} != {expected:.2f}"


def test_allocate_flicker_crisis_keeps_existing_cash():
    # CRISIS: CASH=0.275, others=0.725 → diverted = 100k * 0.725 * 0.5 = 36,250
    # total CASH = 27,500 + 36,250 = 63,750
    alloc = allocate("CRISIS", 100_000.0, flicker_suppression=True)
    assert abs(alloc["CASH"] - (27_500.0 + 36_250.0)) < 0.5


# ── 3-bar hysteresis ──────────────────────────────────────────────────────────

def _apply_hysteresis(prev: str, consec: int, detected: str, min_hold: int = 3) -> str:
    """run_cycle.py 하이스테리시스 로직 미러 (독립 테스트용)."""
    if detected != prev and consec < min_hold:
        return prev
    return detected


def test_hysteresis_blocks_switch_at_1_cycle():
    assert _apply_hysteresis("NEUTRAL", 1, "BEAR") == "NEUTRAL"


def test_hysteresis_blocks_switch_at_2_cycles():
    # 3-bar rule: 2 사이클에서도 여전히 차단
    assert _apply_hysteresis("NEUTRAL", 2, "BEAR") == "NEUTRAL"


def test_hysteresis_allows_switch_at_3_cycles():
    assert _apply_hysteresis("NEUTRAL", 3, "BEAR") == "BEAR"


def test_hysteresis_same_regime_passes_through():
    assert _apply_hysteresis("BULL", 1, "BULL") == "BULL"


# ── Flicker detection ─────────────────────────────────────────────────────────

def _count_transitions(history: list) -> int:
    return sum(1 for i in range(1, len(history)) if history[i] != history[i - 1])


def _detect_flicker(history: list, threshold: int = 4) -> bool:
    return _count_transitions(history) >= threshold


def test_flicker_off_when_no_transitions():
    assert _detect_flicker(["NEUTRAL"] * 20) is False


def test_flicker_off_at_3_transitions():
    # N,B,N,B → 3 transitions
    history = ["NEUTRAL", "BEAR", "NEUTRAL", "BEAR"]
    assert _count_transitions(history) == 3
    assert _detect_flicker(history) is False


def test_flicker_on_at_4_transitions():
    # N,B,N,B,N → 4 transitions
    history = ["NEUTRAL", "BEAR", "NEUTRAL", "BEAR", "NEUTRAL"]
    assert _count_transitions(history) == 4
    assert _detect_flicker(history) is True


def test_flicker_on_with_mixed_regimes():
    # BULL→NEUTRAL→BEAR→CRISIS→BEAR = 4 transitions
    history = ["BULL", "NEUTRAL", "BEAR", "CRISIS", "BEAR"]
    assert _detect_flicker(history) is True


def test_flicker_window_capped_at_20():
    # 21개 → 마지막 20개만 사용 시뮬레이션
    raw = ["NEUTRAL"] * 15 + ["BEAR", "NEUTRAL", "BEAR", "NEUTRAL", "BEAR", "NEUTRAL"]
    window = raw[-20:]
    assert len(window) == 20
    assert _detect_flicker(window) is True  # 5 transitions


# ── regime_state.json schema roundtrip ────────────────────────────────────────

def test_regime_state_schema_roundtrip(tmp_path):
    state_path = tmp_path / "regime_state.json"
    state = {
        "regime": "CRISIS",
        "since": "2026-04-15",
        "consecutive_cycles": 2,
        "regime_history": ["NEUTRAL", "BEAR", "CRISIS", "CRISIS"],
        "flicker_suppression": False,
    }
    state_path.write_text(json.dumps(state))
    loaded = json.loads(state_path.read_text())
    assert loaded["regime_history"] == ["NEUTRAL", "BEAR", "CRISIS", "CRISIS"]
    assert loaded["flicker_suppression"] is False
    assert loaded["consecutive_cycles"] == 2
