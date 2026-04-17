"""kr_research CLI entry point — /analyze-kr 커맨드 진입점.

Full pipeline:
  1. detect_kr_regime(kr_snapshot)
  2. score_universe → select top N
  3. run_rules or run_claude per ticker
  4. aggregate verdicts
  5. save to state/kr_verdicts.json (optional)

Usage (CLI):
  python -m kr_research.analyzer --ticker 005930 --mode rules
  python -m kr_research.analyzer --top-n 50 --mode claude

Usage (Python API):
  from kr_research.analyzer import analyze_ticker, analyze_top_n
  result = analyze_ticker("005930", mode="rules")
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from kr_research.models import KRAnalysisResult, KRRegime, KRVerdict
from kr_research.regime import detect_kr_regime
from kr_research.scorer import score_universe, select_top_n
from kr_research.agent_runner import run_rules, run_claude
from kr_research.consensus import aggregate

_logger = logging.getLogger("kr_research.analyzer")

_PROJECT_ROOT = Path(__file__).parent.parent
_STATE_DIR = _PROJECT_ROOT / "state"
_KR_VERDICTS_PATH = _STATE_DIR / "kr_verdicts.json"
_KR_MARKET_STATE_PATH = _STATE_DIR / "kr_market_state.json"


# ── Market snapshot helpers ────────────────────────────────────────────────

def _load_market_snapshot() -> dict:
    """Load kr_market_state.json from state/. Returns empty dict on failure."""
    try:
        if _KR_MARKET_STATE_PATH.exists():
            with open(_KR_MARKET_STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _logger.warning("Could not load kr_market_state.json: %s", e)
    return {}


# ── State persistence ──────────────────────────────────────────────────────

def _load_verdicts_state() -> dict:
    try:
        if _KR_VERDICTS_PATH.exists():
            with open(_KR_VERDICTS_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_verdicts_state(results: list[KRAnalysisResult]) -> None:
    """Save analysis results to state/kr_verdicts.json."""
    _STATE_DIR.mkdir(exist_ok=True)
    data = {
        "analyzed_at": datetime.now().isoformat(),
        "count": len(results),
        "verdicts": [
            {
                "ticker": r.ticker,
                "verdict": r.consensus.verdict,
                "confidence": r.consensus.confidence,
                "rationale": r.consensus.rationale,
                "regime": r.regime.regime,
                "analyzed_at": r.analyzed_at.isoformat(),
            }
            for r in results
        ],
    }
    try:
        with open(_KR_VERDICTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _logger.info("Saved %d verdicts to %s", len(results), _KR_VERDICTS_PATH)
    except Exception as e:
        _logger.error("Failed to save verdicts: %s", e)


# ── Core analysis functions ────────────────────────────────────────────────

def analyze_ticker(
    ticker: str,
    mode: str = "rules",
    market_snapshot: dict | None = None,
) -> KRAnalysisResult | None:
    """
    Full analysis pipeline for a single ticker.

    Args:
        ticker:          KRX ticker code ("005930")
        mode:            "rules" or "claude"
        market_snapshot: market data dict (loaded from state/ if None)

    Returns:
        KRAnalysisResult or None on failure
    """
    if market_snapshot is None:
        market_snapshot = _load_market_snapshot()

    try:
        regime = detect_kr_regime(kr_snapshot=market_snapshot)
    except Exception as e:
        _logger.error("detect_kr_regime failed: %s", e)
        return None

    try:
        if mode == "claude":
            verdicts = run_claude(
                tickers=[ticker],
                regime=regime,
                market_snapshot=market_snapshot,
            )
        else:
            verdicts = run_rules(tickers=[ticker], regime=regime)
    except Exception as e:
        _logger.error("agent run failed for %s: %s", ticker, e)
        verdicts = []

    if not verdicts:
        _logger.warning("No verdicts for %s", ticker)
        return None

    consensus = aggregate(verdicts, regime)

    return KRAnalysisResult(
        ticker=ticker,
        verdicts=verdicts,
        consensus=consensus,
        regime=regime,
    )


def analyze_top_n(
    n: int = 100,
    mode: str = "rules",
    save_to_state: bool = True,
    market_snapshot: dict | None = None,
) -> list[KRAnalysisResult]:
    """
    Full pipeline: build_universe → score → top N → analyze each.

    Args:
        n:               Number of top stocks to analyze
        mode:            "rules" or "claude"
        save_to_state:   Save results to state/kr_verdicts.json
        market_snapshot: Override market snapshot

    Returns:
        list[KRAnalysisResult]
    """
    if market_snapshot is None:
        market_snapshot = _load_market_snapshot()

    # Build and score universe
    try:
        from kr_data.pykrx_client import build_universe
        universe = build_universe()
    except Exception as e:
        _logger.error("build_universe failed: %s", e)
        return []

    if not universe:
        _logger.warning("Universe is empty")
        return []

    scored = score_universe(universe, market_snapshot)
    top_tickers = select_top_n(scored, n=n)

    _logger.info("Analyzing top %d tickers (mode=%s)", len(top_tickers), mode)

    # Detect regime once
    try:
        regime = detect_kr_regime(kr_snapshot=market_snapshot)
    except Exception as e:
        _logger.error("detect_kr_regime failed: %s", e)
        return []

    # Run agents
    try:
        if mode == "claude":
            all_verdicts = run_claude(
                tickers=top_tickers,
                regime=regime,
                market_snapshot=market_snapshot,
            )
        else:
            all_verdicts = run_rules(tickers=top_tickers, regime=regime)
    except Exception as e:
        _logger.error("agent run failed: %s", e)
        return []

    # Build results
    results: list[KRAnalysisResult] = []
    verdicts_by_ticker: dict[str, list[KRVerdict]] = {}
    for v in all_verdicts:
        verdicts_by_ticker.setdefault(v.ticker, []).append(v)

    for ticker in top_tickers:
        ticker_verdicts = verdicts_by_ticker.get(ticker, [])
        if not ticker_verdicts:
            continue
        consensus = aggregate(ticker_verdicts, regime)
        results.append(KRAnalysisResult(
            ticker=ticker,
            verdicts=ticker_verdicts,
            consensus=consensus,
            regime=regime,
        ))

    if save_to_state and results:
        _save_verdicts_state(results)

    return results


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    import sys

    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="KR Research Analyzer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="단일 종목 분석 (예: 005930)")
    group.add_argument("--top-n", type=int, help="상위 N 종목 분석")
    parser.add_argument("--mode", choices=["rules", "claude"], default="rules")
    parser.add_argument("--no-save", action="store_true", help="state 저장 안함")
    args = parser.parse_args()

    if args.ticker:
        result = analyze_ticker(args.ticker, mode=args.mode)
        if result:
            print(f"\nTicker:    {result.ticker}")
            print(f"Verdict:   {result.consensus.verdict}")
            print(f"Confidence:{result.consensus.confidence:.0%}")
            print(f"Regime:    {result.regime.regime}")
            print(f"Rationale: {result.consensus.rationale}")
        else:
            print("Analysis failed.")
            sys.exit(1)
    else:
        results = analyze_top_n(
            n=args.top_n,
            mode=args.mode,
            save_to_state=not args.no_save,
        )
        buy_count = sum(1 for r in results if r.consensus.verdict == "BUY")
        sell_count = sum(1 for r in results if r.consensus.verdict == "SELL")
        hold_count = sum(1 for r in results if r.consensus.verdict == "HOLD")
        print(f"\nAnalyzed {len(results)} tickers")
        print(f"  BUY:  {buy_count}")
        print(f"  HOLD: {hold_count}")
        print(f"  SELL: {sell_count}")


if __name__ == "__main__":
    main()
