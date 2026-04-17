"""DART (Data Analysis, Retrieval and Transfer System) client.

Wraps dart-fss to provide:
  - corp_code_for(ticker): 6-digit KRX ticker → 8-digit DART corp_code  [HIGH #5]
  - fetch_filings(corp_code, bgn_de, end_de): recent disclosure list
  - fetch_financial_statement(corp_code, year, quarter): financial data
  - fetch_major_holders(corp_code): major shareholder list

All responses are disk-cached via KRCache with per-method TTLs.
"""
import logging
import os
from typing import Optional

import dart_fss

from kr_data.cache import KRCache

_logger = logging.getLogger("kr_data.dart")
_cache = KRCache()

_TTL_CORP_CODE = 86400 * 7   # 7 days — corp codes rarely change
_TTL_FILINGS = 3600          # 1 hour
_TTL_FINANCIALS = 3600 * 6   # 6 hours
_TTL_HOLDERS = 3600 * 6      # 6 hours

# Sentinel value stored in cache to distinguish "ticker not found" from cache miss
_NOT_FOUND = "__NOT_FOUND__"


class DartClient:
    """High-level DART API client with caching and error isolation.

    Parameters
    ----------
    api_key:
        DART Open API key. Falls back to ``DART_API_KEY`` env var.
        If neither is available a warning is logged and calls will fail
        when dart_fss attempts network requests.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("DART_API_KEY")
        if key:
            dart_fss.set_api_key(key)
        else:
            _logger.warning(
                "DART_API_KEY not set — DART calls will fail"
            )
        self._key = key

    # ------------------------------------------------------------------
    # corp_code mapping — HIGH issue #5
    # ------------------------------------------------------------------

    def corp_code_for(self, ticker: str) -> Optional[str]:
        """Return the 8-digit DART corp_code for a 6-digit KRX *ticker*.

        Returns None if the ticker is not found in the DART corp list or
        if the lookup fails.

        Results are cached for 7 days (corp codes do not change frequently).

        Parameters
        ----------
        ticker:
            6-digit KRX stock code, e.g. ``"005930"`` for Samsung Electronics.
        """
        cache_key = f"dart_corp_code_{ticker}"
        cached = _cache.get(cache_key, _TTL_CORP_CODE)
        if cached is not None:
            val = cached.get("corp_code")
            return None if val == _NOT_FOUND else val

        try:
            corp_list = dart_fss.get_corp_list()
            corp = corp_list.find_by_stock_code(ticker)
            result = corp.corp_code if corp is not None else None
        except Exception as exc:
            _logger.warning("corp_code_for(%s) failed: %s", ticker, exc)
            return None

        _cache.set(cache_key, {"corp_code": result if result is not None else _NOT_FOUND})
        return result

    # ------------------------------------------------------------------
    # Filings (공시)
    # ------------------------------------------------------------------

    def fetch_filings(
        self,
        corp_code: str,
        bgn_de: str,
        end_de: str,
    ) -> list:
        """Return recent DART filings for *corp_code* in date range.

        Parameters
        ----------
        corp_code:
            8-digit DART corp_code.
        bgn_de:
            Start date in ``"YYYYMMDD"`` format.
        end_de:
            End date in ``"YYYYMMDD"`` format.

        Returns
        -------
        list[dict]
            Each element has keys: ``rcp_no``, ``corp_name``,
            ``report_nm``, ``rcept_dt``, ``rm``.
            Returns ``[]`` on failure.
        """
        cache_key = f"dart_filings_{corp_code}_{bgn_de}_{end_de}"
        cached = _cache.get(cache_key, _TTL_FILINGS)
        if cached is not None:
            return cached.get("filings", [])

        try:
            results = dart_fss.filings.search(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de
            )
            filings = []
            for r in getattr(results, "report_list", []):
                filings.append({
                    "rcp_no":     getattr(r, "rcp_no",     ""),
                    "corp_name":  getattr(r, "corp_name",  ""),
                    "report_nm":  getattr(r, "report_nm",  ""),
                    "rcept_dt":   getattr(r, "rcept_dt",   ""),
                    "rm":         getattr(r, "rm",         ""),
                })
        except Exception as exc:
            _logger.warning("fetch_filings(%s) failed: %s", corp_code, exc)
            return []

        _cache.set(cache_key, {"filings": filings})
        return filings

    # ------------------------------------------------------------------
    # Financial statements (재무제표)
    # ------------------------------------------------------------------

    def fetch_financial_statement(
        self,
        corp_code: str,
        year: int,
        quarter: str = "11011",
    ) -> Optional[dict]:
        """Return basic financial statement metadata for *corp_code*.

        Parameters
        ----------
        corp_code:
            8-digit DART corp_code.
        year:
            Reporting year, e.g. ``2025``.
        quarter:
            Report code. ``"11011"`` = annual, ``"11012"`` = Q1,
            ``"11013"`` = Q2, ``"11014"`` = Q3.

        Returns
        -------
        dict or None
            Returns ``None`` if the lookup fails.
        """
        cache_key = f"dart_fs_{corp_code}_{year}_{quarter}"
        cached = _cache.get(cache_key, _TTL_FINANCIALS)
        if cached is not None:
            return cached.get("fs")

        try:
            corp = dart_fss.corp.Corp(corp_code)
            result: dict = {
                "corp_code": corp_code,
                "year":      year,
                "quarter":   quarter,
            }
        except Exception as exc:
            _logger.warning(
                "fetch_financial_statement(%s/%s) failed: %s",
                corp_code, year, exc,
            )
            return None

        _cache.set(cache_key, {"fs": result})
        return result

    # ------------------------------------------------------------------
    # Major shareholders (주요주주)
    # ------------------------------------------------------------------

    def fetch_major_holders(self, corp_code: str) -> list:
        """Return major shareholders for *corp_code*.

        Parameters
        ----------
        corp_code:
            8-digit DART corp_code.

        Returns
        -------
        list[dict]
            Each element has keys: ``name`` (str), ``pct`` (float).
            Returns ``[]`` on failure or if no data available.
        """
        cache_key = f"dart_holders_{corp_code}"
        cached = _cache.get(cache_key, _TTL_HOLDERS)
        if cached is not None:
            return cached.get("holders", [])

        try:
            corp = dart_fss.corp.Corp(corp_code)
            df = corp.get_major_shareholder()
            if df is not None:
                holders = [
                    {
                        "name": row.get("nm", ""),
                        "pct":  float(row.get("stkrt", 0)),
                    }
                    for _, row in df.iterrows()
                ]
            else:
                holders = []
        except Exception as exc:
            _logger.warning("fetch_major_holders(%s) failed: %s", corp_code, exc)
            return []

        _cache.set(cache_key, {"holders": holders})
        return holders
