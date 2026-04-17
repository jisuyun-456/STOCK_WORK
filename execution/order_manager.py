"""Order Manager — translates Signals into Alpaca orders and tracks fills.

Responsibilities:
  - Convert Signal objects to Alpaca order requests
  - Generate unique client_order_id for strategy attribution
  - Submit orders and track status
  - Append results to trade_log.jsonl
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from strategies.base_strategy import Signal, Direction
from execution.alpaca_client import (
    get_account_info,
    get_positions,
    submit_market_order,
    submit_limit_order,
    get_order_by_client_id,
)

TRADE_LOG_PATH = Path(__file__).parent.parent / "state" / "trade_log.jsonl"


def _next_seq(strategy: str, symbol: str, date_str: str) -> str:
    """Generate next sequence number for client_order_id."""
    prefix = f"{strategy}-{date_str}-{symbol}"
    seq = 1

    if TRADE_LOG_PATH.exists():
        with open(TRADE_LOG_PATH, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue  # 손상된 라인 스킵
                if entry.get("order_id", "").startswith(prefix):
                    seq += 1

    # Crash-safety: if a previous run submitted the order but was killed before
    # writing to trade_log, Alpaca will still have the order. Bump seq until free.
    from execution.alpaca_client import get_order_by_client_id
    while get_order_by_client_id(f"{prefix}-{seq:03d}") is not None:
        seq += 1

    return f"{prefix}-{seq:03d}"


def execute_signal(
    signal: Signal,
    strategy_capital: float,
    strategy_cash: float,
    dry_run: bool = False,
    current_positions: dict[str, float] | None = None,
) -> dict:
    """Execute a single signal as an Alpaca order.

    Args:
        signal: The trade signal to execute
        strategy_capital: Total allocated capital for this strategy
        strategy_cash: Available cash in this strategy
        dry_run: If True, don't actually submit the order
        current_positions: {symbol: market_value} snapshot for delta BUY sizing.
            If provided, BUY trade_value = max(0, target - existing).

    Returns:
        Dict with execution result
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    order_id = _next_seq(signal.strategy, signal.symbol, date_str)

    # Calculate quantity
    if signal.direction == Direction.BUY:
        target_value = strategy_capital * signal.weight_pct
        existing_mv = (current_positions or {}).get(signal.symbol, 0.0)
        trade_value = max(0.0, target_value - existing_mv)  # delta: 부족분만 매수
        trade_value = min(trade_value, strategy_cash)  # can't exceed available cash

        if trade_value <= 0:
            reason = "already_at_target" if existing_mv >= target_value else "insufficient_cash"
            return _log_result(order_id, signal, "skipped", reason=reason)

        if trade_value < 1.0:
            return _log_result(order_id, signal, "skipped", reason="below_min_notional")

        # For market orders, estimate qty from recent price
        # Alpaca will handle fractional shares
        qty = trade_value  # Use notional for fractional orders

    elif signal.direction == Direction.SELL:
        # Get current position to determine sell quantity
        positions = get_positions()
        pos = next((p for p in positions if p["symbol"] == signal.symbol), None)
        if not pos:
            return _log_result(order_id, signal, "skipped", reason="no_position")
        full_qty = float(pos["qty"])
        # SIM4 fix: weight_pct on SELL = liquidation ratio (0.5=50%, 1.0=100%)
        liquidation_ratio = signal.weight_pct if 0 < signal.weight_pct <= 1.0 else 1.0
        qty = full_qty * liquidation_ratio

    else:
        return _log_result(order_id, signal, "skipped", reason="hold_signal")

    if dry_run:
        if signal.direction == Direction.BUY:
            dry_reason = (
                f"DRY RUN: delta ${trade_value:.2f} "
                f"(target ${target_value:.2f}, existing ${existing_mv:.2f}) of {signal.symbol}"
            )
        else:
            dry_reason = f"DRY RUN: would {signal.direction.value} ~${qty:.2f} of {signal.symbol}"
        return _log_result(order_id, signal, "dry_run", qty=qty, reason=dry_reason)

    # Submit order
    try:
        side = signal.direction.value
        if signal.order_type == "limit" and signal.limit_price:
            result = submit_limit_order(
                symbol=signal.symbol,
                qty=round(qty / signal.limit_price, 4),  # convert notional to shares
                side=side,
                limit_price=signal.limit_price,
                client_order_id=order_id,
            )
        else:
            # Use notional for market orders (Alpaca supports fractional)
            from execution.alpaca_client import get_client
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce

            client = get_client()
            if signal.direction == Direction.BUY:
                request = MarketOrderRequest(
                    symbol=signal.symbol,
                    notional=round(qty, 2),
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=order_id,
                )
            else:
                request = MarketOrderRequest(
                    symbol=signal.symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=order_id,
                )
            order = client.submit_order(request)
            result = {
                "id": str(order.id),
                "client_order_id": order.client_order_id,
                "symbol": order.symbol,
                "side": str(order.side),
                "status": str(order.status),
            }

        # M-3: 부분 체결 확인 — 10초 간격 최대 3회 재시도
        MAX_FILL_RETRIES = 3
        FILL_WAIT_SECONDS = 10
        fill_status = "pending"
        filled_order = None
        try:
            for attempt in range(MAX_FILL_RETRIES):
                time.sleep(FILL_WAIT_SECONDS)
                filled_order = get_order_by_client_id(order_id)
                if not filled_order:
                    continue
                filled_qty = float(filled_order.get("filled_qty", 0))
                if signal.direction == Direction.BUY:
                    # notional 주문 — filled_qty > 0이면 체결됨
                    if filled_qty > 0:
                        fill_status = "filled"
                        break
                else:
                    # SELL — qty 기반 비교
                    requested_qty = qty
                    if filled_qty >= requested_qty:
                        fill_status = "filled"
                        break
                    elif filled_qty > 0:
                        fill_status = "partial_fill"
                        print(
                            f"[ORDER] WARNING: {signal.symbol} 부분 체결 "
                            f"({filled_qty}/{requested_qty} shares)"
                        )
                        break
                if attempt < MAX_FILL_RETRIES - 1:
                    print(f"[ORDER] fill 대기 중... ({attempt + 1}/{MAX_FILL_RETRIES})")

            if fill_status == "pending":
                fill_status = "unfilled"

            if filled_order:
                result["filled_qty"] = float(filled_order.get("filled_qty", 0))
                result["filled_avg_price"] = filled_order.get("filled_avg_price")
        except Exception as fill_err:
            print(f"[ORDER] WARNING: fill 상태 확인 실패 ({fill_err})")
            fill_status = "unknown"

        result["fill_status"] = fill_status
        return _log_result(order_id, signal, fill_status, alpaca_result=result)

    except Exception as e:
        return _log_result(order_id, signal, "error", reason=str(e))


def execute_signals(
    signals: list[Signal],
    strategy_allocations: dict,
    dry_run: bool = False,
) -> list[dict]:
    """Execute a batch of signals.

    Args:
        signals: List of approved signals
        strategy_allocations: Dict of {strategy_code: {capital, cash}}
        dry_run: If True, simulate without real orders

    Returns:
        List of execution results

    Notes:
        C6 fix: 각 BUY 주문 전 Alpaca buying_power 실시간 조회 → 부족 시 skip.
        기존 버그: 전체 배치 제출 → 중간 잔고 소진 → 17/20 주문이 Alpaca
        "insufficient buying power" 에러. 이제는 사전 체크해서 로그만 남기고
        continue.
    """
    results = []

    has_buy = any(s.direction == Direction.BUY for s in signals)

    # BUY delta 계산용 positions 스냅샷 (1회 조회)
    positions_mv: dict[str, float] = {}
    if has_buy:
        try:
            raw_positions = get_positions()
            positions_mv = {p["symbol"]: float(p["market_value"]) for p in raw_positions}
            print(f"  [OM] 포지션 스냅샷 {len(positions_mv)}개 조회")
        except Exception as e:
            print(f"  [OM] WARNING: 포지션 조회 실패 ({e}) — delta 계산 스킵, full target 사용")

    # C6: BUY 주문 있을 때만 Alpaca 잔고 조회 (dry_run 아닌 실거래 시)
    live_buying_power: float | None = None
    if not dry_run and has_buy:
        try:
            account = get_account_info()
            live_buying_power = float(account.get("buying_power", 0) or 0)
            print(f"  [OM] Alpaca buying_power=${live_buying_power:,.2f}")
        except Exception as e:
            print(f"  [OM] WARNING: buying_power 조회 실패 ({e}) — 잔고 체크 스킵")

    for signal in signals:
        alloc = strategy_allocations.get(signal.strategy, {})
        capital = alloc.get("capital", 0)
        cash = alloc.get("cash", 0)

        # C6: BUY 주문 실시간 잔고 확인 (delta 기반으로 수정)
        if signal.direction == Direction.BUY and live_buying_power is not None:
            existing_mv = positions_mv.get(signal.symbol, 0.0)
            trade_value_estimate = max(0.0, capital * signal.weight_pct - existing_mv)
            trade_value_estimate = min(trade_value_estimate, cash)  # strategy cash cap
            # 5% 여유 확보 (수수료·슬리피지·경합 주문 대비)
            if trade_value_estimate > live_buying_power * 0.95:
                skip_entry = _log_result(
                    order_id=_next_seq(
                        signal.strategy, signal.symbol,
                        datetime.now(timezone.utc).strftime("%Y%m%d"),
                    ),
                    signal=signal,
                    status="skipped",
                    reason=(
                        f"insufficient_buying_power: need ${trade_value_estimate:,.0f}, "
                        f"available ${live_buying_power:,.0f}"
                    ),
                )
                print(
                    f"  [OM] SKIP {signal.symbol}: need ${trade_value_estimate:,.0f} > "
                    f"available ${live_buying_power:,.0f}"
                )
                results.append(skip_entry)
                continue
            # 통과 시 로컬 buying_power 차감 (다음 주문 사전 계산용)
            live_buying_power -= trade_value_estimate

        result = execute_signal(signal, capital, cash, dry_run=dry_run, current_positions=positions_mv)
        results.append(result)

        # Deduct cash for buy orders (delta 기준)
        if signal.direction == Direction.BUY and result.get("status") != "skipped":
            existing_mv = positions_mv.get(signal.symbol, 0.0)
            actual_deduction = max(0.0, capital * signal.weight_pct - existing_mv)
            actual_deduction = min(actual_deduction, cash)
            alloc["cash"] = max(0, cash - actual_deduction)

        # LEV 재설계 2026-04-11: SELL 체결 후 strategy_cash 실시간 동기화.
        # 기존 버그: SELL 후 alloc['cash'] 가 갱신되지 않아 동일 사이클 내
        # 리밸런스 BUY 가 insufficient_cash 로 스킵되는 현상. 특히 LEV
        # regime 전환(TQQQ→SQQQ) 시 TQQQ SELL 이 성공해도 SQQQ BUY 가
        # strategy_cash=$0 으로 막힘. 아래 블록은 추정 체결액을 cash 에 가산해
        # 다음 주문이 정상 처리되도록 한다. 실제 fill 가격과 오차는 다음 사이클
        # _sync_alpaca_positions 로 보정됨.
        if signal.direction == Direction.SELL and result.get("status") not in (
            "skipped", "error",
        ):
            # 추정 청산 금액: dry_run 이면 result.qty(=추정 notional), 실거래이면
            # execute_signal 의 로그에 qty 가 없으므로 capital × weight_pct 로 근사.
            est_proceeds = 0.0
            if dry_run:
                # dry_run: _log_result 가 qty 를 저장하지 않으므로 reason 에 적힌 금액 추정 불가
                # → capital × weight_pct × (현재 포지션 기준 가중치)
                # 간단 근사: capital × weight_pct (SELL weight_pct 는 청산 비율이므로
                # 실제 proceeds 는 현재 포지션 가치 × 비율이지만 여기선 capital 기준 상한)
                # 주의: 정확도가 필요하면 execute_signal 이 proceeds 를 반환하도록 개선해야 함.
                est_proceeds = min(capital, capital * signal.weight_pct)
            else:
                alpaca_info = result.get("alpaca", {}) or {}
                filled_qty = float(alpaca_info.get("filled_qty", 0) or 0)
                filled_px = float(alpaca_info.get("filled_avg_price", 0) or 0)
                if filled_qty > 0 and filled_px > 0:
                    est_proceeds = filled_qty * filled_px
                else:
                    # Fallback: capital × weight_pct 로 근사
                    est_proceeds = capital * signal.weight_pct
            if est_proceeds > 0:
                alloc["cash"] = cash + est_proceeds
                print(
                    f"  [OM] SELL {signal.symbol} ({signal.strategy}) "
                    f"→ strategy_cash ${cash:,.2f} → ${alloc['cash']:,.2f} "
                    f"(+${est_proceeds:,.2f})"
                )

    return results


def _log_result(
    order_id: str,
    signal: Signal,
    status: str,
    qty: float = 0,
    reason: str = "",
    alpaca_result: dict | None = None,
) -> dict:
    """Log trade result to trade_log.jsonl and return it."""
    now = datetime.now(timezone.utc)
    entry = {
        "ts": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "order_id": order_id,
        "strategy": signal.strategy,
        "symbol": signal.symbol,
        "side": signal.direction.value,
        "weight_pct": signal.weight_pct,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "status": status,
        "error_reason": reason,
        "qty": qty or None,
        "filled_avg_price": None,
    }
    if alpaca_result:
        entry["alpaca"] = alpaca_result
        # top-level shortcuts for performance_calculator
        if alpaca_result.get("filled_qty"):
            entry["qty"] = float(alpaca_result["filled_qty"])
        if alpaca_result.get("filled_avg_price"):
            entry["filled_avg_price"] = float(alpaca_result["filled_avg_price"])

    # Append to trade log
    TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADE_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())

    return entry
