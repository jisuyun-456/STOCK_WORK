# scripts/backtest_core.py
"""Walk-forward backtest core — pure functions, no I/O, no live API calls."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

TRAIN_DAYS = 252
OOS_DAYS = 126
RISK_FREE_RATE = 0.04
TRANSACTION_COST_BPS = 5  # 5 basis points per trade


@dataclass
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp


@dataclass
class StrategyResult:
    strategy: str
    equity_curve: pd.Series
    trades: list[dict] = field(default_factory=list)
    total_return: float = 0.0
    sharpe: float = 0.0
    mdd: float = 0.0
    win_rate: float = 0.0
    alpha_vs_spy: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class BacktestReport:
    start: str
    end: str
    windows: list[Window]
    strategies: dict[str, StrategyResult]
    benchmarks: dict[str, StrategyResult]
    regime_timeline: dict[str, str]  # date_str → regime


# ── Window generator ──────────────────────────────────────────────────────

def generate_windows(
    start: pd.Timestamp,
    end: pd.Timestamp,
    train: int = TRAIN_DAYS,
    oos: int = OOS_DAYS,
    trading_days: Optional[pd.DatetimeIndex] = None,
) -> list[Window]:
    """Generate non-overlapping OOS walk-forward windows."""
    if trading_days is None:
        trading_days = pd.bdate_range(start, end)
    idx = trading_days[(trading_days >= start) & (trading_days <= end)]
    windows = []
    pos = 0
    while pos + train + oos <= len(idx):
        w = Window(
            train_start=idx[pos],
            train_end=idx[pos + train - 1],
            oos_start=idx[pos + train],
            oos_end=idx[min(pos + train + oos - 1, len(idx) - 1)],
        )
        windows.append(w)
        pos += oos
    return windows


# ── Regime detector ───────────────────────────────────────────────────────

def detect_regime(
    as_of: pd.Timestamp,
    spy: pd.Series,
    vix: pd.Series,
) -> str:
    """Simplified regime: BULL/NEUTRAL/BEAR/CRISIS based on SPY SMA200 + VIX."""
    spy_slice = spy.loc[:as_of].dropna()
    vix_slice = vix.loc[:as_of].dropna()
    if len(spy_slice) < 1 or len(vix_slice) < 1:
        return "NEUTRAL"
    v = float(vix_slice.iloc[-1])
    if v >= 40:
        return "CRISIS"
    s = float(spy_slice.iloc[-1])
    sma200 = float(spy_slice.tail(200).mean())
    if s >= sma200 and v < 20:
        return "BULL"
    if s >= sma200 and v < 30:
        return "NEUTRAL"
    return "BEAR"


# ── Metrics ───────────────────────────────────────────────────────────────

def calc_mdd(equity: pd.Series) -> float:
    """Maximum drawdown (negative float, 0.0 if no drawdown)."""
    if len(equity) == 0:
        return 0.0
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    return float(drawdown.min())


def calc_sharpe(returns: pd.Series, rf: float = RISK_FREE_RATE) -> Optional[float]:
    """Annualized Sharpe. Returns 0.0 if std == 0."""
    if len(returns) < 2:
        return None
    daily_rf = rf / 252
    excess = returns - daily_rf
    std = excess.std()
    if std == 0 or math.isnan(std) or std < 1e-10:
        return 0.0
    return float(excess.mean() / std * math.sqrt(252))


def calc_win_rate(trades: list[dict]) -> float:
    """Fraction of closed round-trips with positive P&L."""
    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return 0.0
    return sum(1 for t in closed if t["pnl"] > 0) / len(closed)


def calc_alpha(equity: pd.Series, spy: pd.Series) -> float:
    """Annualized alpha = strategy annualized return - SPY annualized return."""
    def annualize(s: pd.Series) -> float:
        s = s.dropna()
        if len(s) < 2 or s.iloc[0] == 0:
            return 0.0
        total = s.iloc[-1] / s.iloc[0] - 1
        years = len(s) / 252
        return (1 + total) ** (1 / max(years, 1e-6)) - 1

    spy_aligned = spy.reindex(equity.index, method="ffill").dropna()
    return annualize(equity) - annualize(spy_aligned)


# ── Portfolio runner (internal) ────────────────────────────────────────────

def _run_portfolio(
    target_weights_by_date: dict,  # {date: {symbol: weight}}
    prices: pd.DataFrame,
    capital: float,
    strategy: str,
) -> tuple[pd.Series, list[dict]]:
    """Simulate portfolio given target weights at each rebalance date.
    Between rebalances, positions drift. 5bps transaction cost on turnover."""
    all_dates = prices.index
    holdings: dict[str, float] = {}  # symbol → qty
    cash = capital
    nav_series = {}
    trades = []

    for date in all_dates:
        # Mark-to-market current nav
        nav = cash + sum(
            qty * float(prices.at[date, sym])
            for sym, qty in holdings.items()
            if sym in prices.columns and not pd.isna(prices.at[date, sym])
        )
        if nav <= 0:
            nav = cash

        # Rebalance if target provided
        if date in target_weights_by_date:
            new_w = target_weights_by_date[date]
            # Exit positions not in new weights
            for sym in list(holdings.keys()):
                if sym not in new_w and holdings.get(sym, 0) != 0:
                    if sym in prices.columns and not pd.isna(prices.at[date, sym]):
                        price = float(prices.at[date, sym])
                        proceeds = holdings[sym] * price
                        cost = abs(proceeds) * TRANSACTION_COST_BPS / 10_000
                        cash += proceeds - cost
                        holdings[sym] = 0.0

            # Recalculate nav after exits
            nav = cash + sum(
                holdings.get(sym, 0) * float(prices.at[date, sym])
                for sym in holdings
                if sym in prices.columns and not pd.isna(prices.at[date, sym])
            )

            # Enter/adjust new weights
            for sym, w in new_w.items():
                if sym not in prices.columns or pd.isna(prices.at[date, sym]):
                    continue
                price = float(prices.at[date, sym])
                target_val = nav * w
                current_val = holdings.get(sym, 0) * price
                delta = target_val - current_val
                if abs(delta) < 1.0:
                    continue
                cost = abs(delta) * TRANSACTION_COST_BPS / 10_000
                qty_change = delta / price
                holdings[sym] = holdings.get(sym, 0) + qty_change
                cash -= delta + cost
                trades.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": sym,
                    "side": "buy" if delta > 0 else "sell",
                    "qty": abs(qty_change),
                    "price": price,
                    "pnl": None,
                    "strategy": strategy,
                })

        # Final nav for this date
        nav = cash + sum(
            holdings.get(sym, 0) * float(prices.at[date, sym])
            for sym in holdings
            if sym in prices.columns and not pd.isna(prices.at[date, sym])
        )
        nav_series[date] = max(nav, 0.0)

    equity = pd.Series(nav_series)
    return equity, trades


# ── Benchmark simulators ───────────────────────────────────────────────────

def simulate_spy_buyhold(spy: pd.Series, capital: float) -> StrategyResult:
    """100% SPY from day 1, no rebalancing."""
    if len(spy) == 0:
        return StrategyResult("SPY_BH", pd.Series(dtype=float))
    qty = capital / float(spy.iloc[0])
    equity = spy * qty
    daily_ret = equity.pct_change().dropna()
    return StrategyResult(
        strategy="SPY_BH",
        equity_curve=equity,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1),
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=0.0,
        alpha_vs_spy=0.0,
    )


def simulate_spy_sma200(spy: pd.Series, capital: float) -> StrategyResult:
    """In-market when SPY > 200d SMA, else cash."""
    in_market = False
    shares = 0.0
    cash = capital
    equity = {}

    for i, (date, price) in enumerate(spy.items()):
        hist = spy.iloc[:i + 1]
        sma = float(hist.tail(200).mean())
        signal = float(price) > sma

        if signal and not in_market:
            shares = cash / float(price)
            cash = 0.0
            in_market = True
        elif not signal and in_market:
            cash = shares * float(price)
            shares = 0.0
            in_market = False

        nav = cash + shares * float(price)
        equity[date] = nav

    eq = pd.Series(equity)
    daily_ret = eq.pct_change().dropna()
    return StrategyResult(
        strategy="SPY_SMA200",
        equity_curve=eq,
        total_return=float(eq.iloc[-1] / eq.iloc[0] - 1) if len(eq) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(eq),
        win_rate=0.0,
        alpha_vs_spy=calc_alpha(eq, spy),
    )


def simulate_random(prices: pd.DataFrame, capital: float, seed: int = 42) -> StrategyResult:
    """Shuffle the dates of MOM-style signals — destroys timing alpha."""
    rng = np.random.default_rng(seed)
    all_dates = prices.index

    if len(all_dates) < TRAIN_DAYS + OOS_DAYS:
        return StrategyResult("RANDOM", pd.Series([capital], index=all_dates[:1]))

    rebal_dates = all_dates[TRAIN_DAYS::21]
    symbols = [c for c in prices.columns if c not in ("SPY", "^VIX", "QQQ")]
    weights_by_date = {}

    for rd in rebal_dates:
        avail = [s for s in symbols if s in prices.columns and not pd.isna(prices.at[rd, s])]
        if not avail:
            continue
        picks = rng.choice(avail, size=min(5, len(avail)), replace=False)
        w = {s: 1.0 / len(picks) for s in picks}
        weights_by_date[rd] = w

    oos_prices = prices.iloc[TRAIN_DAYS:] if TRAIN_DAYS < len(prices) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "RANDOM")
    daily_ret = equity.pct_change().dropna()
    spy = prices.get("SPY", pd.Series(dtype=float))
    return StrategyResult(
        strategy="RANDOM",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy) if len(spy) > 0 else 0.0,
    )


# ── MOM simulator ─────────────────────────────────────────────────────────

def simulate_mom_pure(
    prices: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    capital: float,
    max_positions: int = 10,
    lookback_long: int = 252,
    lookback_short: int = 21,
) -> StrategyResult:
    """12-1 momentum on all non-benchmark tickers. SMA200 filter. Monthly rebalance."""
    bench_cols = {"SPY", "QQQ", "^VIX", "TQQQ", "SQQQ", "BND", "GLD"}
    universe = [c for c in prices.columns if c not in bench_cols]
    all_dates = prices.index
    rebal_dates = all_dates[lookback_long::21]
    weights_by_date = {}

    for rd in rebal_dates:
        hist = prices.loc[:rd, universe].dropna(axis=1, how="all")
        scores = {}
        for sym in hist.columns:
            series = hist[sym].dropna()
            if len(series) < lookback_long + 1:
                continue
            try:
                ret_long = float(series.iloc[-lookback_short] / series.iloc[-lookback_long] - 1)
            except (IndexError, ZeroDivisionError):
                continue
            sma200 = float(series.tail(200).mean())
            price_now = float(series.iloc[-1])
            if price_now <= sma200:
                continue
            if ret_long <= 0:
                continue
            scores[sym] = ret_long

        if not scores:
            continue
        top = sorted(scores, key=scores.__getitem__, reverse=True)[:max_positions]
        w = {s: 1.0 / len(top) for s in top}
        weights_by_date[rd] = w

    oos_prices = prices.iloc[lookback_long:] if lookback_long < len(all_dates) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "MOM")
    daily_ret = equity.pct_change().dropna()
    spy_aligned = spy.reindex(equity.index, method="ffill")
    return StrategyResult(
        strategy="MOM",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy_aligned),
    )


# ── VAL simulator ─────────────────────────────────────────────────────────

def simulate_val_price_only(
    prices: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    capital: float,
    max_positions: int = 5,
) -> StrategyResult:
    """VAL proxy without FMP API: rank by low 1y volatility + positive 12m return.
    NOTE: Simplified proxy — real VAL uses PE/ROE/FCF from FMP API."""
    bench_cols = {"SPY", "QQQ", "^VIX", "TQQQ", "SQQQ", "BND", "GLD"}
    universe = [c for c in prices.columns if c not in bench_cols]
    all_dates = prices.index
    rebal_dates = all_dates[252::63]  # quarterly
    weights_by_date = {}

    for rd in rebal_dates:
        hist = prices.loc[:rd, universe].dropna(axis=1, how="all")
        scores = {}
        for sym in hist.columns:
            series = hist[sym].dropna()
            if len(series) < 253:
                continue
            ret_1y = float(series.iloc[-1] / series.iloc[-252] - 1)
            vol_1y = float(series.pct_change().tail(252).std())
            if ret_1y <= 0 or vol_1y == 0:
                continue
            scores[sym] = ret_1y / vol_1y  # Sharpe-like score

        if not scores:
            continue
        top = sorted(scores, key=scores.__getitem__, reverse=True)[:max_positions]
        w = {s: 1.0 / len(top) for s in top}
        weights_by_date[rd] = w

    oos_prices = prices.iloc[252:] if 252 < len(all_dates) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "VAL")
    daily_ret = equity.pct_change().dropna()
    spy_aligned = spy.reindex(equity.index, method="ffill")
    return StrategyResult(
        strategy="VAL",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy_aligned),
        notes=["VAL uses price-only proxy (no FMP in backtest): rank by 1y return / 1y vol"],
    )


# ── QNT simulator ─────────────────────────────────────────────────────────

def simulate_qnt_pure(
    prices: pd.DataFrame,
    ff5: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    capital: float,
    max_positions: int = 20,
    ols_window: int = 60,
) -> StrategyResult:
    """QNT: FF5 factor scoring via OLS. Monthly rebalance."""
    bench_cols = {"SPY", "QQQ", "^VIX", "TQQQ", "SQQQ", "BND", "GLD"}
    universe = [c for c in prices.columns if c not in bench_cols]
    all_dates = prices.index
    factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
    rf_col = "RF"
    rebal_dates = all_dates[252::21]
    weights_by_date = {}

    ff5_available = ff5 is not None and len(ff5) > 0 and all(c in ff5.columns for c in factor_cols)

    for rd in rebal_dates:
        hist_prices = prices.loc[:rd, universe].dropna(axis=1, how="all")

        if not ff5_available:
            # Fallback: use MOM-style scoring
            scores = {}
            for sym in hist_prices.columns:
                series = hist_prices[sym].dropna()
                if len(series) < 253:
                    continue
                ret = float(series.iloc[-1] / series.iloc[-252] - 1)
                if ret > 0:
                    scores[sym] = ret
            if not scores:
                continue
            top = sorted(scores, key=scores.__getitem__, reverse=True)[:max_positions]
            weights_by_date[rd] = {s: 1.0 / len(top) for s in top}
            continue

        ff5_slice = ff5.loc[:rd].tail(ols_window)
        if len(ff5_slice) < ols_window // 2:
            continue
        factor_matrix = ff5_slice[factor_cols].values
        recent_factor_ret = ff5_slice[factor_cols].mean().values
        rf = float(ff5_slice[rf_col].mean()) if rf_col in ff5_slice.columns else 0.0

        scores = {}
        for sym in hist_prices.columns:
            series = hist_prices[sym].dropna()
            if len(series) < ols_window + 10:
                continue
            ret_series = series.pct_change().tail(ols_window).dropna()
            if len(ret_series) < ols_window // 2:
                continue
            excess_ret = ret_series.values - rf
            T = min(len(excess_ret), factor_matrix.shape[0])
            X = np.column_stack([np.ones(T), factor_matrix[-T:]])
            y = excess_ret[-T:]
            try:
                betas, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            except Exception:
                continue
            factor_betas = betas[1:]
            composite = float(np.dot(factor_betas, recent_factor_ret))
            if composite > 0:
                scores[sym] = composite

        if not scores:
            continue
        top = sorted(scores, key=scores.__getitem__, reverse=True)[:max_positions]
        weights_by_date[rd] = {s: 1.0 / len(top) for s in top}

    oos_prices = prices.iloc[252:] if 252 < len(all_dates) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "QNT")
    daily_ret = equity.pct_change().dropna()
    spy_aligned = spy.reindex(equity.index, method="ffill")
    return StrategyResult(
        strategy="QNT",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy_aligned),
    )


# ── LEV simulator ─────────────────────────────────────────────────────────

def simulate_lev_pure(
    prices: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    capital: float,
) -> StrategyResult:
    """LEV: regime-based TQQQ/SQQQ/BND+GLD. Rebalance monthly or on regime change."""
    REGIME_MIX = {
        "BULL":    {"TQQQ": 0.5, "SPY": 0.5},
        "NEUTRAL": {"TQQQ": 0.5, "SPY": 0.5},
        "BEAR":    {"SQQQ": 0.5, "SPY": 0.5},
        "CRISIS":  {"BND": 0.6, "GLD": 0.4},
    }
    all_dates = prices.index
    weights_by_date = {}
    prev_regime = None

    for i, date in enumerate(all_dates):
        if i < 200:
            continue
        regime = detect_regime(date, spy, vix)
        if regime != prev_regime or i % 21 == 0:
            mix = REGIME_MIX.get(regime, {"SPY": 1.0})
            available = {s: w for s, w in mix.items() if s in prices.columns}
            if available:
                total = sum(available.values())
                weights_by_date[date] = {s: w / total for s, w in available.items()}
            prev_regime = regime

    oos_prices = prices.iloc[200:] if 200 < len(all_dates) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "LEV")
    daily_ret = equity.pct_change().dropna()
    spy_aligned = spy.reindex(equity.index, method="ffill")
    return StrategyResult(
        strategy="LEV",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy_aligned),
    )


# ── LEV_ST simulator ──────────────────────────────────────────────────────

def simulate_lev_st_pure(
    prices: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    capital: float,
) -> StrategyResult:
    """LEV_ST: daily VIX-5d + SPY-3d signals → TQQQ/SQQQ/CASH."""
    all_dates = prices.index
    weights_by_date = {}

    for i, date in enumerate(all_dates):
        if i < 10:
            continue
        regime = detect_regime(date, spy, vix)
        if regime == "CRISIS":
            weights_by_date[date] = {}
            continue
        vix_slice = vix.iloc[max(0, i - 5): i + 1]
        spy_slice = spy.iloc[max(0, i - 3): i + 1]
        if len(vix_slice) < 2 or len(spy_slice) < 2:
            continue
        vix_5d = float(vix_slice.iloc[-1] / vix_slice.iloc[0] - 1)
        spy_3d = float(spy_slice.iloc[-1] / spy_slice.iloc[0] - 1)

        if vix_5d <= -0.05 and spy_3d >= 0.005:
            target = "TQQQ"
        elif vix_5d >= 0.10 and spy_3d <= -0.005:
            target = "SQQQ"
        else:
            target = None

        if target and target in prices.columns:
            weights_by_date[date] = {target: 1.0}
        else:
            weights_by_date[date] = {}

    oos_prices = prices.iloc[10:] if 10 < len(all_dates) else prices
    equity, trades = _run_portfolio(weights_by_date, oos_prices, capital, "LEV_ST")
    daily_ret = equity.pct_change().dropna()
    spy_aligned = spy.reindex(equity.index, method="ffill")
    return StrategyResult(
        strategy="LEV_ST",
        equity_curve=equity,
        trades=trades,
        total_return=float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0,
        sharpe=calc_sharpe(daily_ret) or 0.0,
        mdd=calc_mdd(equity),
        win_rate=calc_win_rate(trades),
        alpha_vs_spy=calc_alpha(equity, spy_aligned),
    )


# ── Walk-forward orchestrator ─────────────────────────────────────────────

def run_walk_forward(
    prices: pd.DataFrame,
    spy: pd.Series,
    vix: pd.Series,
    ff5: pd.DataFrame,
    capital: float = 100_000.0,
) -> BacktestReport:
    """Run full walk-forward backtest for all strategies + benchmarks."""
    all_dates = prices.index
    windows = generate_windows(all_dates[0], all_dates[-1], trading_days=all_dates)

    # Strategy capital allocations (BULL defaults from REGIME_ALLOCATIONS)
    ALLOC = {"MOM": 0.20, "VAL": 0.1333, "QNT": 0.1667, "LEV": 0.25, "LEV_ST": 0.25}

    print("  [backtest] Running MOM...")
    mom = simulate_mom_pure(prices, spy, vix, capital * ALLOC["MOM"])
    print("  [backtest] Running VAL...")
    val = simulate_val_price_only(prices, spy, vix, capital * ALLOC["VAL"])
    print("  [backtest] Running QNT...")
    qnt = simulate_qnt_pure(prices, ff5, spy, vix, capital * ALLOC["QNT"])
    print("  [backtest] Running LEV...")
    lev = simulate_lev_pure(prices, spy, vix, capital * ALLOC["LEV"])
    print("  [backtest] Running LEV_ST...")
    lev_st = simulate_lev_st_pure(prices, spy, vix, capital * ALLOC["LEV_ST"])

    strategies = {"MOM": mom, "VAL": val, "QNT": qnt, "LEV": lev, "LEV_ST": lev_st}

    print("  [backtest] Running benchmarks...")
    benchmarks = {
        "SPY_BH":     simulate_spy_buyhold(spy, capital),
        "SPY_SMA200": simulate_spy_sma200(spy, capital),
        "RANDOM":     simulate_random(prices, capital),
    }
    for name, res in benchmarks.items():
        if name != "SPY_BH":
            res.alpha_vs_spy = calc_alpha(res.equity_curve, spy)

    # Regime timeline (monthly snapshots)
    regime_timeline = {}
    for i in range(200, len(all_dates), 21):
        date = all_dates[i]
        regime_timeline[date.strftime("%Y-%m-%d")] = detect_regime(date, spy, vix)

    return BacktestReport(
        start=all_dates[0].strftime("%Y-%m-%d"),
        end=all_dates[-1].strftime("%Y-%m-%d"),
        windows=windows,
        strategies=strategies,
        benchmarks=benchmarks,
        regime_timeline=regime_timeline,
    )
