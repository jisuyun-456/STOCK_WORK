"""Leveraged ETF Strategy — SMA 크로스오버 기반 추세 추종.

Logic:
  1. Universe: QQQ (NASDAQ 100), SPY (S&P 500), SOXX (반도체) 3개 기초지수
  2. 각 기초지수의 SMA50 / SMA200 계산
  3. 골든크로스 (SMA50 > SMA200) → Long ETF (TQQQ/UPRO/SOXL) 매수
  4. 데드크로스 (SMA50 < SMA200) → 현금 보유 (포지션 없음)

Regime 적응:
  - BULL:    ratio > 1.00 이면 매수
  - NEUTRAL: ratio > 1.02 이면 매수 (엄격 기준 적용)
  - BEAR/CRISIS: 모두 현금 (빈 리스트 반환)

인버스 ETF (SQQQ, SPXU, SOXS)는 현재 미사용. 현금 보유가 기본 방어 수단.
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime, timedelta

import yfinance as yf

from strategies.base_strategy import BaseStrategy, Signal, Direction


# ETF 매핑: 기초지수 → Long ETF / Inverse ETF
ETF_MAP = {
    "QQQ":  {"long": "TQQQ", "inverse": "SQQQ"},  # NASDAQ 100 (3x)
    "SPY":  {"long": "UPRO", "inverse": "SPXU"},  # S&P 500 (3x)
    "SOXX": {"long": "SOXL", "inverse": "SOXS"},  # 반도체 (3x)
}

# 데이터 fetch 대상 (기초지수 + Long ETF)
_ALL_TICKERS = ["QQQ", "SPY", "SOXX", "TQQQ", "UPRO", "SOXL"]


def _calc_sma(prices: pd.Series, window: int) -> float:
    """이동평균 계산. 데이터 부족 시 NaN 반환."""
    if len(prices) < window:
        return float("nan")
    return prices.iloc[-window:].mean()


def fetch_leveraged_data(lookback_days: int = 300) -> dict:
    """기초지수 + Long ETF 가격 데이터 fetch.

    yfinance로 QQQ, SPY, SOXX, TQQQ, UPRO, SOXL 다운로드.
    lookback_days=300 (SMA200 계산에 약 280거래일 필요).

    Returns:
        {"prices": DataFrame}  — columns: QQQ, SPY, SOXX, TQQQ, UPRO, SOXL
    """
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    data = yf.download(
        tickers=" ".join(_ALL_TICKERS),
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
    )

    if data.empty:
        return {"prices": pd.DataFrame()}

    # yfinance: 복수 티커 → MultiIndex, 단일 → 단순 columns
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"]
    else:
        prices = data[["Close"]].rename(columns={"Close": _ALL_TICKERS[0]})

    return {"prices": prices}


class LeveragedETFStrategy(BaseStrategy):
    """SMA 크로스오버 기반 레버리지 ETF 추세 추종 전략.

    기초지수(QQQ/SPY/SOXX) SMA50 > SMA200 이면 대응 3x Long ETF 매수.
    Regime이 BEAR/CRISIS이면 전량 현금.
    """

    name = "LEV"
    capital_pct = 0.20
    universe = list(ETF_MAP.keys())  # ["QQQ", "SPY", "SOXX"]
    max_positions = 3
    rebalance_freq = "daily"
    stop_loss_pct = 0.08   # 레버리지라 타이트
    take_profit_pct = 0.15

    regime: str = "NEUTRAL"

    def generate_signals(self, market_data: dict) -> list[Signal]:
        """SMA 크로스오버 기반 레버리지 ETF 매수 시그널 생성.

        Args:
            market_data: 'prices' 키 또는 'leveraged.prices' 키에
                         DataFrame (columns=tickers, index=dates) 포함.

        Returns:
            매수 Signal 리스트. BEAR/CRISIS regime이면 빈 리스트.
        """
        # 데이터 추출 — 두 가지 키 패턴 지원
        prices = market_data.get("prices") or market_data.get("leveraged", {}).get("prices")
        if prices is None or prices.empty:
            print("  LEV: prices 데이터 없음 → 빈 리스트 반환")
            return []

        # BEAR/CRISIS 방어 — regime gateway에서 배분 0% 처리되지만 이중 방어
        if self.regime in ("BEAR", "CRISIS"):
            print(f"  LEV: regime={self.regime}, all positions to CASH")
            return []

        signals: list[Signal] = []

        for base_index, etf_info in ETF_MAP.items():
            if base_index not in prices.columns:
                print(f"  LEV: {base_index} 컬럼 없음 → 스킵")
                continue

            series = prices[base_index].dropna()
            sma50 = _calc_sma(series, 50)
            sma200 = _calc_sma(series, 200)

            # 데이터 부족 또는 SMA200 == 0 방어
            if pd.isna(sma50) or pd.isna(sma200) or sma200 == 0:
                print(
                    f"  LEV: {base_index} SMA 계산 불가 "
                    f"(len={len(series)}, sma50={sma50}, sma200={sma200}) → 스킵"
                )
                continue

            ratio = sma50 / sma200

            # Regime별 매수 임계값
            threshold = 1.02 if self.regime == "NEUTRAL" else 1.00

            print(
                f"  LEV: {base_index} SMA50={sma50:.2f}, SMA200={sma200:.2f}, "
                f"ratio={ratio:.4f}, threshold={threshold}, regime={self.regime} "
                f"→ {'BUY' if ratio > threshold else 'HOLD'}"
            )

            if ratio > threshold:
                long_etf = etf_info["long"]
                # confidence: ratio가 1.0에서 멀수록 높음, 최대 1.0
                confidence = min(1.0, 0.5 + (ratio - 1.0) * 5.0)
                signals.append(Signal(
                    strategy=self.name,
                    symbol=long_etf,
                    direction=Direction.BUY,
                    weight_pct=0.0,  # 이후 등가중으로 재계산
                    confidence=round(confidence, 4),
                    reason=(
                        f"{base_index} SMA50/SMA200={ratio:.4f} > {threshold} "
                        f"→ long {long_etf}"
                    ),
                    order_type="market",
                ))

        # 등가중 배분: 활성 포지션 수에 따라 1/N 할당
        if signals:
            weight = 1.0 / len(signals)
            for s in signals:
                s.weight_pct = round(weight, 6)

        return signals
