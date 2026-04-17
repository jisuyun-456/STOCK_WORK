"""KR Manual Research Override — stores 5-agent consensus verdicts with 24h TTL.

Mirrors research/manual_override.py pattern but targets state/kr_verdicts.json
and uses a flat schema suited for KR 5-agent consensus (no strategy dimension).

File: state/kr_verdicts.json
TTL:  24 hours (configurable)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KR_OVERRIDE_PATH = Path(__file__).parent.parent / "state" / "kr_verdicts.json"
DEFAULT_TTL_HOURS = 24


def _json_default(obj):
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, bool):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _load() -> dict:
    if not KR_OVERRIDE_PATH.exists():
        return {}
    try:
        with open(KR_OVERRIDE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    KR_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(KR_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)


def save_kr_verdicts(
    ticker: str,
    verdicts: list[dict],
    consensus: str,
    final_confidence: float,
    veto_reason: str | None = None,
    regime: str = "UNKNOWN",
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> None:
    """Persist 5-agent KR verdicts with TTL. Overwrites existing entry for same ticker."""
    data = _load()
    now = datetime.now(timezone.utc)
    key = ticker.upper()
    data[key] = {
        "saved_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "ticker": key,
        "regime": regime,
        "verdicts": verdicts,
        "consensus": consensus,
        "final_confidence": round(float(final_confidence), 3),
        "veto_reason": veto_reason,
        "source": "kr_5agent_claude_code",
    }
    _save(data)


def load_kr_verdicts(ticker: str) -> dict | None:
    """Return KR verdict entry if present and not expired; else None."""
    data = _load()
    entry = data.get(ticker.upper())
    if entry is None:
        return None
    try:
        expires = datetime.fromisoformat(entry["expires_at"])
    except (KeyError, ValueError):
        return None
    if datetime.now(timezone.utc) > expires:
        return None
    return entry


def list_active() -> list[dict]:
    """Return metadata for all non-expired KR verdicts."""
    data = _load()
    now = datetime.now(timezone.utc)
    active = []
    for key, entry in data.items():
        try:
            expires = datetime.fromisoformat(entry["expires_at"])
        except (KeyError, ValueError):
            continue
        if now > expires:
            continue
        active.append({
            "ticker": entry.get("ticker", key),
            "consensus": entry.get("consensus", ""),
            "final_confidence": entry.get("final_confidence", 0.0),
            "regime": entry.get("regime", ""),
            "saved_at": entry.get("saved_at", ""),
            "expires_at": entry.get("expires_at", ""),
            "verdict_count": len(entry.get("verdicts", [])),
        })
    return active


def clear_expired() -> int:
    """Remove expired entries. Returns count removed."""
    data = _load()
    now = datetime.now(timezone.utc)
    removed = 0
    for key in list(data.keys()):
        try:
            expires = datetime.fromisoformat(data[key]["expires_at"])
            if now > expires:
                del data[key]
                removed += 1
        except (KeyError, ValueError):
            del data[key]
            removed += 1
    if removed:
        _save(data)
    return removed


def invalidate(ticker: str) -> bool:
    """Explicitly drop a ticker entry. Returns True if removed."""
    data = _load()
    key = ticker.upper()
    if key in data:
        del data[key]
        _save(data)
        return True
    return False
