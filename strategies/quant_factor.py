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

import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

from strategies.base_strategy import BaseStrategy, Signal, Direction

# Kenneth French FF5 일별 팩터 CSV (직접 ZIP 다운로드)
_FF5_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
)


# N-HIGH-3: universe 외부화 — state/universe.json 단일 소스
_UNIVERSE_JSON = Path(__file__).resolve().parent.parent / "state" / "universe.json"

_QNT_FALLBACK = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "AVGO", "ORCL", "CRM", "AMD",
    "JPM", "BAC", "WFC", "UNH", "JNJ", "LLY",
]


def _load_universe(key: str, fallback: list[str]) -> list[str]:
    try:
        data = json.loads(_UNIVERSE_JSON.read_text(encoding="utf-8"))
        tickers = data.get(key)
        if isinstance(tickers, list) and tickers:
            return list(tickers)
        print(f"[quant_factor] WARNING: universe.json 에 {key} 없음 → fallback 사용")
    except (OSError, json.JSONDecodeError) as e:
        print(f"[quant_factor] WARNING: universe.json 로드 실패 ({e}) → fallback 사용")
    return list(fallback)


# Russell 1000 대표 종목 — state/universe.json 에서 로드 (기본 80 종목)
RUSSELL_1000_SUBSET = _load_universe("RUSSELL_1000_SUBSET", _QNT_FALLBACK)

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

    # --- Kenneth French FF5 팩터 (직접 ZIP 다운로드) ---
    factors = pd.DataFrame()
    freq_used = "daily"
    try:
        print("[QNT] Kenneth French FF5 일별 팩터 다운로드 중...")
        resp = requests.get(_FF5_DAILY_URL, timeout=30)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            csv_name = [n for n in zf.namelist() if n.lower().endswith(".csv")][0]
            with zf.open(csv_name) as f:
                raw_text = f.read().decode("utf-8", errors="ignore")

        # CSV 구조: 헤더 텍스트 → 빈줄 → ",Mkt-RF,SMB,HML,RMW,CMA,RF" → 데이터행
        lines = raw_text.splitlines()
        header_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith(",Mkt-RF"):
                header_idx = i
                break

        if header_idx is None:
            raise ValueError("FF5 CSV 헤더행 ',Mkt-RF,...' 찾기 실패")

        # 헤더행 + 데이터행 추출
        csv_lines = [lines[header_idx]]
        for line in lines[header_idx + 1:]:
            stripped = line.strip()
            if not stripped or not stripped[0].isdigit():
                break
            csv_lines.append(stripped)

        factors = pd.read_csv(io.StringIO("\n".join(csv_lines)), index_col=0)
        factors.index = pd.to_datetime(factors.index.astype(str), format="%Y%m%d")
        factors.index.name = "date"
        factors = factors / 100.0  # % → 소수 변환
        factors = factors[
            (factors.index >= pd.Timestamp(start))
            & (factors.index <= pd.Timestamp(end))
        ]
        print(f"[QNT] FF5 팩터 다운로드 완료: {len(factors)}일치 데이터")
    except Exception as e:
        print(f"[QNT] WARNING: FF5 daily 다운로드 실패 ({type(e).__name__}) - MOM 전용 degraded 모드")
        factors = pd.DataFrame()
        freq_used = "daily"

    # N-MEDIUM-2: FF5 staleness 체크
    #   >45일: 경고 로그 (추적 대상)
    #   >90일: degraded 플래그 ON + QNT 시그널 50% 자동 축소 (downstream)
    #   Kenneth French 업데이트 주기는 약 60일 lag — 30일 임계값은 false-positive 발생
    ff5_stale = False
    days_lag = 0
    if not factors.empty:
        max_factor_date = factors.index.max()
        days_lag = (pd.Timestamp.today() - max_factor_date).days
        if days_lag > 90:
            print(
                f"[QNT] CRITICAL: FF5 데이터 {days_lag}일 지연 "
                f"(최신: {max_factor_date.date()}) → degraded 모드 + QNT 시그널 50% 축소"
            )
            ff5_stale = True
        elif days_lag > 45:
            print(
                f"[QNT] WARNING: FF5 데이터 {days_lag}일 지연 "
                f"(최신: {max_factor_date.date()}) — 추적 중, 90일 초과 시 degraded"
            )
        else:
            print(f"[QNT] FF5 최신성 OK: {days_lag}일 지연 (최신: {max_factor_date.date()})")

    return {
        "prices": prices,
        "factors": factors,
        "degraded": factors.empty or ff5_stale,
        "ff5_stale": ff5_stale,
        "ff5_days_lag": days_lag,
        "ff5_last_date": str(factors.index.max().date()) if not factors.empty else None,
        "ff5_freq": freq_used,  # "daily" 또는 "weekly" (RL-3)
    }


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

    def __init__(self) -> None:
        from config.loader import load_strategy_params
        _cfg = load_strategy_params().get("quant_factor", {})
        self.max_positions: int = int(_cfg.get("max_positions", self.__class__.max_positions))
        self.OLS_WINDOW: int = int(_cfg.get("ols_window", self.__class__.OLS_WINDOW))
        self.stop_loss_pct: float = float(_cfg.get("stop_loss_pct", self.__class__.stop_loss_pct))
        self.take_profit_pct: float = float(_cfg.get("take_profit_pct", 0.20))
        self.min_composite_score: float = float(_cfg.get("min_composite_score", 0.01))

    def generate_signals(self, market_data: dict, current_positions: dict | None = None) -> list[Signal]:
        """멀티팩터 점수 기반 매수/매도 신호 생성.

        Args:
            market_data: {
                "prices":  DataFrame — 일별 종가 (columns=symbols, index=dates),
                "factors": DataFrame — FF5 일별 팩터 수익률 (선택적),
            }
            current_positions: Dict of {symbol: {qty, current, ...}} for SELL signal generation.

        Returns:
            BUY + SELL Signal 리스트.
        """
        # QNT 전용 가격 우선 사용, 없으면 공통 prices로 폴백
        qnt_prices = market_data.get("qnt_prices")
        prices: pd.DataFrame = qnt_prices if qnt_prices is not None and not qnt_prices.empty else market_data.get("prices", pd.DataFrame())
        factors: pd.DataFrame = market_data.get("factors", pd.DataFrame())

        if prices is None or prices.empty:
            print("[QNT] ERROR: 가격 데이터 없음 — 신호 없음")
            return []

        regime = self.regime if self.regime in REGIME_WEIGHTS else "NEUTRAL"
        weights = REGIME_WEIGHTS[regime]
        print(f"[QNT] 레짐={regime}, 팩터 가중치={weights}")

        degraded = market_data.get("degraded", factors.empty)
        # N-MEDIUM-2: FF5 30일+ 지연 시 QNT 시그널 가중치 50% 자동 축소
        ff5_stale = bool(market_data.get("ff5_stale", False))
        stale_scale = 0.5 if ff5_stale else 1.0
        use_ff5 = not factors.empty
        if not use_ff5:
            print("[QNT] WARNING: FF5 팩터 없음 — MOM 전용 degraded 모드")
        if ff5_stale:
            print(
                f"[QNT] FF5 stale detected (ff5_days_lag={market_data.get('ff5_days_lag', '?')}) "
                f"— 시그널 weight_pct 50% 축소 적용"
            )

        # prices와 factors를 날짜 기준으로 정렬
        prices = prices.sort_index()
        if use_ff5:
            factors = factors.sort_index()

        composite_scores: dict[str, float] = {}
        skipped = 0

        # H6 fix: 팩터 노출도만 사용 → 노출도 × 최근 팩터 기대수익률.
        # 기존 버그: score = Σ(weight × beta). 팩터 *수익률*이 아니라 *노출도*로
        # 종목을 순위매김해서 단순히 "고베타" 주식이 상위로 올라왔음.
        # 수정: score = Σ(weight × beta × recent_factor_return).
        recent_factor_returns: dict[str, float] = {}
        if use_ff5 and len(factors) >= 60:
            # 최근 60거래일 평균 (daily 팩터 수익률)
            recent = factors.tail(60).mean()
            for col in ["SMB", "HML", "RMW", "CMA"]:
                if col in recent.index:
                    recent_factor_returns[col] = float(recent[col])
            print(
                f"[QNT] 최근 60일 팩터 수익률: "
                f"SMB={recent_factor_returns.get('SMB', 0):+.3%}, "
                f"HML={recent_factor_returns.get('HML', 0):+.3%}, "
                f"RMW={recent_factor_returns.get('RMW', 0):+.3%}, "
                f"CMA={recent_factor_returns.get('CMA', 0):+.3%}"
            )

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

            # H6: 복합 점수 = Σ(regime_weight × beta × recent_factor_return)
            # FF5 없으면 MOM만 사용 (기존 동작 유지).
            if use_ff5 and recent_factor_returns:
                score = (
                    weights["HML"] * beta_hml * recent_factor_returns.get("HML", 0.0)
                    + weights["SMB"] * beta_smb * recent_factor_returns.get("SMB", 0.0)
                    + weights["RMW"] * beta_rmw * recent_factor_returns.get("RMW", 0.0)
                    + weights["CMA"] * beta_cma * recent_factor_returns.get("CMA", 0.0)
                    + weights["MOM"] * mom_score
                )
            else:
                # 폴백: MOM만 사용 (degraded 모드)
                score = weights["MOM"] * mom_score
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

        # min_composite_score 미만 종목 제거 (Variant 파라미터 반영)
        min_score = getattr(self, "min_composite_score", 0.0)
        if min_score > 0:
            ranked = [(sym, s) for sym, s in ranked if s >= min_score]

        if not ranked:
            return []

        # 점수 정규화 → confidence 계산 (0.0 ~ 1.0)
        scores_arr = np.array([s for _, s in ranked])
        score_min = scores_arr.min()
        score_max = scores_arr.max()
        score_range = score_max - score_min

        # 등가중 (max_positions 기준 고정 비중 — len(ranked)로 나누면 필터 후 소수 종목 시
        # risk gate 15% 초과 → 전체 차단. max_positions=20 기준 5% 고정으로 항상 통과)
        target_weight = (1.0 / self.max_positions) * stale_scale

        signals: list[Signal] = []
        for symbol, score in ranked:
            # normalized_score: 0.0(최저) ~ 1.0(최고)
            if score_range > 0:
                normalized = (score - score_min) / score_range
            else:
                normalized = 0.5

            confidence = 0.5 + normalized * 0.5  # 0.5 ~ 1.0

            # FF5 degraded 모드: confidence 20% 감쇠
            if degraded:
                confidence *= 0.8

            reason_prefix = "[DEGRADED] " if degraded else ""
            signals.append(Signal(
                strategy=self.name,
                symbol=symbol,
                direction=Direction.BUY,
                weight_pct=target_weight,
                confidence=round(confidence, 4),
                reason=(
                    f"{reason_prefix}regime={regime}, composite={score:.4f}, "
                    f"mom={_calc_momentum(prices, symbol):.2%}"
                    + (" (FF5 unavailable — MOM-only scoring)" if degraded else "")
                ),
                order_type="market",
            ))

        # ── SELL signals for holdings outside new top-N ──
        sell_signals: list[Signal] = []
        if current_positions:
            top_symbols = {sym for sym, _ in ranked}
            for symbol in list(current_positions.keys()):
                if symbol not in top_symbols:
                    score = composite_scores.get(symbol)
                    reason = f"EXIT: dropped from top-{self.max_positions}"
                    if score is not None:
                        reason += f" (score={score:.4f})"
                    else:
                        reason += " (no score computed)"
                    sell_signals.append(Signal(
                        strategy=self.name,
                        symbol=symbol,
                        direction=Direction.SELL,
                        weight_pct=0.0,
                        confidence=0.9,
                        reason=reason,
                        order_type="market",
                    ))

        print(f"[QNT] 최종 신호: {len(signals)}개 BUY, {len(sell_signals)}개 SELL")
        return sell_signals + signals

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
