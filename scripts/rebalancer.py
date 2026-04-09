"""Rebalancer — 드리프트 감지 + 리밸런스 주문 생성.

스케줄:
  MOM  = monthly  (매월 1거래일)
  VAL  = quarterly (분기 1거래일)
  QNT  = monthly
  LEV  = daily    (매 거래일)

드리프트 임계값 초과 시 스케줄 무관 조기 리밸런스.
SELL 시그널이 항상 BUY보다 먼저 실행 (현금 확보).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from strategies.base_strategy import Signal, Direction

# ─── Constants ───────────────────────────────────────────────────────────

REBALANCE_SCHEDULES = {
    "MOM": "monthly",
    "VAL": "quarterly",
    "QNT": "monthly",
    "LEV": "daily",
}

DRIFT_THRESHOLD = {
    "MOM": 0.05,
    "VAL": 0.08,
    "QNT": 0.05,
    "LEV": 0.03,
}

ROOT = Path(__file__).parent.parent
STATE_DIR = ROOT / "state"


# ─── Schedule Checking ───────────────────────────────────────────────────

def _is_schedule_due(schedule: str, last_rebalance: str | None) -> tuple[bool, str]:
    """Check if rebalance schedule has triggered.

    Returns:
        (due: bool, reason: str)
    """
    today = datetime.now(timezone.utc).date()

    if last_rebalance is None:
        return True, "initial rebalance (never rebalanced)"

    try:
        last_date = datetime.fromisoformat(last_rebalance).date() if "T" in last_rebalance else datetime.strptime(last_rebalance, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return True, f"invalid last_rebalance: {last_rebalance}"

    if schedule == "daily":
        if today > last_date:
            return True, "daily schedule"
        return False, "already rebalanced today"

    elif schedule == "monthly":
        if today.year > last_date.year or today.month > last_date.month:
            return True, f"monthly schedule (last: {last_date})"
        return False, f"already rebalanced this month ({last_date})"

    elif schedule == "quarterly":
        last_quarter = (last_date.month - 1) // 3
        current_quarter = (today.month - 1) // 3
        if today.year > last_date.year or current_quarter > last_quarter:
            return True, f"quarterly schedule (last: {last_date})"
        return False, f"already rebalanced this quarter ({last_date})"

    return False, f"unknown schedule: {schedule}"


def _check_drift(
    positions: dict,
    strategy_nav: float,
    threshold: float,
) -> tuple[bool, str]:
    """Check if any position has drifted beyond threshold.

    Args:
        positions: {symbol: {qty, current, cost_basis}}
        strategy_nav: current total NAV for this strategy
        threshold: max allowed drift (e.g. 0.05 = 5%)

    Returns:
        (drifted: bool, detail: str)
    """
    if not positions or strategy_nav <= 0:
        return False, "no positions"

    n = len(positions)
    if n == 0:
        return False, "no positions"

    target_weight = 1.0 / n
    max_drift = 0.0
    drifted_sym = ""

    for sym, pos in positions.items():
        value = pos.get("qty", 0) * pos.get("current", 0)
        actual_weight = value / strategy_nav if strategy_nav > 0 else 0
        drift = abs(actual_weight - target_weight)
        if drift > max_drift:
            max_drift = drift
            drifted_sym = sym

    if max_drift > threshold:
        return True, f"drift triggered ({drifted_sym}: {max_drift:.1%} > {threshold:.0%})"

    return False, f"no drift (max {max_drift:.1%} < {threshold:.0%})"


# ─── Rebalance Order Generation ─────────────────────────────────────────

def should_rebalance(
    strategy_code: str,
    last_rebalance: str | None,
    positions: dict,
    strategy_nav: float,
) -> tuple[bool, str]:
    """Determine if a strategy should be rebalanced.

    Returns:
        (should: bool, reason: str)
    """
    schedule = REBALANCE_SCHEDULES.get(strategy_code, "monthly")
    threshold = DRIFT_THRESHOLD.get(strategy_code, 0.05)

    # Check schedule
    schedule_due, schedule_reason = _is_schedule_due(schedule, last_rebalance)
    if schedule_due:
        return True, schedule_reason

    # Check drift
    drift_due, drift_reason = _check_drift(positions, strategy_nav, threshold)
    if drift_due:
        return True, drift_reason

    return False, f"not due ({schedule_reason}; {drift_reason})"


def compute_rebalance_orders(
    strategy_code: str,
    current_positions: dict,
    target_signals: list[Signal],
    strategy_nav: float,
    strategy_cash: float,
) -> tuple[list[Signal], list[Signal]]:
    """Compute SELL and BUY signals for rebalancing.

    Args:
        current_positions: {symbol: {qty, current, cost_basis}}
        target_signals: signals from strategy's generate_signals()
        strategy_nav: total NAV
        strategy_cash: available cash

    Returns:
        (sells, buys) — sells first for cash release
    """
    target_symbols = {s.symbol: s for s in target_signals}
    sells = []
    buys = []

    # SELL: positions not in target
    for sym, pos in current_positions.items():
        if sym not in target_symbols:
            value = pos.get("qty", 0) * pos.get("current", 0)
            weight = value / strategy_nav if strategy_nav > 0 else 0
            sells.append(Signal(
                strategy=strategy_code,
                symbol=sym,
                direction=Direction.SELL,
                weight_pct=weight,
                confidence=0.9,
                reason=f"rebalance: exit position (not in target)",
                order_type="market",
            ))

    # BUY: targets not in current, or targets needing size increase
    for sym, target_signal in target_symbols.items():
        if sym not in current_positions:
            buys.append(Signal(
                strategy=strategy_code,
                symbol=sym,
                direction=Direction.BUY,
                weight_pct=target_signal.weight_pct,
                confidence=target_signal.confidence,
                reason=f"rebalance: new position ({target_signal.reason})",
                order_type="market",
            ))

    return sells, buys


def apply_rebalance_risk_gate(
    sells: list[Signal],
    buys: list[Signal],
    strategy_nav: float,
) -> tuple[list[Signal], list[Signal], list[str]]:
    """Pre-rebalance risk gate.

    Blocks:
      - Total turnover > 80% of NAV
      - Resulting portfolio < 5 positions (for MOM/QNT/VAL)
      - Strategy NAV < $1,000

    Returns:
        (approved_sells, approved_buys, block_reasons)
    """
    block_reasons = []

    if strategy_nav < 1000:
        block_reasons.append(f"NAV too low (${strategy_nav:,.0f} < $1,000)")
        return [], [], block_reasons

    total_turnover = sum(s.weight_pct for s in sells) + sum(s.weight_pct for s in buys)
    if total_turnover > 0.80:
        block_reasons.append(f"turnover too high ({total_turnover:.0%} > 80%)")
        return [], [], block_reasons

    return sells, buys, block_reasons


# ─── Main Entry ──────────────────────────────────────────────────────────

def run_rebalance_check(
    portfolios: dict,
    market_data: dict,
    dry_run: bool = False,
) -> dict:
    """Check all strategies and generate rebalance signals if due.

    Returns:
        {rebalanced: [str], skipped: [str], signals: [Signal], summary: str}
    """
    print("[Phase 5.5: REBALANCE] Checking rebalance schedules...")

    rebalanced = []
    skipped = []
    all_signals = []
    summaries = []

    strategies_config = {
        "MOM": "strategies.momentum.MomentumStrategy",
        "VAL": "strategies.value_quality.ValueQualityStrategy",
        "QNT": "strategies.quant_factor.QuantFactorStrategy",
        "LEV": "strategies.leveraged_etf.LeveragedETFStrategy",
    }

    for code, strat_data in portfolios.get("strategies", {}).items():
        positions = strat_data.get("positions", {})
        cash = strat_data.get("cash", 0)
        nav = cash
        for sym, pos in positions.items():
            nav += pos.get("qty", 0) * pos.get("current", 0)

        last_reb = strat_data.get("last_rebalance")
        due, reason = should_rebalance(code, last_reb, positions, nav)

        if not due:
            skipped.append(code)
            print(f"  {code}: SKIP — {reason}")
            continue

        # Only rebalance if we have positions to rebalance
        if not positions:
            skipped.append(code)
            print(f"  {code}: SKIP — no positions to rebalance")
            continue

        print(f"  {code}: REBALANCE — {reason}")

        # Get fresh target signals from strategy
        try:
            target_signals = _get_strategy_signals(code, market_data)
        except Exception as e:
            print(f"  {code}: ERROR getting target signals: {e}")
            skipped.append(code)
            continue

        sells, buys = compute_rebalance_orders(code, positions, target_signals, nav, cash)
        sells, buys, blocks = apply_rebalance_risk_gate(sells, buys, nav)

        if blocks:
            print(f"  {code}: BLOCKED — {'; '.join(blocks)}")
            skipped.append(code)
            continue

        if sells or buys:
            all_signals.extend(sells)
            all_signals.extend(buys)
            rebalanced.append(code)
            summaries.append(f"{code}: {len(sells)} sells, {len(buys)} buys ({reason})")
        else:
            skipped.append(code)
            print(f"  {code}: no changes needed")

    summary = "; ".join(summaries) if summaries else "no rebalances triggered"
    print(f"  Summary: {summary}")

    return {
        "rebalanced": rebalanced,
        "skipped": skipped,
        "signals": all_signals,
        "summary": summary,
    }


def _get_strategy_signals(code: str, market_data: dict) -> list[Signal]:
    """Instantiate strategy and get fresh signals."""
    if code == "MOM":
        from strategies.momentum import MomentumStrategy
        strat = MomentumStrategy()
    elif code == "VAL":
        from strategies.value_quality import ValueQualityStrategy
        strat = ValueQualityStrategy()
    elif code == "QNT":
        from strategies.quant_factor import QuantFactorStrategy
        strat = QuantFactorStrategy()
    elif code == "LEV":
        from strategies.leveraged_etf import LeveragedETFStrategy
        strat = LeveragedETFStrategy()
    else:
        return []

    return strat.generate_signals(market_data)


# ─── Standalone Test ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Rebalancer Test ===")

    portfolios_path = STATE_DIR / "portfolios.json"
    if not portfolios_path.exists():
        print("portfolios.json not found")
        exit(1)

    with open(portfolios_path) as f:
        portfolios = json.load(f)

    for code, strat in portfolios.get("strategies", {}).items():
        last_reb = strat.get("last_rebalance")
        positions = strat.get("positions", {})
        nav = strat.get("cash", 0)
        for sym, pos in positions.items():
            nav += pos.get("qty", 0) * pos.get("current", 0)

        due, reason = should_rebalance(code, last_reb, positions, nav)
        print(f"  {code}: {'DUE' if due else 'SKIP'} — {reason}")
