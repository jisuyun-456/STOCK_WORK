# STOCK_WORK 구축 프로세스 — 일일 리포트 + 투자 데이터 플랫폼

> 생성일: 2026-04-03 | 브레인스토밍 확정 사항 기반

---

## 전체 로드맵

```
Phase 1: 일일 리포트 시스템          Phase 2: 투자 데이터 플랫폼
━━━━━━━━━━━━━━━━━━━━━━━━━━━       ━━━━━━━━━━━━━━━━━━━━━━━━━━━
[데이터 수집] → [분석 엔진] →        [FastAPI] → [TimescaleDB] →
[리포트 생성] → [Gmail 전달]          [Next.js] → [차트/대시보드]
         ↓                                    ↑
    docs/reports/ ──────────────────→ 리포트 뷰어로 시각화
```

**진행 순서:** Phase 1 완성 → Phase 2 착수 (리포트 데이터가 DB 설계를 구체화)

---

## Phase 1: 일일 투자 리포트 시스템

### 1.1 확정 사항

| 항목 | 결정 |
|------|------|
| 트리거 | 자동 스케줄(오전 8:30 KST) + 수동(`/report`) |
| 전달 | Gmail MCP(요약본) + `docs/reports/`(상세본) 병행 |
| 데이터 | OpenBB SDK(미국/글로벌) + pykrx(한국) + FRED(매크로) |
| 에이전트 | ST-01(리서치) + ST-02(기술적) + ST-03(매크로) 연동 |

### 1.2 아키텍처

```
┌──────────────── Data Layer ─────────────────┐
│                                              │
│  OpenBB SDK ─────┐                           │
│   (US/Global)    │                           │
│                  │                           │
│  pykrx ──────────┼──→ data_fetcher.py        │
│   (KR Market)    │                           │
│                  │                           │
│  FRED API ───────┘                           │
│                                              │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────── Analysis Layer ──────────────┐
│                                              │
│  market_screener.py  ← 떠오르는 기업 스크리닝   │
│  macro_analyzer.py   ← 매크로 분석 + 섹터 매핑  │
│                                              │
│  + ST 에이전트 (수동 모드 시):                  │
│    ST-01 equity-research                     │
│    ST-02 technical-strategist                │
│    ST-03 macro-economist                     │
│                                              │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────── Report Layer ────────────────┐
│                                              │
│  report_formatter.py + Jinja2 템플릿          │
│    → Markdown (상세본)                        │
│    → HTML (이메일용)                          │
│                                              │
└──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────── Delivery Layer ──────────────┐
│                                              │
│  docs/reports/YYYY-MM-DD-daily.md  (파일)     │
│  Gmail MCP → 이메일 전송           (이메일)    │
│                                              │
└──────────────────────────────────────────────┘
```

### 1.3 리포트 4개 섹션

| # | 섹션 | 분석 내용 | 데이터 소스 |
|---|------|----------|------------|
| **1** | 나스닥/코스피 일일 분석 | 전일 종가, 변동률, 거래량, RSI/MA 위치, 52주 고저 대비 | OpenBB(`^IXIC`), pykrx(KOSPI `1001`) |
| **2** | 글로벌/미국 시장 종합 | S&P500, DJI, VIX, 10Y 국채, DXY, 금/유가, 11개 섹터 등락 | OpenBB(indices, commodities, sectors) |
| **3** | 나스닥 떠오르는 기업 | 거래량 급등 TOP 10, 52주 신고가 종목, 섹터별 모멘텀 상위 | OpenBB screener + volume filter |
| **4** | 매크로 기반 종목 추천 | 현 경기사이클 → 유리한 섹터 → 대표 종목 3~5개 | FRED + ST-03(매크로) + ST-01(리서치) |

### 1.4 데이터 소스 상세

#### OpenBB SDK (미국/글로벌 — 30+소스 통합)
```python
from openbb import obb

# 지수 데이터
nasdaq = obb.equity.price.historical("^IXIC", provider="yfinance")
sp500 = obb.equity.price.historical("^GSPC", provider="yfinance")

# 기술적 지표
rsi = obb.technical.rsi("^IXIC", length=14)
macd = obb.technical.macd("^IXIC")

# 종목 스크리닝
screener = obb.equity.screener(provider="fmp", market_cap_min=1e9)

# VIX, 금, 유가
vix = obb.equity.price.historical("^VIX", provider="yfinance")
gold = obb.equity.price.historical("GC=F", provider="yfinance")
oil = obb.equity.price.historical("CL=F", provider="yfinance")
```

#### pykrx (한국 시장)
```python
from pykrx import stock

# KOSPI 지수
kospi = stock.get_index_ohlcv("20260403", "20260403", "1001")

# 종목별 데이터
samsung = stock.get_market_ohlcv("20260301", "20260403", "005930")

# 전 종목 시가총액
market_cap = stock.get_market_cap("20260403")

# 외국인/기관 순매수
investor = stock.get_market_trading_value_by_investor("20260403", "20260403", "KOSPI")
```

#### FRED (매크로 경제지표)
```python
from fredapi import Fred

fred = Fred(api_key="YOUR_KEY")
fed_rate = fred.get_series("FEDFUNDS")      # 기준금리
cpi = fred.get_series("CPIAUCSL")           # 소비자물가
unemployment = fred.get_series("UNRATE")     # 실업률
gdp = fred.get_series("GDP")               # GDP
treasury_10y = fred.get_series("GS10")      # 10년 국채
dxy = fred.get_series("DTWEXBGS")           # 달러 인덱스
```

### 1.5 파일 구조

```
STOCK_WORK/
├── scripts/
│   ├── daily_report.py          # 메인 오케스트레이터
│   │   - CLI: --mode auto|manual
│   │   - auto: 데이터 수집 → 분석 → 포맷 → Gmail+파일
│   │   - manual: + ST 에이전트 호출로 품질 향상
│   │
│   ├── data_fetcher.py          # 데이터 수집 모듈
│   │   - fetch_us_indices()     # 미국 지수
│   │   - fetch_kr_indices()     # 한국 지수
│   │   - fetch_macro()          # 매크로 지표
│   │   - fetch_commodities()    # 원자재
│   │
│   ├── market_screener.py       # 스크리닝 로직
│   │   - volume_surge()         # 거래량 급등
│   │   - new_highs()            # 52주 신고가
│   │   - sector_momentum()      # 섹터별 모멘텀
│   │
│   ├── macro_analyzer.py        # 매크로 분석
│   │   - current_cycle()        # 현재 경기사이클 위치
│   │   - favored_sectors()      # 유리한 섹터 매핑
│   │   - recommend_stocks()     # 섹터 대표 종목
│   │
│   └── report_formatter.py      # 포맷터
│       - to_markdown()          # Jinja2 → Markdown
│       - to_html()              # Jinja2 → HTML (이메일)
│       - save_report()          # docs/reports/ 저장
│
├── templates/
│   ├── daily_report.md.j2       # Markdown 리포트 템플릿
│   └── email_template.html      # Gmail HTML 템플릿
│
├── docs/reports/                 # 리포트 아카이브
│   └── 2026-04-03-daily.md      # (예시)
│
├── .claude/skills/
│   └── daily-report.md          # /report 스킬 정의
│
├── .env                          # FRED_API_KEY 등 (git 제외)
└── requirements.txt              # openbb, pykrx, pandas, jinja2, fredapi
```

### 1.6 실행 모드

#### 자동 모드 (CronCreate)
```
시간: 매일 08:30 KST (UTC 23:30)
cron: 30 23 * * *
명령: python3 scripts/daily_report.py --mode auto

프로세스:
  1. data_fetcher.py → 전 시장 데이터 수집
  2. market_screener.py → 떠오르는 기업 필터링
  3. macro_analyzer.py → 매크로 기반 종목 추천
  4. report_formatter.py → Markdown + HTML 생성
  5. docs/reports/YYYY-MM-DD-daily.md 저장
  6. Gmail MCP → 요약본 이메일 전송

한계: Claude Code 세션이 열려 있어야 작동
대안: GitHub Actions 워크플로우로 외부 스케줄링
```

#### 수동 모드 (`/report` 스킬)
```
트리거: /report 또는 "오늘 리포트", "시장 분석"

프로세스:
  1. scripts/daily_report.py --mode manual 실행
  2. ST-01(리서치) + ST-02(기술적) + ST-03(매크로) 에이전트 호출
  3. 에이전트 분석 결과를 리포트에 통합 (자동보다 더 깊은 분석)
  4. 터미널에 상세 분석 출력
  5. docs/reports/ 저장
  6. Gmail 전송 (사용자 선택)
```

### 1.7 Gmail MCP 연동

```
Step 1: mcp__claude_ai_Gmail__authenticate 호출 → OAuth 인증
Step 2: 인증 완료 후 send_email 도구 활성화
Step 3: email_template.html로 시각적 이메일 생성
Step 4: 매일 자동 전송 (auto 모드) 또는 요청 시 전송 (manual 모드)
```

### 1.8 구현 순서 (11단계)

```
 1. [환경 설정]     requirements.txt + pip install + .env 설정
 2. [데이터 수집]    data_fetcher.py — OpenBB/pykrx/FRED 모듈
 3. [스크리닝]      market_screener.py — 떠오르는 기업 로직
 4. [매크로 분석]    macro_analyzer.py — 경기사이클→섹터→종목
 5. [포맷터]        report_formatter.py — Jinja2 Markdown/HTML
 6. [템플릿]        templates/ — 리포트 + 이메일 템플릿
 7. [메인 스크립트]   daily_report.py — 오케스트레이터
 8. [Gmail 인증]     mcp__claude_ai_Gmail__authenticate
 9. [스킬 등록]      .claude/skills/daily-report.md
10. [스케줄 설정]    CronCreate (매일 08:30 KST)
11. [테스트]        수동 + 자동 모두 검증
```

---

## Phase 2: 투자 데이터 관리 플랫폼 (Phase 1 완료 후)

### 2.1 확정 기술 스택

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vercel)                      │
│                                                          │
│   Next.js 15 (App Router)                                │
│   ├── Server Components (학습: React 최신 패턴)           │
│   ├── Streaming SSR (성능: 점진적 렌더링)                 │
│   └── Apache ECharts / TradingView Lightweight (차트)     │
│                                                          │
├──────────────────────┬───────────────────────────────────┤
│                      │                                    │
│   REST API           │   WebSocket                        │
│   (CRUD, 분석)        │   (실시간 주가 푸시)                │
│                      │                                    │
├──────────────────────┴───────────────────────────────────┤
│                    Backend (Railway)                       │
│                                                          │
│   FastAPI (Python)                                        │
│   ├── REST endpoints (포트폴리오/종목/리포트)               │
│   ├── WebSocket server (실시간 데이터)                     │
│   ├── OpenBB/pykrx 직접 통합 (데이터 파이프라인)            │
│   └── Background tasks (데이터 수집 스케줄러)               │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    Database (Railway)                      │
│                                                          │
│   TimescaleDB (Postgres + 시계열 확장)                     │
│   ├── hypertable: stock_prices (OHLCV 시계열)             │
│   ├── continuous aggregate: daily_summary                 │
│   ├── table: portfolios, trades, positions                │
│   └── table: daily_reports (Phase 1 리포트 저장)           │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    Cache (Upstash Redis)                   │
│                                                          │
│   실시간 주가 캐싱 (TTL: 1분)                              │
│   세션 관리                                                │
│   Rate limiting                                           │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2.2 학습 가치

| 기술 | 새로움 | 학습 포인트 |
|------|--------|------------|
| **FastAPI** | 새 프레임워크 | Python async, type hints, Pydantic, dependency injection |
| **TimescaleDB** | 새 DB | 시계열 최적화, hypertable, continuous aggregate, compression |
| **Next.js 15 App Router** | 새 패턴 | React Server Components, Streaming SSR, Server Actions |
| **Apache ECharts** | 새 차트 | 캔들스틱, 볼린저, MACD, 커스텀 금융 차트 |
| **WebSocket** | 새 통신 | 실시간 양방향, FastAPI WebSocket, 클라이언트 재연결 |
| **Redis** | 새 캐시 | Upstash serverless Redis, TTL 전략, pub/sub |

### 2.3 핵심 기능 (5개 페이지)

| 페이지 | 기능 | 차트/시각화 |
|--------|------|-----------|
| **포트폴리오 대시보드** | 보유 종목, 총수익률, 섹터 분포, 일별 PnL | 파이차트(섹터), 라인(수익률) |
| **종목 분석** | OHLCV 차트 + 재무 + 기술적 지표 + 밸류에이션 | 캔들스틱, RSI, MACD, 볼린저 |
| **매매 기록 원장** | INSERT ONLY 거래 이력, 평단가, 실현손익 | 테이블 + 필터 |
| **일일 리포트 뷰어** | Phase 1 리포트를 웹으로 시각화 | 리포트 카드 + 차트 |
| **리스크 대시보드** | VaR, MDD, 섹터 노출도, 상관관계 매트릭스 | 히트맵, 게이지 |

### 2.4 DB 스키마 개요 (TimescaleDB)

```sql
-- 시계열 (hypertable)
CREATE TABLE stock_prices (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      BIGINT,
    market      TEXT  -- 'US' | 'KR'
);
SELECT create_hypertable('stock_prices', 'time');

-- 연속 집계 (자동 일/주/월 요약)
CREATE MATERIALIZED VIEW daily_ohlcv
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS day,
       symbol, market,
       first(open, time), max(high), min(low), last(close, time),
       sum(volume)
FROM stock_prices
GROUP BY day, symbol, market;

-- 포트폴리오
CREATE TABLE portfolios (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 매매 기록 (INSERT ONLY — Immutable Ledger)
CREATE TABLE trades (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID REFERENCES portfolios(id),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,  -- 'BUY' | 'SELL'
    quantity    NUMERIC NOT NULL,
    price       NUMERIC NOT NULL,
    fee         NUMERIC DEFAULT 0,
    currency    TEXT DEFAULT 'KRW',
    executed_at TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    note        TEXT
);
-- DELETE/UPDATE 금지 (트리거로 강제)

-- 일일 리포트 저장
CREATE TABLE daily_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date DATE UNIQUE NOT NULL,
    content_md  TEXT NOT NULL,
    content_html TEXT,
    summary     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.5 배포 구조

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Vercel     │     │  Railway     │     │  Upstash     │
│  (프론트)    │────→│  (백엔드+DB) │────→│  (Redis)     │
│  Next.js 15  │     │  FastAPI     │     │  캐시/실시간  │
│  무료 티어    │     │  TimescaleDB │     │  무료 티어    │
│              │     │  무료 티어    │     │              │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 2.6 구현 순서 (Phase 1 완료 후)

```
 1. [DB 설계]       TimescaleDB 스키마 + 마이그레이션
 2. [백엔드 기반]    FastAPI 프로젝트 초기화 + 기본 CRUD
 3. [데이터 파이프]   OpenBB → TimescaleDB 수집 파이프라인
 4. [API 완성]      REST endpoints + WebSocket
 5. [프론트 기반]    Next.js 15 프로젝트 초기화
 6. [대시보드]       포트폴리오 + 리스크 페이지
 7. [종목 분석]      캔들스틱 차트 + 기술적 지표
 8. [리포트 뷰어]    Phase 1 리포트 연동
 9. [배포]          Railway + Vercel + Upstash
10. [테스트]        E2E 검증
```

---

## Phase 1 ↔ Phase 2 연결점

```
Phase 1 (리포트 시스템)
│
├── scripts/data_fetcher.py  ──→  Phase 2에서 FastAPI 서비스로 승격
├── docs/reports/*.md        ──→  daily_reports 테이블에 저장
├── market_screener.py       ──→  /api/screener 엔드포인트로 변환
└── macro_analyzer.py        ──→  /api/macro 엔드포인트로 변환
```

Phase 1의 Python 스크립트들이 Phase 2의 FastAPI 서비스 모듈로 자연스럽게 승격되므로, 코드 재작성 없이 진화 가능.

---

## 타임라인 (예상)

| Phase | 기간 | 산출물 |
|-------|------|--------|
| **Phase 1** | 1~2주 | 일일 리포트 시스템 (Python + Gmail) |
| **Phase 2-1** | 2~3주 | FastAPI + TimescaleDB 백엔드 |
| **Phase 2-2** | 2~3주 | Next.js 프론트엔드 + 차트 |
| **Phase 2-3** | 1주 | 배포 + 테스트 |

**총 예상: 6~9주** (개인 프로젝트 기준)
