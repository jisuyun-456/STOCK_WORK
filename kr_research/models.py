"""한국 주식 연구 데이터 모델 (v2).

KRVerdict    — 단일 에이전트 분석 결과 (BUY/HOLD/SELL/VETO)
KRRegime     — 한국 시장 Regime (US-corrected)
KRAnalysisResult — 단일 종목 통합 분석 결과
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

KRRegimeType = Literal["BULL", "NEUTRAL", "BEAR", "CRISIS"]
KRVerdictType = Literal["BUY", "HOLD", "SELL", "VETO"]


@dataclass
class KRVerdict:
    """단일 에이전트(또는 consensus)의 분석 결과."""

    ticker: str
    verdict: KRVerdictType
    confidence: float          # 0.0 ~ 1.0
    agent: str                 # "equity" | "technical" | "macro" | "sector" | "commander" | "claude" | "consensus"
    rationale: str
    timestamp: datetime = field(default_factory=datetime.now)
    veto: bool = False
    veto_reason: str = ""


@dataclass
class KRRegime:
    """한국 시장 Regime (US-corrected 보정 포함)."""

    regime: KRRegimeType
    confidence: float
    factors: dict              # {"kospi_trend": ..., "vkospi": ..., "us_override": ..., "sox_trend": ...}
    source: str = "kr_research"


@dataclass
class KRAnalysisResult:
    """단일 종목의 통합 분석 결과."""

    ticker: str
    verdicts: list[KRVerdict]
    consensus: KRVerdict       # final consensus verdict
    regime: KRRegime
    analyzed_at: datetime = field(default_factory=datetime.now)
