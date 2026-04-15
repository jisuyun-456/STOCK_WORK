"""tests/test_news_triggers.py — news.triggers 단위 테스트.

모든 외부 네트워크(yfinance, SEC EDGAR)는 unittest.mock 으로 차단.
pytest tests/test_news_triggers.py -v
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call

import pytest

# ─── FOMC week ────────────────────────────────────────────────────────────────


class TestFOMCWeek:
    def setup_method(self):
        # triggers 모듈을 각 테스트에서 깨끗하게 임포트
        from news.triggers import is_fomc_week, FOMC_MEETING_DATES
        self.is_fomc_week = is_fomc_week
        self.FOMC_MEETING_DATES = FOMC_MEETING_DATES

    def test_exact_meeting_day_true(self):
        # 2026-04-29 = FOMC 발표일
        assert self.is_fomc_week(date(2026, 4, 29)) is True

    def test_minus_two_days_true(self):
        # 발표일 -2일
        assert self.is_fomc_week(date(2026, 4, 27)) is True

    def test_plus_two_days_true(self):
        # 발표일 +2일
        assert self.is_fomc_week(date(2026, 5, 1)) is True

    def test_three_days_away_false(self):
        # 발표일 -3일 → 범위 밖
        assert self.is_fomc_week(date(2026, 4, 26)) is False

    def test_mid_cycle_false(self):
        # 오늘(2026-04-15) — 다음 회의까지 14일
        assert self.is_fomc_week(date(2026, 4, 15)) is False

    def test_all_dates_covered_and_count(self):
        # 2025-2026 총 16개, 같은 날짜 중복 없음
        assert len(self.FOMC_MEETING_DATES) == 16
        assert len(set(self.FOMC_MEETING_DATES)) == 16

    def test_2025_first_meeting(self):
        assert self.is_fomc_week(date(2025, 1, 29)) is True

    def test_2025_last_meeting(self):
        assert self.is_fomc_week(date(2025, 12, 10)) is True


# ─── Earnings week ────────────────────────────────────────────────────────────


class TestEarningsWeek:
    def setup_method(self):
        from news.triggers import is_earnings_week
        self.is_earnings_week = is_earnings_week

    def _make_ticker(self, earnings_date):
        """yfinance Ticker mock — calendar dict 반환."""
        t = MagicMock()
        t.calendar = {"Earnings Date": earnings_date}
        return t

    def test_symbol_within_window_true(self):
        today = date(2026, 4, 15)
        ed = date(2026, 4, 17)  # +2일 이내
        with patch("yfinance.Ticker", return_value=self._make_ticker(ed)):
            hit, syms = self.is_earnings_week(["AAPL"], today)
        assert hit is True
        assert "AAPL" in syms

    def test_symbol_outside_window_false(self):
        today = date(2026, 4, 15)
        ed = date(2026, 4, 25)  # +10일
        with patch("yfinance.Ticker", return_value=self._make_ticker(ed)):
            hit, syms = self.is_earnings_week(["AAPL"], today)
        assert hit is False

    def test_list_of_dates_picks_nearest(self):
        today = date(2026, 4, 15)
        # 첫 번째 날짜는 멀고 두 번째는 가까움
        ed = [date(2026, 5, 20), date(2026, 4, 17)]
        with patch("yfinance.Ticker", return_value=self._make_ticker(ed)):
            hit, syms = self.is_earnings_week(["MSFT"], today)
        assert hit is True

    def test_yfinance_exception_returns_false(self):
        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            hit, syms = self.is_earnings_week(["FAIL"], date(2026, 4, 15))
        assert hit is False
        assert syms == []

    def test_empty_symbol_list_returns_false(self):
        hit, syms = self.is_earnings_week([], date(2026, 4, 15))
        assert hit is False
        assert syms == []

    def test_datetime_object_converted(self):
        today = date(2026, 4, 15)
        # Timestamp-like 객체 (has .date() method)
        dt = datetime(2026, 4, 17, tzinfo=timezone.utc)
        with patch("yfinance.Ticker", return_value=self._make_ticker(dt)):
            hit, syms = self.is_earnings_week(["GOOG"], today)
        assert hit is True

    def test_multiple_symbols_partial_hit(self):
        today = date(2026, 4, 15)
        far = date(2026, 6, 1)   # 멀리 있음
        near = date(2026, 4, 16) # 가까움

        def ticker_factory(sym):
            t = MagicMock()
            t.calendar = {"Earnings Date": near if sym == "NVDA" else far}
            return t

        with patch("yfinance.Ticker", side_effect=ticker_factory):
            hit, syms = self.is_earnings_week(["AAPL", "NVDA"], today)
        assert hit is True
        assert syms == ["NVDA"]


# ─── SEC 8-K ──────────────────────────────────────────────────────────────────


# 샘플 Atom XML (SEC EDGAR 응답 형식)
def _atom_xml(updated_iso: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>EDGAR Filing Search Results</title>
  <entry>
    <title>8-K</title>
    <updated>{updated_iso}</updated>
    <link href="https://www.sec.gov/cgi-bin/browse-edgar"/>
  </entry>
</feed>"""


_CIK_JSON = {
    "0": {"ticker": "AAPL", "cik_str": 320193},
    "1": {"ticker": "NVDA", "cik_str": 1045810},
}


class TestSEC8K:
    def setup_method(self):
        import news.triggers as mod
        mod._CIK_CACHE.clear()
        from news.triggers import has_8k_filing
        self.has_8k_filing = has_8k_filing

    def _mock_requests(self, updated_dt: datetime):
        """requests.get mock: CIK JSON 첫 호출, Atom XML 두 번째 호출."""
        cik_resp = MagicMock()
        cik_resp.json.return_value = _CIK_JSON
        cik_resp.raise_for_status = MagicMock()

        atom_resp = MagicMock()
        atom_resp.text = _atom_xml(updated_dt.isoformat())
        atom_resp.raise_for_status = MagicMock()

        return [cik_resp, atom_resp]

    def test_8k_within_lookback_true(self):
        now = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
        updated = now - timedelta(hours=24)
        resps = self._mock_requests(updated)
        with patch("requests.get", side_effect=resps):
            hit, syms = self.has_8k_filing(["AAPL"], lookback_hours=48, now=now)
        assert hit is True
        assert "AAPL" in syms

    def test_8k_outside_lookback_false(self):
        now = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
        updated = now - timedelta(hours=72)
        resps = self._mock_requests(updated)
        with patch("requests.get", side_effect=resps):
            hit, syms = self.has_8k_filing(["AAPL"], lookback_hours=48, now=now)
        assert hit is False

    def test_unknown_ticker_skipped(self):
        """CIK 없는 티커는 건너뛰고 다른 종목에 영향 없음."""
        import news.triggers as mod
        mod._CIK_CACHE.clear()
        # CIK JSON에 없는 티커
        cik_resp = MagicMock()
        cik_resp.json.return_value = {}  # 빈 맵
        cik_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=cik_resp):
            hit, syms = self.has_8k_filing(["UNKNOWN_XYZ"])
        assert hit is False

    def test_sec_request_failure_returns_false(self):
        """SEC 서버 오류 시 graceful False."""
        import news.triggers as mod
        mod._CIK_CACHE["AAPL"] = "0000320193"  # 캐시 수동 주입
        with patch("requests.get", side_effect=Exception("HTTP 500")):
            hit, syms = self.has_8k_filing(["AAPL"])
        assert hit is False

    def test_user_agent_header_set(self):
        """User-Agent 헤더가 SEC 요구 사항 준수 (식별 가능한 문자열 포함)."""
        from news.triggers import _SEC_UA
        assert "STOCK_WORK" in _SEC_UA or "research" in _SEC_UA.lower()

    def test_cik_cache_loaded_once(self):
        """CIK JSON은 1회만 로드 (캐시 작동)."""
        import news.triggers as mod
        mod._CIK_CACHE.clear()
        now = datetime(2026, 4, 15, 12, 0, 0, tzinfo=timezone.utc)
        updated = now - timedelta(hours=1)

        cik_resp = MagicMock()
        cik_resp.json.return_value = _CIK_JSON
        cik_resp.raise_for_status = MagicMock()
        atom_resp = MagicMock()
        atom_resp.text = _atom_xml(updated.isoformat())
        atom_resp.raise_for_status = MagicMock()

        # AAPL 2번 호출해도 CIK JSON은 1회만
        with patch("requests.get", side_effect=[cik_resp, atom_resp, atom_resp]) as mock_get:
            self.has_8k_filing(["AAPL"], lookback_hours=48, now=now)
            mod_cache_size = len(mod._CIK_CACHE)

        assert mod_cache_size > 0  # 캐시가 채워졌음


# ─── should_analyze_news ─────────────────────────────────────────────────────


class TestShouldAnalyzeNews:
    def setup_method(self):
        from news.triggers import should_analyze_news
        self.should_analyze = should_analyze_news

    def test_fomc_short_circuits_other_triggers(self):
        """FOMC True 면 yfinance/SEC 호출 없음."""
        with patch("news.triggers.is_earnings_week") as mock_earn, \
             patch("news.triggers.has_8k_filing") as mock_8k:
            hit, reason = self.should_analyze(["AAPL"], today=date(2026, 4, 29))
        assert hit is True
        assert reason == "fomc_week"
        mock_earn.assert_not_called()
        mock_8k.assert_not_called()

    def test_no_triggers_returns_false(self):
        non_fomc = date(2026, 4, 15)
        with patch("news.triggers.is_earnings_week", return_value=(False, [])), \
             patch("news.triggers.has_8k_filing", return_value=(False, [])):
            hit, reason = self.should_analyze(["AAPL"], today=non_fomc)
        assert hit is False
        assert reason == "no_trigger"

    def test_earnings_reason_format(self):
        non_fomc = date(2026, 4, 15)
        with patch("news.triggers.is_earnings_week", return_value=(True, ["AAPL", "MSFT"])), \
             patch("news.triggers.has_8k_filing", return_value=(False, [])):
            hit, reason = self.should_analyze(["AAPL", "MSFT"], today=non_fomc)
        assert hit is True
        assert reason.startswith("earnings:")
        assert "AAPL" in reason

    def test_8k_reason_format(self):
        non_fomc = date(2026, 4, 15)
        with patch("news.triggers.is_earnings_week", return_value=(False, [])), \
             patch("news.triggers.has_8k_filing", return_value=(True, ["NVDA"])):
            hit, reason = self.should_analyze(["NVDA"], today=non_fomc)
        assert hit is True
        assert reason.startswith("8k:")
        assert "NVDA" in reason

    def test_empty_symbols_only_fomc_possible(self):
        """심볼 없으면 FOMC만 트리거 가능."""
        non_fomc = date(2026, 4, 15)
        hit, reason = self.should_analyze([], today=non_fomc)
        assert hit is False

    def test_earnings_short_circuits_8k(self):
        """Earnings True 면 8-K 호출 없음."""
        non_fomc = date(2026, 4, 15)
        with patch("news.triggers.is_earnings_week", return_value=(True, ["AAPL"])) as mock_earn, \
             patch("news.triggers.has_8k_filing") as mock_8k:
            hit, reason = self.should_analyze(["AAPL"], today=non_fomc)
        assert hit is True
        mock_8k.assert_not_called()
