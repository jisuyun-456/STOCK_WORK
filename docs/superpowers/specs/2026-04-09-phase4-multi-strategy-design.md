# Phase 4: Multi-Strategy + Regime Gateway + News Sentiment

> 2026-04-09 | Approach A: Regime Gateway (Bridgewater-style)

## Context

Phase 3 완료 (GitHub Actions cron 자동화). 현재 MOM(모멘텀) 전략만 운용 중.
Phase 4에서 나머지 3개 전략(VAL/QNT/LEV) 추가 + Regime Detection 기반 동적 배분 + Gemini 무료 뉴스 감성 분석을 구현한다.

**목표**: 4전략 병렬 운용, Regime-aware 배분, 뉴스 감성 통합. 전부 무료.

---

## 1. Regime Gateway (Phase 1.5)

기존 `consensus.py`의 `detect_regime()`을 확장하여 run_cycle.py에서 Phase 1.5로 독립 실행.
Research Overlay(skip)와 무관하게 **항상 실행**.

### Regime 판별 공식 (확장)

```
Regime Score = VIX 점수(40%) + SPY/SMA200 점수(30%) + 뉴스 감성 점수(30%)
```

| 지표 | 소스 | 가중치 | BULL | NEUTRAL | BEAR | CRISIS |
|------|------|--------|------|---------|------|--------|
| VIX | yfinance ^VIX | 40% | <20 | 20-25 | 25-30 | >30 |
| SPY/SMA200 | yfinance SPY | 30% | >1.05 | 1.0-1.05 | 0.95-1.0 | <0.95 |
| 뉴스 감성 | Gemini API | 30% | >0.3 | -0.1~0.3 | -0.5~-0.1 | <-0.5 |

### Regime별 전략 배분 테이블

```
┌──────────┬──────┬──────┬──────┬──────┬──────┐
│ Regime   │ MOM  │ VAL  │ QNT  │ LEV  │ CASH │
├──────────┼──────┼──────┼──────┼──────┼──────┤
│ BULL     │ 30%  │ 20%  │ 25%  │ 25%  │  0%  │
│ NEUTRAL  │ 25%  │ 25%  │ 30%  │ 20%  │  0%  │
│ BEAR     │ 15%  │ 35%  │ 30%  │  0%  │ 20%  │
│ CRISIS   │ 10%  │ 30%  │ 20%  │  0%  │ 40%  │
└──────────┴──────┴──────┴──────┴──────┴──────┘
```

- CRISIS/BEAR: LEV 비활성 (3x 레버리지 위험), 현금 비중 확보
- BULL: MOM+LEV 강화 (공격적)
- 배분 테이블은 `strategies/regime_allocator.py`에 상수로 관리

### 구현 위치

- `strategies/regime_allocator.py` (신규): 배분 테이블 + `allocate(regime, total_capital) -> dict`
- `research/consensus.py` (수정): `detect_regime()` 확장 (뉴스 감성 점수 통합)
- `run_cycle.py` (수정): Phase 1.5 추가, `phase_regime()` 함수

---

## 2. 전략 구현

### 2.1 VAL — Value Quality (`strategies/value_quality.py`)

| 항목 | 값 |
|------|-----|
| 유니버스 | S&P 500 |
| 데이터 소스 | yfinance + FMP API (무료 250건/일) |
| 리밸런싱 | 분기 (quarterly) |
| max_positions | 15 |
| stop_loss | 10% |
| take_profit | 20% |

**로직:**
1. FMP API로 P/E, ROE, FCF Yield 조회
2. 필터: P/E < 20 AND ROE > 12% AND FCF Yield > 4%
3. 복합 점수 = (1/P/E) * 0.4 + ROE * 0.3 + FCF_Yield * 0.3
4. 상위 15종목 등가중 매수

**Regime 적응:**
- CRISIS: P/E < 15, FCF Yield > 6% (방어적 가치주)
- BULL: P/E < 25 (성장 가치 포함)

**데이터 fetch 함수:** `fetch_value_data(universe) -> {"prices": df, "fundamentals": dict}`

### 2.2 QNT — Quant Factor (`strategies/quant_factor.py`)

| 항목 | 값 |
|------|-----|
| 유니버스 | Russell 1000 |
| 데이터 소스 | yfinance + Kenneth French 라이브러리 (pandas_datareader) |
| 리밸런싱 | 월간 (monthly) |
| max_positions | 20 |
| stop_loss | 10% |
| take_profit | 20% |

**로직:**
1. Kenneth French 라이브러리에서 5-factor 데이터 다운로드 (Mkt-RF, SMB, HML, RMW, CMA)
2. 각 종목의 factor exposure 계산 (rolling 60일 회귀)
3. 복합 점수 = HML * 0.25 + SMB * 0.15 + RMW * 0.25 + CMA * 0.20 + MOM * 0.15
4. 상위 20종목 등가중 매수

**Regime 적응:**
- CRISIS: Quality(RMW) 가중치 0.40으로 상향 (수익성 방어)
- BULL: MOM 가중치 0.25로 상향 (추세 추종 강화)

**데이터 fetch 함수:** `fetch_factor_data(universe) -> {"prices": df, "factors": df}`

### 2.3 LEV — Leveraged ETF (`strategies/leveraged_etf.py`)

| 항목 | 값 |
|------|-----|
| Long ETF | TQQQ (3x QQQ), UPRO (3x SPY), SOXL (3x 반도체) |
| Inverse ETF | SQQQ, SPXU |
| 기초지수 | QQQ, SPY, SOXX |
| 리밸런싱 | 일간 (daily) |
| max_positions | 3 |
| stop_loss | 8% (레버리지라 타이트) |
| take_profit | 15% |

**로직:**
1. 각 기초지수(QQQ, SPY, SOXX)의 SMA50, SMA200 계산
2. SMA50 > SMA200 → 해당 Long ETF 매수 (TQQQ/UPRO/SOXL)
3. SMA50 < SMA200 → 현금 보유 (기본)

**Regime 적응:**
- BULL: Long 3종 활성, 인버스 비활성
- NEUTRAL: SMA 크로스오버 엄격 적용
- BEAR/CRISIS: Regime Gateway에서 배분 0% → 전략 자체 비활성

**데이터 fetch 함수:** `fetch_leveraged_data() -> {"prices": df}` (기초지수 + ETF)

---

## 3. Gemini 뉴스 감성 모듈

### 파일 구조

```
news/
├── __init__.py
├── fetcher.py        # 뉴스 수집 (yfinance URL → 본문 스크래핑)
└── sentiment.py      # Gemini API 감성 분석
```

### fetcher.py

```
1. yf.Ticker(symbol).news → 뉴스 최대 30건 URL 수집
2. requests.get(url) → HTML 다운로드
3. BeautifulSoup → 본문 텍스트 추출 (500자 제한/건)
4. 반환: [{"title": str, "body": str, "url": str, "published": str}, ...]
```

- 페이월 / 접근 실패 시 헤드라인만 사용 (graceful degradation)
- 매크로 뉴스: `yf.Ticker("SPY").news` + `yf.Ticker("^VIX").news` 수집

### sentiment.py

```
1. 종목 30건 뉴스를 한 번에 묶어서 Gemini 1회 호출
2. 프롬프트: "다음 뉴스의 전반적 감성을 -1.0~+1.0 점수 + 한 줄 요약으로 반환"
3. JSON 파싱 → SentimentResult(score, summary, article_count)
```

**API 사용량:**
- 종목당 1회 호출 × 10종목 = 10건
- 매크로 종합 1회 = 총 11건/일
- 한도 1,500건/일의 0.7%

**환경변수:** `GEMINI_API_KEY` (Google AI Studio 무료 발급)

**오류 시:** Gemini 호출 실패 → 뉴스 감성 점수 0.0 (NEUTRAL) fallback

---

## 4. run_cycle.py 수정

### Phase 1: DATA (확장)

```python
def phase_data():
    # 기존: yfinance 가격 데이터
    market_data = fetch_momentum_data(...)
    
    # 추가: FMP 재무 + Kenneth French 팩터 + 뉴스 수집
    market_data["fundamentals"] = fetch_value_data(...)
    market_data["factors"] = fetch_factor_data(...)
    market_data["leveraged"] = fetch_leveraged_data(...)
    market_data["news"] = fetch_all_news(symbols)
    
    return market_data
```

### Phase 1.5: REGIME (신규)

```python
def phase_regime(market_data: dict) -> tuple[str, dict]:
    # 1. 뉴스 감성 분석 (Gemini)
    news_sentiment = analyze_sentiment(market_data["news"])
    
    # 2. Regime 판별 (VIX + SPY/SMA200 + 뉴스 감성)
    regime = detect_regime_enhanced(news_sentiment)
    
    # 3. 전략 배분 동적 조정
    allocations = allocate(regime, account_total=100000)
    
    return regime, allocations
```

### Phase 2: SIGNALS (수정)

```python
def phase_signals(market_data: dict, regime: str, allocations: dict) -> list:
    strategies = [
        MomentumStrategy(),
        ValueQualityStrategy(),
        QuantFactorStrategy(),
        LeveragedETFStrategy(),
    ]
    
    all_signals = []
    for strat in strategies:
        # Regime 기반 배분이 0이면 스킵
        if allocations.get(strat.name, 0) == 0:
            print(f"  {strat.name}: SKIPPED (regime={regime}, allocation=0%)")
            continue
        
        # 전략에 regime 정보 전달
        strat.regime = regime
        signals = strat.generate_signals(market_data)
        all_signals.extend(signals)
    
    return all_signals
```

---

## 5. 신규/수정 파일 목록

### 신규 (7개)

| 파일 | 역할 |
|------|------|
| `strategies/regime_allocator.py` | Regime별 배분 테이블 + allocate() |
| `strategies/value_quality.py` | VAL 전략 (P/E+ROE+FCF) |
| `strategies/quant_factor.py` | QNT 전략 (FF5) |
| `strategies/leveraged_etf.py` | LEV 전략 (SMA 크로스오버) |
| `news/fetcher.py` | yfinance 뉴스 + 본문 스크래핑 |
| `news/sentiment.py` | Gemini API 감성 분석 |
| `news/__init__.py` | 패키지 초기화 |

### 수정 (4개)

| 파일 | 변경 내용 |
|------|----------|
| `run_cycle.py` | Phase 1.5 추가, 4전략 로딩, phase_data 확장 |
| `research/consensus.py` | detect_regime() → detect_regime_enhanced() (뉴스 감성 통합) |
| `requirements.txt` | google-generativeai, pandas-datareader, beautifulsoup4 추가 |
| `CLAUDE.md` | Phase 4 전략 테이블 업데이트 |

### GitHub Secrets 추가 (1개)

| Secret | 용도 |
|--------|------|
| `GEMINI_API_KEY` | Gemini API 무료 티어 (1,500건/일) |

---

## 6. 비용 요약

| 항목 | 비용 |
|------|------|
| yfinance (가격/뉴스) | 무료 |
| FMP API (재무) | 무료 (250건/일) |
| Kenneth French (팩터) | 무료 |
| Gemini API (뉴스 감성) | 무료 (11건/일, 한도 1,500) |
| Alpaca Paper | 무료 |
| GitHub Actions | 무료 |
| **총 비용** | **$0** |

---

## 7. 검증

1. 각 전략 개별 dry-run: `python run_cycle.py --phase signals --dry-run`
2. Regime Gateway 테스트: BULL/BEAR/CRISIS 별 배분 확인
3. Gemini 뉴스 감성 테스트: 10종목 감성 점수 출력
4. 전체 사이클: `python run_cycle.py --phase all --dry-run`
5. GitHub Actions 수동 실행 (workflow_dispatch)
