"""Unit tests for research.kr_manual_override."""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import research.kr_manual_override as kmo


@pytest.fixture(autouse=True)
def tmp_override_path(tmp_path, monkeypatch):
    """Redirect KR_OVERRIDE_PATH to a temp file for each test."""
    fake_path = tmp_path / "kr_verdicts.json"
    monkeypatch.setattr(kmo, "KR_OVERRIDE_PATH", fake_path)
    return fake_path


SAMPLE_VERDICTS = [
    {"agent": "kr_equity_research", "direction": "AGREE", "confidence_delta": 0.10,
     "conviction": "STRONG", "reasoning": "테스트", "key_metrics": {}},
    {"agent": "kr_technical_strategist", "direction": "AGREE", "confidence_delta": 0.07,
     "conviction": "MODERATE", "reasoning": "테스트", "key_metrics": {}},
    {"agent": "kr_macro_economist", "direction": "AGREE", "confidence_delta": 0.08,
     "conviction": "STRONG", "reasoning": "테스트", "key_metrics": {}},
    {"agent": "kr_sector_analyst", "direction": "AGREE", "confidence_delta": 0.05,
     "conviction": "MODERATE", "reasoning": "테스트", "key_metrics": {}},
    {"agent": "kr_risk_controller", "direction": "AGREE", "confidence_delta": 0.05,
     "conviction": "STRONG", "reasoning": "테스트", "key_metrics": {}},
]


def test_save_and_load_returns_entry():
    kmo.save_kr_verdicts(
        ticker="005930",
        verdicts=SAMPLE_VERDICTS,
        consensus="BUY",
        final_confidence=0.72,
        regime="BULL",
    )
    entry = kmo.load_kr_verdicts("005930")
    assert entry is not None
    assert entry["ticker"] == "005930"
    assert entry["consensus"] == "BUY"
    assert abs(entry["final_confidence"] - 0.72) < 0.001
    assert entry["regime"] == "BULL"
    assert len(entry["verdicts"]) == 5


def test_ticker_normalized_to_uppercase():
    kmo.save_kr_verdicts("005930", SAMPLE_VERDICTS, "BUY", 0.7)
    assert kmo.load_kr_verdicts("005930") is not None


def test_expired_entry_returns_none(tmp_override_path):
    now = datetime.now(timezone.utc)
    data = {
        "005930": {
            "saved_at": (now - timedelta(hours=25)).isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
            "ticker": "005930",
            "regime": "BULL",
            "verdicts": SAMPLE_VERDICTS,
            "consensus": "BUY",
            "final_confidence": 0.7,
            "veto_reason": None,
            "source": "kr_5agent_claude_code",
        }
    }
    tmp_override_path.write_text(json.dumps(data), encoding="utf-8")
    assert kmo.load_kr_verdicts("005930") is None


def test_missing_ticker_returns_none():
    assert kmo.load_kr_verdicts("999999") is None


def test_veto_entry_stored_correctly():
    kmo.save_kr_verdicts(
        ticker="000000",
        verdicts=[{"agent": "kr_risk_controller", "direction": "VETO",
                   "confidence_delta": -0.3, "conviction": "STRONG",
                   "reasoning": "자본잠식 67%", "key_metrics": {}}],
        consensus="VETO",
        final_confidence=0.0,
        veto_reason="자본잠식 67%",
        regime="BEAR",
    )
    entry = kmo.load_kr_verdicts("000000")
    assert entry["consensus"] == "VETO"
    assert entry["veto_reason"] == "자본잠식 67%"
    assert entry["final_confidence"] == 0.0


def test_list_active_returns_non_expired_only(tmp_override_path):
    now = datetime.now(timezone.utc)
    data = {
        "005930": {
            "saved_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=23)).isoformat(),
            "ticker": "005930",
            "regime": "BULL",
            "verdicts": SAMPLE_VERDICTS,
            "consensus": "BUY",
            "final_confidence": 0.7,
            "veto_reason": None,
            "source": "kr_5agent_claude_code",
        },
        "012450": {
            "saved_at": (now - timedelta(hours=25)).isoformat(),
            "expires_at": (now - timedelta(hours=1)).isoformat(),
            "ticker": "012450",
            "regime": "NEUTRAL",
            "verdicts": [],
            "consensus": "HOLD",
            "final_confidence": 0.5,
            "veto_reason": None,
            "source": "kr_5agent_claude_code",
        },
    }
    tmp_override_path.write_text(json.dumps(data), encoding="utf-8")
    active = kmo.list_active()
    tickers = [x["ticker"] for x in active]
    assert "005930" in tickers
    assert "012450" not in tickers


def test_invalidate_removes_entry():
    kmo.save_kr_verdicts("005930", SAMPLE_VERDICTS, "BUY", 0.7)
    result = kmo.invalidate("005930")
    assert result is True
    assert kmo.load_kr_verdicts("005930") is None


def test_invalidate_missing_ticker_returns_false():
    assert kmo.invalidate("999999") is False


def test_clear_expired_removes_stale(tmp_override_path):
    now = datetime.now(timezone.utc)
    data = {
        "005930": {
            "saved_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=10)).isoformat(),
            "ticker": "005930",
            "regime": "BULL",
            "verdicts": [],
            "consensus": "BUY",
            "final_confidence": 0.7,
            "veto_reason": None,
            "source": "kr_5agent_claude_code",
        },
        "STALE": {
            "saved_at": (now - timedelta(hours=30)).isoformat(),
            "expires_at": (now - timedelta(hours=6)).isoformat(),
            "ticker": "STALE",
            "regime": "BEAR",
            "verdicts": [],
            "consensus": "SELL",
            "final_confidence": 0.3,
            "veto_reason": None,
            "source": "kr_5agent_claude_code",
        },
    }
    tmp_override_path.write_text(json.dumps(data), encoding="utf-8")
    removed = kmo.clear_expired()
    assert removed == 1
    assert kmo.load_kr_verdicts("005930") is not None
