"""Pre-trade risk validation — 5 risk gates that every signal must pass.

Gates:
  1. Position limit: single position <= 20% of strategy capital
  2. Sector concentration: sector <= 40% of strategy capital
  3. Portfolio VaR: 95% 1-day VaR <= 3%
  4. Correlation: |corr(new, existing)| <= 0.85
  5. Cash buffer: strategy cash >= 5% after trade
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class RiskCheckResult:
    passed: bool
    check_name: str
    reason: str
    value: Optional[float] = None
    threshold: Optional[float] = None


# ---------- Sector mapping (GICS-like) ----------

SECTOR_MAP: dict[str, str] = {
    # Tech
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "GOOGL": "Technology", "META": "Technology", "AMZN": "Technology",
    "PLTR": "Technology", "APLD": "Technology", "IONQ": "Technology",
    # Healthcare
    "JNJ": "Healthcare", "UNH": "Healthcare", "HIMS": "Healthcare",
    # Space / Industrials
    "RKLB": "Industrials",
    # Leveraged ETFs
    "TQQQ": "ETF-Leveraged", "UPRO": "ETF-Leveraged",
    "SQQQ": "ETF-Leveraged", "SPXU": "ETF-Leveraged",
}


def get_sector(symbol: str) -> str:
    """Get sector for a symbol. Falls back to 'Unknown'."""
    return SECTOR_MAP.get(symbol, "Unknown")


# ---------- Individual risk checks ----------

def check_position_limit(
    symbol: str,
    trade_value: float,
    strategy_capital: float,
    current_positions: dict[str, float],
    max_pct: float = 0.20,
) -> RiskCheckResult:
    """Check that a single position doesn't exceed max_pct of strategy capital."""
    existing_value = current_positions.get(symbol, 0.0)
    new_value = existing_value + trade_value
    weight = new_value / strategy_capital if strategy_capital > 0 else 1.0

    return RiskCheckResult(
        passed=weight <= max_pct,
        check_name="position_limit",
        reason=f"{symbol} weight {weight:.1%} {'<=' if weight <= max_pct else '>'} {max_pct:.0%}",
        value=weight,
        threshold=max_pct,
    )


def check_sector_concentration(
    symbol: str,
    trade_value: float,
    strategy_capital: float,
    current_positions: dict[str, float],
    max_pct: float = 0.40,
) -> RiskCheckResult:
    """Check that sector exposure doesn't exceed max_pct."""
    target_sector = get_sector(symbol)
    sector_value = trade_value

    for sym, val in current_positions.items():
        if get_sector(sym) == target_sector:
            sector_value += val

    weight = sector_value / strategy_capital if strategy_capital > 0 else 1.0

    return RiskCheckResult(
        passed=weight <= max_pct,
        check_name="sector_concentration",
        reason=f"Sector '{target_sector}' weight {weight:.1%} {'<=' if weight <= max_pct else '>'} {max_pct:.0%}",
        value=weight,
        threshold=max_pct,
    )


def check_portfolio_var(
    symbols: list[str],
    weights: list[float],
    max_var: float = 0.03,
    lookback_days: int = 252,
    confidence: float = 0.95,
) -> RiskCheckResult:
    """Parametric VaR check (95% 1-day) for portfolio."""
    if not symbols or not weights:
        return RiskCheckResult(
            passed=True, check_name="portfolio_var",
            reason="Empty portfolio, VaR=0", value=0.0, threshold=max_var,
        )

    try:
        tickers = " ".join(symbols)
        data = yf.download(tickers, period=f"{lookback_days}d", progress=False)

        if len(symbols) == 1:
            returns = data["Close"].pct_change().dropna()
            port_returns = returns * weights[0]
        else:
            returns = data["Close"].pct_change().dropna()
            w = np.array(weights)
            port_returns = returns.dot(w)

        z_score = abs(np.percentile(np.random.standard_normal(10000), (1 - confidence) * 100))
        var_value = float(port_returns.std() * z_score)

        return RiskCheckResult(
            passed=var_value <= max_var,
            check_name="portfolio_var",
            reason=f"VaR(95%, 1d) = {var_value:.2%} {'<=' if var_value <= max_var else '>'} {max_var:.0%}",
            value=var_value,
            threshold=max_var,
        )
    except Exception as e:
        return RiskCheckResult(
            passed=False, check_name="portfolio_var",
            reason=f"VaR calculation failed: {e}",
        )


def check_correlation(
    new_symbol: str,
    existing_symbols: list[str],
    max_corr: float = 0.85,
    lookback_days: int = 60,
) -> RiskCheckResult:
    """Check correlation between new symbol and existing holdings."""
    if not existing_symbols:
        return RiskCheckResult(
            passed=True, check_name="correlation",
            reason="No existing positions to check correlation", value=0.0, threshold=max_corr,
        )

    try:
        all_symbols = [new_symbol] + existing_symbols
        tickers = " ".join(all_symbols)
        data = yf.download(tickers, period=f"{lookback_days}d", progress=False)

        if len(all_symbols) == 2:
            returns = data["Close"].pct_change().dropna()
            corr = float(returns.iloc[:, 0].corr(returns.iloc[:, 1]))
            max_found = abs(corr)
        else:
            returns = data["Close"].pct_change().dropna()
            corr_matrix = returns.corr()
            new_corrs = corr_matrix[new_symbol].drop(new_symbol)
            max_found = float(new_corrs.abs().max())

        return RiskCheckResult(
            passed=max_found <= max_corr,
            check_name="correlation",
            reason=f"Max |corr| with existing = {max_found:.2f} {'<=' if max_found <= max_corr else '>'} {max_corr}",
            value=max_found,
            threshold=max_corr,
        )
    except Exception as e:
        # On data fetch failure, pass with warning
        return RiskCheckResult(
            passed=True, check_name="correlation",
            reason=f"Correlation check skipped (data error): {e}",
        )


def check_cash_buffer(
    trade_cost: float,
    strategy_cash: float,
    strategy_capital: float,
    min_cash_pct: float = 0.05,
) -> RiskCheckResult:
    """Ensure strategy maintains minimum cash buffer after trade."""
    remaining_cash = strategy_cash - trade_cost
    cash_pct = remaining_cash / strategy_capital if strategy_capital > 0 else 0.0

    return RiskCheckResult(
        passed=cash_pct >= min_cash_pct,
        check_name="cash_buffer",
        reason=f"Cash after trade: {cash_pct:.1%} {'>=' if cash_pct >= min_cash_pct else '<'} {min_cash_pct:.0%}",
        value=cash_pct,
        threshold=min_cash_pct,
    )


# ---------- Aggregate validator ----------

def validate_signal(
    symbol: str,
    side: str,
    trade_value: float,
    strategy_capital: float,
    strategy_cash: float,
    current_positions: dict[str, float],
) -> tuple[bool, list[RiskCheckResult]]:
    """Run all 5 risk checks on a proposed trade.

    Args:
        symbol: Ticker to trade
        side: "buy" or "sell"
        trade_value: Dollar value of the trade
        strategy_capital: Total allocated capital for this strategy
        strategy_cash: Available cash in this strategy
        current_positions: Dict of {symbol: market_value} for current holdings

    Returns:
        (all_passed, list of RiskCheckResult)
    """
    results = []

    # For sell orders, only check that we have the position
    if side == "sell":
        has_position = symbol in current_positions and current_positions[symbol] > 0
        results.append(RiskCheckResult(
            passed=has_position,
            check_name="sell_validation",
            reason=f"{'Has' if has_position else 'Missing'} position in {symbol}",
        ))
        return all(r.passed for r in results), results

    # Buy orders: full 5-gate validation
    results.append(check_position_limit(symbol, trade_value, strategy_capital, current_positions))
    results.append(check_sector_concentration(symbol, trade_value, strategy_capital, current_positions))

    # VaR check on the whole portfolio including new position
    all_symbols = list(current_positions.keys())
    if symbol not in all_symbols:
        all_symbols.append(symbol)
    total_value = sum(current_positions.values()) + trade_value
    if total_value > 0:
        weights = [
            (current_positions.get(s, 0) + (trade_value if s == symbol else 0)) / total_value
            for s in all_symbols
        ]
        results.append(check_portfolio_var(all_symbols, weights))
    else:
        results.append(RiskCheckResult(
            passed=True, check_name="portfolio_var", reason="No portfolio value", value=0.0, threshold=0.03,
        ))

    existing = [s for s in current_positions if s != symbol]
    results.append(check_correlation(symbol, existing))
    results.append(check_cash_buffer(trade_value, strategy_cash, strategy_capital))

    all_passed = all(r.passed for r in results)
    return all_passed, results
