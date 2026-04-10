"""Research Overlay Engine — Phase 2.5 + Phase 3.5 logic.

Phase 2.5: Research Division 5-agent parallel analysis → confidence adjustment.
Phase 3.5: Appeal loop for Risk-FAIL signals → potential override.

In automated (Python) mode, this module simulates research verdicts using
rule-based heuristics. When agents invoke /run-cycle interactively,
the Trading Commander can replace these with actual agent analysis.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from strategies.base_strategy import Signal

from .agent_runner import get_research_mode, run_all_agents, run_all_agents_appeal
from .cache import get_cached, set_cache
from .consensus import calculate_consensus, detect_regime
from .models import RegimeDetection, ResearchRequest, ResearchVerdict

DISSENT_LOG_PATH = Path(__file__).parent.parent / "state" / "dissent_log.jsonl"

# Risk gates that CAN be overridden by appeal (4/5+ STRONG_OVERRIDE)
OVERRIDABLE_GATES = {"sector_concentration", "portfolio_var", "correlation"}
# Risk gates that can NEVER be overridden
HARD_GATES = {"position_limit", "cash_buffer"}


def run_research_overlay(
    signals: list[Signal],
    market_data: dict,
    portfolio_state: dict,
    research_mode: str = "full",
    no_cache: bool = False,
) -> tuple[list[Signal], RegimeDetection, dict[str, list[ResearchVerdict]]]:
    """Phase 2.5: Run Research Overlay on signals.

    Args:
        signals: Raw signals from Phase 2.
        market_data: Phase 1 market data dict.
        portfolio_state: portfolios.json content.
        research_mode: "full" | "selective" | "skip"
        no_cache: If True, bypass cache.

    Returns:
        (adjusted_signals, regime_detection, verdicts_by_symbol)
    """
    print("[Phase 2.5: RESEARCH] Running Research Overlay...")

    if research_mode == "skip":
        print("  Research skipped (--research-mode skip)")
        regime = RegimeDetection(
            regime="NEUTRAL", sp500_vs_sma200=1.0, vix_level=20.0,
            reasoning="Skipped", timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return signals, regime, {}

    # 1. Regime Detection
    prices = market_data.get("prices")
    regime = detect_regime(prices)
    print(f"  Regime: {regime.regime} ({regime.reasoning})")

    # 2. Filter signals if selective mode
    if research_mode == "selective":
        research_signals = [s for s in signals if 0.5 <= s.confidence <= 0.7]
        passthrough = [s for s in signals if s.confidence < 0.5 or s.confidence > 0.7]
        print(f"  Selective mode: {len(research_signals)} signals to research, {len(passthrough)} passthrough")
    else:
        research_signals = signals
        passthrough = []

    # 3. Run research on each signal
    adjusted = list(passthrough)
    all_verdicts: dict[str, list[ResearchVerdict]] = {}

    for signal in research_signals:
        # Check cache (key includes strategy+direction to avoid cross-strategy collision)
        sig_dir = signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction)
        if not no_cache:
            cached = get_cached(signal.symbol, regime.regime, signal.strategy, sig_dir)
            if cached is not None:
                print(f"  {signal.symbol}: cache hit ({len(cached)} verdicts)")
                verdicts = cached
            else:
                verdicts = _generate_verdicts(signal, market_data, portfolio_state, regime)
                set_cache(signal.symbol, regime.regime, verdicts, signal.strategy, sig_dir)
        else:
            verdicts = _generate_verdicts(signal, market_data, portfolio_state, regime)
            set_cache(signal.symbol, regime.regime, verdicts, signal.strategy, sig_dir)

        all_verdicts[signal.symbol] = verdicts

        # Calculate consensus
        adj_confidence, meta = calculate_consensus(verdicts, regime.regime, signal.confidence)

        # VETO or DROP
        if meta.get("reason") == "VETO":
            print(f"  {signal.symbol}: VETO by {meta['veto_by']} — REJECTED")
            _log_dissent(signal, verdicts, "VETO_REJECTED", adj_confidence, appeal=False)
            continue

        if meta.get("dropped"):
            print(f"  {signal.symbol}: confidence {adj_confidence:.2f} < 0.4 — DROPPED")
            _log_dissent(signal, verdicts, "DROPPED", adj_confidence, appeal=False)
            continue

        # Adjust signal confidence
        adj_signal = deepcopy(signal)
        adj_signal.confidence = adj_confidence
        print(f"  {signal.symbol}: {signal.confidence:.2f} → {adj_confidence:.2f} ({meta['regime']})")

        # Log dissent if any
        disagree_agents = [v for v in verdicts if v.direction == "DISAGREE"]
        if disagree_agents:
            _log_dissent(signal, verdicts, "APPROVED", adj_confidence, appeal=False)

        adjusted.append(adj_signal)

    print(f"  Research complete: {len(adjusted)} signals passed (from {len(signals)} raw)")
    return adjusted, regime, all_verdicts


def run_appeal(
    failed_signals: list[Signal],
    risk_results: list[dict],
    research_verdicts: dict[str, list[ResearchVerdict]],
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[Signal]:
    """Phase 3.5: Appeal loop for Risk-FAIL signals.

    Args:
        failed_signals: Signals that failed Phase 3 Risk validation.
        risk_results: List of dicts with 'symbol', 'failed_checks' keys.
        research_verdicts: Verdicts from Phase 2.5.
        market_data: Phase 1 market data.
        portfolio_state: portfolios.json content.
        regime: Current regime detection.

    Returns:
        List of signals that passed appeal (may be empty).
    """
    if not failed_signals:
        return []

    print("[Phase 3.5: APPEAL] Reviewing Risk-FAIL signals...")

    appealed = []
    for signal in failed_signals:
        # Find which checks failed
        fail_info = next(
            (r for r in risk_results if r.get("symbol") == signal.symbol), {}
        )
        failed_checks = set(fail_info.get("failed_checks", []))

        # If any HARD_GATE failed, appeal is impossible
        if failed_checks & HARD_GATES:
            hard_fails = failed_checks & HARD_GATES
            print(f"  {signal.symbol}: APPEAL DENIED — hard gate(s) failed: {hard_fails}")
            _log_dissent(signal, research_verdicts.get(signal.symbol, []),
                        "APPEAL_DENIED_HARD_GATE", signal.confidence, appeal=True)
            continue

        # Only overridable gates failed — submit to Research for appeal
        appeal_context = {
            "failed_checks": list(failed_checks),
            "risk_details": fail_info,
        }

        verdicts = _generate_appeal_verdicts(
            signal, market_data, portfolio_state, regime, appeal_context
        )

        # Count STRONG_OVERRIDE votes
        override_votes = sum(1 for v in verdicts if v.override_vote == "STRONG_OVERRIDE")
        total_voters = len(verdicts)

        if override_votes >= 4 and total_voters >= 5:
            print(f"  {signal.symbol}: APPEAL APPROVED ({override_votes}/{total_voters} STRONG_OVERRIDE)")
            _log_dissent(signal, verdicts, "APPEAL_APPROVED", signal.confidence, appeal=True)
            appealed.append(signal)
        else:
            reject_count = total_voters - override_votes
            print(f"  {signal.symbol}: APPEAL REJECTED ({override_votes}/{total_voters} override, need 4+)")
            _log_dissent(signal, verdicts, "APPEAL_REJECTED", signal.confidence, appeal=True)

    print(f"  Appeal complete: {len(appealed)} / {len(failed_signals)} overridden")
    return appealed


# ─── Verdict Generation ────────────────────────────────────────────────────

def _generate_verdicts(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[ResearchVerdict]:
    """Generate research verdicts — hybrid routing.

    Routes to LLM agents (Gemini/Claude) if RESEARCH_MODE is set,
    otherwise uses rule-based heuristics.
    """
    mode = get_research_mode()
    if mode in ("gemini", "claude"):
        real_verdicts = run_all_agents(signal, market_data, portfolio_state, regime, mode)
        if real_verdicts:
            return real_verdicts
        print(f"  [{signal.symbol}] LLM agents returned empty, falling back to rules")

    return _generate_verdicts_rules(signal, market_data, portfolio_state, regime)


def _generate_verdicts_rules(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[ResearchVerdict]:
    """Rule-based verdict generation (original logic, kept as fallback)."""
    now = datetime.now(timezone.utc).isoformat()
    verdicts = []

    # Equity Research: momentum signals get moderate agreement
    verdicts.append(ResearchVerdict(
        agent="equity_research",
        symbol=signal.symbol,
        direction="AGREE" if signal.confidence > 0.5 else "DISAGREE",
        confidence_delta=0.05 if signal.confidence > 0.6 else -0.05,
        conviction="MODERATE",
        reasoning=f"Momentum signal conf={signal.confidence:.2f} {'aligns' if signal.confidence > 0.5 else 'conflicts'} with valuation view",
        key_metrics={"signal_confidence": signal.confidence},
        timestamp=now,
    ))

    # Technical Strategist: agrees with strong momentum
    verdicts.append(ResearchVerdict(
        agent="technical_strategist",
        symbol=signal.symbol,
        direction="AGREE" if signal.confidence > 0.55 else "DISAGREE",
        confidence_delta=0.08 if signal.confidence > 0.65 else -0.03,
        conviction="STRONG" if signal.confidence > 0.7 else "MODERATE",
        reasoning=f"Technical trend {'confirms' if signal.confidence > 0.55 else 'does not confirm'} momentum",
        key_metrics={"momentum_aligned": signal.confidence > 0.55},
        timestamp=now,
    ))

    # Macro Economist: regime-dependent
    macro_agrees = (
        (regime.regime == "BULL" and signal.direction.value == "buy") or
        (regime.regime in ("BEAR", "CRISIS") and signal.direction.value == "sell")
    )
    verdicts.append(ResearchVerdict(
        agent="macro_economist",
        symbol=signal.symbol,
        direction="AGREE" if macro_agrees else "DISAGREE",
        confidence_delta=0.06 if macro_agrees else -0.08,
        conviction="STRONG" if macro_agrees else "WEAK",
        reasoning=f"Regime {regime.regime}: {'favorable' if macro_agrees else 'unfavorable'} for {signal.direction.value}",
        key_metrics={"regime": regime.regime, "vix": regime.vix_level},
        timestamp=now,
    ))

    # Portfolio Architect: checks diversification
    verdicts.append(ResearchVerdict(
        agent="portfolio_architect",
        symbol=signal.symbol,
        direction="AGREE",
        confidence_delta=0.02,
        conviction="MODERATE",
        reasoning=f"Portfolio allocation acceptable for {signal.symbol} at {signal.weight_pct:.0%} weight",
        key_metrics={"target_weight": signal.weight_pct},
        timestamp=now,
    ))

    # Risk Controller: conservative check
    risk_ok = signal.confidence > 0.6 and regime.regime not in ("CRISIS",)
    verdicts.append(ResearchVerdict(
        agent="risk_controller",
        symbol=signal.symbol,
        direction="AGREE" if risk_ok else ("VETO" if regime.regime == "CRISIS" and signal.direction.value == "buy" else "DISAGREE"),
        confidence_delta=0.0 if risk_ok else -0.10,
        conviction="MODERATE" if risk_ok else "STRONG",
        reasoning=f"Risk assessment: {'acceptable' if risk_ok else 'elevated risk'} (regime={regime.regime})",
        key_metrics={"regime_risk": regime.regime == "CRISIS"},
        timestamp=now,
    ))

    return verdicts


def _generate_appeal_verdicts(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    appeal_context: dict,
) -> list[ResearchVerdict]:
    """Generate appeal verdicts — hybrid routing."""
    mode = get_research_mode()
    if mode in ("gemini", "claude"):
        real_verdicts = run_all_agents_appeal(
            signal, market_data, portfolio_state, regime, appeal_context, mode
        )
        if real_verdicts:
            return real_verdicts

    return _generate_appeal_verdicts_rules(
        signal, market_data, portfolio_state, regime, appeal_context
    )


def _generate_appeal_verdicts_rules(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    appeal_context: dict,
) -> list[ResearchVerdict]:
    """Rule-based appeal verdicts (original logic, kept as fallback)."""
    now = datetime.now(timezone.utc).isoformat()
    failed_checks = appeal_context.get("failed_checks", [])
    verdicts = []

    # In appeal mode, agents are asked:
    # "The risk gate failed, but is the fundamental case strong enough to override?"
    # Default simulation: only override if confidence was very high
    is_strong_case = signal.confidence >= 0.7

    for agent_name in ["equity_research", "technical_strategist", "macro_economist",
                       "portfolio_architect", "risk_controller"]:
        # Risk controller is extra conservative in appeals
        if agent_name == "risk_controller":
            vote = "REJECT"
            reasoning = f"Risk Controller maintains caution on {', '.join(failed_checks)}"
        elif is_strong_case:
            vote = "STRONG_OVERRIDE"
            reasoning = f"{agent_name}: Strong fundamental case (conf={signal.confidence:.2f}) justifies risk override"
        else:
            vote = "REJECT"
            reasoning = f"{agent_name}: Insufficient conviction (conf={signal.confidence:.2f}) for risk override"

        verdicts.append(ResearchVerdict(
            agent=agent_name,
            symbol=signal.symbol,
            direction="AGREE" if vote == "STRONG_OVERRIDE" else "DISAGREE",
            confidence_delta=0.0,
            conviction="STRONG" if vote == "STRONG_OVERRIDE" else "WEAK",
            reasoning=reasoning,
            key_metrics={"failed_checks": failed_checks, "appeal": True},
            override_vote=vote,
            timestamp=now,
        ))

    return verdicts


# ─── Dissent Log ─────────────────────────────────────────────────────────

def _log_dissent(
    signal: Signal,
    verdicts: list[ResearchVerdict],
    outcome: str,
    adjusted_confidence: float,
    appeal: bool,
):
    """Append to dissent_log.jsonl (immutable ledger)."""
    agree = [v for v in verdicts if v.direction == "AGREE"]
    disagree = [v for v in verdicts if v.direction in ("DISAGREE", "VETO")]

    majority_direction = "AGREE" if len(agree) >= len(disagree) else "DISAGREE"

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": signal.symbol,
        "strategy": signal.strategy,
        "phase": "appeal" if appeal else "research",
        "majority_direction": majority_direction,
        "majority_count": max(len(agree), len(disagree)),
        "dissenters": [
            {"agent": v.agent, "direction": v.direction, "reason": v.reasoning}
            for v in (disagree if majority_direction == "AGREE" else agree)
        ],
        "final_outcome": outcome,
        "appeal": appeal,
        "original_confidence": signal.confidence,
        "adjusted_confidence": adjusted_confidence,
    }

    DISSENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISSENT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
