# /analyze — Equity Research Report 생성 (v1 스키마)

$ARGUMENTS: symbol

GS/JPM 수준 8챕터 논문형 Equity Research Report를 생성합니다.
**반드시 `.claude/skills/equity-research-guide.md` 작성 가이드를 준수하십시오.**

---

## Step 1: 데이터 수집 (병렬 MCP 호출)

아래 Yahoo Finance MCP 도구를 동시에 호출하세요:
- `mcp__yahoo-finance__get_ticker_info` (symbol=$symbol)
- `mcp__yahoo-finance__get_financials` (symbol=$symbol, frequency=annual)
- `mcp__yahoo-finance__get_earnings` (symbol=$symbol)
- `mcp__yahoo-finance__get_holders` (symbol=$symbol)
- `mcp__yahoo-finance__get_price_history` (symbol=$symbol, period=1y, interval=1mo)
- `mcp__yahoo-finance__get_analyst_data` (symbol=$symbol)

SPY/QQQ 성과 비교용 (Exhibit 3):
- `mcp__yahoo-finance__get_price_history` (symbol=SPY, period=1y, interval=1mo)
- `mcp__yahoo-finance__get_price_history` (symbol=QQQ, period=1y, interval=1mo)

Python 기술·펀더멘털 분석:
```bash
cd scripts && python -c "
from stock_analyzer import fetch_technical, fetch_fundamental, fetch_institutional
import json
tech = fetch_technical('$symbol')
fund = fetch_fundamental('$symbol')
inst = fetch_institutional('$symbol')
print(json.dumps({'technical': tech, 'fundamental': fund, 'institutional': inst}, default=str))
"
```

---

## Step 2: v1 스키마 context dict 작성

수집된 데이터를 바탕으로 8챕터 context dict를 **한국어 prose**로 작성하십시오.
**GS/JPM Inverted Pyramid**: 첫 문장에 Rating + Target + 논거를 명시.

### CH1: Executive Summary
```python
"ch1": {
    "rating": "BUY|HOLD|SELL",
    "conviction": "HIGH|MEDIUM|LOW",
    "target_price": float,
    "current_price": float,
    "upside_pct": float,
    "investment_thesis": "3줄 요약 (legacy)",
    "thesis": "200자+ 한국어. 첫 문장: '{symbol}에 대해 {RATING}을 유지한다. 12개월 목표가 ${target}.' 이후 핵심 드라이버·밸류에이션 근거·리스크 요약",
    "thesis_points": ["핵심 논거 1 (수치 포함)", "논거 2", "논거 3"],
    "key_metrics": {"market_cap": float, "fwd_pe": float, "ev_ebitda": float,
                    "revenue_growth": float, "gross_margin": float, "fcf_yield": float},
    "scenarios": {
        "bull":  {"price": float, "prob": int, "note": "100자+ 시나리오"},
        "base":  {"price": float, "prob": int, "note": "100자+ 시나리오"},
        "bear":  {"price": float, "prob": int, "note": "100자+ 시나리오"},
    }
}
```

### CH2: Business Overview
```python
"ch2": {
    "business_model": "150자+ 비즈니스 모델",
    "platform_overview": "200자+ 플랫폼 아키텍처 (Gotham→Foundry→AIP 등)",
    "platforms": [
        {"name": "Gotham", "description": "150자+", "revenue_contribution": "55%"},
    ],
    "revenue_segments": [{"name": str, "pct": float, "yoy": float}],
    "geographic_mix": [{"region": str, "pct": float}],
    "competitors": [
        {"name": str, "mkt_cap": float, "revenue_growth": float,
         "gross_margin": float, "ev_revenue": float, "commentary": "100자+"}
    ],
    "tam_sam_som": {"tam": float, "sam": float, "som": float, "share_pct": float}
}
```

### CH3: Financial Analysis
```python
"ch3": {
    "income_stmt": [{"year": "FY24A", "revenue": float, "gp": float,
                     "ebitda": float, "ebit": float, "ni": float, "eps": float}],
    "income_commentary": "100자+",
    "revenue_breakdown": [        # Exhibit 1 (Government vs Commercial)
        {"year": "FY21A", "gov_rev": float, "com_rev": float}
    ],
    "balance_sheet": {"total_assets": float, "debt_ratio": float,
                      "net_cash": float, "roic": float, "roe": float},
    "cash_flow": [{"year": str, "ocf": float, "capex": float,
                   "fcf": float, "fcf_margin": float}],
    "margins": [{"year": str, "gross_m": float, "ebitda_m": float, "net_m": float}],
    "sbc_analysis": "150자+ SBC 규모·희석 효과 분석 (수치 필수)"
}
```

### CH4: Valuation
```python
"ch4": {
    "dcf": {
        "wacc": float, "tgr": float, "fair_value": float,
        "labels_wacc": ["8%","9%","10%","11%","12%","13%"],
        "labels_tgr":  ["1.5%","2%","2.5%","3%","3.5%"],
        "matrix": [[float×5]×6]   # 6×5 매트릭스
    },
    "dcf_commentary": "150자+ WACC 가정 근거 및 적정가 해석",
    "comps": [{"name": str, "pe": float, "ev_ebitda": float,
               "ev_rev": float, "p_fcf": float}],
    "comps_self": {"pe": float, "ev_ebitda": float, "psr": float},
    "comps_commentary": "150자+ Peer 대비 premium/discount 근거",
    "target_method": "DCF 50% + Comps 50%"
}
```

### CH5: Growth Catalysts
```python
"ch5": {
    "short_term": [{"event": str, "date": "YYYY-MM-DD", "expectation": "100자+"}],
    "mid_term":   [{"theme": str, "description": "100자+", "impact": "수치 영향"}],
    "long_term_thesis": "150자+"
}
```

### CH6: Risk Factors
```python
"ch6": {
    "risks": [
        {"tier": "High|Medium|Low", "title": str,
         "category": "Business|Financial|Regulatory|Macro",
         "probability": "높음|중간|낮음", "impact": "높음|중간|낮음",
         "description": "150자+ (수치 포함)", "bear_price": float}
    ]
}
```

### CH7: Industry & Macro
```python
"ch7": {
    "sector_performance": {"vs_sp500_12m": float, "vs_nasdaq_12m": float},
    "perf_chart_data": [         # Exhibit 3: 12개월 월별 누적수익률 (기준 0%)
        {"date": "2025-04", "ticker_pct": float, "spy_pct": float, "qqq_pct": float}
    ],  # 계산: (월가격 / 첫달가격 - 1) * 100  — 첫 달은 모두 0.0
    "macro_commentary": "200자+ 섹터·매크로·기관 포지션 종합",
    "macro_sensitivity": {"rate_impact": str, "cycle_position": str, "beta": float},
    "institutional": {
        "top_holders": [{"name": str, "shares": str, "change": str}],
        "insider_activity": {"buys_30d": int, "sells_30d": int},
        "short_interest": float
    },
    "technical": {
        "rsi": float, "macd": str, "ma50": float, "ma200": float,
        "above_ma50": bool, "above_ma200": bool,
        "pct_from_high": float, "high_52w": float, "low_52w": float,
        "support": [float, float], "resistance": [float]
    }
}
```

### CH8: Investment Conclusion
```python
"ch8": {
    "final_rating": "BUY|HOLD|SELL",
    "trade_setup": {
        "entry_zone": [float, float], "target1": float,
        "target2": float, "stop_loss": float, "rr_ratio": float
    },
    "kpis": [                    # 5개 KPI
        {"metric": str, "threshold": str, "current": str,
         "signal": "정상|경고|위험", "action": str}
    ],
    "conclusion": "200자+ 최종 결론. Rating 재확인 + 핵심 논거 + 실행 계획",
    "next_update": {"trigger": str, "date": "YYYY-MM-DD", "event": str}
}
```

---

## Step 3: 보고서 생성

```python
# scripts/ 디렉토리에서 실행
from equity_report_generator import generate_equity_report
results = generate_equity_report(context, '$symbol')
# 결과: docs/reports/equity/$symbol-YYYY-MM-DD.{html,json}
```

---

## Step 4: 품질 체크 & 결과 알림

`equity-research-guide.md` 체크리스트 확인 후 결과를 알려주세요:
- [ ] CH1 thesis 200자+ / thesis_points 3개+
- [ ] revenue_breakdown[] 5개년+ (Exhibit 1)
- [ ] income_stmt[] 5개년+ (Exhibit 2)
- [ ] perf_chart_data[] 12개월+ (Exhibit 3)
- [ ] DCF matrix 6×5 완성
- [ ] risks[] 4개+ (tier/description)
- [ ] kpis[] 5개 (signal 포함)
- [ ] conclusion 200자+
- [ ] 금지 표현 없음

생성 파일: `docs/reports/equity/$symbol-YYYY-MM-DD.html` / `.json`
