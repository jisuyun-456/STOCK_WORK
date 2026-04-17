"""US market context → KR regime correction.

apply_us_to_kr_bias() takes the raw KR regime string and a US context dict,
then returns a (possibly downgraded) regime string plus a sector bias dict.
"""
import logging

_logger = logging.getLogger("kr_overlay.us_to_kr")

# Ordered from most pessimistic (index 0) to most optimistic (index 3).
_TIER = ["CRISIS", "BEAR", "NEUTRAL", "BULL"]


def apply_us_to_kr_bias(
    kr_regime_raw: str,         # BULL|NEUTRAL|BEAR|CRISIS
    us_context: dict,           # {us_regime, nasdaq_sma200_ratio, vix, dxy_sma200_ratio, sox_sma200_ratio}
) -> tuple[str, dict]:
    """Apply US market context to correct KR regime.

    Rules
    -----
    1. NASDAQ < SMA200 (ratio < 1.0) AND VIX > 25 → KR regime <= NEUTRAL
    2. SOX < SMA200 (sox_ratio < 1.0) → kr_semi_bias -= 0.15
    3. DXY > SMA200 * 1.05 (ratio > 1.05) → kr_export_bias += 0.05
    4. US regime == CRISIS → KR regime forced to BEAR maximum

    Returns
    -------
    corrected_regime : str
        Possibly downgraded from kr_regime_raw.
    bias_adjustments : dict
        Sector float adjustments, e.g. {"semiconductor": -0.15}.
    """
    vix = us_context.get("vix", 20.0)
    nasdaq_ratio = us_context.get("nasdaq_sma200_ratio", 1.0)
    sox_ratio = us_context.get("sox_sma200_ratio", 1.0)
    dxy_ratio = us_context.get("dxy_sma200_ratio", 1.0)
    us_regime = us_context.get("us_regime", "NEUTRAL")

    corrected = kr_regime_raw
    bias: dict[str, float] = {}

    # Rule 4: US CRISIS → cap KR at BEAR
    if us_regime == "CRISIS":
        corrected = _cap_regime(corrected, "BEAR")
        _logger.info("US CRISIS → KR regime capped at BEAR (was %s)", kr_regime_raw)

    # Rule 1: NASDAQ below SMA200 + elevated VIX → cap at NEUTRAL
    if nasdaq_ratio < 1.0 and vix > 25:
        corrected = _cap_regime(corrected, "NEUTRAL")
        _logger.info(
            "NASDAQ below SMA200 (%.3f) + VIX %.1f → KR regime capped at NEUTRAL",
            nasdaq_ratio, vix,
        )

    # Rule 2: SOX below SMA200 → negative semiconductor sector bias
    if sox_ratio < 1.0:
        bias["semiconductor"] = bias.get("semiconductor", 0.0) - 0.15

    # Rule 3: Strong dollar (DXY > SMA200 * 1.05) → positive export bias
    if dxy_ratio > 1.05:
        bias["export"] = bias.get("export", 0.0) + 0.05

    return corrected, bias


def _cap_regime(current: str, cap: str) -> str:
    """Return the more pessimistic (lower tier) of *current* and *cap*."""
    curr_idx = _TIER.index(current) if current in _TIER else 2
    cap_idx = _TIER.index(cap) if cap in _TIER else 2
    return _TIER[min(curr_idx, cap_idx)]
