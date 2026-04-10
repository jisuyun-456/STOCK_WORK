"""Research Cache — avoid re-analyzing the same stock within TTL window."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ResearchVerdict

CACHE_PATH = Path(__file__).parent.parent / "state" / "research_cache.json"
TTL_DAYS = 7


def _json_default(obj):
    """Coerce numpy types to native Python so json.dump succeeds.

    Python 3.14 의 json 모듈은 numpy.bool_ / int64 / float64 를 직접
    직렬화하지 못한다. ResearchVerdict.to_dict() 내부에 numpy 스칼라가
    섞여 들어올 수 있어 default 콜백으로 변환 처리.
    """
    # numpy 스칼라: .item() 으로 Python native 반환
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return obj.item()
        except Exception:
            pass
    # bool 서브클래스 (numpy.bool_ 포함) 안전 처리
    if isinstance(obj, bool):
        return bool(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


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
        json.dump(data, f, indent=2, ensure_ascii=False, default=_json_default)


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
