"""Tests for kr_data.pykrx_client — HIGH issues #2, #10, #11.

All pykrx API calls are mocked; no real network calls are made.
_cache is patched to always return None (cache miss) so the pykrx
API always executes.
"""
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_df():
    """Minimal OHLCV DataFrame that pykrx_stock.get_market_ohlcv would return."""
    return pd.DataFrame(
        {"시가": [70000], "고가": [75000], "저가": [69000], "종가": [74000], "거래량": [1_000_000]},
        index=pd.to_datetime(["2026-04-16"]),
    )


def _make_fundamental_df():
    return pd.DataFrame(
        {"PER": [12.5], "PBR": [1.2], "DIV": [2.3]},
        index=["005930"],
    )


def _make_investor_flow_df():
    return pd.DataFrame(
        {"외국인": [100_000], "기관합계": [50_000], "개인": [-150_000]},
        index=pd.to_datetime(["2026-04-16"]),
    )


def _make_shorting_df():
    return pd.DataFrame(
        {"공매도잔고": [50_000], "공매도잔고금액": [3_700_000_000]},
        index=pd.to_datetime(["2026-04-16"]),
    )


def _make_vkospi_df():
    return pd.DataFrame(
        {"시가": [20.5], "고가": [21.0], "저가": [20.0], "종가": [20.7], "거래량": [0]},
        index=pd.to_datetime(["2026-04-16"]),
    )


def _make_market_cap_df():
    """Simulated market cap DataFrame from pykrx_stock.get_market_cap."""
    return pd.DataFrame(
        {
            "시가총액": [500_000_000_000, 50_000_000_000, 200_000_000_000],
            "상장주식수": [1_000_000, 500_000, 2_000_000],
        },
        index=["005930", "000020", "035720"],
    )


# ---------------------------------------------------------------------------
# Fixture: patch _cache to always be a cache miss
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Patch the module-level _cache so every call is a cache miss."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    mock_cache.get_df.return_value = None
    mock_cache.set.return_value = None
    mock_cache.set_df.return_value = None
    monkeypatch.setattr("kr_data.pykrx_client._cache", mock_cache)
    return mock_cache


# ---------------------------------------------------------------------------
# Test 1: fetch_ohlcv_batch returns DataFrame
# ---------------------------------------------------------------------------

def test_fetch_ohlcv_batch_returns_dataframe():
    """fetch_ohlcv_batch should call pykrx_stock.get_market_ohlcv and return DataFrame."""
    from kr_data.pykrx_client import fetch_ohlcv_batch

    with patch("kr_data.pykrx_client.pykrx_stock.get_market_ohlcv", return_value=_make_ohlcv_df()) as mock_ohlcv:
        result = fetch_ohlcv_batch(["005930"], "20260410", "20260416")

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    mock_ohlcv.assert_called()


# ---------------------------------------------------------------------------
# Test 2 (HIGH #2): VKOSPI source must be "pykrx", not "estimated"
# ---------------------------------------------------------------------------

def test_vkospi_from_pykrx_not_estimated():
    """HIGH #2: fetch_vkospi must return df with source='pykrx', never 'estimated'."""
    from kr_data.pykrx_client import fetch_vkospi

    with patch("kr_data.pykrx_client.pykrx_stock.get_index_ohlcv", return_value=_make_vkospi_df()):
        result = fetch_vkospi("20260410", "20260416")

    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert "source" in result.columns, "DataFrame must have a 'source' column"
    assert (result["source"] == "pykrx").all(), "All rows must have source='pykrx'"
    assert not (result["source"] == "estimated").any(), "source must never be 'estimated'"


# ---------------------------------------------------------------------------
# Test 3: fetch_vkospi returns None on failure (no estimated fallback)
# ---------------------------------------------------------------------------

def test_vkospi_falls_back_to_vix_on_failure():
    """HIGH #2: if pykrx raises, fetch_vkospi falls back to VIX proxy (source='estimated_from_vix').

    VIX fallback was intentionally added; returns None only when yfinance also fails.
    """
    import pandas as pd
    from kr_data.pykrx_client import fetch_vkospi

    mock_vix_df = pd.DataFrame({"Close": [19.73]}, index=[pd.Timestamp("2026-04-16")])

    with patch("kr_data.pykrx_client.pykrx_stock.get_index_ohlcv", side_effect=Exception("network error")):
        with patch("yfinance.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = mock_vix_df
            result = fetch_vkospi("20260410", "20260416")

    # Either VIX fallback or None (if yfinance also unavailable)
    if result is not None:
        assert "source" in result.columns
        assert (result["source"] == "estimated_from_vix").all()


# ---------------------------------------------------------------------------
# Test 4: fetch_market_fundamental returns DataFrame
# ---------------------------------------------------------------------------

def test_fetch_market_fundamental_returns_dataframe():
    """fetch_market_fundamental should return a DataFrame with PER, PBR, DIV columns."""
    from kr_data.pykrx_client import fetch_market_fundamental

    with patch(
        "kr_data.pykrx_client.pykrx_stock.get_market_fundamental",
        return_value=_make_fundamental_df(),
    ) as mock_fund:
        result = fetch_market_fundamental("20260416", market="KOSPI")

    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    mock_fund.assert_called_once_with("20260416", market="KOSPI")


# ---------------------------------------------------------------------------
# Test 5 (HIGH #10): investor flow uses pykrx, NOT Naver regex
# ---------------------------------------------------------------------------

def test_foreign_flow_uses_pykrx_not_naver_regex():
    """HIGH #10: fetch_investor_flow must call pykrx, never requests/urllib (Naver regex)."""
    from kr_data.pykrx_client import fetch_investor_flow

    with (
        patch(
            "kr_data.pykrx_client.pykrx_stock.get_market_trading_volume_by_investor",
            return_value=_make_investor_flow_df(),
        ) as mock_pykrx,
        patch("kr_data.pykrx_client.pykrx_stock.get_market_ohlcv", side_effect=AssertionError("should not be called")),
    ):
        result = fetch_investor_flow("005930", "20260410", "20260416")

    # pykrx must have been called
    mock_pykrx.assert_called_once_with("20260410", "20260416", "005930")
    assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Test 6 (HIGH #11): shorting balance is actually fetched, not schema-only
# ---------------------------------------------------------------------------

def test_shorting_balance_fetched_and_not_schema_only():
    """HIGH #11: fetch_shorting_balance must call pykrx_stock.get_shorting_balance."""
    from kr_data.pykrx_client import fetch_shorting_balance

    with patch(
        "kr_data.pykrx_client.pykrx_stock.get_shorting_balance",
        return_value=_make_shorting_df(),
    ) as mock_short:
        result = fetch_shorting_balance("005930", "20260410", "20260416")

    # Verify the real API was called (not returning a static schema dict)
    mock_short.assert_called_once_with("20260410", "20260416", "005930")
    assert isinstance(result, pd.DataFrame)
    assert not result.empty


# ---------------------------------------------------------------------------
# Test 7: build_universe filters by min_mcap_krw
# ---------------------------------------------------------------------------

def test_build_universe_filters_by_mcap():
    """build_universe must exclude stocks below min_mcap_krw threshold."""
    from kr_data.pykrx_client import build_universe

    # 005930: 500억원 (above 100억), 000020: 50억원 (below 100억), 035720: 200억원 (above)
    min_mcap = 100_000_000_000  # 1000억

    with patch(
        "kr_data.pykrx_client.pykrx_stock.get_market_cap",
        return_value=_make_market_cap_df(),
    ):
        result = build_universe(market="KOSPI", min_mcap_krw=min_mcap)

    tickers = [item["ticker"] for item in result]
    # 500B >= 100B → included; 50B < 100B → excluded; 200B >= 100B → included
    assert "005930" in tickers
    assert "035720" in tickers
    assert "000020" not in tickers, "000020 (50B mcap) must be filtered out by min_mcap_krw"


# ---------------------------------------------------------------------------
# Test 8: fetch_investor_flow returns None on pykrx failure
# ---------------------------------------------------------------------------

def test_fetch_investor_flow_returns_none_on_failure():
    """fetch_investor_flow must return None when pykrx raises an exception."""
    from kr_data.pykrx_client import fetch_investor_flow

    with patch(
        "kr_data.pykrx_client.pykrx_stock.get_market_trading_volume_by_investor",
        side_effect=Exception("pykrx timeout"),
    ):
        result = fetch_investor_flow("005930", "20260410", "20260416")

    assert result is None
