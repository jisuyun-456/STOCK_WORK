"""Growth Small Cap Strategy (GRW) — 소형 성장주 텐배거 발굴

유니버스: state/universe.json["RUSSELL_2000_SUBSET"] (~100 종목)
스코어:  0.5 × momentum_rank + 0.3 × growth_rank + 0.2 × quality_rank
필터:    시총 $200M~$5B, 매출성장률 > 10%
레짐:    BULL/NEUTRAL 진입, BEAR BUY 차단, CRISIS 전량 청산
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from strategies.base_strategy import BaseStrategy, Direction, Signal

_UNIVERSE_JSON = Path(__file__).resolve().parent.parent / "state" / "universe.json"

_GRW_FALLBACK = [
    "IRTC", "INSP", "TMDX", "ACMR", "FORM", "CRDO", "AMBA",
    "APPF", "JAMF", "HIMS", "WEAV", "DOCN", "GTLB",
    "RXDX", "MGNX", "ACAD", "PRAX", "KYMR", "ARWR",
    "YETI", "KURA", "GSHD", "POWL", "KTOS", "ESAB",
    "BRZE", "ASAN", "FROG", "NCNO",
]


def _load_universe() -> list[str]:
    try:
        data = json.loads(_UNIVERSE_JSON.read_text(encoding="utf-8"))
        tickers = data.get("RUSSELL_2000_SUBSET")
        if isinstance(tickers, list) and tickers:
            return list(tickers)
        print("[GRW] WARNING: universe.json에 RUSSELL_2000_SUBSET 없음 → fallback 사용")
    except (OSError, json.JSONDecodeError) as e:
        print(f"[GRW] WARNING: universe.json 로드 실패 ({e}) → fallback 사용")
    return list(_GRW_FALLBACK)


_GRW_UNIVERSE = _load_universe()

# BEAR/CRISIS 레짐에서 GRW BUY 차단
_NO_BUY_REGIMES = {"BEAR", "CRISIS"}


def fetch_growth_data(
    universe: list[str] | None = None,
    momentum_days: int = 126,
    fundamentals_top_n: int = 30,
) -> dict:
    """GRW용 시장 데이터 fetch.

    Returns:
        {
            "prices": pd.DataFrame,
            "fundamentals": {ticker: {market_cap, revenue_growth, roe, free_cashflow, ok}}
        }
    """
    tickers = universe if universe is not None else _GRW_UNIVERSE
    if not tickers:
        return {"prices": pd.DataFrame(), "fundamentals": {}}

    # 1) 가격 데이터 배치 다운로드 (전체 유니버스, 한 번의 API 호출)
    end = date.today()
    start = end - timedelta(days=momentum_days + 20)
    try:
        raw = yf.download(
            tickers=" ".join(tickers),
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"].dropna(axis=1, how="all")
        else:
            single = tickers[0] if tickers else "UNK"
            prices = raw[["Close"]].rename(columns={"Close": single})
    except Exception as e:
        print(f"[GRW] 가격 다운로드 실패: {e}")
        return {"prices": pd.DataFrame(), "fundamentals": {}}

    if prices.empty:
        return {"prices": prices, "fundamentals": {}}

    # 2) 모멘텀 상위 N개만 펀더멘탈 조회 (API 부담 최소화)
    mom_ret = prices.pct_change(momentum_days).iloc[-1].dropna().sort_values(ascending=False)
    top_tickers = list(mom_ret.head(fundamentals_top_n).index)

    fundamentals: dict[str, dict] = {}
    for ticker in top_tickers:
        try:
            info = yf.Ticker(ticker).info or {}
            mcap = info.get("marketCap")
            rev_growth = info.get("revenueGrowth")
            roe = info.get("returnOnEquity")
            fcf = info.get("freeCashflow")
            fundamentals[ticker] = {
                "market_cap": mcap,
                "revenue_growth": rev_growth,
                "roe": roe,
                "free_cashflow": fcf,
                "ok": mcap is not None,
            }
        except Exception as e:
            print(f"[GRW] {ticker} 펀더멘탈 조회 실패: {e}")
            fundamentals[ticker] = {"ok": False}

    print(f"[GRW] 데이터 로드 완료: 가격 {len(prices.columns)}종목 / 펀더멘탈 {len(fundamentals)}종목")
    return {"prices": prices, "fundamentals": fundamentals}


class GrowthSmallCapStrategy(BaseStrategy):
    """Russell 2000 소형 성장주 텐배거 발굴 전략."""

    name = "GRW"
    capital_pct = 0.10
    universe = _GRW_UNIVERSE
    max_positions = 8
    rebalance_freq = "weekly"
    stop_loss_pct = 0.15

    def __init__(self) -> None:
        from config.loader import load_strategy_params
        _cfg = load_strategy_params().get("growth_smallcap", {})
        self.max_positions: int = int(_cfg.get("max_positions", self.__class__.max_positions))
        self.position_pct: float = float(_cfg.get("position_pct", 0.125))
        self.stop_loss_pct: float = float(_cfg.get("stop_loss_pct", 0.15))
        self.momentum_lookback: int = int(_cfg.get("momentum_lookback_days", 126))
        self.min_revenue_growth: float = float(_cfg.get("min_revenue_growth", 0.10))
        self.max_market_cap: float = float(_cfg.get("max_market_cap", 5_000_000_000))
        self.min_market_cap: float = float(_cfg.get("min_market_cap", 200_000_000))
        self.momentum_weight: float = float(_cfg.get("momentum_weight", 0.5))
        self.growth_weight: float = float(_cfg.get("growth_weight", 0.3))
        self.quality_weight: float = float(_cfg.get("quality_weight", 0.2))

    def _compute_scores(self, prices: pd.DataFrame, fundamentals: dict) -> pd.Series:
        """종목별 복합 스코어 (0~1, 높을수록 우선 매수)."""
        if prices.empty or not fundamentals:
            return pd.Series(dtype=float)

        mom_ret = prices.pct_change(self.momentum_lookback).iloc[-1].dropna()

        # 펀더멘탈 필터 통과 종목만
        valid: dict[str, dict] = {}
        for t, f in fundamentals.items():
            if not f.get("ok"):
                continue
            mcap = f.get("market_cap")
            rev_g = f.get("revenue_growth")
            if mcap is None:
                continue
            if not (self.min_market_cap <= mcap <= self.max_market_cap):
                continue
            if rev_g is not None and rev_g < self.min_revenue_growth:
                continue
            valid[t] = f

        if not valid:
            return pd.Series(dtype=float)

        tickers = [t for t in valid if t in mom_ret.index]
        if not tickers:
            return pd.Series(dtype=float)

        mom_vals = mom_ret[tickers]
        n = len(tickers)

        if n == 1:
            score = pd.Series([1.0], index=tickers)
        else:
            mom_rank = mom_vals.rank(pct=True)
            growth_vals = pd.Series({t: (valid[t].get("revenue_growth") or 0.0) for t in tickers})
            growth_rank = growth_vals.rank(pct=True)
            quality_vals = pd.Series({
                t: float((valid[t].get("roe") or 0.0) > 0 or (valid[t].get("free_cashflow") or 0) > 0)
                for t in tickers
            })
            quality_rank = quality_vals.rank(pct=True)
            score = (
                self.momentum_weight * mom_rank
                + self.growth_weight * growth_rank
                + self.quality_weight * quality_rank
            )

        return score.sort_values(ascending=False)

    def generate_signals(
        self,
        market_data: dict,
        current_positions: dict | None = None,
        regime: str | None = None,
    ) -> list[Signal]:
        regime = regime or getattr(self, "regime", "NEUTRAL")
        # grw_prices/grw_fundamentals 키 우선, fallback으로 prices/fundamentals
        prices: pd.DataFrame = market_data.get("grw_prices", market_data.get("prices", pd.DataFrame()))
        fundamentals: dict = market_data.get("grw_fundamentals", market_data.get("fundamentals", {}))
        current_positions = current_positions or {}

        # CRISIS: 보유 전량 청산
        if regime == "CRISIS":
            return [
                Signal(
                    strategy=self.name, symbol=sym,
                    direction=Direction.SELL,
                    weight_pct=0.0, confidence=0.95,
                    reason="CRISIS 레짐 — GRW 전량 청산",
                    order_type="market",
                )
                for sym in list(current_positions.keys())
            ]

        if prices.empty:
            return []

        scores = self._compute_scores(prices, fundamentals)
        if scores.empty:
            return []

        top_n = list(scores.head(self.max_positions).index)
        drop_cutoff = set(scores.head(self.max_positions * 2).index)

        signals: list[Signal] = []

        # SELL: 보유 중인데 상위 2×max_positions 밖으로 이탈
        for sym in list(current_positions.keys()):
            if sym not in drop_cutoff or sym not in scores.index:
                signals.append(Signal(
                    strategy=self.name, symbol=sym,
                    direction=Direction.SELL,
                    weight_pct=0.0, confidence=0.85,
                    reason="GRW 스코어 이탈 — 청산",
                    order_type="market",
                ))

        # BUY: BEAR/CRISIS 차단, 음수 모멘텀 차단
        if regime not in _NO_BUY_REGIMES:
            mom_ret = prices.pct_change(self.momentum_lookback).iloc[-1]
            for sym in top_n:
                if sym in current_positions:
                    continue
                if sym in mom_ret.index and mom_ret[sym] <= 0:
                    continue
                confidence = float(min(0.95, 0.5 + scores[sym] * 0.45))
                signals.append(Signal(
                    strategy=self.name, symbol=sym,
                    direction=Direction.BUY,
                    weight_pct=self.position_pct,
                    confidence=confidence,
                    reason=f"GRW score={scores[sym]:.2f} ({regime})",
                    order_type="market",
                ))

        return signals
