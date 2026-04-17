"""한국 시장 분석 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KRVerdict:
    """단일 KR 에이전트의 분석 결과.

    direction: "AGREE" | "DISAGREE" | "CAUTION"
      (US ResearchVerdict과 달리 VETO 없음 — 매매 실행 없으므로)
    confidence_delta: -0.3 ~ +0.3
    conviction: "STRONG" | "MODERATE" | "WEAK"
    """

    agent: str          # "kr_equity_research" | "kr_technical_strategist" | ...
    symbol: str         # "005930" (FDR 코드, .KS 없이)
    direction: str      # "AGREE" | "DISAGREE" | "CAUTION"
    confidence_delta: float
    conviction: str     # "STRONG" | "MODERATE" | "WEAK"
    reasoning: str      # 1~3문장 근거
    key_metrics: dict = field(default_factory=dict)
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
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KRVerdict":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class KRRegimeDetection:
    """한국 시장 Regime 판별 결과."""

    regime: str              # "BULL" | "BEAR" | "NEUTRAL" | "CRISIS" | "EUPHORIA"
    kospi_vs_sma200: float   # 비율 (1.04 = SMA200 대비 4% 위)
    vkospi_level: float      # VKOSPI 수준
    usdkrw_20d_change: float # 원달러 20일 변화율 (+는 원화 약세)
    bok_rate: float          # 한국은행 기준금리 (%)
    reasoning: str
    semiconductor_export_yoy: Optional[float] = None  # 반도체 수출 YoY (보정용)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "kospi_vs_sma200": self.kospi_vs_sma200,
            "vkospi_level": self.vkospi_level,
            "usdkrw_20d_change": self.usdkrw_20d_change,
            "bok_rate": self.bok_rate,
            "reasoning": self.reasoning,
            "semiconductor_export_yoy": self.semiconductor_export_yoy,
            "timestamp": self.timestamp,
        }


@dataclass
class KRAnalysisResult:
    """단일 종목/섹터의 통합 분석 결과."""

    symbol: str
    name: str
    sector: str
    verdicts: list = field(default_factory=list)   # list[KRVerdict]
    regime: Optional[KRRegimeDetection] = None
    weighted_score: float = 0.0   # Σ(delta × conviction_weight)
    agree_count: int = 0
    disagree_count: int = 0
    caution_count: int = 0
    summary: str = ""             # 최종 한줄 판단
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "verdicts": [v.to_dict() for v in self.verdicts],
            "regime": self.regime.to_dict() if self.regime else None,
            "weighted_score": self.weighted_score,
            "agree_count": self.agree_count,
            "disagree_count": self.disagree_count,
            "caution_count": self.caution_count,
            "summary": self.summary,
            "timestamp": self.timestamp,
        }
