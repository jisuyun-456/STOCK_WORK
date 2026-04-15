# tests/test_backtest_core.py
"""Unit tests for scripts/backtest_core.py — all fail until implementation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import pytest

from scripts.backtest_core import (
    generate_windows, detect_regime,
    calc_sharpe, calc_mdd, calc_alpha,
    simulate_spy_buyhold, simulate_spy_sma200, simulate_random,
    simulate_mom_pure,
    TRAIN_DAYS, OOS_DAYS,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _bdate_range(start: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)

def _spy_series(dates, prices) -> pd.Series:
    return pd.Series(prices, index=dates)

def _vix_series(dates, vals) -> pd.Series:
    return pd.Series(vals, index=dates)


# ── Window generator ─────────────────────────────────────────────────────

def test_generate_windows_count():
    idx = _bdate_range("2020-01-01", "2022-12-31")
    windows = generate_windows(idx[0], idx[-1], train=252, oos=126, trading_days=idx)
    # each window = 252 train + 126 OOS, stepping 126 days
    assert len(windows) >= 4

def test_generate_windows_no_oos_overlap():
    idx = _bdate_range("2020-01-01", "2022-12-31")
    windows = generate_windows(idx[0], idx[-1], trading_days=idx)
    for a, b in zip(windows, windows[1:]):
        assert b.oos_start > a.oos_end

def test_generate_windows_oos_within_range():
    idx = _bdate_range("2020-01-01", "2022-12-31")
    windows = generate_windows(idx[0], idx[-1], trading_days=idx)
    assert all(w.oos_end <= idx[-1] for w in windows)


# ── Regime detector ──────────────────────────────────────────────────────

def _mk_regime_data(n=300, spy_val=450.0, vix_val=18.0):
    dates = _bdate_range("2019-01-01", pd.Timestamp("2019-01-01") + pd.offsets.BDay(n))
    spy = pd.Series([spy_val] * n, index=dates[:n])
    vix = pd.Series([vix_val] * n, index=dates[:n])
    return dates[:n], spy, vix

def test_detect_regime_bull():
    dates, spy, vix = _mk_regime_data(spy_val=500.0, vix_val=15.0)
    # SMA200 of 500 = 500; SPY > SMA200, VIX < 20 → BULL
    regime = detect_regime(dates[-1], spy, vix)
    assert regime == "BULL"

def test_detect_regime_crisis():
    dates, spy, vix = _mk_regime_data(spy_val=400.0, vix_val=42.0)
    regime = detect_regime(dates[-1], spy, vix)
    assert regime == "CRISIS"

def test_detect_regime_bear():
    # SPY below its SMA200, VIX 35
    dates = _bdate_range("2019-01-01", "2020-03-01")
    n = len(dates)
    # Create declining SPY so price < SMA200
    prices = [500.0 - i * 0.5 for i in range(n)]  # declining
    spy = pd.Series(prices, index=dates)
    vix = pd.Series([35.0] * n, index=dates)
    regime = detect_regime(dates[-1], spy, vix)
    assert regime == "BEAR"

def test_detect_regime_neutral():
    dates, spy, vix = _mk_regime_data(spy_val=500.0, vix_val=25.0)
    regime = detect_regime(dates[-1], spy, vix)
    assert regime == "NEUTRAL"


# ── Metrics ──────────────────────────────────────────────────────────────

def test_calc_mdd_known():
    equity = pd.Series([100.0, 120.0, 90.0, 95.0])
    mdd = calc_mdd(equity)
    assert abs(mdd - (-0.25)) < 1e-6   # 120 → 90 = -25%

def test_calc_mdd_no_drawdown():
    equity = pd.Series([100.0, 110.0, 120.0])
    assert calc_mdd(equity) == 0.0

def test_calc_sharpe_zero_variance():
    returns = pd.Series([0.0] * 252)
    result = calc_sharpe(returns)
    assert result == 0.0 or result is None  # implementation may return 0 or None

def test_calc_alpha_negative():
    # flat equity, rising SPY → negative alpha
    dates = _bdate_range("2020-01-01", "2020-12-31")
    equity = pd.Series([100.0] * len(dates), index=dates)
    spy = pd.Series([100.0 + i * 0.1 for i in range(len(dates))], index=dates)
    alpha = calc_alpha(equity, spy)
    assert alpha < 0


# ── Benchmarks ───────────────────────────────────────────────────────────

def test_spy_buyhold_final_equity():
    dates = _bdate_range("2020-01-01", "2020-12-31")
    spy = pd.Series([100.0 + i * 0.5 for i in range(len(dates))], index=dates)
    capital = 10_000.0
    result = simulate_spy_buyhold(spy, capital)
    expected = capital * spy.iloc[-1] / spy.iloc[0]
    assert abs(result.equity_curve.iloc[-1] - expected) < 1.0

def test_spy_sma200_flat_when_below():
    # SPY below SMA200 for entire period → stays cash → equity flat
    dates = _bdate_range("2019-01-01", "2020-12-31")
    n = len(dates)
    # Start high then drop below SMA200 after 250 days
    prices = [500.0] * 250 + [200.0] * (n - 250)
    spy = pd.Series(prices, index=dates)
    result = simulate_spy_sma200(spy, 10_000.0)
    # After drop, equity should stop falling (held cash)
    oos_equity = result.equity_curve.iloc[260:]
    assert oos_equity.std() < 1.0  # essentially flat

def test_simulate_random_deterministic():
    dates = _bdate_range("2020-01-01", "2021-12-31")
    n = len(dates)
    prices_dict = {
        "AAPL": [100.0 + i * 0.1 for i in range(n)],
        "MSFT": [200.0 + i * 0.05 for i in range(n)],
    }
    prices = pd.DataFrame(prices_dict, index=dates)
    r1 = simulate_random(prices, 10_000.0, seed=42)
    r2 = simulate_random(prices, 10_000.0, seed=42)
    pd.testing.assert_series_equal(r1.equity_curve, r2.equity_curve)


# ── MOM simulator (pure, no network) ────────────────────────────────────

def test_simulate_mom_selects_momentum_leader():
    """Synthetic 3-ticker universe: LEADER has 30% return, others flat."""
    dates = _bdate_range("2019-01-01", "2021-06-30")
    n = len(dates)
    LEADER_return = 1.30
    prices = pd.DataFrame({
        "LEADER": [100.0 * (LEADER_return ** (i / n)) for i in range(n)],
        "FLAT1":  [100.0] * n,
        "FLAT2":  [100.0] * n,
    }, index=dates)
    vix = pd.Series([18.0] * n, index=dates)
    spy = pd.Series([100.0 + i * 0.1 for i in range(n)], index=dates)
    result = simulate_mom_pure(prices, spy, vix, capital=10_000.0)
    # LEADER should appear in trades
    symbols = {t["symbol"] for t in result.trades}
    assert "LEADER" in symbols
