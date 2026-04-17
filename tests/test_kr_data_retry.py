"""Tests for kr_data.retry.retry_with_backoff"""
import pytest
from unittest.mock import MagicMock, call

from kr_data.retry import retry_with_backoff


def test_retry_succeeds_on_first_try():
    """Decorated function called exactly once when it succeeds immediately."""
    mock_fn = MagicMock(return_value="ok")

    @retry_with_backoff
    def call_fn():
        return mock_fn()

    result = call_fn()
    assert result == "ok"
    assert mock_fn.call_count == 1


def test_retry_retries_three_times():
    """Function raises on first 2 calls, succeeds on 3rd → called exactly 3 times."""
    call_count = {"n": 0}

    @retry_with_backoff
    def flaky():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise ValueError("transient error")
        return "success"

    result = flaky()
    assert result == "success"
    assert call_count["n"] == 3


def test_retry_reraises_after_exhaustion():
    """Function always raises → exception propagates after 3 attempts."""
    call_count = {"n": 0}

    @retry_with_backoff
    def always_fails():
        call_count["n"] += 1
        raise RuntimeError("permanent error")

    with pytest.raises(RuntimeError, match="permanent error"):
        always_fails()

    assert call_count["n"] == 3
