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
    # 가격 전략
    entry_price_low: float | None = None   # 매수 구간 하단
    entry_price_high: float | None = None  # 매수 구간 상단
    target_price: float | None = None      # 목표가 T1 (보수적, 50% 익절)
    target_price_2: float | None = None    # 목표가 T2 (공격적, 전량 매도)
    stop_loss: float | None = None         # 손절가
    # 타이밍
    buy_trigger: str = ""        # 매수 타이밍 조건
    sell_trigger: str = ""       # 매도 타이밍 조건
    current_status: str = ""     # 현재 기술적 상태 한줄 요약
    # 시나리오
    bull_case: str = ""          # 강세 시나리오 (수익률 + 촉매)
    base_case: str = ""          # 기본 시나리오
    bear_case: str = ""          # 약세 시나리오
    # 메타
    company_name: str = ""
    sector: str = ""
    risk_factors: list[str] = field(default_factory=list)
    investment_thesis: str = ""
    buy_factors: list[str] = field(default_factory=list)
    sell_factors: list[str] = field(default_factory=list)
    # 하위호환 (기존 코드용)
    entry_price: float | None = None


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
