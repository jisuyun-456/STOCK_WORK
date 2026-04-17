"""KR Backtest Harness — rules-mode only, no Claude API calls.

Main loop:
  For each trading day in [start, end]:
    1. _load_historical_snapshot(day)     — historical or mock data
    2. detect_kr_regime(snapshot, ...)    — rules-based
    3. score_universe([], snapshot)       — empty universe → []
    4. run_rules([], regime)              — empty tickers → no orders
    5. settle_due(today)                  — settle T+2 orders
    6. compute_nav({})                    — current NAV
    7. append nav_history
    8. track daily return

After loop: compute CAGR / MDD / Sharpe / Sortino, return BacktestResult.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# KEY IMPORTS — rules mode only (no Claude calls in backtest)
from kr_research.regime import detect_kr_regime
from kr_research.scorer import score_universe, select_top_n
from kr_research.agent_runner import run_rules  # rules mode ONLY
from kr_paper import portfolio as portfolio_module
from kr_backtest.metrics import (
    compute_cagr,
    compute_mdd,
    compute_sharpe,
    compute_sortino,
    compute_sector_attribution,
)
from kr_backtest.scenarios import SCENARIOS, get_scenario

log = logging.getLogger("kr_backtest.harness")

# Path to the real market state snapshot (used when day == today)
_KR_MARKET_STATE_PATH = (
    Path(__file__).parent.parent / "state" / "kr_market_state.json"
)


@dataclass
class BacktestResult:
    scenario: str
    cagr: float
    sharpe: float
    mdd: float
    sortino: float
    sector_attribution: dict
    nav_history: list
    trade_log: list
    benchmark_comparison: dict


def _build_mock_snapshot(day: date) -> dict:
    """Return a minimal snapshot dict compatible with detect_kr_regime.

    Values are fixed-neutral so that rules-mode produces stable NEUTRAL regime
    without any external data calls.
    """
    return {
        "date": day.isoformat(),
        "kospi": {
            "close": 2500.0,
            "sma200": 2400.0,
            "kospi_vs_sma200": 1.04,  # above SMA200 → mild BULL candidate
        },
        "vkospi": {
            "level": 18.0,  # below 20 → no BEAR/CRISIS from VKOSPI
        },
        "bok_rate": {
            "rate": 3.0,
        },
        "semiconductor_export": {
            "yoy_pct": 5.0,  # positive → no semi-export cap
        },
    }


class KRBacktest:
    def __init__(self, start: str, end: str, initial_krw: int = 10_000_000):
        self.start = date.fromisoformat(start)
        self.end = date.fromisoformat(end)
        self.initial_krw = initial_krw
        self._nav_history: list[dict] = []
        self._trade_log: list[dict] = []
        self._daily_returns: list[float] = []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_trading_days(self) -> list[date]:
        """Return all weekdays between start and end (inclusive)."""
        days: list[date] = []
        current = self.start
        while current <= self.end:
            if current.weekday() < 5:  # Mon=0 … Fri=4
                days.append(current)
            current += timedelta(days=1)
        return days

    def _load_historical_snapshot(self, day: date) -> dict:
        """Load or synthesise a KR market snapshot for the given day.

        Strategy:
        - If day == today AND state/kr_market_state.json exists → use real file.
        - Otherwise → return a mock snapshot (no pykrx / DART calls in backtest).
        """
        today = date.today()
        if day == today and _KR_MARKET_STATE_PATH.exists():
            try:
                with open(_KR_MARKET_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log.debug("Loaded real snapshot for %s", day)
                return data
            except Exception as exc:
                log.warning("Failed to load real snapshot for %s: %s — using mock", day, exc)

        return _build_mock_snapshot(day)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(
        self,
        scenario: str = "default_16m",
        max_days: Optional[int] = None,
        portfolio_path_override: Optional[str] = None,
        initial_state: Optional[dict] = None,
    ) -> BacktestResult:
        """Execute the backtest loop and return a BacktestResult.

        Args:
            scenario:                Scenario name (key in SCENARIOS dict).
            max_days:                If set, limit the loop to this many trading days
                                     (useful for fast unit tests).
            portfolio_path_override: Override the portfolio JSON path for test isolation.
                                     When set, also patches portfolio_module.KR_PORTFOLIOS_PATH.
            initial_state:           If provided, use this as the starting portfolio state
                                     instead of a blank slate. Useful for injecting pre-seeded
                                     pending_settlement records in tests.
        """
        # ------------------------------------------------------------------
        # Apply portfolio path override for test isolation
        # ------------------------------------------------------------------
        _original_path = portfolio_module.KR_PORTFOLIOS_PATH
        if portfolio_path_override is not None:
            portfolio_module.KR_PORTFOLIOS_PATH = Path(portfolio_path_override)

        try:
            return self._run_inner(scenario=scenario, max_days=max_days, initial_state=initial_state)
        finally:
            # Always restore the original path
            portfolio_module.KR_PORTFOLIOS_PATH = _original_path

    def _run_inner(
        self,
        scenario: str,
        max_days: Optional[int],
        initial_state: Optional[dict] = None,
    ) -> BacktestResult:
        # ------------------------------------------------------------------
        # Initialise portfolio state — use provided state or create blank slate
        # ------------------------------------------------------------------
        if initial_state is not None:
            portfolio_module.save(initial_state)
        else:
            blank: dict = {
                "KR_PAPER": {
                    "cash_krw": self.initial_krw,
                    "positions": {},
                    "nav_history": [],
                    "pending_settlement": [],
                }
            }
            portfolio_module.save(blank)

        trading_days = self._get_trading_days()
        if max_days is not None:
            trading_days = trading_days[:max_days]

        self._nav_history = []
        self._trade_log = []
        self._daily_returns = []

        prev_nav: Optional[int] = None

        for day in trading_days:
            day_str = day.isoformat()

            # Step 1: Historical snapshot
            snapshot = self._load_historical_snapshot(day)

            # Step 2: Detect regime (rules-based, no Claude)
            regime = detect_kr_regime(snapshot)

            # Step 3: Score universe (empty in skeleton — no pykrx calls)
            scored = score_universe([], snapshot)

            # Step 4: rules-mode verdicts (empty tickers → no orders)
            top_tickers = select_top_n(scored, n=10)
            verdicts = run_rules(top_tickers, regime)

            # Step 5: Settle T+2 orders due today
            settled = portfolio_module.settle_due(day_str)
            for record in settled:
                self._trade_log.append(record)

            # Step 6: Compute current NAV (no open positions in skeleton)
            nav = portfolio_module.compute_nav({})

            # Step 7: Append nav history
            portfolio_module.append_nav_history(day_str, nav)
            self._nav_history.append({"date": day_str, "nav": nav})

            # Step 8: Track daily return
            if prev_nav is not None and prev_nav > 0:
                daily_return = (nav - prev_nav) / prev_nav
                self._daily_returns.append(daily_return)
            prev_nav = nav

            log.debug(
                "Day %s | regime=%s | nav=%d | settled=%d",
                day_str,
                regime.regime,
                nav,
                len(settled),
            )

        # ------------------------------------------------------------------
        # Compute metrics after loop
        # ------------------------------------------------------------------
        cagr = compute_cagr(self._nav_history)
        mdd = compute_mdd(self._nav_history)
        sharpe = compute_sharpe(self._daily_returns)
        sortino = compute_sortino(self._daily_returns)
        sector_attr = compute_sector_attribution(self._trade_log)

        return BacktestResult(
            scenario=scenario,
            cagr=cagr,
            sharpe=sharpe,
            mdd=mdd,
            sortino=sortino,
            sector_attribution=sector_attr,
            nav_history=list(self._nav_history),
            trade_log=list(self._trade_log),
            benchmark_comparison={},  # populated by caller if needed
        )
