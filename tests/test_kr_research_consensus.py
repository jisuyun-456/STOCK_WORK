"""Tests for kr_research.consensus — 3 tests."""


def _make_verdict(ticker: str, verdict_type: str, agent: str = "equity", confidence: float = 0.7, veto: bool = False):
    from kr_research.models import KRVerdict
    return KRVerdict(
        ticker=ticker,
        verdict=verdict_type,
        confidence=confidence,
        agent=agent,
        rationale="test",
        veto=veto,
        veto_reason="test veto" if veto else "",
    )


def _make_regime(regime_type: str = "NEUTRAL"):
    from kr_research.models import KRRegime
    return KRRegime(
        regime=regime_type,
        confidence=0.7,
        factors={"vkospi": 20.0},
    )


def test_any_veto_wins():
    """If any verdict has veto=True, consensus must be VETO regardless of other verdicts."""
    from kr_research.consensus import aggregate

    verdicts = [
        _make_verdict("005930", "BUY", agent="equity", confidence=0.9),
        _make_verdict("005930", "BUY", agent="technical", confidence=0.8),
        _make_verdict("005930", "VETO", agent="macro", confidence=0.95, veto=True),
        _make_verdict("005930", "BUY", agent="sector", confidence=0.85),
    ]
    regime = _make_regime("NEUTRAL")

    consensus = aggregate(verdicts, regime)
    assert consensus.verdict == "VETO", f"VETO should win, got {consensus.verdict}"
    assert consensus.veto is True


def test_majority_buy_produces_buy():
    """Multiple BUY verdicts outweighing SELL should produce BUY consensus."""
    from kr_research.consensus import aggregate

    verdicts = [
        _make_verdict("005930", "BUY", agent="equity", confidence=0.8),
        _make_verdict("005930", "BUY", agent="technical", confidence=0.75),
        _make_verdict("005930", "BUY", agent="sector", confidence=0.7),
        _make_verdict("005930", "SELL", agent="macro", confidence=0.5),
    ]
    regime = _make_regime("BULL")

    consensus = aggregate(verdicts, regime)
    assert consensus.verdict == "BUY", f"Majority BUY should produce BUY, got {consensus.verdict}"
    assert consensus.agent == "consensus"
    assert 0.0 <= consensus.confidence <= 1.0


def test_crisis_regime_boosts_macro_weight():
    """In CRISIS regime, macro agent should have higher effective weight than normal."""
    from kr_research.consensus import _get_regime_weights

    crisis_weights = _get_regime_weights("CRISIS")
    neutral_weights = _get_regime_weights("NEUTRAL")

    macro_crisis = crisis_weights.get("macro", 0.0)
    macro_neutral = neutral_weights.get("macro", 0.0)

    assert macro_crisis > macro_neutral, (
        f"CRISIS should boost macro weight: crisis={macro_crisis} neutral={macro_neutral}"
    )

    commander_crisis = crisis_weights.get("commander", 0.0)
    commander_neutral = neutral_weights.get("commander", 0.0)
    assert commander_crisis >= commander_neutral
