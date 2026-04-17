from dataclasses import dataclass
from datetime import datetime


@dataclass
class KRRiskCheckResult:
    passed: bool
    check_name: str
    reason: str


UPPER_LIMIT_PCT = 0.30   # 상한 +30%
LOWER_LIMIT_PCT = -0.30  # 하한 -30%


def check_price_limit(ticker: str, current_price: int, base_price: int) -> KRRiskCheckResult:
    """
    Check if current_price is within ±30% of base_price (한국 주식 가격제한폭).
    base_price is yesterday's closing price.
    If current_price > base_price * 1.30 → fail (at or above upper limit)
    If current_price < base_price * 0.70 → fail (at or below lower limit)
    Otherwise → pass
    """
    upper = base_price * (1 + UPPER_LIMIT_PCT)
    lower = base_price * (1 + LOWER_LIMIT_PCT)

    if current_price > upper:
        return KRRiskCheckResult(
            passed=False,
            check_name="price_limit",
            reason=f"{ticker}: current_price {current_price} exceeds upper limit {upper} (+30% of {base_price})",
        )
    if current_price < lower:
        return KRRiskCheckResult(
            passed=False,
            check_name="price_limit",
            reason=f"{ticker}: current_price {current_price} below lower limit {lower} (-30% of {base_price})",
        )
    return KRRiskCheckResult(
        passed=True,
        check_name="price_limit",
        reason=f"{ticker}: current_price {current_price} within ±30% limit",
    )


def check_trading_halt(ticker: str, halted_tickers: set) -> KRRiskCheckResult:
    """
    If ticker is in halted_tickers → fail.
    Otherwise → pass.
    """
    if ticker in halted_tickers:
        return KRRiskCheckResult(
            passed=False,
            check_name="trading_halt",
            reason=f"{ticker}: trading is currently halted",
        )
    return KRRiskCheckResult(
        passed=True,
        check_name="trading_halt",
        reason=f"{ticker}: no trading halt",
    )


def check_vi_cooldown(ticker: str, vi_active_until: dict, now: datetime = None) -> KRRiskCheckResult:
    """
    VI (Volatility Interruption) cooldown check.
    vi_active_until: dict mapping ticker -> datetime when VI expires.
    If ticker in vi_active_until and now < vi_active_until[ticker] → fail.
    now defaults to datetime.now() if not provided.

    NOTE: All datetimes assumed to be naive KST. Do not mix tz-aware and naive.
    """
    if now is None:
        now = datetime.now()

    if ticker in vi_active_until and now < vi_active_until[ticker]:
        expires_at = vi_active_until[ticker]
        return KRRiskCheckResult(
            passed=False,
            check_name="vi_cooldown",
            reason=f"{ticker}: VI cooldown active until {expires_at} (now={now})",
        )
    return KRRiskCheckResult(
        passed=True,
        check_name="vi_cooldown",
        reason=f"{ticker}: no active VI cooldown",
    )


def check_circuit_breaker(level: int, side: str = "BUY") -> KRRiskCheckResult:
    """
    Korean market circuit breaker levels:
    level 0: normal → pass
    level 1: CB triggered (KOSPI -8%) → BUY blocked, SELL allowed
    level 2: CB triggered (KOSPI -15%) → ALL trades blocked
    level 3: CB triggered (KOSPI -20%) → ALL trades blocked (early close)
    """
    if level == 0:
        return KRRiskCheckResult(
            passed=True,
            check_name="circuit_breaker",
            reason="Circuit breaker level 0: normal trading",
        )
    if level == 1:
        if side.upper() == "BUY":
            return KRRiskCheckResult(
                passed=False,
                check_name="circuit_breaker",
                reason="Circuit breaker level 1 (KOSPI -8%): BUY orders blocked",
            )
        return KRRiskCheckResult(
            passed=True,
            check_name="circuit_breaker",
            reason="Circuit breaker level 1 (KOSPI -8%): SELL orders allowed",
        )
    # level 2 or 3: all trades blocked
    return KRRiskCheckResult(
        passed=False,
        check_name="circuit_breaker",
        reason=f"Circuit breaker level {level} (KOSPI -{15 if level == 2 else 20}%): all trades blocked",
    )


def validate_kr_order(
    ticker: str,
    current_price: int,
    base_price: int,
    halted_tickers: set | None = None,
    vi_active_until: dict | None = None,
    cb_level: int = 0,
    side: str = "BUY",
    now: datetime = None,
) -> tuple:
    """
    Run all KR risk checks. Returns (passed: bool, results: list[KRRiskCheckResult]).
    Runs: price_limit, trading_halt, vi_cooldown, circuit_breaker.
    Uses defaults: halted_tickers=frozenset(), vi_active_until={}
    """
    if halted_tickers is None:
        halted_tickers = frozenset()
    if vi_active_until is None:
        vi_active_until = {}

    results = [
        check_price_limit(ticker, current_price, base_price),
        check_trading_halt(ticker, halted_tickers),
        check_vi_cooldown(ticker, vi_active_until, now=now),
        check_circuit_breaker(cb_level, side=side),
    ]

    passed = all(r.passed for r in results)
    return passed, results
