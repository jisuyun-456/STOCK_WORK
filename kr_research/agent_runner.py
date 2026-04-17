"""KR Research Agent Runner — HIGH #1 FIX: real Claude API dispatch.

두 가지 모드:
  rules:  Python 규칙 기반 (LLM 호출 없음, $0, 백테스트용)
  claude: Anthropic Claude API 실제 호출 (claude-sonnet-4-6)

이전 구현의 `claude` 모드는 "rules fallback으로 돌아감" 이라는 dead stub이었음.
이 모듈은 진짜 Anthropic client.messages.create()를 호출한다.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

from anthropic import Anthropic

from kr_research.models import KRVerdict, KRRegime

_logger = logging.getLogger("kr_research.agent_runner")
_client: Anthropic | None = None


def _get_client() -> Anthropic:
    """Lazy singleton Anthropic client."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        _client = Anthropic(api_key=api_key)
    return _client


# ── rules mode ─────────────────────────────────────────────────────────────

def run_rules(tickers: list[str], regime: KRRegime) -> list[KRVerdict]:
    """
    Layer 1 rules-only mode (no Claude). Used in backtest / dry-run.

    Rules:
    - CRISIS → SELL all
    - BEAR   → HOLD all
    - else   → HOLD (signals come from scorer composite)
    """
    verdicts: list[KRVerdict] = []
    regime_type = regime.regime

    for ticker in tickers:
        if regime_type == "CRISIS":
            verdict_str: str = "SELL"
            rationale = f"CRISIS regime — all positions SELL (rules mode)"
            confidence = 0.85
        elif regime_type == "BEAR":
            verdict_str = "HOLD"
            rationale = f"BEAR regime — hold, no new entries (rules mode)"
            confidence = 0.65
        else:
            verdict_str = "HOLD"
            rationale = f"{regime_type} regime — HOLD pending scorer ranking (rules mode)"
            confidence = 0.5

        verdicts.append(KRVerdict(
            ticker=ticker,
            verdict=verdict_str,  # type: ignore[arg-type]
            confidence=confidence,
            agent="rules",
            rationale=rationale,
        ))

    return verdicts


# ── claude mode — HIGH #1 FIX ─────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a Korean stock market analyst specializing in KRX-listed equities.
Your role: analyze a given KRX ticker based on the market regime and snapshot data provided.
Respond ONLY with a valid JSON object — no markdown, no explanation, no extra text.
Required format: {"verdict": "BUY|HOLD|SELL|VETO", "confidence": 0.0-1.0, "rationale": "brief reason"}

Verdict definitions:
- BUY:  Strong positive signal, worth accumulating
- HOLD: Neutral, keep existing position or wait
- SELL: Negative signal, reduce or exit
- VETO: Extreme risk, mandatory avoidance (regulatory/fraud/delisting risk)"""


def run_claude(
    tickers: list[str],
    regime: KRRegime,
    market_snapshot: dict,
    mode: Literal["sequential", "parallel"] = "sequential",
) -> list[KRVerdict]:
    """
    HIGH #1 FIX: Actually calls Claude API for each ticker.

    Args:
        tickers:         KRX ticker codes to analyze
        regime:          Current KR market regime
        market_snapshot: Market data dict
        mode:            "sequential" (default) | "parallel" (ThreadPoolExecutor)

    Returns:
        list[KRVerdict] — one per ticker; parse errors → HOLD/0.3
    """
    if mode == "parallel":
        return _run_parallel(tickers, regime, market_snapshot)
    return _run_sequential(tickers, regime, market_snapshot)


def _run_sequential(tickers: list[str], regime: KRRegime, snapshot: dict) -> list[KRVerdict]:
    verdicts: list[KRVerdict] = []
    client = _get_client()

    for ticker in tickers:
        try:
            prompt = _build_analysis_prompt(ticker, regime, snapshot)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            verdict = _parse_verdict(ticker, raw_text)
            verdicts.append(verdict)
        except Exception as e:
            _logger.warning("run_claude(%s) failed: %s", ticker, e)
            verdicts.append(KRVerdict(
                ticker=ticker,
                verdict="HOLD",
                confidence=0.3,
                agent="claude",
                rationale=f"error: {e}",
            ))

    return verdicts


def _run_parallel(tickers: list[str], regime: KRRegime, snapshot: dict) -> list[KRVerdict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    client = _get_client()
    results: dict[str, KRVerdict] = {}

    def analyze_one(ticker: str) -> tuple[str, KRVerdict]:
        try:
            prompt = _build_analysis_prompt(ticker, regime, snapshot)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            return ticker, _parse_verdict(ticker, raw_text)
        except Exception as e:
            _logger.warning("run_claude parallel(%s) failed: %s", ticker, e)
            return ticker, KRVerdict(
                ticker=ticker,
                verdict="HOLD",
                confidence=0.3,
                agent="claude",
                rationale=f"error: {e}",
            )

    with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
        futures = {pool.submit(analyze_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker_key, verdict = future.result()
            results[ticker_key] = verdict

    # Return in original order
    return [results[t] for t in tickers if t in results]


# ── Prompt builder ─────────────────────────────────────────────────────────

def _build_analysis_prompt(ticker: str, regime: KRRegime, snapshot: dict) -> str:
    """Build concise analysis prompt for Claude."""
    snapshot_str = str(snapshot)[:500]
    factors_str = str(regime.factors)[:300]

    return (
        f"Analyze KRX ticker: {ticker}\n\n"
        f"Market regime: {regime.regime} (confidence: {regime.confidence:.0%})\n"
        f"Regime factors: {factors_str}\n"
        f"Market snapshot: {snapshot_str}\n\n"
        f'Respond with ONLY valid JSON: {{"verdict": "BUY|HOLD|SELL|VETO", '
        f'"confidence": 0.0-1.0, "rationale": "brief reason"}}'
    )


# ── Response parser ────────────────────────────────────────────────────────

def _parse_verdict(ticker: str, text: str) -> KRVerdict:
    """Parse Claude response text → KRVerdict.

    Handles:
    - Clean JSON: {"verdict": "BUY", ...}
    - JSON embedded in text/markdown
    - Malformed or missing JSON → HOLD fallback
    """
    _VALID_VERDICTS = {"BUY", "HOLD", "SELL", "VETO"}

    # Try to extract JSON from text
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if not match:
        _logger.debug("_parse_verdict(%s): no JSON found in response", ticker)
        return KRVerdict(
            ticker=ticker,
            verdict="HOLD",
            confidence=0.3,
            agent="claude",
            rationale="no json in response",
        )

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as e:
        _logger.debug("_parse_verdict(%s): JSON decode error: %s", ticker, e)
        return KRVerdict(
            ticker=ticker,
            verdict="HOLD",
            confidence=0.3,
            agent="claude",
            rationale=f"json_parse_error: {e}",
        )

    verdict_str = str(data.get("verdict", "HOLD")).upper()
    if verdict_str not in _VALID_VERDICTS:
        verdict_str = "HOLD"

    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    rationale = str(data.get("rationale", ""))

    return KRVerdict(
        ticker=ticker,
        verdict=verdict_str,  # type: ignore[arg-type]
        confidence=confidence,
        agent="claude",
        rationale=rationale,
        veto=verdict_str == "VETO",
        veto_reason=rationale if verdict_str == "VETO" else "",
    )
