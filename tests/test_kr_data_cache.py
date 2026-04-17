"""Tests for kr_data.cache.KRCache"""
import time
import pytest
import pandas as pd
import tempfile
import os

from kr_data.cache import KRCache


@pytest.fixture
def cache(tmp_path):
    """Create a KRCache instance using a temporary directory."""
    return KRCache(cache_dir=str(tmp_path / "kr"))


def test_cache_set_and_get(cache):
    """Set value, get within TTL → same value returned."""
    value = {"symbol": "005930", "price": 75000}
    cache.set("samsung_price", value)
    result = cache.get("samsung_price", ttl_seconds=60)
    assert result == value


def test_cache_expired(cache):
    """Set value, get with TTL=0 → None returned (immediately expired)."""
    value = {"symbol": "005930", "price": 75000}
    cache.set("samsung_price", value)
    # TTL=0 means already expired
    result = cache.get("samsung_price", ttl_seconds=0)
    assert result is None


def test_cache_df_roundtrip(cache):
    """Set DataFrame, get within TTL → equal DataFrame returned."""
    df = pd.DataFrame({
        "open": [74000, 75000],
        "close": [75000, 76000],
        "volume": [1000000, 1200000],
    })
    cache.set_df("samsung_ohlcv", df)
    result = cache.get_df("samsung_ohlcv", ttl_seconds=60)
    assert result is not None
    pd.testing.assert_frame_equal(result, df)


def test_cache_invalidate(cache):
    """Set value, invalidate, get → None returned."""
    value = {"symbol": "005930", "price": 75000}
    cache.set("samsung_price", value)
    # Confirm it's there first
    assert cache.get("samsung_price", ttl_seconds=60) is not None
    cache.invalidate("samsung_price")
    result = cache.get("samsung_price", ttl_seconds=60)
    assert result is None
