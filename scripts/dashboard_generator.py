"""
트레이딩 대시보드 HTML 생성기
context dict → templates/trading_dashboard.html → docs/dashboard.html
"""
import sys
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _signal_class(rating: str) -> str:
    """뷰 등급 → CSS 클래스"""
    m = {"BUY": "sig-buy", "HOLD": "sig-hold", "WATCH": "sig-watch", "REDUCE": "sig-reduce"}
    return m.get(rating, "sig-hold")


def _pct_class(val) -> str:
    """등락률 → CSS 클래스"""
    try:
        v = float(val)
        return "up" if v >= 0 else "dn"
    except (TypeError, ValueError):
        return "nt"


def _fmt_pct(val, sign=True) -> str:
    try:
        v = float(val)
        prefix = "+" if (sign and v >= 0) else ""
        return f"{prefix}{v:.2f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_price(val, prefix="$") -> str:
    try:
        v = float(val)
        return f"{prefix}{v:,.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_value(val, prefix="$") -> str:
    try:
        v = float(val)
        return f"{prefix}{v:,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def _arrow(val) -> str:
    try:
        return "▲" if float(val) >= 0 else "▼"
    except (TypeError, ValueError):
        return "—"


def _risk_level(rsi, vol_ratio, pct_from_high) -> tuple[str, int]:
    """리스크 레벨 계산 → (label, score 0-10)"""
    score = 5
    if rsi:
        if rsi > 75:
            score += 2
        elif rsi > 65:
            score += 1
        elif rsi < 30:
            score -= 1
    if vol_ratio and vol_ratio > 2.0:
        score += 1
    if pct_from_high and pct_from_high < -30:
        score -= 1
    score = max(1, min(10, score))
    if score <= 3:
        label = "낮음"
        color = "var(--up)"
    elif score <= 6:
        label = "중간"
        color = "var(--gold)"
    else:
        label = "높음"
        color = "var(--down)"
    return label, score, color


def _target_prices(tech: dict, thesis: dict) -> dict:
    """Bull/Base/Bear 목표가 계산"""
    price = tech.get("current_price", 0) or 0
    ma200 = tech.get("ma200", price * 0.82) or price * 0.82
    high52 = tech.get("high_52w", price * 1.30) or price * 1.30

    bull_target = round(max(price * 1.28, high52 * 0.98), 2)
    base_target = round(price * 1.13, 2)
    bear_target = round(max(price * 0.78, ma200 * 0.95), 2)

    # 확률 (단순 rule-based)
    rsi = tech.get("rsi", 50) or 50
    if rsi > 65:
        bull_prob, base_prob, bear_prob = 25, 45, 30
    elif rsi < 35:
        bull_prob, base_prob, bear_prob = 40, 40, 20
    else:
        bull_prob, base_prob, bear_prob = 30, 45, 25

    return {
        "bull": {"price": bull_target, "prob": bull_prob, "note": thesis.get("bull", "")[:60]},
        "base": {"price": base_target, "prob": base_prob, "note": "현 thesis 유지, 카탈리스트 대기"},
        "bear": {"price": bear_target, "prob": bear_prob, "note": thesis.get("bear", "")[:60]},
    }


def _build_ticker_data(us_indices: dict, commodities: dict) -> list:
    """티커바 데이터 구성"""
    items = []

    def _item(name, data, key_close="close", key_pct="change_pct"):
        if not data or data.get("error"):
            return None
        c = data.get(key_close, 0) or 0
        p = data.get(key_pct, 0) or 0
        return {"name": name, "val": c, "pct": p}

    idx_map = [
        ("NQ", "NASDAQ100"),
        ("S&P", "S&P500"),
        ("VIX", "VIX"),
        ("KOSPI", "KOSPI"),
    ]
    for label, key in idx_map:
        d = us_indices.get(key) or us_indices.get(key.lower())
        if not d:
            d = {}
        item = _item(label, d)
        if item:
            items.append(item)

    com_map = [
        ("10Y", "US10Y"),
        ("DXY", "DXY"),
        ("Gold", "Gold"),
        ("WTI", "WTI"),
    ]
    for label, key in com_map:
        d = commodities.get(key) or commodities.get(key.lower())
        if not d:
            d = {}
        item = _item(label, d)
        if item:
            items.append(item)

    return items


def _top_bottom_sector(sectors_daily: dict) -> tuple[str, float, str, float]:
    """섹터 상위/하위 추출"""
    if not sectors_daily:
        return "Tech", 0.0, "Utilities", 0.0
    items = [(k, v.get("change_pct", 0) if isinstance(v, dict) else float(v or 0))
             for k, v in sectors_daily.items()]
    items.sort(key=lambda x: x[1], reverse=True)
    top_name, top_pct = items[0] if items else ("Tech", 0.0)
    bot_name, bot_pct = items[-1] if len(items) > 1 else ("Utilities", 0.0)
    return top_name, top_pct, bot_name, bot_pct


def _build_dashboard_context(context: dict) -> dict:
    """daily_report context → dashboard 전용 context 변환"""
    sim_summary = context.get("sim_summary", {})
    sim_stocks = context.get("sim_stocks", [])
    us_indices = context.get("us_indices", {})
    commodities = context.get("commodities", {})
    sectors_daily = context.get("sectors_daily", {})
    cycle_info = context.get("cycle_info", {})

    total_capital = sim_summary.get("total_capital", 20000)
    total_value = sim_summary.get("total_value", total_capital)
    daily_pct = sim_summary.get("daily_return_pct", 0.0)
    cum_pct = sim_summary.get("cumulative_return_pct", 0.0)
    daily_change = total_value - total_value / (1 + daily_pct / 100) if daily_pct else 0
    positions = sim_summary.get("positions", [])

    # 티커바
    ticker_items = _build_ticker_data(us_indices, commodities)

    # 섹터 리더
    top_sector, top_pct, bot_sector, bot_pct = _top_bottom_sector(sectors_daily)

    # Market overview 4-card
    nasdaq_d = us_indices.get("NASDAQ100") or us_indices.get("NASDAQ") or {}
    vix_d = us_indices.get("VIX") or {}
    sp_d = us_indices.get("S&P500") or {}

    market_cards = [
        {
            "name": "NASDAQ 100",
            "val": _fmt_value(nasdaq_d.get("close", 0), "$"),
            "chg_pct": _fmt_pct(nasdaq_d.get("change_pct", 0)),
            "cls": _pct_class(nasdaq_d.get("change_pct", 0)),
        },
        {
            "name": "S&P 500",
            "val": _fmt_value(sp_d.get("close", 0), "$"),
            "chg_pct": _fmt_pct(sp_d.get("change_pct", 0)),
            "cls": _pct_class(sp_d.get("change_pct", 0)),
        },
        {
            "name": "VIX (공포지수)",
            "val": f"{vix_d.get('close', 0):.1f}" if vix_d.get("close") else "N/A",
            "chg_pct": _fmt_pct(vix_d.get("change_pct", 0)),
            "cls": _pct_class(-(vix_d.get("change_pct", 0) or 0)),  # VIX 하락이 좋음
        },
        {
            "name": f"섹터 리더: {top_sector[:12]}",
            "val": _fmt_pct(top_pct),
            "chg_pct": f"하위: {bot_sector[:10]} {_fmt_pct(bot_pct)}",
            "cls": _pct_class(top_pct),
        },
    ]

    # 종목 패널 데이터 조립
    stock_panels = []
    for stock in sim_stocks:
        sym = stock.get("symbol", "")
        tech = stock.get("technical", {})
        dv = stock.get("daily_view", {})
        thesis = stock.get("thesis", {})
        fund = stock.get("fundamental", {})

        price = tech.get("current_price", 0) or 0
        chg_pct = tech.get("change_pct", 0) or 0
        rsi = tech.get("rsi")
        vol_ratio = tech.get("volume_ratio", 1.0) or 1.0
        pct_from_high = tech.get("pct_from_52w_high", 0) or 0

        risk_label, risk_score, risk_color = _risk_level(rsi, vol_ratio, pct_from_high)
        targets = _target_prices(tech, thesis)
        signal = dv.get("view_rating", "HOLD")
        sig_cls = _signal_class(signal)

        # 포지션에서 현재 가치 찾기
        pos = next((p for p in positions if p["symbol"] == sym), {})
        current_value = pos.get("current_value", pos.get("allocation", 0))
        return_pct = pos.get("return_pct", 0.0)
        weight_pct = current_value / total_value * 100 if total_value else 0

        stock_panels.append({
            "symbol": sym,
            "company": stock.get("company", sym),
            "price": _fmt_price(price),
            "chg_pct": _fmt_pct(chg_pct),
            "chg_cls": _pct_class(chg_pct),
            "arrow": _arrow(chg_pct),
            "signal": signal,
            "sig_cls": sig_cls,
            "return_pct": _fmt_pct(return_pct),
            "return_cls": _pct_class(return_pct),
            "current_value": _fmt_value(current_value),
            "weight_pct": round(weight_pct, 1),
            "metrics": [
                {"label": "RSI(14)", "val": f"{rsi:.0f}" if rsi else "N/A"},
                {"label": "MA50 대비", "val": f"{'▲' if tech.get('above_ma50') else '▼'} ${tech.get('ma50', 0):.2f}" if tech.get('ma50') else "N/A"},
                {"label": "MA200 대비", "val": f"{'▲' if tech.get('above_ma200') else '▼'} ${tech.get('ma200', 0):.2f}" if tech.get('ma200') else "N/A"},
                {"label": "52W 고점比", "val": f"{pct_from_high:.1f}%"},
            ],
            "targets": targets,
            "risk_label": risk_label,
            "risk_score": risk_score,
            "risk_color": risk_color,
            "risk_bar_width": risk_score * 10,
            "insight": dv.get("today", ""),
            "catalyst": dv.get("catalyst", ""),
            "view_reason": dv.get("view_reason", ""),
            "macd_trend": tech.get("macd_trend", "N/A"),
            "vol_ratio": f"{vol_ratio:.1f}x",
            "thesis_short": stock.get("thesis_short", ""),
        })

    # 사이드바 배분 바 (positions 기준)
    alloc_bars = []
    max_val = max((p.get("current_value", 0) for p in positions), default=1)
    for pos in positions:
        cv = pos.get("current_value", pos.get("allocation", 0))
        rp = pos.get("return_pct", 0.0)
        alloc_bars.append({
            "symbol": pos["symbol"],
            "value": _fmt_value(cv),
            "return_pct": _fmt_pct(rp),
            "return_cls": _pct_class(rp),
            "bar_width": round(cv / max_val * 100) if max_val else 0,
            "weight_pct": f"{cv / total_value * 100:.0f}%" if total_value else "0%",
        })

    # Trade Ideas: BUY 종목 우선, 없으면 HOLD
    buy_stocks = [s for s in stock_panels if s["signal"] == "BUY"]
    trade_idea = buy_stocks[0] if buy_stocks else (stock_panels[0] if stock_panels else None)

    # Macro Events
    cycle = cycle_info.get("cycle", "expansion")
    favored = cycle_info.get("sectors", [])[:3]
    macro_events = [
        {"time": "미장 휴장", "name": "Good Friday (4/3)", "meta": "다음 개장: 4/6 (월)", "imp": "imp-high"},
        {"time": "경기사이클", "name": cycle.capitalize(), "meta": f"유리섹터: {', '.join(favored[:2])}", "imp": "imp-mid"},
        {"time": "섹터리더", "name": top_sector, "meta": f"{_fmt_pct(top_pct)} | 하위: {bot_sector} {_fmt_pct(bot_pct)}", "imp": "imp-mid"},
    ]

    # Risk summary
    portfolio_beta = 1.5  # 고성장주 5종목 추정치
    max_loss = total_value * 0.20  # MDD -20% 한도

    return {
        "report_date": context.get("report_date", ""),
        "generated_at": context.get("generated_at", ""),
        "total_value": _fmt_value(total_value),
        "total_capital": _fmt_value(total_capital),
        "daily_change_amt": f"{'+'if daily_change>=0 else ''}{daily_change:,.0f}",
        "daily_pct": _fmt_pct(daily_pct),
        "cum_pct": _fmt_pct(cum_pct),
        "daily_cls": _pct_class(daily_pct),
        "cum_cls": _pct_class(cum_pct),
        "days_running": sim_summary.get("days_running", 1),
        "ticker_items": ticker_items,
        "market_cards": market_cards,
        "stock_panels": stock_panels,
        "alloc_bars": alloc_bars,
        "trade_idea": trade_idea,
        "macro_events": macro_events,
        "portfolio_beta": portfolio_beta,
        "max_loss": _fmt_value(max_loss),
        "cycle": cycle.capitalize(),
        "best_sym": sim_summary.get("best_performer", {}).get("symbol", ""),
        "best_pct": _fmt_pct(sim_summary.get("best_performer", {}).get("return_pct", 0)),
    }


def generate_dashboard(context: dict, output_path: str) -> bool:
    """daily_report context → trading_dashboard.html 생성"""
    try:
        from jinja2 import Environment, FileSystemLoader
        templates_dir = Path(__file__).parent.parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)

        # 커스텀 필터
        env.filters["abs"] = abs
        env.filters["fmt_pct"] = _fmt_pct
        env.filters["fmt_price"] = _fmt_price

        template = env.get_template("trading_dashboard.html")
        dash_ctx = _build_dashboard_context(context)
        html = template.render(**dash_ctx)

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"  [dashboard] 저장 완료: {out}", file=sys.stderr)
        return True

    except Exception as e:
        print(f"  [dashboard] 생성 실패: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return False


if __name__ == "__main__":
    # 독립 테스트 실행 (mock context)
    import json
    from simulation_tracker import run_daily_update

    sim = run_daily_update()
    test_context = {
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sim_summary": sim,
        "sim_stocks": [],
        "us_indices": {},
        "commodities": {},
        "sectors_daily": {},
        "cycle_info": {"cycle": "expansion", "sectors": ["Technology", "Industrials"]},
    }
    generate_dashboard(test_context, "../docs/dashboard.html")
