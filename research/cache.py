"""Research Cache — avoid re-analyzing the same stock within TTL window."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ResearchVerdict

CACHE_PATH = Path(__file__).parent.parent / "state" / "research_cache.json"
TTL_DAYS = 7


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(data: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_cached(symbol: str, regime: str, strategy: str = "", direction: str = "") -> list[ResearchVerdict] | None:
    """Return cached verdicts if valid, else None."""
    cache = _load_cache()
    cache_key = f"{symbol}:{strategy}:{direction}" if strategy else symbol
    entry = cache.get(cache_key)
    if entry is None:
        return None

    # Check regime match
    if entry.get("regime_at_cache") != regime:
        return None

    # Check TTL
    try:
        expires = datetime.fromisoformat(entry["expires_at"])
        if datetime.now(timezone.utc) > expires:
            return None
    except (KeyError, ValueError):
        return None

    # Reconstruct verdicts
    try:
        return [ResearchVerdict.from_dict(v) for v in entry["verdicts"]]
    except Exception:
        return None


def set_cache(symbol: str, regime: str, verdicts: list[ResearchVerdict], strategy: str = "", direction: str = ""):
    """Store verdicts in cache."""
    cache = _load_cache()
    now = datetime.now(timezone.utc)
    cache_key = f"{symbol}:{strategy}:{direction}" if strategy else symbol
    cache[cache_key] = {
        "cached_at": now.isoformat(),
        "expires_at": (now + timedelta(days=TTL_DAYS)).isoformat(),
        "regime_at_cache": regime,
        "verdicts": [v.to_dict() for v in verdicts],
    }
    _save_cache(cache)


def invalidate_all():
    """Clear entire cache (e.g., on regime change)."""
    _save_cache({})


def invalidate_symbol(symbol: str):
    """Remove a single symbol from cache."""
    cache = _load_cache()
    cache.pop(symbol, None)
    _save_cache(cache)
