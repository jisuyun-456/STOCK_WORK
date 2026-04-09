"""Alpaca Trading Client — paper/live toggle via environment variable.

Switch between Paper and Live trading by changing ALPACA_MODE:
  Paper: ALPACA_MODE=paper (default)
  Live:  ALPACA_MODE=live

No code changes required for the transition.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce


@lru_cache(maxsize=1)
def get_client() -> TradingClient:
    """Get singleton Alpaca TradingClient.

    Environment variables required:
        ALPACA_API_KEY: API key ID
        ALPACA_SECRET_KEY: API secret key
        ALPACA_MODE: "paper" (default) or "live"
    """
    api_key = os.environ["ALPACA_API_KEY"]
    secret_key = os.environ["ALPACA_SECRET_KEY"]
    mode = os.environ.get("ALPACA_MODE", "paper")

    if mode not in ("paper", "live"):
        raise ValueError(f"ALPACA_MODE must be 'paper' or 'live', got '{mode}'")

    return TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=(mode == "paper"),
    )


def get_account_info() -> dict:
    """Get account balance, buying power, and equity."""
    client = get_client()
    account = client.get_account()
    return {
        "equity": float(account.equity),
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "portfolio_value": float(account.portfolio_value),
        "mode": os.environ.get("ALPACA_MODE", "paper"),
    }


def get_positions() -> list[dict]:
    """Get all current positions."""
    client = get_client()
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "avg_entry_price": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pl": float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
        }
        for p in positions
    ]


def submit_market_order(
    symbol: str,
    qty: float,
    side: str,
    client_order_id: str,
) -> dict:
    """Submit a market order.

    Args:
        symbol: Ticker symbol (e.g., "NVDA")
        qty: Number of shares (fractional supported)
        side: "buy" or "sell"
        client_order_id: Strategy-tagged ID (e.g., "MOM-20260409-NVDA-001")
    """
    client = get_client()
    request = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )
    order = client.submit_order(request)
    return _order_to_dict(order)


def submit_limit_order(
    symbol: str,
    qty: float,
    side: str,
    limit_price: float,
    client_order_id: str,
) -> dict:
    """Submit a limit order."""
    client = get_client()
    request = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        client_order_id=client_order_id,
    )
    order = client.submit_order(request)
    return _order_to_dict(order)


def close_position(symbol: str) -> dict:
    """Close entire position for a symbol (market order)."""
    client = get_client()
    result = client.close_position(symbol)
    return _order_to_dict(result)


def get_open_orders() -> list[dict]:
    """Get all open (pending) orders."""
    client = get_client()
    orders = client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN))
    return [_order_to_dict(o) for o in orders]


def is_market_open() -> bool:
    """Check if US market is currently open."""
    client = get_client()
    clock = client.get_clock()
    return clock.is_open


def get_order_by_client_id(client_order_id: str) -> dict | None:
    """Look up an order by client_order_id."""
    client = get_client()
    try:
        order = client.get_order_by_client_id(client_order_id)
        return _order_to_dict(order)
    except Exception:
        return None


def _order_to_dict(order) -> dict:
    """Convert Alpaca Order object to serializable dict."""
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": str(order.side),
        "qty": str(order.qty),
        "filled_qty": str(order.filled_qty) if order.filled_qty else "0",
        "filled_avg_price": str(order.filled_avg_price)
        if order.filled_avg_price
        else None,
        "status": str(order.status),
        "order_type": str(order.order_type),
        "created_at": str(order.created_at),
    }
