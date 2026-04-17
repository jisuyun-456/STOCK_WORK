"""Tests for kr_data.unipass_client — all requests.get calls are mocked.

TDD: tests written before implementation.
HIGH issue #4: Real semiconductor export YoY from UNIPASS (not null).
"""
from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Fixture: always cache miss — patch at module level after import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Force all cache reads to return None (cache miss) and swallow writes."""
    import kr_data.unipass_client as uc
    monkeypatch.setattr(uc, "_cache", MagicMock(
        get=lambda k, t: None,
        set=lambda k, v: None,
    ))


# ---------------------------------------------------------------------------
# Test 1 — HIGH #4: mock requests.get → valid response → returns dict with "yoy_pct"
# ---------------------------------------------------------------------------

def test_semi_export_yoy_not_null_when_api_live():
    """HIGH #4: When UNIPASS API returns valid data, fetch_semiconductor_export_yoy
    must return a dict with 'yoy_pct' key (not None)."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "response": {
            "data": [{"expAmt": "5000000000"}]
        }
    }

    with patch.dict("os.environ", {"UNIPASS_API_KEY": "test-key"}), \
         patch("requests.get", return_value=mock_response):
        from kr_data.unipass_client import fetch_semiconductor_export_yoy
        result = fetch_semiconductor_export_yoy()

    assert result is not None, "Must not return None when API succeeds (HIGH #4)"
    assert "yoy_pct" in result
    assert "latest_month" in result
    assert result["source"] == "unipass"
    assert isinstance(result["yoy_pct"], float)


# ---------------------------------------------------------------------------
# Test 2 — UNIPASS_API_KEY not in env → fetch_semiconductor_export_yoy returns None
# ---------------------------------------------------------------------------

@patch("tenacity.nap.time.sleep")
def test_semi_export_yoy_returns_none_if_no_key(mock_sleep):
    """When UNIPASS_API_KEY is not set, fetch_semiconductor_export_yoy returns None."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "UNIPASS_API_KEY"}
    with patch.dict("os.environ", env, clear=True), \
         patch("requests.get") as mock_get:
        from kr_data.unipass_client import fetch_semiconductor_export_yoy
        result = fetch_semiconductor_export_yoy()

    assert result is None
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3 — requests.get raises → fetch_semiconductor_export_yoy returns None
# ---------------------------------------------------------------------------

@patch("tenacity.nap.time.sleep")
def test_semi_export_yoy_returns_none_on_api_error(mock_sleep):
    """When requests.get raises an exception, must return None gracefully."""
    with patch.dict("os.environ", {"UNIPASS_API_KEY": "test-key"}), \
         patch("requests.get", side_effect=Exception("connection refused")):
        from kr_data.unipass_client import fetch_semiconductor_export_yoy
        result = fetch_semiconductor_export_yoy()

    assert result is None
