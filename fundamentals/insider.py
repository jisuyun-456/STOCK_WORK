"""yfinance ticker.insider_transactions → 경영진 순매수/매도 시그널.

Usage:
    from fundamentals.insider import get_insider_signals
    data = get_insider_signals(["AAPL", "MSFT"])
    # {"AAPL": {"buy_30d": 3, "sell_30d": 1, "net_30d": 2}}

yfinance 무료 (추가 비용 없음).
"""

from __future__ import annotations

from datetime import date, timedelta


def get_insider_signals(symbols: list[str]) -> dict[str, dict]:
    """최근 30일 내부자 거래 순매수/매도 집계.

    Returns:
        {symbol: {
            "buy_30d": int,   # 매수 건수
            "sell_30d": int,  # 매도 건수
            "net_30d": int,   # buy - sell (양수=순매수, 음수=순매도)
        }}
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    cutoff = date.today() - timedelta(days=30)
    result: dict[str, dict] = {}

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            txns = ticker.insider_transactions
            if txns is None or txns.empty:
                result[sym] = {"buy_30d": 0, "sell_30d": 0, "net_30d": 0}
                continue

            # 날짜 컬럼 정규화
            date_col = None
            for col in ("Date", "Start Date", "Transaction Date", "startDate"):
                if col in txns.columns:
                    date_col = col
                    break

            buy_count = 0
            sell_count = 0

            for _, row in txns.iterrows():
                if date_col:
                    try:
                        import pandas as pd
                        txn_date = pd.to_datetime(row[date_col]).date()
                        if txn_date < cutoff:
                            continue
                    except Exception:
                        pass  # 날짜 파싱 실패 시 포함

                # 매수/매도 구분 컬럼 탐색
                txn_type = ""
                for col in ("Transaction", "Shares", "Text"):
                    val = str(row.get(col, "")).lower()
                    if val:
                        txn_type = val
                        break

                if any(kw in txn_type for kw in ("purchase", "buy", "acquisition", "grant")):
                    buy_count += 1
                elif any(kw in txn_type for kw in ("sale", "sell", "disposed")):
                    sell_count += 1

            result[sym] = {
                "buy_30d": buy_count,
                "sell_30d": sell_count,
                "net_30d": buy_count - sell_count,
            }
        except Exception as e:
            print(f"  [fundamentals/insider] {sym} 조회 실패: {e}")
            result[sym] = {"buy_30d": 0, "sell_30d": 0, "net_30d": 0}

    return result
