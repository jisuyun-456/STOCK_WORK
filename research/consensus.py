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


def detect_regime_enhanced(
    news_sentiment_score: float = 0.0,
    polymarket_score: float | None = None,
) -> RegimeDetection:
    """확장된 Regime Detection: VIX + SPY/SMA200 + 뉴스감성 + Polymarket.

    가중치 (Polymarket 데이터 유무에 따라 동적):
        Polymarket 없음: VIX(40%) + SPY/SMA200(30%) + 뉴스(30%)
        Polymarket 있음: VIX(35%) + SPY/SMA200(25%) + 뉴스(30%) + Polymarket(10%)

    Args:
        news_sentiment_score: -1.0 ~ +1.0 (뉴스 감성 점수, 기본값 0.0=중립)
        polymarket_score: -1.0 ~ +1.0 (예측시장 매크로 점수, 기본값 0.0)
    """
    try:
        import yfinance as yf

        spy = yf.Ticker("SPY")
        hist = spy.history(period="1y")
        if hist.empty:
            return _neutral_fallback("No SPY data available (enhanced)")

        current_price = hist["Close"].iloc[-1]
        sma200 = hist["Close"].rolling(200).mean().iloc[-1]

        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="5d")
        vix_level = vix_hist["Close"].iloc[-1] if not vix_hist.empty else 20.0

    except Exception as e:
        return _neutral_fallback(f"Data fetch error (enhanced): {e}")

    ratio = current_price / sma200 if sma200 > 0 else 1.0

    # ── VIX 점수 (0~1) ──────────────────────────────────────────────────────
    if vix_level < 20:
        vix_score = 1.0
    elif vix_level <= 25:
        vix_score = 0.6
    elif vix_level <= 30:
        vix_score = 0.3
    else:
        vix_score = 0.0

    # ── SPY/SMA200 점수 (0~1) ────────────────────────────────────────────────
    if ratio > 1.05:
        spy_score = 1.0
    elif ratio >= 1.0:
        spy_score = 0.7
    elif ratio >= 0.95:
        spy_score = 0.3
    else:
        spy_score = 0.0

    # ── 뉴스 감성 점수 정규화 (0~1) ──────────────────────────────────────────
    news_sentiment_score = max(-1.0, min(1.0, news_sentiment_score))  # clamp
    news_score = (news_sentiment_score + 1.0) / 2.0

    # ── Polymarket 점수 정규화 (0~1) ─────────────────────────────────────────
    _pm = max(-1.0, min(1.0, polymarket_score)) if polymarket_score is not None else 0.0
    poly_score = (_pm + 1.0) / 2.0

    # ── 가중 합산 (Polymarket 유무에 따라 동적) ──────────────────────────────
    if polymarket_score is not None:
        # Polymarket 10% 배분: VIX 35% + SPY 25% + News 30% + Poly 10%
        composite = vix_score * 0.35 + spy_score * 0.25 + news_score * 0.30 + poly_score * 0.10
        poly_msg = f"polymarket={_pm:+.2f} → poly_score={poly_score:.2f}×0.10 | "
    else:
        # 기존 가중치 유지: VIX 40% + SPY 30% + News 30%
        composite = vix_score * 0.4 + spy_score * 0.3 + news_score * 0.3
        poly_msg = ""

    print(
        f"[detect_regime_enhanced] "
        f"VIX={vix_level:.1f} → vix_score={vix_score:.2f} | "
        f"SPY/SMA200={ratio:.4f} → spy_score={spy_score:.2f} | "
        f"news_sentiment={news_sentiment_score:.2f} → news_score={news_score:.2f} | "
        f"{poly_msg}"
        f"composite={composite:.4f}"
    )

    if composite > 0.7:
        regime = "BULL"
    elif composite > 0.4:
        regime = "NEUTRAL"
    elif composite > 0.2:
        regime = "BEAR"
    else:
        regime = "CRISIS"

    poly_reason = f", polymarket={_pm:+.2f}(score={poly_score:.2f}×0.10)" if polymarket_score is not None else ""
    weights = "VIX×0.35+SPY×0.25+news×0.30+poly×0.10" if polymarket_score is not None else "VIX×0.40+SPY×0.30+news×0.30"
    reasoning = (
        f"Enhanced ({weights}): VIX={vix_level:.1f}(score={vix_score:.2f}), "
        f"SPY/SMA200={ratio:.4f}(score={spy_score:.2f}), "
        f"news_sentiment={news_sentiment_score:.2f}(score={news_score:.2f})"
        f"{poly_reason} → composite={composite:.4f} → {regime}"
    )

    return RegimeDetection(
        regime=regime,
        sp500_vs_sma200=round(ratio, 4),
        vix_level=round(vix_level, 2),
        reasoning=reasoning,
        timestamp=datetime.now(timezone.utc).isoformat(),
        polymarket_score=round(_pm, 3),
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
