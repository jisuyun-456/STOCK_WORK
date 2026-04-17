from datetime import date, timedelta

KR_TRADING_TAX = 0.0018       # 증권거래세 0.18% (2026 현행)
KR_DIVIDEND_TAX = 0.154       # 배당소득세 15.4%


def business_days_add(start: date, n: int) -> date:
    """
    Add n business days to start date.
    Business days = weekdays only (Mon-Fri). No Korean holiday adjustment.
    Saturday=5, Sunday=6 in weekday() notation.
    """
    current = start
    added = 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            added += 1
    return current


def settlement_date(trade_date: str) -> str:
    """
    Calculate T+2 settlement date.
    trade_date is "YYYY-MM-DD" string.
    Returns settlement date as "YYYY-MM-DD" string.
    Uses business_days_add(trade_date, 2).
    """
    td = date.fromisoformat(trade_date)
    sd = business_days_add(td, 2)
    return sd.isoformat()


def simulate_buy(ticker: str, qty: int, price_krw: int, trade_date: str) -> dict:
    """
    Simulate a BUY order. No tax on buy in Korea.
    Returns a dict with cost and settlement info.
    """
    gross_cost_krw = qty * price_krw
    return {
        "ticker": ticker,
        "qty": qty,
        "price_krw": price_krw,
        "trade_date": trade_date,
        "settlement_date": settlement_date(trade_date),
        "gross_cost_krw": gross_cost_krw,
        "net_cost_krw": gross_cost_krw,  # same as gross (no buy tax)
        "side": "BUY",
        "status": "pending_settlement",
    }


def simulate_sell(
    ticker: str,
    qty: int,
    price_krw: int,
    avg_entry_krw: int,
    trade_date: str,
) -> dict:
    """
    Simulate a SELL order.
    - 증권거래세 0.18% on gross proceeds
    - 양도세: 유예 (일반 소액 투자자) → 0
    Returns a dict with proceeds and tax breakdown.
    """
    gross_proceeds_krw = qty * price_krw
    trading_tax_krw = int(gross_proceeds_krw * KR_TRADING_TAX)
    capital_gains_tax_krw = 0  # 유예 중
    net_proceeds_krw = gross_proceeds_krw - trading_tax_krw
    return {
        "ticker": ticker,
        "qty": qty,
        "price_krw": price_krw,
        "avg_entry_krw": avg_entry_krw,
        "trade_date": trade_date,
        "settlement_date": settlement_date(trade_date),
        "gross_proceeds_krw": gross_proceeds_krw,
        "trading_tax_krw": trading_tax_krw,
        "capital_gains_tax_krw": capital_gains_tax_krw,
        "net_proceeds_krw": net_proceeds_krw,
        "side": "SELL",
        "status": "pending_settlement",
    }


def apply_dividend(ticker: str, gross_dividend_krw: int) -> dict:
    """
    Calculate dividend after tax (배당소득세 15.4%).
    Returns a dict with gross, tax, and net dividend amounts.
    """
    tax_krw = int(gross_dividend_krw * KR_DIVIDEND_TAX)
    net_dividend_krw = gross_dividend_krw - tax_krw
    return {
        "ticker": ticker,
        "gross_dividend_krw": gross_dividend_krw,
        "tax_krw": tax_krw,
        "net_dividend_krw": net_dividend_krw,
    }
