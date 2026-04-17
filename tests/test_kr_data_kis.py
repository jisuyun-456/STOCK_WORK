"""Tests for kr_data.kis_client — KIS (한국투자증권) API client.

All tests run without real API calls. KisClient is instantiated with
app_key=None, app_secret=None to simulate unconfigured (mock/degraded) mode.
"""
import logging
import pytest

from kr_data.kis_client import KisClient


# ---------------------------------------------------------------------------
# 1. Degraded mode when no keys are provided
# ---------------------------------------------------------------------------

def test_kis_client_degraded_mode_when_no_keys(caplog):
    """KisClient with no keys → _is_configured() False, get_quote returns None with warning."""
    with caplog.at_level(logging.WARNING, logger="kr_data.kis"):
        client = KisClient(app_key=None, app_secret=None)

    assert not client._is_configured()

    with caplog.at_level(logging.WARNING, logger="kr_data.kis"):
        result = client.get_quote("005930")

    assert result is None
    assert any("KIS" in msg or "not configured" in msg.lower() for msg in caplog.messages)


# ---------------------------------------------------------------------------
# 2. place_order paper mode returns simulated fill
# ---------------------------------------------------------------------------

def test_kis_place_order_paper_returns_simulated():
    """mode='paper' → place_order returns dict with status='simulated'."""
    client = KisClient(app_key=None, app_secret=None, mode="paper")
    result = client.place_order(ticker="005930", qty=10, price=75000, side="BUY")

    assert isinstance(result, dict)
    assert result["status"] == "simulated"
    assert result["ticker"] == "005930"
    assert result["qty"] == 10
    assert result["price"] == 75000
    assert result["side"] == "BUY"
    assert "order_id" in result


# ---------------------------------------------------------------------------
# 3. place_order live mode raises NotImplementedError
# ---------------------------------------------------------------------------

def test_kis_place_order_live_raises():
    """mode='live' → place_order raises NotImplementedError."""
    client = KisClient(app_key=None, app_secret=None, mode="live")
    with pytest.raises(NotImplementedError):
        client.place_order(ticker="005930", qty=5, price=75000, side="SELL")


# ---------------------------------------------------------------------------
# 4. get_positions returns empty list when not configured
# ---------------------------------------------------------------------------

def test_kis_get_positions_returns_empty_when_not_configured():
    """No keys → get_positions returns []."""
    client = KisClient(app_key=None, app_secret=None)
    assert not client._is_configured()
    result = client.get_positions()
    assert result == []


# ---------------------------------------------------------------------------
# 5. get_news returns empty list when not configured
# ---------------------------------------------------------------------------

def test_kis_get_news_returns_empty_when_not_configured():
    """No keys → get_news returns []."""
    client = KisClient(app_key=None, app_secret=None)
    assert not client._is_configured()
    result = client.get_news("005930")
    assert result == []
