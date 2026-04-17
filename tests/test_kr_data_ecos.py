"""Tests for kr_data.ecos_client — all requests.get calls are mocked.

TDD: tests written before implementation.
HIGH issue #3: Real BOK base rate from ECOS API (not hardcoded 3.00%).
"""
from unittest.mock import patch, MagicMock
import pytest
import json


# ---------------------------------------------------------------------------
# Fixture: always cache miss — patch at module level after import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Force all cache reads to return None (cache miss) and swallow writes."""
    import kr_data.ecos_client as ec
    monkeypatch.setattr(ec, "_cache", MagicMock(
        get=lambda k, t: None,
        get_df=lambda k, t: None,
        set=lambda k, v: None,
        set_df=lambda k, df: None,
    ))


# ---------------------------------------------------------------------------
# Test 1 — HIGH #3: requests.get raises → fetch_base_rate returns None (not 3.00%)
# ---------------------------------------------------------------------------

@patch("tenacity.nap.time.sleep")
def test_bok_rate_returns_none_if_api_fails(mock_sleep):
    """HIGH #3: When requests.get raises, fetch_base_rate must return None
    (not hardcoded 3.00%) — confirms we rely on real API data."""
    with patch.dict("os.environ", {"ECOS_API_KEY": "test-key"}), \
         patch("requests.get", side_effect=Exception("network error")):
        from kr_data.ecos_client import fetch_base_rate
        result = fetch_base_rate()

    assert result is None, "Must return None on API failure, not a hardcoded fallback"


# ---------------------------------------------------------------------------
# Test 2 — ECOS_API_KEY not in env → fetch_base_rate returns None
# ---------------------------------------------------------------------------

@patch("tenacity.nap.time.sleep")
def test_bok_rate_returns_none_if_no_api_key(mock_sleep):
    """When ECOS_API_KEY is not set, fetch_base_rate must return None."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "ECOS_API_KEY"}
    with patch.dict("os.environ", env, clear=True), \
         patch("requests.get") as mock_get:
        from kr_data.ecos_client import fetch_base_rate
        result = fetch_base_rate()

    assert result is None
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — valid ECOS response → DataFrame with "rate" column returned
# ---------------------------------------------------------------------------

def test_fetch_base_rate_returns_dataframe():
    """mock requests.get with valid ECOS response → DataFrame with 'rate' column."""
    import pandas as pd

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "StatisticSearch": {
            "row": [
                {"TIME": "202401", "DATA_VALUE": "3.50"},
                {"TIME": "202402", "DATA_VALUE": "3.50"},
                {"TIME": "202403", "DATA_VALUE": "3.25"},
            ]
        }
    }

    with patch.dict("os.environ", {"ECOS_API_KEY": "test-key"}), \
         patch("requests.get", return_value=mock_response):
        from kr_data.ecos_client import fetch_base_rate
        result = fetch_base_rate(start="202401", end="202403")

    assert result is not None
    assert isinstance(result, pd.DataFrame)
    assert "rate" in result.columns
    assert "date" in result.columns
    assert len(result) == 3
    assert result["rate"].iloc[-1] == pytest.approx(3.25)
