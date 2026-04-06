---
name: analyze
description: >
  GS/JPM 수준 8챕터 Equity Research Report 생성.
  "{종목명} 분석해줘", "{티커} 보고서", "리서치 리포트" 요청 시 자동 트리거.
---

# /analyze {SYMBOL} — Equity Research Report

## 언제 사용
- "{종목명} 분석해줘"
- "{티커} 보고서 작성해줘"
- "{symbol} equity research"
- "리서치 리포트"

## Step 1: 심볼 확인
요청에서 종목 심볼(티커) 추출. 불명확하면 사용자에게 확인.

## Step 2: 데이터 수집 (Yahoo Finance MCP 병렬)

아래 MCP 도구를 병렬 호출하여 데이터 수집:
- `mcp__yahoo-finance__get_ticker_info` (symbol)
- `mcp__yahoo-finance__get_financials` (symbol, statement=income, period=yearly)
- `mcp__yahoo-finance__get_financials` (symbol, statement=balance, period=yearly)
- `mcp__yahoo-finance__get_financials` (symbol, statement=cashflow, period=yearly)
- `mcp__yahoo-finance__get_earnings` (symbol)
- `mcp__yahoo-finance__get_holders` (symbol, holder_type=institutional)
- `mcp__yahoo-finance__get_price_history` (symbol, period=1y, interval=1wk)
- `mcp__yahoo-finance__get_analyst_data` (symbol, data_type=price_targets)

## Step 3: 풀 prose context JSON 생성

수집한 데이터를 기반으로 **equity-research-guide.md** 기준에 맞는 8챕터 prose를 직접 작성.
`docs/reports/equity/{SYMBOL}-context.json` 파일로 저장.

JSON 구조는 아래 스키마를 따른다:

```json
{
  "symbol": "PLTR",
  "company_name": "Palantir Technologies Inc.",
  "exchange": "NASDAQ",
  "sector": "Technology",
  "industry": "Software - Infrastructure",
  "report_date": "2026-04-06",
  "current_price": 148.46,
  "target_price": 175.0,
  "rating": "HOLD",
  "conviction": "MEDIUM",
  "market_cap": "$355B",
  "forward_pe": "79.8x",
  "ev_ebitda": "241.8x",
  "revenue_growth": "+56.2%",
  "gross_margin": "82.4%",
  "fcf_yield": "0.4%",

  "ch1": {
    "thesis": "5-7문장 투자 논거. 결론 먼저.",
    "investment_thesis": "1줄 요약",
    "thesis_points": ["포인트1", "포인트2", "포인트3"],
    "scenarios": {
      "bull": {"price": 250, "probability": 30, "note": "설명"},
      "base": {"price": 175, "probability": 45, "note": "설명"},
      "bear": {"price": 90, "probability": 25, "note": "설명"}
    }
  },
  "ch2": {
    "platform_overview": "사업 모델 상세 5-7문장",
    "business_model": "1줄 요약",
    "platforms": [
      {"name": "제품명", "target": "대상", "description": "3-4문장"}
    ],
    "competitors_commentary": "경쟁 분석 3-5문장"
  },
  "ch3": {
    "income_commentary": "손익 분석 5-7문장",
    "sbc_analysis": "SBC 분석 3-5문장",
    "cashflow_commentary": "현금흐름 3-5문장",
    "income_stmt": [
      {"year": "FY2023", "revenue": 2225, "revenue_growth": 17, "gross_margin": 82, "op_margin": 5, "net_income": 210}
    ]
  },
  "ch4": {
    "dcf_commentary": "DCF 분석 3-5문장",
    "comps_commentary": "Comps 분석 3-5문장",
    "dcf": {"wacc": 10.5, "tgr": 4.0, "fair_value": 155},
    "comps": [
      {"ticker": "SNOW", "ev_rev": "13x", "pe_fwd": "145x", "growth": "+28%"}
    ]
  },
  "ch5": {
    "short_term": [
      {"timing": "시기", "title": "이벤트", "description": "설명", "importance": "HIGH"}
    ],
    "mid_term": [
      {"theme_name": "테마", "description": "설명"}
    ],
    "long_term_thesis": "장기 비전 설명"
  },
  "ch6": {
    "risks": [
      {"category": "Business", "title": "리스크명", "description": "3-5문장", "probability": "중간", "impact": "높음", "bear_price": 90}
    ]
  },
  "ch7": {
    "macro_commentary": "산업+매크로 5-7문장",
    "technical_commentary": "기술적 분석 3-5문장",
    "technical": {"rsi_14": 47.9, "ma50": 146.9, "ma200": 164.2, "macd_signal": "하락"}
  },
  "ch8": {
    "conclusion": "투자 결론 5-7문장",
    "trade_setup": {"entry_zone": "$130-$140", "target1": 165, "target2": 175, "stop_loss": 125},
    "kpis": [
      {"metric": "KPI명", "threshold": "기준", "action": "행동"}
    ]
  }
}
```

## Step 4: Git commit + push

```bash
git add docs/reports/equity/{SYMBOL}-context.json
git commit -m "data: {SYMBOL} equity research context"
git push
```

## Step 5: GitHub Actions 트리거

```bash
"/c/Program Files/GitHub CLI/gh.exe" workflow run equity-report.yml -f symbol={SYMBOL}
```

Actions가 context.json을 읽어 HTML/PDF 렌더링 → 이메일 발송.

## Step 6: 결과 안내

사용자에게:
1. 핵심 분석 요약 (Rating + 목표가 + 핵심 논거) — 대화 내 즉시
2. "풀 리서치 PDF는 메일로 발송됩니다" — 1~2분 후 도착
