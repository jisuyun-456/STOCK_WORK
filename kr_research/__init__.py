"""한국 주식 시장 분석 모듈 v2 — 분석 전용 (매매 실행 없음).

Entry points:
    /analyze-kr → analyzer.main()

v2 changes (HIGH #1 fix):
    - models.py:       KRVerdict/KRRegime/KRAnalysisResult (BUY/HOLD/SELL/VETO)
    - regime.py:       US-corrected Regime Detection
    - scorer.py:       Layer 1 pykrx-based scoring (no Claude)
    - agent_runner.py: Real Claude API dispatch (not a dead stub)
    - consensus.py:    Regime-aware weighted aggregation
    - analyzer.py:     Full pipeline + CLI entry point

Legacy v1 files preserved:
    - kr_models.py, kr_regime.py, kr_agent_runner.py, kr_analyzer.py, kr_report_generator.py
    (imported by existing scripts that reference them)
"""

# v2 public API
from kr_research.models import KRVerdict, KRRegime, KRAnalysisResult
from kr_research.analyzer import analyze_ticker, analyze_top_n
from kr_research import agent_runner  # noqa: F401 — needed for mock patching in tests

# v1 legacy compatibility (existing scripts)
from kr_research.kr_models import (
    KRVerdict as KRVerdictLegacy,
    KRAnalysisResult as KRAnalysisResultLegacy,
    KRRegimeDetection,
)
from kr_research.kr_analyzer import run_analysis

__all__ = [
    # v2
    "KRVerdict",
    "KRRegime",
    "KRAnalysisResult",
    "analyze_ticker",
    "analyze_top_n",
    "agent_runner",
    # v1 legacy
    "KRVerdictLegacy",
    "KRAnalysisResultLegacy",
    "KRRegimeDetection",
    "run_analysis",
]
