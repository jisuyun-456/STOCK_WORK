"""Layer 1 pykrx-based scorer — Claude API 호출 없음.

각 종목에 대해 momentum/value/flow/shorting 4개 점수를 계산하고
composite 가중합으로 정렬한다.

composite = 0.3*momentum + 0.2*value + 0.3*flow + 0.2*shorting
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_logger = logging.getLogger("kr_research.scorer")

# 가중치
_W_MOMENTUM = 0.3
_W_VALUE = 0.2
_W_FLOW = 0.3
_W_SHORTING = 0.2


@dataclass
class ScoredStock:
    ticker: str
    name: str = ""
    market: str = ""
    momentum_score: float = 0.0
    value_score: float = 0.0
    flow_score: float = 0.0
    shorting_score: float = 0.0
    composite: float = 0.0


# ── Internal fetchers (monkeypatched in tests) ─────────────────────────────

def _fetch_momentum(ticker: str, snapshot: dict) -> float:
    """1-month return from pykrx OHLCV. Returns 0.0 on failure."""
    try:
        from kr_data.pykrx_client import fetch_ohlcv_batch
        today = datetime.now()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=35)).strftime("%Y%m%d")
        df = fetch_ohlcv_batch([ticker], start, end)
        if df is None or df.empty:
            return 0.0
        # df has a date column (first column after reset_index) and ticker column
        ticker_df = df[df["ticker"] == ticker].copy()
        if ticker_df.empty or len(ticker_df) < 2:
            return 0.0
        # sort by the date column (first column)
        date_col = ticker_df.columns[0]
        ticker_df = ticker_df.sort_values(date_col)
        close_col = next((c for c in ticker_df.columns if c in ("종가", "Close")), None)
        if close_col is None:
            return 0.0
        first = float(ticker_df[close_col].iloc[0])
        last = float(ticker_df[close_col].iloc[-1])
        if first == 0:
            return 0.0
        return (last - first) / first
    except Exception as exc:
        _logger.debug("_fetch_momentum(%s): %s", ticker, exc)
        return 0.0


def _fetch_value(ticker: str, snapshot: dict) -> float:
    """1/PBR normalized value score. Returns 0.5 on failure."""
    try:
        from kr_data.pykrx_client import fetch_market_fundamental
        today = datetime.now().strftime("%Y%m%d")
        df = fetch_market_fundamental(today, market="KOSPI")
        if df is None or ticker not in df.index:
            # try KOSDAQ
            df = fetch_market_fundamental(today, market="KOSDAQ")
        if df is None or ticker not in df.index:
            return 0.5
        pbr_col = next((c for c in df.columns if "PBR" in str(c).upper()), None)
        if pbr_col is None:
            return 0.5
        pbr = float(df.loc[ticker, pbr_col])
        if pbr <= 0:
            return 0.5
        # 1/PBR capped at 1.0 (PBR=1.0 → score=1.0, PBR=2 → 0.5, PBR=0.5 → 1.0)
        return min(1.0, 1.0 / pbr)
    except Exception as exc:
        _logger.debug("_fetch_value(%s): %s", ticker, exc)
        return 0.5


def _fetch_flow(ticker: str, snapshot: dict) -> float:
    """Foreign net buy 20d in raw KRW units. Returns 0.0 on failure."""
    try:
        from kr_data.pykrx_client import fetch_investor_flow
        today = datetime.now()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=30)).strftime("%Y%m%d")
        df = fetch_investor_flow(ticker, start, end)
        if df is None or df.empty:
            return 0.0
        # Find foreign column: 외국인 or similar
        foreign_col = next(
            (c for c in df.columns if "외국인" in str(c) or "foreign" in str(c).lower()),
            None,
        )
        if foreign_col is None:
            return 0.0
        return float(df[foreign_col].sum())
    except Exception as exc:
        _logger.debug("_fetch_flow(%s): %s", ticker, exc)
        return 0.0


def _fetch_shorting_pct(ticker: str, snapshot: dict) -> float:
    """Shorting balance as percentage. Returns 0.0 on failure."""
    try:
        from kr_data.pykrx_client import fetch_shorting_balance
        today = datetime.now()
        end = today.strftime("%Y%m%d")
        start = (today - timedelta(days=7)).strftime("%Y%m%d")
        df = fetch_shorting_balance(ticker, start, end)
        if df is None or df.empty:
            return 0.0
        # Find balance ratio column
        pct_col = next(
            (c for c in df.columns if "비율" in str(c) or "ratio" in str(c).lower() or "Ratio" in str(c)),
            None,
        )
        if pct_col is not None:
            return float(df[pct_col].iloc[-1])
        # Fallback: last row first numeric column
        numeric_cols = df.select_dtypes("number").columns.tolist()
        if numeric_cols:
            return float(df[numeric_cols[0]].iloc[-1])
        return 0.0
    except Exception as exc:
        _logger.debug("_fetch_shorting_pct(%s): %s", ticker, exc)
        return 0.0


# ── Normalization ─────────────────────────────────────────────────────────

def _normalize_flow(raw: float) -> float:
    """Normalize raw KRW flow to [-1, 1] range using soft sigmoid-like scaling."""
    # 1조원 net buy → ~1.0 score
    scale = 1_000_000_000_000.0  # 1조
    if scale == 0:
        return 0.0
    return max(-1.0, min(1.0, raw / scale))


def _normalize_shorting(pct: float) -> float:
    """High shorting % is bearish: score = -pct/10, capped at [-1, 0]."""
    return max(-1.0, -pct / 10.0)


# ── Public API ────────────────────────────────────────────────────────────

def score_universe(universe: list[dict], market_snapshot: dict) -> list[ScoredStock]:
    """
    Score all stocks in universe using pykrx data (no Claude).

    Args:
        universe:        list of {"ticker": ..., "name": ..., "market": ..., "mcap_krw": ...}
        market_snapshot: {"date": ..., ...}

    Returns:
        list[ScoredStock] sorted by composite descending.
        On individual stock failure: score = 0.0 (don't fail entire universe).
    """
    results: list[ScoredStock] = []

    for stock in universe:
        ticker = stock["ticker"]
        name = stock.get("name", "")
        market = stock.get("market", "")

        # Momentum score
        try:
            momentum = _fetch_momentum(ticker, market_snapshot)
        except Exception:
            momentum = 0.0

        # Value score
        try:
            value = _fetch_value(ticker, market_snapshot)
        except Exception:
            value = 0.5

        # Flow score (normalized)
        try:
            raw_flow = _fetch_flow(ticker, market_snapshot)
            flow = _normalize_flow(raw_flow)
        except Exception:
            raw_flow = 0.0
            flow = 0.0

        # Shorting score (normalized)
        try:
            shorting_pct = _fetch_shorting_pct(ticker, market_snapshot)
            shorting = _normalize_shorting(shorting_pct)
        except Exception:
            shorting = 0.0

        composite = (
            _W_MOMENTUM * momentum
            + _W_VALUE * value
            + _W_FLOW * flow
            + _W_SHORTING * shorting
        )

        scored = ScoredStock(
            ticker=ticker,
            name=name,
            market=market,
            momentum_score=momentum,
            value_score=value,
            flow_score=flow,
            shorting_score=shorting,
            composite=composite,
        )
        results.append(scored)

    results.sort(key=lambda s: s.composite, reverse=True)
    return results


def select_top_n(scored: list[ScoredStock], n: int = 100) -> list[str]:
    """Return top N ticker symbols for Layer 2 Claude analysis."""
    return [s.ticker for s in sorted(scored, key=lambda x: x.composite, reverse=True)[:n]]
