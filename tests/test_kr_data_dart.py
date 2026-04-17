"""Tests for kr_data.dart_client — all dart_fss calls are mocked.

TDD: tests written before implementation.
HIGH issue #5: DART corp_code mapping (6-digit KRX ticker → 8-digit corp_code)
"""
from unittest.mock import patch, MagicMock
import pytest
import logging


# ---------------------------------------------------------------------------
# Fixture: always cache miss — patch at module level after import
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """Force all cache reads to return None (cache miss) and swallow writes."""
    import kr_data.dart_client as dc
    monkeypatch.setattr(dc, "_cache", MagicMock(
        get=lambda k, t: None,
        set=lambda k, v: None,
    ))


# ---------------------------------------------------------------------------
# Test 1 — HIGH #5: 6-digit ticker → 8-digit corp_code
# ---------------------------------------------------------------------------

def test_corp_code_mapping_exists():
    """DartClient.corp_code_for('005930') returns '00126380' from mocked corp_list."""
    mock_corp = MagicMock()
    mock_corp.corp_code = "00126380"

    mock_corp_list = MagicMock()
    mock_corp_list.find_by_stock_code.return_value = mock_corp

    with patch("dart_fss.set_api_key"), \
         patch("dart_fss.get_corp_list", return_value=mock_corp_list):
        from kr_data.dart_client import DartClient
        client = DartClient(api_key="test-key")
        result = client.corp_code_for("005930")

    assert result == "00126380"
    mock_corp_list.find_by_stock_code.assert_called_once_with("005930")


# ---------------------------------------------------------------------------
# Test 2 — Unknown ticker returns None
# ---------------------------------------------------------------------------

def test_corp_code_returns_none_for_unknown_ticker():
    """find_by_stock_code returning None → corp_code_for returns None."""
    mock_corp_list = MagicMock()
    mock_corp_list.find_by_stock_code.return_value = None

    with patch("dart_fss.set_api_key"), \
         patch("dart_fss.get_corp_list", return_value=mock_corp_list):
        from kr_data.dart_client import DartClient
        client = DartClient(api_key="test-key")
        result = client.corp_code_for("999999")

    assert result is None


# ---------------------------------------------------------------------------
# Test 3 — fetch_filings returns list of dicts with rcp_no
# ---------------------------------------------------------------------------

def test_fetch_filings_returns_list():
    """fetch_filings wraps SearchResults.report_list into list[dict] with rcp_no."""
    mock_report = MagicMock()
    mock_report.rcp_no = "20260101000001"
    mock_report.corp_name = "삼성전자"
    mock_report.report_nm = "사업보고서"
    mock_report.rcept_dt = "20260101"
    mock_report.rm = ""

    mock_search_results = MagicMock()
    mock_search_results.report_list = [mock_report]

    with patch("dart_fss.set_api_key"), \
         patch("dart_fss.filings.search", return_value=mock_search_results):
        from kr_data.dart_client import DartClient
        client = DartClient(api_key="test-key")
        result = client.fetch_filings("00126380", "20260101", "20260417")

    assert isinstance(result, list)
    assert len(result) == 1
    assert "rcp_no" in result[0]
    assert result[0]["rcp_no"] == "20260101000001"


# ---------------------------------------------------------------------------
# Test 4 — fetch_financial_statement returns None on exception
# ---------------------------------------------------------------------------

def test_fetch_financial_statement_returns_none_on_failure():
    """When dart_fss.corp.Corp raises Exception, returns None (no crash)."""
    with patch("dart_fss.set_api_key"), \
         patch("dart_fss.corp.Corp", side_effect=Exception("network error")):
        from kr_data.dart_client import DartClient
        client = DartClient(api_key="test-key")
        result = client.fetch_financial_statement("00126380", 2025)

    assert result is None


# ---------------------------------------------------------------------------
# Test 5 — warns when DART_API_KEY is missing
# ---------------------------------------------------------------------------

def test_dart_client_warns_if_no_api_key(caplog):
    """DartClient(api_key=None) with no env var logs a WARNING on kr_data.dart."""
    with patch("dart_fss.set_api_key"), \
         patch.dict("os.environ", {}, clear=True):
        # Remove DART_API_KEY if present
        import os
        os.environ.pop("DART_API_KEY", None)

        with caplog.at_level(logging.WARNING, logger="kr_data.dart"):
            from kr_data.dart_client import DartClient
            DartClient(api_key=None)

    assert any("DART_API_KEY" in record.message for record in caplog.records)
