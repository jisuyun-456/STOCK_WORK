# /analyze — Equity Research Report 생성

$ARGUMENTS: symbol

GS/JPM 수준 8챕터 Equity Research Report를 생성합니다.

## 실행 절차

1. **데이터 수집** — Yahoo Finance MCP + FMP API + yfinance로 $symbol 종목의 기술적/펀더멘털/기관 데이터를 수집하세요.

   아래 MCP 도구를 병렬로 호출하세요:
   - `mcp__yahoo-finance__get_ticker_info` (symbol=$symbol)
   - `mcp__yahoo-finance__get_financials` (symbol=$symbol, frequency=annual)
   - `mcp__yahoo-finance__get_earnings` (symbol=$symbol)
   - `mcp__yahoo-finance__get_holders` (symbol=$symbol)
   - `mcp__yahoo-finance__get_price_history` (symbol=$symbol, period=1y, interval=1d)
   - `mcp__yahoo-finance__get_analyst_data` (symbol=$symbol)

   그런 다음 Python으로 기존 분석 함수를 실행하세요:
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

2. **에이전트 분석** — 수집된 데이터를 기반으로 8챕터 context dict를 작성하세요. 각 챕터별로:

   - **CH1 Executive Summary**: Rating(BUY/HOLD/SELL), 12개월 목표가, Investment Thesis(3줄), 핵심 지표 6개(시가총액/Fwd P/E/EV·EBITDA/매출성장률/Gross Margin/FCF Yield), Bull/Base/Bear 시나리오(각 목표가+확률+근거)
   - **CH2 Business Overview**: 사업모델 설명, 매출 세그먼트별 비중+YoY, 지역별 매출 분포, 경쟁사 5개 비교(시총/성장률/마진), TAM/SAM/SOM
   - **CH3 Financial Analysis**: 손익계산서 5개년(실적3Y+추정2Y), 대차대조표 핵심(총자산/부채비율/순현금/ROIC/ROE), 현금흐름 5개년(OCF/CAPEX/FCF/FCF마진), 마진 추세
   - **CH4 Valuation**: DCF(WACC/TGR/적정가/민감도 5×5), Comps(Peer 5개사 P/E·EV/EBITDA·EV/Rev·P/FCF), 역사적 밸류에이션 3년 P/E 밴드, 목표가 방법론
   - **CH5 Growth Catalysts**: 단기 이벤트(0-6개월, 날짜 포함), 중장기 테마(1-3년), 마진 레버리지 포인트, 자본 배분 전략
   - **CH6 Risk Factors**: 사업/재무/규제/매크로 리스크 각각(제목/설명/확률/영향도/Bear가격 연결)
   - **CH7 Industry & Macro**: 섹터 상대 퍼포먼스(12M), 매크로 민감도(금리/경기사이클/Beta), 기관 포지션(Top3/내부자/공매도), 기술적 분석(지지/저항/RSI/MACD/MA)
   - **CH8 Investment Conclusion**: 최종 Rating, Trade Setup(진입구간/목표1/목표2/손절/R:R), 모니터링 KPI 5개(지표/임계치/액션), 다음 업데이트 트리거

3. **보고서 생성** — context dict를 사용하여 보고서를 생성하세요:
   ```bash
   cd scripts && python -c "
   from equity_report_generator import generate_equity_report
   generate_equity_report(context, '$symbol')
   "
   ```
   여기서 context는 위에서 작성한 8챕터 dict입니다.

4. **결과 알림** — 생성된 파일 경로를 사용자에게 알려주세요:
   - HTML: `docs/reports/equity/$symbol-YYYY-MM-DD.html`
   - PDF: `docs/reports/equity/$symbol-YYYY-MM-DD.pdf`
   - JSON: `docs/reports/equity/$symbol-YYYY-MM-DD.json`
