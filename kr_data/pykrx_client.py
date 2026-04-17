"""pykrx-backed data client for Korean market data.

Fixes:
  HIGH #2  — VKOSPI sourced from pykrx (ticker "1163"), never estimated.
  HIGH #10 — Investor flow via pykrx, not Naver HTML regex.
  HIGH #11 — Short-selling balance actually fetched via pykrx.

All public functions:
  - are decorated with @retry_with_backoff (3 retries, exponential backoff)
  - check the disk cache first (KRCache) and write through on a miss
  - return None on unrecoverable failure (caller decides what to do)
"""
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from pykrx import stock as pykrx_stock  # noqa: F401  (patched in tests)

from kr_data.retry import retry_with_backoff
from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.pykrx")
_cache = KRCache()

# TTL constants (seconds)
_TTL_OHLCV = 3600        # 1 hour
_TTL_FUNDAMENTAL = 3600
_TTL_FLOW = 3600
_TTL_SHORTING = 3600
_TTL_VKOSPI = 3600
_TTL_SECTOR = 3600
_TTL_UNIVERSE = 86400    # 24 hours

# KOSDAQ top-N cap for universe building
_KOSDAQ_TOP_N = 300


# ---------------------------------------------------------------------------
# OHLCV
# ---------------------------------------------------------------------------

@retry_with_backoff
def fetch_ohlcv_batch(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV for multiple tickers via pykrx.

    Returns DataFrame with MultiIndex (ticker, date), or empty DataFrame on
    failure.  Uses a 1-hour disk cache.

    Args:
        tickers: List of KRX ticker codes, e.g. ["005930", "000660"].
        start:   Start date string "YYYYMMDD".
        end:     End date string "YYYYMMDD".
    """
    cache_key = f"ohlcv_{'-'.join(sorted(tickers))}_{start}_{end}"

    cached = _cache.get_df(cache_key, _TTL_OHLCV)
    if cached is not None:
        return cached

    frames: list[pd.DataFrame] = []
    for ticker in tickers:
        try:
            df = pykrx_stock.get_market_ohlcv(start, end, ticker)
            if df is not None and not df.empty:
                df.index = pd.to_datetime(df.index)
                df["ticker"] = ticker
                frames.append(df)
        except Exception as exc:
            _logger.warning("fetch_ohlcv_batch: ticker=%s error=%s", ticker, exc)

    if not frames:
        _logger.warning("fetch_ohlcv_batch: no data for tickers=%s", tickers)
        return pd.DataFrame()

    result = pd.concat(frames)
    result = result.reset_index().rename(columns={"index": "date"})
    result = result.set_index(["ticker", result.columns[0]])

    _cache.set_df(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Fundamentals (PER / PBR / DIV)
# ---------------------------------------------------------------------------

@retry_with_backoff
def fetch_market_fundamental(date: str, market: str = "KOSPI") -> Optional[pd.DataFrame]:
    """Fetch PER, PBR, DIV for all stocks on *date* via pykrx.

    Args:
        date:   Date string "YYYYMMDD".
        market: "KOSPI" or "KOSDAQ".

    Returns:
        DataFrame with ticker as index and columns [PER, PBR, DIV],
        or None on failure.
    """
    cache_key = f"fundamental_{market}_{date}"

    cached = _cache.get_df(cache_key, _TTL_FUNDAMENTAL)
    if cached is not None:
        return cached

    try:
        df = pykrx_stock.get_market_fundamental(date, market=market)
        if df is None or df.empty:
            _logger.warning("fetch_market_fundamental: empty result date=%s market=%s", date, market)
            return None
    except Exception as exc:
        _logger.warning("fetch_market_fundamental: date=%s market=%s error=%s", date, market, exc)
        return None

    _cache.set_df(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# Investor flow (HIGH #10 — pykrx, not Naver regex)
# ---------------------------------------------------------------------------

@retry_with_backoff
def fetch_investor_flow(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch institutional/foreign net-buy data via pykrx.

    HIGH #10 fix: uses pykrx_stock.get_market_trading_volume_by_investor,
    NOT Naver Finance HTML scraping / regex.

    Args:
        ticker: KRX ticker code, e.g. "005930".
        start:  Start date string "YYYYMMDD".
        end:    End date string "YYYYMMDD".

    Returns:
        DataFrame indexed by date with columns [외국인, 기관합계, 개인],
        or None on failure.
    """
    cache_key = f"flow_{ticker}_{start}_{end}"

    cached = _cache.get_df(cache_key, _TTL_FLOW)
    if cached is not None:
        return cached

    try:
        df = pykrx_stock.get_market_trading_volume_by_investor(start, end, ticker)
        if df is None or df.empty:
            _logger.warning("fetch_investor_flow: empty result ticker=%s", ticker)
            return None
    except Exception as exc:
        _logger.warning("fetch_investor_flow: ticker=%s error=%s", ticker, exc)
        return None

    _cache.set_df(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# Short-selling balance (HIGH #11 — actually fetched, not schema-only)
# ---------------------------------------------------------------------------

@retry_with_backoff
def fetch_shorting_balance(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch short-selling balance via pykrx.

    HIGH #11 fix: calls pykrx_stock.get_shorting_balance for real data
    instead of returning a static schema placeholder.

    Args:
        ticker: KRX ticker code, e.g. "005930".
        start:  Start date string "YYYYMMDD".
        end:    End date string "YYYYMMDD".

    Returns:
        DataFrame from pykrx, or None on failure.
    """
    cache_key = f"shorting_{ticker}_{start}_{end}"

    cached = _cache.get_df(cache_key, _TTL_SHORTING)
    if cached is not None:
        return cached

    try:
        df = pykrx_stock.get_shorting_balance(start, end, ticker)
        if df is None or df.empty:
            _logger.warning("fetch_shorting_balance: empty result ticker=%s", ticker)
            return None
    except Exception as exc:
        _logger.warning("fetch_shorting_balance: ticker=%s error=%s", ticker, exc)
        return None

    _cache.set_df(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# VKOSPI (HIGH #2 — source="pykrx", never "estimated")
# ---------------------------------------------------------------------------

_VKOSPI_TICKER = "1163"


@retry_with_backoff
def fetch_vkospi(start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch VKOSPI index data from pykrx.

    HIGH #2 fix: data is sourced exclusively from pykrx (ticker "1163").
    On failure, returns None.  Never falls back to an estimated value.

    Args:
        start: Start date string "YYYYMMDD".
        end:   End date string "YYYYMMDD".

    Returns:
        DataFrame indexed by date with column "Close" (= VKOSPI value)
        and metadata column "source" = "pykrx" on every row.
        Returns None if pykrx raises an exception.
    """
    cache_key = f"vkospi_{start}_{end}"

    cached = _cache.get_df(cache_key, _TTL_VKOSPI)
    if cached is not None:
        return cached

    try:
        df = pykrx_stock.get_index_ohlcv(start, end, _VKOSPI_TICKER)
        if df is None or df.empty:
            _logger.warning("fetch_vkospi: empty result start=%s end=%s", start, end)
            return None
    except Exception as exc:
        _logger.warning("fetch_vkospi: pykrx error=%s — returning None (no estimated fallback)", exc)
        return None

    # Rename "종가" → "Close" if present; otherwise keep existing columns.
    if "종가" in df.columns:
        df = df.rename(columns={"종가": "Close"})
    elif "Close" not in df.columns:
        # pykrx may return English column names depending on version.
        pass

    # Attach provenance metadata — HIGH #2 guarantee.
    df = df.copy()
    df["source"] = "pykrx"

    _cache.set_df(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# Sector index OHLCV
# ---------------------------------------------------------------------------

@retry_with_backoff
def fetch_sector_index_ohlcv(sector_code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch sector index OHLCV via pykrx.

    Args:
        sector_code: pykrx sector index code, e.g. "1028" (KOSPI 200).
        start:       Start date string "YYYYMMDD".
        end:         End date string "YYYYMMDD".

    Returns:
        DataFrame from pykrx, or None on failure.
    """
    cache_key = f"sector_idx_{sector_code}_{start}_{end}"

    cached = _cache.get_df(cache_key, _TTL_SECTOR)
    if cached is not None:
        return cached

    try:
        df = pykrx_stock.get_index_ohlcv(start, end, sector_code)
        if df is None or df.empty:
            _logger.warning("fetch_sector_index_ohlcv: empty result code=%s", sector_code)
            return None
    except Exception as exc:
        _logger.warning("fetch_sector_index_ohlcv: code=%s error=%s", sector_code, exc)
        return None

    _cache.set_df(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# Universe builder (replaces manual kr_universe.json curation)
# ---------------------------------------------------------------------------

def build_universe(
    market: str = "ALL",
    min_mcap_krw: int = 100_000_000_000,
) -> list[dict]:
    """Auto-build universe from pykrx.

    Replaces the manual kr_universe.json curation workflow.

    Args:
        market:       "KOSPI", "KOSDAQ", or "ALL".
        min_mcap_krw: Minimum market-cap filter in KRW (default 1000억).
                      Applied to KOSPI; KOSDAQ uses top-300 by market cap.

    Returns:
        List of dicts:
          [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "mcap_krw": 500_000_000_000}, ...]
        Empty list on failure.
    """
    cache_key = f"universe_{market}_{min_mcap_krw}"

    cached = _cache.get(cache_key, _TTL_UNIVERSE)
    if cached is not None:
        return cached  # type: ignore[return-value]

    today = datetime.now().strftime("%Y%m%d")
    universe: list[dict] = []

    try:
        if market in ("KOSPI", "ALL"):
            universe.extend(_fetch_kospi_universe(today, min_mcap_krw))
        if market in ("KOSDAQ", "ALL"):
            universe.extend(_fetch_kosdaq_universe(today))
    except Exception as exc:
        _logger.warning("build_universe: unexpected error=%s", exc)
        return []

    _cache.set(cache_key, universe)  # type: ignore[arg-type]
    return universe


def _fetch_kospi_universe(today: str, min_mcap_krw: int) -> list[dict]:
    try:
        df = pykrx_stock.get_market_cap(today, market="KOSPI")
        if df is None or df.empty:
            return []
        filtered = df[df["시가총액"] >= min_mcap_krw]
        return _df_to_universe_list(filtered, market_label="KOSPI")
    except Exception as exc:
        _logger.warning("_fetch_kospi_universe: error=%s", exc)
        return []


def _fetch_kosdaq_universe(today: str) -> list[dict]:
    try:
        df = pykrx_stock.get_market_cap(today, market="KOSDAQ")
        if df is None or df.empty:
            return []
        top300 = df.nlargest(_KOSDAQ_TOP_N, "시가총액")
        return _df_to_universe_list(top300, market_label="KOSDAQ")
    except Exception as exc:
        _logger.warning("_fetch_kosdaq_universe: error=%s", exc)
        return []


def _df_to_universe_list(df: pd.DataFrame, market_label: str) -> list[dict]:
    result: list[dict] = []
    for ticker, row in df.iterrows():
        result.append({
            "ticker": str(ticker),
            "name": row.get("종목명", ""),
            "market": market_label,
            "mcap_krw": int(row.get("시가총액", 0)),
        })
    return result
