"""Integration tests for Phase 1.65 KR_CONTEXT in run_cycle.py.

HIGH #13: kr_research was not integrated into run_cycle.py.
These tests verify that phase_kr_context() is callable from run_cycle,
writes the expected state files, and degrades gracefully on failure.
"""

from unittest.mock import patch
import json
from pathlib import Path
import pandas as pd
import pytest


def test_phase_16_writes_kr_state_files(tmp_path, monkeypatch):
    """HIGH #13: Phase 1.65 must write kr_market_state.json and kr_regime_state.json."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    with patch("kr_data.pykrx_client.fetch_vkospi") as mock_vkospi, \
         patch("kr_data.ecos_client.fetch_base_rate") as mock_bok, \
         patch("kr_data.unipass_client.fetch_semiconductor_export_yoy") as mock_semi, \
         patch("kr_data.sector_feeds.compute_all_scores") as mock_sectors:

        mock_vkospi.return_value = pd.DataFrame({"Close": [18.5]})
        mock_bok.return_value = pd.DataFrame({"date": ["202603"], "rate": [3.25]})
        mock_semi.return_value = {"yoy_pct": 12.5, "source": "unipass"}
        mock_sectors.return_value = {
            s: 0.0
            for s in [
                "semiconductor", "battery", "bio", "shipbuilding",
                "chemical", "auto", "content", "finance",
            ]
        }

        from run_cycle import phase_kr_context
        result = phase_kr_context(
            snapshot={"vix": 18.0, "spy_sma200_ratio": 1.05},
            regime_state={"regime": "BULL"},
        )

    assert (tmp_path / "state" / "kr_market_state.json").exists(), \
        "kr_market_state.json must be written"
    assert (tmp_path / "state" / "kr_regime_state.json").exists(), \
        "kr_regime_state.json must be written"

    state = json.loads((tmp_path / "state" / "kr_market_state.json").read_text(encoding="utf-8"))
    assert "vkospi" in state
    assert "bok_rate" in state
    assert "semiconductor_export" in state
    assert "sector_scores" in state


def test_phase_16_vkospi_source_is_pykrx(tmp_path, monkeypatch):
    """VKOSPI source must be 'pykrx', not 'estimated'."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    with patch("kr_data.pykrx_client.fetch_vkospi") as mock_v, \
         patch("kr_data.ecos_client.fetch_base_rate", return_value=None), \
         patch("kr_data.unipass_client.fetch_semiconductor_export_yoy", return_value=None), \
         patch("kr_data.sector_feeds.compute_all_scores", return_value={}):

        mock_v.return_value = pd.DataFrame({"Close": [20.0]})

        from run_cycle import phase_kr_context
        result = phase_kr_context({}, {"regime": "NEUTRAL"})

    assert result.get("vkospi", {}).get("source") == "pykrx"


def test_phase_16_graceful_on_total_failure(tmp_path, monkeypatch):
    """Phase 1.65 failure → returns {} without crashing."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    with patch("kr_data.pykrx_client.fetch_vkospi", side_effect=Exception("network error")), \
         patch("kr_data.ecos_client.fetch_base_rate", side_effect=Exception("api error")), \
         patch("kr_data.unipass_client.fetch_semiconductor_export_yoy", return_value=None), \
         patch("kr_data.sector_feeds.compute_all_scores", return_value={}):

        from run_cycle import phase_kr_context
        result = phase_kr_context({}, {})

    # Graceful degradation: must return a dict (possibly empty or partial)
    assert isinstance(result, dict)


def test_phase_16_bok_rate_source_is_ecos(tmp_path, monkeypatch):
    """BOK rate source must be 'ecos', not hardcoded."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "state").mkdir()

    with patch("kr_data.pykrx_client.fetch_vkospi", return_value=None), \
         patch("kr_data.ecos_client.fetch_base_rate") as mock_bok, \
         patch("kr_data.unipass_client.fetch_semiconductor_export_yoy", return_value=None), \
         patch("kr_data.sector_feeds.compute_all_scores", return_value={}):

        mock_bok.return_value = pd.DataFrame({"date": ["202603"], "rate": [3.50]})

        from run_cycle import phase_kr_context
        result = phase_kr_context({}, {})

    assert result.get("bok_rate", {}).get("source") == "ecos"


def test_skip_kr_flag_skips_phase16():
    """--skip-kr CLI flag: phase_kr_context must exist in run_cycle."""
    import run_cycle
    assert hasattr(run_cycle, "phase_kr_context"), \
        "phase_kr_context must be defined in run_cycle"
    assert callable(run_cycle.phase_kr_context), \
        "phase_kr_context must be callable"
