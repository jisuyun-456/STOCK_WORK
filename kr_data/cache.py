"""Unified cache with TTL management for kr_data.

Supports:
  - JSON cache (small data, dict/list) → cache/kr/{key}.json
  - Parquet cache (OHLCV / time-series DataFrames) → cache/kr/{key}.parquet
    with sidecar .meta.json storing {"cached_at": <unix_timestamp>}

TTL is checked at read time; expired entries are treated as cache misses.
"""
import json
import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

_logger = logging.getLogger("kr_data.cache")


class KRCache:
    """Disk-backed cache with TTL for JSON and DataFrame entries."""

    def __init__(self, cache_dir: str = "cache/kr") -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Key sanitisation — prevents path traversal attacks
    # ------------------------------------------------------------------

    def _safe_key(self, key: str) -> str:
        """Return a filesystem-safe version of *key*.

        Compound keys like "pykrx/ohlcv/005930" are flattened to
        "pykrx_ohlcv_005930" so they stay inside self._dir.
        """
        return key.replace("/", "_").replace("\\", "_").replace("..", "__")

    # ------------------------------------------------------------------
    # JSON cache
    # ------------------------------------------------------------------

    def _json_path(self, key: str) -> Path:
        return self._dir / f"{self._safe_key(key)}.json"

    def get(self, key: str, ttl_seconds: int) -> Optional[dict]:
        """Return cached value if not expired, else None.

        Args:
            key: Cache key (used as filename stem).
            ttl_seconds: Maximum age in seconds. 0 → always expired.
        """
        path = self._json_path(key)
        if not path.exists():
            _logger.debug("cache miss (no file): %s", key)
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("cache read error for %s: %s", key, exc)
            return None

        cached_at: float = data.get("__kr_cached_at__", 0.0)
        age = time.time() - cached_at
        if age >= ttl_seconds:
            _logger.debug("cache expired (age=%.1fs ttl=%ds): %s", age, ttl_seconds, key)
            return None

        _logger.debug("cache hit: %s", key)
        return data.get("__data__")

    def set(self, key: str, value: dict) -> None:
        """Save value as JSON to cache/kr/{key}.json with timestamp.

        Args:
            key: Cache key.
            value: Dict to cache. Must be JSON-serialisable.
        """
        path = self._json_path(key)
        payload = {"__data__": value, "__kr_cached_at__": time.time()}
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            _logger.debug("cache set: %s", key)
        except OSError as exc:
            _logger.warning("cache write error for %s: %s", key, exc)

    # ------------------------------------------------------------------
    # DataFrame (parquet) cache
    # ------------------------------------------------------------------

    def _parquet_path(self, key: str) -> Path:
        return self._dir / f"{self._safe_key(key)}.parquet"

    def _meta_path(self, key: str) -> Path:
        return self._dir / f"{self._safe_key(key)}.meta.json"

    def get_df(self, key: str, ttl_seconds: int) -> Optional[pd.DataFrame]:
        """Return cached DataFrame if not expired, else None.

        Args:
            key: Cache key.
            ttl_seconds: Maximum age in seconds. 0 → always expired.
        """
        parquet = self._parquet_path(key)
        meta = self._meta_path(key)

        if not parquet.exists() or not meta.exists():
            _logger.debug("df cache miss (no file): %s", key)
            return None

        try:
            meta_data = json.loads(meta.read_text(encoding="utf-8"))
            cached_at: float = meta_data.get("cached_at", 0.0)
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("df meta read error for %s: %s", key, exc)
            return None

        age = time.time() - cached_at
        if age >= ttl_seconds:
            _logger.debug("df cache expired (age=%.1fs ttl=%ds): %s", age, ttl_seconds, key)
            return None

        try:
            df = pd.read_parquet(str(parquet))
            _logger.debug("df cache hit: %s", key)
            return df
        except Exception as exc:
            _logger.warning("df read error for %s: %s", key, exc)
            return None

    def set_df(self, key: str, df: pd.DataFrame) -> None:
        """Save DataFrame as parquet with sidecar .meta.json for timestamp.

        Args:
            key: Cache key.
            df: DataFrame to cache.
        """
        parquet = self._parquet_path(key)
        meta = self._meta_path(key)
        try:
            df.to_parquet(str(parquet), index=True)
            meta.write_text(
                json.dumps({"cached_at": time.time()}),
                encoding="utf-8",
            )
            _logger.debug("df cache set: %s", key)
        except Exception as exc:
            _logger.warning("df write error for %s: %s", key, exc)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, key: str) -> None:
        """Remove cached entry (both JSON and parquet/meta if exist).

        Args:
            key: Cache key to remove.
        """
        removed = False
        for path in (
            self._json_path(key),
            self._parquet_path(key),
            self._meta_path(key),
        ):
            if path.exists():
                path.unlink()
                removed = True
        if removed:
            _logger.debug("cache invalidated: %s", key)
        else:
            _logger.debug("cache invalidate: key not found: %s", key)
