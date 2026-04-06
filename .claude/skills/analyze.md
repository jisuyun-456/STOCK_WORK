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

## Step 2: FMP 예산 체크
```bash
cd scripts && python3 fmp_rate_limiter.py check
```
245콜 이상이면 FMP 없이 Yahoo Finance만으로 진행.

## Step 3: 데이터 수집 (병렬)

Yahoo Finance MCP 호출:
- `mcp__yahoo-finance__get_ticker_info` (symbol)
- `mcp__yahoo-finance__get_financials` (symbol, frequency=annual)
- `mcp__yahoo-finance__get_earnings` (symbol)
- `mcp__yahoo-finance__get_holders` (symbol)
- `mcp__yahoo-finance__get_price_history` (symbol, period=1y, interval=1d)
- `mcp__yahoo-finance__get_analyst_data` (symbol)

Python 스크립트:
```bash
cd scripts && python3 -c "
from stock_analyzer import fetch_technical, fetch_fundamental, fetch_institutional
import json
tech = fetch_technical('SYMBOL')
fund = fetch_fundamental('SYMBOL')
inst = fetch_institutional('SYMBOL')
print(json.dumps({'technical': tech, 'fundamental': fund, 'institutional': inst}, default=str))
"
```

## Step 4: 에이전트 분석 (병렬)

3개 에이전트를 병렬 호출:
- **Fundamental Analyst** → CH1~CH4, CH6 (기업가치, 재무, 밸류에이션, 리스크)
- **Quant Strategist** → CH5, CH7 일부 (성장 촉매, 기술적 분석)
- **Market Scanner** → CH7 일부 (수급, 공시, 센티멘트)

## Step 5: 8챕터 context dict 조립

| 챕터 | 내용 |
|------|------|
| CH1 Executive Summary | Rating, 12개월 목표가, Investment Thesis, Bull/Base/Bear |
| CH2 Business Overview | 사업모델, 매출 세그먼트, 경쟁사 5개, TAM/SAM/SOM |
| CH3 Financial Analysis | 5개년 P&L, BS 핵심, CF, 마진 추세 |
| CH4 Valuation | DCF(민감도 5x5), Comps(Peer 5개), 역사적 P/E 밴드 |
| CH5 Growth Catalysts | 단기(0-6M), 중장기(1-3Y), 마진 레버리지 |
| CH6 Risk Factors | 사업/재무/규제/매크로 리스크 |
| CH7 Industry & Macro | 섹터 퍼포먼스, 매크로 민감도, 기관 포지션, 기술적 |
| CH8 Investment Conclusion | Rating, Trade Setup, 모니터링 KPI 5개 |

## Step 6: 보고서 생성

```bash
cd scripts && python3 -c "
from equity_report_generator import generate_equity_report
generate_equity_report(context, 'SYMBOL')
"
```

## Step 7: 결과 알림

출력 파일:
- HTML: `docs/reports/equity/SYMBOL-YYYY-MM-DD.html`
- PDF: `docs/reports/equity/SYMBOL-YYYY-MM-DD.pdf`
- JSON: `docs/reports/equity/SYMBOL-YYYY-MM-DD.json`

사용자에게 파일 경로 + 핵심 결론 요약 (Rating + 목표가 + 핵심 논거)
