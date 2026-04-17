"""한국 시장 Regime 판별 (US-corrected).

우선순위 규칙:
  1. US CRISIS → KR max BEAR (override, BULL/NEUTRAL 불가)
  2. VKOSPI >= 30 → CRISIS
  3. VKOSPI >= 22 → BEAR
  4. SOX < SMA200 (sox_trend < 1.0) AND semi weight 고려 → -1 tier
  5. 반도체 수출 YoY < -15% → BULL 금지
  6. KOSPI > SMA200 AND VKOSPI < 20 → BULL
  7. default → NEUTRAL
"""
from __future__ import annotations

import logging

from kr_research.models import KRRegime, KRRegimeType

_logger = logging.getLogger("kr_research.regime")

# Tier 순서: 높을수록 낙관적
_TIER: dict[KRRegimeType, int] = {
    "BULL": 3,
    "NEUTRAL": 2,
    "BEAR": 1,
    "CRISIS": 0,
}
_TIER_INV: dict[int, KRRegimeType] = {v: k for k, v in _TIER.items()}

_US_CRISIS_MAX_TIER = _TIER["BEAR"]  # US CRISIS → KR max BEAR


def detect_kr_regime(
    kr_snapshot: dict,
    us_regime: str = "NEUTRAL",
    sox_trend: float = 1.0,   # SOX / SMA200
    us_vix: float = 20.0,
) -> KRRegime:
    """
    Args:
        kr_snapshot: state/kr_market_state.json 호환 딕셔너리
        us_regime:   미국 Regime 문자열 ("BULL" | "NEUTRAL" | "BEAR" | "CRISIS")
        sox_trend:   SOX 지수 / SMA200 비율
        us_vix:      미국 VIX 수준

    Returns:
        KRRegime
    """
    kospi_section = kr_snapshot.get("kospi", {})
    vkospi_section = kr_snapshot.get("vkospi", {})
    semi_section = kr_snapshot.get("semiconductor_export", {})

    kospi_vs_sma200: float = float(kospi_section.get("kospi_vs_sma200", 1.0))
    vkospi: float = float(vkospi_section.get("level", 20.0))
    semi_yoy = semi_section.get("yoy_pct")  # may be None
    if semi_yoy is not None:
        semi_yoy = float(semi_yoy)

    factors: dict = {
        "kospi_trend": kospi_vs_sma200,
        "vkospi": vkospi,
        "sox_trend": sox_trend,
        "us_regime": us_regime,
        "us_vix": us_vix,
    }
    if semi_yoy is not None:
        factors["semi_export_yoy"] = semi_yoy

    us_crisis = us_regime == "CRISIS"

    # ── Rule 2/3: VKOSPI-based ──────────────────────────────────────────────
    if vkospi >= 30.0:
        raw_regime: KRRegimeType = "CRISIS"
    elif vkospi >= 22.0:
        raw_regime = "BEAR"
    # ── Rule 6: KOSPI trend + VKOSPI ────────────────────────────────────────
    elif kospi_vs_sma200 > 1.0 and vkospi < 20.0:
        raw_regime = "BULL"
    else:
        raw_regime = "NEUTRAL"

    # ── Rule 5: semi export cap ──────────────────────────────────────────────
    if semi_yoy is not None and semi_yoy < -15.0 and raw_regime == "BULL":
        raw_regime = "NEUTRAL"
        factors["semi_export_cap"] = True

    # ── Rule 4: SOX below SMA200 → -1 tier ──────────────────────────────────
    if sox_trend < 1.0:
        current_tier = _TIER[raw_regime]
        downgraded_tier = max(0, current_tier - 1)
        if downgraded_tier < current_tier:
            raw_regime = _TIER_INV[downgraded_tier]
            factors["sox_downgrade"] = True

    # ── Rule 1: US CRISIS cap ────────────────────────────────────────────────
    if us_crisis:
        current_tier = _TIER[raw_regime]
        if current_tier > _US_CRISIS_MAX_TIER:
            raw_regime = _TIER_INV[_US_CRISIS_MAX_TIER]
            factors["us_crisis_override"] = True

    # ── Confidence ───────────────────────────────────────────────────────────
    confidence = _compute_confidence(raw_regime, kospi_vs_sma200, vkospi, us_crisis)

    return KRRegime(
        regime=raw_regime,
        confidence=confidence,
        factors=factors,
    )


def _compute_confidence(
    regime: KRRegimeType,
    kospi_trend: float,
    vkospi: float,
    us_crisis: bool,
) -> float:
    """Compute regime confidence 0.0 ~ 1.0."""
    base: float

    if regime == "CRISIS":
        # Strong signals if VKOSPI very high
        base = min(1.0, (vkospi - 22.0) / 20.0 + 0.5) if vkospi >= 22 else 0.6
    elif regime == "BEAR":
        base = 0.6
    elif regime == "BULL":
        # Confidence based on how far above SMA200 + how low VKOSPI
        trend_conf = min(1.0, (kospi_trend - 1.0) / 0.1)
        vkospi_conf = max(0.0, 1.0 - (vkospi / 20.0))
        base = 0.5 + 0.25 * trend_conf + 0.25 * vkospi_conf
    else:  # NEUTRAL
        base = 0.5

    if us_crisis:
        base = max(base, 0.7)  # higher confidence when US override applies

    return round(min(1.0, max(0.0, base)), 3)
