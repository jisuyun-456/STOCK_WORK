"""SEC EDGAR Form 4 인사이더 매수 데이터 (달러 금액 기준).

SEC EDGAR 무료 API — API 키 불필요, User-Agent만 필요.
- CIK 매핑: https://www.sec.gov/files/company_tickers.json (1회 요청, 모듈 캐시)
- 제출 목록: https://data.sec.gov/submissions/CIK{cik:010d}.json (ticker당 1 req)
- Form 4 XML: https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{filename}

Usage:
    from fundamentals.sec_form4 import get_form4_signals
    data = get_form4_signals(["AAPL", "MSFT", "NVDA"], lookback_days=7)
    # {"NVDA": {"net_purchase_usd": 550000, "max_single_usd": 550000, ...}}

제한: SEC 10 req/sec → time.sleep(0.12) 적용.
"""

from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Optional

import requests

_SEC_UA = "STOCK_WORK research-bot contact@stock-work.internal"
_REQUEST_TIMEOUT = 12

# 모듈 전역 CIK 캐시 (프로세스 1회 로드)
_CIK_CACHE: dict[str, str] = {}  # ticker.upper() → "0001234567"


# ─── CIK 매핑 ────────────────────────────────────────────────────────────────

def _load_cik_map() -> dict[str, str]:
    """SEC EDGAR company_tickers.json → {TICKER: "CIK(10자리 zero-pad)"}.

    첫 호출 시 한 번만 요청하고 모듈 캐시에 저장.
    """
    global _CIK_CACHE
    if _CIK_CACHE:
        return _CIK_CACHE

    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": _SEC_UA},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
        # 형식: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
        _CIK_CACHE = {
            v["ticker"].upper(): str(v["cik_str"]).zfill(10)
            for v in raw.values()
            if "ticker" in v and "cik_str" in v
        }
    except Exception as e:
        print(f"  [sec_form4] CIK 맵 로드 실패: {e}")

    return _CIK_CACHE


# ─── Form 4 제출 목록 조회 ────────────────────────────────────────────────────

def _get_recent_form4_filings(cik: str, lookback_days: int) -> list[dict]:
    """data.sec.gov submissions API에서 최근 Form 4 제출 목록 반환.

    Returns:
        [{"accession": "0001234567-26-000001", "filed": "2026-04-15",
          "primaryDocument": "form4.xml"}, ...]
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _SEC_UA},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])

    result = []
    for form, filed_str, acc, pdoc in zip(forms, dates, accessions, primary_docs):
        if form not in ("4", "4/A"):
            continue
        try:
            filed = date.fromisoformat(filed_str)
        except ValueError:
            continue
        if filed < cutoff:
            break  # 최신순 정렬 → cutoff 이전이면 이후도 모두 이전
        result.append({
            "accession": acc,
            "filed": filed_str,
            "primaryDocument": pdoc,
        })

    return result


# ─── Form 4 XML 파싱 ──────────────────────────────────────────────────────────

def _parse_form4_xml(cik: str, accession: str, primary_doc: str) -> list[dict]:
    """Form 4 XML에서 비파생 거래(nonDerivativeTransaction) 추출.

    Returns:
        [{"code": "P"|"S", "shares": float, "price": float,
          "usd": float, "date": str, "title": str}, ...]
    """
    # accession 형식: "0001234567-26-000001" → "000123456726000001"
    acc_no_dashes = accession.replace("-", "")
    cik_int = str(int(cik))  # leading zeros 제거
    # primaryDocument가 "xslF345X06/wk-form4_xxx.xml" 형태일 수 있음
    # XSL 스타일시트 경로 접두사 제거하여 실제 XML 파일만 사용
    import posixpath
    doc_name = posixpath.basename(primary_doc)
    url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
        f"{acc_no_dashes}/{doc_name}"
    )

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _SEC_UA},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.text
    except Exception:
        return []

    # Form 4 XML은 네임스페이스 없이 단순 구조
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    transactions: list[dict] = []

    # 신고자 직책 (reportingOwner → officerTitle)
    title = ""
    for owner in root.findall(".//reportingOwner"):
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            t = rel.findtext("officerTitle", "").strip()
            if t:
                title = t
                break

    # nonDerivativeTransaction (일반 주식 직접 거래)
    for txn in root.findall(".//nonDerivativeTransaction"):
        code_el = txn.find(".//transactionCoding/transactionCode")
        shares_el = txn.find(".//transactionAmounts/transactionShares/value")
        price_el = txn.find(".//transactionAmounts/transactionPricePerShare/value")
        date_el = txn.find(".//transactionDate/value")

        if code_el is None or shares_el is None:
            continue

        code = (code_el.text or "").strip().upper()
        if code not in ("P", "S"):
            continue  # P=Purchase, S=Sale; 무시: A(Award), M(Option exercise) 등

        try:
            shares = float(shares_el.text or 0)
            price = float(price_el.text or 0) if price_el is not None else 0.0
        except (ValueError, TypeError):
            continue

        usd = shares * price
        txn_date = date_el.text.strip() if date_el is not None else ""

        transactions.append({
            "code": code,
            "shares": shares,
            "price": price,
            "usd": usd,
            "date": txn_date,
            "title": title,
        })

    return transactions


# ─── 메인 진입점 ─────────────────────────────────────────────────────────────

def get_form4_signals(
    symbols: list[str],
    lookback_days: int = 7,
    min_usd: float = 50_000,
) -> dict[str, dict]:
    """SEC EDGAR Form 4 기반 인사이더 달러 매수/매도 신호.

    Args:
        symbols: 조회할 ticker 목록
        lookback_days: 조회 기간 (기본 7일)
        min_usd: 집계에 포함할 최소 거래 금액 (기본 $50k)

    Returns:
        {symbol: {
            "net_purchase_usd": float,   # 순매수 금액 (매수 - 매도, lookback_days 내)
            "max_single_usd": float,     # 최대 단일 매수 금액
            "purchase_count": int,       # min_usd 이상 매수 건수
            "days_since_latest": int,    # 최근 매수 경과일 (없으면 99)
            "titles": list[str],         # ["CEO", "CFO"] 등 중복 제거
        }}
        심볼이 없거나 오류 시 해당 심볼은 결과에서 제외.
    """
    cik_map = _load_cik_map()
    today = date.today()
    result: dict[str, dict] = {}

    for sym in symbols:
        cik = cik_map.get(sym.upper())
        if not cik:
            continue  # CIK 없으면 스킵 (ETF, 미등록 등)

        try:
            filings = _get_recent_form4_filings(cik, lookback_days)
            time.sleep(0.12)  # SEC 10 req/sec 제한 준수

            if not filings:
                continue

            purchase_usd = 0.0
            sale_usd = 0.0
            max_single = 0.0
            purchase_count = 0
            latest_purchase_date: Optional[date] = None
            titles: list[str] = []

            for filing in filings:
                txns = _parse_form4_xml(cik, filing["accession"], filing["primaryDocument"])
                time.sleep(0.12)

                for txn in txns:
                    if txn["title"] and txn["title"] not in titles:
                        titles.append(txn["title"])

                    if txn["code"] == "P":
                        usd = txn["usd"]
                        purchase_usd += usd
                        if usd >= min_usd:
                            purchase_count += 1
                            if usd > max_single:
                                max_single = usd
                        # 최근 매수일 추적
                        try:
                            txn_date = date.fromisoformat(txn["date"])
                            if latest_purchase_date is None or txn_date > latest_purchase_date:
                                latest_purchase_date = txn_date
                        except (ValueError, TypeError):
                            pass

                    elif txn["code"] == "S":
                        sale_usd += txn["usd"]

            net = purchase_usd - sale_usd
            days_ago = (today - latest_purchase_date).days if latest_purchase_date else 99

            # 매수/순매도 신호가 있을 때만 결과에 포함
            if purchase_usd > 0 or sale_usd > min_usd:
                result[sym] = {
                    "net_purchase_usd": round(net, 0),
                    "max_single_usd": round(max_single, 0),
                    "purchase_count": purchase_count,
                    "days_since_latest": days_ago,
                    "titles": titles[:5],  # 최대 5개
                }

        except Exception as e:
            print(f"  [sec_form4] {sym} 처리 실패: {e}")
            continue

    return result
