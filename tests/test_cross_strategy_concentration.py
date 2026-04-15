"""Cross-strategy sector concentration gate tests."""
import pytest
from unittest.mock import patch
from execution.risk_validator import (
    check_cross_strategy_concentration,
    STRATEGY_SECTOR_LIMITS,
)


# ── 섹터 mock (yfinance 호출 없이) ──────────────────────────────────────────
SECTOR_MAP_MOCK = {
    "NVDA": "Technology",
    "AMD":  "Technology",
    "AMAT": "Technology",
    "LRCX": "Technology",
    "AAPL": "Technology",
    "MSFT": "Technology",
    "JPM":  "Financials",
    "BAC":  "Financials",
    "SPY":  "ETF-Broad",
}


def _mock_get_sector(symbol: str) -> str:
    return SECTOR_MAP_MOCK.get(symbol, "Unknown")


class TestCheckCrossStrategyConcentration:
    """check_cross_strategy_concentration() 단위 테스트."""

    def _build_strat(self, positions: dict) -> dict:
        """portfolios['strategies'] 한 항목 형식 생성."""
        return {
            "positions": {
                sym: {"market_value": val, "qty": 1, "current": val}
                for sym, val in positions.items()
            }
        }

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_blocks_when_cross_strategy_exceeds_threshold(self, _):
        """MOM 25%+QNT 20% Technology → 총 45% > 30% → BLOCK."""
        all_positions = {
            "MOM": self._build_strat({"NVDA": 25_000, "AMD": 0}),
            "QNT": self._build_strat({"AMAT": 20_000}),
        }
        passed, result = check_cross_strategy_concentration(
            symbol="LRCX",          # Technology
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert not passed
        assert result.check_name == "cross_strategy_concentration"
        assert "Technology" in result.reason

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_passes_when_below_threshold(self, _):
        """MOM 10%+QNT 10% Technology → 총 20% < 30% → PASS."""
        all_positions = {
            "MOM": self._build_strat({"NVDA": 10_000}),
            "QNT": self._build_strat({"AMD": 10_000}),
        }
        passed, result = check_cross_strategy_concentration(
            symbol="JPM",           # Financials — different sector
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_unknown_sector_passes(self, _):
        """Unknown 섹터는 per-strategy 게이트에서 처리 → cross-strategy PASS."""
        all_positions = {"MOM": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="UNKNOWN_TICKER",
            trade_value=5_000,
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed
        assert result.check_name == "cross_strategy_concentration"

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_trade_value_included_in_calculation(self, _):
        """새로 매수할 금액도 계산에 포함된다."""
        # 기존 보유 없음, trade_value만으로 50% → BLOCK
        all_positions = {"MOM": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="NVDA",
            trade_value=50_000,     # 50% of 100K
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert not passed

    @patch("execution.risk_validator.get_sector", side_effect=_mock_get_sector)
    def test_empty_positions_passes(self, _):
        """포지션 없고 소액 매수 → PASS."""
        all_positions = {"MOM": self._build_strat({}), "QNT": self._build_strat({})}
        passed, result = check_cross_strategy_concentration(
            symbol="NVDA",
            trade_value=5_000,      # 5% → below 30%
            all_strategy_positions=all_positions,
            total_portfolio=100_000,
            max_pct=0.30,
        )
        assert passed

    def test_strategy_sector_limits_tightened(self):
        """MOM/VAL/QNT 전략별 sector limit이 30% 이하인지 확인."""
        for strat in ("MOM", "VAL", "QNT"):
            assert STRATEGY_SECTOR_LIMITS[strat] <= 0.30, (
                f"{strat} sector limit {STRATEGY_SECTOR_LIMITS[strat]:.0%} > 30%"
            )
