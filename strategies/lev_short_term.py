"""LEV Short-Term — 1~3일 단기 방향성 신호 기반 TQQQ/SQQQ/CASH 전환.

Rule:
  vix_5d = (VIX_today / VIX_5d_ago) - 1
  spy_3d = (SPY_today / SPY_3d_ago) - 1

  vix_5d <= -0.05 and spy_3d >= +0.005   → TQQQ 100%  (공포 해소 + 상승 모멘텀)
  vix_5d >= +0.10 and spy_3d <= -0.005   → SQQQ 100%  (공포 확대 + 하락 모멘텀)
  else                                    → CASH 100%  (방향성 없음)
  regime == "CRISIS"                      → CASH 100%  (무조건 방어)

기존 LEV(leveraged_etf.py, 장기 레짐 기반)와 독립.
max_positions=1 (단일 ETF 보유), 별도 allocated_capital 슬롯.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from strategies.base_strategy import BaseStrategy, Signal, Direction

_LONG_ETF = "TQQQ"
_INVERSE_ETF = "SQQQ"

_DEFAULTS: dict = {
    "vix_down_threshold": -0.05,    # VIX 5일 -5% 이하 = 공포 해소
    "vix_up_threshold": +0.10,      # VIX 5일 +10% 이상 = 공포 확대
    "spy_up_threshold": +0.005,     # SPY 3일 +0.5% 이상 = 상승 모멘텀
    "spy_down_threshold": -0.005,   # SPY 3일 -0.5% 이하 = 하락 모멘텀
    "vix_lookback_days": 5,
    "spy_lookback_days": 3,
}


def _fetch_vix_change(lookback_days: int = 5) -> float | None:
    """VIX `lookback_days`일 변화율. 실패 시 None 반환."""
    try:
        hist = yf.Ticker("^VIX").history(period=f"{max(lookback_days + 3, 10)}d")
        closes = hist["Close"].dropna()
        if len(closes) < lookback_days + 1:
            return None
        return float(closes.iloc[-1] / closes.iloc[-lookback_days - 1] - 1.0)
    except Exception as e:
        print(f"[LEV_ST] VIX fetch failed: {e}")
        return None


def _spy_change_from_data(market_data: dict, lookback_days: int = 3) -> float | None:
    """market_data['prices']에서 SPY `lookback_days`일 변화율. 없으면 yfinance fallback."""
    prices = market_data.get("prices")
    if isinstance(prices, pd.DataFrame) and "SPY" in prices.columns:
        s = prices["SPY"].dropna()
        if len(s) >= lookback_days + 1:
            return float(s.iloc[-1] / s.iloc[-lookback_days - 1] - 1.0)
    try:
        hist = yf.Ticker("SPY").history(period=f"{max(lookback_days + 3, 10)}d")
        closes = hist["Close"].dropna()
        if len(closes) < lookback_days + 1:
            return None
        return float(closes.iloc[-1] / closes.iloc[-lookback_days - 1] - 1.0)
    except Exception as e:
        print(f"[LEV_ST] SPY fetch failed: {e}")
        return None


class LevShortTermStrategy(BaseStrategy):
    name = "LEV_ST"
    universe = [_LONG_ETF, _INVERSE_ETF]
    max_positions = 1
    stop_loss_pct = 0.15
    take_profit_pct = 0.10
    regime: str = "NEUTRAL"
    allocated_capital: float = 0.0

    def __init__(self) -> None:
        from config.loader import load_strategy_params
        cfg = load_strategy_params().get("lev_short_term", {}) or {}
        self._p = {**_DEFAULTS, **cfg}

    def _target_symbol(self, vix_5d: float | None, spy_3d: float | None) -> str | None:
        """→ 'TQQQ' | 'SQQQ' | None(=CASH)."""
        if self.regime == "CRISIS":
            return None
        if vix_5d is None or spy_3d is None:
            print("[LEV_ST] data unavailable → CASH")
            return None
        if (vix_5d <= self._p["vix_down_threshold"]
                and spy_3d >= self._p["spy_up_threshold"]):
            return _LONG_ETF
        if (vix_5d >= self._p["vix_up_threshold"]
                and spy_3d <= self._p["spy_down_threshold"]):
            return _INVERSE_ETF
        return None

    def generate_signals(
        self,
        market_data: dict,
        current_positions: dict | None = None,
    ) -> list[Signal]:
        vix_5d = _fetch_vix_change(self._p["vix_lookback_days"])
        spy_3d = _spy_change_from_data(market_data, self._p["spy_lookback_days"])
        target = self._target_symbol(vix_5d, spy_3d)

        vix_str = f"{vix_5d:+.2%}" if vix_5d is not None else "N/A"
        spy_str = f"{spy_3d:+.2%}" if spy_3d is not None else "N/A"
        print(
            f"  LEV_ST: regime={self.regime}, VIX5d={vix_str}, SPY3d={spy_str}, "
            f"target={target or 'CASH'}, allocated=${self.allocated_capital:,.2f}"
        )

        current = current_positions or {}
        sells: list[Signal] = []
        buys: list[Signal] = []

        # 보유 중인 종목 중 target 아닌 것 전량 청산
        for sym, pos in current.items():
            if float(pos.get("market_value", 0) or 0) <= 0:
                continue
            if sym == target:
                continue
            sells.append(Signal(
                strategy=self.name, symbol=sym, direction=Direction.SELL,
                weight_pct=1.0, confidence=0.99,
                reason=f"LEV_ST VIX5d={vix_str} SPY3d={spy_str}: {sym} → 청산",
                order_type="market",
            ))

        # target 있고 미보유 시 신규 BUY
        if target is not None:
            already_held = (
                target in current
                and float(current.get(target, {}).get("market_value", 0) or 0) > 0
            )
            if not already_held and self.allocated_capital > 0:
                buys.append(Signal(
                    strategy=self.name, symbol=target, direction=Direction.BUY,
                    weight_pct=1.0, confidence=0.92,
                    reason=f"LEV_ST VIX5d={vix_str} SPY3d={spy_str}: 100% → {target}",
                    order_type="market",
                ))

        return sells + buys

    @staticmethod
    def get_stop_loss_for_regime(regime: str) -> float | None:
        """CRISIS: target=CASH라 자연 청산. 그 외 -15% 손절."""
        return None if regime == "CRISIS" else -0.15

    @staticmethod
    def get_take_profit_for_regime(regime: str) -> float | None:
        return 0.10 if regime != "CRISIS" else None
