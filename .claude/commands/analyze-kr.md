# /analyze-kr — 한국 주식 시장 분석

한국 주식 시장 분석 커맨드. kr-commander 에이전트가 4개 KR 리서치 에이전트를 병렬 실행하여 분석 결과를 종합한다.
**분석 전용 — 매매 실행 없음.**

## 사용법

```
/analyze-kr {TARGET}

TARGET 예시:
  005930            종목 코드 (삼성전자)
  005930.KS         yfinance 형식도 허용
  삼성전자           종목명 검색 (universe에서 코드로 변환)
  sector:반도체      섹터 전체 분석
  sector:이차전지    섹터 분석
  all               KOSPI TOP50 전체 스캔
```

## 실행 지침 (kr-commander 호출)

이 커맨드가 실행되면 **kr-commander 에이전트**가 자동으로 처리한다.
직접 실행이 필요한 경우 아래 단계를 따른다.

### Step 1 — Python rules mode (빠른 분석, 기본)

```bash
# 단일 종목
python kr_research/kr_analyzer.py --symbol 005930

# 섹터
python kr_research/kr_analyzer.py --sector 반도체

# 전체 스캔 (시간 소요)
python kr_research/kr_analyzer.py --all

# 캐시 무시 (강제 새로고침)
python kr_research/kr_analyzer.py --symbol 005930 --force-refresh
```

### Step 2 — 결과 확인

```bash
# 저장된 분석 결과
cat state/kr_verdicts.json

# 시장 스냅샷 (Regime, VKOSPI, 환율, BOK 금리)
cat state/kr_market_state.json

# 생성된 리포트
ls reports/kr/
```

### Step 3 — 심층 분석 (claude mode, 선택)

정밀 분석이 필요한 경우 kr-commander가 4개 에이전트를 병렬 호출:

```
Agent(subagent_type="kr-equity-research",     ...)  # 밸류에이션
Agent(subagent_type="kr-technical-strategist", ...)  # 차트/수급
Agent(subagent_type="kr-macro-economist",      ...)  # 매크로/Regime
Agent(subagent_type="kr-sector-analyst",       ...)  # 섹터 순환
```

## 출력 형식

```
=== /analyze-kr {SYMBOL} ({종목명}) ===
KR Regime: BULL  |  VKOSPI: 17.2  |  BOK: 3.00%  |  KRW/USD: 1,340

  kr_equity_research      AGREE    +0.10 STRONG    PBR 1.2, ROE 12.3%
  kr_technical_strategist AGREE    +0.05 MODERATE  SMA200 위, 외인 순매수
  kr_macro_economist      AGREE    +0.06 STRONG    KR Regime BULL, KRW 약세
  kr_sector_analyst       AGREE    +0.08 STRONG    반도체 사이클 상승

Aggregate: 4 AGREE / 0 DISAGREE / 0 CAUTION
Weighted Score: +0.29 (STRONG — 분석 전용)
Report: reports/kr/YYYY-MM-DD-kr-{SYMBOL}-analysis.md
```

## 데이터 소스

| 소스 | 용도 | API 키 |
|------|------|--------|
| FinanceDataReader | OHLCV, KOSPI 지수, KRW/USD | 불필요 |
| yfinance | ^VKOSPI, 보조 PER/PBR | 불필요 |
| DART OpenAPI | 공시, 재무제표 | `DART_API_KEY` (선택) |
| 한국은행 ECOS | 기준금리 | `ECOS_API_KEY` (선택) |
| naver 금융 | 외국인/기관 수급 | 불필요 (크롤링) |

## 관련 파일

- `kr_research/kr_analyzer.py` — 메인 진입점
- `kr_research/kr_data_fetcher.py` — 데이터 수집
- `kr_research/kr_regime.py` — KR Regime 판별
- `kr_research/kr_agent_runner.py` — 에이전트 병렬 실행
- `state/kr_universe.json` — KOSPI TOP50 유니버스
- `state/kr_verdicts.json` — 분석 캐시 (24h TTL)
- `reports/kr/` — 생성 리포트
