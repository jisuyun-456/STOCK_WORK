#!/usr/bin/env python3
"""Daily Analysis Report Generator -- Obsidian-ready markdown.

Runs after market close to generate a comprehensive daily analysis:
  - Market regime & news sentiment
  - Today's trades with reasons
  - Monitor events (stop-loss/take-profit triggers)
  - Portfolio performance & risk alerts
  - Top/worst positions

Usage:
    python scripts/daily_analysis.py                 # Generate report
    python scripts/daily_analysis.py --obsidian      # Also copy to Obsidian vault
    python scripts/daily_analysis.py --date 2026-04-10  # Specific date
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

STATE_DIR = ROOT / "state"
REPORTS_DIR = ROOT / "reports" / "daily"
OBSIDIAN_DIR = Path(r"C:\Users\yjisu\Documents\ClaudeVault\STOCK\DailyReport")

PORTFOLIOS_PATH = STATE_DIR / "portfolios.json"
TRADE_LOG_PATH = STATE_DIR / "trade_log.jsonl"
MONITOR_LOG_PATH = STATE_DIR / "monitor_log.jsonl"


# ---- Data Collection ----

def _load_portfolios() -> dict:
    if PORTFOLIOS_PATH.exists():
        with open(PORTFOLIOS_PATH) as f:
            return json.load(f)
    return {}


def _load_today_trades(date_str: str) -> list[dict]:
    """Filter trade_log.jsonl for today's entries."""
    trades = []
    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH) as f:
            for line in f:
                entry = json.loads(line.strip())
                ts = entry.get("ts", "")
                if ts.startswith(date_str):
                    trades.append(entry)
    return trades


def _load_today_monitor_events(date_str: str) -> list[dict]:
    """Filter monitor_log.jsonl for today's events with exits."""
    events = []
    if MONITOR_LOG_PATH.exists():
        with open(MONITOR_LOG_PATH) as f:
            for line in f:
                entry = json.loads(line.strip())
                ts = entry.get("ts", "")
                if ts.startswith(date_str) and entry.get("exits"):
                    events.append(entry)
    return events


def _get_positions() -> list[dict]:
    try:
        from execution.alpaca_client import get_positions
        return get_positions()
    except Exception:
        return []


def _get_account() -> dict:
    try:
        from execution.alpaca_client import get_account_info
        return get_account_info()
    except Exception:
        return {"equity": 0, "cash": 0, "portfolio_value": 0, "mode": "paper"}


def _get_market_data() -> dict:
    """Fetch basic market indices via yfinance."""
    import yfinance as yf

    data = {}
    tickers = {"SPY": "S&P 500", "QQQ": "NASDAQ 100", "^VIX": "VIX"}
    for symbol, name in tickers.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                change_pct = (curr - prev) / prev * 100
            elif len(hist) == 1:
                curr = float(hist["Close"].iloc[-1])
                change_pct = 0
            else:
                curr, change_pct = 0, 0
            data[symbol] = {"name": name, "price": curr, "change_pct": change_pct}
        except Exception:
            data[symbol] = {"name": name, "price": 0, "change_pct": 0}
    return data


def _get_regime_and_news() -> tuple[str, str, str]:
    """Get current regime detection + news summary."""
    regime_str = "UNKNOWN"
    reasoning = ""
    news_summary = ""

    try:
        from news.fetcher import fetch_macro_news
        from news.sentiment import analyze_sentiment
        from research.consensus import detect_regime_enhanced

        news = fetch_macro_news()
        if news:
            result = analyze_sentiment("_MACRO", news)
            score = result.score
            news_summary = result.summary
        else:
            score = 0.0

        regime_info = detect_regime_enhanced(score)
        regime_str = regime_info.regime
        reasoning = regime_info.reasoning
    except Exception as e:
        reasoning = f"Regime detection failed: {e}"

    return regime_str, reasoning, news_summary


def _build_symbol_strategy_map() -> dict[str, str]:
    """Build symbol->strategy from trade_log."""
    mapping = {}
    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH) as f:
            for line in f:
                e = json.loads(line.strip())
                if e.get("side") == "buy" and e.get("symbol") and e.get("strategy"):
                    mapping[e["symbol"]] = e["strategy"]
    return mapping


# ---- New Metric Helpers ----

def _calc_daily_pnl(portfolios: dict) -> tuple[float, float]:
    """오늘 NAV - 어제 NAV로 일간 손익 계산."""
    total_today = 0.0
    total_yesterday = 0.0
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        if len(nav_history) >= 2:
            total_today += nav_history[-1]["nav"]
            total_yesterday += nav_history[-2]["nav"]
        elif len(nav_history) == 1:
            total_today += nav_history[-1]["nav"]
            total_yesterday += nav_history[-1]["nav"]
    daily_pnl = total_today - total_yesterday
    daily_pnl_pct = (daily_pnl / total_yesterday * 100) if total_yesterday > 0 else 0.0
    return daily_pnl, daily_pnl_pct


def _calc_cumulative_returns(portfolios: dict) -> list[tuple[str, float, float, float]]:
    """전략별 누적 수익률. Returns: [(code, inception_nav, current_nav, pct), ...]"""
    results = []
    inception = portfolios.get("inception", {}).get("strategies", {})
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        inception_nav = inception.get(code, strat.get("allocated", 0))
        current_nav = nav_history[-1]["nav"] if nav_history else strat.get("allocated", inception_nav)
        pct = ((current_nav - inception_nav) / inception_nav * 100) if inception_nav > 0 else 0.0
        results.append((code, inception_nav, current_nav, pct))
    return results


def _calc_mdd(portfolios: dict) -> list[tuple[str, float, str, str]]:
    """전략별 Max Drawdown. Returns: [(code, mdd_pct, peak_date, trough_date), ...]"""
    results = []
    for code in ["MOM", "VAL", "QNT", "LEV", "LEV_ST"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        if len(nav_history) < 2:
            results.append((code, 0.0, "-", "-"))
            continue
        navs = [h["nav"] for h in nav_history]
        dates = [h["date"] for h in nav_history]
        peak = navs[0]
        peak_date = dates[0]
        max_dd = 0.0
        trough_date = dates[0]
        for nav, date in zip(navs, dates):
            if nav > peak:
                peak = nav
                peak_date = date
            dd = (nav - peak) / peak * 100 if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd
                trough_date = date
        results.append((code, max_dd, peak_date, trough_date))
    return results


def _calc_position_aging(
    positions: list[dict], sym_map: dict[str, str]
) -> list[tuple[str, str, int, float]]:
    """포지션별 보유 기간. trade_log에서 최초 매수일 찾아 계산.
    Returns: [(symbol, strategy, days_held, unrealized_plpc), ...]
    """
    from datetime import date as _date
    today = _date.today()
    buy_dates: dict[str, str] = {}
    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH) as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except Exception:
                    continue
                if entry.get("side") == "buy" and entry.get("status") in ("submitted", "filled"):
                    sym = entry.get("symbol", "")
                    ts = entry.get("ts", "")[:10]  # YYYY-MM-DD
                    if sym and sym not in buy_dates:
                        buy_dates[sym] = ts
    result = []
    for p in sorted(positions, key=lambda x: x.get("symbol", "")):
        sym = p.get("symbol", "")
        strat = sym_map.get(sym, "?")
        buy_date_str = buy_dates.get(sym)
        if buy_date_str:
            try:
                buy_dt = _date.fromisoformat(buy_date_str)
                days = (today - buy_dt).days
            except ValueError:
                days = 0
        else:
            days = 0
        plpc = p.get("unrealized_plpc", 0.0)
        result.append((sym, strat, days, plpc))
    return result


# ---- Report Generation ----

def generate_daily_analysis(date_str: str | None = None) -> str:
    """Generate comprehensive daily analysis markdown."""

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"[Daily Analysis] Generating report for {date_str}...")

    # Collect data
    portfolios = _load_portfolios()
    trades = _load_today_trades(date_str)
    monitor_events = _load_today_monitor_events(date_str)
    positions = _get_positions()
    account = _get_account()
    sym_map = _build_symbol_strategy_map()

    # New metric calculations
    daily_pnl, daily_pnl_pct = _calc_daily_pnl(portfolios)
    cumulative = _calc_cumulative_returns(portfolios)
    mdd_data = _calc_mdd(portfolios)
    aging_data = _calc_position_aging(positions, sym_map) if positions else []

    # Market data (may fail in CI without yfinance)
    try:
        market = _get_market_data()
    except Exception:
        market = {}

    # Regime & news
    try:
        regime, reasoning, news_summary = _get_regime_and_news()
    except Exception:
        regime, reasoning, news_summary = "UNKNOWN", "", ""

    # ---- Build markdown ----
    lines = []
    lines.append(f"# Daily Analysis - {date_str}")
    lines.append("")

    # Regime
    lines.append(f"## Market Regime: {regime}")
    if reasoning:
        lines.append(f"> {reasoning}")
    lines.append("")

    # Today's P&L
    pnl_sign = "+" if daily_pnl >= 0 else ""
    lines.append(f"## Today's P&L: {pnl_sign}${daily_pnl:,.2f} ({pnl_sign}{daily_pnl_pct:.2f}%)")
    lines.append("")

    # Market summary
    lines.append("## Market Summary")
    if market:
        for sym, info in market.items():
            sign = "+" if info["change_pct"] >= 0 else ""
            lines.append(f"- **{info['name']}**: ${info['price']:,.2f} ({sign}{info['change_pct']:.2f}%)")
    if news_summary:
        lines.append(f"- News Sentiment: {news_summary}")
    lines.append("")

    # Today's trades
    buys = [t for t in trades if t.get("side") == "buy" and t.get("status") in ("submitted", "filled")]
    sells = [t for t in trades if t.get("side") == "sell" and t.get("status") in ("submitted", "filled")]
    skipped = [t for t in trades if t.get("status") == "skipped"]

    lines.append(f"## Today's Trades ({len(buys)} BUY, {len(sells)} SELL, {len(skipped)} skipped)")
    lines.append("")

    if buys:
        lines.append("### BUY")
        lines.append("| Symbol | Strategy | Amount | Reason |")
        lines.append("|--------|----------|--------|--------|")
        for t in sorted(buys, key=lambda x: x.get("strategy", "")):
            reason = t.get("reason", "")
            # Truncate long reasons
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append(f"| {t['symbol']} | {t['strategy']} | ${_notional(t):,.0f} | {reason} |")
        lines.append("")

    if sells:
        lines.append("### SELL")
        lines.append("| Symbol | Strategy | Reason | Trigger |")
        lines.append("|--------|----------|--------|---------|")
        for t in sorted(sells, key=lambda x: x.get("strategy", "")):
            reason = t.get("reason", "")
            trigger = "monitor" if "[MONITOR]" in reason else "signal"
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append(f"| {t['symbol']} | {t['strategy']} | {reason} | {trigger} |")
        lines.append("")

    # Monitor events
    if monitor_events:
        lines.append("### Monitor Events (Intraday)")
        for evt in monitor_events:
            ts = evt.get("ts", "")[:19]
            lines.append(f"**{ts}** - {evt.get('positions_checked', 0)} positions checked")
            for ex in evt.get("exits", []):
                lines.append(f"- EXIT **{ex['symbol']}** ({ex['strategy']}): {ex['reason']} | P&L: {ex.get('plpc', 0):+.1%}")
        lines.append("")

    # Portfolio performance
    lines.append("## Portfolio Performance")
    lines.append("| Strategy | NAV | Allocated | Positions | Cash |")
    lines.append("|----------|-----|-----------|-----------|------|")
    total_nav = 0
    for code in ["MOM", "VAL", "QNT", "LEV"]:
        strat = portfolios.get("strategies", {}).get(code, {})
        nav_history = strat.get("nav_history", [])
        latest_nav = nav_history[-1]["nav"] if nav_history else strat.get("allocated", 0)
        pos_count = len(strat.get("positions", {}))
        cash = strat.get("cash", 0)
        total_nav += latest_nav
        lines.append(f"| {code} | ${latest_nav:,.0f} | ${strat.get('allocated', 0):,.0f} | {pos_count} | ${cash:,.0f} |")

    lines.append(f"| **Total** | **${total_nav:,.0f}** | | | ${account.get('cash', 0):,.0f} |")
    lines.append("")

    # Cumulative Return by Strategy
    lines.append("## Cumulative Return by Strategy")
    lines.append("| Strategy | Inception NAV | Current NAV | Return |")
    lines.append("|----------|--------------|------------|--------|")
    for code, inception_nav, current_nav, pct in cumulative:
        ret_sign = "+" if pct >= 0 else ""
        lines.append(f"| {code} | ${inception_nav:,.0f} | ${current_nav:,.0f} | {ret_sign}{pct:.2f}% |")
    lines.append("")

    # Max Drawdown by Strategy
    lines.append("## Max Drawdown by Strategy")
    lines.append("| Strategy | MDD | Peak Date | Trough Date |")
    lines.append("|----------|-----|-----------|-------------|")
    for code, mdd, peak_d, trough_d in mdd_data:
        flag = " ⚠️" if mdd < -10 else ""
        lines.append(f"| {code} | {mdd:.1f}%{flag} | {peak_d} | {trough_d} |")
    lines.append("")

    # Position details - Top 5 / Worst 5
    if positions:
        sorted_pos = sorted(positions, key=lambda x: x["unrealized_plpc"], reverse=True)

        lines.append("## Top 5 Performers")
        lines.append("| Symbol | Strategy | Entry | Current | P&L | P&L% |")
        lines.append("|--------|----------|-------|---------|-----|------|")
        for p in sorted_pos[:5]:
            strat = sym_map.get(p["symbol"], "?")
            lines.append(
                f"| {p['symbol']} | {strat} | ${p['avg_entry_price']:,.2f} | "
                f"${p['current_price']:,.2f} | ${p['unrealized_pl']:+,.2f} | "
                f"{p['unrealized_plpc']:+.2%} |"
            )
        lines.append("")

        lines.append("## Worst 5 Performers")
        lines.append("| Symbol | Strategy | Entry | Current | P&L | P&L% |")
        lines.append("|--------|----------|-------|---------|-----|------|")
        for p in sorted_pos[-5:]:
            strat = sym_map.get(p["symbol"], "?")
            lines.append(
                f"| {p['symbol']} | {strat} | ${p['avg_entry_price']:,.2f} | "
                f"${p['current_price']:,.2f} | ${p['unrealized_pl']:+,.2f} | "
                f"{p['unrealized_plpc']:+.2%} |"
            )
        lines.append("")

    # Risk alerts
    lines.append("## Risk Alerts")
    alerts = []

    # Sector concentration check
    if positions:
        from collections import Counter
        sectors = Counter()
        for p in positions:
            strat = sym_map.get(p["symbol"], "UNKNOWN")
            sectors[strat] += 1
        for strat, count in sectors.most_common(1):
            if count > len(positions) * 0.5:
                alerts.append(f"Strategy concentration: {strat} holds {count}/{len(positions)} positions ({count/len(positions):.0%})")

    # MDD check
    for code, strat in portfolios.get("strategies", {}).items():
        nav_history = strat.get("nav_history", [])
        if len(nav_history) >= 2:
            navs = [h["nav"] for h in nav_history]
            peak = max(navs)
            current = navs[-1]
            if peak > 0:
                mdd = (current - peak) / peak
                if mdd < -0.10:
                    alerts.append(f"{code} MDD: {mdd:.1%} (peak=${peak:,.0f}, now=${current:,.0f})")

    if alerts:
        for a in alerts:
            lines.append(f"- {a}")
    else:
        lines.append("- No alerts")
    lines.append("")

    # Open Position Aging
    if aging_data:
        lines.append("## Open Position Aging")
        lines.append("| Symbol | Strategy | Days Held | Unrealized P&L% | Note |")
        lines.append("|--------|----------|-----------|----------------|------|")
        for sym, strat, days, plpc in aging_data:
            note = ""
            if days >= 60:
                note = "⚠️ Review (60d+)"
            elif plpc < -0.10:
                note = "⚠️ Near stop-loss"
            lines.append(f"| {sym} | {strat} | {days}d | {plpc:+.1%} | {note} |")
        lines.append("")

    # Tomorrow outlook
    lines.append("## Tomorrow Outlook")
    from strategies.regime_allocator import allocate, get_regime_description
    try:
        total_capital = portfolios.get("account_total", 100000)
        alloc = allocate(regime, total_capital)
        lines.append(f"Regime **{regime}**: {get_regime_description(regime)}")
        lines.append("")
        lines.append("Expected allocation:")
        for code, amount in alloc.items():
            lines.append(f"- {code}: ${amount:,.0f}")
    except Exception:
        lines.append(f"Regime: {regime}")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | Paper Trading*")

    report = "\n".join(lines)

    # Save
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"{date_str}-analysis.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  Report saved: {report_path}")

    return str(report_path)


def _notional(trade: dict) -> float:
    """Extract notional value from trade entry."""
    # weight_pct * strategy capital approximation
    weight = trade.get("weight_pct", 0)
    strategy = trade.get("strategy", "")
    strategy_capitals = {"MOM": 25000, "VAL": 25000, "QNT": 30000, "LEV": 20000}
    return weight * strategy_capitals.get(strategy, 25000)


def copy_to_obsidian(report_path: str):
    """Copy report to Obsidian vault."""
    src = Path(report_path)
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    dest = OBSIDIAN_DIR / src.name
    shutil.copy2(src, dest)
    print(f"  Copied to Obsidian: {dest}")


# ---- CLI ----

def main():
    parser = argparse.ArgumentParser(description="Daily Analysis Report Generator")
    parser.add_argument("--date", default=None, help="Date to analyze (YYYY-MM-DD)")
    parser.add_argument("--obsidian", action="store_true", help="Copy to Obsidian vault")
    args = parser.parse_args()

    report_path = generate_daily_analysis(date_str=args.date)

    if args.obsidian:
        copy_to_obsidian(report_path)


if __name__ == "__main__":
    main()
