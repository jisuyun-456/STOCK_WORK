"""Base strategy interface and Signal data structures for paper trading."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass
class Signal:
    """A trade signal produced by a strategy module."""

    strategy: str  # "MOM", "VAL", "QNT", "LEV"
    symbol: str
    direction: Direction
    weight_pct: float  # target weight within strategy (0.0 ~ 1.0)
    confidence: float  # 0.0 ~ 1.0
    reason: str
    order_type: str = "market"  # "market" | "limit"
    limit_price: Optional[float] = None

    @property
    def client_order_id_prefix(self) -> str:
        """Generate order ID prefix for strategy attribution."""
        from datetime import date

        return f"{self.strategy}-{date.today().strftime('%Y%m%d')}-{self.symbol}"


@dataclass
class ExitRule:
    """Exit rules for a position."""

    stop_loss_pct: float  # e.g., 0.10 = -10%
    take_profit_pct: float  # e.g., 0.20 = +20%
    time_stop_days: Optional[int] = None  # max holding period


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies.

    Strategies are deterministic Python modules — given the same market data,
    they always produce the same signals. This enables backtesting and auditing.
    """

    name: str = ""
    capital_pct: float = 0.25  # fraction of total account capital
    universe: list[str] = field(default_factory=list)
    max_positions: int = 10
    rebalance_freq: str = "monthly"  # "daily" | "weekly" | "monthly"
    stop_loss_pct: float = 0.10
    take_profit_pct: float = 0.20

    @abstractmethod
    def generate_signals(self, market_data: dict) -> list[Signal]:
        """Generate trade signals from market data.

        Args:
            market_data: Dict with keys like 'prices', 'fundamentals', 'indicators'
                         structured per strategy needs.

        Returns:
            List of Signal objects. Empty list = no action.
        """
        ...

    def get_exit_rules(self) -> ExitRule:
        """Default exit rules. Override per strategy if needed."""
        return ExitRule(
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
        )

    def should_rebalance(self, last_rebalance_date: str, today: str) -> bool:
        """Check if rebalancing is due based on frequency."""
        from datetime import datetime

        last = datetime.strptime(last_rebalance_date, "%Y-%m-%d")
        now = datetime.strptime(today, "%Y-%m-%d")
        delta = (now - last).days

        thresholds = {"daily": 1, "weekly": 7, "monthly": 28}
        return delta >= thresholds.get(self.rebalance_freq, 28)
