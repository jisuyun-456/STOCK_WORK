"""Data structures for the Research Overlay system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResearchRequest:
    """Input to Research Division agents."""

    signals: list  # list[Signal] from strategies.base_strategy
    market_snapshot: dict  # Phase 1 data (prices, positions)
    portfolio_state: dict  # state/portfolios.json content
    regime: str  # "BULL" | "BEAR" | "CRISIS" | "NEUTRAL"
    mode: str = "initial"  # "initial" | "appeal"
    appeal_context: Optional[dict] = None  # {"failed_checks": [...], "risk_details": {...}}


@dataclass
class ResearchVerdict:
    """Output from a single Research Division agent."""

    agent: str  # "equity_research", "technical_strategist", etc.
    symbol: str
    direction: str  # "AGREE" | "DISAGREE" | "VETO"
    confidence_delta: float  # -0.3 ~ +0.3
    conviction: str  # "STRONG" | "MODERATE" | "WEAK"
    reasoning: str  # 1-3 sentence justification
    key_metrics: dict = field(default_factory=dict)
    override_vote: Optional[str] = None  # "STRONG_OVERRIDE" | "REJECT" | None (appeal only)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence_delta": self.confidence_delta,
            "conviction": self.conviction,
            "reasoning": self.reasoning,
            "key_metrics": self.key_metrics,
            "override_vote": self.override_vote,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ResearchVerdict:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RegimeDetection:
    """Market regime classification output."""

    regime: str  # "BULL" | "BEAR" | "CRISIS" | "NEUTRAL"
    sp500_vs_sma200: float  # ratio (1.05 = 5% above SMA200)
    vix_level: float
    reasoning: str
    timestamp: str = ""
