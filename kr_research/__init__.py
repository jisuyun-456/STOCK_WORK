"""한국 주식 시장 분석 모듈 — 분석 전용 (매매 실행 없음).

Entry points:
    /analyze-kr → kr_analyzer.main()

Data sources:
    - FinanceDataReader (FDR): KRX OHLCV, KOSPI 지수, KRW/USD
    - yfinance: ^VKOSPI, 보조 지표
    - DART OpenAPI: 공시/재무제표 (DART_API_KEY 환경변수 필요, 없으면 skip)
    - 한국은행 ECOS API: 기준금리 (ECOS_API_KEY 환경변수 필요, 없으면 WebFetch)
    - naver 금융 crawl: 외국인/기관 수급 (선택, 실패 시 graceful degradation)
"""

from kr_research.kr_models import KRVerdict, KRAnalysisResult, KRRegimeDetection
from kr_research.kr_analyzer import run_analysis

__all__ = ["KRVerdict", "KRAnalysisResult", "KRRegimeDetection", "run_analysis"]
