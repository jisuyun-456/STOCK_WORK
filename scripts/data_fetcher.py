"""
데이터 수집 모듈 — yfinance(미국/글로벌/한국) + FRED(매크로)
"""
import os
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def fetch_us_indices() -> dict:
    """나스닥, S&P500, DJI, VIX 전일 데이터"""
    symbols = {
        "NASDAQ": "^IXIC",
        "S&P500": "^GSPC",
        "DOW": "^DJI",
        "VIX": "^VIX",
    }
    result = {}
    for name, ticker in symbols.items():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="5d")
            if len(hist) < 2:
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change = latest["Close"] - prev["Close"]
            change_pct = (change / prev["Close"]) * 100

            # 52주 고저
            hist_1y = data.history(period="1y")
            high_52w = hist_1y["High"].max() if len(hist_1y) > 0 else None
            low_52w = hist_1y["Low"].min() if len(hist_1y) > 0 else None

            result[name] = {
                "close": round(latest["Close"], 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(latest["Volume"]),
                "high_52w": round(high_52w, 2) if high_52w else None,
                "low_52w": round(low_52w, 2) if low_52w else None,
            }
        except Exception as e:
            result[name] = {"error": str(e)}
    return result


def fetch_kr_indices() -> dict:
    """KOSPI, KOSDAQ 전일 데이터 (yfinance 기반 — pykrx pandas 3.0 비호환 대체)"""
    symbols = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    result = {}

    for name, ticker in symbols.items():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="5d")
            if len(hist) < 2:
                result[name] = {"error": "데이터 없음 (비거래일 가능)"}
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change = latest["Close"] - prev["Close"]
            change_pct = (change / prev["Close"]) * 100

            result[name] = {
                "close": round(latest["Close"], 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "volume": int(latest["Volume"]),
            }
        except Exception as e:
            result[name] = {"error": str(e)}

    return result


def fetch_commodities() -> dict:
    """금, 유가, DXY, 10Y 국채"""
    symbols = {
        "Gold": "GC=F",
        "WTI Oil": "CL=F",
        "DXY": "DX-Y.NYB",
        "US 10Y": "^TNX",
    }
    result = {}
    for name, ticker in symbols.items():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="5d")
            if len(hist) < 2:
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2]
            change_pct = ((latest["Close"] - prev["Close"]) / prev["Close"]) * 100
            result[name] = {
                "close": round(latest["Close"], 2),
                "change_pct": round(change_pct, 2),
            }
        except Exception as e:
            result[name] = {"error": str(e)}
    return result


def fetch_macro() -> dict:
    """기준금리, CPI, 실업률, GDP (FRED_API_KEY 없으면 빈 dict)"""
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    if not api_key:
        return {}

    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)

        indicators = {
            "Fed Funds Rate": "FEDFUNDS",
            "CPI (YoY)": "CPIAUCSL",
            "Unemployment": "UNRATE",
            "GDP Growth": "A191RL1Q225SBEA",
            "10Y Treasury": "GS10",
        }
        result = {}
        for name, series_id in indicators.items():
            try:
                s = fred.get_series(series_id, observation_start="2024-01-01")
                if s is not None and len(s) > 0:
                    result[name] = round(float(s.iloc[-1]), 2)
            except Exception:
                continue
        return result
    except Exception:
        return {}


def fetch_sector_performance() -> dict:
    """S&P500 11개 섹터 ETF 등락률"""
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
            hist = yf.Ticker(ticker).history(period="5d")
            if len(hist) >= 2:
                change_pct = ((hist.iloc[-1]["Close"] - hist.iloc[-2]["Close"]) / hist.iloc[-2]["Close"]) * 100
                result[name] = round(change_pct, 2)
        except Exception:
            continue
    return result


if __name__ == "__main__":
    import json

    print("=== US Indices ===")
    print(json.dumps(fetch_us_indices(), indent=2, ensure_ascii=False))

    print("\n=== KR Indices ===")
    print(json.dumps(fetch_kr_indices(), indent=2, ensure_ascii=False))

    print("\n=== Commodities ===")
    print(json.dumps(fetch_commodities(), indent=2, ensure_ascii=False))

    print("\n=== Macro ===")
    print(json.dumps(fetch_macro(), indent=2, ensure_ascii=False))

    print("\n=== Sector Performance ===")
    print(json.dumps(fetch_sector_performance(), indent=2, ensure_ascii=False))
