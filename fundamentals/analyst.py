"""yfinance ticker.info → 애널리스트 컨센서스 + 목표주가.

Usage:
    from fundamentals.analyst import get_analyst_consensus
    data = get_analyst_consensus(["AAPL", "MSFT"])
    # {"AAPL": {"rec_mean": 1.8, "target_price": 230.0, "analyst_count": 42}}

yfinance 무료 (추가 비용 없음, VAL 전략에서 이미 호출 중).
"""

from __future__ import annotations


def get_analyst_consensus(symbols: list[str]) -> dict[str, dict]:
    """종목별 애널리스트 추천 지수와 목표주가를 반환한다.

    Returns:
        {symbol: {
            "rec_mean": float,       # 1.0=Strong Buy ~ 5.0=Strong Sell
            "target_price": float,   # 컨센서스 목표주가 (없으면 0.0)
            "analyst_count": int,    # 커버리지 애널리스트 수
        }}
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    result: dict[str, dict] = {}

    for sym in symbols:
        try:
            info = yf.Ticker(sym).info
            rec_mean = float(info.get("recommendationMean") or 3.0)
            target = float(info.get("targetMeanPrice") or 0.0)
            count = int(info.get("numberOfAnalystOpinions") or 0)
            result[sym] = {
                "rec_mean": rec_mean,
                "target_price": target,
                "analyst_count": count,
            }
        except Exception as e:
            print(f"  [fundamentals/analyst] {sym} 조회 실패: {e}")
            continue

    return result
