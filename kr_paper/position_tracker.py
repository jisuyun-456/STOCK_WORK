"""KR Paper Position Tracker — pure in-memory position accounting.

All functions operate on a plain dict and return an updated copy.
They do NOT read or write any file — callers are responsible for persistence.
"""

from __future__ import annotations


def update_position_buy(positions: dict, ticker: str, qty: int, price_krw: int) -> dict:
    """Update positions dict after a buy.

    If ticker already exists: compute weighted average of avg_price_krw.
        new_avg = (old_qty * old_avg + qty * price_krw) / (old_qty + qty)
    If ticker not in positions: create entry.

    positions[ticker] = {
        "qty": int,
        "avg_price_krw": int  # rounded weighted average
    }

    Returns updated positions dict.
    IMPORTANT: Does not save to file — caller handles that.
    """
    if ticker in positions:
        old_qty = positions[ticker]["qty"]
        old_avg = positions[ticker]["avg_price_krw"]
        new_qty = old_qty + qty
        new_avg = round((old_qty * old_avg + qty * price_krw) / new_qty)
        positions[ticker] = {"qty": new_qty, "avg_price_krw": new_avg}
    else:
        positions[ticker] = {"qty": qty, "avg_price_krw": price_krw}
    return positions


def update_position_sell(positions: dict, ticker: str, qty: int) -> dict:
    """Update positions dict after a sell.

    Reduce qty. If qty reaches 0, remove ticker from positions.

    Raises ValueError if ticker not in positions or qty > current qty.

    Returns updated positions dict.
    IMPORTANT: Does not save to file — caller handles that.
    """
    if ticker not in positions:
        raise ValueError(f"update_position_sell: ticker {ticker!r} not in positions")

    current_qty = positions[ticker]["qty"]
    if qty > current_qty:
        raise ValueError(
            f"update_position_sell: sell qty {qty} > current qty {current_qty} for {ticker!r}"
        )

    new_qty = current_qty - qty
    if new_qty == 0:
        del positions[ticker]
    else:
        positions[ticker]["qty"] = new_qty
    return positions


def compute_unrealized_pl(positions: dict, current_prices: dict) -> dict:
    """Compute unrealized P&L for each position.

    For each ticker in positions:
    {
      ticker: {
        "qty": int,
        "avg_price_krw": int,
        "current_price_krw": int,   # current_prices.get(ticker, avg_price_krw)
        "market_value_krw": qty * current_price,
        "unrealized_pl_krw": (current_price - avg_price) * qty,
        "unrealized_plpc": (current_price - avg_price) / avg_price  # float
      }
    }

    Returns dict keyed by ticker.
    """
    result: dict = {}
    for ticker, pos in positions.items():
        qty = pos["qty"]
        avg_price = pos["avg_price_krw"]
        current_price = current_prices.get(ticker, avg_price)
        market_value = qty * current_price
        unrealized_pl = (current_price - avg_price) * qty
        unrealized_plpc = (current_price - avg_price) / avg_price if avg_price != 0 else 0.0
        result[ticker] = {
            "qty": qty,
            "avg_price_krw": avg_price,
            "current_price_krw": current_price,
            "market_value_krw": market_value,
            "unrealized_pl_krw": unrealized_pl,
            "unrealized_plpc": unrealized_plpc,
        }
    return result
