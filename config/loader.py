"""strategy_params.json 로더 — 모듈 레벨 캐시로 중복 IO 방지."""
from __future__ import annotations
import json
from pathlib import Path

_CONFIG_PATH = Path(__file__).parent / "strategy_params.json"
_cache: dict | None = None


def load_strategy_params() -> dict:
    """strategy_params.json을 읽어 dict로 반환. 모듈 캐시 사용."""
    global _cache
    if _cache is None:
        _cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return _cache


def reload_strategy_params() -> dict:
    """캐시를 버리고 다시 읽는다 (테스트/변경 감지용)."""
    global _cache
    _cache = None
    return load_strategy_params()
