"""Pre-trade risk validation — 5 risk gates that every signal must pass.

Gates:
  1. Position limit: single position <= 20% of strategy capital
  2. Sector concentration: sector <= 40% of strategy capital
  3. Portfolio VaR: 95% 1-day VaR <= 3%
  4. Correlation: |corr(new, existing)| <= 0.85
  5. Cash buffer: strategy cash >= 5% after trade
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
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

# Hardcoded fallback for known symbols (instant lookup, no API call)
SECTOR_MAP: dict[str, str] = {
    # Tech
    "AAPL": "Technology", "MSFT": "Technology", "NVDA": "Technology",
    "GOOGL": "Technology", "META": "Technology", "AMZN": "Technology",
    "PLTR": "Technology", "APLD": "Technology", "IONQ": "Technology",
    "AMD": "Technology", "INTC": "Technology", "AVGO": "Technology",
    "CSCO": "Technology", "TXN": "Technology", "QCOM": "Technology",
    "AMAT": "Technology", "LRCX": "Technology", "KLAC": "Technology",
    "MU": "Technology", "MRVL": "Technology", "ADI": "Technology",
    "ASML": "Technology", "SNPS": "Technology", "CDNS": "Technology",
    "CRM": "Technology", "ORCL": "Technology", "ADBE": "Technology",
    "INTU": "Technology", "PANW": "Technology", "CRWD": "Technology",
    "NFLX": "Communication Services", "GOOG": "Communication Services",
    "TMUS": "Communication Services", "VZ": "Communication Services",
    "T": "Communication Services", "DIS": "Communication Services",
    # Healthcare
    "JNJ": "Healthcare", "UNH": "Healthcare", "HIMS": "Healthcare",
    "LLY": "Healthcare", "ABBV": "Healthcare", "MRK": "Healthcare",
    "PFE": "Healthcare", "TMO": "Healthcare", "ABT": "Healthcare",
    "AMGN": "Healthcare", "GILD": "Healthcare", "ISRG": "Healthcare",
    "VRTX": "Healthcare", "REGN": "Healthcare", "BSX": "Healthcare",
    # Financials
    "JPM": "Financials", "BAC": "Financials", "WFC": "Financials",
    "GS": "Financials", "MS": "Financials", "BLK": "Financials",
    "SCHW": "Financials", "C": "Financials", "USB": "Financials",
    "PNC": "Financials", "CB": "Financials", "ICE": "Financials",
    "CME": "Financials", "SPGI": "Financials", "MMC": "Financials",
    # Consumer
    "WMT": "Consumer Staples", "COST": "Consumer Staples", "PG": "Consumer Staples",
    "KO": "Consumer Staples", "PEP": "Consumer Staples", "PM": "Consumer Staples",
    "MO": "Consumer Staples", "CL": "Consumer Staples", "KDP": "Consumer Staples",
    "MDLZ": "Consumer Staples", "KHC": "Consumer Staples", "MCD": "Consumer Discretionary",
    "HD": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "NKE": "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "TJX": "Consumer Discretionary", "BKNG": "Consumer Discretionary",
    "ABNB": "Consumer Discretionary", "TSLA": "Consumer Discretionary",
    "LULU": "Consumer Discretionary", "ROST": "Consumer Discretionary",
    # Industrials
    "RKLB": "Industrials", "CAT": "Industrials", "HON": "Industrials",
    "UNP": "Industrials", "RTX": "Industrials", "GE": "Industrials",
    "DE": "Industrials", "BA": "Industrials", "LMT": "Industrials",
    "FDX": "Industrials", "MMM": "Industrials", "NOC": "Industrials",
    "GD": "Industrials", "EMR": "Industrials",
    # Energy
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy",
    "SLB": "Energy", "EOG": "Energy", "PSX": "Energy",
    "MPC": "Energy", "VLO": "Energy", "OXY": "Energy",
    "HAL": "Energy", "FANG": "Energy",
    # Utilities
    "NEE": "Utilities", "DUK": "Utilities", "SO": "Utilities",
    "AEP": "Utilities", "D": "Utilities", "EXC": "Utilities",
    "XEL": "Utilities", "CEG": "Utilities",
    # Real Estate
    "PLD": "Real Estate", "CCI": "Real Estate", "AMT": "Real Estate",
    # Materials
    "LIN": "Materials", "APD": "Materials", "SHW": "Materials",
    # Leveraged ETFs
    "TQQQ": "ETF-Leveraged", "UPRO": "ETF-Leveraged",
    "SQQQ": "ETF-Leveraged", "SPXU": "ETF-Leveraged",
    "SOXL": "ETF-Leveraged", "SOXS": "ETF-Leveraged",
    # Broad Market ETFs (used as LEV Core or hedging)
    "SPY": "ETF-Broad", "QQQ": "ETF-Broad", "IWM": "ETF-Broad",
    "VOO": "ETF-Broad", "DIA": "ETF-Broad",
    "BIL": "ETF-ShortTerm", "SHV": "ETF-ShortTerm",
    # Defensive ETFs (used by LEV in CRISIS regime)
    "BND": "ETF-Defensive", "GLD": "ETF-Defensive",
    "TLT": "ETF-Defensive", "IEF": "ETF-Defensive",
    "IAU": "ETF-Defensive", "SLV": "ETF-Defensive",
}

# Dynamic sector cache (yfinance fallback for symbols not in SECTOR_MAP)
_SECTOR_CACHE_PATH = Path(__file__).parent.parent / "state" / "sector_cache.json"
_SECTOR_CACHE_TTL = 86400  # 24 hours


def _load_sector_cache() -> dict:
    if not _SECTOR_CACHE_PATH.exists():
        return {}
    try:
        with open(_SECTOR_CACHE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sector_cache(symbol: str, sector: str):
    cache = _load_sector_cache()
    cache[symbol] = {"sector": sector, "ts": time.time()}
    _SECTOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SECTOR_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def get_sector(symbol: str) -> str:
    """Get sector for a symbol. Uses hardcoded map → cache → yfinance fallback."""
    # 1. Hardcoded map (instant, no API call)
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]

    # 2. Check dynamic cache
    cache = _load_sector_cache()
    if symbol in cache:
        entry = cache[symbol]
        if time.time() - entry.get("ts", 0) < _SECTOR_CACHE_TTL:
            return entry["sector"]

    # 3. yfinance dynamic lookup
    try:
        sector = yf.Ticker(symbol).info.get("sector", "Unknown")
        _save_sector_cache(symbol, sector)
        return sector
    except Exception:
        return "Unknown"


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
    # H7 fix: Unknown 섹터는 **게이트 PASS가 아닌 BLOCK**.
    # 기존 버그: Unknown → 자동 PASS → 섹터 집중도 미감지. MOM 포트폴리오가
    # 70%+ 반도체였는데 섹터 게이트가 전혀 동작하지 않았음.
    # 수정: Unknown = 미분류 = 리스크 미산정 = 보수적으로 차단.
    if target_sector == "Unknown":
        return RiskCheckResult(
            passed=False,
            check_name="sector_concentration",
            reason=(
                f"Sector unknown for {symbol} — BLOCKED "
                f"(H7: 미분류 섹터는 집중도 산정 불가 → 보수적 차단)"
            ),
            value=0.0,
            threshold=max_pct,
        )
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

        z_score = 1.6449  # norm.ppf(0.95), deterministic
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
        # On data fetch failure, REJECT (never silently pass)
        return RiskCheckResult(
            passed=False, check_name="correlation",
            reason=f"Correlation check FAILED (data unavailable): {e}",
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

# Strategy-specific position limits (default 20%, LEV allows 50% per ETF)
STRATEGY_POSITION_LIMITS: dict[str, float] = {
    "MOM": 0.20,
    "VAL": 0.25,
    "QNT": 0.15,
    "LEV": 1.00,     # max 2 ETFs: SPY+TQQQ(50/50), BND+GLD(60/40) — 60% is max weight
    "LEV_ST": 1.00,  # Single ETF (TQQQ or SQQQ) 100% by design
}

# Strategy-specific sector concentration limits (default 40%, LEV allows 100%)
STRATEGY_SECTOR_LIMITS: dict[str, float] = {
    "MOM": 0.40,
    "VAL": 0.40,
    "QNT": 0.40,
    "LEV": 1.00,    # All ETF-Leveraged sector by design
    "LEV_ST": 1.00, # Single ETF by design
}


def validate_signal(
    symbol: str,
    side: str,
    trade_value: float,
    strategy_capital: float,
    strategy_cash: float,
    current_positions: dict[str, float],
    strategy_code: str = "",
) -> tuple[bool, list[RiskCheckResult]]:
    """Run all 5 risk checks on a proposed trade.

    Args:
        symbol: Ticker to trade
        side: "buy" or "sell"
        trade_value: Dollar value of the trade
        strategy_capital: Total allocated capital for this strategy
        strategy_cash: Available cash in this strategy
        current_positions: Dict of {symbol: market_value} for current holdings
        strategy_code: Strategy identifier ("MOM", "VAL", "QNT", "LEV")

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
    pos_limit = STRATEGY_POSITION_LIMITS.get(strategy_code, 0.20)
    results.append(check_position_limit(symbol, trade_value, strategy_capital, current_positions, max_pct=pos_limit))

    sector_limit = STRATEGY_SECTOR_LIMITS.get(strategy_code, 0.40)
    results.append(check_sector_concentration(symbol, trade_value, strategy_capital, current_positions, max_pct=sector_limit))

    # LEV 재설계 2026-04-11: LEV 전략은 설계상 TQQQ/SQQQ(일일 ~6% 변동성)를 보유하므로
    # 기본 3% VaR 게이트를 원천적으로 통과할 수 없다. LEV 는 이미 position_limit 50%
    # + sector_limit 100% + regime 기반 stop-loss (-30%/-20%) 로 리스크 통제하므로
    # 여기서는 VaR/correlation 게이트를 스킵한다. MOM/VAL/QNT 는 기존 로직 그대로.
    if strategy_code in ("LEV", "LEV_ST"):
        results.append(RiskCheckResult(
            passed=True, check_name="portfolio_var",
            reason=f"{strategy_code} 전략은 설계상 고변동성 레버리지 ETF 보유 → VaR 게이트 면제 (stop-loss regime 동적 통제)",
            value=0.0, threshold=0.03,
        ))
        results.append(RiskCheckResult(
            passed=True, check_name="correlation",
            reason=f"{strategy_code} 전략은 단일 레버리지 ETF 내재적 고상관(설계) → correlation 게이트 면제",
            value=0.0, threshold=0.85,
        ))
        # LEV 는 cash_buffer 만 적용 (잔여 현금 보호)
        results.append(check_cash_buffer(trade_value, strategy_cash, strategy_capital))
        all_passed = all(r.passed for r in results)
        return all_passed, results

    # H4 fix: build-phase VaR 스킵은 단일 종목 비중이 낮을 때만 허용.
    # 기존 버그: 포지션 < 3 이면 무조건 VaR 스킵 → 초기 35개 포지션 전체가
    # VaR 검증 없이 진입. 이제는 단일 종목 비중 > 30% 이면 스킵하지 않음.
    single_position_pct = (trade_value / strategy_capital) if strategy_capital > 0 else 1.0
    skip_var_build_phase = (
        len(current_positions) < 3
        and single_position_pct < 0.30
    )
    if skip_var_build_phase:
        results.append(RiskCheckResult(
            passed=True, check_name="portfolio_var",
            reason=(
                f"VaR check skipped (build phase, {len(current_positions)} positions, "
                f"size {single_position_pct:.1%} < 30%)"
            ),
            value=0.0, threshold=0.03,
        ))
    else:
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
