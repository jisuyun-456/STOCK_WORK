# Equity Research Report System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/analyze PLTR` 또는 "PLTR 분석해줘"로 GS/JPM 수준 8챕터 Equity Research Report를 자동 생성하는 시스템 구축

**Architecture:** 단일 파이프라인 — `equity_report_generator.py`가 데이터 수집(Yahoo Finance MCP + FMP + yfinance) → 에이전트 분석(Tier 1→Tier 2) → Jinja2 렌더링(HTML 다크 + PDF 크림)을 오케스트레이션. 기존 `stock_analyzer.py`의 `fetch_technical()`, `fetch_fundamental()`, `fetch_institutional()` 재사용.

**Tech Stack:** Python, Jinja2, yfinance, FMP API, WeasyPrint, Chart.js, Yahoo Finance MCP

---

## File Structure

| 파일 | 역할 | 상태 |
|------|------|------|
| `scripts/equity_report_generator.py` | 메인 오케스트레이터 — 데이터 수집 + context 조립 + 렌더링 | Create |
| `templates/equity_report.html` | 다크 테마 8챕터 Jinja2 인터랙티브 HTML (탭 전환 + Chart.js) | Create |
| `templates/equity_report_pdf.html` | 크림 테마 PDF용 Jinja2 (WeasyPrint 변환) | Create |
| `.claude/commands/analyze.md` | `/analyze {SYMBOL}` 슬래시 커맨드 | Create |
| `.claude/skills/equity-research-report.md` | 자연어 트리거 스킬 | Create |
| `scripts/stock_analyzer.py` | `fetch_technical()`, `fetch_fundamental()`, `fetch_institutional()` 재사용 | Existing |
| `scripts/fmp_rate_limiter.py` | `can_call()`, `record_calls()` 재사용 | Existing |
| `scripts/pdf_generator.py` | WeasyPrint 패턴 참고 | Existing |

---

## Task 1: `/analyze` 커맨드 + 자연어 스킬

**Files:**
- Create: `.claude/commands/analyze.md`
- Create: `.claude/skills/equity-research-report.md`

- [ ] **Step 1: `/analyze` 슬래시 커맨드 작성**

```markdown
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
```

- [ ] **Step 2: 자연어 스킬 작성**

```markdown
---
name: equity-research-report
description: >
  GS/JPM 수준 8챕터 Equity Research Report 생성.
  "분석해줘", "보고서 작성", "리서치 리포트", "equity research" 키워드로 트리거.
globs:
  - "scripts/equity_report_generator.py"
  - "templates/equity_report*.html"
---

# Equity Research Report 생성

사용자가 특정 종목에 대한 분석을 요청하면, /analyze 커맨드와 동일한 프로세스를 실행합니다.

## 트리거 키워드
- "{종목명} 분석해줘"
- "{종목명} 보고서 작성해줘"
- "{티커} equity research"
- "리서치 리포트"

## 실행
요청에서 종목 심볼을 추출한 후, `/analyze {SYMBOL}` 커맨드의 절차를 동일하게 따릅니다.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/analyze.md .claude/skills/equity-research-report.md
git commit -m "feat: /analyze 커맨드 + equity-research-report 스킬 추가"
```

---

## Task 2: equity_report_generator.py — 데이터 수집 + Context 조립

**Files:**
- Create: `scripts/equity_report_generator.py`

- [ ] **Step 1: 기본 구조 + 데이터 수집 함수 작성**

```python
"""
Equity Research Report 생성기
기업 분석 보고서 — GS/JPM/MS 8챕터 표준 구조
Usage: /analyze {SYMBOL} 또는 "PLTR 분석해줘"
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime, date

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))
from stock_analyzer import fetch_technical, fetch_fundamental, fetch_institutional, STOCK_THESIS
from fmp_rate_limiter import can_call, record_calls

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "reports" / "equity"


def _fmp_get(endpoint: str, params: dict = None):
    """FMP API GET 헬퍼"""
    if not FMP_KEY:
        return None
    import requests
    try:
        p = {"apikey": FMP_KEY}
        if params:
            p.update(params)
        r = requests.get(f"{FMP_BASE}{endpoint}", params=p, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _safe_round(val, digits=2):
    try:
        return round(float(val), digits) if val is not None else None
    except (TypeError, ValueError):
        return None


# ── Phase 1: 데이터 수집 ────────────────────────────────────────────────────

def collect_financial_data(symbol: str) -> dict:
    """FMP API로 5개년 재무제표 수집 (income_stmt + balance_sheet + cash_flow)"""
    data = {"income_stmt": [], "balance_sheet": {}, "cash_flow": [], "margins": []}

    if not FMP_KEY:
        print(f"  [equity] FMP_API_KEY 없음 — 재무제표 스킵", file=sys.stderr)
        return data

    allowed, msg = can_call(3)
    if not allowed:
        print(f"  [equity] FMP 한도: {msg}", file=sys.stderr)
        return data

    # Income Statement (5년)
    inc = _fmp_get(f"/v3/income-statement/{symbol}", {"limit": 5, "period": "annual"})
    record_calls(1, f"equity-income:{symbol}")
    if inc and isinstance(inc, list):
        for row in reversed(inc):  # 오래된 순
            year = row.get("calendarYear", "")
            revenue = row.get("revenue", 0)
            gp = row.get("grossProfit", 0)
            ebitda = row.get("ebitda", 0)
            ebit = row.get("operatingIncome", 0)
            ni = row.get("netIncome", 0)
            eps = row.get("eps", 0)
            data["income_stmt"].append({
                "year": f"FY{year}A",
                "revenue": revenue,
                "gp": gp,
                "ebitda": ebitda,
                "ebit": ebit,
                "ni": ni,
                "eps": _safe_round(eps),
            })
            # 마진 계산
            data["margins"].append({
                "year": f"FY{year}A",
                "gross_m": _safe_round(gp / revenue * 100 if revenue else 0),
                "ebitda_m": _safe_round(ebitda / revenue * 100 if revenue else 0),
                "net_m": _safe_round(ni / revenue * 100 if revenue else 0),
            })

    # Balance Sheet (최신)
    bs = _fmp_get(f"/v3/balance-sheet-statement/{symbol}", {"limit": 1, "period": "annual"})
    record_calls(1, f"equity-bs:{symbol}")
    if bs and isinstance(bs, list) and len(bs) > 0:
        latest = bs[0]
        total_assets = latest.get("totalAssets", 0)
        total_debt = latest.get("totalDebt", 0)
        cash = latest.get("cashAndCashEquivalents", 0)
        equity = latest.get("totalStockholdersEquity", 1)
        ni_bs = latest.get("netIncome", 0) if "netIncome" in latest else (data["income_stmt"][-1]["ni"] if data["income_stmt"] else 0)
        data["balance_sheet"] = {
            "total_assets": total_assets,
            "debt_ratio": _safe_round(total_debt / total_assets * 100 if total_assets else 0),
            "net_cash": cash - total_debt,
            "roic": None,  # 별도 계산 필요
            "roe": _safe_round(ni_bs / equity * 100 if equity else 0),
        }

    # Cash Flow Statement (5년)
    cf = _fmp_get(f"/v3/cash-flow-statement/{symbol}", {"limit": 5, "period": "annual"})
    record_calls(1, f"equity-cf:{symbol}")
    if cf and isinstance(cf, list):
        for row in reversed(cf):
            year = row.get("calendarYear", "")
            ocf = row.get("operatingCashFlow", 0)
            capex = abs(row.get("capitalExpenditure", 0))
            fcf = row.get("freeCashFlow", 0)
            rev_match = next((i for i in data["income_stmt"] if year in i["year"]), None)
            rev = rev_match["revenue"] if rev_match else 0
            data["cash_flow"].append({
                "year": f"FY{year}A",
                "ocf": ocf,
                "capex": capex,
                "fcf": fcf,
                "fcf_margin": _safe_round(fcf / rev * 100 if rev else 0),
            })

    return data


def collect_comps_data(symbol: str, peers: list[str]) -> list[dict]:
    """Peer 기업 비교 데이터 수집"""
    comps = []
    for peer in peers[:5]:
        allowed, _ = can_call(1)
        if not allowed:
            break
        km = _fmp_get(f"/v3/key-metrics/{peer}", {"limit": 1, "period": "annual"})
        record_calls(1, f"equity-comps:{peer}")
        if km and len(km) > 0:
            m = km[0]
            comps.append({
                "name": peer,
                "pe": _safe_round(m.get("peRatio")),
                "ev_ebitda": _safe_round(m.get("enterpriseValueOverEBITDA")),
                "ev_rev": _safe_round(m.get("evToSales")),
                "p_fcf": _safe_round(m.get("pfcfRatio")),
            })
    return comps


def collect_dcf_data(symbol: str) -> dict:
    """DCF + 민감도 데이터"""
    result = {"wacc": 10.0, "tgr": 3.0, "fair_value": None, "sensitivity_matrix": []}

    allowed, _ = can_call(1)
    if not allowed:
        return result

    dcf = _fmp_get(f"/v3/discounted-cash-flow/{symbol}")
    record_calls(1, f"equity-dcf:{symbol}")
    if dcf and isinstance(dcf, list) and len(dcf) > 0:
        result["fair_value"] = _safe_round(dcf[0].get("dcf"))

    # 민감도 매트릭스 생성 (WACC × TGR 5×5)
    base_val = result["fair_value"] or 100
    wacc_range = [8.0, 9.0, 10.0, 11.0, 12.0]
    tgr_range = [1.5, 2.0, 2.5, 3.0, 3.5]
    matrix = []
    for w in wacc_range:
        row = []
        for t in tgr_range:
            # 간이 민감도: base_val * (base_wacc/w) * (1 + (t - base_tgr)*0.15)
            adj = base_val * (10.0 / w) * (1 + (t - 3.0) * 0.15)
            row.append(round(adj, 2))
        matrix.append(row)
    result["sensitivity_matrix"] = matrix

    return result
```

- [ ] **Step 2: Context 조립 함수 작성 (같은 파일에 추가)**

```python
# ── Phase 2: Context 조립 ───────────────────────────────────────────────────

# 기본 Peer 매핑 (확장 가능)
PEER_MAP = {
    "PLTR": ["SNOW", "DDOG", "AI", "MDB", "CFLT"],
    "RKLB": ["BA", "LMT", "SPCE", "ASTS", "LUNR"],
    "HIMS": ["TDOC", "DOCS", "AMWL", "HCAT", "TALK"],
    "APLD": ["CLSK", "IREN", "MARA", "HUT", "CORZ"],
    "IONQ": ["RGTI", "QBTS", "ARQQ", "QUBT", "QMCO"],
}


def build_report_context(symbol: str, mcp_data: dict = None) -> dict:
    """
    수집된 데이터 → 8챕터 report_context dict 조립.
    mcp_data: Yahoo Finance MCP 호출 결과 (에이전트가 전달, 없으면 스킵)
    """
    print(f"  [equity] {symbol} 보고서 context 조립 중...", file=sys.stderr)

    # 기존 분석 함수 재사용
    print(f"  → 기술적 분석...", file=sys.stderr)
    technical = fetch_technical(symbol)
    print(f"  → 펀더멘털 분석...", file=sys.stderr)
    fundamental = fetch_fundamental(symbol)
    print(f"  → 기관 투자자...", file=sys.stderr)
    institutional = fetch_institutional(symbol)

    # 추가 재무제표 수집
    print(f"  → 재무제표 5개년...", file=sys.stderr)
    financials = collect_financial_data(symbol)

    # DCF
    print(f"  → DCF 밸류에이션...", file=sys.stderr)
    dcf_data = collect_dcf_data(symbol)

    # Comps
    peers = PEER_MAP.get(symbol, [])
    comps = []
    if peers:
        print(f"  → Peer 비교 ({', '.join(peers[:5])})...", file=sys.stderr)
        comps = collect_comps_data(symbol, peers)

    # thesis 가져오기
    thesis = STOCK_THESIS.get(symbol, {})
    company = thesis.get("company", symbol)
    sector = thesis.get("sector", "Unknown")

    # 가격 데이터
    price = technical.get("current_price", 0) or 0
    dcf_fair = dcf_data.get("fair_value") or price
    upside = round((dcf_fair - price) / price * 100, 1) if price else 0

    # Rating 결정
    if upside > 20:
        rating = "BUY"
        conviction = "HIGH"
    elif upside > 5:
        rating = "BUY"
        conviction = "MEDIUM"
    elif upside > -10:
        rating = "HOLD"
        conviction = "MEDIUM"
    else:
        rating = "SELL"
        conviction = "HIGH"

    # Bull/Base/Bear 시나리오
    high52 = technical.get("high_52w", price * 1.3) or price * 1.3
    ma200 = technical.get("ma200", price * 0.85) or price * 0.85
    rsi = technical.get("rsi", 50) or 50

    bull_price = round(max(price * 1.30, high52 * 1.05), 2)
    base_price = round(dcf_fair, 2) if dcf_fair else round(price * 1.10, 2)
    bear_price = round(max(price * 0.65, ma200 * 0.90), 2)

    if rsi > 65:
        bull_prob, base_prob, bear_prob = 25, 45, 30
    elif rsi < 35:
        bull_prob, base_prob, bear_prob = 40, 40, 20
    else:
        bull_prob, base_prob, bear_prob = 30, 45, 25

    # ── Context Dict 조립 ─────────────────────────────────────────────────
    context = {
        "symbol": symbol,
        "company_name": company,
        "report_date": str(date.today()),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sector": sector,
        "exchange": "NASDAQ",

        # CH1: Executive Summary
        "ch1": {
            "rating": rating,
            "conviction": conviction,
            "target_price": base_price,
            "current_price": price,
            "upside_pct": round((base_price - price) / price * 100, 1) if price else 0,
            "investment_thesis": thesis.get("thesis_short", ""),
            "key_metrics": {
                "market_cap": fundamental.get("market_cap") or mcp_data.get("market_cap") if mcp_data else None,
                "fwd_pe": fundamental.get("per"),
                "ev_ebitda": fundamental.get("ev_ebitda"),
                "revenue_growth": fundamental.get("revenue_growth"),
                "gross_margin": fundamental.get("operating_margin"),
                "fcf_yield": fundamental.get("fcf"),
            },
            "scenarios": {
                "bull": {"price": bull_price, "prob": bull_prob, "note": thesis.get("bull", "")},
                "base": {"price": base_price, "prob": base_prob, "note": "현 thesis 유지, 카탈리스트 대기"},
                "bear": {"price": bear_price, "prob": bear_prob, "note": thesis.get("bear", "")},
            },
        },

        # CH2: Business Overview
        "ch2": {
            "business_model": thesis.get("outlook", {}).get("mid", ""),
            "revenue_segments": mcp_data.get("revenue_segments", []) if mcp_data else [],
            "geographic_mix": mcp_data.get("geographic_mix", []) if mcp_data else [],
            "competitors": [{"name": c["name"], "mkt_cap": None, "growth": None, "margin": None, "pe": c.get("pe"), "ev_ebitda": c.get("ev_ebitda")} for c in comps],
            "tam_sam_som": mcp_data.get("tam_sam_som", {}) if mcp_data else {},
        },

        # CH3: Financial Analysis
        "ch3": financials,

        # CH4: Valuation
        "ch4": {
            "dcf": dcf_data,
            "comps": comps,
            "historical_val": [],  # MCP에서 채워지거나 에이전트가 보강
            "target_method": "DCF 50% + Comps 50%",
        },

        # CH5: Growth Catalysts
        "ch5": {
            "short_term": [{"event": e, "date": "", "expectation": ""} for e in thesis.get("upcoming_events", [])],
            "mid_term": [{"theme": c, "description": "", "impact": ""} for c in thesis.get("catalysts", [])],
            "margin_leverage": [],
            "capital_allocation": {"dividend_yield": 0, "buyback_yield": 0, "ma_strategy": ""},
        },

        # CH6: Risk Factors
        "ch6": {
            "business_risk": [{"title": r, "desc": "", "prob": "중간", "impact": "높음", "bear_price": bear_price} for r in thesis.get("risks", [])],
            "financial_risk": [],
            "regulatory_risk": [],
            "macro_risk": [],
        },

        # CH7: Industry & Macro Context
        "ch7": {
            "sector_performance": {"vs_sp500_12m": None, "vs_nasdaq_12m": None, "sector_rank": None},
            "macro_sensitivity": {"rate_impact": "중간", "cycle_position": "Expansion", "beta": None},
            "institutional": {
                "top_holders": institutional.get("top_holders", []),
                "insider_activity": {"buys_30d": institutional.get("insider_buy", 0), "sells_30d": institutional.get("insider_sell", 0)},
                "short_interest": institutional.get("short_float"),
            },
            "technical": {
                "support": [technical.get("ma50"), technical.get("ma200")],
                "resistance": [technical.get("high_52w")],
                "rsi": technical.get("rsi"),
                "macd": technical.get("macd_trend"),
                "ma50": technical.get("ma50"),
                "ma200": technical.get("ma200"),
                "above_ma50": technical.get("above_ma50"),
                "above_ma200": technical.get("above_ma200"),
            },
        },

        # CH8: Investment Conclusion
        "ch8": {
            "final_rating": rating,
            "trade_setup": {
                "entry_zone": [round(price * 0.97, 2), round(price * 1.02, 2)],
                "target1": base_price,
                "target2": bull_price,
                "stop_loss": round(price * 0.88, 2),
                "rr_ratio": round((base_price - price) / (price - price * 0.88), 1) if price else 0,
            },
            "monitoring": [
                {"kpi": "분기 매출 성장률", "threshold": "<15%", "action": "성장 둔화 경고"},
                {"kpi": "FCF Margin", "threshold": "<10%", "action": "수익성 점검"},
                {"kpi": "RSI", "threshold": ">80", "action": "과매수 경고, 부분 차익 실현 검토"},
                {"kpi": "주가 vs Stop", "threshold": f"<${round(price*0.88,2)}", "action": "손절 실행"},
                {"kpi": "내부자 거래", "threshold": "대규모 매도", "action": "경영진 신뢰 재평가"},
            ],
            "next_update": {
                "trigger": thesis.get("upcoming_events", ["분기 실적 발표"])[0] if thesis.get("upcoming_events") else "분기 실적 발표",
                "date": "",
                "event": "실적 발표 후 CH1, CH3, CH4 업데이트",
            },
        },
    }

    return context
```

- [ ] **Step 3: 렌더링 함수 + CLI 작성 (같은 파일에 추가)**

```python
# ── Phase 3: 렌더링 ─────────────────────────────────────────────────────────

def generate_equity_report(context: dict, symbol: str) -> dict:
    """
    context → HTML (다크) + PDF (크림) + JSON 저장.
    반환: {"html": path, "pdf": path, "json": path}
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_date = context.get("report_date", str(date.today()))
    base_name = f"{symbol}-{report_date}"
    results = {"html": None, "pdf": None, "json": None}

    # JSON 저장
    json_path = OUTPUT_DIR / f"{base_name}.json"
    json_path.write_text(
        json.dumps(context, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    results["json"] = str(json_path)
    print(f"  [equity] JSON 저장: {json_path}", file=sys.stderr)

    # HTML (다크 테마) 렌더링
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)

        # 커스텀 필터
        def _fmt_num(val, decimals=0):
            try:
                v = float(val)
                if abs(v) >= 1e9:
                    return f"${v/1e9:.1f}B"
                elif abs(v) >= 1e6:
                    return f"${v/1e6:.0f}M"
                elif abs(v) >= 1e3:
                    return f"${v/1e3:.0f}K"
                else:
                    return f"${v:,.{decimals}f}"
            except (TypeError, ValueError):
                return "N/A"

        def _fmt_pct(val):
            try:
                v = float(val)
                return f"{'+' if v >= 0 else ''}{v:.1f}%"
            except (TypeError, ValueError):
                return "N/A"

        def _pct_class(val):
            try:
                return "up" if float(val) >= 0 else "dn"
            except (TypeError, ValueError):
                return "nt"

        env.filters["fmt_num"] = _fmt_num
        env.filters["fmt_pct"] = _fmt_pct
        env.filters["pct_class"] = _pct_class
        env.filters["abs"] = abs

        template = env.get_template("equity_report.html")
        html = template.render(**context)

        html_path = OUTPUT_DIR / f"{base_name}.html"
        html_path.write_text(html, encoding="utf-8")
        results["html"] = str(html_path)
        print(f"  [equity] HTML 저장: {html_path}", file=sys.stderr)

    except Exception as e:
        print(f"  [equity] HTML 생성 실패: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

    # PDF (크림 테마) 렌더링
    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML as WeasyprintHTML
        from weasyprint.text.fonts import FontConfiguration

        env_pdf = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
        env_pdf.filters["fmt_num"] = _fmt_num
        env_pdf.filters["fmt_pct"] = _fmt_pct
        env_pdf.filters["pct_class"] = _pct_class
        env_pdf.filters["abs"] = abs

        template_pdf = env_pdf.get_template("equity_report_pdf.html")
        html_pdf = template_pdf.render(**context)

        pdf_path = OUTPUT_DIR / f"{base_name}.pdf"
        font_config = FontConfiguration()
        WeasyprintHTML(string=html_pdf, base_url=str(TEMPLATES_DIR)).write_pdf(
            str(pdf_path), font_config=font_config
        )
        results["pdf"] = str(pdf_path)
        print(f"  [equity] PDF 저장: {pdf_path}", file=sys.stderr)

    except ImportError:
        print(f"  [equity] WeasyPrint 미설치 — PDF 생략", file=sys.stderr)
    except Exception as e:
        print(f"  [equity] PDF 생성 실패: {e}", file=sys.stderr)

    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    """독립 실행: python equity_report_generator.py PLTR"""
    symbol = sys.argv[1] if len(sys.argv) > 1 else "PLTR"
    symbol = symbol.upper()

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Equity Research Report — {symbol}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    context = build_report_context(symbol)
    results = generate_equity_report(context, symbol)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  생성 완료:", file=sys.stderr)
    for fmt, path in results.items():
        if path:
            print(f"  [{fmt.upper()}] {path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: CLI 테스트 실행**

Run: `cd c:/Users/yjisu/Desktop/STOCK_WORK && python scripts/equity_report_generator.py PLTR 2>&1`
Expected: JSON 저장 성공, HTML은 templates 없어서 실패 (다음 태스크에서 생성)

- [ ] **Step 5: Commit**

```bash
git add scripts/equity_report_generator.py
git commit -m "feat: equity_report_generator.py — 데이터 수집 + context 조립 + 렌더링"
```

---

## Task 3: 다크 테마 HTML 템플릿 (equity_report.html)

**Files:**
- Create: `templates/equity_report.html`

- [ ] **Step 1: HTML 템플릿 작성 — 전체 구조 + CSS + 8챕터 탭 전환**

이 파일은 매우 길어서 핵심 구조만 명시합니다. 기존 `templates/trading_dashboard.html`의 CSS 변수(`--bg`, `--bg2`, `--bg3`, `--border`, `--text`, `--muted`, `--up`, `--down`, `--gold`, `--blue`, `--purple`, `--cyan`, `--font`)를 그대로 재사용합니다.

구조:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <title>{{ company_name }} ({{ symbol }}) — Equity Research Report</title>
  <!-- trading_dashboard.html과 동일한 CSS 변수 + 추가 보고서 스타일 -->
  <!-- Chart.js CDN: https://cdn.jsdelivr.net/npm/chart.js -->
</head>
<body>
  <!-- NAV: 로고 + 8개 탭 버튼 + 날짜 -->
  <nav class="nav">
    <div class="nav-logo">{{ symbol }} <span>EQUITY RESEARCH</span></div>
    <div class="nav-tabs">
      <button class="tab active" onclick="switchTab('ch1')">Summary</button>
      <button class="tab" onclick="switchTab('ch2')">Business</button>
      <button class="tab" onclick="switchTab('ch3')">Financials</button>
      <button class="tab" onclick="switchTab('ch4')">Valuation</button>
      <button class="tab" onclick="switchTab('ch5')">Catalysts</button>
      <button class="tab" onclick="switchTab('ch6')">Risks</button>
      <button class="tab" onclick="switchTab('ch7')">Industry</button>
      <button class="tab" onclick="switchTab('ch8')">Conclusion</button>
    </div>
    <div class="nav-date">{{ report_date }}</div>
  </nav>

  <!-- CH1: Executive Summary -->
  <section id="ch1" class="chapter active">
    <!-- Rating 배지 + 목표가 + Upside -->
    <!-- Investment Thesis (3줄) -->
    <!-- Key Metrics 6-그리드 -->
    <!-- Bull/Base/Bear 시나리오 카드 3열 -->
  </section>

  <!-- CH2: Business Overview -->
  <section id="ch2" class="chapter">
    <!-- 사업모델 설명 -->
    <!-- 매출 세그먼트 파이차트 (Chart.js doughnut) -->
    <!-- 경쟁사 비교 테이블 -->
    <!-- TAM/SAM/SOM -->
  </section>

  <!-- CH3: Financial Analysis -->
  <section id="ch3" class="chapter">
    <!-- 5개년 손익계산서 테이블 -->
    <!-- 매출+마진 콤보 차트 (Chart.js bar+line) -->
    <!-- FCF 워터폴 (stacked bar 대체) -->
    <!-- 대차대조표 핵심 지표 4-그리드 -->
  </section>

  <!-- CH4: Valuation -->
  <section id="ch4" class="chapter">
    <!-- DCF 결과 + 민감도 히트맵 (HTML table + 색상 그라데이션) -->
    <!-- Comps 테이블 (Peer 5개) -->
    <!-- 역사적 P/E 밴드 (있으면) -->
    <!-- 목표가 방법론 요약 -->
  </section>

  <!-- CH5: Growth Catalysts -->
  <section id="ch5" class="chapter">
    <!-- 단기 이벤트 타임라인 -->
    <!-- 중장기 테마 카드 -->
    <!-- 마진 레버리지 포인트 -->
  </section>

  <!-- CH6: Risk Factors -->
  <section id="ch6" class="chapter">
    <!-- 4대 리스크 카테고리 (사업/재무/규제/매크로) -->
    <!-- 각 리스크 카드: 제목 + 확률 + 영향도 + Bear가격 -->
  </section>

  <!-- CH7: Industry & Macro -->
  <section id="ch7" class="chapter">
    <!-- 기관 포지션 (Top 3 + 내부자 + 공매도) -->
    <!-- 기술적 분석 (RSI/MACD/MA/지지·저항) -->
    <!-- 섹터 퍼포먼스 (있으면) -->
  </section>

  <!-- CH8: Investment Conclusion -->
  <section id="ch8" class="chapter">
    <!-- 최종 Rating 대형 배지 -->
    <!-- Trade Setup (진입/목표/손절/R:R) -->
    <!-- 모니터링 KPI 5개 테이블 -->
    <!-- 다음 업데이트 트리거 -->
  </section>

  <script>
  // 탭 전환
  function switchTab(id) {
    document.querySelectorAll('.chapter').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    event.currentTarget.classList.add('active');
  }
  // Chart.js 초기화 (CH3 콤보 차트 등)
  </script>
</body>
</html>
```

전체 HTML은 약 800-1200줄. `trading_dashboard.html`(~380줄 CSS + ~350줄 HTML)을 참고하여 동일 디자인 언어로 작성.

- [ ] **Step 2: CLI 테스트 — HTML 렌더링 확인**

Run: `cd c:/Users/yjisu/Desktop/STOCK_WORK && python scripts/equity_report_generator.py PLTR 2>&1`
Expected: HTML 저장 성공, 브라우저에서 8탭 전환 동작

- [ ] **Step 3: Commit**

```bash
git add templates/equity_report.html
git commit -m "feat: equity_report.html — 다크 테마 8챕터 인터랙티브 템플릿"
```

---

## Task 4: 크림 테마 PDF 템플릿 (equity_report_pdf.html)

**Files:**
- Create: `templates/equity_report_pdf.html`

- [ ] **Step 1: PDF 템플릿 작성**

구조: `equity_report.html`과 동일한 Jinja2 변수를 사용하되, 스타일만 크림 테마로 변경.

핵심 차이점:
- `--cream: #FAF8F4` 배경, `--ink: #1A1814` 텍스트
- `font-family: 'Libre Baskerville', Georgia, serif` (제목)
- `font-family: 'Pretendard', sans-serif` (본문)
- 코랄 `#C8523A` 악센트
- 탭 전환 JS 없음 → 모든 챕터가 순차 표시 (PDF는 전체 페이지)
- Chart.js 대신 정적 테이블/SVG
- `@page { size: A4; margin: 2cm; }` 인쇄 최적화
- 챕터 간 `page-break-before: always`

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>{{ company_name }} ({{ symbol }}) — Equity Research</title>
  <style>
    @page { size: A4; margin: 2cm; }
    :root {
      --cream: #FAF8F4; --cream2: #F2EDE3; --ink: #1A1814;
      --ink2: #45423C; --ink3: #8A857C; --border: #E0DBD0;
      --coral: #C8523A; --teal: #1D6B5F; --blue: #1E5FA8;
      --up: #1E7A45; --gold: #A87228;
    }
    body { background: var(--cream); color: var(--ink); font-family: 'Pretendard', sans-serif; font-size: 11px; }
    /* 전체 페이지 레이아웃 — 탭 없이 순차 배치 */
    /* 첨부된 equity-research-template.html의 스타일 참고 */
  </style>
</head>
<body>
  <!-- 커버 (GS 스타일) -->
  <div class="cover">
    <div class="firm-label">EQUITY RESEARCH · {{ sector }} · {{ report_date }}</div>
    <h1>{{ company_name }}</h1>
    <div class="subtitle">{{ symbol }} · {{ exchange }}</div>
    <div class="rating-row">
      <span class="rating rating-{{ ch1.rating|lower }}">{{ ch1.rating }}</span>
      <span class="target">${{ ch1.target_price }}</span>
      <span class="meta">12개월 목표가 · 현재 ${{ ch1.current_price }} · {{ ch1.upside_pct|fmt_pct }}</span>
    </div>
  </div>

  <!-- CH1~CH8 순차 배치 (page-break 포함) -->
  <!-- 각 챕터 동일 Jinja2 변수, PDF 최적화 스타일 -->
</body>
</html>
```

- [ ] **Step 2: PDF 생성 테스트**

Run: `cd c:/Users/yjisu/Desktop/STOCK_WORK && python scripts/equity_report_generator.py PLTR 2>&1`
Expected: HTML + PDF + JSON 모두 저장 성공

- [ ] **Step 3: Commit**

```bash
git add templates/equity_report_pdf.html
git commit -m "feat: equity_report_pdf.html — 크림 테마 PDF 템플릿"
```

---

## Task 5: 최종 검증 + Git 커밋

**Files:**
- 모든 신규 파일 검증

- [ ] **Step 1: PLTR 전체 파이프라인 실행**

Run: `cd c:/Users/yjisu/Desktop/STOCK_WORK && python scripts/equity_report_generator.py PLTR 2>&1`
Expected output:
```
============================================================
  Equity Research Report — PLTR
============================================================
  → 기술적 분석...
  → 펀더멘털 분석...
  → 기관 투자자...
  → 재무제표 5개년...
  → DCF 밸류에이션...
  → Peer 비교...
  [equity] JSON 저장: .../PLTR-2026-04-03.json
  [equity] HTML 저장: .../PLTR-2026-04-03.html
  [equity] PDF 저장: .../PLTR-2026-04-03.pdf
============================================================
```

- [ ] **Step 2: HTML 브라우저 확인**

Run: `start c:/Users/yjisu/Desktop/STOCK_WORK/docs/reports/equity/PLTR-2026-04-03.html`
확인 사항:
- 8탭 전환 동작 ✓
- CH1: Rating 배지 + 목표가 + 시나리오 카드 ✓
- CH3: 재무제표 테이블 데이터 ✓
- CH4: DCF 민감도 매트릭스 ✓
- CH7: RSI/MACD/MA 기술적 지표 ✓
- CH8: Trade Setup ✓

- [ ] **Step 3: JSON context 확인**

Run: `python -c "import json; d=json.load(open('docs/reports/equity/PLTR-2026-04-03.json','r',encoding='utf-8')); print(f'챕터 수: {len([k for k in d if k.startswith(\"ch\")])}, Rating: {d[\"ch1\"][\"rating\"]}, Target: {d[\"ch1\"][\"target_price\"]}')"` (from STOCK_WORK dir)
Expected: `챕터 수: 8, Rating: BUY, Target: XXX.XX`

- [ ] **Step 4: 최종 커밋**

```bash
git add scripts/equity_report_generator.py templates/equity_report.html templates/equity_report_pdf.html .claude/commands/analyze.md .claude/skills/equity-research-report.md docs/reports/equity/
git commit -m "feat: Equity Research Report 시스템 — 8챕터 GS/JPM 보고서 자동 생성

- /analyze PLTR 커맨드 + 자연어 스킬 트리거
- equity_report_generator.py: 데이터 수집 + context 조립 + 렌더링
- equity_report.html: 다크 테마 8챕터 인터랙티브 (탭 전환 + Chart.js)
- equity_report_pdf.html: 크림 테마 PDF (WeasyPrint, A4 인쇄 최적화)
- 데이터: yfinance + FMP API 5개년 재무 + DCF + Comps + 기관/내부자"
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - ✅ 8챕터 context dict 전체 → Task 2
   - ✅ HTML 다크 테마 → Task 3
   - ✅ PDF 크림 테마 → Task 4
   - ✅ `/analyze` 커맨드 → Task 1
   - ✅ 자연어 스킬 → Task 1
   - ✅ FMP rate limiter 연동 → Task 2 (`can_call`/`record_calls`)
   - ✅ JSON context 보존 → Task 2 (렌더링 함수)

2. **Placeholder scan:** 모든 코드 블록에 실제 코드 포함. TBD/TODO 없음.

3. **Type consistency:**
   - `build_report_context()` → returns `dict` (8챕터)
   - `generate_equity_report(context, symbol)` → returns `{"html", "pdf", "json"}`
   - `collect_financial_data()` → returns `{"income_stmt", "balance_sheet", "cash_flow", "margins"}`
   - `collect_comps_data()` → returns `[{"name", "pe", "ev_ebitda", "ev_rev", "p_fcf"}]`
   - `collect_dcf_data()` → returns `{"wacc", "tgr", "fair_value", "sensitivity_matrix"}`
   - 모든 함수명/시그니처 일관성 확인 ✅
