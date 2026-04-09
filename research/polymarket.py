"""Polymarket prediction market integration for macro regime signals.

Fetches public prediction market data from Polymarket's gamma API (no auth).
Filters for macro-relevant markets (Fed rate, recession, inflation, etc.)
and computes a single macro sentiment score (-1.0 to +1.0).
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

_GAMMA_API = "https://gamma-api.polymarket.com"
_REQUEST_TIMEOUT = 10

RELEVANT_KEYWORDS = [
    "federal reserve", "fed rate", "interest rate", "rate cut", "rate hike",
    "fed chair", "fed decrease", "fed increase",
    "recession", "inflation", "cpi", "unemployment", "gdp",
    "election", "tariff", "default", "debt ceiling",
    "stock market", "s&p 500", "s&p500", "nasdaq", "crash",
    "soft landing", "hard landing",
    "treasury", "oil price", "gold",
]

# Markets where "Yes" = bullish for stocks
BULLISH_KEYWORDS = [
    "rate cut", "soft landing", "no recession", "bull", "rally",
    "gdp growth", "employment",
]

# Markets where "Yes" = bearish for stocks
BEARISH_KEYWORDS = [
    "recession", "rate hike", "crash", "default", "debt ceiling",
    "hard landing", "inflation above", "unemployment above",
    "bear market", "tariff",
]


@dataclass
class PolymarketSignal:
    """Single prediction market data point."""

    question: str
    outcomes: list[str]
    probabilities: list[float]
    volume_usd: float
    end_date: str
    market_id: str


def fetch_macro_markets(max_markets: int = 20) -> list[PolymarketSignal]:
    """Fetch prediction markets relevant to macro events.

    Uses Polymarket gamma API (public, no auth). Filters by keyword relevance.

    Args:
        max_markets: Maximum markets to return.

    Returns:
        List of PolymarketSignal. Empty list on any error.
    """
    try:
        resp = requests.get(
            f"{_GAMMA_API}/markets",
            params={
                "closed": "false",
                "limit": 500,
                "order": "volume",
                "ascending": "false",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[polymarket] API fetch failed: {exc}")
        return []

    signals: list[PolymarketSignal] = []

    for market in data:
        question = (market.get("question") or "").lower()

        # Filter by keyword relevance
        if not any(kw in question for kw in RELEVANT_KEYWORDS):
            continue

        raw_outcomes = market.get("outcomes", [])
        raw_prices = market.get("outcomePrices", [])

        # API returns JSON strings, not lists
        if isinstance(raw_outcomes, str):
            try:
                import json
                raw_outcomes = json.loads(raw_outcomes)
            except (json.JSONDecodeError, TypeError):
                continue
        if isinstance(raw_prices, str):
            try:
                import json
                raw_prices = json.loads(raw_prices)
            except (json.JSONDecodeError, TypeError):
                continue

        if not raw_outcomes or not raw_prices:
            continue

        try:
            probs = [float(p) for p in raw_prices]
        except (ValueError, TypeError):
            continue

        outcomes = raw_outcomes if isinstance(raw_outcomes, list) else []

        volume = float(market.get("volume", 0) or 0)
        end_date = market.get("endDate", "")
        market_id = market.get("conditionId", market.get("id", ""))

        signals.append(PolymarketSignal(
            question=market.get("question", ""),
            outcomes=outcomes,
            probabilities=probs,
            volume_usd=volume,
            end_date=end_date,
            market_id=str(market_id),
        ))

    # Sort by volume (most liquid = most reliable)
    signals.sort(key=lambda s: s.volume_usd, reverse=True)
    return signals[:max_markets]


def compute_polymarket_score(signals: list[PolymarketSignal]) -> float:
    """Aggregate prediction market data into a macro sentiment score.

    Score: -1.0 (extremely bearish) to +1.0 (extremely bullish).
    Markets are weighted by volume (liquidity = reliability).

    Args:
        signals: List of PolymarketSignal from fetch_macro_markets().

    Returns:
        Float score in [-1.0, +1.0]. 0.0 if no relevant signals.
    """
    if not signals:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0

    for signal in signals:
        question_lower = signal.question.lower()

        # Determine if "Yes" outcome is bullish or bearish
        is_bullish = any(kw in question_lower for kw in BULLISH_KEYWORDS)
        is_bearish = any(kw in question_lower for kw in BEARISH_KEYWORDS)

        if not is_bullish and not is_bearish:
            continue  # Skip ambiguous markets

        # Get "Yes" probability (first outcome assumed to be "Yes")
        if not signal.probabilities:
            continue
        yes_prob = signal.probabilities[0]

        # Convert to directional contribution
        if is_bullish:
            contribution = (yes_prob - 0.5) * 2  # 0.5→0, 1.0→+1, 0.0→-1
        else:  # bearish
            contribution = (0.5 - yes_prob) * 2   # high yes_prob → negative score

        # Weight by volume (log scale to avoid mega-markets dominating)
        weight = max(1.0, _log_weight(signal.volume_usd))
        weighted_sum += contribution * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0

    score = weighted_sum / total_weight
    return max(-1.0, min(1.0, round(score, 3)))


def _log_weight(volume: float) -> float:
    """Convert volume to log-scale weight."""
    import math
    if volume <= 0:
        return 1.0
    return math.log10(volume + 1)
