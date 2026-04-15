"""Hybrid LLM agent runner for Research Overlay.

Supports 2 modes:
- rules: Rule-based heuristics (default, zero cost)
- claude: Claude Haiku API (opt-in: RESEARCH_AGENTS=claude, ~$1~2/month)

Environment variable RESEARCH_AGENTS controls the mode.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from strategies.base_strategy import Signal
from .agent_prompts import AGENT_PROMPTS, APPEAL_SUFFIX, AGENT_NAMES
from .models import RegimeDetection, ResearchVerdict

_MODE = os.environ.get("RESEARCH_AGENTS", "rules")


def get_research_mode() -> str:
    """Return current research mode."""
    return _MODE


def run_all_agents(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    mode: str | None = None,
) -> list[ResearchVerdict]:
    """Run all 5 research agents in parallel and return verdicts.

    Args:
        signal: Trading signal to evaluate.
        market_data: Phase 1 data (prices, indicators, news, polymarket).
        portfolio_state: portfolios.json content.
        regime: Current regime detection.
        mode: Override for research mode.

    Returns:
        List of 5 ResearchVerdict objects. Never raises.
    """
    mode = mode or _MODE

    if mode == "claude":
        return _run_claude_agents(signal, market_data, portfolio_state, regime)
    else:  # rules (default, zero cost)
        return _run_data_driven_agents(signal, market_data, portfolio_state, regime)


def run_all_agents_appeal(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    appeal_context: dict,
    mode: str | None = None,
) -> list[ResearchVerdict]:
    """Run appeal analysis with all 5 agents."""
    mode = mode or _MODE

    if mode == "claude":
        return _run_claude_appeal(signal, market_data, portfolio_state, regime, appeal_context)
    else:  # rules (default, zero cost)
        return _run_data_driven_agents(signal, market_data, portfolio_state, regime)




def _build_agent_context(
    agent_name: str,
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> str:
    """Build context message for a specific agent."""
    parts = [
        f"Symbol: {signal.symbol}",
        f"Strategy: {signal.strategy}",
        f"Direction: {signal.direction.value}",
        f"Confidence: {signal.confidence:.2f}",
        f"Target Weight: {signal.weight_pct:.1%}",
        f"Regime: {regime.regime} (VIX={regime.vix_level}, SPY/SMA200={regime.sp500_vs_sma200})",
    ]

    # Agent-specific context
    if agent_name == "equity_research":
        fundamentals = market_data.get("fundamentals", {}).get(signal.symbol, {})
        if fundamentals:
            parts.append(f"Fundamentals: PE={fundamentals.get('pe', 'N/A')}, "
                        f"ROE={fundamentals.get('roe', 'N/A')}, "
                        f"FCF_Yield={fundamentals.get('fcf_yield', 'N/A')}")
        # Top 3 news for this symbol
        symbol_news = market_data.get("news", {}).get(signal.symbol, [])[:3]
        if symbol_news:
            parts.append("Recent news:")
            for n in symbol_news:
                parts.append(f"  - [{n.get('source', '?')}] {n.get('title', '')[:80]}")

    elif agent_name == "technical_strategist":
        indicators = market_data.get("indicators", {}).get(signal.symbol, {})
        if indicators:
            parts.append(f"Indicators: RSI={indicators.get('rsi', 'N/A')}, "
                        f"MACD_hist={indicators.get('macd_hist', 'N/A')}, "
                        f"MACD_cross={indicators.get('macd_cross', 'N/A')}, "
                        f"BB_%B={indicators.get('bb_pct_b', 'N/A')}, "
                        f"BB_squeeze={indicators.get('bb_squeeze', 'N/A')}, "
                        f"Volume_ratio={indicators.get('volume_ratio', 'N/A')}, "
                        f"Trend={indicators.get('trend', 'N/A')}, "
                        f"SMA50={indicators.get('sma_50', 'N/A')}, "
                        f"SMA200={indicators.get('sma_200', 'N/A')}")

    elif agent_name == "macro_economist":
        # Macro news summary
        macro_news = market_data.get("news", {}).get("_MACRO", [])[:5]
        if macro_news:
            parts.append("Macro news (top 5):")
            for n in macro_news:
                parts.append(f"  - [{n.get('source', '?')}] {n.get('title', '')[:80]}")
        # Polymarket data
        poly_data = market_data.get("polymarket", [])
        if poly_data:
            parts.append("Prediction markets:")
            for p in poly_data[:5]:
                parts.append(f"  - {p.get('question', '')[:60]}: {p.get('probabilities', [])}")

    elif agent_name == "portfolio_architect":
        # Current positions for this strategy
        strat = signal.strategy
        strat_state = portfolio_state.get("strategies", {}).get(strat, {})
        positions = strat_state.get("positions", {})
        if positions:
            parts.append(f"Current {strat} positions: {list(positions.keys())[:10]}")
            parts.append(f"Position count: {len(positions)}")

    elif agent_name == "risk_controller":
        indicators = market_data.get("indicators", {}).get(signal.symbol, {})
        if indicators:
            parts.append(f"Volatility: BB_%B={indicators.get('bb_pct_b', 'N/A')}, "
                        f"RSI={indicators.get('rsi', 'N/A')}")
        parts.append(f"Regime risk: {regime.regime}")

    return "\n".join(parts)


def _parse_verdict_json(text: str, agent_name: str, symbol: str) -> ResearchVerdict | None:
    """Parse LLM response into ResearchVerdict."""
    # Remove markdown code blocks
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()

    # Try JSON parse
    try:
        # Find the JSON object in the response
        match = re.search(r"\{[^{}]*\}", clean)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(clean)

        direction = data.get("direction", "AGREE")
        if direction not in ("AGREE", "DISAGREE", "VETO"):
            direction = "AGREE"

        delta = float(data.get("confidence_delta", 0.0))
        delta = max(-0.3, min(0.3, delta))

        conviction = data.get("conviction", "MODERATE")
        if conviction not in ("STRONG", "MODERATE", "WEAK"):
            conviction = "MODERATE"

        return ResearchVerdict(
            agent=agent_name,
            symbol=symbol,
            direction=direction,
            confidence_delta=delta,
            conviction=conviction,
            reasoning=str(data.get("reasoning", ""))[:200],
            key_metrics=data.get("key_metrics", {}),
            override_vote=data.get("override_vote"),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except (json.JSONDecodeError, ValueError, KeyError):
        return None




# ─── Claude Mode (Interactive) ─────────────────────────────────────────────


def _get_claude_client():
    """Get Anthropic client. Returns None if unavailable."""
    try:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        return anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return None


_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def _run_claude_agents(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[ResearchVerdict]:
    """Run 5 agents in parallel via Claude API (Haiku 4.5)."""
    client = _get_claude_client()
    if client is None:
        print("  [agent_runner] Claude unavailable (no API key or SDK), falling back to rules")
        return _run_data_driven_agents(signal, market_data, portfolio_state, regime)

    print(f"  [agent_runner] Claude mode: {_CLAUDE_MODEL} × {len(AGENT_NAMES)} agents (parallel)")
    verdicts: list[ResearchVerdict] = []

    def _call_agent(agent_name: str) -> ResearchVerdict | None:
        system_prompt = AGENT_PROMPTS[agent_name]
        context = _build_agent_context(agent_name, signal, market_data, portfolio_state, regime)
        try:
            response = client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": f"--- SIGNAL CONTEXT ---\n{context}"}],
            )
            return _parse_verdict_json(response.content[0].text, agent_name, signal.symbol)
        except Exception as exc:
            print(f"    [{agent_name}] Claude error: {exc}")
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_call_agent, name): name for name in AGENT_NAMES}
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                verdict = future.result(timeout=30)
                if verdict:
                    verdicts.append(verdict)
                    print(f"    [{agent_name}] {verdict.direction} (delta={verdict.confidence_delta:+.2f})")
                else:
                    print(f"    [{agent_name}] parse failed, skipping")
            except Exception as exc:
                print(f"    [{agent_name}] timeout/error: {exc}")

    return verdicts


def _run_claude_appeal(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    appeal_context: dict,
) -> list[ResearchVerdict]:
    """Run appeal analysis via Claude API (Haiku 4.5)."""
    client = _get_claude_client()
    if client is None:
        print("  [agent_runner] Claude unavailable, falling back to rules for appeal")
        return _run_data_driven_agents(signal, market_data, portfolio_state, regime)

    failed_checks = appeal_context.get("failed_checks", [])
    appeal_suffix = APPEAL_SUFFIX.format(failed_checks=", ".join(failed_checks))

    verdicts: list[ResearchVerdict] = []

    def _call_appeal_agent(agent_name: str) -> ResearchVerdict | None:
        system_prompt = AGENT_PROMPTS[agent_name] + "\n" + appeal_suffix
        context = _build_agent_context(agent_name, signal, market_data, portfolio_state, regime)
        context += f"\nFailed risk checks: {', '.join(failed_checks)}"
        try:
            response = client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=512,
                system=system_prompt,
                messages=[{"role": "user", "content": f"--- APPEAL CONTEXT ---\n{context}"}],
            )
            return _parse_verdict_json(response.content[0].text, agent_name, signal.symbol)
        except Exception as exc:
            print(f"    [{agent_name}] appeal error: {exc}")
            return None

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_call_appeal_agent, name): name for name in AGENT_NAMES}
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                verdict = future.result(timeout=30)
                if verdict:
                    verdicts.append(verdict)
            except Exception as exc:
                print(f"    [{agent_name}] appeal timeout: {exc}")

    return verdicts


# ─── Data-Driven Rules Mode ($0, TMS-style) ───────────────────────────────────


def _run_data_driven_agents(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[ResearchVerdict]:
    """Rule-based verdicts using pre-fetched Phase 1 data. Zero LLM calls, zero cost.

    Mirrors TMS agent pattern: read structured data → apply thresholds → emit verdict.
    Each of the 5 agent roles applies its domain rules to already-available market_data.
    """
    now = datetime.now(timezone.utc).isoformat()
    sym = signal.symbol
    direction = signal.direction.value if hasattr(signal.direction, "value") else str(signal.direction)
    indicators = market_data.get("indicators", {}).get(sym, {})
    fundamentals = market_data.get("fundamentals", {}).get(sym, {})
    symbol_news = market_data.get("news", {}).get(sym, [])
    strat_state = portfolio_state.get("strategies", {}).get(signal.strategy, {})
    positions = strat_state.get("positions", {})
    max_pos = {"MOM": 10, "VAL": 5, "QNT": 20, "LEV": 3}.get(signal.strategy, 10)

    def _verdict(agent: str, d: str, delta: float, conv: str, reason: str, metrics: dict) -> ResearchVerdict:
        return ResearchVerdict(
            agent=agent, symbol=sym, direction=d,
            confidence_delta=round(delta, 2), conviction=conv,
            reasoning=reason, key_metrics=metrics, timestamp=now,
        )

    verdicts: list[ResearchVerdict] = []

    # ── Phase 1.6 펀더멘털 데이터 추출 ──────────────────────────────────────
    _fund = market_data.get("fundamental", {})
    _days_earn = _fund.get("earnings_blackout", {}).get(sym, 99)
    _ec = _fund.get("economic_blackout", {})
    _fomc_days = _ec.get("FOMC", 99)
    _cpi_days = _ec.get("CPI", 99)
    _ppi_days = _ec.get("PPI", 99)
    _analyst_info = _fund.get("analyst", {}).get(sym, {})
    _rec_mean = _analyst_info.get("rec_mean", 3.0)
    _target_price = _analyst_info.get("target_price", 0.0)
    _analyst_count = _analyst_info.get("analyst_count", 0)
    _insider_info = _fund.get("insider", {}).get(sym, {})
    _insider_net = _insider_info.get("net_30d", 0)

    # ── 1. technical_strategist ─────────────────────────────────────────────
    rsi = indicators.get("rsi")
    macd_cross = indicators.get("macd_cross", "")
    trend = indicators.get("trend", "")
    bb_pct_b = indicators.get("bb_pct_b")
    metrics_tech = {"rsi": rsi, "macd_cross": macd_cross, "trend": trend, "bb_pct_b": bb_pct_b}

    if rsi is not None and rsi > 75 and direction == "BUY":
        verdicts.append(_verdict("technical_strategist", "DISAGREE", -0.15, "STRONG",
            f"RSI={rsi:.0f} — 과매수 구간. 단기 조정 가능성.", metrics_tech))
    elif rsi is not None and rsi < 30 and direction == "BUY":
        verdicts.append(_verdict("technical_strategist", "AGREE", +0.10, "MODERATE",
            f"RSI={rsi:.0f} — 과매도 반등 구간.", metrics_tech))
    elif trend == "BEARISH" and direction == "BUY":
        verdicts.append(_verdict("technical_strategist", "DISAGREE", -0.10, "MODERATE",
            f"추세 하락(BEARISH). MACD={macd_cross}.", metrics_tech))
    elif macd_cross == "bullish" and direction == "BUY":
        verdicts.append(_verdict("technical_strategist", "AGREE", +0.05, "WEAK",
            f"MACD 골든크로스 확인. RSI={rsi}.", metrics_tech))
    else:
        verdicts.append(_verdict("technical_strategist", "AGREE", 0.0, "WEAK",
            f"기술적 중립. RSI={rsi}, trend={trend}.", metrics_tech))

    # ── 2. risk_controller ──────────────────────────────────────────────────
    metrics_risk = {"bb_pct_b": bb_pct_b, "regime": regime.regime, "vix": regime.vix_level}

    if bb_pct_b is not None and bb_pct_b > 1.0 and direction == "BUY":
        verdicts.append(_verdict("risk_controller", "VETO", 0.0, "STRONG",
            f"BB %B={bb_pct_b:.2f} > 1.0 — 볼린저밴드 상단 돌파. 극단적 과매수 VETO.", metrics_risk))
    elif regime.regime == "CRISIS":
        verdicts.append(_verdict("risk_controller", "DISAGREE", -0.20, "STRONG",
            f"CRISIS 레짐. VIX={regime.vix_level:.1f} — 전략적 리스크 축소.", metrics_risk))
    elif regime.regime == "BEAR" and direction == "BUY":
        verdicts.append(_verdict("risk_controller", "DISAGREE", -0.10, "MODERATE",
            f"BEAR 레짐 진입 중. 신규 매수 리스크 상승.", metrics_risk))
    else:
        verdicts.append(_verdict("risk_controller", "AGREE", 0.0, "WEAK",
            f"리스크 정상 범위. Regime={regime.regime}, VIX={regime.vix_level:.1f}.", metrics_risk))

    # ── 3. equity_research ──────────────────────────────────────────────────
    pe = fundamentals.get("pe")
    fcf_yield = fundamentals.get("fcf_yield")
    roe = fundamentals.get("roe")
    neg_news = sum(1 for n in symbol_news if any(
        kw in n.get("title", "").lower()
        for kw in ["downgrade", "miss", "cut", "loss", "warning", "recall", "lawsuit", "layoff"]
    ))
    metrics_eq = {"pe": pe, "fcf_yield": fcf_yield, "roe": roe, "neg_news_count": neg_news}

    if neg_news >= 2:
        verdicts.append(_verdict("equity_research", "DISAGREE", -0.10, "MODERATE",
            f"부정 뉴스 {neg_news}건 감지. 펀더멘탈 리스크.", metrics_eq))
    elif pe is not None and pe > 40 and direction == "BUY":
        verdicts.append(_verdict("equity_research", "DISAGREE", -0.08, "WEAK",
            f"PE={pe:.1f} — 고평가 구간(>40). 밸류에이션 부담.", metrics_eq))
    elif fcf_yield is not None and fcf_yield > 0.05 and direction == "BUY":
        verdicts.append(_verdict("equity_research", "AGREE", +0.08, "MODERATE",
            f"FCF_Yield={fcf_yield:.1%} — 양호한 현금흐름 수익률.", metrics_eq))
    else:
        verdicts.append(_verdict("equity_research", "AGREE", 0.0, "WEAK",
            f"펀더멘탈 중립. PE={pe}, FCF_Yield={fcf_yield}.", metrics_eq))

    # ── 3a. equity_research (Phase 1.6: 실적발표 블랙아웃) ──────────────────
    if _days_earn <= 3 and direction == "BUY":
        metrics_earn = {"days_to_earnings": _days_earn}
        verdicts.append(_verdict("equity_research", "DISAGREE", -0.20, "STRONG",
            f"실적발표 D-{_days_earn} — 이벤트 리스크. 포지션 50% 축소 권고.", metrics_earn))

    # ── 3b. equity_research (Phase 1.6: 애널리스트 컨센서스) ────────────────
    if _analyst_count >= 5:  # 커버리지 충분할 때만 적용
        metrics_ana = {"rec_mean": _rec_mean, "target_price": _target_price, "analyst_count": _analyst_count}
        if _rec_mean >= 4.0:
            verdicts.append(_verdict("equity_research", "DISAGREE", -0.15, "MODERATE",
                f"애널리스트 컨센서스 매도 (rec={_rec_mean:.1f}/5.0, N={_analyst_count}).", metrics_ana))
        elif _rec_mean <= 2.0 and _target_price > 0 and signal.price > 0:
            current_price = signal.price
            upside = (_target_price - current_price) / current_price
            if upside >= 0.10:
                verdicts.append(_verdict("equity_research", "AGREE", +0.10, "MODERATE",
                    f"애널리스트 강력매수 (rec={_rec_mean:.1f}) + 목표가 업사이드 {upside:.0%}.", metrics_ana))

    # ── 3c. equity_research (Phase 1.6: 내부자 거래) ─────────────────────────
    if _insider_net <= -3:
        metrics_ins = {"insider_net_30d": _insider_net}
        verdicts.append(_verdict("equity_research", "DISAGREE", -0.10, "MODERATE",
            f"내부자 순매도 {abs(_insider_net)}건 (30일) — 경영진 신뢰 저하.", metrics_ins))
    elif _insider_net >= 3 and direction == "BUY":
        metrics_ins = {"insider_net_30d": _insider_net}
        verdicts.append(_verdict("equity_research", "AGREE", +0.05, "WEAK",
            f"내부자 순매수 {_insider_net}건 (30일) — 경영진 신뢰.", metrics_ins))

    # ── 4. macro_economist ──────────────────────────────────────────────────
    macro_news = market_data.get("news", {}).get("_MACRO", [])
    macro_neg = sum(1 for n in macro_news[:10] if any(
        kw in n.get("title", "").lower()
        for kw in ["recession", "inflation", "rate hike", "tariff", "crisis", "crash", "default"]
    ))
    metrics_macro = {"regime": regime.regime, "macro_neg_news": macro_neg, "sp500_vs_sma200": regime.sp500_vs_sma200}

    if regime.regime in ("BEAR", "CRISIS"):
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.15, "STRONG",
            f"매크로 역풍. Regime={regime.regime}, SPY/SMA200={regime.sp500_vs_sma200:.3f}.", metrics_macro))
    elif macro_neg >= 3:
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.08, "MODERATE",
            f"부정 매크로 뉴스 {macro_neg}건. 불확실성 상승.", metrics_macro))
    else:
        verdicts.append(_verdict("macro_economist", "AGREE", 0.0, "WEAK",
            f"매크로 중립. Regime={regime.regime}.", metrics_macro))

    # ── 4a. macro_economist (Phase 1.6: FOMC/CPI 블랙아웃) ──────────────────
    metrics_ec = {"fomc_days": _fomc_days, "cpi_days": _cpi_days, "ppi_days": _ppi_days}
    if _fomc_days <= 2 and direction == "BUY":
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.25, "STRONG",
            f"FOMC D-{_fomc_days} — 금리 결정 대기. 신규 BUY 전면 차단.", metrics_ec))
    elif _fomc_days <= 5:
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.10, "MODERATE",
            f"FOMC D-{_fomc_days} — 포지션 축소 권고.", metrics_ec))
    elif _cpi_days <= 1 and direction == "BUY":
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.15, "MODERATE",
            f"CPI D-{_cpi_days} — 인플레이션 데이터 대기. 포지션 30% 축소 권고.", metrics_ec))
    elif _ppi_days <= 1 and direction == "BUY":
        verdicts.append(_verdict("macro_economist", "DISAGREE", -0.08, "WEAK",
            f"PPI D-{_ppi_days} — 생산자물가 발표 임박.", metrics_ec))

    # ── 5. portfolio_architect ──────────────────────────────────────────────
    pos_count = len(positions)
    metrics_port = {"position_count": pos_count, "max_positions": max_pos, "strategy": signal.strategy}

    if pos_count >= max_pos and direction == "BUY":
        verdicts.append(_verdict("portfolio_architect", "DISAGREE", -0.10, "MODERATE",
            f"{signal.strategy} 포지션 {pos_count}/{max_pos} — 최대 도달. 신규 매수 비권고.", metrics_port))
    else:
        verdicts.append(_verdict("portfolio_architect", "AGREE", 0.0, "WEAK",
            f"{signal.strategy} 포지션 {pos_count}/{max_pos} — 여유 있음.", metrics_port))

    return verdicts
