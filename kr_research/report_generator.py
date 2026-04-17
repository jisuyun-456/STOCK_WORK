"""KR Analysis Report Generator — 인터랙티브 HTML 리포트 생성.

Goldman Sachs / JP Morgan 수준의 8챕터 탭 구조.
디자인: Apple 스타일 (SF Pro Display / SF Mono / Apple 컬러 팔레트).
출력: reports/kr/{DATE}-{TICKER}-analysis.html
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from kr_research.models import KRAnalysisResult

_logger = logging.getLogger("kr_research.report_generator")
_REPORTS_DIR = Path(__file__).parent.parent / "reports" / "kr"
_STATE_DIR = Path(__file__).parent.parent / "state"

# ── CSS + HTML template constants ──────────────────────────────────────────

_CSS = """
:root {
  --cream:    #F5F5F7;  --cream2:   #E8E8ED;
  --surface:  #FFFFFF;  --ink:      #1D1D1F;
  --ink2:     #3A3A3C;  --ink3:     #6E6E73;
  --border:   #D2D2D7;
  --blue:     #0071E3;  --blue-bg:  #F0F6FF;
  --amber:    #FF9500;  --amber-bg: #FFF5E0;
  --up:       #34C759;  --up-bg:    #E8FAF0;
  --dn:       #FF3B30;  --dn-bg:    #FFF0EF;
  --nav-bg:   #1D1D1F;
  --shadow:   0 1px 3px rgba(0,0,0,0.08),0 1px 2px rgba(0,0,0,0.06);
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--cream); color:var(--ink); font-family:'SF Pro Display',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; font-size:13px; line-height:1.65; -webkit-font-smoothing:antialiased; }

/* NAV */
.nav { background:linear-gradient(180deg,#2D2D2F 0%,var(--nav-bg) 100%); border-bottom:1px solid rgba(255,255,255,0.12); padding:0 32px; height:52px; display:flex; align-items:center; position:sticky; top:0; z-index:100; }
.nav-logo { font-size:15px; font-weight:700; color:#F5F5F7; margin-right:24px; letter-spacing:-0.02em; }
.nav-logo span { color:var(--blue); }
.nav-tabs { display:flex; gap:2px; flex:1; }
.nav-tab { padding:5px 13px; border-radius:6px; font-size:11.5px; font-weight:500; font-family:'SF Mono','Fira Code',monospace; letter-spacing:0.02em; cursor:pointer; color:#86868B; background:transparent; border:none; transition:all 0.15s ease; white-space:nowrap; }
.nav-tab:hover:not(.active) { background:rgba(255,255,255,0.10); color:#AEAEB2; }
.nav-tab.active { background:var(--blue); color:#fff; font-weight:600; }
.nav-meta { margin-left:auto; font-family:'SF Mono','Fira Code',monospace; font-size:10px; color:#636366; letter-spacing:0.06em; text-align:right; line-height:1.4; }

/* PANELS */
.panel { display:none; }
.panel.active { display:block; }

/* COMPANY HEADER */
.co-header { background:linear-gradient(135deg,#2D2D2F 0%,var(--nav-bg) 60%,#000 100%); padding:24px 32px 22px; position:relative; overflow:hidden; }
.co-header::before { content:''; position:absolute; inset:0; background:linear-gradient(135deg,rgba(0,113,227,0.10) 0%,transparent 55%); pointer-events:none; }
.co-sub { font-family:'SF Mono','Fira Code',monospace; font-size:10px; color:#636366; letter-spacing:0.12em; text-transform:uppercase; margin-bottom:6px; }
.co-name { font-size:28px; font-weight:700; color:#F5F5F7; letter-spacing:-0.03em; margin-bottom:3px; }
.co-desc { font-size:12px; color:#86868B; margin-bottom:16px; }
.co-rating-row { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.badge { display:inline-flex; align-items:center; padding:5px 12px; border-radius:6px; font-family:'SF Mono','Fira Code',monospace; font-size:12px; font-weight:600; letter-spacing:0.04em; }
.badge-buy  { background:var(--up);   color:#fff; }
.badge-hold { background:var(--amber);color:#fff; }
.badge-sell { background:var(--dn);   color:#fff; }
.badge-veto { background:#3A3A3C;     color:#F5F5F7; }
.price-chip { background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.12); border-radius:10px; padding:8px 14px; }
.price-label { font-size:10px; color:#636366; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:2px; }
.price-display { font-family:'SF Mono','Fira Code',monospace; font-size:17px; font-weight:600; color:#F5F5F7; }
.up-label { color:var(--up); font-family:'SF Mono','Fira Code',monospace; font-size:11px; }
.dn-label { color:var(--dn); font-family:'SF Mono','Fira Code',monospace; font-size:11px; }

/* LAYOUT */
.main { padding:24px 32px; max-width:1280px; margin:0 auto; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; box-shadow:var(--shadow); }
.card-label { font-family:'SF Mono','Fira Code',monospace; font-size:9px; letter-spacing:0.12em; text-transform:uppercase; color:var(--ink3); margin-bottom:8px; }
.section-title { font-family:'SF Mono','Fira Code',monospace; font-size:9px; letter-spacing:0.14em; text-transform:uppercase; color:var(--ink3); padding:16px 0 8px; border-bottom:1px solid var(--border); margin-bottom:12px; }

/* THESIS */
.thesis { background:var(--blue-bg); border:1px solid #C5DCF8; border-left:3px solid var(--blue); border-radius:12px; padding:16px 18px; margin-bottom:16px; }
.thesis-label { font-family:'SF Mono','Fira Code',monospace; font-size:9px; letter-spacing:0.14em; color:var(--blue); text-transform:uppercase; margin-bottom:8px; font-weight:600; }
.thesis-text { font-size:13px; color:var(--ink2); line-height:1.75; }

/* METRICS */
.metrics-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-bottom:16px; }
.metric-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:13px 14px; box-shadow:var(--shadow); }
.metric-label { font-size:10px; color:var(--ink3); margin-bottom:4px; }
.metric-val { font-family:'SF Mono','Fira Code',monospace; font-size:15px; font-weight:600; color:var(--ink); }
.metric-sub { font-size:10px; margin-top:2px; font-family:'SF Mono','Fira Code',monospace; }
.up { color:var(--up); } .dn { color:var(--dn); } .neutral { color:var(--amber); }

/* SCENARIOS */
.scenarios { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-bottom:16px; }
.sc { border-radius:12px; padding:16px; border:1px solid var(--border); }
.sc-bull { background:var(--up-bg);  border-color:#A8E6C0; }
.sc-base { background:var(--cream); }
.sc-bear { background:var(--dn-bg);  border-color:#FFB8B5; }
.sc-type { font-family:'SF Mono','Fira Code',monospace; font-size:9px; letter-spacing:0.12em; color:var(--ink3); text-transform:uppercase; margin-bottom:6px; }
.sc-price { font-family:'SF Mono','Fira Code',monospace; font-size:20px; font-weight:600; margin-bottom:4px; }
.sc-bull .sc-price { color:var(--up); } .sc-base .sc-price { color:var(--ink); } .sc-bear .sc-price { color:var(--dn); }
.sc-text { font-size:12px; color:var(--ink2); line-height:1.65; }

/* MARKET BARS */
.market-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
.mkt-bars { display:flex; flex-direction:column; gap:10px; }
.mkt-row { display:flex; align-items:center; gap:12px; }
.mkt-name { font-family:'SF Mono','Fira Code',monospace; font-size:11px; color:var(--ink2); width:68px; }
.mkt-bar-track { flex:1; height:5px; background:var(--cream2); border-radius:3px; overflow:hidden; }
.mkt-bar-fill { height:100%; border-radius:3px; width:0; transition:width 1.1s cubic-bezier(0.4,0,0.2,1); }
.mkt-bar-up { background:var(--up); } .mkt-bar-dn { background:var(--dn); } .mkt-bar-neu { background:var(--amber); }
.mkt-val { font-family:'SF Mono','Fira Code',monospace; font-size:12px; color:var(--ink); width:100px; text-align:right; }
.mkt-pct { font-family:'SF Mono','Fira Code',monospace; font-size:11px; width:56px; text-align:right; }

/* TECH TABLE */
.tech-table { width:100%; border-collapse:collapse; font-size:12.5px; margin-bottom:16px; }
.tech-table th { background:var(--nav-bg); color:#F5F5F7; padding:7px 12px; text-align:left; font-family:'SF Mono','Fira Code',monospace; font-size:10px; letter-spacing:0.06em; font-weight:500; }
.tech-table td { padding:9px 12px; border-bottom:1px solid var(--border); color:var(--ink2); }
.tech-table tr:last-child td { border-bottom:none; }
.tech-table tr:nth-child(even) td { background:var(--cream); }
.signal-tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; font-family:'SF Mono','Fira Code',monospace; }
.sig-up   { background:var(--up-bg);    color:var(--up); }
.sig-warn { background:var(--amber-bg); color:var(--amber); }
.sig-dn   { background:var(--dn-bg);    color:var(--dn); }

/* PRICE LADDER */
.ladder-row { display:flex; align-items:center; padding:7px 4px; border-bottom:1px solid var(--border); }
.ladder-row:last-child { border-bottom:none; }
.ladder-price { width:150px; text-align:right; font-family:'SF Mono','Fira Code',monospace; font-size:12px; font-weight:600; padding-right:14px; color:var(--ink3); }
.ladder-line  { flex:1; height:2px; background:var(--cream2); }
.ladder-label { padding-left:14px; font-family:'SF Mono','Fira Code',monospace; font-size:11px; color:var(--ink3); }
.ladder-current { background:rgba(0,113,227,0.07); border-radius:6px; margin:2px 0; }
.ladder-current .ladder-price { color:var(--blue); }
.ladder-current .ladder-line  { background:var(--blue); height:3px; }
.ladder-current .ladder-label { color:var(--blue); font-weight:600; }
.ladder-target1 .ladder-price { color:var(--up); } .ladder-target1 .ladder-line { background:var(--up-bg); }
.ladder-target2 .ladder-price { color:#30B652; }   .ladder-target2 .ladder-line { background:var(--up-bg); }
.ladder-stop .ladder-price    { color:var(--dn); } .ladder-stop .ladder-line    { background:var(--dn-bg); }
.ladder-entry .ladder-price   { color:var(--amber); } .ladder-entry .ladder-line { background:var(--amber-bg); }

/* TRADE BOX */
.trade-box { background:var(--nav-bg); border-radius:12px; padding:18px 20px; margin-bottom:16px; position:relative; overflow:hidden; }
.trade-box::after { content:''; position:absolute; inset:0; background:linear-gradient(135deg,rgba(0,113,227,0.10) 0%,transparent 60%); pointer-events:none; }
.trade-box .card-label { color:var(--blue); }
.trade-row { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; }
.trade-item .tlabel { font-size:10px; color:#636366; margin-bottom:4px; font-family:'SF Mono','Fira Code',monospace; letter-spacing:0.04em; }
.trade-item .tval   { font-family:'SF Mono','Fira Code',monospace; font-size:14px; font-weight:600; color:#F5F5F7; }
.trade-item .tsub   { font-size:10px; font-family:'SF Mono','Fira Code',monospace; margin-top:2px; color:#636366; }
.trade-item.t1 .tval   { color:var(--up); }
.trade-item.t2 .tval   { color:#30D158; }
.trade-item.stop .tval { color:var(--dn); }
.trade-item.rr .tval   { color:var(--blue); font-size:18px; }
.trade-trigger { margin-top:14px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.08); font-size:11.5px; color:#86868B; font-family:'SF Mono','Fira Code',monospace; line-height:1.75; }
.trigger-label { color:var(--blue); font-size:9px; text-transform:uppercase; letter-spacing:0.12em; margin-bottom:4px; }

/* FACTORS */
.factors-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
.factor-col-header { display:flex; align-items:center; gap:8px; font-weight:600; font-size:13px; margin-bottom:12px; padding-bottom:8px; border-bottom:2px solid; }
.fch-up { border-color:var(--up); color:var(--up); }
.fch-dn { border-color:var(--dn); color:var(--dn); }
.factor-item { display:flex; align-items:flex-start; gap:8px; padding:10px 0; border-bottom:1px solid var(--border); }
.factor-item:last-child { border-bottom:none; }
.factor-icon { width:18px; height:18px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:10px; flex-shrink:0; margin-top:1px; }
.fi-up { background:var(--up-bg); color:var(--up); }
.fi-dn { background:var(--dn-bg); color:var(--dn); }
.factor-text { font-size:12.5px; color:var(--ink2); line-height:1.6; }

/* RISK */
.risk-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.risk-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 15px; }
.risk-title { font-size:13px; font-weight:600; color:var(--ink); margin-bottom:4px; }
.risk-desc  { font-size:12px; color:var(--ink2); line-height:1.65; }
.risk-tag { display:inline-block; padding:1px 7px; border-radius:3px; font-size:10px; font-family:'SF Mono','Fira Code',monospace; margin-top:6px; }
.rt-high { background:var(--dn-bg);    color:var(--dn); }
.rt-mid  { background:var(--amber-bg); color:var(--amber); }
.rt-low  { background:var(--up-bg);    color:var(--up); }

/* SUPPLY */
.flow-item { display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid var(--border); }
.flow-item:last-child { border-bottom:none; }
.flow-name { font-size:12.5px; color:var(--ink2); }
.flow-val  { font-family:'SF Mono','Fira Code',monospace; font-size:13px; font-weight:500; }

/* CHECKLIST */
.check-item { display:flex; gap:10px; padding:10px 12px; border-radius:8px; margin-bottom:6px; background:var(--cream); border:1px solid var(--border); }
.check-num  { font-family:'SF Mono','Fira Code',monospace; font-size:11px; color:var(--blue); font-weight:600; flex-shrink:0; width:20px; }
.check-text { font-size:12.5px; color:var(--ink2); line-height:1.6; }

/* FOOTER */
.report-footer { margin-top:32px; padding-top:16px; border-top:1px solid var(--border); font-size:11px; color:var(--ink3); font-family:'SF Mono','Fira Code',monospace; line-height:1.7; }

/* ANIMATION */
@keyframes fadeUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
.panel.active > * { animation:fadeUp 0.3s ease both; }
.panel.active > *:nth-child(2){animation-delay:0.06s}
.panel.active > *:nth-child(3){animation-delay:0.12s}
.panel.active > *:nth-child(4){animation-delay:0.18s}
"""


# ── Helper functions ────────────────────────────────────────────────────────

def _fmt_price(p: float | None, unit: str = "원") -> str:
    if p is None:
        return "—"
    return f"{int(p):,}{unit}"


def _pct(current: float | None, target: float | None) -> str:
    if current and target and current > 0:
        return f"{(target / current - 1) * 100:+.1f}%"
    return ""


def _badge_class(verdict: str) -> str:
    return {"BUY": "buy", "SELL": "sell", "VETO": "veto"}.get(verdict.upper(), "hold")


def _rr_ratio(entry_mid: float | None, target: float | None, stop: float | None) -> str:
    if entry_mid and target and stop and entry_mid > 0:
        reward = target - entry_mid
        risk = entry_mid - stop
        if risk > 0:
            return f"{reward / risk:.1f}"
    return "—"


def _fetch_market_context() -> dict:
    """KOSPI/USD-KRW from state/, NASDAQ/KOSDAQ from yfinance."""
    ctx: dict = {}
    try:
        state_path = _STATE_DIR / "kr_market_state.json"
        if state_path.exists():
            with open(state_path, encoding="utf-8") as f:
                st = json.load(f)
            kospi = st.get("kospi", {})
            ctx["kospi_close"] = kospi.get("close", 0)
            ctx["kospi_chg"] = kospi.get("change_1d_pct", 0)
            ctx["kospi_sma200"] = kospi.get("sma200", 0)
            usdkrw = st.get("usdkrw", {})
            ctx["usdkrw"] = usdkrw.get("rate", 0)
    except Exception as e:
        _logger.debug("market_context state load: %s", e)

    try:
        import yfinance as yf
        ixic = yf.Ticker("^IXIC").history(period="2d")
        if not ixic.empty and len(ixic) >= 2:
            ctx["nasdaq_close"] = round(float(ixic["Close"].iloc[-1]))
            ctx["nasdaq_chg"] = round((ixic["Close"].iloc[-1] / ixic["Close"].iloc[-2] - 1) * 100, 2)
    except Exception as e:
        _logger.debug("nasdaq fetch: %s", e)

    try:
        import yfinance as yf
        kq = yf.Ticker("^KQ11").history(period="2d")
        if not kq.empty and len(kq) >= 2:
            ctx["kosdaq_close"] = round(float(kq["Close"].iloc[-1]))
            ctx["kosdaq_chg"] = round((kq["Close"].iloc[-1] / kq["Close"].iloc[-2] - 1) * 100, 2)
    except Exception as e:
        _logger.debug("kosdaq fetch: %s", e)

    return ctx


def _market_bar_html(ctx: dict) -> str:
    """시장 컨텍스트 바 HTML 생성."""
    rows = []

    def _bar_row(name: str, close_val, chg_val, bar_pct: int) -> str:
        if close_val is None:
            return ""
        bar_cls = "mkt-bar-up" if (chg_val or 0) >= 0 else "mkt-bar-dn"
        chg_cls = "up" if (chg_val or 0) >= 0 else "dn"
        chg_str = f"{chg_val:+.1f}%" if chg_val is not None else "—"
        close_str = f"{close_val:,.0f}" if isinstance(close_val, (int, float)) else str(close_val)
        return (
            f'<div class="mkt-row">'
            f'<div class="mkt-name">{name}</div>'
            f'<div class="mkt-bar-track"><div class="mkt-bar-fill {bar_cls}" data-pct="{bar_pct}"></div></div>'
            f'<div class="mkt-val">{close_str}p</div>'
            f'<div class="mkt-pct {chg_cls}">{chg_str}</div>'
            f'</div>'
        )

    if ctx.get("kospi_close"):
        chg = ctx.get("kospi_chg", 0)
        pct = min(90, max(30, 60 + int(chg * 15)))
        rows.append(_bar_row("KOSPI", ctx["kospi_close"], chg, pct))

    if ctx.get("kosdaq_close"):
        chg = ctx.get("kosdaq_chg", 0)
        pct = min(85, max(25, 55 + int(chg * 15)))
        rows.append(_bar_row("KOSDAQ", ctx["kosdaq_close"], chg, pct))

    if ctx.get("nasdaq_close"):
        chg = ctx.get("nasdaq_chg", 0)
        pct = min(90, max(30, 65 + int(chg * 10)))
        rows.append(_bar_row("NASDAQ", ctx["nasdaq_close"], chg, pct))

    if ctx.get("usdkrw"):
        rows.append(
            f'<div class="mkt-row">'
            f'<div class="mkt-name">USD/KRW</div>'
            f'<div class="mkt-bar-track"><div class="mkt-bar-fill mkt-bar-neu" data-pct="55"></div></div>'
            f'<div class="mkt-val">{ctx["usdkrw"]:,.0f}원</div>'
            f'<div class="mkt-pct neutral">환율</div>'
            f'</div>'
        )

    if not rows:
        return '<div class="mkt-row" style="color:var(--ink3);font-size:12px">시장 데이터 없음</div>'
    return "\n".join(rows)


def _tech_table_html(td: dict) -> str:
    if not td:
        return "<p style='color:var(--ink3);font-size:12px'>기술 데이터 없음</p>"
    cp = td.get("current_price")
    rows = []

    def _sig(val, key):
        s = td.get(key, "")
        if "과매수" in s or "주의" in s:
            return f'<span class="signal-tag sig-warn">{s}</span>'
        if "과매도" in s or "기회" in s or "골든" in s:
            return f'<span class="signal-tag sig-up">{s}</span>'
        if "데드" in s or "하락" in s:
            return f'<span class="signal-tag sig-dn">{s}</span>'
        if s:
            return f'<span class="signal-tag sig-up">{s}</span>'
        return "—"

    if cp and "sma20" in td:
        sig = "상방 ✅" if cp > td["sma20"] else "하방 ⚠️"
        cls = "sig-up" if cp > td["sma20"] else "sig-warn"
        rows.append(f"<tr><td>SMA20</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['sma20']:,}원</td><td><span class='signal-tag {cls}'>{sig}</span></td></tr>")
    if cp and "sma60" in td:
        sig = "상방 ✅" if cp > td["sma60"] else "하방 ⚠️"
        cls = "sig-up" if cp > td["sma60"] else "sig-warn"
        rows.append(f"<tr><td>SMA60</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['sma60']:,}원</td><td><span class='signal-tag {cls}'>{sig}</span></td></tr>")
    if cp and "sma200" in td:
        sig = "상방 ✅" if cp > td["sma200"] else "하방 ⚠️"
        cls = "sig-up" if cp > td["sma200"] else "sig-warn"
        rows.append(f"<tr><td>SMA200</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['sma200']:,}원</td><td><span class='signal-tag {cls}'>{sig}</span></td></tr>")
    if "rsi14" in td:
        rows.append(f"<tr><td>RSI(14)</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['rsi14']}</td><td>{_sig(td['rsi14'], 'rsi_signal')}</td></tr>")
    if "macd" in td:
        rows.append(f"<tr><td>MACD</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['macd']:+,.0f}</td><td>{_sig(td.get('macd_hist',0), 'macd_cross')}</td></tr>")
    if "bb_upper" in td:
        rows.append(f"<tr><td>볼린저 상단</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['bb_upper']:,}원</td><td><span class='signal-tag sig-warn'>위치 {td.get('bb_pct','-')}%</span></td></tr>")
        rows.append(f"<tr><td>볼린저 하단</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['bb_lower']:,}원</td><td>{_sig(td.get('bb_pct',50), 'bb_signal')}</td></tr>")

    if not rows:
        return "<p style='color:var(--ink3);font-size:12px'>기술 데이터 없음</p>"
    return f"""<table class="tech-table"><thead><tr><th>지표</th><th>값</th><th>신호</th></tr></thead><tbody>{"".join(rows)}</tbody></table>"""


def _price_ladder_html(td: dict, v) -> str:
    cp = td.get("current_price")
    levels: list[tuple[float, str, str]] = []  # (price, label, css_class)

    if v.target_price_2:
        levels.append((v.target_price_2, "T2 목표가", "ladder-target2"))
    if v.target_price:
        levels.append((v.target_price, "T1 목표가", "ladder-target1"))
    if td.get("high_52w"):
        levels.append((td["high_52w"], "52주 고가", ""))
    if cp:
        levels.append((cp, "현재가 ◀", "ladder-current"))
    if v.entry_price_high:
        levels.append((v.entry_price_high, f"매수 구간 상단", "ladder-entry"))
    if v.entry_price_low:
        levels.append((v.entry_price_low, f"매수 구간 하단", "ladder-entry"))
    if td.get("sma20"):
        levels.append((td["sma20"], "SMA20 (지지)", ""))
    if v.stop_loss:
        levels.append((v.stop_loss, "손절가", "ladder-stop"))
    if td.get("sma200"):
        levels.append((td["sma200"], "SMA200", ""))
    if td.get("low_52w"):
        levels.append((td["low_52w"], "52주 저가", ""))

    levels.sort(key=lambda x: x[0], reverse=True)
    seen: set[float] = set()
    rows = []
    for price, label, cls in levels:
        if price in seen:
            continue
        seen.add(price)
        rows.append(
            f'<div class="ladder-row {cls}">'
            f'<div class="ladder-price">{price:,.0f}원</div>'
            f'<div class="ladder-line"></div>'
            f'<div class="ladder-label">{label}</div>'
            f'</div>'
        )

    return "\n".join(rows) if rows else '<p style="color:var(--ink3)">가격 데이터 없음</p>'


def _buy_factor_rows(factors: list[str]) -> str:
    if not factors:
        return '<div class="factor-item"><div class="factor-text" style="color:var(--ink3)">데이터 없음</div></div>'
    return "".join(
        f'<div class="factor-item"><div class="factor-icon fi-up">✓</div><div class="factor-text">{f}</div></div>'
        for f in factors
    )


def _sell_factor_rows(factors: list[str]) -> str:
    if not factors:
        return '<div class="factor-item"><div class="factor-text" style="color:var(--ink3)">데이터 없음</div></div>'
    return "".join(
        f'<div class="factor-item"><div class="factor-icon fi-dn">✕</div><div class="factor-text">{f}</div></div>'
        for f in factors
    )


def _risk_cards_html(risk_factors: list[str]) -> str:
    if not risk_factors:
        return '<div class="risk-card"><div class="risk-desc" style="color:var(--ink3)">리스크 데이터 없음</div></div>'
    cards = []
    for i, rf in enumerate(risk_factors):
        # Heuristic: first 2 risks = HIGH, rest = MID
        level = "HIGH" if i < 2 else "MID"
        rt_cls = "rt-high" if level == "HIGH" else "rt-mid"
        label = ["기술적", "지정학/규제", "산업", "매크로", "재무"][min(i, 4)]
        cards.append(
            f'<div class="risk-card">'
            f'<div class="card-label">{label} 리스크</div>'
            f'<div class="risk-title">{rf[:50]}</div>'
            f'<div class="risk-desc">{rf}</div>'
            f'<span class="risk-tag {rt_cls}">{level}</span>'
            f'</div>'
        )
    return "\n".join(cards)


def _supply_rows_html(td: dict) -> str:
    rows = []
    if "foreign_flow_20d" in td:
        val = td["foreign_flow_20d"]
        cls = "up" if val == "순매수" else "dn"
        emoji = "📈" if val == "순매수" else "📉"
        rows.append(f'<div class="flow-item"><div class="flow-name">외국인 20일 순매수 방향</div><div class="flow-val {cls}">{emoji} {val}</div></div>')
    if "short_ratio_pct" in td:
        rows.append(f'<div class="flow-item"><div class="flow-name">공매도 잔고비율</div><div class="flow-val">{td["short_ratio_pct"]}%</div></div>')
    if not rows:
        return '<div class="flow-item"><div class="flow-name" style="color:var(--ink3)">수급 데이터 없음</div></div>'
    return "\n".join(rows)


def _checklist_html(v) -> str:
    items = []
    if v.buy_trigger:
        items.append(("매수 타이밍", v.buy_trigger))
    if v.sell_trigger:
        items.append(("매도/손절", v.sell_trigger))
    for rf in (v.risk_factors or [])[:3]:
        items.append(("리스크 모니터링", rf[:80]))

    rows = []
    for i, (label, text) in enumerate(items, 1):
        rows.append(
            f'<div class="check-item">'
            f'<div class="check-num">{i:02d}</div>'
            f'<div class="check-text"><strong>{label}</strong> — {text}</div>'
            f'</div>'
        )
    return "\n".join(rows) if rows else ""


def _fund_table_html(td: dict) -> str:
    rows = []
    if td.get("per", 0) > 0:
        rows.append(f"<tr><td>PER (TTM)</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['per']}배</td><td style='color:var(--ink3);font-size:11px'>수익성 지표</td></tr>")
    if td.get("pbr", 0) > 0:
        rows.append(f"<tr><td>PBR</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['pbr']}배</td><td style='color:var(--ink3);font-size:11px'>자산가치 대비</td></tr>")
    if td.get("div_yield", 0) > 0:
        rows.append(f"<tr><td>배당수익률</td><td style=\"font-family:'SF Mono','Fira Code',monospace\">{td['div_yield']}%</td><td style='color:var(--ink3);font-size:11px'>현재가 기준</td></tr>")
    if not rows:
        return ""
    return (
        '<div class="section-title">기초 분석</div>'
        f'<table class="tech-table"><thead><tr><th>지표</th><th>값</th><th>비고</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def _valuation_panel_html(td: dict) -> str:
    """밸류에이션 탭: PER/PBR/배당/부채비율 지표 카드 + 섹터 피어 비교 테이블."""
    per = td.get("per", 0)
    pbr = td.get("pbr", 0)
    div_yield = td.get("div_yield", 0)
    debt_ratio = td.get("debt_ratio", 0)
    ev_ebitda = td.get("ev_ebitda", 0)
    roe = td.get("roe", 0)

    def _card(label: str, val: str, sub: str = "", color: str = "") -> str:
        color_style = f"color:{color}" if color else ""
        return (
            f'<div class="metric-card">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-val" style="{color_style}">{val}</div>'
            f'<div class="metric-sub neutral">{sub}</div>'
            f'</div>'
        )

    cards = []
    if per > 0:
        cards.append(_card("PER (TTM)", f"{per}배", "수익성 지표"))
    if pbr > 0:
        color = "#34C759" if pbr < 1.0 else ("#FF9500" if pbr < 2.0 else "")
        cards.append(_card("PBR", f"{pbr}배", "청산가치 이하" if pbr < 1.0 else "자산가치 대비", color))
    if roe > 0:
        color = "#34C759" if roe >= 12 else ""
        cards.append(_card("ROE", f"{roe}%", "12% 이상 우량" if roe >= 12 else "수익성", color))
    if ev_ebitda > 0:
        cards.append(_card("EV/EBITDA", f"{ev_ebitda}배", "기업가치 배수"))
    if div_yield > 0:
        cards.append(_card("배당수익률", f"{div_yield}%", "현재가 기준"))
    if debt_ratio > 0:
        color = "#FF3B30" if debt_ratio > 300 else ("#FF9500" if debt_ratio > 200 else "#34C759")
        cards.append(_card("부채비율", f"{debt_ratio}%", "재무안정성", color))

    cards_html = "".join(cards) if cards else '<div class="metric-card"><div class="metric-label" style="color:var(--ink3)">밸류에이션 데이터 없음</div></div>'

    # K-IFRS quality
    ocf_quality = td.get("ocf_ni_ratio")
    quality_html = ""
    if ocf_quality:
        color = "#34C759" if ocf_quality >= 1.0 else "#FF9500"
        quality_html = (
            f'<div style="margin-top:8px;padding:10px 14px;background:var(--cream2);border-radius:8px;font-size:12.5px">'
            f'<span style="color:var(--ink3)">K-IFRS 회계품질 (OCF/NI)</span>'
            f'<span style="font-family:\'SF Mono\',\'Fira Code\',monospace;font-weight:600;color:{color};margin-left:12px">{ocf_quality:.2f}x</span>'
            f'{"<span style=\"color:#34C759;margin-left:8px\">✓ 양호</span>" if ocf_quality >= 1.0 else "<span style=\"color:#FF9500;margin-left:8px\">주의</span>"}'
            f'</div>'
        )

    # Peer comparison table
    peers = td.get("peer_comparison", [])
    if peers:
        peer_rows = "".join(
            f'<tr>'
            f'<td>{p.get("name", p.get("ticker", "—"))}</td>'
            f'<td style="font-family:\'SF Mono\',\'Fira Code\',monospace">{p.get("current_price", "—"):,}원' if isinstance(p.get("current_price"), (int, float)) else f'<td>{p.get("current_price", "—")}'
            f'</td>'
            f'<td style="font-family:\'SF Mono\',\'Fira Code\',monospace">{p.get("per", "—")}배</td>'
            f'<td style="font-family:\'SF Mono\',\'Fira Code\',monospace">{p.get("pbr", "—")}배</td>'
            f'<td style="font-family:\'SF Mono\',\'Fira Code\',monospace">{p.get("roe", "—")}%</td>'
            f'</tr>'
            for p in peers
        )
        peer_html = (
            '<div class="section-title" style="margin-top:24px">섹터 피어 비교</div>'
            '<table class="tech-table"><thead><tr>'
            '<th>종목</th><th>현재가</th><th>PER</th><th>PBR</th><th>ROE</th>'
            f'</tr></thead><tbody>{peer_rows}</tbody></table>'
        )
    else:
        peer_html = (
            '<div class="section-title" style="margin-top:24px">섹터 피어 비교</div>'
            '<div style="padding:12px;color:var(--ink3);font-size:12.5px">피어 데이터 없음 (analyzer 조회 필요)</div>'
        )

    return (
        '<div class="section-title">밸류에이션 지표</div>'
        f'<div class="metrics-grid">{cards_html}</div>'
        f'{quality_html}'
        f'{peer_html}'
    )


# ── Main entry point ────────────────────────────────────────────────────────

def generate_report(result: KRAnalysisResult, ticker_data: dict | None = None) -> Path:
    """KRAnalysisResult → 인터랙티브 HTML 리포트 저장 후 경로 반환."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    v = result.consensus
    regime = result.regime
    today = datetime.now().strftime("%Y-%m-%d")
    fname = f"{today}-{result.ticker}-analysis.html"
    path = _REPORTS_DIR / fname

    td = ticker_data or {}
    cp = td.get("current_price")
    ctx = _fetch_market_context()

    verdict_str = v.verdict.upper()
    badge_cls = _badge_class(verdict_str)
    conf_pct = f"{v.confidence:.0%}"

    # Entry mid for R:R
    entry_mid = None
    if v.entry_price_low and v.entry_price_high:
        entry_mid = (v.entry_price_low + v.entry_price_high) / 2
    elif v.entry_price_low:
        entry_mid = v.entry_price_low

    # Market display
    market_label = "KOSPI"  # could be enhanced

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{v.company_name or result.ticker} — KR Research</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>{_CSS}</style>
</head>
<body>

<!-- NAV -->
<nav class="nav">
  <div class="nav-logo">KR <span>Research</span></div>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="show('summary',this)">요약</button>
    <button class="nav-tab" onclick="show('market',this)">시장</button>
    <button class="nav-tab" onclick="show('chart',this)">차트/기술</button>
    <button class="nav-tab" onclick="show('valuation',this)">밸류에이션</button>
    <button class="nav-tab" onclick="show('strategy',this)">투자전략</button>
    <button class="nav-tab" onclick="show('scenario',this)">시나리오</button>
    <button class="nav-tab" onclick="show('risk',this)">리스크/수급</button>
    <button class="nav-tab" onclick="show('conclusion',this)">결론</button>
  </div>
  <div class="nav-meta">{v.company_name or result.ticker} · {result.ticker}<br>{today} · {market_label}</div>
</nav>

<!-- COMPANY HEADER -->
<div class="co-header">
  <div class="co-sub">{market_label} EQUITY RESEARCH · {v.sector or '—'} · KR RESEARCH</div>
  <div class="co-name">{v.company_name or result.ticker}</div>
  <div class="co-desc">{result.ticker} · {market_label} · {v.sector or '—'}{f' · 현재가 {cp:,}원' if cp else ''}</div>
  <div class="co-rating-row">
    <span class="badge badge-{badge_cls}">{verdict_str}</span>
    {f'<div class="price-chip"><div class="price-label">현재가</div><div class="price-display">{cp:,}원</div></div>' if cp else ''}
    {f'<div class="price-chip"><div class="price-label">T1 목표가</div><div class="price-display" style="color:#34C759">{int(v.target_price):,}원</div><div class="up-label">{_pct(cp or entry_mid, v.target_price)}</div></div>' if v.target_price else ''}
    {f'<div class="price-chip"><div class="price-label">T2 목표가</div><div class="price-display" style="color:#30D158">{int(v.target_price_2):,}원</div><div class="up-label">{_pct(cp or entry_mid, v.target_price_2)}</div></div>' if v.target_price_2 else ''}
    {f'<div class="price-chip"><div class="price-label">손절가</div><div class="price-display" style="color:#FF3B30">{int(v.stop_loss):,}원</div><div class="dn-label">{_pct(cp or entry_mid, v.stop_loss)}</div></div>' if v.stop_loss else ''}
    <div style="margin-left:auto;text-align:right">
      <div style="font-size:10px;color:#636366;font-family:'SF Mono','Fira Code',monospace;margin-bottom:4px;">신뢰도</div>
      <div style="font-family:'SF Mono','Fira Code',monospace;font-size:14px;color:#FF9500;font-weight:600;">{conf_pct}</div>
    </div>
  </div>
</div>

<!-- ═══ PANEL: 요약 ═══ -->
<div id="panel-summary" class="panel active">
<div class="main">
  <div class="thesis">
    <div class="thesis-label">Why Invest — 투자 의견</div>
    <div class="thesis-text">{v.investment_thesis or v.rationale or '투자 의견 데이터 없음'}</div>
  </div>
  <div class="section-title">핵심 지표</div>
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="metric-label">현재가</div>
      <div class="metric-val">{f'{cp:,}' if cp else '—'}</div>
      <div class="metric-sub neutral">{verdict_str} 구간</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">매수 구간</div>
      <div class="metric-val" style="font-size:13px">{f'{int(v.entry_price_low):,}–{int(v.entry_price_high):,}' if v.entry_price_low and v.entry_price_high else ('—')}</div>
      <div class="metric-sub" style="color:var(--ink3)">조정 시 진입</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">T1 목표가 (보수)</div>
      <div class="metric-val up">{f'{int(v.target_price):,}' if v.target_price else '—'}</div>
      <div class="metric-sub up">{_pct(cp or entry_mid, v.target_price)} · 50% 청산</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">T2 목표가 (공격)</div>
      <div class="metric-val up">{f'{int(v.target_price_2):,}' if v.target_price_2 else '—'}</div>
      <div class="metric-sub up">{_pct(cp or entry_mid, v.target_price_2)} · 잔량 청산</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">손절가</div>
      <div class="metric-val dn">{f'{int(v.stop_loss):,}' if v.stop_loss else '—'}</div>
      <div class="metric-sub dn">{_pct(cp or entry_mid, v.stop_loss)}</div>
    </div>
  </div>
  <div class="section-title">시나리오 전망 (3~6개월)</div>
  <div class="scenarios">
    <div class="sc sc-bull">
      <div class="sc-type">Bull Case</div>
      <div class="sc-price" style="font-size:16px">{v.bull_case[:60] if v.bull_case else '—'}</div>
    </div>
    <div class="sc sc-base">
      <div class="sc-type">Base Case</div>
      <div class="sc-price" style="font-size:16px">{v.base_case[:60] if v.base_case else '—'}</div>
    </div>
    <div class="sc sc-bear">
      <div class="sc-type">Bear Case</div>
      <div class="sc-price" style="font-size:16px">{v.bear_case[:60] if v.bear_case else '—'}</div>
    </div>
  </div>
  <div class="report-footer">분석 기준일: {today} · 데이터: pykrx · 분석: Claude Code CLI (claude-sonnet-4-6)<br>본 리포트는 참고용이며 투자 결정의 최종 책임은 투자자 본인에게 있습니다.</div>
</div>
</div>

<!-- ═══ PANEL: 시장 ═══ -->
<div id="panel-market" class="panel">
<div class="main">
  <div class="section-title">시장 컨텍스트 · {today} 기준</div>
  <div class="market-grid">
    <div class="card">
      <div class="card-label">글로벌 시장 현황</div>
      <div class="mkt-bars">
        {_market_bar_html(ctx)}
      </div>
    </div>
    <div class="card">
      <div class="card-label">KR Regime</div>
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
        <canvas id="regimeChart" width="80" height="80"></canvas>
        <div>
          <div style="font-size:22px;font-weight:700;color:{'var(--up)' if regime.regime=='BULL' else ('var(--dn)' if regime.regime in ('BEAR','CRISIS') else 'var(--amber)')};font-family:'SF Mono','Fira Code',monospace">{regime.regime}</div>
          <div style="font-size:11px;color:var(--ink3);margin-top:2px">신뢰도 {regime.confidence:.0%}</div>
          <div style="font-size:11px;color:var(--ink3);margin-top:4px">{v.current_status or '기술적 상태 참조'}</div>
        </div>
      </div>
    </div>
  </div>
</div>
</div>

<!-- ═══ PANEL: 차트/기술 ═══ -->
<div id="panel-chart" class="panel">
<div class="main">
  <div class="section-title">캔들스틱 차트 (최근 60일)</div>
  <div class="card" style="padding:16px 8px">
    <canvas id="candleCanvas" height="380" style="width:100%;display:block"></canvas>
  </div>
  <div class="section-title" style="margin-top:20px">감지된 패턴</div>
  <div class="card" id="patternList" style="padding:14px 16px">패턴 없음</div>
  <div class="section-title" style="margin-top:24px">기술적 지표</div>
  {_tech_table_html(td)}
  <div class="section-title">가격 레벨</div>
  {_price_ladder_html(td, v)}
  {f'<div style="margin-top:12px;padding:12px;background:var(--cream2);border-radius:8px;font-size:12.5px;color:var(--ink2)">{v.current_status}</div>' if v.current_status else ''}
</div>
</div>

<!-- ═══ PANEL: 밸류에이션 ═══ -->
<div id="panel-valuation" class="panel">
<div class="main">
  {_valuation_panel_html(td)}
</div>
</div>

<!-- ═══ PANEL: 투자전략 ═══ -->
<div id="panel-strategy" class="panel">
<div class="main">
  <div class="trade-box">
    <div class="card-label">Trade Setup</div>
    <div class="trade-row">
      <div class="trade-item">
        <div class="tlabel">매수 구간</div>
        <div class="tval" style="font-size:12px">{f'{int(v.entry_price_low):,}–{int(v.entry_price_high):,}원' if v.entry_price_low and v.entry_price_high else '—'}</div>
        <div class="tsub">분할 매수 권고</div>
      </div>
      <div class="trade-item t1">
        <div class="tlabel">T1 목표 (50% 청산)</div>
        <div class="tval">{f'{int(v.target_price):,}원' if v.target_price else '—'}</div>
        <div class="tsub" style="color:#5CB87A">{_pct(cp or entry_mid, v.target_price)}</div>
      </div>
      <div class="trade-item t2">
        <div class="tlabel">T2 목표 (잔량)</div>
        <div class="tval">{f'{int(v.target_price_2):,}원' if v.target_price_2 else '—'}</div>
        <div class="tsub" style="color:#7DD8A0">{_pct(cp or entry_mid, v.target_price_2)}</div>
      </div>
      <div class="trade-item stop">
        <div class="tlabel">손절가</div>
        <div class="tval">{f'{int(v.stop_loss):,}원' if v.stop_loss else '—'}</div>
        <div class="tsub" style="color:#FF3B30">{_pct(cp or entry_mid, v.stop_loss)}</div>
      </div>
      <div class="trade-item rr">
        <div class="tlabel">R:R 비율</div>
        <div class="tval">{_rr_ratio(entry_mid, v.target_price, v.stop_loss)} : 1</div>
        <div class="tsub" style="color:var(--blue)">Base case</div>
      </div>
    </div>
    <div class="trade-trigger">
      <div class="trigger-label">매수 타이밍</div>
      {v.buy_trigger or '—'}
      <br><br>
      <div class="trigger-label">매도 타이밍</div>
      {v.sell_trigger or '—'}
    </div>
  </div>
  <div class="section-title">매수 근거 vs 매도/우려 요인</div>
  <div class="factors-grid">
    <div>
      <div class="factor-col-header fch-up"><span style="font-size:14px">✅</span> 매수 근거</div>
      {_buy_factor_rows(v.buy_factors)}
    </div>
    <div>
      <div class="factor-col-header fch-dn"><span style="font-size:14px">❌</span> 매도/우려 요인</div>
      {_sell_factor_rows(v.sell_factors)}
    </div>
  </div>
</div>
</div>

<!-- ═══ PANEL: 시나리오 ═══ -->
<div id="panel-scenario" class="panel">
<div class="main">
  <div class="section-title">시나리오 전망 상세 (3~6개월)</div>
  <div class="scenarios" style="margin-bottom:24px">
    <div class="sc sc-bull">
      <div class="sc-type">Bull Case</div>
      <div class="sc-text" style="color:var(--up)">{v.bull_case or '—'}</div>
    </div>
    <div class="sc sc-base">
      <div class="sc-type">Base Case</div>
      <div class="sc-text">{v.base_case or '—'}</div>
    </div>
    <div class="sc sc-bear">
      <div class="sc-type">Bear Case</div>
      <div class="sc-text" style="color:var(--dn)">{v.bear_case or '—'}</div>
    </div>
  </div>
  {_fund_table_html(td)}
</div>
</div>

<!-- ═══ PANEL: 리스크/수급 ═══ -->
<div id="panel-risk" class="panel">
<div class="main">
  <div class="section-title">리스크 요인</div>
  <div class="risk-grid">{_risk_cards_html(v.risk_factors)}</div>
  <div class="section-title" style="margin-top:24px">수급 분석</div>
  <div class="card">{_supply_rows_html(td)}</div>
</div>
</div>

<!-- ═══ PANEL: 결론 ═══ -->
<div id="panel-conclusion" class="panel">
<div class="main">
  <div class="trade-box" style="margin-bottom:16px">
    <div class="card-label">최종 투자 판단</div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:14px">
      <span class="badge badge-{badge_cls}" style="font-size:14px;padding:7px 16px">{verdict_str}</span>
      <div>
        <div style="font-family:'SF Mono','Fira Code',monospace;font-size:18px;color:var(--cream);font-weight:600">신뢰도 {conf_pct}</div>
        <div style="font-size:11px;color:#6A6460;margin-top:2px">{v.current_status or regime.regime + ' Regime'}</div>
      </div>
    </div>
    <div style="font-size:13px;color:#9A948C;line-height:1.75">{v.rationale or '—'}</div>
  </div>
  <div class="section-title">모니터링 체크리스트</div>
  {_checklist_html(v)}
  <div class="report-footer">
    분석 기준일: {today} · 데이터: pykrx · 분석: Claude Code CLI (claude-sonnet-4-6)<br>
    Regime: {regime.regime} ({regime.confidence:.0%}) · 종목: {result.ticker}<br>
    본 리포트는 참고용이며 투자 결정의 최종 책임은 투자자 본인에게 있습니다.
  </div>
</div>
</div>

<script>
function show(id, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  btn.classList.add('active');
  if (id === 'market') {{
    setTimeout(() => {{
      document.querySelectorAll('.mkt-bar-fill').forEach(b => {{ b.style.width = b.dataset.pct + '%'; }});
      initRegime();
    }}, 80);
  }}
  if (id === 'chart') setTimeout(initCandles, 80);
}}
function initCandles() {{
  const canvas = document.getElementById('candleCanvas');
  if (!canvas || canvas._done) return; canvas._done = true;
  const ohlcv = {json.dumps(td.get('ohlcv_60d', []))};
  const patterns = {json.dumps(td.get('candle_patterns', []))};
  if (!ohlcv.length) {{
    const msg = document.createElement('p');
    msg.style.cssText = 'color:var(--ink3);padding:16px';
    msg.textContent = 'OHLCV \ub370\uc774\ud130 \uc5c6\uc74c';
    canvas.parentElement.replaceChild(msg, canvas);
    return;
  }}
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth; const H = canvas.height;
  canvas.width = W;
  const PAD_L = 8, PAD_R = 8, PAD_TOP = 20, VOL_H = Math.floor(H * 0.18);
  const chartH = H - PAD_TOP - VOL_H - 4;
  const n = ohlcv.length;
  const barW = Math.max(3, Math.floor((W - PAD_L - PAD_R) / n) - 1);
  const gap = Math.floor((W - PAD_L - PAD_R) / n);
  const highs = ohlcv.map(r => r.h), lows = ohlcv.map(r => r.l);
  const priceMax = Math.max(...highs), priceMin = Math.min(...lows);
  const priceRange = priceMax - priceMin || 1;
  const vols = ohlcv.map(r => r.v), volMax = Math.max(...vols) || 1;
  const py = p => PAD_TOP + chartH - ((p - priceMin) / priceRange) * chartH;
  const vy = v => H - Math.floor((v / volMax) * VOL_H);
  const patDates = new Set(patterns.map(p => p.date));
  for (let i = 0; i < n; i++) {{
    const r = ohlcv[i];
    const x = PAD_L + i * gap + Math.floor(gap / 2);
    const isBull = r.c >= r.o;
    const color = isBull ? '#5CB87A' : '#E8806A';
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.beginPath(); ctx.lineWidth = 1;
    ctx.moveTo(x, py(r.h)); ctx.lineTo(x, py(r.l)); ctx.stroke();
    const bodyTop = py(Math.max(r.o, r.c));
    const bodyBot = py(Math.min(r.o, r.c));
    const bodyH = Math.max(1, bodyBot - bodyTop);
    const bx = x - Math.floor(barW / 2);
    ctx.fillRect(bx, bodyTop, barW, bodyH);
    ctx.globalAlpha = 0.35;
    ctx.fillRect(bx, vy(r.v), barW, H - vy(r.v));
    ctx.globalAlpha = 1.0;
    if (i % 10 === 0 && r.d) {{
      ctx.fillStyle = '#6E6E73'; ctx.font = '9px SF Mono,Fira Code,monospace';
      ctx.fillText(r.d.slice(5), x - 10, H - 2);
    }}
    if (patDates.has(r.d)) {{
      const pat = patterns.find(p => p.date === r.d);
      if (pat) {{
        ctx.font = 'bold 11px sans-serif';
        if (pat.signal === 'buy') {{ ctx.fillStyle = '#34C759'; ctx.fillText('\u25b2', x - 4, py(r.l) + 14); }}
        else if (pat.signal === 'sell') {{ ctx.fillStyle = '#FF3B30'; ctx.fillText('\u25bc', x - 4, py(r.h) - 4); }}
        else {{ ctx.fillStyle = '#FF9500'; ctx.fillText('\u25c6', x - 4, py(r.l) + 14); }}
      }}
    }}
  }}
  const pl = document.getElementById('patternList');
  while (pl.firstChild) pl.removeChild(pl.firstChild);
  if (patterns.length === 0) {{ pl.textContent = '\uac10\uc9c0\ub41c \ud328\ud134 \uc5c6\uc74c (\ucd5c\uadfc 60\uc77c)'; return; }}
  const tbl = document.createElement('table');
  tbl.style.cssText = 'width:100%;border-collapse:collapse;font-size:12.5px';
  const hdrRow = tbl.insertRow();
  hdrRow.style.background = '#1D1D1F'; hdrRow.style.color = '#F5F5F7';
  ['\ub0a0\uc9dc','\ud328\ud134','\uc2e0\ud638','\uc124\uba85'].forEach(h => {{
    const th = document.createElement('th');
    th.textContent = h;
    th.style.cssText = 'padding:7px 12px;text-align:left;font-family:SF Mono,Fira Code,monospace;font-size:10px;letter-spacing:.06em;font-weight:500';
    hdrRow.appendChild(th);
  }});
  patterns.slice().reverse().forEach(p => {{
    const row = tbl.insertRow();
    const signalColor = p.signal === 'buy' ? '#34C759' : p.signal === 'sell' ? '#FF3B30' : '#FF9500';
    const signalBg = p.signal === 'buy' ? '#E8FAF0' : p.signal === 'sell' ? '#FFF0EF' : '#FFF5E0';
    const signalLabel = p.signal === 'buy' ? '\ub9e4\uc218' : p.signal === 'sell' ? '\ub9e4\ub3c4' : '\uc911\ub9bd';
    const cellStyle = 'padding:9px 12px;border-bottom:1px solid #D2D2D7;color:#3A3A3C';
    [p.date, p.pattern, p.desc].forEach((txt, ci) => {{
      const td2 = row.insertCell();
      td2.style.cssText = cellStyle;
      if (ci === 1) {{
        const span = document.createElement('span');
        span.textContent = signalLabel;
        span.style.cssText = 'display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-family:SF Mono,Fira Code,monospace;background:' + signalBg + ';color:' + signalColor;
        const nameNode = document.createTextNode(p.pattern + ' ');
        td2.appendChild(nameNode);
        td2.appendChild(span);
      }} else {{
        td2.textContent = txt;
      }}
    }});
  }});
  pl.appendChild(tbl);
}}
function initRegime() {{
  const c = document.getElementById('regimeChart');
  if (!c || c._done) return; c._done = true;
  const conf = {int(regime.confidence * 100)};
  const color = conf >= 70 ? '#34C759' : conf >= 50 ? '#FF9500' : '#FF3B30';
  new Chart(c, {{
    type: 'doughnut',
    data: {{ datasets: [{{ data: [conf, 100-conf], backgroundColor: [color, '#D2D2D7'], borderWidth: 0 }}] }},
    options: {{ cutout: '72%', plugins: {{ legend: {{ display: false }}, tooltip: {{ enabled: false }} }}, animation: {{ duration: 900 }} }}
  }});
}}
</script>
</body>
</html>"""

    path.write_text(html, encoding="utf-8")
    _logger.info("HTML report saved: %s", path)
    return path
