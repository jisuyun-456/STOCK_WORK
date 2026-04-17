"""Tests for execution/monitor_rules.py — MDD check with realloc window.

Bug context: check_strategy_mdd() was using max() over the full nav_history,
which caused false MDD triggers after strategy reallocation (e.g. VAL $15K→$10K
produced a phantom -33.4% MDD even though post-realloc NAV was healthy).

Fix: use post-realloc window only, same pattern as performance_calculator.py.
"""
import pytest
from execution.monitor_rules import check_strategy_mdd


# ──────────────────────────────────────────────
# CASE 1: realloc 없음 — 기본 MDD 계산
# ──────────────────────────────────────────────

def test_no_realloc_below_threshold():
    """MDD -10% → threshold -20%: triggered=False"""
    nav_history = [{"nav": 10000}, {"nav": 9500}, {"nav": 9000}]
    triggered, msg = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is False
    assert msg == ""


def test_no_realloc_above_threshold():
    """MDD -21% → threshold -20%: triggered=True"""
    nav_history = [{"nav": 10000}, {"nav": 8500}, {"nav": 7900}]
    triggered, msg = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is True
    assert "strategy_mdd" in msg


# ──────────────────────────────────────────────
# CASE 2: realloc 아티팩트 — 핵심 버그 케이스
# ──────────────────────────────────────────────

def test_realloc_artifact_should_not_trigger():
    """VAL: $15K→$10K 재배분. realloc 이후 NAV는 정상(-3.9%).
    이전 패턴(full peak)에서는 -33.4%로 오판정됐던 케이스."""
    nav_history = [
        {"nav": 15063},                          # 재배분 전 고점
        {"nav": 12000},                          # 재배분 전 하락
        {"nav": 10032, "event": "realloc"},      # 재배분 시점 → 새 기준
        {"nav": 10200},                          # 재배분 후 상승
        {"nav": 9800},                           # 재배분 후 소폭 하락
    ]
    triggered, msg = check_strategy_mdd(nav_history, threshold=-0.20)
    # post-realloc peak=10200, current=9800 → MDD=-3.9% → NOT triggered
    assert triggered is False, f"False MDD triggered (realloc artifact): {msg}"


def test_realloc_genuine_mdd_triggers():
    """재배분 후 진짜 -25.7% 손실은 트리거돼야 함."""
    nav_history = [
        {"nav": 15063},
        {"nav": 10032, "event": "realloc"},
        {"nav": 10500},
        {"nav": 7800},                           # realloc 이후 -25.7%
    ]
    triggered, msg = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is True
    assert "strategy_mdd" in msg


def test_multiple_reallocs_uses_latest():
    """복수 realloc이 있을 때 마지막 realloc 이후 window를 사용해야 함."""
    nav_history = [
        {"nav": 20000},
        {"nav": 15000, "event": "realloc"},      # 1차 재배분
        {"nav": 14000},
        {"nav": 10000, "event": "realloc"},      # 2차 재배분 → 이 이후가 기준
        {"nav": 10500},
        {"nav": 9600},                           # -8.6% → NOT triggered
    ]
    triggered, msg = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is False, f"False trigger after multiple reallocs: {msg}"


def test_realloc_is_only_entry_after_window():
    """realloc 이후 엔트리가 1개뿐이면 길이 부족 → triggered=False"""
    nav_history = [
        {"nav": 15000},
        {"nav": 10000, "event": "realloc"},      # window = [10000] → len=1
    ]
    triggered, _ = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is False


# ──────────────────────────────────────────────
# CASE 3: 엣지 케이스
# ──────────────────────────────────────────────

def test_edge_single_entry():
    triggered, _ = check_strategy_mdd([{"nav": 10000}])
    assert triggered is False


def test_edge_empty():
    triggered, _ = check_strategy_mdd([])
    assert triggered is False


def test_edge_zero_peak():
    """peak=0 이면 ZeroDivision 없이 False 반환"""
    nav_history = [{"nav": 0}, {"nav": 0}]
    triggered, _ = check_strategy_mdd(nav_history, threshold=-0.20)
    assert triggered is False
