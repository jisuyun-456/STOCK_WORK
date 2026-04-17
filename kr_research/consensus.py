"""Regime-aware weighted aggregation of KRVerdict list → single consensus KRVerdict.

Rules:
  1. ANY veto=True → consensus = VETO (absolute)
  2. Regime-aware weight adjustments
  3. Weighted sum of verdict scores → BUY/HOLD/SELL threshold
  4. Confidence = weighted max confidence
"""
from __future__ import annotations

import logging

from kr_research.models import KRVerdict, KRRegime, KRVerdictType

_logger = logging.getLogger("kr_research.consensus")

_VERDICT_SCORE: dict[str, float] = {
    "BUY": 1.0,
    "HOLD": 0.0,
    "SELL": -1.0,
    "VETO": -2.0,
}

_BASE_WEIGHTS: dict[str, float] = {
    "equity": 0.30,
    "technical": 0.20,
    "macro": 0.20,
    "sector": 0.15,
    "commander": 0.15,
    "claude": 0.30,   # generic claude verdict
    "rules": 0.20,    # rules-mode weight
}

# Regime multipliers for specific agents
_REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "CRISIS": {
        "macro": 2.0,
        "commander": 2.0,
        "technical": 0.8,
    },
    "BEAR": {
        "macro": 1.5,
        "commander": 1.5,
    },
    "BULL": {
        "equity": 1.3,
        "sector": 1.2,
    },
    "NEUTRAL": {},
}


def _get_regime_weights(regime_type: str) -> dict[str, float]:
    """Return effective agent weights after regime adjustment."""
    multipliers = _REGIME_MULTIPLIERS.get(regime_type, {})
    weights: dict[str, float] = {}
    for agent, base_w in _BASE_WEIGHTS.items():
        mult = multipliers.get(agent, 1.0)
        weights[agent] = base_w * mult
    return weights


def aggregate(verdicts: list[KRVerdict], regime: KRRegime) -> KRVerdict:
    """
    Weighted consensus with regime adjustments.

    Args:
        verdicts: list of KRVerdict from various agents
        regime:   current KR market regime

    Returns:
        KRVerdict with agent="consensus"
    """
    if not verdicts:
        return KRVerdict(
            ticker="UNKNOWN",
            verdict="HOLD",
            confidence=0.0,
            agent="consensus",
            rationale="no verdicts provided",
        )

    # Rule 1: ANY veto wins
    veto_verdicts = [v for v in verdicts if v.veto]
    if veto_verdicts:
        veto_v = veto_verdicts[0]
        return KRVerdict(
            ticker=veto_v.ticker,
            verdict="VETO",
            confidence=1.0,
            agent="consensus",
            rationale=f"VETO by {veto_v.agent}: {veto_v.veto_reason or veto_v.rationale}",
            veto=True,
            veto_reason=veto_v.veto_reason or veto_v.rationale,
        )

    weights = _get_regime_weights(regime.regime)
    ticker = verdicts[0].ticker

    total_weight = 0.0
    weighted_score = 0.0
    weighted_confidence = 0.0

    for v in verdicts:
        agent_weight = weights.get(v.agent, 0.20)  # default weight for unknown agents
        score = _VERDICT_SCORE.get(v.verdict, 0.0)

        # Weight by both agent weight and verdict confidence
        effective_weight = agent_weight * v.confidence

        weighted_score += score * effective_weight
        weighted_confidence += v.confidence * agent_weight
        total_weight += effective_weight

    if total_weight == 0.0:
        final_score = 0.0
        confidence = 0.3
    else:
        final_score = weighted_score / total_weight
        confidence = min(1.0, weighted_confidence / sum(weights.get(v.agent, 0.20) for v in verdicts))

    # Score → verdict
    if final_score >= 0.4:
        final_verdict: KRVerdictType = "BUY"
    elif final_score <= -0.4:
        final_verdict = "SELL"
    else:
        final_verdict = "HOLD"

    agent_summary = ", ".join(f"{v.agent}:{v.verdict}" for v in verdicts)
    consensus_note = f"consensus={final_score:.2f} [{agent_summary}]"

    # Use original rationale if single claude verdict; else append consensus note
    if len(verdicts) == 1 and verdicts[0].agent == "claude":
        rationale = verdicts[0].rationale
    else:
        claude_v = next((v for v in verdicts if v.agent == "claude"), None)
        rationale = (claude_v.rationale + " | " + consensus_note) if claude_v else consensus_note

    # Propagate all fields from claude verdict (highest priority source)
    claude_v = next((v for v in verdicts if v.agent == "claude"), None)
    src = claude_v or next(
        (v for v in verdicts if v.entry_price_low is not None or v.target_price is not None),
        None
    )

    return KRVerdict(
        ticker=ticker,
        verdict=final_verdict,
        confidence=round(confidence, 3),
        agent="consensus",
        rationale=rationale,
        # 가격 전략
        entry_price_low=src.entry_price_low if src else None,
        entry_price_high=src.entry_price_high if src else None,
        target_price=src.target_price if src else None,
        target_price_2=src.target_price_2 if src else None,
        stop_loss=src.stop_loss if src else None,
        entry_price=src.entry_price if src else None,
        # 타이밍
        buy_trigger=src.buy_trigger if src else "",
        sell_trigger=src.sell_trigger if src else "",
        current_status=src.current_status if src else "",
        # 시나리오
        bull_case=src.bull_case if src else "",
        base_case=src.base_case if src else "",
        bear_case=src.bear_case if src else "",
        # 메타
        company_name=src.company_name if src else "",
        sector=src.sector if src else "",
        risk_factors=src.risk_factors if src else [],
        investment_thesis=src.investment_thesis if src else "",
        buy_factors=src.buy_factors if src else [],
        sell_factors=src.sell_factors if src else [],
    )
