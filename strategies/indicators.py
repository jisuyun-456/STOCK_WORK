"""Technical indicators — RSI, MACD, Bollinger Bands, Volume analysis.

Pure pandas/numpy implementation. No external dependencies (ta-lib, pandas-ta).
Used by Phase 1 to compute market_data["indicators"] dict per symbol.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_indicators(
    close: pd.Series,
    volume: pd.Series | None = None,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> dict:
    """Compute technical indicators for a single symbol.

    Args:
        close: Closing price series (oldest → newest).
        volume: Volume series (optional).
        rsi_period: RSI lookback period (default 14).
        macd_fast/slow/signal: MACD EMA periods.
        bb_period: Bollinger Bands lookback period.
        bb_std: Bollinger Bands standard deviation multiplier.

    Returns:
        Dict with all indicators. Empty dict if insufficient data.
    """
    if len(close) < max(200, macd_slow + macd_signal):
        # Need at least 200 bars for SMA200
        if len(close) < 50:
            return {}

    close = close.dropna()
    current_price = float(close.iloc[-1])

    result: dict = {}

    # ─── RSI (Wilder Smoothing) ────────────────────────────────────────
    result.update(_compute_rsi(close, rsi_period))

    # ─── MACD ──────────────────────────────────────────────────────────
    result.update(_compute_macd(close, macd_fast, macd_slow, macd_signal))

    # ─── Bollinger Bands ───────────────────────────────────────────────
    result.update(_compute_bollinger(close, bb_period, bb_std))

    # ─── Volume Ratio ──────────────────────────────────────────────────
    if volume is not None and len(volume) >= 20:
        vol_clean = volume.dropna()
        if len(vol_clean) >= 20:
            avg_vol = float(vol_clean.iloc[-20:].mean())
            cur_vol = float(vol_clean.iloc[-1])
            result["volume_ratio"] = round(cur_vol / avg_vol, 2) if avg_vol > 0 else None
        else:
            result["volume_ratio"] = None
    else:
        result["volume_ratio"] = None

    # ─── SMAs ──────────────────────────────────────────────────────────
    result["sma_20"] = round(float(close.iloc[-20:].mean()), 2) if len(close) >= 20 else None
    result["sma_50"] = round(float(close.iloc[-50:].mean()), 2) if len(close) >= 50 else None
    result["sma_200"] = round(float(close.iloc[-200:].mean()), 2) if len(close) >= 200 else None

    if result["sma_200"] and result["sma_200"] > 0:
        result["price_vs_sma200"] = round(current_price / result["sma_200"], 4)
    else:
        result["price_vs_sma200"] = None

    # ─── Trend Classification ──────────────────────────────────────────
    result["trend"] = _classify_trend(close, result)

    return result


def _compute_rsi(close: pd.Series, period: int = 14) -> dict:
    """Compute RSI using Wilder smoothing (EWM adjust=False)."""
    if len(close) < period + 1:
        return {"rsi": 50.0}  # neutral default

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    rsi_val = float(rsi.iloc[-1])
    if np.isnan(rsi_val):
        rsi_val = 50.0

    return {"rsi": round(rsi_val, 1)}


def _compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """Compute MACD line, signal line, histogram, and cross signal."""
    if len(close) < slow + signal:
        return {
            "macd": 0.0,
            "macd_signal": 0.0,
            "macd_hist": 0.0,
            "macd_cross": "none",
        }

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_val = float(macd_line.iloc[-1])
    signal_val = float(signal_line.iloc[-1])
    hist_val = float(histogram.iloc[-1])

    # Cross detection (compare last two bars)
    cross = "none"
    if len(histogram) >= 2:
        prev_hist = float(histogram.iloc[-2])
        if prev_hist <= 0 < hist_val:
            cross = "bullish"
        elif prev_hist >= 0 > hist_val:
            cross = "bearish"

    return {
        "macd": round(macd_val, 4),
        "macd_signal": round(signal_val, 4),
        "macd_hist": round(hist_val, 4),
        "macd_cross": cross,
    }


def _compute_bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> dict:
    """Compute Bollinger Bands and %B."""
    if len(close) < period:
        return {
            "bb_upper": None,
            "bb_middle": None,
            "bb_lower": None,
            "bb_pct_b": 0.5,
            "bb_squeeze": False,
        }

    rolling_mean = close.rolling(period).mean()
    rolling_std = close.rolling(period).std()

    upper = rolling_mean + num_std * rolling_std
    lower = rolling_mean - num_std * rolling_std

    bb_upper = float(upper.iloc[-1])
    bb_middle = float(rolling_mean.iloc[-1])
    bb_lower = float(lower.iloc[-1])
    current = float(close.iloc[-1])

    band_width = bb_upper - bb_lower
    pct_b = (current - bb_lower) / band_width if band_width > 0 else 0.5

    # Squeeze: bandwidth < 50% of 120-day average bandwidth
    squeeze = False
    if len(close) >= 120:
        bw_series = (upper - lower) / rolling_mean
        bw_avg = float(bw_series.iloc[-120:].mean())
        bw_current = band_width / bb_middle if bb_middle > 0 else 0
        squeeze = bw_current < bw_avg * 0.5

    return {
        "bb_upper": round(bb_upper, 2),
        "bb_middle": round(bb_middle, 2),
        "bb_lower": round(bb_lower, 2),
        "bb_pct_b": round(pct_b, 3),
        "bb_squeeze": squeeze,
    }


def _classify_trend(close: pd.Series, indicators: dict) -> str:
    """Classify overall trend from multiple indicators."""
    signals = 0  # positive = bullish, negative = bearish

    rsi = indicators.get("rsi", 50)
    if rsi > 60:
        signals += 1
    elif rsi < 40:
        signals -= 1

    macd_hist = indicators.get("macd_hist", 0)
    if macd_hist > 0:
        signals += 1
    elif macd_hist < 0:
        signals -= 1

    price_vs_sma200 = indicators.get("price_vs_sma200")
    if price_vs_sma200 is not None:
        if price_vs_sma200 > 1.05:
            signals += 1
        elif price_vs_sma200 < 0.95:
            signals -= 1

    sma_50 = indicators.get("sma_50")
    sma_200 = indicators.get("sma_200")
    if sma_50 is not None and sma_200 is not None and sma_200 > 0:
        if sma_50 > sma_200:
            signals += 1  # golden cross territory
        else:
            signals -= 1  # death cross territory

    if signals >= 3:
        return "strong_up"
    elif signals >= 1:
        return "up"
    elif signals <= -3:
        return "strong_down"
    elif signals <= -1:
        return "down"
    return "neutral"
