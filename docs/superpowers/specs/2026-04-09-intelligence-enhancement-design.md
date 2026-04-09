# Intelligence Enhancement Master Spec (Phases 7-10)

> 작성일: 2026-04-09 | 상태: Draft
> 프로젝트: STOCK_WORK Paper Trading System

## Context

현재 Paper Trading 시스템의 정보 파이프라인이 취약하다:
- **뉴스**: yfinance `.news`만 사용, 500자 truncation, 유료기사 body 비어있음
- **감성분석**: Gemini로 헤드라인 위주 분석 (본문 200자만 전달)
- **Research Overlay**: 5에이전트가 가짜 규칙엔진 (`if confidence > 0.55 → AGREE`)
- **기술적분석**: SMA 크로스오버만 존재, RSI/MACD/볼린저 없음
- **매크로**: FRED 데이터가 리포트에만 사용, 매수/매도 결정에 미반영
- **예측시장**: 없음

이 스펙은 4단계 순차 강화를 통해 정보 수집과 분석을 실질적으로 개선한다.

## Phase Dependency Graph

```
Phase 7 (뉴스 크롤링)
    ├──> Phase 1.5 REGIME: 풍부한 sentiment_score
    ├──> Phase 8 (기술적분석) ──> market_data["indicators"]
    │       └──> Phase 2.5: Technical Strategist에 실제 데이터
    ├──> Phase 9 (Polymarket) ──> regime composite score 보강
    │       └──> Phase 1.5: polymarket_score 추가
    └──> Phase 10 (Research 실체화)
            모든 데이터 소비 → 실제 LLM 에이전트 분석
```

구현 순서: **7 → 8 → 9 → 10** (엄격한 의존 순서)

---

## Phase 7: News Crawling Enhancement

### 문제
`fetch_macro_news()`는 yfinance SPY+VIX 뉴스만 가져오고, body를 500자로 자름. 유료기사는 빈 body 반환.

### 대상 소스 (전부 무료 RSS)

| 소스 | RSS URL | 비고 |
|------|---------|------|
| Reuters Business | `https://feeds.reuters.com/reuters/businessNews` | |
| Reuters Markets | `https://feeds.reuters.com/reuters/USmarkets` | |
| AP Business | `https://feeds.ap.org/rss/topics/business` | |
| CNBC Top News | `https://www.cnbc.com/id/100003114/device/rss/rss.html` | |
| CNBC Finance | `https://www.cnbc.com/id/10000664/device/rss/rss.html` | |
| MarketWatch Top | `https://feeds.marketwatch.com/marketwatch/topstories/` | |
| MarketWatch Markets | `https://feeds.marketwatch.com/marketwatch/marketpulse/` | |
| NYT Business | `https://rss.nytimes.com/services/xml/rss/nyt/Business.xml` | |
| WSJ Markets | `https://feeds.content.dowjones.io/public/rss/mktw_mktnews` | description만 (페이월) |

### 새 파일 구조

```
news/sources/
├── __init__.py
├── base.py          # abstract NewsSource 어댑터
├── rss.py           # 범용 RSS/Atom 파서 (xml.etree.ElementTree)
├── reuters.py       # Reuters 어댑터
├── ap.py            # AP 어댑터
├── cnbc.py          # CNBC 어댑터
├── marketwatch.py   # MarketWatch 어댑터
├── nyt.py           # NYT 어댑터
└── wsj.py           # WSJ 어댑터 (description only)
```

### 어댑터 인터페이스

```python
class NewsSource(ABC):
    name: str
    rss_urls: list[str]
    paywall_domains: list[str]
    rate_limit_seconds: float

    @abstractmethod
    def fetch(self, max_articles: int = 20) -> list[dict]:
        """Returns [{"title", "body", "url", "published", "source"}]"""

    def _scrape_body_extended(self, url: str, max_chars: int = 3000) -> str:
        """공유 스크래핑 로직. 500→3000자로 확대."""
```

### 수정 파일

**`news/fetcher.py`**:
- `_BODY_MAX_CHARS`: 500 → 3000
- 새 함수: `fetch_rss_news(max_articles_per_source=15) -> list[dict]`
- 새 함수: `fetch_macro_news_enhanced()` — yfinance + RSS 병합, URL 중복 제거, 최대 60건
- `fetch_macro_news()`는 `fetch_macro_news_enhanced()`의 alias로 유지 (하위호환)
- 병렬 fetch: `ThreadPoolExecutor(max_workers=4)`

**`news/sentiment.py`**:
- `_build_prompt()`: body snippet 200 → 800자
- 기사에 `source` 필드 추가 (Gemini가 출처 인지)

**`run_cycle.py` Phase 1**:
- `fetch_macro_news()` → `fetch_macro_news_enhanced()`로 교체

### Graceful Degradation
- 개별 소스 실패 → 해당 소스만 skip, 나머지 계속
- 전체 RSS 실패 → 기존 yfinance fallback
- body 스크래핑 실패 → RSS `<description>` (200-400자) 사용
- 새 의존성: **없음** (xml.etree.ElementTree는 stdlib)

### 타이밍 예산
- RSS 8소스 × 2s + body 60건 × 1-3s = +30~90초
- `ThreadPoolExecutor(4)`로 병렬화 → 실제 +30~45초

---

## Phase 8: Technical Analysis Enhancement

### 문제
전략이 SMA 크로스오버만 사용. RSI, MACD, 볼린저, Volume 분석 없음. Technical Strategist 에이전트가 무력화 상태.

### 새 파일

**`strategies/indicators.py`** — 순수 pandas/numpy 구현 (ta-lib 불필요):

```python
def compute_indicators(
    close: pd.Series,
    volume: pd.Series | None = None,
    rsi_period: int = 14,
    macd_fast: int = 12, macd_slow: int = 26, macd_signal: int = 9,
    bb_period: int = 20, bb_std: float = 2.0,
) -> dict:
    """Returns:
    {
        "rsi": float,              # 0-100
        "macd": float,             # MACD line
        "macd_signal": float,      # signal line
        "macd_hist": float,        # histogram
        "macd_cross": str,         # "bullish"|"bearish"|"none"
        "bb_upper/middle/lower": float,
        "bb_pct_b": float,         # (price-lower)/(upper-lower)
        "bb_squeeze": bool,        # bandwidth < threshold
        "volume_ratio": float|None, # current / 20d avg
        "sma_20/50/200": float,
        "price_vs_sma200": float,
        "trend": str,              # "strong_up"|"up"|"neutral"|"down"|"strong_down"
    }
    """
```

구현:
- RSI: Wilder smoothing (EWM `adjust=False, alpha=1/period`)
- MACD: 두 EWM 차이 + signal EWM
- Bollinger: rolling mean ± N×std
- Volume ratio: `volume[-1] / volume.rolling(20).mean()[-1]`

### 수정 파일

**`run_cycle.py` Phase 1**:
- `yf.download()`에서 Volume 데이터 보존 (현재 버림)
- indicators dict 계산: `market_data["indicators"] = {symbol: compute_indicators(...)}`

**전략 파일 (선택적 강화)**:
- `momentum.py`: RSI overbought/oversold + MACD cross로 confidence 보정
- `leveraged_etf.py`: RSI>80이면 LEV confidence 감소 (변동성 드래그 위험)

### 인터페이스 계약

```python
market_data["indicators"]: dict[str, dict] = {
    "AAPL": {"rsi": 58.3, "macd": 2.14, ...},
    ...
}
# 누락 심볼 → 빈 dict, 전략은 .get(symbol, {}).get("rsi", 50)으로 안전 접근
```

### 새 의존성: **없음** (pandas/numpy만)

---

## Phase 9: Polymarket Integration

### 문제
Regime Detection이 VIX(40%) + SPY/SMA200(30%) + sentiment(30%)만 사용. 예측시장의 이벤트 확률 데이터 누락.

### 새 파일

**`research/polymarket.py`**:

```python
RELEVANT_MARKET_KEYWORDS = [
    "federal reserve", "fed rate", "interest rate", "recession",
    "inflation", "cpi", "unemployment", "gdp", "election",
    "tariff", "default", "debt ceiling",
]

@dataclass
class PolymarketSignal:
    question: str
    outcomes: list[str]        # ["Yes", "No"]
    probabilities: list[float] # [0.72, 0.28]
    volume_usd: float
    end_date: str
    market_id: str

def fetch_macro_markets(max_markets: int = 20) -> list[PolymarketSignal]:
    """Polymarket gamma API (무료, 인증 불필요)
    GET https://gamma-api.polymarket.com/markets?closed=false&limit=100
    RELEVANT_MARKET_KEYWORDS로 필터링
    """

def compute_polymarket_score(signals: list[PolymarketSignal]) -> float:
    """매크로 감성 점수 -1.0 ~ +1.0
    - rate cut 확률 → positive
    - recession 확률 → negative
    - volume_usd로 가중 (유동성 = 신뢰도)
    """
```

### Regime 통합

**`research/consensus.py` 수정**:

```python
def detect_regime_enhanced(
    news_sentiment_score: float = 0.0,
    polymarket_score: float = 0.0,      # NEW
) -> RegimeDetection:
    if polymarket_score == 0.0:
        # 기존 가중치 유지
        composite = vix * 0.40 + spy * 0.30 + news * 0.30
    else:
        # Polymarket 10% 배분 (보수적)
        composite = vix * 0.35 + spy * 0.25 + news * 0.30 + poly * 0.10
```

**`research/models.py` 수정**:
- `RegimeDetection`에 `polymarket_score: float = 0.0` 필드 추가

**`run_cycle.py` Phase 1.5**:
- Polymarket fetch → `polymarket_score` 계산 → `detect_regime_enhanced()`에 전달

### 새 의존성: **없음** (requests 기존 사용)
### Rate Limit: 무제한 (공개 API, 하루 1회 호출)

---

## Phase 10: Research Overlay Realization (하이브리드)

### 문제
`research/overlay.py`의 `_generate_verdicts()` (line 196-275)가 가짜 규칙엔진. 5에이전트가 실제 분석 안 함.

### 하이브리드 전략

| 모드 | 트리거 | LLM | 비용 |
|------|--------|-----|------|
| **cron 자동** | GH Actions 22:30 KST | Gemini 2.0 Flash (무료) | $0 |
| **대화형** | Claude Code `/run-cycle` | Claude Code 에이전트 토큰 | 구독 포함 |

### 새 파일

**`research/agent_runner.py`** — 하이브리드 LLM 에이전트 실행:

```python
# 모드 감지
_MODE = os.environ.get("RESEARCH_MODE", "rules")  # "rules"|"gemini"|"claude"

def run_agent_analysis(
    agent_name: str,       # equity_research|technical_strategist|...
    signal: Signal,
    market_data: dict,
    regime: RegimeDetection,
    mode: str = _MODE,
) -> ResearchVerdict:
    if mode == "rules":
        return _rule_fallback(agent_name, signal, regime)
    elif mode == "gemini":
        return _gemini_analysis(agent_name, signal, market_data, regime)
    elif mode == "claude":
        return _claude_interactive(agent_name, signal, market_data, regime)
```

**`research/agent_prompts.py`** — `.claude/agents/*.md`에서 파생된 시스템 프롬프트

### Gemini 모드 (cron용, 무료)

```python
def _gemini_analysis(agent_name, signal, market_data, regime):
    """Gemini 2.0 Flash로 경량 분석
    - 에이전트별 특화 프롬프트
    - 구조화된 컨텍스트 주입 (indicators, news, polymarket)
    - JSON ResearchVerdict 형식 반환
    - 실패 시 규칙엔진 fallback
    """
```

### Claude 대화형 모드

```python
def _claude_interactive(agent_name, signal, market_data, regime):
    """Claude Code 에이전트가 직접 분석
    - run_cycle.py가 research_request.json 작성
    - Claude Code 세션에서 에이전트 호출 (WebSearch/WebFetch 사용)
    - 에이전트가 실시간 웹 검색으로 최신 정보 수집
    - ResearchVerdict JSON 반환
    """
```

### 에이전트별 컨텍스트 주입

| 에이전트 | 받는 데이터 |
|---------|-----------|
| equity_research | fundamentals (PE, ROE, FCF) + 종목별 뉴스 top 3 |
| technical_strategist | indicators dict (RSI, MACD, BB, volume) + 가격 추세 |
| macro_economist | regime + VIX + polymarket signals + 매크로 뉴스 top 5 |
| portfolio_architect | portfolios.json 포지션 + 목표 비중 + 섹터 노출 |
| risk_controller | 변동성(BB) + 포지션 크기 + regime |

### overlay.py 수정

```python
_RESEARCH_MODE = os.environ.get("RESEARCH_MODE", "rules")

def _generate_verdicts(signal, market_data, portfolio_state, regime):
    if _RESEARCH_MODE == "rules":
        return _generate_verdicts_rules(...)   # 기존 코드 (이름만 변경)
    else:
        return _generate_verdicts_real(...)     # 새 LLM 기반
```

### 5에이전트 병렬 실행

```python
def _generate_verdicts_real(signal, market_data, portfolio_state, regime):
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(run_agent_analysis, agent, signal, market_data, regime): agent
            for agent in AGENT_NAMES
        }
        verdicts = []
        for future in as_completed(futures, timeout=60):
            try:
                verdicts.append(future.result(timeout=5))
            except Exception:
                verdicts.append(_rule_fallback(...))
    return verdicts
```

### GitHub Actions 설정

```yaml
# trading-cycle.yml
env:
  RESEARCH_MODE: ${{ secrets.RESEARCH_MODE || 'gemini' }}  # cron: gemini (무료)
```

### 캐시 호환성
- 기존 `research_cache.json` 형식 그대로 사용
- 실제 에이전트 verdict도 동일한 `ResearchVerdict.to_dict()` 저장
- TTL: rules=7일, gemini/claude=1일

### Gemini Rate Limit
- 무료: 15 req/min, 1M tokens/day
- 5에이전트 × ~35종목 = ~175 requests/cycle → **15 req/min 제한에 걸림**
- 해결: 전 종목이 아닌 **Phase 2 시그널이 발생한 종목만** 분석 (보통 5-15개)
- 5에이전트 × 15종목 = 75 requests → 5분 스로틀링으로 처리 가능

---

## 전체 데이터 플로우

```
Phase 1: DATA
  yfinance (prices + volume) ─────────────┐
  yfinance (fundamentals) ────────────────┤
  Kenneth French FF5 ─────────────────────┤
  Alpaca positions ───────────────────────┤──> market_data{}
  news/fetcher.py:fetch_macro_news_enhanced()  │
    ├── yfinance SPY/VIX news ────────────┤   keys: prices, volumes,
    ├── Reuters RSS ──────────────────────┤        fundamentals, factors,
    ├── AP RSS ───────────────────────────┤        news, indicators[P8],
    ├── CNBC RSS ─────────────────────────┤        polymarket[P9]
    ├── MarketWatch RSS ──────────────────┤
    ├── NYT RSS ──────────────────────────┤
    └── WSJ RSS (description only) ───────┘
  strategies/indicators.py [P8] ──────────> market_data["indicators"]

Phase 1.5: REGIME
  Gemini sentiment (강화된 뉴스) ──────────> news_sentiment_score
  polymarket.py [P9] ────────────────────> polymarket_score
  detect_regime_enhanced(news, poly) ────> RegimeDetection
  regime_allocator.allocate() ───────────> 전략별 자본 배분

Phase 2: SIGNALS (4전략 + indicators 보정)

Phase 2.5: RESEARCH [P10]
  mode=rules: 기존 규칙엔진 (변경 없음)
  mode=gemini: Gemini Flash 5에이전트 병렬 분석 (cron)
  mode=claude: Claude Code 에이전트 풀 분석 (대화형)
  → ResearchVerdict[] → calculate_consensus() → confidence 조정

Phase 3-9: 기존과 동일
```

---

## 비용 요약

| Phase | 새 비용 | 비고 |
|-------|--------|------|
| Phase 7 | $0 | RSS 무료, stdlib |
| Phase 8 | $0 | pandas/numpy만 |
| Phase 9 | $0 | Polymarket 공개 API |
| Phase 10 (cron) | $0 | Gemini Flash 무료 |
| Phase 10 (대화형) | 구독 포함 | Claude Code 토큰 |
| **합계** | **$0** | |

---

## 수정 파일 전체 목록

### 새 파일 (14개)

| 파일 | Phase | 용도 |
|------|-------|------|
| `news/sources/__init__.py` | 7 | 패키지 초기화 |
| `news/sources/base.py` | 7 | NewsSource ABC |
| `news/sources/rss.py` | 7 | 범용 RSS 파서 |
| `news/sources/reuters.py` | 7 | Reuters 어댑터 |
| `news/sources/ap.py` | 7 | AP 어댑터 |
| `news/sources/cnbc.py` | 7 | CNBC 어댑터 |
| `news/sources/marketwatch.py` | 7 | MarketWatch 어댑터 |
| `news/sources/nyt.py` | 7 | NYT 어댑터 |
| `news/sources/wsj.py` | 7 | WSJ 어댑터 |
| `strategies/indicators.py` | 8 | 기술지표 계산 |
| `research/polymarket.py` | 9 | Polymarket API |
| `research/agent_runner.py` | 10 | 하이브리드 LLM 실행 |
| `research/agent_prompts.py` | 10 | 에이전트 시스템 프롬프트 |

### 수정 파일 (9개)

| 파일 | Phase | 변경 내용 |
|------|-------|----------|
| `news/fetcher.py` | 7 | `fetch_rss_news()`, `fetch_macro_news_enhanced()`, body limit 3000 |
| `news/sentiment.py` | 7 | body snippet 200→800, source 필드 추가 |
| `strategies/momentum.py` | 8 | indicators 기반 confidence 보정 (선택) |
| `strategies/leveraged_etf.py` | 8 | RSI overbought 시 confidence 감소 (선택) |
| `research/consensus.py` | 9 | `polymarket_score` 파라미터, 가중치 재배분 |
| `research/models.py` | 9 | RegimeDetection에 polymarket_score 필드 |
| `research/overlay.py` | 10 | `_generate_verdicts` → rules/real 분기 |
| `run_cycle.py` | 7,8,9 | Phase 1/1.5에 새 데이터소스 통합 |
| `requirements.txt` | 10 | `google-genai` 확인 (이미 있음) |

---

## Graceful Degradation 전략

```
Phase 7: RSS 소스 X 실패 → skip, 나머지 계속
         전체 RSS 실패 → yfinance fallback
         body 스크래핑 실패 → RSS description 사용

Phase 8: indicators 계산 실패 → indicators[symbol] = {}, 전략은 기본값 사용
         Volume 없음 → volume_ratio = None

Phase 9: Polymarket API 실패 → score=0.0, 가중치 기존으로 복귀
         빈 응답 → score=0.0

Phase 10: RESEARCH_MODE=rules → 기존 동작 (변경 없음)
          Gemini 개별 에이전트 실패 → 해당 에이전트만 규칙 fallback
          전체 실패 → 5개 모두 규칙엔진 (Phase 1 동일)
          Gemini API 키 없음 → rules 모드로 강제 전환
```

---

## 타이밍 예산 (GH Actions 기준)

| Phase | 추가 시간 |
|-------|----------|
| Phase 7 (RSS + scraping) | +30~45초 (병렬) |
| Phase 8 (indicator 계산) | +10~20초 |
| Phase 9 (Polymarket API) | +3~5초 |
| Phase 10 (Gemini 5에이전트) | +60~120초 (rate limit 스로틀) |
| **합계** | **+100~190초** |

현재 사이클 3-5분 → 강화 후 5-8분. GH Actions 6시간 제한 내 여유.

---

## 검증 방법

### Phase 7 검증
```bash
cd STOCK_WORK
python -c "from news.sources.reuters import ReutersSource; print(ReutersSource().fetch(3))"
python -c "from news.fetcher import fetch_macro_news_enhanced; articles = fetch_macro_news_enhanced(); print(f'{len(articles)} articles from {set(a[\"source\"] for a in articles)}')"
```

### Phase 8 검증
```bash
python -c "
import yfinance as yf
from strategies.indicators import compute_indicators
data = yf.download('AAPL', period='1y')
ind = compute_indicators(data['Close'], data['Volume'])
print(f'RSI={ind[\"rsi\"]:.1f}, MACD={ind[\"macd\"]:.2f}, BB%B={ind[\"bb_pct_b\"]:.2f}')
"
```

### Phase 9 검증
```bash
python -c "
from research.polymarket import fetch_macro_markets, compute_polymarket_score
markets = fetch_macro_markets()
score = compute_polymarket_score(markets)
print(f'{len(markets)} markets, score={score:+.2f}')
for m in markets[:3]: print(f'  {m.question}: {m.probabilities}')
"
```

### Phase 10 검증
```bash
# Gemini 모드
RESEARCH_MODE=gemini python run_cycle.py --phase research --dry-run

# Claude 대화형 모드
# Claude Code에서: /run-cycle --phase research
```

### 통합 검증
```bash
python run_cycle.py --phase all --dry-run
# trade_log.jsonl에 새 사이클 기록 확인
# state/research_cache.json에 verdict 저장 확인
```
