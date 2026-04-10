"""News fetcher — yfinance 뉴스 수집 + BeautifulSoup 본문 스크래핑.

yf.Ticker(symbol).news 에서 URL 목록을 수집하고,
requests로 HTML을 다운로드한 뒤 BeautifulSoup으로 본문을 추출한다.
페이월/접근 실패 시 body=""로 graceful degradation.
"""

from __future__ import annotations

import datetime
import time

import requests
import yfinance as yf

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BS4_AVAILABLE = False
    print("[news.fetcher] WARNING: beautifulsoup4 not installed — body will always be empty")

# HTTP 요청 공통 헤더 (봇 차단 방지)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_REQUEST_TIMEOUT = 10   # 초
_BODY_MAX_CHARS = 3000  # 기사당 본문 최대 문자 수 (Phase 7: 500→3000)
_TITLE_DEDUP_THRESHOLD = 0.8  # 제목 유사도 기반 중복 제거 임계값


def _dedup_by_title(articles: list[dict], threshold: float = _TITLE_DEDUP_THRESHOLD) -> list[dict]:
    """제목 유사도 기반 중복 제거 (SequenceMatcher).

    동일 뉴스가 여러 소스에서 약간 다른 제목으로 수집될 때 80%+ 유사도면 제거.
    """
    from difflib import SequenceMatcher
    unique: list[dict] = []
    for art in articles:
        title = art.get("title", "")
        if not title:
            unique.append(art)
            continue
        is_dup = any(
            SequenceMatcher(None, title.lower(), u.get("title", "").lower()).ratio() >= threshold
            for u in unique
        )
        if not is_dup:
            unique.append(art)
    return unique


def _scrape_body(url: str) -> str:
    """URL에서 기사 본문을 스크래핑한다.

    <article> > <p> 순으로 탐색하며 최대 _BODY_MAX_CHARS 자까지 반환한다.
    페이월·타임아웃·파싱 오류 시 빈 문자열을 반환한다 (graceful degradation).

    Args:
        url: 기사 URL.

    Returns:
        본문 텍스트 (최대 500자) 또는 "".
    """
    if not _BS4_AVAILABLE:
        return ""

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        # 개별 기사 실패 — 전체에 영향 없음
        print(f"  [fetcher] body 스크래핑 실패 ({url[:60]}...): {exc}")
        return ""

    try:
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1순위: <article> 태그 내부 <p>
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
        else:
            # 2순위: 전체 <p> 태그
            paragraphs = soup.find_all("p")

        body = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
        return body[:_BODY_MAX_CHARS]
    except Exception as exc:
        print(f"  [fetcher] HTML 파싱 실패 ({url[:60]}...): {exc}")
        return ""


def fetch_news(symbol: str, max_articles: int = 30) -> list[dict]:
    """종목의 최신 뉴스를 yfinance에서 수집하고 본문을 스크래핑한다.

    yf.Ticker(symbol).news 에서 URL 목록을 가져온 뒤,
    requests + BeautifulSoup으로 각 기사 본문을 최대 500자 추출한다.
    페이월·타임아웃 등 접근 실패 기사는 body=""로 처리하며 전체 실패를 막는다.

    Args:
        symbol: 종목 티커 (예: "AAPL").
        max_articles: 수집할 최대 기사 수 (기본 30).

    Returns:
        [{"title": str, "body": str, "url": str, "published": str}, ...]
        실패 시 빈 리스트.
    """
    print(f"[fetcher] {symbol} 뉴스 수집 중 (최대 {max_articles}건)...")
    try:
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news
    except Exception as exc:
        print(f"[fetcher] {symbol} yfinance 뉴스 조회 실패: {exc}")
        return []

    if not raw_news:
        print(f"[fetcher] {symbol}: 뉴스 없음")
        return []

    articles: list[dict] = []
    for item in raw_news[:max_articles]:
        try:
            # yfinance news 항목 구조 (버전마다 약간 다를 수 있음)
            content = item.get("content", item)  # 신규 API 래퍼 대응
            if isinstance(content, dict):
                title = content.get("title", item.get("title", ""))
                url = (
                    content.get("canonicalUrl", {}).get("url", "")
                    or content.get("clickThroughUrl", {}).get("url", "")
                    or item.get("link", "")
                )
                pub_ts = content.get("pubDate", "") or item.get("providerPublishTime", "")
            else:
                title = item.get("title", "")
                url = item.get("link", "")
                pub_ts = item.get("providerPublishTime", "")

            # published 타임스탬프 → ISO 문자열
            if isinstance(pub_ts, (int, float)):
                published = datetime.datetime.fromtimestamp(pub_ts, tz=datetime.timezone.utc).isoformat()
            else:
                published = str(pub_ts)

            if not title:
                continue

            body = _scrape_body(url) if url else ""

            articles.append({
                "title": title,
                "body": body,
                "url": url,
                "published": published,
            })
        except Exception as exc:
            print(f"  [fetcher] 기사 파싱 오류 (skip): {exc}")
            continue

    articles = _dedup_by_title(articles)
    print(f"[fetcher] {symbol}: {len(articles)}건 수집 완료")
    return articles


def fetch_macro_news() -> list[dict]:
    """SPY, ^VIX 관련 매크로 뉴스를 수집한다 (합산 최대 30건).

    SPY(S&P500 ETF) 와 ^VIX(변동성지수) 뉴스를 각 15건씩 수집하고 합쳐서 반환한다.
    중복 URL은 제거한다.

    Returns:
        [{"title": str, "body": str, "url": str, "published": str}, ...]
    """
    print("[fetcher] 매크로 뉴스 수집 중 (SPY + ^VIX)...")
    spy_news = fetch_news("SPY", max_articles=15)
    vix_news = fetch_news("^VIX", max_articles=15)

    # URL 기준 중복 제거
    seen: set[str] = set()
    combined: list[dict] = []
    for article in spy_news + vix_news:
        url = article.get("url", "")
        if url and url in seen:
            continue
        seen.add(url)
        combined.append(article)

    print(f"[fetcher] 매크로: {len(combined)}건 수집 완료")
    return combined[:30]


def fetch_rss_news(max_articles_per_source: int = 15) -> list[dict]:
    """6개 RSS 소스에서 금융 뉴스를 병렬 수집한다.

    Reuters, AP, CNBC, MarketWatch, NYT, WSJ 소스를 ThreadPoolExecutor로
    병렬 호출하여 기사를 수집한다. 개별 소스 실패는 skip하며 전체에 영향 없음.

    Args:
        max_articles_per_source: 소스당 최대 기사 수 (기본 15).

    Returns:
        [{"title", "body", "url", "published", "source"}, ...]
        전체 실패 시 빈 리스트.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    try:
        from news.sources import ALL_SOURCES
    except ImportError as exc:
        print(f"[fetcher] RSS sources import 실패: {exc}")
        return []

    print(f"[fetcher] RSS 뉴스 수집 중 ({len(ALL_SOURCES)}개 소스)...")
    articles: list[dict] = []

    def _fetch_source(source_cls):
        try:
            source = source_cls()
            return source.fetch(max_articles=max_articles_per_source)
        except Exception as exc:
            print(f"  [fetcher] {source_cls.name} 실패: {exc}")
            return []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(_fetch_source, cls): cls.name
            for cls in ALL_SOURCES
        }
        for future in as_completed(futures, timeout=60):
            source_name = futures[future]
            try:
                result = future.result(timeout=10)
                articles.extend(result)
                if result:
                    print(f"  [fetcher] {source_name}: {len(result)}건")
            except Exception as exc:
                print(f"  [fetcher] {source_name} 타임아웃/실패: {exc}")

    print(f"[fetcher] RSS 수집 완료: 총 {len(articles)}건")
    return articles


def fetch_macro_news_enhanced() -> list[dict]:
    """yfinance + RSS 소스를 병합하여 풍부한 매크로 뉴스를 수집한다.

    기존 yfinance(SPY+VIX) 뉴스에 6개 RSS 소스를 추가하여 최대 60건의
    매크로 뉴스를 반환한다. URL 기준 중복 제거.

    Returns:
        [{"title", "body", "url", "published", "source"}, ...]
    """
    print("[fetcher] 강화 매크로 뉴스 수집 중 (yfinance + RSS)...")

    # 1) 기존 yfinance 뉴스 (source 필드 추가)
    yf_articles = []
    try:
        spy_news = fetch_news("SPY", max_articles=15)
        vix_news = fetch_news("^VIX", max_articles=15)
        for article in spy_news + vix_news:
            article.setdefault("source", "yfinance")
            yf_articles.append(article)
    except Exception as exc:
        print(f"[fetcher] yfinance 뉴스 실패: {exc}")

    # 2) RSS 뉴스
    rss_articles = fetch_rss_news(max_articles_per_source=15)

    # 3) 병합 + URL 중복 제거
    seen: set[str] = set()
    combined: list[dict] = []
    for article in yf_articles + rss_articles:
        url = article.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        combined.append(article)

    # 제목 유사도 기반 중복 제거
    before_dedup = len(combined)
    combined = _dedup_by_title(combined)
    if before_dedup != len(combined):
        print(f"[fetcher] 제목 유사도 dedup: {before_dedup} → {len(combined)}건")

    source_counts = {}
    for a in combined:
        s = a.get("source", "unknown")
        source_counts[s] = source_counts.get(s, 0) + 1

    print(f"[fetcher] 강화 매크로: {len(combined)}건 (소스별: {source_counts})")
    return combined[:60]


def fetch_all_news(symbols: list[str]) -> dict[str, list[dict]]:
    """여러 종목 + 매크로 뉴스를 일괄 수집한다.

    각 종목에 대해 fetch_news()를 호출하고 _MACRO 키로 매크로 뉴스를 추가한다.
    개별 종목 실패는 빈 리스트로 처리되며 전체에 영향을 주지 않는다.

    Args:
        symbols: 종목 티커 리스트 (예: ["AAPL", "MSFT"]).

    Returns:
        {"AAPL": [...], "MSFT": [...], "_MACRO": [...]}
        실패 종목은 빈 리스트.
    """
    print(f"[fetcher] 일괄 수집 시작: {symbols} + _MACRO")
    result: dict[str, list[dict]] = {}

    for symbol in symbols:
        result[symbol] = fetch_news(symbol, max_articles=30)
        time.sleep(0.3)  # yfinance rate-limit 방지

    result["_MACRO"] = fetch_macro_news()

    total = sum(len(v) for v in result.values())
    print(f"[fetcher] 일괄 수집 완료: 총 {total}건 ({len(result)}개 키)")
    return result
