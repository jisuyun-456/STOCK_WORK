"""Tests for kr_data.kind_client — all requests.get calls are mocked.

TDD: tests written before implementation.
KRX KIND public API: investment alerts, trading halts, unusual filings.
"""
from unittest.mock import patch, MagicMock
import pytest


# ---------------------------------------------------------------------------
# Fixture: always cache miss — patch at module level after import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Force all cache reads to return None (cache miss) and swallow writes."""
    import kr_data.kind_client as kc
    monkeypatch.setattr(kc, "_cache", MagicMock(
        get=lambda k, t: None,
        set=lambda k, v: None,
    ))


# ---------------------------------------------------------------------------
# Test 1 — mock valid response → list with "alert_type" key returned
# ---------------------------------------------------------------------------

def test_fetch_investment_alerts_returns_list():
    """mock requests.get with valid KIND response → list[dict] with 'alert_type' key."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "list": [
            {"isu_cd": "005930", "isu_nm": "삼성전자", "invst_wrn_tp_nm": "투자주의"},
            {"isu_cd": "000660", "isu_nm": "SK하이닉스", "invst_wrn_tp_nm": "투자경고"},
        ]
    }

    with patch("requests.get", return_value=mock_response):
        from kr_data.kind_client import fetch_investment_alerts
        result = fetch_investment_alerts("20260417")

    assert isinstance(result, list)
    assert len(result) == 2
    assert "alert_type" in result[0]
    assert result[0]["ticker"] == "005930"
    assert result[0]["alert_type"] == "투자주의"


# ---------------------------------------------------------------------------
# Test 2 — requests.get raises → fetch_trading_halts returns []
# ---------------------------------------------------------------------------

@patch("tenacity.nap.time.sleep")
def test_fetch_trading_halts_returns_empty_on_error(mock_sleep):
    """When requests.get raises, fetch_trading_halts must return [] (not crash)."""
    with patch("requests.get", side_effect=Exception("timeout")):
        from kr_data.kind_client import fetch_trading_halts
        result = fetch_trading_halts("20260417")

    assert result == []


# ---------------------------------------------------------------------------
# Test 3 — mock valid response → fetch_unusual_filings returns list
# ---------------------------------------------------------------------------

def test_fetch_unusual_filings_returns_list():
    """mock requests.get with valid KIND response → list[dict] returned."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "result": [
            {"isu_cd": "005930", "isu_nm": "삼성전자", "inqr_cn": "조회공시 요청"},
        ]
    }

    with patch("requests.get", return_value=mock_response):
        from kr_data.kind_client import fetch_unusual_filings
        result = fetch_unusual_filings()

    assert isinstance(result, list)
    assert len(result) == 1
    assert "corp_name" in result[0]
    assert result[0]["ticker"] == "005930"
