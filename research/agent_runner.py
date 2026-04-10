"""Hybrid LLM agent runner for Research Overlay.

Supports 3 modes:
- rules: Original rule-based heuristics (default, zero cost)
- gemini: Gemini 2.0 Flash analysis (free tier, for cron)
- claude: Claude Code agent analysis (interactive, subscription tokens)

Environment variable RESEARCH_MODE controls the mode.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from strategies.base_strategy import Signal
from .agent_prompts import AGENT_PROMPTS, APPEAL_SUFFIX, AGENT_NAMES
from .models import RegimeDetection, ResearchVerdict

_MODE = os.environ.get("RESEARCH_AGENTS", "rules")

# Gemini rate limit: 15 req/min → 5 second interval between requests
_GEMINI_DELAY = 5.0
_GEMINI_MAX_RETRIES = 3
_GEMINI_BACKOFF_BASE = 10.0  # 429 시 첫 대기: 10초, 이후 20초, 40초


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

    if mode == "gemini":
        return _run_gemini_agents(signal, market_data, portfolio_state, regime)
    elif mode == "claude":
        return _run_claude_agents(signal, market_data, portfolio_state, regime)
    else:
        return []  # Caller should use existing rule-based logic


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

    if mode == "gemini":
        return _run_gemini_appeal(signal, market_data, portfolio_state, regime, appeal_context)
    elif mode == "claude":
        return _run_claude_appeal(signal, market_data, portfolio_state, regime, appeal_context)
    else:
        return []


# ─── Gemini Mode (Free Tier) ───────────────────────────────────────────────


def _get_gemini_client():
    """Get Gemini client. Returns None if unavailable."""
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return None
        return genai.Client(api_key=api_key)
    except ImportError:
        return None


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


def _gemini_call_with_retry(client, prompt: str, agent_name: str) -> str | None:
    """Gemini API call with exponential backoff on 429."""
    for attempt in range(_GEMINI_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            return response.text
        except Exception as exc:
            err_str = str(exc)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = _GEMINI_BACKOFF_BASE * (2 ** attempt)
                print(f"    [{agent_name}] 429 rate limit — retry {attempt + 1}/{_GEMINI_MAX_RETRIES} in {wait:.0f}s")
                time.sleep(wait)
            else:
                print(f"    [{agent_name}] Gemini error: {exc}")
                return None
    print(f"    [{agent_name}] 429 — max retries exceeded")
    return None


def _run_gemini_agents(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
) -> list[ResearchVerdict]:
    """Run 5 agents sequentially via Gemini Flash (rate limit aware with retry)."""
    client = _get_gemini_client()
    if client is None:
        print("  [agent_runner] Gemini unavailable, skipping real analysis")
        return []

    verdicts: list[ResearchVerdict] = []

    for agent_name in AGENT_NAMES:
        system_prompt = AGENT_PROMPTS[agent_name]
        context = _build_agent_context(agent_name, signal, market_data, portfolio_state, regime)
        full_prompt = f"{system_prompt}\n\n--- SIGNAL CONTEXT ---\n{context}"

        text = _gemini_call_with_retry(client, full_prompt, agent_name)
        if text:
            verdict = _parse_verdict_json(text, agent_name, signal.symbol)
            if verdict:
                verdicts.append(verdict)
                print(f"    [{agent_name}] {verdict.direction} (delta={verdict.confidence_delta:+.2f})")
            else:
                print(f"    [{agent_name}] parse failed, using fallback")

        time.sleep(_GEMINI_DELAY)  # Rate limit

    return verdicts


def _run_gemini_appeal(
    signal: Signal,
    market_data: dict,
    portfolio_state: dict,
    regime: RegimeDetection,
    appeal_context: dict,
) -> list[ResearchVerdict]:
    """Run appeal analysis via Gemini Flash (with retry)."""
    client = _get_gemini_client()
    if client is None:
        return []

    failed_checks = appeal_context.get("failed_checks", [])
    appeal_suffix = APPEAL_SUFFIX.format(failed_checks=", ".join(failed_checks))

    verdicts: list[ResearchVerdict] = []

    for agent_name in AGENT_NAMES:
        system_prompt = AGENT_PROMPTS[agent_name] + "\n" + appeal_suffix
        context = _build_agent_context(agent_name, signal, market_data, portfolio_state, regime)
        context += f"\nFailed risk checks: {', '.join(failed_checks)}"
        full_prompt = f"{system_prompt}\n\n--- APPEAL CONTEXT ---\n{context}"

        text = _gemini_call_with_retry(client, full_prompt, agent_name)
        if text:
            verdict = _parse_verdict_json(text, agent_name, signal.symbol)
            if verdict:
                verdicts.append(verdict)
        time.sleep(_GEMINI_DELAY)

    return verdicts


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
        print("  [agent_runner] Claude unavailable (no API key or SDK), falling back to Gemini")
        return _run_gemini_agents(signal, market_data, portfolio_state, regime)

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
        return _run_gemini_appeal(signal, market_data, portfolio_state, regime, appeal_context)

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
