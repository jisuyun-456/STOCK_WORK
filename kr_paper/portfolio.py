"""KR Paper Portfolio — JSON state management with T+2 pending settlement.

State file: state/kr_portfolios.json
Writes are atomic: tmp file -> fsync -> os.replace.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

KR_PORTFOLIOS_PATH = "state/kr_portfolios.json"

DEFAULT_STATE: dict = {
    "KR_PAPER": {
        "cash_krw": 10_000_000,
        "positions": {},
        "nav_history": [],
        "pending_settlement": [],
    }
}


# ---------------------------------------------------------------------------
# Core I/O
# ---------------------------------------------------------------------------


def load() -> dict:
    """Load state/kr_portfolios.json. Create default if missing."""
    path = Path(KR_PORTFOLIOS_PATH)
    if not path.exists():
        state = _deep_copy_default()
        save(state)
        return state
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        state = _deep_copy_default()
        save(state)
        return state


def save(state: dict) -> None:
    """Atomic write: write to tmp file, fsync, then os.replace."""
    path = Path(KR_PORTFOLIOS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    dir_str = str(path.parent)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_str, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up tmp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


def get_cash() -> int:
    """Return current cash_krw."""
    return load()["KR_PAPER"]["cash_krw"]


def get_positions() -> dict:
    """Return current positions dict."""
    return load()["KR_PAPER"]["positions"]


# ---------------------------------------------------------------------------
# Pending settlement (T+2)
# ---------------------------------------------------------------------------


def add_pending_settlement(record: dict) -> None:
    """Append record to pending_settlement list and save."""
    state = load()
    state["KR_PAPER"]["pending_settlement"].append(record)
    save(state)


def settle_due(today: str) -> list[dict]:
    """Settle all pending records whose settlement_date <= today.

    BUY record: deduct net_cost_krw from cash.
    SELL record: add net_proceeds_krw to cash.

    Returns the settled records.
    """
    state = load()
    kr = state["KR_PAPER"]
    pending: list[dict] = kr["pending_settlement"]

    due: list[dict] = []
    remaining: list[dict] = []

    for record in pending:
        if record["settlement_date"] <= today:
            due.append(record)
        else:
            remaining.append(record)

    for record in due:
        side = record.get("side", "").upper()
        if side == "BUY":
            kr["cash_krw"] -= record["net_cost_krw"]
        elif side == "SELL":
            kr["cash_krw"] += record["net_proceeds_krw"]

    kr["pending_settlement"] = remaining
    save(state)
    return due


# ---------------------------------------------------------------------------
# NAV
# ---------------------------------------------------------------------------


def compute_nav(prices: dict[str, int]) -> int:
    """NAV = cash_krw + sum(qty * current_price) for each position.

    Falls back to avg_price_krw when ticker not in prices.
    """
    state = load()
    kr = state["KR_PAPER"]
    cash = kr["cash_krw"]
    positions: dict = kr["positions"]

    market_value = sum(
        pos["qty"] * prices.get(ticker, pos["avg_price_krw"])
        for ticker, pos in positions.items()
    )
    return cash + market_value


def append_nav_history(date: str, nav: int) -> None:
    """Append {"date": date, "nav": nav} to nav_history and save."""
    state = load()
    state["KR_PAPER"]["nav_history"].append({"date": date, "nav": nav})
    save(state)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _deep_copy_default() -> dict:
    """Return a fresh deep copy of DEFAULT_STATE."""
    return json.loads(json.dumps(DEFAULT_STATE))
