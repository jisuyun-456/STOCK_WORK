"""Google News RSS — 종목별 뉴스 검색 수집기.

Google News RSS 검색 엔드포인트를 사용해 특정 종목에 대한 최신 기사를 수집한다.
CNBC/Reuters/Bloomberg/WSJ/MarketWatch 등 여러 소스를 집계해서 반환하므로
단일 소스(yfinance) 대비 커버리지가 훨씬 넓다.

URL 패턴:
    https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en

무료, API 키 불필요, 1분당 수십 회 호출 가능 (레이트 리밋 느슨함).
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

_SEARCH_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en-US&gl=US&ceid=US:en"
)
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
_TIMEOUT = 10
_MAX_BODY_CHARS = 500


def _strip_html(text: str) -> str:
    """HTML 태그/엔티티 제거 후 공백 정리."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_BODY_CHARS]


def _parse_pub_date(date_str: str) -> str:
    """RFC 822 날짜 → ISO 8601 UTC 문자열."""
    if not date_str:
        return ""
    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return date_str


def fetch_google_news_symbol(symbol: str, max_articles: int = 15) -> list[dict]:
    """종목별 Google News RSS 기사 수집.

    Args:
        symbol: 종목 티커 (예: "AAPL")
        max_articles: 최대 기사 수 (기본 15)

    Returns:
        [{"title", "body", "url", "published", "source"}, ...]
        실패 시 빈 리스트.
    """
    # 검색어: "{symbol} stock" — 주식 관련 기사만 필터
    query = f"{symbol}+stock+news"
    url = _SEARCH_URL.format(query=query)

    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  [google_news] {symbol} RSS 요청 실패: {exc}")
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as exc:
        print(f"  [google_news] {symbol} XML 파싱 실패: {exc}")
        return []

    # RSS 2.0 포맷: rss/channel/item
    items = root.findall(".//item")
    articles: list[dict] = []

    for item in items[:max_articles]:
        try:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pubdate_el = item.find("pubDate")
            source_el = item.find("source")

            title = (title_el.text or "").strip() if title_el is not None else ""
            url_val = (link_el.text or "").strip() if link_el is not None else ""
            body = _strip_html(desc_el.text) if desc_el is not None else ""
            published = _parse_pub_date(pubdate_el.text) if pubdate_el is not None else ""

            # Google News 제목 포맷: "기사제목 - 소스명"
            # 소스명을 source 필드로 추출, 제목에서는 제거
            source_name = "GoogleNews"
            if source_el is not None and source_el.text:
                source_name = source_el.text.strip()
            elif " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) == 2:
                    title, source_name = parts[0].strip(), parts[1].strip()

            if not title:
                continue

            articles.append({
                "title": title,
                "body": body,
                "url": url_val,
                "published": published,
                "source": source_name,
            })
        except Exception as exc:
            print(f"  [google_news] item 파싱 오류 (skip): {exc}")
            continue

    return articles


if __name__ == "__main__":
    # CLI 테스트
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    results = fetch_google_news_symbol(sym, max_articles=10)
    print(f"{sym}: {len(results)}건")
    for i, art in enumerate(results, 1):
        print(f"{i}. [{art['source']}] {art['title']}")
