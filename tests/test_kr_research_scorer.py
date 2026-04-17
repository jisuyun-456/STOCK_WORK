"""Tests for kr_research.scorer — 4 tests."""
from unittest.mock import patch, MagicMock
import pandas as pd


def _make_universe(n: int = 5) -> list[dict]:
    return [
        {"ticker": f"{str(i).zfill(6)}", "name": f"Stock{i}", "market": "KOSPI", "mcap_krw": 1_000_000_000_000}
        for i in range(1, n + 1)
    ]


def test_score_universe_returns_scored_stocks():
    """score_universe must return ScoredStock list with composite scores computed."""
    from kr_research import scorer

    universe = _make_universe(3)
    snapshot = {"date": "20260417"}

    # Mock pykrx calls inside scorer
    with patch.object(scorer, "_fetch_momentum", return_value=0.05), \
         patch.object(scorer, "_fetch_value", return_value=0.6), \
         patch.object(scorer, "_fetch_flow", return_value=100_000), \
         patch.object(scorer, "_fetch_shorting_pct", return_value=2.0):

        results = scorer.score_universe(universe, snapshot)

    assert len(results) == 3
    for r in results:
        assert hasattr(r, "ticker")
        assert hasattr(r, "composite")
        assert isinstance(r.composite, float)


def test_select_top_n_returns_n_tickers():
    """select_top_n must return exactly N tickers from a list of 200+ ScoredStocks."""
    from kr_research.scorer import ScoredStock, select_top_n
    import random

    # Build 200 scored stocks with random composites
    scored = [
        ScoredStock(
            ticker=f"{str(i).zfill(6)}",
            name=f"Stock{i}",
            market="KOSPI",
            composite=random.uniform(-1, 1),
        )
        for i in range(1, 201)
    ]

    top = select_top_n(scored, n=100)
    assert len(top) == 100
    # All items should be ticker strings
    assert all(isinstance(t, str) for t in top)


def test_individual_failure_doesnt_fail_universe():
    """If one stock fails scoring, others should still be returned."""
    from kr_research import scorer

    universe = _make_universe(5)
    snapshot = {"date": "20260417"}

    call_count = [0]

    def mock_momentum(ticker, snapshot):
        call_count[0] += 1
        if ticker == "000002":  # second stock fails
            raise ValueError("pykrx timeout")
        return 0.03

    with patch.object(scorer, "_fetch_momentum", side_effect=mock_momentum), \
         patch.object(scorer, "_fetch_value", return_value=0.5), \
         patch.object(scorer, "_fetch_flow", return_value=50_000), \
         patch.object(scorer, "_fetch_shorting_pct", return_value=1.5):

        results = scorer.score_universe(universe, snapshot)

    # Must return all 5 stocks (failing one gets 0.0 scores, not excluded)
    assert len(results) == 5
    # The failing stock should have composite=0.0 (or near zero due to other scores)
    failing = next(r for r in results if r.ticker == "000002")
    assert failing.momentum_score == 0.0


def test_composite_is_weighted_sum():
    """Composite must equal 0.3*momentum + 0.2*value + 0.3*flow + 0.2*shorting."""
    from kr_research import scorer

    universe = [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "mcap_krw": 500_000_000_000}]
    snapshot = {"date": "20260417"}

    with patch.object(scorer, "_fetch_momentum", return_value=0.1), \
         patch.object(scorer, "_fetch_value", return_value=0.8), \
         patch.object(scorer, "_fetch_flow", return_value=200_000), \
         patch.object(scorer, "_fetch_shorting_pct", return_value=3.0):

        results = scorer.score_universe(universe, snapshot)

    assert len(results) == 1
    stock = results[0]

    # The scorer normalizes flow and shorting_pct before weighting.
    # We verify the formula structure: composite uses the 4 sub-scores
    assert stock.momentum_score == 0.1
    assert stock.value_score == 0.8

    # Composite must be deterministic given fixed sub-scores
    expected_raw_composite = 0.3 * stock.momentum_score + 0.2 * stock.value_score + \
                             0.3 * stock.flow_score + 0.2 * stock.shorting_score
    assert abs(stock.composite - expected_raw_composite) < 1e-9, (
        f"composite={stock.composite} != formula={expected_raw_composite}"
    )
