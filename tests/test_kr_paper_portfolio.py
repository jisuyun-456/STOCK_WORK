"""Tests for kr_paper.portfolio — JSON state management + T+2 pending settlement."""

import json
import os
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_path(monkeypatch, tmp_path):
    """Redirect KR_PORTFOLIOS_PATH to a temp file for isolation."""
    import kr_paper.portfolio as portfolio_mod

    fake_path = str(tmp_path / "kr_portfolios.json")
    monkeypatch.setattr(portfolio_mod, "KR_PORTFOLIOS_PATH", fake_path)
    return fake_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_creates_default_if_missing(monkeypatch, tmp_path):
    """load() must create default state when file does not exist."""
    import kr_paper.portfolio as portfolio_mod

    fake_path = _patch_path(monkeypatch, tmp_path)

    # Ensure file does NOT exist
    if os.path.exists(fake_path):
        os.remove(fake_path)

    state = portfolio_mod.load()

    assert "KR_PAPER" in state
    kr = state["KR_PAPER"]
    assert kr["cash_krw"] == 10_000_000
    assert kr["positions"] == {}
    assert kr["nav_history"] == []
    assert kr["pending_settlement"] == []


def test_save_is_atomic(monkeypatch, tmp_path):
    """save() writes atomically; resulting file must contain the expected state."""
    import kr_paper.portfolio as portfolio_mod

    fake_path = _patch_path(monkeypatch, tmp_path)

    state = {
        "KR_PAPER": {
            "cash_krw": 5_000_000,
            "positions": {"005930": {"qty": 10, "avg_price_krw": 70_000}},
            "nav_history": [],
            "pending_settlement": [],
        }
    }
    portfolio_mod.save(state)

    assert os.path.exists(fake_path)
    with open(fake_path, "r", encoding="utf-8") as f:
        on_disk = json.load(f)

    assert on_disk["KR_PAPER"]["cash_krw"] == 5_000_000
    assert "005930" in on_disk["KR_PAPER"]["positions"]


def test_add_pending_settlement(monkeypatch, tmp_path):
    """add_pending_settlement() appends record and persists it."""
    import kr_paper.portfolio as portfolio_mod

    _patch_path(monkeypatch, tmp_path)

    # Start from a clean default
    state = portfolio_mod.load()
    portfolio_mod.save(state)

    record = {
        "ticker": "005930",
        "side": "BUY",
        "qty": 5,
        "net_cost_krw": 350_000,
        "settlement_date": "2026-04-19",
    }
    portfolio_mod.add_pending_settlement(record)

    reloaded = portfolio_mod.load()
    pending = reloaded["KR_PAPER"]["pending_settlement"]
    assert len(pending) == 1
    assert pending[0]["ticker"] == "005930"
    assert pending[0]["settlement_date"] == "2026-04-19"


def test_settle_due_returns_correct_records(monkeypatch, tmp_path):
    """settle_due() settles only past records and updates cash correctly."""
    import kr_paper.portfolio as portfolio_mod

    _patch_path(monkeypatch, tmp_path)

    # Set up initial state with 10_000_000 cash
    state = portfolio_mod.load()
    portfolio_mod.save(state)

    past_record = {
        "ticker": "005930",
        "side": "BUY",
        "qty": 10,
        "net_cost_krw": 700_000,
        "settlement_date": "2026-04-01",  # past
    }
    future_record = {
        "ticker": "000660",
        "side": "SELL",
        "qty": 5,
        "net_proceeds_krw": 300_000,
        "settlement_date": "2099-01-01",  # future
    }

    portfolio_mod.add_pending_settlement(past_record)
    portfolio_mod.add_pending_settlement(future_record)

    settled = portfolio_mod.settle_due("2026-04-17")

    # Only the past record should be settled
    assert len(settled) == 1
    assert settled[0]["ticker"] == "005930"

    # Cash should be reduced by the BUY's net_cost_krw
    reloaded = portfolio_mod.load()
    assert reloaded["KR_PAPER"]["cash_krw"] == 10_000_000 - 700_000

    # Future record must still be pending
    remaining = reloaded["KR_PAPER"]["pending_settlement"]
    assert len(remaining) == 1
    assert remaining[0]["ticker"] == "000660"


def test_compute_nav(monkeypatch, tmp_path):
    """compute_nav() returns cash + market value of all positions."""
    import kr_paper.portfolio as portfolio_mod

    _patch_path(monkeypatch, tmp_path)

    state = portfolio_mod.load()
    # Set cash and positions directly
    state["KR_PAPER"]["cash_krw"] = 8_000_000
    state["KR_PAPER"]["positions"] = {
        "005930": {"qty": 10, "avg_price_krw": 70_000},
        "000660": {"qty": 5, "avg_price_krw": 100_000},
    }
    portfolio_mod.save(state)

    # prices dict provides current market prices
    prices = {
        "005930": 75_000,   # 10 * 75_000 = 750_000
        "000660": 110_000,  # 5  * 110_000 = 550_000
    }
    nav = portfolio_mod.compute_nav(prices)

    expected = 8_000_000 + 10 * 75_000 + 5 * 110_000
    assert nav == expected
