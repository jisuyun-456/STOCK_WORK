"""한국 시장 데이터 수집.

Data sources (우선순위):
1. FinanceDataReader (FDR): KRX OHLCV, KOSPI 지수, KRW/USD, 전체 목록
2. yfinance: ^VKOSPI, 보조 PER/PBR
3. DART OpenAPI: 공시/재무제표 (DART_API_KEY 환경변수, 없으면 skip)
4. 한국은행 ECOS API: 기준금리 (ECOS_API_KEY, 없으면 fallback=3.0)
5. naver 금융 crawl: 외국인/기관 수급 (선택, 실패 시 {} 반환)

모든 함수는 실패 시 graceful degradation — 빈 dict 또는 기본값 반환.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

try:
    import FinanceDataReader as fdr
    _FDR_AVAILABLE = True
except ImportError:
    _FDR_AVAILABLE = False

_UNIVERSE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "kr_universe.json")
_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "kr_market_state.json")


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────

def load_universe() -> list[dict]:
    """state/kr_universe.json 로드 → [{code, name, sector}, ...]"""
    try:
        with open(_UNIVERSE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("KOSPI_TOP50", [])
    except Exception:
        return []


def code_to_fdr(code: str) -> str:
    """'005930' → '005930' (FDR은 코드 그대로 사용)"""
    return code.replace(".KS", "").strip()


def code_to_yf(code: str) -> str:
    """'005930' → '005930.KS' (yfinance 형식)"""
    c = code.replace(".KS", "").strip()
    return f"{c}.KS"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _n_days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%Y-%m-%d")


# ─────────────────────────────────────────────
# KOSPI 지수
# ─────────────────────────────────────────────

def fetch_kospi_index() -> dict:
    """KOSPI 지수: close, SMA200, 52주 고저, ratio.

    Returns:
        {"close": float, "sma200": float, "kospi_vs_sma200": float,
         "52w_high": float, "52w_low": float, "change_1d_pct": float}
    """
    try:
        start = _n_days_ago(300)
        if _FDR_AVAILABLE:
            df = fdr.DataReader("KS11", start)
        else:
            df = yf.download("^KS11", start=start, progress=False)

        if df is None or df.empty:
            return {}

        close_col = "Close" if "Close" in df.columns else df.columns[3]
        closes = df[close_col].dropna()

        if len(closes) < 5:
            return {}

        sma200 = float(closes.tail(200).mean()) if len(closes) >= 200 else float(closes.mean())
        current = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else current

        return {
            "close": round(current, 2),
            "sma200": round(sma200, 2),
            "kospi_vs_sma200": round(current / sma200, 4) if sma200 > 0 else 1.0,
            "52w_high": round(float(closes.tail(252).max()), 2),
            "52w_low": round(float(closes.tail(252).min()), 2),
            "change_1d_pct": round((current - prev) / prev * 100, 2) if prev > 0 else 0.0,
        }
    except Exception as e:
        print(f"[kr_data] KOSPI 지수 fetch 실패: {e}")
        return {}


# ─────────────────────────────────────────────
# VKOSPI (한국판 VIX)
# ─────────────────────────────────────────────

def fetch_vkospi() -> dict:
    """VKOSPI 수준.

    yfinance ^VKOSPI 시도 → 실패 시 KOSPI 21일 실현변동성으로 추정.

    Returns:
        {"level": float, "source": "vkospi"|"estimated"}
    """
    try:
        tk = yf.Ticker("^VKOSPI")
        hist = tk.history(period="5d")
        if not hist.empty:
            level = float(hist["Close"].iloc[-1])
            return {"level": round(level, 2), "source": "vkospi"}
    except Exception:
        pass

    # fallback: KOSPI 21일 실현변동성 * sqrt(252) * 100
    try:
        start = _n_days_ago(60)
        if _FDR_AVAILABLE:
            df = fdr.DataReader("KS11", start)
        else:
            df = yf.download("^KS11", start=start, progress=False)

        close_col = "Close" if "Close" in df.columns else df.columns[3]
        closes = df[close_col].dropna()
        daily_ret = closes.pct_change().dropna()
        if len(daily_ret) >= 10:
            vol = float(daily_ret.tail(21).std()) * (252 ** 0.5) * 100
            return {"level": round(vol, 2), "source": "estimated"}
    except Exception as e:
        print(f"[kr_data] VKOSPI 추정 실패: {e}")

    return {"level": 20.0, "source": "default"}


# ─────────────────────────────────────────────
# KRW/USD 환율
# ─────────────────────────────────────────────

def fetch_usdkrw() -> dict:
    """원달러 환율.

    Returns:
        {"rate": float, "20d_change_pct": float, "sma50": float}
        20d_change_pct > 0 → 원화 약세 (수출주에 긍정적)
    """
    try:
        start = _n_days_ago(80)
        if _FDR_AVAILABLE:
            df = fdr.DataReader("USD/KRW", start)
        else:
            df = yf.download("KRW=X", start=start, progress=False)

        if df is None or df.empty:
            return {}

        close_col = "Close" if "Close" in df.columns else df.columns[3]
        closes = df[close_col].dropna()

        if len(closes) < 5:
            return {}

        current = float(closes.iloc[-1])
        past20 = float(closes.iloc[-20]) if len(closes) >= 20 else float(closes.iloc[0])
        sma50 = float(closes.tail(50).mean()) if len(closes) >= 50 else float(closes.mean())

        return {
            "rate": round(current, 1),
            "20d_change_pct": round((current - past20) / past20 * 100, 2) if past20 > 0 else 0.0,
            "sma50": round(sma50, 1),
        }
    except Exception as e:
        print(f"[kr_data] KRW/USD fetch 실패: {e}")
        return {}


# ─────────────────────────────────────────────
# 한국은행 기준금리 (ECOS API or 고정값)
# ─────────────────────────────────────────────

def fetch_bok_rate() -> dict:
    """한국은행 기준금리.

    ECOS_API_KEY 있으면 ECOS API 사용.
    없으면 WebFetch fallback (bok.or.kr) — 실패 시 3.00% 기본값.

    Returns:
        {"rate": float, "source": "ecos"|"web"|"default", "last_change": str}
    """
    api_key = os.environ.get("ECOS_API_KEY", "")

    if api_key:
        try:
            # ECOS 통계: 기준금리 (722Y001, 일별)
            start = _n_days_ago(90).replace("-", "")
            end = datetime.now().strftime("%Y%m%d")
            url = (
                f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr"
                f"/1/10/722Y001/D/{start}/{end}/0101000"
            )
            resp = requests.get(url, timeout=10)
            data = resp.json()
            rows = data.get("StatisticSearch", {}).get("row", [])
            if rows:
                latest = rows[-1]
                rate = float(latest.get("DATA_VALUE", 3.0))
                date = latest.get("TIME", "")
                return {"rate": rate, "source": "ecos", "last_change": date}
        except Exception as e:
            print(f"[kr_data] ECOS API 실패: {e}")

    # naver 금융에서 기준금리 확인 (fallback)
    try:
        resp = requests.get(
            "https://finance.naver.com/marketindex/",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        # 단순 패턴 검색 — "3.00%" 형태
        match = re.search(r"기준금리.*?(\d+\.\d+)", resp.text)
        if match:
            rate = float(match.group(1))
            return {"rate": rate, "source": "web", "last_change": ""}
    except Exception:
        pass

    # 기본값: 현재 한국 기준금리 (2026-04-16 기준 3.00%)
    return {"rate": 3.00, "source": "default", "last_change": ""}


# ─────────────────────────────────────────────
# 개별 종목 OHLCV + 기본 지표
# ─────────────────────────────────────────────

def fetch_kr_stock(code: str, period_days: int = 120) -> dict:
    """단일 종목 OHLCV + 기술 지표.

    Args:
        code: "005930" (6자리 코드)
        period_days: 조회 기간 (일)

    Returns:
        {"code", "name", "price", "change_1d_pct", "volume",
         "sma20", "sma60", "sma200",
         "rsi14", "macd", "macd_signal", "bb_pct_b",
         "per", "pbr", "market_cap_bn", "dividend_yield"}
    """
    fdr_code = code_to_fdr(code)
    yf_code = code_to_yf(code)
    start = _n_days_ago(period_days + 50)

    result: dict = {"code": fdr_code}

    # OHLCV (FDR 우선)
    df = None
    try:
        if _FDR_AVAILABLE:
            df = fdr.DataReader(fdr_code, start)
    except Exception:
        pass

    if df is None or df.empty:
        try:
            df = yf.download(yf_code, start=start, progress=False)
        except Exception as e:
            print(f"[kr_data] {code} OHLCV 실패: {e}")
            return result

    if df is None or df.empty:
        return result

    close_col = "Close" if "Close" in df.columns else df.columns[3]
    vol_col = "Volume" if "Volume" in df.columns else None

    closes = df[close_col].dropna()
    if len(closes) < 5:
        return result

    current = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    result["price"] = round(current, 0)
    result["change_1d_pct"] = round((current - prev) / prev * 100, 2) if prev > 0 else 0.0

    if vol_col and vol_col in df.columns:
        result["volume"] = int(df[vol_col].iloc[-1])

    # 이동평균
    for n, key in [(20, "sma20"), (60, "sma60"), (200, "sma200")]:
        if len(closes) >= n:
            result[key] = round(float(closes.tail(n).mean()), 0)

    # RSI-14
    try:
        delta = closes.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("inf"))
        rsi = 100 - (100 / (1 + rs))
        result["rsi14"] = round(float(rsi.iloc[-1]), 1)
    except Exception:
        pass

    # MACD (12,26,9)
    try:
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        result["macd"] = round(float(macd_line.iloc[-1]), 2)
        result["macd_signal"] = round(float(signal_line.iloc[-1]), 2)
    except Exception:
        pass

    # Bollinger Band %B
    try:
        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20
        bb_range = upper - lower
        pct_b = (closes - lower) / bb_range.replace(0, float("nan"))
        result["bb_pct_b"] = round(float(pct_b.iloc[-1]), 3)
    except Exception:
        pass

    # 펀더멘털 (yfinance .info, partial coverage)
    try:
        tk = yf.Ticker(yf_code)
        info = tk.info
        if info:
            result["per"] = info.get("trailingPE") or info.get("forwardPE")
            result["pbr"] = info.get("priceToBook")
            mc = info.get("marketCap")
            if mc:
                result["market_cap_bn"] = round(mc / 1e8, 0)  # 억원 단위
            result["dividend_yield"] = info.get("dividendYield")
            result["name"] = info.get("shortName") or info.get("longName", fdr_code)
    except Exception:
        pass

    return result


# ─────────────────────────────────────────────
# 섹터별 종목 일괄 데이터
# ─────────────────────────────────────────────

def fetch_sector_stocks(sector: str) -> list[dict]:
    """특정 섹터 종목 전체 데이터 수집."""
    universe = load_universe()
    sector_stocks = [s for s in universe if s["sector"] == sector]
    results = []
    for stock in sector_stocks:
        data = fetch_kr_stock(stock["code"])
        data.update({"name": stock["name"], "sector": stock["sector"]})
        results.append(data)
        time.sleep(0.2)  # 레이트 리밋 방지
    return results


# ─────────────────────────────────────────────
# 외국인/기관 수급 (naver 금융 crawl)
# ─────────────────────────────────────────────

def fetch_foreign_flow(code: str) -> dict:
    """외국인/기관 20일 순매수 (naver 금융 크롤).

    Returns:
        {"foreign_20d_net": int, "institution_20d_net": int,
         "short_sell_ratio": float, "source": "naver"}
        실패 시 {} 반환 (graceful degradation)
    """
    fdr_code = code_to_fdr(code)
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={fdr_code}"
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=8,
        )
        if resp.status_code != 200:
            return {}

        # 외국인 누적 순매수 추출 (td.num, class=tah)
        # naver 페이지 구조: 외국인 보유 수량, 순매수 컬럼
        # 단순 패턴 매칭으로 첫번째 유의미한 숫자 추출
        text = resp.text
        # 외국인 순매수 패턴 찾기
        foreign_match = re.findall(r'class="tah[^"]*">([+\-]?[\d,]+)</td>', text)
        if foreign_match and len(foreign_match) >= 2:
            foreign_net = int(foreign_match[0].replace(",", "").replace("+", ""))
            institution_net = int(foreign_match[1].replace(",", "").replace("+", ""))
            return {
                "foreign_20d_net": foreign_net,
                "institution_20d_net": institution_net,
                "source": "naver",
            }
    except Exception as e:
        print(f"[kr_data] 수급 crawl 실패 ({code}): {e}")

    return {}


# ─────────────────────────────────────────────
# DART 공시 (선택)
# ─────────────────────────────────────────────

def fetch_dart_disclosures(corp_code: str) -> list[dict]:
    """DART 공시 목록 (DART_API_KEY 필요).

    Returns:
        list[{"rcept_no", "corp_name", "report_nm", "rcept_dt"}]
        DART_API_KEY 없으면 [] 반환
    """
    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        return []

    try:
        url = "https://opendart.fss.or.kr/api/list.json"
        params = {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bgn_de": _n_days_ago(90).replace("-", ""),
            "end_de": datetime.now().strftime("%Y%m%d"),
            "pblntf_ty": "A",  # 정기공시
            "page_count": 10,
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "000":
            return data.get("list", [])
    except Exception as e:
        print(f"[kr_data] DART 공시 실패: {e}")

    return []


def fetch_dart_financials(corp_code: str, year: int = 2024) -> dict:
    """DART 재무제표 (DART_API_KEY 필요).

    Returns 주요 재무 지표: {"revenue", "operating_profit", "net_profit",
                              "total_assets", "total_equity", "roe", "source"}
    """
    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        return {}

    try:
        url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
        params = {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # 사업보고서
            "fs_div": "OFS",        # 별도 재무제표
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        if data.get("status") != "000":
            return {}

        rows = {r["account_nm"]: r["thstrm_amount"] for r in data.get("list", [])}

        def to_billion(key: str) -> Optional[float]:
            val = rows.get(key, "")
            if not val:
                return None
            try:
                return round(int(val.replace(",", "")) / 1e8, 1)  # 억원
            except Exception:
                return None

        revenue = to_billion("매출액")
        op_profit = to_billion("영업이익")
        net_profit = to_billion("당기순이익")
        total_assets = to_billion("자산총계")
        total_equity = to_billion("자본총계")

        roe = None
        if net_profit and total_equity and total_equity > 0:
            roe = round(net_profit / total_equity * 100, 1)

        return {
            "revenue_bn": revenue,
            "operating_profit_bn": op_profit,
            "net_profit_bn": net_profit,
            "total_assets_bn": total_assets,
            "total_equity_bn": total_equity,
            "roe_pct": roe,
            "year": year,
            "source": "dart",
        }
    except Exception as e:
        print(f"[kr_data] DART 재무 실패: {e}")
        return {}


# ─────────────────────────────────────────────
# 반도체 수출 (매크로 보정용)
# ─────────────────────────────────────────────

def fetch_semiconductor_export_yoy() -> dict:
    """반도체 수출 YoY (한국관세청 / 무역협회 WebSearch 기반).

    Returns:
        {"yoy_pct": float|None, "source": str}
    """
    # 환경변수로 수동 설정 가능 (가장 최신 값)
    manual = os.environ.get("KR_SEMICONDUCTOR_EXPORT_YOY", "")
    if manual:
        try:
            return {"yoy_pct": float(manual), "source": "env"}
        except ValueError:
            pass

    # 기본값: 데이터 없음 (에이전트가 WebSearch로 실시간 수집)
    return {"yoy_pct": None, "source": "unknown"}


# ─────────────────────────────────────────────
# 전체 시장 스냅샷
# ─────────────────────────────────────────────

def build_market_snapshot(force_refresh: bool = False) -> dict:
    """시장 스냅샷 수집 및 캐시.

    state/kr_market_state.json에 저장. 6시간 이내면 캐시 재사용.

    Returns:
        {"kospi": {...}, "vkospi": {...}, "usdkrw": {...},
         "bok_rate": {...}, "timestamp": str, "cached": bool}
    """
    # 캐시 확인
    if not force_refresh and os.path.exists(_STATE_PATH):
        try:
            with open(_STATE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
            ts = datetime.fromisoformat(cached.get("timestamp", "2000-01-01"))
            if datetime.now() - ts < timedelta(hours=6):
                cached["cached"] = True
                return cached
        except Exception:
            pass

    print("[kr_data] 시장 스냅샷 수집 중...")
    snapshot = {
        "kospi": fetch_kospi_index(),
        "vkospi": fetch_vkospi(),
        "usdkrw": fetch_usdkrw(),
        "bok_rate": fetch_bok_rate(),
        "semiconductor_export": fetch_semiconductor_export_yoy(),
        "timestamp": datetime.now().isoformat(),
        "cached": False,
    }

    # 저장
    try:
        with open(_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[kr_data] 스냅샷 저장 실패: {e}")

    return snapshot
