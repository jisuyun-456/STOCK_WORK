"""Tests for kr_research.models — 3 tests."""
from datetime import datetime


def test_krverdict_dataclass_fields():
    """KRVerdict must have all required fields with correct types/defaults."""
    from kr_research.models import KRVerdict

    v = KRVerdict(
        ticker="005930",
        verdict="BUY",
        confidence=0.8,
        agent="claude",
        rationale="strong momentum",
    )

    assert v.ticker == "005930"
    assert v.verdict == "BUY"
    assert v.confidence == 0.8
    assert v.agent == "claude"
    assert v.rationale == "strong momentum"
    # Default fields
    assert isinstance(v.timestamp, datetime)
    assert v.veto is False
    assert v.veto_reason == ""


def test_krregime_dataclass_fields():
    """KRRegime must have all required fields with correct types/defaults."""
    from kr_research.models import KRRegime

    r = KRRegime(
        regime="BULL",
        confidence=0.9,
        factors={"kospi_trend": 1.05, "vkospi": 15.0},
    )

    assert r.regime == "BULL"
    assert r.confidence == 0.9
    assert isinstance(r.factors, dict)
    assert r.source == "kr_research"  # default


def test_kranalysisresult_fields():
    """KRAnalysisResult must have all required fields."""
    from kr_research.models import KRVerdict, KRRegime, KRAnalysisResult
    from datetime import datetime

    verdict = KRVerdict(
        ticker="005930",
        verdict="BUY",
        confidence=0.75,
        agent="equity",
        rationale="value play",
    )
    regime = KRRegime(
        regime="NEUTRAL",
        confidence=0.6,
        factors={"vkospi": 20.0},
    )
    consensus = KRVerdict(
        ticker="005930",
        verdict="BUY",
        confidence=0.75,
        agent="consensus",
        rationale="aggregated",
    )

    result = KRAnalysisResult(
        ticker="005930",
        verdicts=[verdict],
        consensus=consensus,
        regime=regime,
    )

    assert result.ticker == "005930"
    assert len(result.verdicts) == 1
    assert result.consensus.agent == "consensus"
    assert result.regime.regime == "NEUTRAL"
    assert isinstance(result.analyzed_at, datetime)
