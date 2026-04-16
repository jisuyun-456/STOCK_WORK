"""Manual Research Override — user-initiated Claude Code agent analysis.

Stored separately from auto cache (state/research_cache.json) so that a
user's deliberate `/analyze` invocation always beats rules/cache in
Phase 2.5. Key format mirrors research.cache to allow drop-in lookup.

File: state/manual_verdicts.json
Key:  "{SYMBOL}:{STRATEGY}:{direction}"   (direction lowercase, e.g. "buy")
TTL:  24 hours (configurable)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ResearchVerdict

OVERRIDE_PATH = Path(__file__).parent.parent / "state" / "manual_verdicts.json"
DEFAULT_TTL_HOURS = 24


def _json_default(obj):
    """Numpy-safe JSON default (mirrors research.cache._json_default)."""
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, bool):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _load() -> dict:
    if not OVERRIDE_PATH.exists():
        return {}
    try:
        with open(OVERRIDE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)


def _make_key(symbol: str, strategy: str, direction: str) -> str:
    return f"{symbol.upper()}:{strategy.upper()}:{direction.lower()}"


def save_manual_verdicts(
    symbol: str,
    strategy: str,
    direction: str,
    verdicts: list[ResearchVerdict],
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> None:
    """Persist manual verdicts with TTL. Overwrites existing entry for the same key."""
    data = _load()
    now = datetime.now(timezone.utc)
    key = _make_key(symbol, strategy, direction)
    data[key] = {
        "saved_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=ttl_hours)).isoformat(),
        "symbol": symbol.upper(),
        "strategy": strategy.upper(),
        "direction": direction.lower(),
        "verdicts": [v.to_dict() for v in verdicts],
        "source": "manual_claude_code_agents",
    }
    _save(data)


def load_manual_verdicts(
    symbol: str,
    strategy: str,
    direction: str,
) -> list[ResearchVerdict] | None:
    """Return manual verdicts if present and not expired; else None."""
    data = _load()
    key = _make_key(symbol, strategy, direction)
    entry = data.get(key)
    if entry is None:
        return None

    try:
        expires = datetime.fromisoformat(entry["expires_at"])
    except (KeyError, ValueError):
        return None
    if datetime.now(timezone.utc) > expires:
        return None

    try:
        return [ResearchVerdict.from_dict(v) for v in entry["verdicts"]]
    except Exception:
        return None


def list_active() -> list[dict]:
    """Return metadata for all non-expired manual verdicts."""
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
            "key": key,
            "symbol": entry.get("symbol", ""),
            "strategy": entry.get("strategy", ""),
            "direction": entry.get("direction", ""),
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


def invalidate(symbol: str, strategy: str, direction: str) -> bool:
    """Explicitly drop an entry. Returns True if removed, False if not found."""
    data = _load()
    key = _make_key(symbol, strategy, direction)
    if key in data:
        del data[key]
        _save(data)
        return True
    return False
