"""
떠오르는 기업 스크리닝 — 거래량 급등, 52주 신고가, 섹터별 모멘텀
yfinance 기반 (OpenBB screener 대체)
"""
import yfinance as yf
import pandas as pd


# 나스닥 주요 대형주 유니버스 (스크리닝 대상)
NASDAQ_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "COST", "NFLX",
    "AMD", "ADBE", "QCOM", "INTC", "CSCO", "TXN", "AMGN", "INTU", "AMAT", "ISRG",
    "MU", "LRCX", "ADI", "KLAC", "SNPS", "CDNS", "MRVL", "PANW", "CRWD", "FTNT",
    "DDOG", "ZS", "WDAY", "TEAM", "MELI", "ABNB", "BKNG", "PDD", "JD", "PYPL",
    "COIN", "SHOP", "ROKU", "SNAP", "PINS", "UBER", "LYFT", "DASH", "RBLX",
]


def volume_surge(universe: list[str] | None = None, top_n: int = 10) -> list[dict]:
    """거래량 급등 TOP N — 최근 거래량 vs 20일 평균 비율"""
    tickers = universe or NASDAQ_UNIVERSE
    results = []

    for symbol in tickers:
        try:
            hist = yf.Ticker(symbol).history(period="1mo")
            if len(hist) < 5:
                continue
            avg_vol_20d = hist["Volume"].iloc[:-1].tail(20).mean()
            latest_vol = hist["Volume"].iloc[-1]
            if avg_vol_20d == 0:
                continue
            ratio = latest_vol / avg_vol_20d
            latest_close = hist["Close"].iloc[-1]
            prev_close = hist["Close"].iloc[-2]
            change_pct = ((latest_close - prev_close) / prev_close) * 100

            results.append({
                "symbol": symbol,
                "volume": int(latest_vol),
                "avg_volume_20d": int(avg_vol_20d),
                "volume_ratio": round(ratio, 2),
                "close": round(latest_close, 2),
                "change_pct": round(change_pct, 2),
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["volume_ratio"], reverse=True)
    return results[:top_n]


def new_highs(universe: list[str] | None = None) -> list[dict]:
    """52주 신고가 종목"""
    tickers = universe or NASDAQ_UNIVERSE
    results = []

    for symbol in tickers:
        try:
            hist = yf.Ticker(symbol).history(period="1y")
            if len(hist) < 20:
                continue
            high_52w = hist["High"].max()
            latest_close = hist["Close"].iloc[-1]
            # 현재가가 52주 고가의 98% 이상이면 신고가 근접
            if latest_close >= high_52w * 0.98:
                results.append({
                    "symbol": symbol,
                    "close": round(latest_close, 2),
                    "high_52w": round(high_52w, 2),
                    "pct_from_high": round(((latest_close / high_52w) - 1) * 100, 2),
                })
        except Exception:
            continue

    results.sort(key=lambda x: x["pct_from_high"], reverse=True)
    return results


def sector_momentum() -> dict:
    """11개 섹터 ETF 1주/1개월 수익률"""
    sector_etfs = {
        "Technology": "XLK",
        "Healthcare": "XLV",
        "Financials": "XLF",
        "Consumer Disc.": "XLY",
        "Communication": "XLC",
        "Industrials": "XLI",
        "Consumer Staples": "XLP",
        "Energy": "XLE",
        "Utilities": "XLU",
        "Real Estate": "XLRE",
        "Materials": "XLB",
    }
    result = {}
    for name, ticker in sector_etfs.items():
        try:
            hist = yf.Ticker(ticker).history(period="1mo")
            if len(hist) < 5:
                continue
            close_now = hist["Close"].iloc[-1]
            close_1w = hist["Close"].iloc[-5] if len(hist) >= 5 else close_now
            close_1m = hist["Close"].iloc[0]

            result[name] = {
                "return_1w": round(((close_now / close_1w) - 1) * 100, 2),
                "return_1m": round(((close_now / close_1m) - 1) * 100, 2),
            }
        except Exception:
            continue

    return result


if __name__ == "__main__":
    import json

    print("=== Volume Surge TOP 10 ===")
    print(json.dumps(volume_surge(top_n=10), indent=2))

    print("\n=== 52-Week New Highs ===")
    print(json.dumps(new_highs(), indent=2))

    print("\n=== Sector Momentum ===")
    print(json.dumps(sector_momentum(), indent=2))
