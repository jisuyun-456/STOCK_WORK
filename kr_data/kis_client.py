"""KIS (한국투자증권) Open API client.

Data queries are mock-safe: if KIS_APP_KEY / KIS_APP_SECRET are not set,
the client enters degraded mode and returns None / [] for all data calls.

Paper KR order simulation is fully functional without credentials.
Live orders are not yet supported (raise NotImplementedError).
"""
import logging
import os
from typing import Literal

from kr_data.retry import retry_with_backoff
from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.kis")
_cache = KRCache()
_TTL = 60  # 1 minute (real-time data)


class KisClient:
    def __init__(
        self,
        app_key: str | None = None,
        app_secret: str | None = None,
        mode: Literal["paper", "live"] = "paper",
    ):
        self._key = app_key or os.environ.get("KIS_APP_KEY")
        self._secret = app_secret or os.environ.get("KIS_APP_SECRET")
        self._mode = mode
        self._token: str | None = None

        if not self._key or not self._secret:
            _logger.warning(
                "KIS_APP_KEY/KIS_APP_SECRET not set — KIS client in degraded mode"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_configured(self) -> bool:
        return bool(self._key and self._secret)

    @retry_with_backoff
    def _get_token_raw(self) -> str:
        """Get OAuth token from KIS API."""
        if not self._is_configured():
            raise ValueError("KIS credentials not set")
        import requests

        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        resp = requests.post(
            url,
            json={
                "grant_type": "client_credentials",
                "appkey": self._key,
                "appsecret": self._secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ------------------------------------------------------------------
    # Data queries (mock-safe)
    # ------------------------------------------------------------------

    def get_quote(self, ticker: str) -> dict | None:
        """Real-time quote for a KRX ticker.

        Returns {"ticker": ..., "price": ..., "change_pct": ..., "volume": ...}
        or None if not configured or on error.
        """
        if not self._is_configured():
            _logger.warning(
                "KIS not configured — get_quote(%s) returning None", ticker
            )
            return None

        cache_key = f"kis_quote_{ticker}"
        cached = _cache.get(cache_key, _TTL)
        if cached is not None:
            return cached

        try:
            # Real implementation would call KIS FHKST01010100 API here.
            # Returns None until KIS credentials are available.
            return None
        except Exception as e:
            _logger.warning("get_quote(%s) failed: %s", ticker, e)
            return None

    def get_daily_executions(self, ticker: str) -> list[dict]:
        """Daily executions for ticker. Returns [] if not configured or on error."""
        if not self._is_configured():
            return []
        try:
            return []  # Stub — real implementation pending KIS key
        except Exception as e:
            _logger.warning("get_daily_executions(%s) failed: %s", ticker, e)
            return []

    def get_news(self, ticker: str) -> list[dict]:
        """Stock news from KIS. Returns [] if not configured or on error."""
        if not self._is_configured():
            return []
        try:
            return []  # Stub — real implementation pending KIS key
        except Exception as e:
            _logger.warning("get_news(%s) failed: %s", ticker, e)
            return []

    def get_positions(self) -> list[dict]:
        """Current positions from KIS. Returns [] if not configured."""
        if not self._is_configured():
            return []
        return []  # Stub — real implementation pending KIS key

    def get_account_balance(self) -> dict | None:
        """Account balance from KIS. Returns None if not configured."""
        if not self._is_configured():
            return None
        return None  # Stub — real implementation pending KIS key

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def place_order(
        self,
        ticker: str,
        qty: int,
        price: int,
        side: Literal["BUY", "SELL"],
    ) -> dict:
        """Place an order.

        mode="paper" → simulate (return mock fill dict, no real order sent)
        mode="live"  → raise NotImplementedError (pending API approval)

        Returns:
            dict with keys: order_id, ticker, qty, price, side, status
            status is "simulated" for paper orders.
        """
        if self._mode == "live":
            raise NotImplementedError(
                "Live KIS orders not yet supported — pending API approval"
            )

        # Paper simulation — no network call, no credentials required
        return {
            "order_id": f"KIS-PAPER-{ticker}-{side}-{qty}",
            "ticker": ticker,
            "qty": qty,
            "price": price,
            "side": side,
            "status": "simulated",
        }
