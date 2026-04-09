"""MOM Strategy — 12-1 Month Momentum with SMA200 Filter.

Logic:
  1. Universe: NASDAQ 100 (top liquid tech/growth stocks)
  2. Rank by 12-month return excluding last month (12-1 momentum)
  3. Filter: only stocks above SMA200 (trend confirmation)
  4. Select top 10 by momentum score
  5. Equal-weight allocation within strategy capital
  6. Monthly rebalance

References:
  - Jegadeesh & Titman (1993) "Returns to Buying Winners and Selling Losers"
  - Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere"
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy, Signal, Direction


# NASDAQ 100 representative subset (most liquid)
NASDAQ_100_SUBSET = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO",
    "TSLA", "COST", "NFLX", "AMD", "ADBE", "PEP", "CSCO", "TMUS",
    "INTC", "CMCSA", "TXN", "QCOM", "AMGN", "ISRG", "HON", "INTU",
    "AMAT", "BKNG", "LRCX", "VRTX", "ADI", "MDLZ", "REGN", "KLAC",
    "SNPS", "PANW", "CDNS", "MELI", "ASML", "ABNB", "PYPL", "MAR",
    "CRWD", "FTNT", "ORLY", "CTAS", "MRVL", "CEG", "DASH", "ROP",
    "MNST", "ADSK", "NXPI", "KDP", "AEP", "PCAR", "PAYX", "CHTR",
    "KHC", "FANG", "ODFL", "FAST", "CPRT", "MCHP", "EXC", "DXCM",
    "ROST", "EA", "CTSH", "VRSK", "IDXX", "GEHC", "LULU", "ON",
    "XEL", "BIIB", "CDW", "ILMN", "TTWO", "ZS", "WBD",
    "PLTR", "RKLB", "HIMS", "APLD", "IONQ",  # user's watchlist additions
]


class MomentumStrategy(BaseStrategy):
    name = "MOM"
    capital_pct = 0.25
    universe = NASDAQ_100_SUBSET
    max_positions = 10
    rebalance_freq = "monthly"
    stop_loss_pct = 0.10
    take_profit_pct = 0.30

    def generate_signals(self, market_data: dict) -> list[Signal]:
        """Generate momentum signals from market data.

        Args:
            market_data: Must contain 'prices' key with DataFrame of
                         daily close prices (columns=symbols, index=dates)
                         for at least 252 trading days.
        """
        prices = market_data.get("prices")
        if prices is None or prices.empty:
            return []

        signals = []
        momentum_scores = {}

        for symbol in self.universe:
            if symbol not in prices.columns:
                continue

            series = prices[symbol].dropna()
            if len(series) < 252:
                continue

            # 12-1 momentum: 12-month return excluding last month
            price_12m_ago = series.iloc[-252]
            price_1m_ago = series.iloc[-21]
            price_now = series.iloc[-1]

            if price_12m_ago <= 0 or price_1m_ago <= 0:
                continue

            mom_12_1 = (price_1m_ago / price_12m_ago) - 1.0

            # SMA200 filter: current price must be above 200-day SMA
            sma200 = series.iloc[-200:].mean()
            if price_now < sma200:
                continue

            momentum_scores[symbol] = {
                "score": mom_12_1,
                "price": price_now,
                "sma200": sma200,
            }

        if not momentum_scores:
            return []

        # Rank and select top N
        ranked = sorted(
            momentum_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )[:self.max_positions]

        # Equal weight within strategy
        target_weight = 1.0 / len(ranked) if ranked else 0.0

        for symbol, data in ranked:
            signals.append(Signal(
                strategy=self.name,
                symbol=symbol,
                direction=Direction.BUY,
                weight_pct=target_weight,
                confidence=min(1.0, 0.5 + data["score"]),  # higher momentum = higher confidence
                reason=f"12-1 mom={data['score']:.1%}, price={data['price']:.2f} > SMA200={data['sma200']:.2f}",
                order_type="market",
            ))

        return signals


def fetch_momentum_data(universe: list[str] | None = None, days: int = 400) -> dict:
    """Fetch price data needed for momentum strategy.

    Args:
        universe: List of tickers. Defaults to NASDAQ_100_SUBSET.
        days: Calendar days of history. 400 cal days ~ 280 trading days > 252 needed.

    Returns:
        dict with 'prices' key containing DataFrame.
    """
    tickers = universe or NASDAQ_100_SUBSET
    end = datetime.now()
    start = end - timedelta(days=days)

    data = yf.download(
        tickers=" ".join(tickers),
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
    )

    if data.empty:
        return {"prices": pd.DataFrame()}

    # yfinance returns multi-level columns for multiple tickers
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        # Single ticker case
        prices = data[["Close"]].rename(columns={"Close": tickers[0]})

    return {"prices": prices}
