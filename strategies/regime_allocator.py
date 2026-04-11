"""Regime-based dynamic strategy allocation (Bridgewater-style)."""

from __future__ import annotations

# LEV 50% 고정 + 나머지 50%는 기존 비율(BULL/NEUTRAL/BEAR/CRISIS)을 비례 재정규화.
# LEV 전략은 내부에서 regime 에 따라 SPY+TQQQ↔SPY+SQQQ↔현금 을 자체 관리하므로,
# allocator 는 모든 regime 에서 LEV 슬롯 50% 를 유지해 generate_signals() 가 호출되도록 보장한다.
# (CRISIS 에서도 LEV=0.5 인 이유: LeveragedETFStrategy 가 target_mix={} → 전량 SELL 신호를
#  생성해 포지션을 자연스럽게 청산하려면 allocator 가 LEV 를 SKIP 시키지 말아야 함)
REGIME_ALLOCATIONS: dict[str, dict[str, float]] = {
    # 기존 BULL    MOM 30, VAL 20, QNT 25, LEV 25, CASH 0  → 비-LEV 합 75
    #   × 50/75 → MOM 20.00, VAL 13.33, QNT 16.67, CASH 0.00
    "BULL":    {"MOM": 0.2000, "VAL": 0.1333, "QNT": 0.1667, "LEV": 0.50, "CASH": 0.00},

    # 기존 NEUTRAL MOM 25, VAL 25, QNT 30, LEV 20, CASH 0  → 비-LEV 합 80
    #   × 50/80 → MOM 15.625, VAL 15.625, QNT 18.75, CASH 0.00
    "NEUTRAL": {"MOM": 0.15625, "VAL": 0.15625, "QNT": 0.1875, "LEV": 0.50, "CASH": 0.00},

    # 기존 BEAR    MOM 15, VAL 35, QNT 30, LEV 0, CASH 20  → 비-LEV 합 100
    #   × 50/100 → MOM 7.5, VAL 17.5, QNT 15.0, CASH 10.0
    "BEAR":    {"MOM": 0.075, "VAL": 0.175, "QNT": 0.15, "LEV": 0.50, "CASH": 0.10},

    # 기존 CRISIS  MOM 10, VAL 30, QNT 20, LEV 0, CASH 40  → 비-LEV 합 100
    #   × 50/100 → MOM 5.0, VAL 15.0, QNT 10.0, CASH 20.0
    #   (LEV 50% 는 내부 target_mix={} 로 즉시 청산 → 실효 현금 50+20=70%)
    "CRISIS":  {"MOM": 0.05, "VAL": 0.15, "QNT": 0.10, "LEV": 0.50, "CASH": 0.20},
}

_REGIME_DESCRIPTIONS: dict[str, str] = {
    "BULL": (
        "강세장: 레버리지(LEV) 50% Core-Satellite + 모멘텀(MOM) 20% + 퀀트(QNT) 16.67% + 가치(VAL) 13.33%. "
        "위험자산 비중 최대, 현금 0%."
    ),
    "NEUTRAL": (
        "중립장: 레버리지(LEV) 50% Core-Satellite + 퀀트(QNT) 18.75% + 모멘텀(MOM)/가치(VAL) 각 15.625%. "
        "균형 배분, 방향성 중립 포지션."
    ),
    "BEAR": (
        "약세장: 레버리지(LEV) 50% (내부 SPY 50% + SQQQ 50%) + 가치(VAL) 17.5% + 퀀트(QNT) 15% + 현금 10% + 모멘텀(MOM) 7.5%. "
        "LEV 는 SQQQ 전환으로 하락 베팅, 나머지는 방어적 배분."
    ),
    "CRISIS": (
        "위기장: LEV 50%(내부 전량 현금화) + 현금(CASH) 20% + 가치(VAL) 15% + 퀀트(QNT) 10% + 모멘텀(MOM) 5%. "
        "LEV 는 즉시 청산 트리거, 실효 현금 70%, 자본 보존 최우선."
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
