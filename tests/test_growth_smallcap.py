"""tests/test_growth_smallcap.py — GrowthSmallCapStrategy 유닛 테스트"""
from __future__ import annotations
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import date


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_prices(tickers: list[str], days: int = 130, base: float = 100.0) -> pd.DataFrame:
    import numpy as np
    idx = pd.bdate_range(end=date.today(), periods=days)
    rng = np.random.default_rng(42)
    data = {t: base * (1 + rng.normal(0.001, 0.02, days)).cumprod() for t in tickers}
    return pd.DataFrame(data, index=idx)


def _make_market_data(tickers: list[str]) -> dict:
    prices = _make_prices(tickers)
    fundamentals = {
        t: {
            "market_cap": 500_000_000,
            "revenue_growth": 0.25,
            "roe": 0.12,
            "free_cashflow": 10_000_000,
            "ok": True,
        }
        for t in tickers
    }
    return {"prices": prices, "fundamentals": fundamentals}


# ── fetch_growth_data ─────────────────────────────────────────────────────────

class TestFetchGrowthData:
    def test_returns_required_keys(self):
        from strategies.growth_smallcap import fetch_growth_data
        with patch("strategies.growth_smallcap.yf") as mock_yf:
            mock_yf.download.return_value = _make_prices(["IRTC", "INSP"])
            mock_ticker = MagicMock()
            mock_ticker.info = {
                "marketCap": 800_000_000,
                "revenueGrowth": 0.30,
                "returnOnEquity": 0.15,
                "freeCashflow": 5_000_000,
            }
            mock_yf.Ticker.return_value = mock_ticker
            result = fetch_growth_data(universe=["IRTC", "INSP"])
        assert "prices" in result
        assert "fundamentals" in result

    def test_empty_universe_returns_empty(self):
        from strategies.growth_smallcap import fetch_growth_data
        result = fetch_growth_data(universe=[])
        assert result["prices"].empty
        assert result["fundamentals"] == {}


# ── GrowthSmallCapStrategy.generate_signals ───────────────────────────────────

class TestGenerateSignals:
    def _make_strategy(self):
        from strategies.growth_smallcap import GrowthSmallCapStrategy
        return GrowthSmallCapStrategy()

    def test_returns_list(self):
        strat = self._make_strategy()
        tickers = ["IRTC", "INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA", "APPF", "JAMF", "HIMS"]
        signals = strat.generate_signals(_make_market_data(tickers))
        assert isinstance(signals, list)

    def test_empty_market_data_returns_empty(self):
        strat = self._make_strategy()
        signals = strat.generate_signals({"prices": pd.DataFrame(), "fundamentals": {}})
        assert signals == []

    def test_buy_signals_have_correct_strategy_name(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        tickers = ["IRTC", "INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA", "APPF", "JAMF", "HIMS"]
        signals = strat.generate_signals(_make_market_data(tickers))
        buy_signals = [s for s in signals if s.direction == Direction.BUY]
        assert all(s.strategy == "GRW" for s in buy_signals)

    def test_max_positions_respected(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        tickers = [f"TICK{i}" for i in range(30)]
        md = _make_market_data(tickers)
        signals = strat.generate_signals(md)
        buy_signals = [s for s in signals if s.direction == Direction.BUY]
        assert len(buy_signals) <= strat.max_positions

    def test_sell_signals_for_dropped_positions(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        current_positions = {"IRTC": {"market_value": 5000}}
        md = _make_market_data(["INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA", "APPF", "JAMF"])
        signals = strat.generate_signals(md, current_positions=current_positions)
        sell = [s for s in signals if s.direction == Direction.SELL and s.symbol == "IRTC"]
        assert len(sell) == 1

    def test_crisis_regime_generates_sell_all(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        md = _make_market_data(["IRTC", "INSP"])
        current_positions = {"IRTC": {"market_value": 5000}, "INSP": {"market_value": 3000}}
        signals = strat.generate_signals(md, current_positions=current_positions, regime="CRISIS")
        sell = [s for s in signals if s.direction == Direction.SELL]
        assert len(sell) == 2
        assert all(s.weight_pct == 0.0 for s in sell)

    def test_confidence_in_range(self):
        strat = self._make_strategy()
        tickers = ["IRTC", "INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA", "APPF", "JAMF", "HIMS"]
        signals = strat.generate_signals(_make_market_data(tickers))
        for s in signals:
            assert 0.0 <= s.confidence <= 1.0

    def test_weight_pct_for_buy_equals_position_pct(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        tickers = ["IRTC", "INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA", "APPF", "JAMF", "HIMS"]
        signals = strat.generate_signals(_make_market_data(tickers))
        for s in signals:
            if s.direction == Direction.BUY:
                assert s.weight_pct == pytest.approx(strat.position_pct)

    def test_no_buy_in_bear_regime_with_negative_momentum(self):
        from strategies.base_strategy import Direction
        strat = self._make_strategy()
        tickers = ["IRTC", "INSP", "TMDX"]
        idx = pd.bdate_range(end=date.today(), periods=130)
        prices = pd.DataFrame(
            {t: [100 * (0.998 ** i) for i in range(130)] for t in tickers},
            index=idx,
        )
        fundamentals = {
            t: {"market_cap": 500_000_000, "revenue_growth": 0.25, "roe": 0.12,
                "free_cashflow": 1_000_000, "ok": True}
            for t in tickers
        }
        signals = strat.generate_signals(
            {"prices": prices, "fundamentals": fundamentals}, regime="BEAR"
        )
        buy_signals = [s for s in signals if s.direction == Direction.BUY]
        assert len(buy_signals) == 0
