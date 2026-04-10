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

import json
from pathlib import Path

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy, Signal, Direction


# N-HIGH-3: universe 외부화 — state/universe.json 단일 소스
_UNIVERSE_JSON = Path(__file__).resolve().parent.parent / "state" / "universe.json"

# 최소 폴백 (universe.json 이 읽히지 않을 때만 사용 — 시스템이 멈추지 않도록)
_MOM_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO",
    "TSLA", "COST", "NFLX", "AMD", "ADBE", "PEP", "CSCO", "TMUS",
]


def _load_universe(key: str, fallback: list[str]) -> list[str]:
    try:
        data = json.loads(_UNIVERSE_JSON.read_text(encoding="utf-8"))
        tickers = data.get(key)
        if isinstance(tickers, list) and tickers:
            return list(tickers)
        print(f"[momentum] WARNING: universe.json 에 {key} 없음 → fallback 사용")
    except (OSError, json.JSONDecodeError) as e:
        print(f"[momentum] WARNING: universe.json 로드 실패 ({e}) → fallback 사용")
    return list(fallback)


# NASDAQ 100 representative subset — state/universe.json 에서 로드 (기본 84 종목)
NASDAQ_100_SUBSET = _load_universe("NASDAQ_100_SUBSET", _MOM_FALLBACK)


class MomentumStrategy(BaseStrategy):
    name = "MOM"
    capital_pct = 0.25
    universe = NASDAQ_100_SUBSET
    max_positions = 10
    rebalance_freq = "monthly"
    stop_loss_pct = 0.10
    take_profit_pct = 0.30

    def generate_signals(self, market_data: dict, current_positions: dict | None = None) -> list[Signal]:
        """Generate momentum BUY + SELL signals from market data.

        Args:
            market_data: Must contain 'prices' key with DataFrame of
                         daily close prices (columns=symbols, index=dates)
                         for at least 252 trading days.
            current_positions: Dict of {symbol: {qty, current, ...}} for existing holdings.
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

            # H1 fix: 날짜 기반 lookback (기존 iloc[-252]는 NaN 드롭 시 창 드리프트)
            # 12-1 momentum: 12-month return excluding last month
            last_date = series.index[-1]
            try:
                price_12m_ago = series.asof(last_date - pd.DateOffset(months=12))
                price_1m_ago = series.asof(last_date - pd.DateOffset(months=1))
            except Exception:
                # 폴백: 기존 iloc 방식
                price_12m_ago = series.iloc[-252]
                price_1m_ago = series.iloc[-21]
            price_now = series.iloc[-1]

            if pd.isna(price_12m_ago) or pd.isna(price_1m_ago):
                continue
            if price_12m_ago <= 0 or price_1m_ago <= 0:
                continue

            mom_12_1 = (price_1m_ago / price_12m_ago) - 1.0

            # SMA200 filter: 최근 200거래일 평균 (iloc 유지 — 창 드리프트 미미)
            sma200 = series.iloc[-200:].mean()
            if price_now < sma200:
                continue

            momentum_scores[symbol] = {
                "score": mom_12_1,
                "price": price_now,
                "sma200": sma200,
            }

        # ── SELL signals for existing positions that no longer qualify ──
        if current_positions:
            for symbol in list(current_positions.keys()):
                if symbol not in prices.columns:
                    continue
                series = prices[symbol].dropna()
                if len(series) < 252:
                    continue

                price_now = series.iloc[-1]
                sma200 = series.iloc[-200:].mean()
                # H1 fix: 날짜 기반 lookback
                last_date = series.index[-1]
                try:
                    price_12m_ago = series.asof(last_date - pd.DateOffset(months=12))
                    price_1m_ago = series.asof(last_date - pd.DateOffset(months=1))
                except Exception:
                    price_12m_ago = series.iloc[-252]
                    price_1m_ago = series.iloc[-21]
                if pd.isna(price_12m_ago) or pd.isna(price_1m_ago) or price_12m_ago <= 0:
                    mom_12_1 = 0.0
                else:
                    mom_12_1 = (price_1m_ago / price_12m_ago) - 1.0

                # EXIT: momentum < 0 OR price < SMA200
                should_sell = mom_12_1 < 0 or price_now < sma200
                if should_sell:
                    pos = current_positions[symbol]
                    weight = pos.get("market_value", 0) / 1.0  # actual weight resolved at execution
                    signals.append(Signal(
                        strategy=self.name,
                        symbol=symbol,
                        direction=Direction.SELL,
                        weight_pct=0.0,
                        confidence=0.9,
                        reason=f"EXIT: mom={mom_12_1:.1%}, price={price_now:.2f} {'< SMA200=' + f'{sma200:.2f}' if price_now < sma200 else 'mom<0'}",
                        order_type="market",
                    ))

        if not momentum_scores:
            return signals  # return SELL signals even if no BUY candidates

        # Rank and select top N
        ranked = sorted(
            momentum_scores.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )[:self.max_positions]

        # M-2: 전 종목 음수 모멘텀 시 매수 거부
        if ranked and all(data["score"] < 0 for _, data in ranked):
            print(
                f"[MOM] WARNING: 전 종목 음수 모멘텀 — 매수 거부 "
                f"(best={ranked[0][1]['score']:.1%})"
            )
            return signals  # SELL signals only

        # Equal weight within strategy
        target_weight = 1.0 / len(ranked) if ranked else 0.0

        # Confidence: scale by relative rank (top=1.0, bottom=0.5)
        max_mom = ranked[0][1]["score"] if ranked else 1.0

        for symbol, data in ranked:
            # Scale confidence: 0.5 (lowest ranked) to 1.0 (highest ranked)
            # M-2: max_mom <= 0 보호 (음수 역전 방지)
            if max_mom > 0:
                relative = data["score"] / max_mom
            else:
                relative = 0.0
            confidence = 0.5 + 0.5 * relative

            signals.append(Signal(
                strategy=self.name,
                symbol=symbol,
                direction=Direction.BUY,
                weight_pct=target_weight,
                confidence=round(min(1.0, confidence), 4),
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
        return {"prices": pd.DataFrame(), "volumes": pd.DataFrame()}

    # yfinance returns multi-level columns for multiple tickers
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
        volumes = data["Volume"] if "Volume" in data.columns.get_level_values(0) else pd.DataFrame()
    else:
        # Single ticker case
        prices = data[["Close"]].rename(columns={"Close": tickers[0]})
        volumes = data[["Volume"]].rename(columns={"Volume": tickers[0]}) if "Volume" in data.columns else pd.DataFrame()

    return {"prices": prices, "volumes": volumes}
