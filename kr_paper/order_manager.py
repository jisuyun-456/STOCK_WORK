"""KR Paper Order Manager — full paper order flow for Korean equities.

Flow per order:
  1. validate_kr_order (risk gate)
  2. simulate_buy / simulate_sell
  3. (if not dry_run) update portfolio state + positions
  4. Append to JSONL trade log
  5. Return status dict
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from kr_paper.risk_gate import validate_kr_order
from kr_paper.simulator import simulate_buy, simulate_sell
from kr_paper import portfolio as portfolio_module
from kr_paper.position_tracker import update_position_buy, update_position_sell

KR_TRADE_LOG_PATH = Path(__file__).parent.parent / "state" / "kr_trade_log.jsonl"

log = logging.getLogger("kr_paper.order_manager")


def _append_trade_log(entry: dict, log_path: Path = KR_TRADE_LOG_PATH) -> None:
    """Append a single JSON record (one line) to the JSONL trade log.

    Simple O(1) append — crash-safe at the entry level (worst case: lose the
    last line, which is acceptable for a trade log).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def place_kr_order(
    ticker: str,
    qty: int,
    price_krw: int,
    side: str,  # "BUY" or "SELL"
    trade_date: str,  # "YYYY-MM-DD"
    base_price: int,
    halted_tickers: set | None = None,
    vi_active_until: dict | None = None,
    cb_level: int = 0,
    dry_run: bool = True,
    _log_path: Path | None = None,  # override for testing
) -> dict:
    """Full KR paper order flow.

    1. validate_kr_order (risk gate) — if not passed, return rejected result.
    2. simulate_buy or simulate_sell to get the settlement record.
    3. If not dry_run: single load/save cycle that atomically appends the
       pending settlement AND updates the position (no TOCTOU window).
    4. Log to JSONL file (O(1) append, one JSON line per order).
    5. Return result dict with status: "submitted" | "rejected" | "dry_run".
    """
    log_path = _log_path if _log_path is not None else KR_TRADE_LOG_PATH

    # ------------------------------------------------------------------
    # Step 1: Risk gate
    # ------------------------------------------------------------------
    passed, risk_results = validate_kr_order(
        ticker=ticker,
        current_price=price_krw,
        base_price=base_price,
        halted_tickers=halted_tickers,
        vi_active_until=vi_active_until,
        cb_level=cb_level,
        side=side,
    )

    if not passed:
        # Find first failure reason
        first_failure = next(r for r in risk_results if not r.passed)
        result = {
            "status": "rejected",
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "price_krw": price_krw,
            "trade_date": trade_date,
            "reason": first_failure.reason,
            "risk_results": [
                {"check_name": r.check_name, "passed": r.passed, "reason": r.reason}
                for r in risk_results
            ],
        }
        log.warning("KR order REJECTED: %s %s x%d @ %d — %s", side, ticker, qty, price_krw, first_failure.reason)
        _append_trade_log(
            {
                "timestamp": datetime.now().isoformat(),
                "ticker": ticker,
                "side": side,
                "qty": qty,
                "price_krw": price_krw,
                "status": "rejected",
                "dry_run": dry_run,
                "reason": first_failure.reason,
            },
            log_path=log_path,
        )
        return result

    # ------------------------------------------------------------------
    # Step 2: Simulate (single load for SELL avg_entry in dry_run path)
    # ------------------------------------------------------------------
    side_upper = side.upper()

    if not dry_run:
        # Single load/save cycle — avoids TOCTOU between get_positions(),
        # add_pending_settlement(), and the subsequent position update.
        state = portfolio_module.load()
        kr = state["KR_PAPER"]
        positions = kr["positions"]

        if side_upper == "SELL":
            avg_entry = positions.get(ticker, {}).get("avg_price_krw", price_krw)
            record = simulate_sell(ticker, qty, price_krw, avg_entry, trade_date)
        else:
            record = simulate_buy(ticker, qty, price_krw, trade_date)

        # Atomically: append settlement + update position in one save
        kr["pending_settlement"].append(record)
        if side_upper == "BUY":
            update_position_buy(positions, ticker, qty, price_krw)
        else:
            try:
                update_position_sell(positions, ticker, qty)
            except ValueError as exc:
                log.error("Position update failed for SELL: %s", exc)
                return {
                    "status": "rejected",
                    "ticker": ticker,
                    "side": side,
                    "qty": qty,
                    "price_krw": price_krw,
                    "trade_date": trade_date,
                    "reason": str(exc),
                    "risk_results": [],
                }
        kr["positions"] = positions
        portfolio_module.save(state)  # single atomic write

        settlement_date = record["settlement_date"]
        status = "submitted"
        log.info("KR order SUBMITTED: %s %s x%d @ %d settle=%s", side, ticker, qty, price_krw, settlement_date)
    else:
        # dry_run: still need avg_entry for SELL — one read-only load
        if side_upper == "SELL":
            positions = portfolio_module.get_positions()
            avg_entry = positions.get(ticker, {}).get("avg_price_krw", price_krw)
            record = simulate_sell(ticker, qty, price_krw, avg_entry, trade_date)
        else:
            record = simulate_buy(ticker, qty, price_krw, trade_date)

        settlement_date = record["settlement_date"]
        status = "dry_run"
        log.info("KR order DRY_RUN: %s %s x%d @ %d", side, ticker, qty, price_krw)

    # ------------------------------------------------------------------
    # Step 4: Log to JSONL
    # ------------------------------------------------------------------
    log_record = {
        "timestamp": datetime.now().isoformat(),
        "ticker": ticker,
        "side": side_upper,
        "qty": qty,
        "price_krw": price_krw,
        "status": status,
        "dry_run": dry_run,
        "settlement_date": settlement_date,
    }
    _append_trade_log(log_record, log_path=log_path)

    # ------------------------------------------------------------------
    # Step 5: Return result
    # ------------------------------------------------------------------
    return {
        "status": status,
        "ticker": ticker,
        "side": side_upper,
        "qty": qty,
        "price_krw": price_krw,
        "trade_date": trade_date,
        "settlement_date": settlement_date,
        "record": record,
    }
