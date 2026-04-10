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
                entry = json.loads(line.strip())
                if entry.get("order_id", "").startswith(prefix):
                    seq += 1

    return f"{prefix}-{seq:03d}"


def execute_signal(
    signal: Signal,
    strategy_capital: float,
    strategy_cash: float,
    dry_run: bool = False,
) -> dict:
    """Execute a single signal as an Alpaca order.

    Args:
        signal: The trade signal to execute
        strategy_capital: Total allocated capital for this strategy
        strategy_cash: Available cash in this strategy
        dry_run: If True, don't actually submit the order

    Returns:
        Dict with execution result
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    order_id = _next_seq(signal.strategy, signal.symbol, date_str)

    # Calculate quantity
    if signal.direction == Direction.BUY:
        trade_value = strategy_capital * signal.weight_pct
        trade_value = min(trade_value, strategy_cash)  # can't exceed available cash

        if trade_value <= 0:
            return _log_result(order_id, signal, "skipped", reason="insufficient_cash")

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
        return _log_result(
            order_id, signal, "dry_run",
            qty=qty, reason=f"DRY RUN: would {signal.direction.value} ~${qty:.2f} of {signal.symbol}",
        )

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

        # M-3: 부분 체결 확인 — 3초 대기 후 fill 상태 검증
        fill_status = "pending"
        try:
            time.sleep(3)
            filled_order = get_order_by_client_id(order_id)
            if filled_order:
                filled_qty = float(filled_order.get("filled_qty", 0))
                if signal.direction == Direction.BUY:
                    # notional 주문 — filled_qty > 0이면 체결됨
                    if filled_qty > 0:
                        fill_status = "filled"
                    else:
                        fill_status = "unfilled"
                else:
                    # SELL — qty 기반 비교
                    requested_qty = qty
                    if filled_qty >= requested_qty:
                        fill_status = "filled"
                    elif filled_qty > 0:
                        fill_status = "partial_fill"
                        print(
                            f"[ORDER] WARNING: {signal.symbol} 부분 체결 "
                            f"({filled_qty}/{requested_qty} shares)"
                        )
                    else:
                        fill_status = "unfilled"
                result["filled_qty"] = filled_qty
                result["filled_avg_price"] = filled_order.get("filled_avg_price")
        except Exception as fill_err:
            print(f"[ORDER] WARNING: fill 상태 확인 실패 ({fill_err})")
            fill_status = "unknown"

        result["fill_status"] = fill_status
        return _log_result(order_id, signal, "submitted", alpaca_result=result)

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

    # C6: BUY 주문 있을 때만 Alpaca 잔고 조회 (dry_run 아닌 실거래 시)
    live_buying_power: float | None = None
    if not dry_run and any(s.direction == Direction.BUY for s in signals):
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

        # C6: BUY 주문 실시간 잔고 확인
        if signal.direction == Direction.BUY and live_buying_power is not None:
            trade_value_estimate = capital * signal.weight_pct
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

        result = execute_signal(signal, capital, cash, dry_run=dry_run)
        results.append(result)

        # Deduct cash for buy orders
        if signal.direction == Direction.BUY and result.get("status") != "skipped":
            trade_value = capital * signal.weight_pct
            alloc["cash"] = max(0, cash - trade_value)

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
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "order_id": order_id,
        "strategy": signal.strategy,
        "symbol": signal.symbol,
        "side": signal.direction.value,
        "weight_pct": signal.weight_pct,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "status": status,
        "error_reason": reason,
    }
    if alpaca_result:
        entry["alpaca"] = alpaca_result

    # Append to trade log
    TRADE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADE_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")

    return entry
