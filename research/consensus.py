"""Weighted Consensus algorithm with Regime-Aware dynamic weighting."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import RegimeDetection, ResearchVerdict

# ─── Base Weights ────────────────────────────────────────────────────────

BASE_WEIGHTS: dict[str, float] = {
    "equity_research": 0.25,
    "technical_strategist": 0.20,
    "macro_economist": 0.20,
    "portfolio_architect": 0.15,
    "risk_controller": 0.20,
}

# ─── Regime-Aware Multipliers ────────────────────────────────────────────

REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "CRISIS": {"risk_controller": 2.0, "macro_economist": 1.5},
    "BEAR": {"risk_controller": 1.5, "macro_economist": 1.3},
    "BULL": {"equity_research": 1.3, "technical_strategist": 1.2},
    "NEUTRAL": {},
}


def get_regime_weights(regime: str) -> dict[str, float]:
    """Apply regime multipliers to base weights and normalize to sum=1.0."""
    multipliers = REGIME_MULTIPLIERS.get(regime, {})
    raw = {
        agent: weight * multipliers.get(agent, 1.0)
        for agent, weight in BASE_WEIGHTS.items()
    }
    total = sum(raw.values())
    return {agent: w / total for agent, w in raw.items()}


def detect_regime(prices_df) -> RegimeDetection:
    """Detect market regime from price data.

    Uses S&P500 vs SMA200 and VIX level:
        - S&P500 < SMA200 & VIX > 30 → CRISIS
        - S&P500 < SMA200 & VIX <= 30 → BEAR
        - S&P500 > SMA200 & VIX < 20 → BULL
        - Otherwise → NEUTRAL
    """
    try:
        import yfinance as yf

        spy = yf.Ticker("SPY")
        hist = spy.history(period="1y")
        if hist.empty:
            return _neutral_fallback("No SPY data available")

        current_price = hist["Close"].iloc[-1]
        sma200 = hist["Close"].rolling(200).mean().iloc[-1]

        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="5d")
        vix_level = vix_hist["Close"].iloc[-1] if not vix_hist.empty else 20.0

    except Exception as e:
        return _neutral_fallback(f"Data fetch error: {e}")

    ratio = current_price / sma200 if sma200 > 0 else 1.0

    if ratio < 1.0 and vix_level > 30:
        regime = "CRISIS"
        reasoning = f"SPY ({current_price:.2f}) below SMA200 ({sma200:.2f}), VIX={vix_level:.1f} > 30"
    elif ratio < 1.0 and vix_level <= 30:
        regime = "BEAR"
        reasoning = f"SPY ({current_price:.2f}) below SMA200 ({sma200:.2f}), VIX={vix_level:.1f}"
    elif ratio >= 1.0 and vix_level < 20:
        regime = "BULL"
        reasoning = f"SPY ({current_price:.2f}) above SMA200 ({sma200:.2f}), VIX={vix_level:.1f} < 20"
    else:
        regime = "NEUTRAL"
        reasoning = f"SPY ({current_price:.2f}) vs SMA200 ({sma200:.2f}), VIX={vix_level:.1f}"

    return RegimeDetection(
        regime=regime,
        sp500_vs_sma200=round(ratio, 4),
        vix_level=round(vix_level, 2),
        reasoning=reasoning,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def _neutral_fallback(reason: str) -> RegimeDetection:
    return RegimeDetection(
        regime="NEUTRAL",
        sp500_vs_sma200=1.0,
        vix_level=20.0,
        reasoning=f"Fallback to NEUTRAL: {reason}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def calculate_consensus(
    verdicts: list[ResearchVerdict],
    regime: str,
    original_confidence: float,
) -> tuple[float, dict]:
    """Calculate weighted consensus confidence adjustment.

    Returns:
        (adjusted_confidence, metadata_dict)
    """
    if not verdicts:
        return original_confidence, {"reason": "no verdicts"}

    # VETO check — immediate reject
    veto_verdicts = [v for v in verdicts if v.direction == "VETO"]
    if veto_verdicts:
        return 0.0, {
            "reason": "VETO",
            "veto_by": [v.agent for v in veto_verdicts],
            "veto_reasoning": [v.reasoning for v in veto_verdicts],
        }

    weights = get_regime_weights(regime)

    # Weighted sum of confidence deltas
    weighted_delta = sum(
        weights.get(v.agent, 0.0) * v.confidence_delta for v in verdicts
    )

    # Special rules
    disagree_count = sum(1 for v in verdicts if v.direction == "DISAGREE")
    agree_count = sum(1 for v in verdicts if v.direction == "AGREE")

    bonus = 0.0
    if disagree_count >= 3:
        bonus -= 0.15
    if agree_count == len(verdicts):
        bonus += 0.15

    adjusted = original_confidence + weighted_delta + bonus
    adjusted = max(0.0, min(1.0, adjusted))

    metadata = {
        "original": original_confidence,
        "weighted_delta": round(weighted_delta, 4),
        "bonus": bonus,
        "adjusted": round(adjusted, 4),
        "regime": regime,
        "agree_count": agree_count,
        "disagree_count": disagree_count,
        "dropped": adjusted < 0.4,
    }

    return round(adjusted, 4), metadata
