"""Leveraged ETF Strategy — Core-Satellite Barbell (SPY + TQQQ/SQQQ/BND+GLD).

설계 근거: STOCK/2026-04-11-LEV-Strategy-Brainstorm-Design.md

구조:
  - Core:      SPY 50% (Buy&Hold, CRISIS 제외 항상 유지)
  - Satellite: TQQQ 50% (BULL/NEUTRAL) / SQQQ 50% (BEAR) / BND+GLD (CRISIS)

Regime 적응:
  | Regime  | SPY | TQQQ | SQQQ | BND  | GLD  | Stop-loss | Take-profit |
  |---------|-----|------|------|------|------|-----------|-------------|
  | BULL    | 50% | 50%  | —    | —    | —    | -30%      | +60%        |
  | NEUTRAL | 50% | 50%  | —    | —    | —    | -20%      | +35%        |
  | BEAR    | 50% | —    | 50%  | —    | —    | 즉시 전환 | —           |
  | CRISIS  | —   | —    | —    | 60%  | 40%  | -10%      | —           |

리밸런싱:
  - 현재 가중치가 목표에서 ±10% 이탈하면 자동 리밸런스 신호 생성
  - delta 기반 부분 체결 (delta > 1% allocated) → 과매매 방지
  - 예: SPY 61% / TQQQ 39% → SPY 11%(=$5.5k) SELL + TQQQ 11%(=$5.5k) BUY

Regime 전환:
  - generate_signals() 호출 시 self.regime 과 current_positions 를 비교
  - 포지션에 TQQQ가 있는데 regime=BEAR → TQQQ 전량 SELL + SQQQ 신규 BUY
  - 포지션에 SQQQ가 있는데 regime=BULL/NEUTRAL → SQQQ 전량 SELL + TQQQ 신규 BUY
  - 별도 이벤트 트리거 불필요 — self.regime 주입만으로 자연스럽게 전환

capital 주입:
  - run_cycle.phase_signals() 가 strat.allocated_capital 을 주입
  - generate_signals() 는 allocated_capital 을 기준으로 delta 계산
  - 미주입 시 current_positions 총 market_value 를 폴백 capital 로 사용
"""

from __future__ import annotations

from strategies.base_strategy import BaseStrategy, Signal, Direction


# ─── 설정 상수 ──────────────────────────────────────────────────────────
_CORE_SYMBOL = "SPY"
_LONG_SATELLITE = "TQQQ"      # NASDAQ 3x Long
_INVERSE_SATELLITE = "SQQQ"   # NASDAQ 3x Inverse
_DEFENSIVE_BOND = "BND"        # Vanguard Total Bond (CRISIS 방어)
_DEFENSIVE_GOLD = "GLD"        # SPDR Gold (CRISIS 방어)

# Regime → Target weight mix (sum = 1.0 또는 0.0)
_REGIME_MIX: dict[str, dict[str, float]] = {
    "BULL":    {"SPY": 0.50, "TQQQ": 0.50},
    "NEUTRAL": {"SPY": 0.50, "TQQQ": 0.50},
    "BEAR":    {"SPY": 0.50, "SQQQ": 0.50},
    "CRISIS":  {"BND": 0.60, "GLD": 0.40},  # 전량 현금화 → 방어 포지션 보유
}

# Regime → (stop_loss_pct, take_profit_pct)
# None = 해당 regime 에서는 percentage 기반 손절/익절 무효
_REGIME_EXITS: dict[str, tuple[float | None, float | None]] = {
    "BULL":    (-0.30, +0.60),
    "NEUTRAL": (-0.20, +0.35),
    "BEAR":    (None, None),
    "CRISIS":  (-0.10, None),  # 방어자산도 -10% 손절
}

# ±10% 이탈 시 리밸런스 트리거 (weight 기준)
REBALANCE_BAND = 0.10

# delta 가 allocated 의 1% 미만이면 신호 무시 (noise 제거, 슬리피지 최소화)
MIN_TRADE_FRACTION = 0.01


class LeveragedETFStrategy(BaseStrategy):
    """Core-Satellite Barbell: SPY + TQQQ/SQQQ.

    BaseStrategy 규약:
      - name = "LEV"
      - generate_signals(market_data, current_positions) → list[Signal]
      - self.regime 은 run_cycle.phase_signals() 에서 주입됨
      - self.allocated_capital 은 run_cycle.phase_signals() 에서 주입됨 (신규)
    """

    name = "LEV"
    capital_pct = 0.25  # A/B 테스트: LEV_ST 와 25%씩 분할 (regime_allocator 와 일치)
    universe = [_CORE_SYMBOL, _LONG_SATELLITE, _INVERSE_SATELLITE, _DEFENSIVE_BOND, _DEFENSIVE_GOLD]
    max_positions = 2  # SPY+TQQQ, SPY+SQQQ, BND+GLD 모두 2종목
    rebalance_freq = "daily"

    # BaseStrategy 기본값 유지 (run_cycle._get_strategy_stop_loss 가
    # regime 별로 get_stop_loss_for_regime() 을 호출)
    stop_loss_pct = 0.20
    take_profit_pct = 0.35

    regime: str = "NEUTRAL"
    allocated_capital: float = 0.0  # phase_signals 가 주입 (0 이면 폴백)

    # ─── Regime 기반 exit 헬퍼 (run_cycle 이 직접 호출) ──────────────
    @staticmethod
    def get_stop_loss_for_regime(regime: str) -> float | None:
        """Regime 별 stop-loss 임계값. None = 퍼센티지 기반 손절 미적용."""
        return _REGIME_EXITS.get(regime, _REGIME_EXITS["NEUTRAL"])[0]

    @staticmethod
    def get_take_profit_for_regime(regime: str) -> float | None:
        """Regime 별 take-profit 임계값. None = 퍼센티지 기반 익절 미적용."""
        return _REGIME_EXITS.get(regime, _REGIME_EXITS["NEUTRAL"])[1]

    @staticmethod
    def get_target_mix(regime: str) -> dict[str, float]:
        """Regime 별 목표 자산 배분 (weight_pct, 합 = 1.0 또는 0.0)."""
        return dict(_REGIME_MIX.get(regime, _REGIME_MIX["NEUTRAL"]))

    # ─── 내부 유틸 ─────────────────────────────────────────────────────
    @staticmethod
    def _positions_market_value(current_positions: dict | None) -> dict[str, float]:
        """심볼 → market_value. 음수/0 은 제외."""
        if not current_positions:
            return {}
        out: dict[str, float] = {}
        for sym, pos in current_positions.items():
            v = float(pos.get("market_value", 0) or 0)
            if v > 0:
                out[sym] = v
        return out

    @staticmethod
    def _current_weights(mv: dict[str, float]) -> dict[str, float]:
        """market_value dict → weight dict. 합이 0 이면 빈 dict."""
        total = sum(mv.values())
        if total <= 0:
            return {}
        return {s: v / total for s, v in mv.items()}

    @staticmethod
    def _needs_rebalance(
        current_weights: dict[str, float],
        target_mix: dict[str, float],
    ) -> bool:
        """최대 편차가 REBALANCE_BAND 초과 시 True."""
        symbols = set(current_weights) | set(target_mix)
        for s in symbols:
            diff = abs(current_weights.get(s, 0.0) - target_mix.get(s, 0.0))
            if diff > REBALANCE_BAND:
                return True
        return False

    def _effective_capital(self, mv: dict[str, float]) -> float:
        """리밸런스/delta 계산에 사용할 capital.

        우선순위:
          1. self.allocated_capital (phase_signals 주입값, > 0)
          2. current positions 총 market_value 합 (폴백)
        """
        if self.allocated_capital and self.allocated_capital > 0:
            return float(self.allocated_capital)
        return float(sum(mv.values()))

    # ─── 메인 로직 ─────────────────────────────────────────────────────
    def generate_signals(
        self,
        market_data: dict,
        current_positions: dict | None = None,
    ) -> list[Signal]:
        """Regime 과 current_positions 을 비교해 SELL/BUY 시그널 생성.

        핵심 흐름:
          1. target_mix = _REGIME_MIX[regime]
          2. held_but_not_target → 전량 SELL (regime 전환/CRISIS)
          3. target_but_not_held → 신규 BUY (weight_pct = target_weight)
          4. overlap symbols + 밴드 초과 → delta 기반 부분 SELL/BUY
          5. delta 가 너무 작으면 (< MIN_TRADE_FRACTION × capital) 스킵

        SELL signals are emitted before BUY signals (cash 흐름 보장).
        """
        target_mix = self.get_target_mix(self.regime)
        mv = self._positions_market_value(current_positions)
        current_weights = self._current_weights(mv)
        held_symbols = set(mv.keys())
        target_symbols = set(target_mix.keys())
        capital = self._effective_capital(mv)

        print(
            f"  LEV: regime={self.regime}, capital=${capital:,.2f}, "
            f"target={dict(sorted(target_mix.items()))}, "
            f"current={dict(sorted({k: round(v, 4) for k, v in current_weights.items()}.items()))}"
        )

        sell_signals: list[Signal] = []
        buy_signals: list[Signal] = []

        # ── 1) target 에 없는 보유 심볼 → 전량 SELL ──────────────────
        for sym in sorted(held_symbols - target_symbols):
            reason = (
                f"LEV regime={self.regime}: {sym} not in target "
                f"{sorted(target_mix.keys()) or 'CASH'} → liquidate 100%"
            )
            sell_signals.append(
                Signal(
                    strategy=self.name,
                    symbol=sym,
                    direction=Direction.SELL,
                    weight_pct=1.0,  # 전량 청산 (liquidation_ratio)
                    confidence=0.99,
                    reason=reason,
                    order_type="market",
                )
            )

        # CRISIS 또는 target_mix 가 비어있으면 여기서 종료
        if not target_mix:
            if sell_signals:
                print(f"  LEV: {self.regime} → {len(sell_signals)}개 포지션 전량 청산")
            else:
                print(f"  LEV: {self.regime} → no positions to liquidate (already cash)")
            return sell_signals

        # capital 가 0 이면 그냥 신규 진입 — 첫 사이클 + allocated 주입 안 된 경우
        # (테스트 환경 등). phase_signals 에서 주입되면 이 경로는 피함.
        if capital <= 0:
            print("  LEV: capital=$0 → target weight 기반 신규 진입 신호만 생성")
            for sym in sorted(target_symbols):
                buy_signals.append(
                    Signal(
                        strategy=self.name,
                        symbol=sym,
                        direction=Direction.BUY,
                        weight_pct=round(target_mix[sym], 6),
                        confidence=0.95,
                        reason=f"LEV regime={self.regime}: new entry target={target_mix[sym]:.0%}",
                        order_type="market",
                    )
                )
            return sell_signals + buy_signals

        # ── 2) 신규 진입 + 리밸런스 필요 판정 ──
        new_entries = target_symbols - held_symbols
        overlap = target_symbols & held_symbols
        needs_rebalance = self._needs_rebalance(current_weights, target_mix) if overlap else False
        needs_action = bool(new_entries) or needs_rebalance

        if not needs_action:
            print(f"  LEV: no action (within ±{REBALANCE_BAND:.0%} band)")
            return sell_signals + buy_signals

        # ── 3) delta 계산 + SELL/BUY 시그널 생성 ──
        # target_value = capital × target_weight
        # delta = target_value - current_value
        # delta > 0 → BUY (delta / capital 비율)
        # delta < 0 → SELL (|delta| / current_value 청산 비율)
        min_delta = capital * MIN_TRADE_FRACTION

        for sym in sorted(target_symbols | held_symbols):
            # target 에 없는 held 는 이미 sell_signals 에 들어감
            if sym not in target_symbols:
                continue

            target_weight = target_mix[sym]
            target_value = capital * target_weight
            current_value = mv.get(sym, 0.0)
            delta = target_value - current_value

            # 아주 작은 delta 는 무시 (slippage/noise 방지)
            if abs(delta) < min_delta:
                continue

            if delta > 0:
                # BUY — weight_pct = target_weight (order_manager가 delta 계산)
                reason_tag = "new entry" if sym in new_entries else "rebalance BUY"
                buy_signals.append(
                    Signal(
                        strategy=self.name,
                        symbol=sym,
                        direction=Direction.BUY,
                        weight_pct=round(target_weight, 6),
                        confidence=0.95,
                        reason=(
                            f"LEV regime={self.regime}: {reason_tag} "
                            f"current=${current_value:,.0f} → target=${target_value:,.0f} "
                            f"(Δ=${delta:+,.0f})"
                        ),
                        order_type="market",
                    )
                )
            else:
                # SELL 초과분 — liquidation_ratio = |delta| / current_value
                if current_value <= 0:
                    continue
                liquidation = min(1.0, abs(delta) / current_value)
                sell_signals.append(
                    Signal(
                        strategy=self.name,
                        symbol=sym,
                        direction=Direction.SELL,
                        weight_pct=round(liquidation, 6),
                        confidence=0.95,
                        reason=(
                            f"LEV regime={self.regime}: rebalance SELL "
                            f"current=${current_value:,.0f} → target=${target_value:,.0f} "
                            f"(Δ=${delta:+,.0f}, liquidate={liquidation:.2%})"
                        ),
                        order_type="market",
                    )
                )

        # SELL 먼저 → BUY 나중 (cash 흐름 보장)
        return sell_signals + buy_signals
