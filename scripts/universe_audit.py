#!/usr/bin/env python3
"""Universe audit — weekly liveness check for tickers in state/universe.json.

Logic:
  1. For each ticker in each universe, query yfinance `.info` and `.history(period="5d")`.
  2. Classify:
       - LIVE     : info has `shortName` or `regularMarketPrice`, and recent history is non-empty.
       - STALE    : info returned but no recent price data.
       - DELISTED : `.info` empty, or `history` empty for 5 days.
  3. Track consecutive DELISTED/STALE counts in `state/universe_audit_state.json`.
  4. Auto-remove from universe.json ONLY when a ticker is DELISTED for 2+ consecutive audits
     (protects against one-off yfinance outages like MMC).
  5. Writes a summary to stdout + `state/universe_audit_last.json`.

Usage:
    python scripts/universe_audit.py                # Run audit, update universe.json
    python scripts/universe_audit.py --dry-run      # Run audit, do NOT modify universe.json

Exit code: 0 on success, 1 on any fatal error.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("[universe_audit] yfinance not installed — run `pip install yfinance`", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
UNIVERSE_PATH = STATE_DIR / "universe.json"
AUDIT_STATE_PATH = STATE_DIR / "universe_audit_state.json"
AUDIT_LAST_PATH = STATE_DIR / "universe_audit_last.json"

# Auto-remove a ticker after this many consecutive DELISTED audits.
REMOVE_AFTER_CONSECUTIVE = 2


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _classify(ticker: str) -> str:
    """Return 'LIVE' | 'STALE' | 'DELISTED' for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        has_info = bool(info.get("shortName") or info.get("regularMarketPrice"))
        hist = t.history(period="5d")
        has_hist = hist is not None and not hist.empty
    except Exception:
        return "DELISTED"

    if has_info and has_hist:
        return "LIVE"
    if has_info and not has_hist:
        return "STALE"
    return "DELISTED"


def _audit_list(tickers: list[str]) -> dict[str, str]:
    """Classify every ticker in a universe list."""
    results: dict[str, str] = {}
    for i, ticker in enumerate(tickers, 1):
        status = _classify(ticker)
        results[ticker] = status
        if status != "LIVE":
            print(f"  [{i}/{len(tickers)}] {ticker}: {status}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Universe liveness audit")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify universe.json")
    args = parser.parse_args()

    if not UNIVERSE_PATH.exists():
        print(f"[universe_audit] FATAL: {UNIVERSE_PATH} not found", file=sys.stderr)
        return 1

    universe = _load_json(UNIVERSE_PATH, {})
    prior_state = _load_json(AUDIT_STATE_PATH, {"consecutive_delisted": {}})
    consecutive = prior_state.get("consecutive_delisted", {})

    run_summary: dict[str, dict] = {}
    removals_by_key: dict[str, list[str]] = {}

    for key, tickers in universe.items():
        if key.startswith("_") or not isinstance(tickers, list):
            continue
        print(f"\n[universe_audit] {key} ({len(tickers)} tickers)")
        results = _audit_list(tickers)
        live = [t for t, s in results.items() if s == "LIVE"]
        stale = [t for t, s in results.items() if s == "STALE"]
        delisted = [t for t, s in results.items() if s == "DELISTED"]

        # Update consecutive counters
        to_remove: list[str] = []
        for ticker in tickers:
            status = results[ticker]
            counter_key = f"{key}:{ticker}"
            if status == "DELISTED":
                consecutive[counter_key] = int(consecutive.get(counter_key, 0)) + 1
                if consecutive[counter_key] >= REMOVE_AFTER_CONSECUTIVE:
                    to_remove.append(ticker)
            else:
                consecutive.pop(counter_key, None)

        run_summary[key] = {
            "total": len(tickers),
            "live": len(live),
            "stale": len(stale),
            "delisted": len(delisted),
            "delisted_tickers": delisted,
            "to_remove_tickers": to_remove,
        }
        removals_by_key[key] = to_remove
        print(
            f"  → LIVE {len(live)}, STALE {len(stale)}, DELISTED {len(delisted)}, "
            f"to_remove {len(to_remove)}"
        )

    total_removed = 0
    if not args.dry_run:
        for key, remove in removals_by_key.items():
            if not remove:
                continue
            before = universe[key]
            universe[key] = [t for t in before if t not in remove]
            total_removed += len(remove)
            print(f"[universe_audit] {key}: removed {remove} ({len(before)} → {len(universe[key])})")

        if total_removed:
            universe.setdefault("_meta", {})["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            UNIVERSE_PATH.write_text(
                json.dumps(universe, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"[universe_audit] universe.json 갱신: {total_removed} 종목 제거")
        else:
            print("[universe_audit] 변경사항 없음 — universe.json 유지")

    # Persist audit state (consecutive counters + last run)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_STATE_PATH.write_text(
        json.dumps(
            {
                "consecutive_delisted": consecutive,
                "last_audit_ts": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    AUDIT_LAST_PATH.write_text(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "dry_run": args.dry_run,
                "summary": run_summary,
                "removed": total_removed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
