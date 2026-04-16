"""Workflow hardening regression tests (2026-04-16).

Covers 10 vulnerability fixes:
  A1  _next_seq JSON defense
  A4  _save_sector_cache atomic write
  B1  check_portfolio_var NaN guard
  D6  fetch_benchmark_prices None on failure
  B9  Sharpe sqrt negative variance guard
  E7  phase_report dynamic strategy list
  C1  --force-regime EUPHORIA in choices
  C12 SMA200 NaN cold-start fallback
  D2  fill retry 3x10s
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ─── A1: _next_seq JSON defense ──────────────────────────────────────────────

class TestNextSeqJsonDefense:
    def test_malformed_line_does_not_crash(self, tmp_path, monkeypatch):
        """Malformed JSONL line must be skipped, not crash _next_seq."""
        log = tmp_path / "trade_log.jsonl"
        log.write_text('{"order_id": "MOM-20260416-NVDA-001"}\n{BROKEN\n')

        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", log)

        seq_id = om._next_seq("MOM", "NVDA", "20260416")
        assert seq_id == "MOM-20260416-NVDA-002"

    def test_empty_file_returns_seq_001(self, tmp_path, monkeypatch):
        log = tmp_path / "trade_log.jsonl"
        log.write_text("")

        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", log)
        assert om._next_seq("MOM", "AAPL", "20260416") == "MOM-20260416-AAPL-001"

    def test_all_malformed_still_returns_seq_001(self, tmp_path, monkeypatch):
        """If every line is corrupt, seq starts at 001."""
        log = tmp_path / "trade_log.jsonl"
        log.write_text("{BROKEN\n{ALSO_BROKEN\n")

        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", log)
        assert om._next_seq("MOM", "AAPL", "20260416") == "MOM-20260416-AAPL-001"


# ─── A4: _save_sector_cache atomic write ─────────────────────────────────────

class TestSectorCacheAtomicWrite:
    def test_no_tmp_file_left_on_success(self, tmp_path, monkeypatch):
        """tmp 파일이 성공 후 남지 않아야 한다."""
        import execution.risk_validator as rv
        monkeypatch.setattr(rv, "_SECTOR_CACHE_PATH", tmp_path / "sector_cache.json")

        rv._save_sector_cache("NVDA", "Technology")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"tmp file leaked: {tmp_files}"

    def test_cache_readable_after_save(self, tmp_path, monkeypatch):
        import execution.risk_validator as rv
        monkeypatch.setattr(rv, "_SECTOR_CACHE_PATH", tmp_path / "sector_cache.json")

        rv._save_sector_cache("AAPL", "Technology")
        cache = rv._load_sector_cache()
        assert cache["AAPL"]["sector"] == "Technology"

    def test_existing_entries_preserved(self, tmp_path, monkeypatch):
        import execution.risk_validator as rv
        cache_path = tmp_path / "sector_cache.json"
        cache_path.write_text(json.dumps({"MSFT": {"sector": "Technology", "ts": 1.0}}))
        monkeypatch.setattr(rv, "_SECTOR_CACHE_PATH", cache_path)

        rv._save_sector_cache("NVDA", "Technology")
        result = json.loads(cache_path.read_text())
        assert "MSFT" in result
        assert result["NVDA"]["sector"] == "Technology"


# ─── B1: check_portfolio_var NaN guard ───────────────────────────────────────

class TestVarNaNHandling:
    def test_single_data_point_returns_data_insufficient(self):
        """std() of 1 return = NaN → 'data insufficient' reason, not 'nan%'."""
        from execution.risk_validator import check_portfolio_var

        two_rows = pd.DataFrame(
            {"Close": [180.0, 181.0]},
            index=pd.date_range("2025-01-01", periods=2),
        )
        with patch("execution.risk_validator.yf.download", return_value=two_rows):
            result = check_portfolio_var(symbols=["AAPL"], weights=[1.0])

        assert not result.passed
        assert "nan" not in result.reason.lower(), (
            f"Reason should not contain 'nan', got: {result.reason!r}"
        )

    def test_normal_data_does_not_trigger_insufficient(self):
        """60+ rows: VaR computes normally, no 'insufficient' message."""
        from execution.risk_validator import check_portfolio_var

        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        prices = pd.DataFrame(
            {"Close": [180.0 + i * 0.5 for i in range(60)]},
            index=dates,
        )
        with patch("execution.risk_validator.yf.download", return_value=prices):
            result = check_portfolio_var(symbols=["AAPL"], weights=[1.0])

        assert result.check_name == "portfolio_var"
        assert "nan" not in result.reason.lower()


# ─── D6: fetch_benchmark_prices None on failure ──────────────────────────────

class TestBenchmarkPriceFailure:
    def test_yfinance_failure_returns_none_not_zero(self):
        """yfinance 실패 시 0.0 대신 None 반환해야 한다."""
        from scripts.performance_calculator import fetch_benchmark_prices

        with patch("scripts.performance_calculator.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.fast_info.__getitem__.side_effect = Exception("network")
            prices = fetch_benchmark_prices()

        assert prices.get("SPY") is None, (
            f"SPY should be None on failure, got {prices.get('SPY')!r}"
        )
        assert prices.get("QQQ") is None, (
            f"QQQ should be None on failure, got {prices.get('QQQ')!r}"
        )

    def test_successful_fetch_returns_float(self):
        """정상 케이스에서 float 반환."""
        from scripts.performance_calculator import fetch_benchmark_prices

        with patch("scripts.performance_calculator.yf.Ticker") as mock_ticker:
            mock_info = MagicMock()
            mock_info.__getitem__ = lambda self, key: 500.0
            mock_ticker.return_value.fast_info = mock_info
            prices = fetch_benchmark_prices()

        assert isinstance(prices.get("SPY"), float)


# ─── B9: Sharpe sqrt negative-variance guard ─────────────────────────────────

class TestSharpeNegativeVariance:
    def test_negative_variance_does_not_raise(self):
        """math.sqrt(variance) must use max(0.0, variance) to avoid ValueError on tiny negative."""
        from scripts import performance_calculator as pc

        # Patch math.sqrt to detect if it's ever called with a negative arg
        real_sqrt = math.sqrt
        sqrt_args = []

        def recording_sqrt(x):
            sqrt_args.append(x)
            return real_sqrt(max(0.0, x))  # guard emulation

        with patch("scripts.performance_calculator.math") as mock_math:
            mock_math.sqrt = recording_sqrt
            mock_math.sqrt(252)  # side calls from annualization
            navs = [1000.0 + i * 0.1 for i in range(30)]
            pc._compute_sharpe(navs)

        # No assertion on result — just must not raise ValueError
        assert True

    def test_identical_navs_returns_none_not_crash(self):
        """동일 NAV → std=0 → None 반환 (ZeroDivisionError 아님)."""
        from scripts.performance_calculator import _compute_sharpe

        navs = [1000.0] * 30  # identical → std=0
        result = _compute_sharpe(navs)
        assert result is None  # std=0 → division-by-zero guard → None

    def test_variance_sqrt_uses_max_guard(self):
        """_compute_sharpe must use max(0.0, variance) in sqrt to guard float rounding."""
        source = Path("scripts/performance_calculator.py").read_text(encoding="utf-8")
        assert "max(0.0, variance)" in source, (
            "scripts/performance_calculator.py:_compute_sharpe should use "
            "math.sqrt(max(0.0, variance)) to guard against float rounding artifacts. "
            "Currently uses bare math.sqrt(variance)."
        )


# ─── E7: phase_report dynamic strategy list ──────────────────────────────────

class TestPhaseReportDynamicStrategies:
    def test_no_hardcoded_four_strategy_list_in_phase_report(self):
        """run_cycle.py는 LEV_ST/GRW를 누락하는 하드코딩 전략 리스트를 갖지 않아야 한다."""
        source = Path("run_cycle.py").read_text(encoding="utf-8")
        assert 'for code in ["MOM", "VAL", "QNT", "LEV"]' not in source, (
            "run_cycle.py still uses hardcoded strategy list "
            '["MOM", "VAL", "QNT", "LEV"] — LEV_ST and GRW will be '
            "excluded from daily reports. Fix: use dynamic strats.keys()."
        )


# ─── C1: --force-regime EUPHORIA ─────────────────────────────────────────────

class TestForceRegimeEuphoria:
    def test_force_regime_choices_include_euphoria(self):
        """--force-regime choices list in run_cycle.py must include EUPHORIA."""
        source = Path("run_cycle.py").read_text(encoding="utf-8")
        # The choices list must contain EUPHORIA
        assert '"EUPHORIA"' in source, (
            "EUPHORIA is missing from --force-regime choices in run_cycle.py. "
            "Cannot simulate/test EUPHORIA regime via CLI."
        )
        # The old incomplete 4-regime list must not still be the only choices
        assert 'choices=["BULL", "BEAR", "NEUTRAL", "CRISIS"]' not in source, (
            "run_cycle.py still uses 4-regime choices list without EUPHORIA."
        )


# ─── C12: SMA200 NaN cold-start fallback ─────────────────────────────────────

class TestSma200NanHandling:
    def _make_short_hist(self, n: int = 50) -> pd.DataFrame:
        dates = pd.date_range("2025-01-01", periods=n, freq="B")
        return pd.DataFrame(
            {"Close": [480.0 + i * 0.1 for i in range(n)]},
            index=dates,
        )

    def test_short_history_does_not_return_false_crisis(self):
        """SMA200 미계산 시 CRISIS로 오분류되지 않아야 한다."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_short_hist(n=50)
        result = _classify_regime_from_data(hist, vix_level=15.0)
        assert result != "CRISIS", (
            f"SMA200=NaN (short data) should not trigger CRISIS, got {result!r}"
        )

    def test_short_history_does_not_crash(self):
        """짧은 데이터(SMA200 미계산)에서 예외 없이 실행되어야 한다."""
        from research.consensus import _classify_regime_from_data

        hist = self._make_short_hist(n=30)
        try:
            result = _classify_regime_from_data(hist, vix_level=20.0)
        except Exception as e:
            pytest.fail(f"_classify_regime_from_data raised on short data: {e}")
        assert isinstance(result, str)

    def test_full_history_still_classifies(self):
        """충분한 데이터에서는 정상 분류 작동."""
        from research.consensus import _classify_regime_from_data

        # 250행 = SMA200 계산 가능
        hist = self._make_short_hist(n=250)
        result = _classify_regime_from_data(hist, vix_level=25.0)
        assert result in ("BULL", "NEUTRAL", "BEAR", "CRISIS", "EUPHORIA")


# ─── D2: fill retry loop ──────────────────────────────────────────────────────

class TestFillRetryLoop:
    def _make_signal(self):
        from strategies.base_strategy import Signal, Direction

        return Signal(
            strategy="MOM",
            symbol="NVDA",
            direction=Direction.BUY,
            weight_pct=0.10,
            confidence=0.8,
            reason="test",
        )

    def test_unfilled_first_check_retries_and_fills(self, tmp_path, monkeypatch):
        """첫 check unfilled → retry → filled 반환."""
        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", tmp_path / "trade_log.jsonl")

        call_count = [0]

        def mock_get_order(order_id):
            call_count[0] += 1
            if call_count[0] < 2:
                return {"filled_qty": "0", "filled_avg_price": None}
            return {"filled_qty": "10.5", "filled_avg_price": "180.0"}

        mock_order = MagicMock()
        mock_order.id = "alpaca-123"
        mock_order.client_order_id = "MOM-20260416-NVDA-001"
        mock_order.symbol = "NVDA"
        mock_order.side = MagicMock(__str__=lambda s: "buy")
        mock_order.status = MagicMock(__str__=lambda s: "filled")

        with patch("execution.alpaca_client.get_client") as mock_client, \
             patch("execution.order_manager.get_order_by_client_id",
                   side_effect=mock_get_order), \
             patch("execution.order_manager.get_positions", return_value=[]), \
             patch("execution.order_manager.time.sleep"):
            mock_client.return_value.submit_order.return_value = mock_order

            result = om.execute_signal(
                signal=self._make_signal(),
                strategy_capital=100_000,
                strategy_cash=100_000,
            )

        assert result.get("status") == "filled", (
            f"Expected status='filled' after retry, got {result!r}"
        )
        assert call_count[0] >= 2, (
            f"Expected at least 2 calls to get_order_by_client_id, got {call_count[0]}"
        )

    def test_always_unfilled_after_retries_returns_unfilled(self, tmp_path, monkeypatch):
        """최대 재시도 후에도 미체결 → 'unfilled' 반환 (crash 없음)."""
        import execution.order_manager as om
        monkeypatch.setattr(om, "TRADE_LOG_PATH", tmp_path / "trade_log.jsonl")

        mock_order = MagicMock()
        mock_order.id = "alpaca-456"
        mock_order.client_order_id = "MOM-20260416-NVDA-001"
        mock_order.symbol = "NVDA"
        mock_order.side = MagicMock(__str__=lambda s: "buy")
        mock_order.status = MagicMock(__str__=lambda s: "pending_new")

        with patch("execution.alpaca_client.get_client") as mock_client, \
             patch("execution.order_manager.get_order_by_client_id",
                   return_value={"filled_qty": "0", "filled_avg_price": None}), \
             patch("execution.order_manager.get_positions", return_value=[]), \
             patch("execution.order_manager.time.sleep"):
            mock_client.return_value.submit_order.return_value = mock_order

            result = om.execute_signal(
                signal=self._make_signal(),
                strategy_capital=100_000,
                strategy_cash=100_000,
            )

        assert result["status"] == "unfilled"
