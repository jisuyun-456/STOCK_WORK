"""Sentiment analysis — Gemini API로 뉴스 감성 분석.

fetch_all_news() 결과를 받아 종목별로 Gemini 1회 호출하여
score(-1.0~+1.0)와 한 줄 요약(summary)을 반환한다.
GEMINI_API_KEY 미설정 시 score=0.0 (NEUTRAL) fallback.
429 rate limit 시 exponential backoff로 최대 3회 재시도.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

# Gemini SDK 임포트 (없으면 graceful fallback)
try:
    from google import genai as _genai_client_module
    _GENAI_AVAILABLE = True
except ImportError:  # pragma: no cover
    _genai_client_module = None  # type: ignore
    _GENAI_AVAILABLE = False
    print("[sentiment] WARNING: google-genai not installed -- all scores will be 0.0")


_GEMINI_MODEL = "gemini-2.0-flash"
_MAX_ARTICLES_PER_PROMPT = 20  # 프롬프트 길이 제한
_MAX_RETRIES = 3
_BACKOFF_BASE = 10.0  # 429 시 10초, 20초, 40초 대기


@dataclass
class SentimentResult:
    """종목 뉴스 감성 분석 결과."""

    symbol: str
    score: float          # -1.0 (극부정) ~ +1.0 (극긍정)
    summary: str          # 한 줄 요약
    article_count: int    # 분석된 기사 수
    error: str = ""       # 에러 발생 시 메시지


def _build_prompt(symbol: str, articles: list[dict]) -> str:
    """Gemini에 전달할 감성 분석 프롬프트를 생성한다.

    Args:
        symbol: 종목 티커.
        articles: 기사 목록 (title, body 포함).

    Returns:
        완성된 프롬프트 문자열.
    """
    lines = []
    for i, article in enumerate(articles[:_MAX_ARTICLES_PER_PROMPT], start=1):
        title = article.get("title", "")
        body = article.get("body", "")
        source = article.get("source", "")
        snippet = body[:800] if body else ""  # Phase 7: 200→800자
        source_tag = f" ({source})" if source else ""
        entry = f"{i}. [{title}]{source_tag}"
        if snippet:
            entry += f" {snippet}"
        lines.append(entry)

    news_block = "\n".join(lines)
    count = len(articles[:_MAX_ARTICLES_PER_PROMPT])

    prompt = (
        f"다음 {symbol} 관련 뉴스 {count}건의 전반적 감성을 분석하세요.\n"
        f"JSON으로만 반환하세요 (마크다운 코드블록 없이): "
        f'{{\"score\": float(-1~1), \"summary\": \"한 줄 요약\"}}\n\n'
        f"score 기준: -1.0=극부정, -0.5=부정, 0.0=중립, 0.5=긍정, 1.0=극긍정\n\n"
        f"뉴스:\n{news_block}"
    )
    return prompt


def _parse_gemini_response(response_text: str) -> tuple[float, str]:
    """Gemini 응답 텍스트에서 score와 summary를 파싱한다.

    JSON 파싱 실패 시 정규식으로 숫자를 추출하고, 그것도 실패하면 (0.0, "") 반환.

    Args:
        response_text: Gemini가 반환한 텍스트.

    Returns:
        (score: float, summary: str) 튜플.
    """
    # 마크다운 코드블록 제거
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", response_text).strip()

    try:
        data = json.loads(clean)
        score = float(data.get("score", 0.0))
        score = max(-1.0, min(1.0, score))  # clamp
        summary = str(data.get("summary", ""))
        return score, summary
    except (json.JSONDecodeError, ValueError, KeyError):
        pass

    # 정규식 fallback: 첫 번째 부동소수점 추출
    match = re.search(r"[-+]?\d+\.?\d*", clean)
    score = float(match.group()) if match else 0.0
    score = max(-1.0, min(1.0, score))
    return score, ""


def _get_client():
    """Gemini Client 인스턴스를 반환한다.

    GEMINI_API_KEY가 없거나 SDK 미설치 시 None 반환.
    """
    if not _GENAI_AVAILABLE:
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    return _genai_client_module.Client(api_key=api_key)


def analyze_sentiment(symbol: str, articles: list[dict]) -> SentimentResult:
    """종목의 뉴스 기사들을 Gemini로 감성 분석한다.

    기사 목록을 하나의 프롬프트로 묶어 Gemini 1회 호출한다.
    429 rate limit 시 exponential backoff로 최대 3회 재시도.
    API 키 미설정·SDK 미설치·호출 실패 시 score=0.0 (NEUTRAL)을 반환하며
    error 필드에 사유를 기록한다.

    Args:
        symbol: 종목 티커.
        articles: fetch_news()가 반환한 기사 목록.

    Returns:
        SentimentResult 인스턴스.
    """
    print(f"[sentiment] {symbol} 감성 분석 중 ({len(articles)}건)...")

    if not articles:
        return SentimentResult(
            symbol=symbol,
            score=0.0,
            summary="뉴스 없음",
            article_count=0,
            error="no_articles",
        )

    # API 키 확인
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print(f"[sentiment] {symbol}: GEMINI_API_KEY 미설정 → NEUTRAL fallback")
        return SentimentResult(
            symbol=symbol,
            score=0.0,
            summary="",
            article_count=len(articles),
            error="GEMINI_API_KEY not set",
        )

    client = _get_client()
    if client is None:
        return SentimentResult(
            symbol=symbol,
            score=0.0,
            summary="",
            article_count=len(articles),
            error="Gemini SDK not available or API key not set",
        )

    prompt = _build_prompt(symbol, articles)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=prompt,
            )
            score, summary = _parse_gemini_response(response.text)
            print(f"[sentiment] {symbol}: score={score:.2f}, summary={summary[:50]}")
            return SentimentResult(
                symbol=symbol,
                score=score,
                summary=summary,
                article_count=len(articles[:_MAX_ARTICLES_PER_PROMPT]),
            )
        except Exception as exc:
            err_str = str(exc)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_BASE * (2 ** attempt)
                print(f"[sentiment] {symbol}: 429 rate limit — retry {attempt + 1}/{_MAX_RETRIES} in {wait:.0f}s")
                time.sleep(wait)
            else:
                print(f"[sentiment] {symbol} Gemini 호출 실패: {exc}")
                return SentimentResult(
                    symbol=symbol,
                    score=0.0,
                    summary="",
                    article_count=len(articles),
                    error=str(exc),
                )

    return SentimentResult(
        symbol=symbol, score=0.0, summary="", article_count=len(articles),
        error="max retries exceeded",
    )


def analyze_all_sentiment(news_data: dict[str, list[dict]]) -> dict[str, SentimentResult]:
    """fetch_all_news() 결과를 받아 종목별 감성 분석을 수행한다.

    각 키(종목 티커 또는 "_MACRO")에 대해 analyze_sentiment()를 호출한다.
    개별 종목 실패는 score=0.0 SentimentResult로 처리되며 전체에 영향을 주지 않는다.

    Args:
        news_data: fetch_all_news() 반환값.
                   {"AAPL": [...], "MSFT": [...], "_MACRO": [...]}

    Returns:
        {"AAPL": SentimentResult, "_MACRO": SentimentResult, ...}
    """
    print(f"[sentiment] 일괄 감성 분석 시작: {list(news_data.keys())}")
    results: dict[str, SentimentResult] = {}

    for symbol, articles in news_data.items():
        results[symbol] = analyze_sentiment(symbol, articles)

    print(f"[sentiment] 일괄 감성 분석 완료: {len(results)}개 종목")
    return results
