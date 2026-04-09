"""Regime-based dynamic strategy allocation (Bridgewater-style)."""

from __future__ import annotations

REGIME_ALLOCATIONS: dict[str, dict[str, float]] = {
    "BULL":    {"MOM": 0.30, "VAL": 0.20, "QNT": 0.25, "LEV": 0.25, "CASH": 0.00},
    "NEUTRAL": {"MOM": 0.25, "VAL": 0.25, "QNT": 0.30, "LEV": 0.20, "CASH": 0.00},
    "BEAR":    {"MOM": 0.15, "VAL": 0.35, "QNT": 0.30, "LEV": 0.00, "CASH": 0.20},
    "CRISIS":  {"MOM": 0.10, "VAL": 0.30, "QNT": 0.20, "LEV": 0.00, "CASH": 0.40},
}

_REGIME_DESCRIPTIONS: dict[str, str] = {
    "BULL": (
        "강세장: 모멘텀(MOM) 30% + 퀀트(QNT) 25% + 레버리지(LEV) 25% + 가치(VAL) 20%. "
        "위험자산 비중 최대, 현금 0%."
    ),
    "NEUTRAL": (
        "중립장: 퀀트(QNT) 30% + 모멘텀(MOM) 25% + 가치(VAL) 25% + 레버리지(LEV) 20%. "
        "균형 배분, 방향성 중립 포지션."
    ),
    "BEAR": (
        "약세장: 가치(VAL) 35% + 퀀트(QNT) 30% + 현금(CASH) 20% + 모멘텀(MOM) 15%. "
        "레버리지 완전 제거, 방어적 배분."
    ),
    "CRISIS": (
        "위기장: 현금(CASH) 40% + 가치(VAL) 30% + 퀀트(QNT) 20% + 모멘텀(MOM) 10%. "
        "레버리지 0%, 현금 비중 최대, 자본 보존 우선."
    ),
}


def allocate(regime: str, total_capital: float) -> dict[str, float]:
    """Regime에 따라 전략별 자본 배분.

    Args:
        regime: "BULL" | "NEUTRAL" | "BEAR" | "CRISIS"
        total_capital: 전체 자본 (예: 100000)

    Returns:
        {"MOM": 30000, "VAL": 20000, "QNT": 25000, "LEV": 25000, "CASH": 0}

    알 수 없는 regime → NEUTRAL fallback
    """
    if regime not in REGIME_ALLOCATIONS:
        print(f"[regime_allocator] Unknown regime '{regime}' → NEUTRAL fallback")
        regime = "NEUTRAL"

    weights = REGIME_ALLOCATIONS[regime]
    allocation = {strategy: round(weight * total_capital, 2) for strategy, weight in weights.items()}

    print(f"[regime_allocator] Regime={regime} | Capital={total_capital:,.0f}")
    for strategy, amount in allocation.items():
        pct = weights[strategy] * 100
        print(f"  {strategy}: {amount:>10,.2f}  ({pct:.0f}%)")

    return allocation


def get_regime_description(regime: str) -> str:
    """Regime 설명 반환 (리포트용).

    알 수 없는 regime → NEUTRAL 설명 반환.
    """
    return _REGIME_DESCRIPTIONS.get(regime, _REGIME_DESCRIPTIONS["NEUTRAL"])
