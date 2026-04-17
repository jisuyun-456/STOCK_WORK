"""KR macro data → US signal confidence adjustment.

apply_kr_to_us_bias() takes KR context and a list of US signals, returning
an adjusted copy (input is never mutated).
"""
import logging

_logger = logging.getLogger("kr_overlay.kr_to_us")

# US tickers that are meaningfully correlated with KR semiconductor exports.
_KR_SEMI_US_TICKERS: frozenset[str] = frozenset(
    {"MU", "LRCX", "AMAT", "KLAC", "NVDA", "TSM"}
)

# US entertainment/content tickers boosted by K-content popularity.
_KR_CONTENT_US_TICKERS: frozenset[str] = frozenset({"NFLX", "SPOT", "META"})

# KRW outflow threshold: -10 trillion KRW (exclusive — must be *below* this)
_OUTFLOW_THRESHOLD_KRW: int = -10_000_000_000_000


def apply_kr_to_us_bias(
    kr_context: dict,           # {semi_export_yoy, foreign_flow_20d_krw, sector_scores}
    us_signals: list[dict],     # [{ticker, side, confidence, strategy, reason}]
) -> list[dict]:
    """Apply KR macro data to adjust US signal confidence.

    Rules
    -----
    1. semi_export_yoy < -15 % → US semiconductor tickers confidence -= 0.20
    2. foreign_flow_20d_krw < -10T KRW → ALL risk assets confidence -= 0.10
    3. sector_scores["content"] > 0.3 → US entertainment tickers confidence += 0.05

    Returns a new list with copied dicts; the original *us_signals* is never
    mutated.
    """
    semi_yoy: float | None = kr_context.get("semi_export_yoy")   # may be None
    foreign_flow: float = kr_context.get("foreign_flow_20d_krw", 0)
    content_score: float = kr_context.get("sector_scores", {}).get("content", 0.0)

    adjusted: list[dict] = []

    for sig in us_signals:
        s = dict(sig)           # shallow copy — all values are primitives
        ticker: str = s.get("ticker", "")
        conf: float = float(s.get("confidence", 0.5))

        # Rule 1: semiconductor export contraction
        if semi_yoy is not None and semi_yoy < -15.0 and ticker in _KR_SEMI_US_TICKERS:
            conf = max(0.0, conf - 0.20)
            s["kr_overlay_note"] = (
                f"KR semi export YoY {semi_yoy:.1f}% → confidence reduced"
            )
            _logger.debug("%s: semi export contraction → confidence -0.20", ticker)

        # Rule 2: foreign outflow (strictly below threshold)
        if foreign_flow < _OUTFLOW_THRESHOLD_KRW:
            conf = max(0.0, conf - 0.10)
            existing_note: str = s.get("kr_overlay_note", "")
            s["kr_overlay_note"] = (existing_note + " KR foreign outflow").strip()
            _logger.debug("%s: KR foreign outflow → confidence -0.10", ticker)

        # Rule 3: K-content bullish
        if content_score > 0.3 and ticker in _KR_CONTENT_US_TICKERS:
            conf = min(1.0, conf + 0.05)
            _logger.debug("%s: K-content score %.2f → confidence +0.05", ticker, content_score)

        s["confidence"] = conf
        adjusted.append(s)

    return adjusted
