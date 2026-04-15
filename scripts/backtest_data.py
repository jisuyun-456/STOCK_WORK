# scripts/backtest_data.py
"""Historical data fetcher with CSV cache for backtest."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "state" / "backtest_cache"


def _all_tickers() -> list[str]:
    """Union of all strategy universes + benchmarks."""
    universe_path = ROOT / "state" / "universe.json"
    tickers = set()
    if universe_path.exists():
        data = json.loads(universe_path.read_text(encoding="utf-8"))
        for key in ("NASDAQ_100_SUBSET", "SP500_TOP100", "RUSSELL_1000_SUBSET"):
            tickers.update(data.get(key, []))
    # Always include benchmarks + ETFs
    tickers.update(["SPY", "QQQ", "^VIX", "TQQQ", "SQQQ", "BND", "GLD"])
    return sorted(tickers)


def _save_prices_csv(prices: pd.DataFrame, path: Path) -> None:
    prices.to_csv(path, encoding="utf-8")


def _load_prices_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, encoding="utf-8")
    df.index = pd.to_datetime(df.index)
    return df


def _save_ff5_csv(ff5: pd.DataFrame, path: Path) -> None:
    ff5.to_csv(path, encoding="utf-8")


def _load_ff5_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, encoding="utf-8")
    df.index = pd.to_datetime(df.index)
    return df


def fetch_historical(
    start: str,
    end: str,
    cache_dir: Path | None = CACHE_DIR,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.DataFrame]:
    """Returns (prices, spy, vix, ff5).

    prices: DataFrame[dates × tickers]
    spy:    Series[dates]
    vix:    Series[dates]
    ff5:    DataFrame[dates × [Mkt-RF,SMB,HML,RMW,CMA,RF]]
    """
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = f"{start}_{end}".replace("-", "")
        prices_path = cache_dir / f"prices_{cache_key}.csv"
        ff5_path = cache_dir / f"ff5_{cache_key}.csv"

        if prices_path.exists() and ff5_path.exists():
            print(f"  [backtest_data] Loading from cache: {cache_dir}")
            prices = _load_prices_csv(prices_path)
            ff5 = _load_ff5_csv(ff5_path)
            spy = prices["SPY"].dropna() if "SPY" in prices.columns else pd.Series(dtype=float)
            vix = prices["^VIX"].dropna() if "^VIX" in prices.columns else pd.Series(dtype=float)
            return prices, spy, vix, ff5

    print(f"  [backtest_data] Fetching {start} → {end} from yfinance...")
    tickers = _all_tickers()
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)

    # Handle MultiIndex columns from yfinance
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            prices = raw["Close"]
        else:
            # Take first price level available
            first_level = raw.columns.get_level_values(0)[0]
            prices = raw[first_level]
    else:
        prices = raw

    prices.index = pd.to_datetime(prices.index)

    spy = prices["SPY"].dropna() if "SPY" in prices.columns else pd.Series(dtype=float)
    vix = prices["^VIX"].dropna() if "^VIX" in prices.columns else pd.Series(dtype=float)

    # Fetch FF5 factors
    ff5 = _fetch_ff5(start, end)

    if cache_dir:
        _save_prices_csv(prices, prices_path)
        ff5_to_save = ff5 if ff5 is not None and len(ff5) > 0 else pd.DataFrame()
        _save_ff5_csv(ff5_to_save, ff5_path)

    return prices, spy, vix, (ff5 if ff5 is not None else pd.DataFrame())


def _fetch_ff5(start: str, end: str) -> pd.DataFrame:
    """Download Kenneth French FF5 daily factors via pandas_datareader."""
    try:
        import pandas_datareader.data as web
        ff5 = web.DataReader(
            "F-F_Research_Data_5_Factors_2x3_daily",
            "famafrench",
            start=start,
            end=end,
        )[0] / 100
        ff5.index = pd.to_datetime(ff5.index, format="%Y%m%d")
        return ff5
    except Exception as e:
        print(f"  [backtest_data] WARNING: FF5 fetch failed: {e}")
        print("  [backtest_data] QNT will use price-momentum fallback scoring.")
        return pd.DataFrame()
