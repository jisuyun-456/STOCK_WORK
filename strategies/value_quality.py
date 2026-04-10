"""Value Quality Strategy — P/E + ROE + FCF Yield 기반 가치주 선정.

Logic:
  1. Universe: S&P 500 상위 100개 대형주 (FMP 무료 티어 250건/일 제약 내 수용)
  2. Fundamentals: FMP API 우선, 실패 시 yfinance fallback
  3. Filter by regime:
     - NEUTRAL: P/E < 20 AND ROE > 12% AND FCF Yield > 4%
     - CRISIS:  P/E < 15 AND ROE > 15% AND FCF Yield > 6%
     - BULL:    P/E < 25 AND ROE > 10% AND FCF Yield > 3%
     - BEAR:    P/E < 18 AND ROE > 13% AND FCF Yield > 5%
  4. Composite score = (1/PE) * 0.4 + ROE * 0.3 + FCF_Yield * 0.3
  5. Top max_positions by score → equal-weight BUY signals
  6. Quarterly rebalance

References:
  - Fama & French (1992) "The Cross-Section of Expected Stock Returns"
  - Piotroski (2000) "Value Investing: F-Score"
  - Graham & Dodd "Security Analysis"
"""

from __future__ import annotations

import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy, Signal, Direction


# S&P 500 유니버스 (상위 100개 대형주 — FMP 무료 티어 250건/일 제약 내 수용)
SP500_TOP100 = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "LLY", "TSM", "AVGO",
    "JPM", "V", "UNH", "XOM", "MA", "COST", "JNJ", "HD", "PG", "ABBV",
    "MRK", "CRM", "ORCL", "BAC", "CVX", "NFLX", "AMD", "KO", "PEP", "TMO",
    "LIN", "ACN", "MCD", "ABT", "CSCO", "WMT", "PM", "DIS", "DHR", "INTC",
    "NEE", "TXN", "VZ", "QCOM", "UNP", "RTX", "LOW", "INTU", "HON", "IBM",
    "GE", "CAT", "BA", "AMGN", "SPGI", "AMAT", "DE", "GS", "BLK", "SYK",
    "LMT", "ADP", "MDT", "ADI", "REGN", "ISRG", "BKNG", "GILD", "VRTX", "LRCX",
    "MMC", "PANW", "SBUX", "TJX", "CI", "CB", "PLD", "CME", "MO", "SO",
    "CL", "EOG", "ZTS", "SLB", "BSX", "SCHW", "DUK", "ICE", "APD", "WM",
    "FDX", "MCK", "NOC", "PNC", "AEP", "SHW", "CCI", "USB", "EMR", "GD",
]

FMP_API_KEY = os.environ.get("FMP_API_KEY", "")

# Regime별 필터 기준
REGIME_FILTERS: dict[str, dict[str, float]] = {
    "NEUTRAL": {"max_pe": 20.0, "min_roe": 0.12, "min_fcf_yield": 0.04},
    "CRISIS":  {"max_pe": 15.0, "min_roe": 0.15, "min_fcf_yield": 0.06},
    "BULL":    {"max_pe": 25.0, "min_roe": 0.10, "min_fcf_yield": 0.03},
    "BEAR":    {"max_pe": 18.0, "min_roe": 0.13, "min_fcf_yield": 0.05},
}


# ---------------------------------------------------------------------------
# Data fetch helpers
# ---------------------------------------------------------------------------

def _fetch_fmp_profile(symbol: str) -> dict | None:
    """FMP /profile endpoint에서 재무 데이터 조회. API 키 없으면 None 반환."""
    if not FMP_API_KEY:
        return None
    url = (
        f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        f"?apikey={FMP_API_KEY}"
    )
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data and isinstance(data, list):
            return data[0]
    except Exception:
        pass
    return None


def _fetch_yf_fundamentals(symbol: str) -> dict | None:
    """yfinance .info에서 재무 데이터 조회. FMP 실패 시 fallback."""
    try:
        info = yf.Ticker(symbol).info
        pe = info.get("trailingPE") or info.get("forwardPE")
        roe = info.get("returnOnEquity")
        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        fcf_yield = (fcf / mcap) if (fcf and mcap and mcap > 0) else None
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0.0

        if pe is not None and roe is not None:
            return {
                "pe": float(pe),
                "roe": float(roe),
                "fcf_yield": float(fcf_yield) if fcf_yield is not None else 0.0,
                "price": float(price),
            }
    except Exception:
        pass
    return None


def fetch_value_data(universe: list[str] | None = None) -> dict:
    """FMP API로 재무 데이터 조회 + yfinance 가격 데이터.

    FMP API: https://financialmodelingprep.com/api/v3/profile/{symbol}?apikey={key}
    - forwardPE, returnOnEquity, freeCashFlowPerShare, marketCap, price

    FMP_API_KEY 환경변수 없으면 → yfinance .info fallback:
    - trailingPE (또는 forwardPE)
    - returnOnEquity
    - freeCashflow / marketCap (FCF Yield 계산)

    Returns:
        {
            "prices": DataFrame (index=dates, columns=symbols),
            "fundamentals": {
                "AAPL": {"pe": 28.5, "roe": 0.165, "fcf_yield": 0.038, "price": 185.0},
                ...
            }
        }
    """
    tickers = universe or SP500_TOP100
    fundamentals: dict[str, dict] = {}

    fmp_ok = 0
    fmp_fail = 0
    yf_ok = 0
    yf_fail = 0

    for symbol in tickers:
        fund = None

        # --- FMP 우선 ---
        profile = _fetch_fmp_profile(symbol)
        if profile:
            pe = profile.get("pe")
            roe = profile.get("roe")  # 일부 엔드포인트에서는 없을 수 있음
            # FMP profile에는 returnOnEquity 직접 없음 → ratios endpoint가 더 정확하지만
            # 무료 티어에서는 profile.pe + yfinance roe 혼용
            price = profile.get("price") or 0.0

            if pe and pe > 0:
                # ROE / FCF Yield는 yfinance로 보완
                yf_data = _fetch_yf_fundamentals(symbol)
                if yf_data:
                    fund = {
                        "pe": float(pe),
                        "roe": yf_data["roe"],
                        "fcf_yield": yf_data["fcf_yield"],
                        "price": float(price) or yf_data["price"],
                    }
                    fmp_ok += 1
                else:
                    fmp_fail += 1
            else:
                fmp_fail += 1

        # --- yfinance fallback ---
        if fund is None:
            yf_data = _fetch_yf_fundamentals(symbol)
            if yf_data:
                fund = yf_data
                yf_ok += 1
            else:
                yf_fail += 1

        if fund:
            fundamentals[symbol] = fund

    total_ok = fmp_ok + yf_ok
    total_fail = fmp_fail + yf_fail
    print(
        f"[VAL] fetch_value_data: {total_ok}개 성공 (FMP={fmp_ok}, yf={yf_ok}), "
        f"{total_fail}개 실패"
    )

    # --- 가격 데이터 (최근 30일, 당일 가격 확인용) ---
    end = datetime.now()
    start = end - timedelta(days=35)
    try:
        raw = yf.download(
            " ".join(tickers),
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
        )
        if not raw.empty:
            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw["Close"]
            else:
                prices = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            prices = pd.DataFrame()
    except Exception:
        prices = pd.DataFrame()

    return {"prices": prices, "fundamentals": fundamentals}


# ---------------------------------------------------------------------------
# Strategy class
# ---------------------------------------------------------------------------

class ValueQualityStrategy(BaseStrategy):
    """P/E + ROE + FCF Yield 복합 점수 기반 가치주 선정 전략.

    Quarterly rebalance. Regime에 따라 필터 기준 동적 조정.
    """

    name = "VAL"
    capital_pct = 0.25
    universe = SP500_TOP100
    max_positions = 15
    rebalance_freq = "quarterly"
    stop_loss_pct = 0.10
    take_profit_pct = 0.20

    # run_cycle.py에서 주입. NEUTRAL / CRISIS / BULL / BEAR
    regime: str = "NEUTRAL"

    def generate_signals(self, market_data: dict, current_positions: dict | None = None) -> list[Signal]:
        """P/E + ROE + FCF Yield 기반 복합 점수로 매수/매도 시그널 생성.

        Args:
            market_data: fetch_value_data()의 반환값.
                - 'prices': DataFrame (가격, 참조용)
                - 'fundamentals': {symbol: {"pe", "roe", "fcf_yield", "price"}}
            current_positions: Dict of {symbol: {qty, current, ...}} for SELL signal generation.

        Returns:
            List of Signal (BUY + SELL).
        """
        fundamentals: dict[str, dict] = market_data.get("fundamentals", {})
        if not fundamentals:
            print("[VAL] fundamentals 데이터 없음 — 빈 시그널 반환")
            return []

        # Regime 필터 기준 선택
        regime = self.regime.upper()
        filters = REGIME_FILTERS.get(regime, REGIME_FILTERS["NEUTRAL"])
        max_pe = filters["max_pe"]
        min_roe = filters["min_roe"]
        min_fcf_yield = filters["min_fcf_yield"]

        print(
            f"[VAL] Regime={regime} | 필터: P/E<{max_pe}, ROE>{min_roe:.0%}, "
            f"FCFYield>{min_fcf_yield:.0%}"
        )

        # --- 1단계: 필터링 + 복합 점수 계산 ---
        candidates: dict[str, dict] = {}

        for symbol in self.universe:
            fund = fundamentals.get(symbol)
            if fund is None:
                continue

            pe = fund.get("pe")
            roe = fund.get("roe")
            fcf_yield = fund.get("fcf_yield", 0.0)

            # 필수 데이터 누락 제외
            if pe is None or roe is None:
                continue

            # 적자 기업(P/E 음수) 제외
            if pe <= 0:
                continue

            # Regime 필터 적용
            if pe > max_pe:
                continue
            if roe < min_roe:
                continue
            if fcf_yield < min_fcf_yield:
                continue

            # 복합 점수 = (1/PE)*0.4 + ROE*0.3 + FCF_Yield*0.3
            score = (1.0 / pe) * 0.4 + roe * 0.3 + fcf_yield * 0.3

            candidates[symbol] = {
                "pe": pe,
                "roe": roe,
                "fcf_yield": fcf_yield,
                "price": fund.get("price", 0.0),
                "score": score,
            }

        # ── SELL signals for holdings that no longer pass regime filters ──
        sell_signals: list[Signal] = []
        if current_positions:
            for symbol in list(current_positions.keys()):
                fund = fundamentals.get(symbol)
                should_sell = False
                sell_reason = ""

                if fund is None:
                    should_sell = True
                    sell_reason = "no fundamentals data available"
                else:
                    pe = fund.get("pe", 0)
                    roe = fund.get("roe", 0)
                    fcf_yield = fund.get("fcf_yield", 0)
                    if pe <= 0 or pe > max_pe:
                        should_sell = True
                        sell_reason = f"P/E={pe:.1f} > {max_pe}" if pe > 0 else "negative P/E"
                    elif roe < min_roe:
                        should_sell = True
                        sell_reason = f"ROE={roe:.1%} < {min_roe:.0%}"
                    elif fcf_yield < min_fcf_yield:
                        should_sell = True
                        sell_reason = f"FCFYield={fcf_yield:.1%} < {min_fcf_yield:.0%}"

                if should_sell:
                    sell_signals.append(Signal(
                        strategy=self.name,
                        symbol=symbol,
                        direction=Direction.SELL,
                        weight_pct=0.0,
                        confidence=0.9,
                        reason=f"EXIT: {sell_reason} (regime={regime})",
                        order_type="market",
                    ))

        if not candidates:
            print(f"[VAL] Regime={regime} 필터 통과 종목 없음")
            return sell_signals

        # --- 2단계: 점수 상위 max_positions 선택 ---
        ranked = sorted(
            candidates.items(),
            key=lambda x: x[1]["score"],
            reverse=True,
        )[: self.max_positions]

        print(f"[VAL] 필터 통과: {len(candidates)}개 → 상위 {len(ranked)}개 선택")

        # --- 3단계: confidence 정규화 (score → 0.5 ~ 1.0) ---
        scores = [data["score"] for _, data in ranked]
        score_min = min(scores)
        score_max = max(scores)
        score_range = score_max - score_min if score_max > score_min else 1.0

        # 등가중
        target_weight = 1.0 / len(ranked)

        signals: list[Signal] = []
        for symbol, data in ranked:
            normalized = (data["score"] - score_min) / score_range  # 0.0 ~ 1.0
            confidence = 0.5 + normalized * 0.5  # 0.5 ~ 1.0

            signals.append(
                Signal(
                    strategy=self.name,
                    symbol=symbol,
                    direction=Direction.BUY,
                    weight_pct=target_weight,
                    confidence=round(confidence, 4),
                    reason=(
                        f"P/E={data['pe']:.1f}, ROE={data['roe']:.1%}, "
                        f"FCFYield={data['fcf_yield']:.1%}, score={data['score']:.4f}"
                    ),
                    order_type="market",
                )
            )

        return sell_signals + signals
