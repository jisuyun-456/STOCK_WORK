"""Intraday Monitor Rules Engine — stop-loss, take-profit, trailing stop.

Each check function returns (should_exit: bool, reason: str).
The evaluate_position() function runs all checks in priority order.
"""

from __future__ import annotations

# Strategy-specific thresholds
# Keys: stop_loss (negative), take_profit (positive), trailing_stop (negative from peak), trailing_arm (activate trailing after this gain)
STOP_CONFIG = {
    "MOM": {"stop_loss": -0.10, "take_profit": 0.30, "trailing_stop": -0.15, "trailing_arm": 0.20},
    "VAL": {"stop_loss": -0.10, "take_profit": 0.20, "trailing_stop": -0.12, "trailing_arm": 0.15},
    "QNT": {"stop_loss": -0.10, "take_profit": 0.20, "trailing_stop": -0.12, "trailing_arm": 0.15},
    "LEV": {"stop_loss": -0.08, "take_profit": 0.15, "trailing_stop": -0.10, "trailing_arm": 0.10},
}

# Fallback for unknown strategies (most conservative = LEV)
DEFAULT_CONFIG = STOP_CONFIG["LEV"]

# MDD thresholds
STRATEGY_MDD_THRESHOLD = -0.20  # -20% per strategy
PORTFOLIO_MDD_THRESHOLD = -0.15  # -15% total portfolio


def get_config(strategy: str) -> dict:
    return STOP_CONFIG.get(strategy, DEFAULT_CONFIG)


def check_stop_loss(unrealized_plpc: float, strategy: str) -> tuple[bool, str]:
    """Hard stop-loss: exit if unrealized P&L % breaches threshold."""
    cfg = get_config(strategy)
    threshold = cfg["stop_loss"]
    if unrealized_plpc <= threshold:
        return True, f"stop_loss: {unrealized_plpc:.1%} <= {threshold:.0%}"
    return False, ""


def check_take_profit(unrealized_plpc: float, strategy: str) -> tuple[bool, str]:
    """Take-profit: exit if unrealized gain exceeds threshold."""
    cfg = get_config(strategy)
    threshold = cfg["take_profit"]
    if unrealized_plpc >= threshold:
        return True, f"take_profit: {unrealized_plpc:.1%} >= {threshold:.0%}"
    return False, ""


def check_trailing_stop(
    unrealized_plpc: float,
    peak_plpc: float,
    strategy: str,
) -> tuple[bool, str]:
    """Trailing stop: exit if price has dropped from peak by trailing threshold.

    Only active when peak_plpc >= trailing_arm (i.e., position was in profit zone).
    """
    cfg = get_config(strategy)
    trailing_arm = cfg["trailing_arm"]
    trailing_stop = cfg["trailing_stop"]

    # Not armed yet — peak never reached the activation level
    if peak_plpc < trailing_arm:
        return False, ""

    drawdown_from_peak = unrealized_plpc - peak_plpc
    if drawdown_from_peak <= trailing_stop:
        return True, (
            f"trailing_stop: peak={peak_plpc:.1%}, "
            f"current={unrealized_plpc:.1%}, "
            f"drawdown={drawdown_from_peak:.1%} <= {trailing_stop:.0%}"
        )
    return False, ""


def check_strategy_mdd(nav_history: list[dict], threshold: float = STRATEGY_MDD_THRESHOLD) -> tuple[bool, str]:
    """Check if a strategy's NAV has hit MDD threshold from its peak."""
    if len(nav_history) < 2:
        return False, ""

    navs = [h["nav"] for h in nav_history]
    peak = max(navs)
    if peak <= 0:
        return False, ""

    current = navs[-1]
    mdd = (current - peak) / peak

    if mdd <= threshold:
        return True, f"strategy_mdd: {mdd:.1%} <= {threshold:.0%} (peak=${peak:,.0f}, now=${current:,.0f})"
    return False, ""


def check_portfolio_mdd(strategies: dict, threshold: float = PORTFOLIO_MDD_THRESHOLD) -> tuple[bool, str]:
    """Check if total portfolio NAV has hit MDD threshold."""
    total_peak = 0
    total_current = 0

    for code, strat in strategies.items():
        nav_history = strat.get("nav_history", [])
        if not nav_history:
            continue
        navs = [h["nav"] for h in nav_history]
        total_peak += max(navs)
        total_current += navs[-1]

    if total_peak <= 0:
        return False, ""

    mdd = (total_current - total_peak) / total_peak
    if mdd <= threshold:
        return True, f"portfolio_mdd: {mdd:.1%} <= {threshold:.0%} (peak=${total_peak:,.0f}, now=${total_current:,.0f})"
    return False, ""


def evaluate_position(
    unrealized_plpc: float,
    peak_plpc: float,
    strategy: str,
) -> tuple[bool, str]:
    """Run all position-level checks in priority order.

    Returns (should_exit, reason) — first trigger wins.
    """
    # Priority 1: Hard stop-loss
    triggered, reason = check_stop_loss(unrealized_plpc, strategy)
    if triggered:
        return True, reason

    # Priority 2: Trailing stop (only if armed)
    triggered, reason = check_trailing_stop(unrealized_plpc, peak_plpc, strategy)
    if triggered:
        return True, reason

    # Priority 3: Take-profit
    triggered, reason = check_take_profit(unrealized_plpc, strategy)
    if triggered:
        return True, reason

    return False, ""
