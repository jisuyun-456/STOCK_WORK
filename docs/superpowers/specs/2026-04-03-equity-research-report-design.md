# Equity Research Report System — Design Spec

## Overview

글로벌 IB(GS/JPM/MS) 수준의 8챕터 Equity Research Report 자동 생성 시스템.
`/analyze PLTR` 또는 "PLTR 분석해줘"로 트리거 → 데이터 수집 → 에이전트 팀 분석 → HTML(다크) + PDF(크림) 출력.

**기존 daily_report.py(데일리 리포트)와 완전 별개 시스템.** 리포트는 매일 자동, 보고서는 온디맨드.

---

## 설계 결정

| 항목 | 결정 | 근거 |
|------|------|------|
| 대상 | 포트폴리오 5종목 + 워치리스트 무제한 | 어떤 미국/한국 종목이든 분석 가능 |
| 데이터 깊이 | 에이전트 팀 풀 연동 | ST-01~08 + D6/D7 2계층 분석 |
| 실행 방식 | `/analyze` 커맨드 + 자연어 스킬 | 진입점 2개로 편의성 극대화 |
| 디자인 | Hybrid (HTML=다크, PDF=크림) | 화면은 터미널 톤, 인쇄는 에디토리얼 톤 |
| 아키텍처 | 단일 파이프라인 (Approach A) | daily_report.py 패턴 재활용, 단순 유지보수 |
| 8챕터 | GS/JPM/MS 표준 구조 그대로 | 추후 챕터 추가/수정 가능 |

---

## 시스템 아키텍처

### 파이프라인 흐름

```
/analyze {SYMBOL}
  │
  ├── Phase 1: Data Collection (병렬)
  │   ├── Yahoo Finance MCP — ticker_info, financials, earnings, holders, price_history
  │   ├── FMP API — DCF, key_metrics, income_statement 5Y, balance_sheet
  │   ├── yfinance — RSI, MACD, MA50/200, volume, 52w range, sector ETF comps
  │   └── WebSearch — 최신 뉴스, IR 자료, 경쟁사 동향
  │
  ├── Phase 2: Agent Analysis (Tier 1 → Tier 2)
  │   ├── Tier 1 병렬
  │   │   ├── ST-01 equity-research → CH1(Summary), CH3(Financials), CH4(Valuation)
  │   │   ├── ST-02 technical-strategist → CH7.4(기술적 분석)
  │   │   ├── ST-03 macro-economist → CH7.1~3(섹터, 매크로, 기관)
  │   │   └── ST-07 market-intelligence → CH5(Catalysts), CH6(Risks)
  │   │
  │   └── Tier 2 검토
  │       ├── D6 investment-expert → CH1, CH4, CH8 최종 검토
  │       ├── D7 economics-expert → CH7 이론 프레임 검증
  │       └── orchestrator → 전체 통합 + CH8 결론
  │
  └── Phase 3: Render
      ├── context → Jinja2 → equity_report.html (다크 테마, 인터랙티브)
      ├── context → Jinja2 → equity_report_pdf.html → WeasyPrint → PDF (크림 테마)
      └── context → JSON 저장 (업데이트/비교용)
```

### 신규 파일

| 파일 | 역할 |
|------|------|
| `scripts/equity_report_generator.py` | 메인 오케스트레이터 — 3단계 파이프라인 실행 |
| `templates/equity_report.html` | 다크 테마 8챕터 Jinja2 (탭 전환 + Chart.js) |
| `templates/equity_report_pdf.html` | 크림 테마 PDF용 Jinja2 (WeasyPrint) |
| `.claude/commands/analyze.md` | `/analyze {SYMBOL}` 슬래시 커맨드 |
| `.claude/skills/equity-research-report.md` | 자연어 트리거 스킬 |

### 기존 재활용 파일

| 파일 | 재활용 부분 |
|------|-----------|
| `scripts/stock_analyzer.py` | `fetch_technical()`, `fetch_fundamental()`, `fetch_institutional()`, `STOCK_THESIS` |
| `scripts/data_fetcher.py` | `fetch_sector_performance()`, `fetch_commodities()` |
| `scripts/macro_analyzer.py` | `current_cycle()`, `favored_sectors()` |
| `scripts/fmp_rate_limiter.py` | FMP API 쿼터 관리 |
| `scripts/pdf_generator.py` | WeasyPrint 변환 로직 참고 |

---

## 8챕터 구조 & Context Dict

### CH1: Executive Summary
**목적:** 1페이지에 전체 투자 논거 압축. PM은 여기만 읽고 투자 결정.

```python
"ch1": {
    "rating": "BUY",                    # BUY / HOLD / SELL
    "conviction": "HIGH",               # HIGH / MEDIUM / LOW
    "target_price": 125.00,             # 12개월 목표가
    "current_price": 148.46,
    "upside_pct": -15.8,
    "investment_thesis": "...",          # 3줄 이내 핵심 논거
    "key_metrics": {
        "market_cap": 87.4e9,
        "fwd_pe": 72.0,
        "ev_ebitda": 55.0,
        "revenue_growth": 0.33,
        "gross_margin": 0.76,
        "fcf_yield": 0.028
    },
    "scenarios": {
        "bull":  {"price": 420, "prob": 35, "note": "..."},
        "base":  {"price": 370, "prob": 45, "note": "..."},
        "bear":  {"price": 280, "prob": 20, "note": "..."}
    }
}
```

### CH2: Business Overview
**목적:** 무엇을 하는 회사인가. 사업모델 + 경쟁 구도 + 시장 규모.

```python
"ch2": {
    "business_model": "...",                              # 사업모델 설명
    "revenue_segments": [{"name": "Government", "pct": 55, "yoy": 30}, ...],
    "geographic_mix": [{"region": "North America", "pct": 67}, ...],
    "competitors": [{"name": "Snowflake", "mkt_cap": 50e9, "growth": 25, "margin": 10}, ...],
    "tam_sam_som": {"tam": 150e9, "sam": 45e9, "som": 3.5e9, "share_pct": 7.8}
}
```

### CH3: Financial Analysis
**목적:** 숫자로 보는 건강 상태. 5개년 재무 + FCF + 마진 추세.

```python
"ch3": {
    "income_stmt": [                    # 실적 3Y + 추정 2Y
        {"year": "FY24A", "revenue": 2.2e9, "gp": 1.7e9, "ebitda": 800e6,
         "ebit": 600e6, "ni": 450e6, "eps": 0.19},
        ...
    ],
    "balance_sheet": {
        "total_assets": 5.2e9, "debt_ratio": 0.15,
        "net_cash": 3.8e9, "roic": 12.5, "roe": 18.3
    },
    "cash_flow": [
        {"year": "FY24A", "ocf": 900e6, "capex": 150e6, "fcf": 750e6, "fcf_margin": 34.1},
        ...
    ],
    "margins": [
        {"year": "FY24A", "gross_m": 81.0, "ebitda_m": 36.4, "net_m": 20.5},
        ...
    ]
}
```

### CH4: Valuation
**목적:** 지금 비싼가 싼가. DCF + Comps + 역사적 밸류에이션.

```python
"ch4": {
    "dcf": {
        "wacc": 10.5, "tgr": 3.0, "fair_value": 95.0,
        "sensitivity_matrix": [[...]]   # WACC(rows) × TGR(cols) 5×5
    },
    "comps": [                          # Peer 5개사
        {"name": "Snowflake", "pe": 85, "ev_ebitda": 60, "ev_rev": 18, "p_fcf": 55},
        ...
    ],
    "historical_val": [                 # 3년 월별 P/E 밴드
        {"date": "2024-01", "pe": 65, "avg": 58, "std_up": 72, "std_dn": 44},
        ...
    ],
    "target_method": "DCF 50% + Comps 50%"
}
```

### CH5: Growth Catalysts
**목적:** 왜 오를 수 있는가. 단기 이벤트 + 중장기 테마.

```python
"ch5": {
    "short_term": [                     # 0-6개월
        {"event": "Q1 실적 발표", "date": "2026-05-06", "expectation": "ARR 가이던스 상향 기대"},
        ...
    ],
    "mid_term": [                       # 1-3년
        {"theme": "AI 플랫폼 확장", "description": "...", "impact": "매출 +40% 가속 가능"},
        ...
    ],
    "margin_leverage": [
        {"point": "클라우드 마이그레이션", "current": "36%", "potential": "45%"},
        ...
    ],
    "capital_allocation": {
        "dividend_yield": 0, "buyback_yield": 1.2, "ma_strategy": "Bolt-on acquisitions"
    }
}
```

### CH6: Risk Factors
**목적:** 왜 틀릴 수 있는가. 각 리스크 → Bear Case 가격 연결.

```python
"ch6": {
    "business_risk": [
        {"title": "정부 의존도", "desc": "...", "prob": "중간", "impact": "높음", "bear_price": 80},
        ...
    ],
    "financial_risk": [...],
    "regulatory_risk": [...],
    "macro_risk": [...]
}
```

### CH7: Industry & Macro Context
**목적:** 배경 환경. 섹터 퍼포먼스 + 매크로 + 기관 포지션 + 기술적 분석.

```python
"ch7": {
    "sector_performance": {"vs_sp500_12m": 15.3, "vs_nasdaq_12m": 8.2, "sector_rank": 2},
    "macro_sensitivity": {"rate_impact": "중간", "cycle_position": "Expansion", "beta": 1.8},
    "institutional": {
        "top_holders": [{"name": "Vanguard", "pct": 8.2, "change": "+0.3%"}, ...],
        "insider_activity": {"buys_30d": 2, "sells_30d": 5, "net": "순매도"},
        "short_interest": 3.2
    },
    "technical": {
        "support": [140, 128], "resistance": [155, 170],
        "rsi": 58, "macd": "bullish_crossover",
        "ma50": 142.5, "ma200": 118.3, "above_ma50": True, "above_ma200": True
    }
}
```

### CH8: Investment Conclusion
**목적:** 최종 판단 + 실행 계획. CH1의 mirror.

```python
"ch8": {
    "final_rating": "BUY",
    "trade_setup": {
        "entry_zone": [140, 148],
        "target1": 170,                # Base Case, 50% 청산
        "target2": 200,                # Bull Case
        "stop_loss": 125,              # 구조적 지지 하단
        "rr_ratio": 2.7
    },
    "monitoring": [                     # 5개 KPI + 임계치
        {"kpi": "분기 ARR 성장률", "threshold": "<25%", "action": "HOLD 하향 검토"},
        {"kpi": "FCF Margin", "threshold": "<20%", "action": "수익성 점검"},
        {"kpi": "정부 매출 비중", "threshold": ">70%", "action": "집중도 리스크 경고"},
        {"kpi": "주가 vs Stop", "threshold": "<$125", "action": "손절 실행"},
        {"kpi": "NRR", "threshold": "<110%", "action": "성장 둔화 경고"}
    ],
    "next_update": {"trigger": "Q1 실적 발표", "date": "2026-05-06", "event": "ARR/마진 가이던스"}
}
```

---

## 디자인 테마

### HTML (Dark Terminal)
- 기존 `trading_dashboard.html`과 동일 톤
- `--bg: #0d0f14`, `--text: #e2e8f0`, 모노스페이스 폰트
- 8개 탭 버튼으로 챕터 전환 (JS onclick → display toggle)
- Chart.js: 콤보(매출+마진), 히트맵(DCF 민감도), 워터폴(FCF), 버블(경쟁사), 밴드(역사적 P/E)
- 접이식 리스크 매트릭스, 시나리오 카드

### PDF (Cream Editorial)
- 첨부 `equity-research-template.html` 톤
- `--cream: #FAF8F4`, Libre Baskerville 세리프, 코랄 `#C8523A` 악센트
- WeasyPrint 변환, 인쇄 최적화 (A4, 페이지 나눔)
- 차트는 정적 SVG 또는 테이블로 대체

---

## 커맨드 & 스킬

### `/analyze` 커맨드 (`.claude/commands/analyze.md`)
```markdown
# /analyze — Equity Research Report 생성

## Usage
/analyze {SYMBOL}

## Process
1. Phase 1: 데이터 수집 (Yahoo Finance MCP + FMP + yfinance + WebSearch)
2. Phase 2: 에이전트 분석 (ST-01, ST-02, ST-03, ST-07 → D6, D7 검토)
3. Phase 3: 렌더링 (HTML 다크 + PDF 크림 + JSON)
4. 출력: docs/reports/equity/{SYMBOL}-{DATE}.html/pdf/json
```

### 자연어 스킬 (`.claude/skills/equity-research-report.md`)
트리거 키워드: "분석해줘", "보고서 작성", "리서치 리포트", "equity research"
→ 동일 파이프라인 실행

---

## 제약 조건

- FMP API: 일일 250콜 한도 준수 (`fmp_rate_limiter.py` 연동)
- 보고서 1건당 FMP 예상 소비: ~30콜 (재무제표 5Y + DCF + key_metrics + comps)
- 에이전트 호출은 Claude Code 세션 내에서만 가능 (GitHub Actions 불가)
- 한국 종목 지원: yfinance 기본 데이터만 (DART 연동은 추후)

---

## 향후 확장 (V2)

- 분기 실적 발표 시 자동 업데이트 트리거
- 이전 보고서 JSON과 비교 → 변경 하이라이트
- 한국 종목 DART 공시 연동
- 챕터 추가/수정 (사용자 요청에 따라)
