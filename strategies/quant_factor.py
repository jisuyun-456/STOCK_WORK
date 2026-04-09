"""Quant Factor Strategy — Fama-French 5-Factor 기반 멀티팩터 종목 선정.

Logic:
  1. Kenneth French 라이브러리에서 Fama-French 5-factor 일별 데이터 다운로드
  2. 각 종목의 일별 초과수익률 계산 (yfinance)
  3. Rolling 60일 OLS 회귀로 factor exposure (beta) 추정:
     Ri - Rf = α + β_mkt*(Mkt-RF) + β_smb*SMB + β_hml*HML + β_rmw*RMW + β_cma*CMA + ε
  4. 레짐별 팩터 가중치로 복합 점수 계산 후 상위 20종목 등가중 매수
  5. MOM factor는 12-1 momentum으로 직접 계산 (yfinance 가격)

References:
  - Fama & French (2015) "A five-factor asset pricing model"
  - Carhart (1997) "On Persistence in Mutual Fund Performance" (momentum)
  - Kenneth French Data Library: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy, Signal, Direction

# pandas_datareader: Kenneth French 팩터 데이터 다운로드용
try:
    import pandas_datareader.data as web
    _PDRWEB_AVAILABLE = True
except ImportError:
    _PDRWEB_AVAILABLE = False
    print("[QNT] WARNING: pandas_datareader 미설치 — FF5 팩터 비활성화, MOM 전용 모드로 동작")


# Russell 1000 대표 종목 (상위 80개 — 계산 효율 최적화)
RUSSELL_1000_SUBSET = [
    # 대형 기술주
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AVGO", "ORCL", "CRM", "AMD",
    "INTC", "CSCO", "TXN", "QCOM", "AMAT", "ADI", "LRCX", "MU", "KLAC", "MRVL",
    # 금융
    "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "C", "USB", "PNC",
    # 헬스케어
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "PFE", "ABT", "AMGN", "GILD",
    # 소비재
    "WMT", "COST", "HD", "MCD", "NKE", "SBUX", "TJX", "LOW", "TGT", "DG",
    # 산업재
    "CAT", "HON", "UNP", "RTX", "GE", "DE", "BA", "LMT", "FDX", "MMM",
    # 에너지
    "XOM", "CVX", "COP", "SLB", "EOG", "PSX", "MPC", "VLO", "OXY", "HAL",
    # 유틸리티/통신
    "NEE", "DUK", "SO", "AEP", "D", "VZ", "T", "TMUS", "CCI", "AMT",
]

# 레짐별 팩터 가중치 (합계 = 1.0)
# 컬럼 순서: HML, SMB, RMW, CMA, MOM
REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "NEUTRAL": {"HML": 0.25, "SMB": 0.15, "RMW": 0.25, "CMA": 0.20, "MOM": 0.15},
    "CRISIS":  {"HML": 0.20, "SMB": 0.05, "RMW": 0.40, "CMA": 0.25, "MOM": 0.10},
    "BULL":    {"HML": 0.20, "SMB": 0.20, "RMW": 0.20, "CMA": 0.15, "MOM": 0.25},
    "BEAR":    {"HML": 0.25, "SMB": 0.05, "RMW": 0.35, "CMA": 0.25, "MOM": 0.10},
}


# ---------------------------------------------------------------------------
# 헬퍼: OLS 회귀 (numpy 전용, statsmodels 불필요)
# ---------------------------------------------------------------------------

def _ols_factor_exposure(
    stock_returns: np.ndarray,
    factor_matrix: np.ndarray,
) -> np.ndarray:
    """최소자승법으로 factor beta 추정.

    Args:
        stock_returns: (N,) 일별 초과수익률 (Ri - Rf)
        factor_matrix: (N, 5) — [Mkt-RF, SMB, HML, RMW, CMA] 순서

    Returns:
        (6,) — [alpha, beta_mkt, beta_smb, beta_hml, beta_rmw, beta_cma]
        데이터 부족 또는 특이행렬 시 zeros 반환
    """
    N = len(stock_returns)
    if N < 10 or factor_matrix.shape[0] != N:
        return np.zeros(6)

    # 상수항(intercept) 추가
    X = np.column_stack([np.ones(N), factor_matrix])  # (N, 6)

    try:
        betas, _, _, _ = np.linalg.lstsq(X, stock_returns, rcond=None)
    except np.linalg.LinAlgError:
        return np.zeros(6)

    return betas  # [alpha, beta_mkt, beta_smb, beta_hml, beta_rmw, beta_cma]


# ---------------------------------------------------------------------------
# 헬퍼: 12-1 모멘텀 계산
# ---------------------------------------------------------------------------

def _calc_momentum(prices: pd.DataFrame, symbol: str) -> float:
    """12-1 모멘텀 계산 (Jegadeesh & Titman 방식).

    Args:
        prices: 일별 종가 DataFrame (columns=symbols, index=dates)
        symbol: 계산 대상 심볼

    Returns:
        mom_12_1 스코어. 데이터 부족(252거래일 미만) 시 0.0 반환.
    """
    if symbol not in prices.columns:
        return 0.0

    series = prices[symbol].dropna()

    if len(series) < 252:
        return 0.0

    price_12m_ago = series.iloc[-252]
    price_1m_ago = series.iloc[-21]

    if price_12m_ago <= 0 or price_1m_ago <= 0:
        return 0.0

    return float((price_1m_ago / price_12m_ago) - 1.0)


# ---------------------------------------------------------------------------
# 데이터 수집
# ---------------------------------------------------------------------------

def fetch_factor_data(
    universe: list[str] | None = None,
    lookback_days: int = 400,
) -> dict:
    """Kenneth French 5-factor + 종목 가격 데이터 수집.

    Args:
        universe: 종목 리스트. None이면 RUSSELL_1000_SUBSET 사용.
        lookback_days: 캘린더 일 수 (400일 ≈ 280거래일 > 252거래일 필요치).

    Returns:
        {
            "prices":  DataFrame — 일별 종가 (columns=symbols, index=dates),
            "factors": DataFrame — 일별 팩터 수익률 (columns=['Mkt-RF','SMB','HML','RMW','CMA','RF']),
                       FF5 다운로드 실패 시 빈 DataFrame
        }
    """
    tickers = universe or RUSSELL_1000_SUBSET
    end = datetime.now()
    start = end - timedelta(days=lookback_days)

    # --- 종목 가격 (yfinance) ---
    print(f"[QNT] 가격 데이터 다운로드 중: {len(tickers)}개 종목, {lookback_days}일")
    raw = yf.download(
        tickers=" ".join(tickers),
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
    )

    if raw.empty:
        print("[QNT] ERROR: yfinance 가격 데이터 없음")
        return {"prices": pd.DataFrame(), "factors": pd.DataFrame()}

    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[["Close"]].rename(columns={"Close": tickers[0]})

    # --- Kenneth French FF5 팩터 ---
    factors = pd.DataFrame()
    if _PDRWEB_AVAILABLE:
        try:
            print("[QNT] Kenneth French FF5 일별 팩터 다운로드 중...")
            ff5_raw = web.DataReader(
                "F-F_Research_Data_5_Factors_2x3_daily",
                "famafrench",
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            # ff5_raw[0]: DataFrame with columns Mkt-RF, SMB, HML, RMW, CMA, RF
            factors = ff5_raw[0] / 100.0  # % → 소수 변환
            # 인덱스가 Period 타입일 경우 DatetimeIndex로 변환
            if hasattr(factors.index, "to_timestamp"):
                factors.index = factors.index.to_timestamp()
            factors.index = pd.to_datetime(factors.index)
            print(f"[QNT] FF5 팩터 다운로드 완료: {len(factors)}일치 데이터")
        except Exception as e:
            print(f"[QNT] WARNING: FF5 팩터 다운로드 실패 ({e}) — MOM 전용 모드로 폴백")
            factors = pd.DataFrame()
    else:
        print("[QNT] pandas_datareader 없음 — MOM 전용 모드로 동작")

    return {"prices": prices, "factors": factors}


# ---------------------------------------------------------------------------
# 전략 클래스
# ---------------------------------------------------------------------------

class QuantFactorStrategy(BaseStrategy):
    """Fama-French 5-Factor 기반 멀티팩터 종목 선정 전략.

    레짐(NEUTRAL/CRISIS/BULL/BEAR)에 따라 팩터 가중치를 동적으로 조정하여
    상위 20종목을 등가중 매수한다.
    """

    name = "QNT"
    capital_pct = 0.30
    universe = RUSSELL_1000_SUBSET
    max_positions = 20
    rebalance_freq = "monthly"
    stop_loss_pct = 0.10
    take_profit_pct = 0.20

    # 현재 시장 레짐 — 외부에서 주입 또는 기본값 NEUTRAL
    regime: str = "NEUTRAL"

    # OLS 회귀 윈도우 (거래일)
    OLS_WINDOW: int = 60

    def generate_signals(self, market_data: dict) -> list[Signal]:
        """멀티팩터 점수 기반 매수 신호 생성.

        Args:
            market_data: {
                "prices":  DataFrame — 일별 종가 (columns=symbols, index=dates),
                "factors": DataFrame — FF5 일별 팩터 수익률 (선택적),
            }

        Returns:
            상위 max_positions개 종목의 BUY Signal 리스트. 데이터 부족 시 빈 리스트.
        """
        # QNT 전용 가격 우선 사용, 없으면 공통 prices로 폴백
        prices: pd.DataFrame = market_data.get("qnt_prices") or market_data.get("prices", pd.DataFrame())
        factors: pd.DataFrame = market_data.get("factors", pd.DataFrame())

        if prices is None or prices.empty:
            print("[QNT] ERROR: 가격 데이터 없음 — 신호 없음")
            return []

        regime = self.regime if self.regime in REGIME_WEIGHTS else "NEUTRAL"
        weights = REGIME_WEIGHTS[regime]
        print(f"[QNT] 레짐={regime}, 팩터 가중치={weights}")

        use_ff5 = not factors.empty
        if not use_ff5:
            print("[QNT] FF5 팩터 없음 — MOM 전용 스코어링")

        # prices와 factors를 날짜 기준으로 정렬
        prices = prices.sort_index()
        if use_ff5:
            factors = factors.sort_index()

        composite_scores: dict[str, float] = {}
        skipped = 0

        for symbol in self.universe:
            if symbol not in prices.columns:
                skipped += 1
                continue

            price_series = prices[symbol].dropna()

            # --- MOM factor (12-1 모멘텀, 직접 계산) ---
            mom_score = _calc_momentum(prices, symbol)

            if use_ff5:
                # OLS 회귀로 팩터 beta 추정
                betas = self._estimate_factor_betas(
                    price_series=price_series,
                    factors=factors,
                )
                if betas is None:
                    skipped += 1
                    continue

                # betas: [alpha, beta_mkt, beta_smb, beta_hml, beta_rmw, beta_cma]
                beta_smb = betas[2]
                beta_hml = betas[3]
                beta_rmw = betas[4]
                beta_cma = betas[5]
            else:
                # FF5 없음: 모든 beta를 0으로, MOM만 사용
                beta_smb = 0.0
                beta_hml = 0.0
                beta_rmw = 0.0
                beta_cma = 0.0

            # 복합 점수 계산
            score = (
                weights["HML"] * beta_hml
                + weights["SMB"] * beta_smb
                + weights["RMW"] * beta_rmw
                + weights["CMA"] * beta_cma
                + weights["MOM"] * mom_score
            )
            composite_scores[symbol] = score

        print(
            f"[QNT] 스코어 계산 완료: 유효 {len(composite_scores)}개 종목, "
            f"스킵 {skipped}개 종목"
        )

        if not composite_scores:
            return []

        # 상위 max_positions개 선택 (음수 스코어도 포함)
        ranked = sorted(
            composite_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:self.max_positions]

        if not ranked:
            return []

        # 점수 정규화 → confidence 계산 (0.0 ~ 1.0)
        scores_arr = np.array([s for _, s in ranked])
        score_min = scores_arr.min()
        score_max = scores_arr.max()
        score_range = score_max - score_min

        # 등가중
        target_weight = 1.0 / len(ranked)

        signals: list[Signal] = []
        for symbol, score in ranked:
            # normalized_score: 0.0(최저) ~ 1.0(최고)
            if score_range > 0:
                normalized = (score - score_min) / score_range
            else:
                normalized = 0.5

            confidence = 0.5 + normalized * 0.5  # 0.5 ~ 1.0

            signals.append(Signal(
                strategy=self.name,
                symbol=symbol,
                direction=Direction.BUY,
                weight_pct=target_weight,
                confidence=round(confidence, 4),
                reason=(
                    f"regime={regime}, composite={score:.4f}, "
                    f"mom={_calc_momentum(prices, symbol):.2%}"
                ),
                order_type="market",
            ))

        print(f"[QNT] 최종 신호: {len(signals)}개 종목 BUY")
        return signals

    def _estimate_factor_betas(
        self,
        price_series: pd.Series,
        factors: pd.DataFrame,
    ) -> np.ndarray | None:
        """Rolling OLS로 Fama-French 5-factor beta 추정.

        Args:
            price_series: 종목 일별 종가 Series (index=dates)
            factors: FF5 팩터 DataFrame (columns=['Mkt-RF','SMB','HML','RMW','CMA','RF'])

        Returns:
            (6,) ndarray — [alpha, beta_mkt, beta_smb, beta_hml, beta_rmw, beta_cma]
            데이터 부족 시 None 반환
        """
        if len(price_series) < self.OLS_WINDOW + 1:
            return None

        # 일별 수익률 계산
        stock_ret = price_series.pct_change().dropna()

        # factors와 날짜 정렬 (inner join)
        aligned = stock_ret.to_frame("ret").join(factors, how="inner").dropna()

        if len(aligned) < self.OLS_WINDOW:
            return None

        # 최근 OLS_WINDOW 거래일만 사용
        window_data = aligned.iloc[-self.OLS_WINDOW:]

        rf = window_data["RF"].values if "RF" in window_data.columns else np.zeros(len(window_data))

        # 초과수익률 (Ri - Rf)
        excess_ret = window_data["ret"].values - rf

        # 팩터 행렬 (N, 5) — Mkt-RF, SMB, HML, RMW, CMA
        factor_cols = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
        missing_cols = [c for c in factor_cols if c not in window_data.columns]
        if missing_cols:
            return None

        factor_matrix = window_data[factor_cols].values

        betas = _ols_factor_exposure(excess_ret, factor_matrix)
        return betas
