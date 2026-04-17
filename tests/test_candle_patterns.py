"""Unit tests for _detect_candle_patterns in kr_research.agent_runner."""
import pytest
from kr_research.agent_runner import _detect_candle_patterns


def _row(d, o, h, l, c, v=1000):
    return {"d": d, "o": o, "h": h, "l": l, "c": c, "v": v}


def test_empty_returns_empty():
    assert _detect_candle_patterns([]) == []


def test_too_few_rows_returns_empty():
    rows = [_row("2026-01-01", 100, 110, 90, 105),
            _row("2026-01-02", 105, 115, 95, 110)]
    assert _detect_candle_patterns(rows) == []


def test_doji_detected():
    rows = [
        _row("2026-01-01", 100, 110, 90, 95),
        _row("2026-01-02", 95, 105, 85, 90),
        _row("2026-01-03", 100, 120, 80, 101),  # body=1, total=40 → body_pct=2.5% < 10%
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "도지" for p in pats)


def test_hammer_after_downtrend():
    # body=5 (body_pct=5/19=0.26 > 0.1), lower_wick=12>=2*5=10, upper_wick=2<=5*0.5=2.5
    rows = [
        _row("2026-01-01", 110, 115, 105, 108),
        _row("2026-01-02", 108, 112, 100, 105),  # downtrend: prev close < prev prev close ✓
        _row("2026-01-03", 100, 107, 88, 105),   # body=5, lw=12, uw=2
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "망치형" and p["signal"] == "buy" for p in pats)


def test_shooting_star_after_uptrend():
    # body=4 (body_pct=4/16=0.25 > 0.1), upper_wick=11>=2*4=8, lower_wick=1<=4*0.5=2
    rows = [
        _row("2026-01-01", 90, 95, 85, 93),
        _row("2026-01-02", 93, 98, 88, 96),    # uptrend: prev close > prev prev close ✓
        _row("2026-01-03", 100, 115, 99, 104), # body=4, uw=11, lw=1
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "유성형" and p["signal"] == "sell" for p in pats)


def test_bullish_engulfing():
    rows = [
        _row("2026-01-01", 110, 115, 105, 110),
        _row("2026-01-02", 110, 112, 100, 102),  # bearish: o=110 > c=102
        _row("2026-01-03", 100, 115, 99, 112),   # bullish engulf: o<=102, c>=110
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "상승장악형" and p["signal"] == "buy" for p in pats)


def test_bearish_engulfing():
    rows = [
        _row("2026-01-01", 90, 95, 85, 90),
        _row("2026-01-02", 90, 105, 89, 103),  # bullish: c=103 > o=90
        _row("2026-01-03", 106, 108, 88, 89),  # bearish engulf: o>=103, c<=90
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "하락장악형" and p["signal"] == "sell" for p in pats)


def test_morning_star():
    # prev candle is bullish (o=108, c=110) → bullish engulfing won't trigger (pc≮po)
    rows = [
        _row("2026-01-01", 120, 122, 110, 111),  # bearish: body=9
        _row("2026-01-02", 108, 113, 107, 110),  # bullish small body=2 < 9*0.4=3.6 ✓
        _row("2026-01-03", 110, 125, 109, 122),  # bullish: body=12 > 9*0.5=4.5 ✓
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "새벽별" and p["signal"] == "buy" for p in pats)


def test_evening_star():
    # prev candle is bearish (o=112, c=110) → bearish engulfing won't trigger (pc≯po)
    rows = [
        _row("2026-01-01", 100, 112, 99, 110),  # bullish: body=10
        _row("2026-01-02", 112, 114, 109, 110),  # bearish small body=2 < 10*0.4=4 ✓
        _row("2026-01-03", 111, 112, 98, 100),   # bearish: body=11 > 10*0.5=5 ✓
    ]
    pats = _detect_candle_patterns(rows)
    assert any(p["pattern"] == "석별형" and p["signal"] == "sell" for p in pats)


def test_returns_at_most_8():
    rows = [_row(f"2026-01-{i+1:02d}", 100, 120, 80, 101) for i in range(20)]
    pats = _detect_candle_patterns(rows)
    assert len(pats) <= 8


def test_zero_total_range_skipped():
    rows = [
        _row("2026-01-01", 100, 100, 100, 100),  # total=0, should skip
        _row("2026-01-02", 100, 100, 100, 100),
        _row("2026-01-03", 100, 100, 100, 100),
    ]
    # No crash, just empty result
    _detect_candle_patterns(rows)
