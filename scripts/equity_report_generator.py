"""
Equity Research Report 생성기
기업 분석 보고서 — GS/JPM/MS 8챕터 표준 구조
Usage: python equity_report_generator.py PLTR
       /analyze PLTR (Claude Code 커맨드)
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent))

# .env 로드 (dotenv 없이 직접 파싱)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

from stock_analyzer import fetch_technical, fetch_fundamental, fetch_institutional, STOCK_THESIS
from fmp_rate_limiter import can_call, record_calls

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api"
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "reports" / "equity"


def _fmp_get(endpoint: str, params: dict = None):
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
    """FMP API로 5개년 재무제표 수집"""
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
        for row in reversed(inc):
            year = row.get("calendarYear", "")
            revenue = row.get("revenue", 0) or 0
            gp = row.get("grossProfit", 0) or 0
            ebitda = row.get("ebitda", 0) or 0
            ebit = row.get("operatingIncome", 0) or 0
            ni = row.get("netIncome", 0) or 0
            eps = row.get("eps", 0) or 0
            data["income_stmt"].append({
                "year": f"FY{year}A",
                "revenue": revenue,
                "gp": gp,
                "ebitda": ebitda,
                "ebit": ebit,
                "ni": ni,
                "eps": _safe_round(eps),
            })
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
        total_assets = latest.get("totalAssets", 0) or 0
        total_debt = latest.get("totalDebt", 0) or 0
        cash = latest.get("cashAndCashEquivalents", 0) or 0
        equity = latest.get("totalStockholdersEquity", 1) or 1
        ni_bs = data["income_stmt"][-1]["ni"] if data["income_stmt"] else 0
        data["balance_sheet"] = {
            "total_assets": total_assets,
            "debt_ratio": _safe_round(total_debt / total_assets * 100 if total_assets else 0),
            "net_cash": cash - total_debt,
            "roic": None,
            "roe": _safe_round(ni_bs / equity * 100 if equity else 0),
        }

    # Cash Flow Statement (5년)
    cf = _fmp_get(f"/v3/cash-flow-statement/{symbol}", {"limit": 5, "period": "annual"})
    record_calls(1, f"equity-cf:{symbol}")
    if cf and isinstance(cf, list):
        for row in reversed(cf):
            year = row.get("calendarYear", "")
            ocf = row.get("operatingCashFlow", 0) or 0
            capex = abs(row.get("capitalExpenditure", 0) or 0)
            fcf = row.get("freeCashFlow", 0) or 0
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

    # 민감도 매트릭스 (WACC × TGR 5×5)
    base_val = result["fair_value"] or 100
    wacc_range = [8.0, 9.0, 10.0, 11.0, 12.0]
    tgr_range = [1.5, 2.0, 2.5, 3.0, 3.5]
    matrix = []
    for w in wacc_range:
        row = []
        for t in tgr_range:
            adj = base_val * (10.0 / w) * (1 + (t - 3.0) * 0.15)
            row.append(round(adj, 2))
        matrix.append(row)
    result["sensitivity_matrix"] = matrix

    return result


# ── Phase 2: Context 조립 ───────────────────────────────────────────────────

PEER_MAP = {
    "PLTR": ["SNOW", "DDOG", "AI", "MDB", "CFLT"],
    "RKLB": ["BA", "LMT", "SPCE", "ASTS", "LUNR"],
    "HIMS": ["TDOC", "DOCS", "AMWL", "HCAT", "TALK"],
    "APLD": ["CLSK", "IREN", "MARA", "HUT", "CORZ"],
    "IONQ": ["RGTI", "QBTS", "ARQQ", "QUBT", "QMCO"],
}


def build_report_context(symbol: str, mcp_data: dict = None) -> dict:
    """수집된 데이터 → 8챕터 report_context dict 조립"""
    print(f"  [equity] {symbol} 보고서 context 조립 중...", file=sys.stderr)

    print(f"  → 기술적 분석...", file=sys.stderr)
    technical = fetch_technical(symbol)
    print(f"  → 펀더멘털 분석...", file=sys.stderr)
    fundamental = fetch_fundamental(symbol)
    print(f"  → 기관 투자자...", file=sys.stderr)
    institutional = fetch_institutional(symbol)

    print(f"  → 재무제표 5개년...", file=sys.stderr)
    financials = collect_financial_data(symbol)

    print(f"  → DCF 밸류에이션...", file=sys.stderr)
    dcf_data = collect_dcf_data(symbol)

    peers = PEER_MAP.get(symbol, [])
    comps = []
    if peers:
        print(f"  → Peer 비교 ({', '.join(peers[:5])})...", file=sys.stderr)
        comps = collect_comps_data(symbol, peers)

    thesis = STOCK_THESIS.get(symbol, {
        "company": symbol, "thesis_short": "", "sector": "Unknown",
        "outlook": {"short": "", "mid": "", "long": ""},
        "bull": "", "bear": "", "risks": [], "catalysts": [], "upcoming_events": [],
    })
    company = thesis.get("company", symbol)
    sector = thesis.get("sector", "Unknown")

    price = technical.get("current_price", 0) or 0
    dcf_fair = dcf_data.get("fair_value") or price
    upside = round((dcf_fair - price) / price * 100, 1) if price else 0

    # Rating 결정
    if upside > 20:
        rating, conviction = "BUY", "HIGH"
    elif upside > 5:
        rating, conviction = "BUY", "MEDIUM"
    elif upside > -10:
        rating, conviction = "HOLD", "MEDIUM"
    else:
        rating, conviction = "SELL", "HIGH"

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

    # Revenue growth 계산 (income_stmt 기준)
    rev_growth = None
    if len(financials["income_stmt"]) >= 2:
        r1 = financials["income_stmt"][-1]["revenue"]
        r0 = financials["income_stmt"][-2]["revenue"]
        if r0:
            rev_growth = _safe_round((r1 - r0) / r0 * 100)

    context = {
        "symbol": symbol,
        "company_name": company,
        "report_date": str(date.today()),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sector": sector,
        "exchange": "NASDAQ",

        "ch1": {
            "rating": rating,
            "conviction": conviction,
            "target_price": base_price,
            "current_price": price,
            "upside_pct": round((base_price - price) / price * 100, 1) if price else 0,
            "investment_thesis": thesis.get("thesis_short", ""),
            "investment_thesis_long": thesis.get("outlook", {}).get("mid", ""),
            "key_metrics": {
                "market_cap": fundamental.get("market_cap"),
                "fwd_pe": fundamental.get("per"),
                "ev_ebitda": fundamental.get("ev_ebitda"),
                "revenue_growth": rev_growth or fundamental.get("revenue_growth"),
                "gross_margin": financials["margins"][-1]["gross_m"] if financials["margins"] else None,
                "fcf_yield": fundamental.get("fcf"),
            },
            "scenarios": {
                "bull": {"price": bull_price, "prob": bull_prob, "note": thesis.get("bull", "")},
                "base": {"price": base_price, "prob": base_prob, "note": "현 thesis 유지, 카탈리스트 대기"},
                "bear": {"price": bear_price, "prob": bear_prob, "note": thesis.get("bear", "")},
            },
        },

        "ch2": {
            "business_model": thesis.get("outlook", {}).get("mid", ""),
            "business_model_short": thesis.get("outlook", {}).get("short", ""),
            "revenue_segments": mcp_data.get("revenue_segments", []) if mcp_data else [],
            "geographic_mix": mcp_data.get("geographic_mix", []) if mcp_data else [],
            "competitors": [{"name": c["name"], "pe": c.get("pe"), "ev_ebitda": c.get("ev_ebitda"), "ev_rev": c.get("ev_rev"), "p_fcf": c.get("p_fcf")} for c in comps],
            "tam_sam_som": mcp_data.get("tam_sam_som", {}) if mcp_data else {},
        },

        "ch3": financials,

        "ch4": {
            "dcf": dcf_data,
            "comps": comps,
            "comps_self": {
                "pe": fundamental.get("per"),
                "ev_ebitda": fundamental.get("ev_ebitda"),
                "psr": fundamental.get("psr"),
            },
            "historical_val": [],
            "target_method": "DCF 50% + Comps 50%",
        },

        "ch5": {
            "short_term": [{"event": e, "date": "", "expectation": ""} for e in thesis.get("upcoming_events", [])],
            "mid_term": [{"theme": c, "description": "", "impact": ""} for c in thesis.get("catalysts", [])],
            "long_term_thesis": thesis.get("outlook", {}).get("long", ""),
            "margin_leverage": [],
            "capital_allocation": {"dividend_yield": 0, "buyback_yield": 0, "ma_strategy": ""},
        },

        "ch6": {
            "business_risk": [{"title": r, "desc": "", "prob": "중간", "impact": "높음", "bear_price": bear_price} for r in thesis.get("risks", [])],
            "financial_risk": [],
            "regulatory_risk": [],
            "macro_risk": [],
        },

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
                "pct_from_high": technical.get("pct_from_52w_high"),
                "high_52w": technical.get("high_52w"),
                "low_52w": technical.get("low_52w"),
            },
        },

        "ch8": {
            "final_rating": rating,
            "trade_setup": {
                "entry_zone": [round(price * 0.97, 2), round(price * 1.02, 2)],
                "target1": base_price,
                "target2": bull_price,
                "stop_loss": round(price * 0.88, 2),
                "rr_ratio": round((base_price - price) / (price - price * 0.88), 1) if price and price * 0.12 else 0,
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


# ── Phase 3: 렌더링 ─────────────────────────────────────────────────────────

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


def _fmt_m(val, decimals=1):
    """millions 단위 값 → $x.xB / $xxxM 포맷 (income_stmt, cashflow 전용)"""
    try:
        v = float(val) * 1_000_000
        if abs(v) >= 1e9:
            return f"${v/1e9:.{decimals}f}B"
        elif abs(v) >= 1e6:
            return f"${v/1e6:.0f}M"
        else:
            return f"${v:,.0f}"
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


def _tojson_filter(val, **kwargs):
    """Jinja2 tojson filter — Chart.js 데이터 주입용"""
    return json.dumps(val, ensure_ascii=False, default=str)


def _ensure_v1_defaults(context: dict) -> dict:
    """v1 스키마 필드 기본값 보장 (템플릿 렌더링 오류 방지)"""
    # 최상위 필드 → ch1으로 매핑 (context.json 호환)
    ch1 = context.setdefault("ch1", {})
    for top_key, ch1_key in [
        ("rating", "rating"), ("conviction", "conviction"),
        ("target_price", "target_price"), ("current_price", "current_price"),
    ]:
        if top_key in context and ch1_key not in ch1:
            ch1[ch1_key] = context[top_key]

    # key_metrics 기본값 (최상위 필드에서 추출)
    km = ch1.setdefault("key_metrics", {})
    km.setdefault("market_cap", context.get("market_cap", "—"))
    km.setdefault("fwd_pe", context.get("forward_pe", "—"))
    km.setdefault("ev_ebitda", context.get("ev_ebitda", "—"))
    km.setdefault("revenue_growth", context.get("revenue_growth", "—"))
    km.setdefault("gross_margin", context.get("gross_margin", "—"))
    km.setdefault("fcf_yield", context.get("fcf_yield", "—"))

    # upside_pct 자동 계산
    if "upside_pct" not in ch1 and ch1.get("target_price") and ch1.get("current_price"):
        try:
            ch1["upside_pct"] = round((float(ch1["target_price"]) / float(ch1["current_price"]) - 1) * 100, 1)
        except (ValueError, ZeroDivisionError):
            ch1["upside_pct"] = 0

    # scenarios: probability → prob 매핑 (템플릿 호환)
    scenarios = ch1.get("scenarios", {})
    for case in ["bull", "base", "bear"]:
        sc = scenarios.get(case, {})
        if "probability" in sc and "prob" not in sc:
            sc["prob"] = sc["probability"]

    ch1.setdefault("thesis", ch1.get("investment_thesis", ""))
    ch1.setdefault("thesis_points", [])

    ch2 = context.setdefault("ch2", {})
    ch2.setdefault("platform_overview", ch2.get("business_model", ""))
    ch2.setdefault("platforms", [])
    ch2.setdefault("segments", ch2.get("revenue_segments", []))
    ch2.setdefault("geo", ch2.get("geographic_mix", []))
    ch2.setdefault("competitors", [])

    ch3 = context.setdefault("ch3", {})
    ch3.setdefault("income_stmt", [])
    ch3.setdefault("revenue_breakdown", [])
    ch3.setdefault("sbc_analysis", "")
    ch3.setdefault("income_commentary", "")
    ch3.setdefault("cashflow", ch3.get("cash_flow", []))
    if not ch3.get("cash_flow") and ch3.get("cashflow"):
        ch3["cash_flow"] = ch3["cashflow"]

    # ch3.balance_sheet 기본값
    bs = ch3.setdefault("balance_sheet", {})
    bs.setdefault("total_assets", "—")
    bs.setdefault("net_cash", "—")
    bs.setdefault("roe", "—")
    bs.setdefault("debt_ratio", "—")

    ch4 = context.setdefault("ch4", {})
    ch4.setdefault("dcf_commentary", "")
    ch4.setdefault("comps_commentary", "")
    ch4.setdefault("comps", [])
    ch4.setdefault("comps_self", {})
    dcf = ch4.setdefault("dcf", {})
    dcf.setdefault("sensitivity_headers", dcf.get("labels_tgr", []))
    dcf.setdefault("sensitivity_row_labels", dcf.get("labels_wacc", []))
    dcf.setdefault("sensitivity_matrix", dcf.get("matrix", []))
    dcf.setdefault("current_price", context.get("current_price"))
    dcf.setdefault("fair_value", None)
    if dcf.get("fair_value") and dcf.get("current_price"):
        try:
            dcf.setdefault("upside", round((float(dcf["fair_value"]) / float(dcf["current_price"]) - 1) * 100, 1))
        except (ValueError, ZeroDivisionError):
            dcf.setdefault("upside", None)

    ch5 = context.setdefault("ch5", {})
    ch5.setdefault("short_term", [])
    ch5.setdefault("mid_term", [])

    ch6 = context.setdefault("ch6", {})
    ch6.setdefault("risks", [])
    # risks → 카테고리별 분류 (템플릿 호환)
    if ch6.get("risks") and not ch6.get("business_risk"):
        for r in ch6["risks"]:
            cat = r.get("category", "Business").lower()
            if "business" in cat or "competitive" in cat:
                ch6.setdefault("business_risk", []).append(r)
            elif "financial" in cat:
                ch6.setdefault("financial_risk", []).append(r)
            elif "regulatory" in cat:
                ch6.setdefault("regulatory_risk", []).append(r)
            elif "macro" in cat:
                ch6.setdefault("macro_risk", []).append(r)
            else:
                ch6.setdefault("business_risk", []).append(r)

    ch7 = context.setdefault("ch7", {})
    ch7.setdefault("perf_chart_data", [])
    ch7.setdefault("macro_commentary", "")

    ch8 = context.setdefault("ch8", {})
    ch8.setdefault("kpis", [])
    ch8.setdefault("conclusion", "")
    ch8.setdefault("summary", "")
    ch8.setdefault("rating", ch1.get("rating", "HOLD"))
    ch8.setdefault("trade_setup", {})
    ch8.setdefault("monitoring", [])
    ch8.setdefault("next_update", {})

    return context


def generate_equity_report(context: dict, symbol: str) -> dict:
    """context → HTML (크림) + PDF (크림) + JSON 저장"""
    context = _ensure_v1_defaults(context)
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

    # HTML (크림 테마)
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
        env.filters["fmt_num"] = _fmt_num
        env.filters["fmt_m"] = _fmt_m
        env.filters["fmt_pct"] = _fmt_pct
        env.filters["pct_class"] = _pct_class
        env.filters["abs"] = abs
        env.filters["tojson"] = _tojson_filter

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

    # PDF (크림 테마)
    try:
        from jinja2 import Environment, FileSystemLoader
        from weasyprint import HTML as WeasyprintHTML
        from weasyprint.text.fonts import FontConfiguration

        env_pdf = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
        env_pdf.filters["fmt_num"] = _fmt_num
        env_pdf.filters["fmt_m"] = _fmt_m
        env_pdf.filters["fmt_pct"] = _fmt_pct
        env_pdf.filters["pct_class"] = _pct_class
        env_pdf.filters["abs"] = abs
        env_pdf.filters["tojson"] = _tojson_filter

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


# ── Email ────────────────────────────────────────────────────────────────────

def send_email(symbol: str, report_date: str, html_path: str = None, pdf_path: str = None, context: dict = None):
    """Gmail SMTP로 Equity Research Report 이메일 발송 (PDF 첨부)"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    smtp_user = os.environ.get("GMAIL_ADDRESS", "").strip()
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    to_email = os.environ.get("REPORT_EMAIL_TO", "").strip()

    if not all([smtp_user, smtp_pass, to_email]):
        print("  [email] 설정 누락 (GMAIL_ADDRESS, GMAIL_APP_PASSWORD, REPORT_EMAIL_TO)", file=sys.stderr)
        return False

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[Equity Research] {symbol} — {report_date}"
    msg["From"] = smtp_user
    msg["To"] = to_email

    # HTML 본문 — equity_email.html (Gmail 호환 요약), context 없으면 기본 텍스트
    if context:
        try:
            from jinja2 import Environment, FileSystemLoader
            env_mail = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
            env_mail.filters["fmt_num"] = _fmt_num
            env_mail.filters["fmt_m"] = _fmt_m
            env_mail.filters["fmt_pct"] = _fmt_pct
            env_mail.filters["pct_class"] = _pct_class
            template_mail = env_mail.get_template("equity_email.html")
            email_html = template_mail.render(**context)
            msg.attach(MIMEText(email_html, "html", "utf-8"))
            print("  [email] equity_email.html 렌더링 완료", file=sys.stderr)
        except Exception as e:
            print(f"  [email] 이메일 템플릿 렌더링 실패: {e}", file=sys.stderr)
            msg.attach(MIMEText(f"<h1>{symbol} Equity Research — {report_date}</h1><p>PDF 첨부 확인</p>", "html", "utf-8"))
    else:
        msg.attach(MIMEText(f"<h1>{symbol} Equity Research Report — {report_date}</h1><p>PDF 첨부 확인</p>", "html", "utf-8"))

    # PDF 첨부
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_part = MIMEApplication(f.read(), _subtype="pdf")
            filename = f"{symbol}-{report_date}.pdf"
            pdf_part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(pdf_part)
        size_kb = os.path.getsize(pdf_path) / 1024
        print(f"  [email] PDF 첨부: {filename} ({size_kb:.0f}KB)", file=sys.stderr)
    else:
        print("  [email] PDF 없음 — 본문만 발송", file=sys.stderr)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"  [email] 발송 완료 → {to_email}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  [email] 발송 실패: {e}", file=sys.stderr)
        return False


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    symbol = args[0].upper() if args else "PLTR"
    do_send = "--send" in flags

    # --context 플래그: Claude Code에서 생성한 prose JSON 로드
    context_path = None
    for f in flags:
        if f.startswith("--context="):
            context_path = f.split("=", 1)[1]
    if not context_path:
        # 기본 경로: docs/reports/equity/{SYMBOL}-context.json
        default_ctx = OUTPUT_DIR / f"{symbol}-context.json"
        if default_ctx.exists():
            context_path = str(default_ctx)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  Equity Research Report — {symbol}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if context_path and os.path.exists(context_path):
        print(f"  [context] 외부 JSON 로드: {context_path}", file=sys.stderr)
        with open(context_path, "r", encoding="utf-8") as f:
            context = json.load(f)
        context = _ensure_v1_defaults(context)
    else:
        print(f"  [context] API 데이터 수집 모드", file=sys.stderr)
        context = build_report_context(symbol)

    results = generate_equity_report(context, symbol)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  생성 완료:", file=sys.stderr)
    for fmt, path in results.items():
        if path:
            print(f"  [{fmt.upper()}] {path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    if do_send:
        report_date = context.get("report_date", str(date.today()))
        send_email(symbol, report_date, results.get("html"), results.get("pdf"), context=context)


if __name__ == "__main__":
    main()
