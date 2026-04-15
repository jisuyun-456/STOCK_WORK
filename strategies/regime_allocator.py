"""Regime-based dynamic strategy allocation (Bridgewater-style)."""

from __future__ import annotations

# LEV+LEV_ST 합계 50% 고정 (각 25%) + 나머지 50%는 기존 비율을 비례 재정규화.
# LEV: 장기 레짐 기반 (SPY+TQQQ/SQQQ/BND+GLD), LEV_ST: 1~3일 VIX/SPY 모멘텀 기반.
# allocator 는 모든 regime 에서 LEV/LEV_ST 슬롯을 유지해 generate_signals() 가 호출되도록 보장.
REGIME_ALLOCATIONS: dict[str, dict[str, float]] = {
    "BULL":    {"MOM": 0.2000, "VAL": 0.1333, "QNT": 0.1667, "LEV": 0.25, "LEV_ST": 0.25, "CASH": 0.00},
    "NEUTRAL": {"MOM": 0.15625, "VAL": 0.15625, "QNT": 0.1875, "LEV": 0.25, "LEV_ST": 0.25, "CASH": 0.00},
    "BEAR":    {"MOM": 0.075, "VAL": 0.175, "QNT": 0.15, "LEV": 0.25, "LEV_ST": 0.25, "CASH": 0.10},
    # CRISIS: LEV는 내부에서 BND/GLD 방어 포지션, LEV_ST는 CASH 강제
    "CRISIS":  {"MOM": 0.05, "VAL": 0.15, "QNT": 0.10, "LEV": 0.25, "LEV_ST": 0.25, "CASH": 0.20},
}

_REGIME_DESCRIPTIONS: dict[str, str] = {
    "BULL": (
        "강세장: LEV 25%(SPY+TQQQ) + LEV_ST 25%(VIX/SPY 모멘텀) + MOM 20% + QNT 16.67% + VAL 13.33%. "
        "위험자산 비중 최대, 현금 0%."
    ),
    "NEUTRAL": (
        "중립장: LEV 25%(SPY+TQQQ) + LEV_ST 25%(VIX/SPY 모멘텀) + QNT 18.75% + MOM/VAL 각 15.625%. "
        "균형 배분, 방향성 중립 포지션."
    ),
    "BEAR": (
        "약세장: LEV 25%(SPY+SQQQ) + LEV_ST 25%(VIX/SPY 모멘텀) + VAL 17.5% + QNT 15% + 현금 10% + MOM 7.5%. "
        "LEV는 SQQQ 전환으로 하락 베팅."
    ),
    "CRISIS": (
        "위기장: LEV 25%(BND 60%+GLD 40% 방어) + LEV_ST 25%(CASH 강제) + "
        "VAL 15% + QNT 10% + MOM 5% + CASH 20%. "
        "실효: BND 15% + GLD 10% + 현금 45% + 개별주 30%. 자본 보존 최우선."
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


# ─── Emergency Exit Protocol ─────────────────────────────────────────────

# Regime transition → which strategies to liquidate
# NOTE: LEV 는 자체 generate_signals() 내에서 regime 전환 시 TQQQ↔SQQQ↔현금 을
# 직접 처리하므로 exit_rules 에서 제외한다. (Core-Satellite Barbell 재설계 2026-04-11)
_REGIME_EXIT_RULES: dict[str, dict[str, float]] = {
    # BEAR: MOM 50% 축소 (LEV 는 자체 관리)
    "BEAR": {"MOM": 0.5},
    # CRISIS: MOM 전량 청산, VAL+QNT 50% 축소 (LEV 는 자체 관리)
    "CRISIS": {"MOM": 1.0, "VAL": 0.5, "QNT": 0.5},
}


def generate_regime_exit_signals(
    new_regime: str,
    previous_regime: str,
    portfolios: dict,
) -> list:
    """Generate emergency SELL signals when regime transitions to BEAR/CRISIS.

    Args:
        new_regime: Current detected regime.
        previous_regime: Previous regime from regime_state.json.
        portfolios: portfolios.json content.

    Returns:
        List of Signal objects for emergency exits.
    """
    from strategies.base_strategy import Signal, Direction

    # Only trigger on transitions to more defensive regimes
    severity = {"BULL": 0, "NEUTRAL": 1, "BEAR": 2, "CRISIS": 3}
    if severity.get(new_regime, 0) <= severity.get(previous_regime, 0):
        return []  # Not a defensive transition

    exit_rules = _REGIME_EXIT_RULES.get(new_regime, {})
    if not exit_rules:
        return []

    signals = []
    for strategy_code, liquidation_pct in exit_rules.items():
        strat_data = portfolios.get("strategies", {}).get(strategy_code, {})
        positions = strat_data.get("positions", {})

        for symbol, pos in positions.items():
            qty = pos.get("qty", 0)
            if qty <= 0:
                continue

            signals.append(Signal(
                strategy=strategy_code,
                symbol=symbol,
                direction=Direction.SELL,
                weight_pct=liquidation_pct,  # SIM4 fix: 1.0=전량, 0.5=50% 부분 청산
                confidence=0.99,
                reason=f"EMERGENCY EXIT: regime {previous_regime}→{new_regime}, liquidate {liquidation_pct:.0%}",
                order_type="market",
            ))

    if signals:
        print(f"[REGIME EXIT] {previous_regime}→{new_regime}: {len(signals)} emergency SELL signals")

    return signals
