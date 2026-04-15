# execution/circuit_breaker.py
"""4-Stage graduated circuit breaker for portfolio protection.

Stages:
  NORMAL    (0): All metrics within limits — no action.
  WARNING   (1): daily_loss >= -2% — log alert, no action.
  CAUTION   (2): daily_loss >= -3% — halve new BUY signal weights.
  HALT      (3): weekly_loss >= -5% — block all BUY signals.
  EMERGENCY (4): portfolio_mdd >= -10% — liquidate all, write lock file.
"""
from __future__ import annotations

import copy
import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "state" / "circuit_breaker.lock"

# ── Stage thresholds (negative = loss fraction) ───────────────────────────
DAILY_WARNING  = -0.02   # Stage 1
DAILY_CAUTION  = -0.03   # Stage 2
WEEKLY_HALT    = -0.05   # Stage 3
MDD_EMERGENCY  = -0.10   # Stage 4


class Stage(IntEnum):
    NORMAL    = 0
    WARNING   = 1
    CAUTION   = 2
    HALT      = 3
    EMERGENCY = 4


@dataclass
class CircuitBreakerState:
    stage: Stage
    triggered_at: str
    trigger_value: float
    trigger_metric: str   # "daily_loss" | "weekly_loss" | "portfolio_mdd" | "none"
    reason: str
    resolved: bool = False
    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    portfolio_mdd: float = 0.0


# ── Internal metric helpers ───────────────────────────────────────────────

def _get_nav_history(portfolios: dict) -> list[float]:
    """Extract aggregated NAV history from portfolios dict.

    Prefers account_total_history (Alpaca account balance) to avoid
    false MDD from strategy reallocation artifacts (e.g. CRISIS reducing
    allocated capital makes strategy-NAV-sum drop without real losses).

    Falls back to strategy-NAV sum if account_total_history is absent.
    """
    # Prefer Alpaca-account-level history (accurate, no realloc artifacts)
    acct_hist = portfolios.get("account_total_history", [])
    if acct_hist:
        return [float(e["nav"]) for e in sorted(acct_hist, key=lambda x: x["date"])]

    # Legacy fallback: sum strategy nav_history entries by date
    strategies = portfolios.get("strategies", {})
    date_navs: dict[str, float] = {}

    for strat_data in strategies.values():
        for entry in strat_data.get("nav_history", []):
            d = entry.get("date", "")
            n = float(entry.get("nav", 0.0))
            if d:
                date_navs[d] = date_navs.get(d, 0.0) + n

    if not date_navs:
        total = float(portfolios.get("account_total", 0.0))
        return [total] if total else []

    return [v for _, v in sorted(date_navs.items())]


def _compute_daily_loss(nav_history: list[float]) -> float:
    """Last-day return as fraction. Returns 0.0 if < 2 data points."""
    if len(nav_history) < 2 or nav_history[-2] == 0:
        return 0.0
    return (nav_history[-1] - nav_history[-2]) / abs(nav_history[-2])


def _compute_weekly_loss(nav_history: list[float]) -> float:
    """5-day rolling return. Returns 0.0 if < 6 data points."""
    if len(nav_history) < 6 or nav_history[-6] == 0:
        return 0.0
    return (nav_history[-1] - nav_history[-6]) / abs(nav_history[-6])


def _compute_portfolio_mdd(nav_history: list[float]) -> float:
    """Max drawdown from peak (negative float or 0.0)."""
    if not nav_history:
        return 0.0
    peak = nav_history[0]
    max_dd = 0.0
    for nav in nav_history:
        if nav > peak:
            peak = nav
        if peak > 0:
            dd = (nav - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd


# ── Lock file I/O ─────────────────────────────────────────────────────────

def load_lock() -> Optional[CircuitBreakerState]:
    """Load existing lock file. Returns None if absent or unreadable."""
    if not LOCK_PATH.exists():
        return None
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        return CircuitBreakerState(
            stage=Stage(data["stage"]),
            triggered_at=data["triggered_at"],
            trigger_value=data["trigger_value"],
            trigger_metric=data["trigger_metric"],
            reason=data["reason"],
            resolved=data.get("resolved", False),
        )
    except Exception:
        return None


def write_lock(state: CircuitBreakerState) -> None:
    """Atomic write of lock file (tmp → rename)."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "stage": int(state.stage),
        "triggered_at": state.triggered_at,
        "trigger_value": round(state.trigger_value, 6),
        "trigger_metric": state.trigger_metric,
        "reason": state.reason,
        "resolved": state.resolved,
    }
    tmp = LOCK_PATH.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LOCK_PATH)


def clear_lock() -> bool:
    """Delete lock file if it exists. Returns True if deleted."""
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()
        return True
    return False


# ── Main API ──────────────────────────────────────────────────────────────

def check_circuit_breaker(portfolios: dict) -> CircuitBreakerState:
    """Evaluate 4 stages. EMERGENCY is checked first and is sticky via lock file.

    Stage priority (highest wins):
      4 EMERGENCY → portfolio_mdd >= 10%  (writes lock, sticky until resolved)
      3 HALT      → weekly_loss >= 5%
      2 CAUTION   → daily_loss >= 3%
      1 WARNING   → daily_loss >= 2%
      0 NORMAL    → all within limits
    """
    now_str = datetime.now(timezone.utc).isoformat()

    # Sticky lock check — if unresolved EMERGENCY exists, return it
    existing = load_lock()
    if existing is not None and existing.stage == Stage.EMERGENCY and not existing.resolved:
        return existing

    nav_history = _get_nav_history(portfolios)
    daily_loss = _compute_daily_loss(nav_history)
    weekly_loss = _compute_weekly_loss(nav_history)
    portfolio_mdd = _compute_portfolio_mdd(nav_history)

    # Stage 4 EMERGENCY (highest priority — check first)
    if portfolio_mdd <= MDD_EMERGENCY:
        state = CircuitBreakerState(
            stage=Stage.EMERGENCY,
            triggered_at=now_str,
            trigger_value=portfolio_mdd,
            trigger_metric="portfolio_mdd",
            reason=f"portfolio_mdd={portfolio_mdd*100:.1f}% <= {MDD_EMERGENCY*100:.0f}%",
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            portfolio_mdd=portfolio_mdd,
        )
        write_lock(state)
        return state

    # Stage 3 HALT
    if weekly_loss <= WEEKLY_HALT:
        return CircuitBreakerState(
            stage=Stage.HALT,
            triggered_at=now_str,
            trigger_value=weekly_loss,
            trigger_metric="weekly_loss",
            reason=f"weekly_loss={weekly_loss*100:.1f}% <= {WEEKLY_HALT*100:.0f}%",
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            portfolio_mdd=portfolio_mdd,
        )

    # Stage 2 CAUTION
    if daily_loss <= DAILY_CAUTION:
        return CircuitBreakerState(
            stage=Stage.CAUTION,
            triggered_at=now_str,
            trigger_value=daily_loss,
            trigger_metric="daily_loss",
            reason=f"daily_loss={daily_loss*100:.1f}% <= {DAILY_CAUTION*100:.0f}%",
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            portfolio_mdd=portfolio_mdd,
        )

    # Stage 1 WARNING
    if daily_loss <= DAILY_WARNING:
        return CircuitBreakerState(
            stage=Stage.WARNING,
            triggered_at=now_str,
            trigger_value=daily_loss,
            trigger_metric="daily_loss",
            reason=f"daily_loss={daily_loss*100:.1f}% <= {DAILY_WARNING*100:.0f}%",
            daily_loss=daily_loss,
            weekly_loss=weekly_loss,
            portfolio_mdd=portfolio_mdd,
        )

    # Stage 0 NORMAL
    return CircuitBreakerState(
        stage=Stage.NORMAL,
        triggered_at=now_str,
        trigger_value=0.0,
        trigger_metric="none",
        reason="All metrics within limits",
        daily_loss=daily_loss,
        weekly_loss=weekly_loss,
        portfolio_mdd=portfolio_mdd,
    )


# ── Signal filtering ──────────────────────────────────────────────────────

def filter_signals_by_stage(signals: list, stage: Stage) -> tuple[list, list]:
    """Apply circuit breaker stage to signal list.

    NORMAL/WARNING: pass all through unchanged.
    CAUTION:        halve BUY weight_pct; SELLs unchanged.
    HALT:           drop all BUY signals; keep SELLs.
    EMERGENCY:      drop all signals (no new entries or exits via CB).

    Returns (kept, filtered_out).
    """
    from strategies.base_strategy import Direction

    if stage in (Stage.NORMAL, Stage.WARNING):
        return list(signals), []

    if stage == Stage.EMERGENCY:
        return [], list(signals)

    kept, filtered_out = [], []
    for sig in signals:
        if sig.direction == Direction.BUY:
            if stage == Stage.HALT:
                filtered_out.append(sig)
            elif stage == Stage.CAUTION:
                modified = copy.copy(sig)
                modified.weight_pct = sig.weight_pct * 0.5
                kept.append(modified)
        else:
            kept.append(sig)

    return kept, filtered_out
