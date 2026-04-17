"""Common retry decorator using tenacity.

Used by every HTTP call in kr_data/ to provide exponential backoff
with 3 retry attempts on any exception.
"""
import logging
import functools
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

_logger = logging.getLogger("kr_data.retry")


def retry_with_backoff(func):
    """Decorator: exponential backoff, 3 retries on any exception.

    Configuration:
      - stop: after 3 attempts
      - wait: exponential backoff, multiplier=1, min=1s, max=10s
      - reraise: True (original exception propagates after exhaustion)
    """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
        before_sleep=before_sleep_log(_logger, logging.WARNING),
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
