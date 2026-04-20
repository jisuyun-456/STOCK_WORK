"""KR Research Division 4-에이전트 병렬 실행기.

두 가지 모드:
  rules (기본): 데이터 기반 규칙, LLM 호출 없음 ($0)
  claude:       Claude API 호출 (KR_RESEARCH_AGENTS=claude)

각 에이전트는 KRVerdict를 반환.
direction: "AGREE" | "DISAGREE" | "CAUTION"
conviction: "STRONG" | "MODERATE" | "WEAK"
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from kr_research.kr_data_fetcher import fetch_kr_stock, fetch_foreign_flow
from kr_research.kr_models import KRVerdict, KRRegimeDetection

_MODE = os.environ.get("KR_RESEARCH_AGENTS", "rules")

AGENT_NAMES = [
    "kr_equity_research",
    "kr_technical_strategist",
    "kr_macro_economist",
    "kr_sector_analyst",
]

CONVICTION_WEIGHTS = {"STRONG": 1.0, "MODERATE": 0.6, "WEAK": 0.3}


# ─────────────────────────────────────────────
# 규칙 기반 에이전트 (rules mode)
# ─────────────────────────────────────────────

def _rules_equity(stock: dict, regime: KRRegimeDetection) -> KRVerdict:
    """PBR/PER/배당 기반 밸류에이션 판단."""
    symbol = stock.get("code", "")
    per = stock.get("per")
    pbr = stock.get("pbr")
    div_yield = stock.get("dividend_yield")

    metrics = {"per": per, "pbr": pbr, "dividend_yield": div_yield}
    score = 0.0
    reasons = []

    if pbr is not None:
        if pbr < 1.0:
            score += 0.12
            reasons.append(f"PBR {pbr:.2f} (순자산 이하)")
        elif pbr < 1.5:
            score += 0.06
            reasons.append(f"PBR {pbr:.2f} (저평가 구간)")
        elif pbr > 4.0:
            score -= 0.10
            reasons.append(f"PBR {pbr:.2f} (고평가)")

    if per is not None:
        if per < 10:
            score += 0.08
            reasons.append(f"PER {per:.1f} (저PER)")
        elif per > 30:
            score -= 0.08
            reasons.append(f"PER {per:.1f} (고PER)")

    if div_yield is not None and div_yield > 0.03:
        score += 0.05
        reasons.append(f"배당수익률 {div_yield*100:.1f}%")

    direction, conviction = _score_to_verdict(score)
    return KRVerdict(
        agent="kr_equity_research",
        symbol=symbol,
        direction=direction,
        confidence_delta=round(score, 3),
        conviction=conviction,
        reasoning=". ".join(reasons) or "밸류에이션 데이터 부족 — CAUTION",
        key_metrics=metrics,
        timestamp=datetime.now().isoformat(),
    )


def _rules_technical(stock: dict, regime: KRRegimeDetection) -> KRVerdict:
    """SMA/RSI/MACD/BB%B 기반 기술적 판단 + 수급."""
    symbol = stock.get("code", "")
    price = stock.get("price", 0)
    sma20 = stock.get("sma20", 0)
    sma60 = stock.get("sma60", 0)
    sma200 = stock.get("sma200", 0)
    rsi = stock.get("rsi14")
    macd = stock.get("macd")
    macd_sig = stock.get("macd_signal")
    bb = stock.get("bb_pct_b")

    score = 0.0
    reasons = []
    metrics = {"rsi14": rsi, "macd": macd, "sma200": sma200, "bb_pct_b": bb}

    # 추세 (SMA200)
    if price and sma200 and sma200 > 0:
        vs_sma200 = price / sma200
        if vs_sma200 > 1.05:
            score += 0.07
            reasons.append(f"SMA200 위 {vs_sma200:.2f}x")
        elif vs_sma200 < 0.95:
            score -= 0.07
            reasons.append(f"SMA200 아래 {vs_sma200:.2f}x")

    # RSI
    if rsi is not None:
        if rsi < 35:
            score += 0.05
            reasons.append(f"RSI {rsi:.0f} (과매도)")
        elif rsi > 70:
            score -= 0.05
            reasons.append(f"RSI {rsi:.0f} (과매수)")

    # MACD 크로스
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd > 0:
            score += 0.04
            reasons.append("MACD 골든크로스")
        elif macd < macd_sig and macd < 0:
            score -= 0.04
            reasons.append("MACD 데드크로스")

    # BB %B
    if bb is not None:
        if bb < 0.2:
            score += 0.03
            reasons.append(f"BB%B {bb:.2f} (밴드 하단)")
        elif bb > 0.8:
            score -= 0.03
            reasons.append(f"BB%B {bb:.2f} (밴드 상단)")

    # 수급 crawl (선택)
    flow = fetch_foreign_flow(symbol)
    if flow:
        foreign_net = flow.get("foreign_20d_net", 0)
        metrics["foreign_20d_net"] = foreign_net
        if foreign_net > 0:
            score += 0.03
            reasons.append(f"외국인 20일 순매수 +{foreign_net:,}")
        elif foreign_net < 0:
            score -= 0.03
            reasons.append(f"외국인 20일 순매도 {foreign_net:,}")

    direction, conviction = _score_to_verdict(score)
    return KRVerdict(
        agent="kr_technical_strategist",
        symbol=symbol,
        direction=direction,
        confidence_delta=round(score, 3),
        conviction=conviction,
        reasoning=". ".join(reasons) or "기술 지표 데이터 부족",
        key_metrics=metrics,
        timestamp=datetime.now().isoformat(),
    )


def _rules_macro(stock: dict, regime: KRRegimeDetection) -> KRVerdict:
    """Regime + KRW + BOK 기반 매크로 판단."""
    symbol = stock.get("code", "")
    score = 0.0
    reasons = []

    regime_score = {
        "BULL": 0.08,
        "EUPHORIA": 0.04,  # 고점 경고
        "NEUTRAL": 0.0,
        "BEAR": -0.08,
        "CRISIS": -0.15,
    }
    regime_str = regime.regime if regime else "NEUTRAL"
    r_score = regime_score.get(regime_str, 0.0)
    score += r_score
    reasons.append(f"KR Regime: {regime_str}")

    # KRW 약세 = 수출주 우호
    if regime and regime.usdkrw_20d_change > 2.0:
        score += 0.04
        reasons.append(f"원화 약세 {regime.usdkrw_20d_change:.1f}% (수출 수혜)")
    elif regime and regime.usdkrw_20d_change < -2.0:
        score -= 0.03
        reasons.append(f"원화 강세 {regime.usdkrw_20d_change:.1f}%")

    # 반도체 수출 보정
    if regime and regime.semiconductor_export_yoy is not None:
        yoy = regime.semiconductor_export_yoy
        if yoy > 30:
            score += 0.05
            reasons.append(f"반도체 수출 YoY +{yoy:.0f}%")
        elif yoy < -10:
            score -= 0.05
            reasons.append(f"반도체 수출 YoY {yoy:.0f}%")

    metrics = {
        "kr_regime": regime_str,
        "bok_rate": regime.bok_rate if regime else None,
        "usdkrw_change": regime.usdkrw_20d_change if regime else None,
    }

    direction, conviction = _score_to_verdict(score)
    return KRVerdict(
        agent="kr_macro_economist",
        symbol=symbol,
        direction=direction,
        confidence_delta=round(score, 3),
        conviction=conviction,
        reasoning=". ".join(reasons),
        key_metrics=metrics,
        timestamp=datetime.now().isoformat(),
    )


# 섹터별 모멘텀 바이어스 (수동 조정 가능)
_SECTOR_BIAS: dict[str, float] = {
    "반도체": 0.06,       # HBM 사이클
    "이차전지": 0.0,       # 중립 (과도 낙관 경계)
    "바이오": 0.02,
    "자동차": 0.03,
    "금융": 0.02,
    "인터넷/IT": 0.01,
    "화학/에너지": -0.02,
    "조선/기계": 0.04,
    "전자": 0.01,
    "K-콘텐츠": 0.01,
    "철강/소재": 0.0,
    "지주/건설": -0.01,
    "통신": 0.0,
    "유틸리티": 0.0,
    "필수소비재": 0.0,
    "운송": 0.0,
}


def _rules_sector(stock: dict, regime: KRRegimeDetection) -> KRVerdict:
    """섹터 순환 + 상대강도 기반 판단."""
    symbol = stock.get("code", "")
    sector = stock.get("sector", "")

    bias = _SECTOR_BIAS.get(sector, 0.0)
    # BULL/EUPHORIA면 성장 섹터 가중
    if regime and regime.regime in ("BULL", "EUPHORIA"):
        if sector in ("반도체", "이차전지", "바이오", "인터넷/IT"):
            bias += 0.02
    # BEAR/CRISIS면 방어 섹터 가중
    elif regime and regime.regime in ("BEAR", "CRISIS"):
        if sector in ("금융", "통신", "유틸리티", "필수소비재"):
            bias += 0.03
        elif sector in ("반도체", "이차전지"):
            bias -= 0.04

    score = bias
    reasons = [f"섹터: {sector} (바이어스 {bias:+.2f})"]
    if regime:
        reasons.append(f"Regime {regime.regime} 기반 조정")

    direction, conviction = _score_to_verdict(score)
    return KRVerdict(
        agent="kr_sector_analyst",
        symbol=symbol,
        direction=direction,
        confidence_delta=round(score, 3),
        conviction=conviction,
        reasoning=". ".join(reasons),
        key_metrics={"sector": sector, "sector_bias": bias},
        timestamp=datetime.now().isoformat(),
    )


def _score_to_verdict(score: float) -> tuple[str, str]:
    """점수 → (direction, conviction) 변환."""
    if score > 0.10:
        return "AGREE", "STRONG"
    elif score > 0.04:
        return "AGREE", "MODERATE"
    elif score > 0.01:
        return "AGREE", "WEAK"
    elif score < -0.10:
        return "DISAGREE", "STRONG"
    elif score < -0.04:
        return "DISAGREE", "MODERATE"
    elif score < -0.01:
        return "DISAGREE", "WEAK"
    else:
        return "CAUTION", "WEAK"


# ─────────────────────────────────────────────
# 병렬 실행
# ─────────────────────────────────────────────

def run_all_agents(
    code: str,
    stock_data: dict,
    regime: KRRegimeDetection,
    mode: Optional[str] = None,
) -> list[KRVerdict]:
    """4에이전트 병렬 실행 → KRVerdict 리스트 반환.

    Args:
        code:       종목 코드 ("005930")
        stock_data: fetch_kr_stock() 결과
        regime:     detect_kr_regime() 결과
        mode:       "rules" (기본) | "claude"

    Returns:
        list[KRVerdict] (4개, 실패 에이전트 제외)
    """
    mode = mode or _MODE

    if mode == "claude":
        # claude 모드: 에이전트 파일을 직접 호출하는 방식은 Claude Code에서 실행되므로
        # kr-commander 에이전트가 직접 Agent 도구로 dispatch. 여기서는 rules fallback.
        print("[kr_agent_runner] claude 모드 — Claude Code Agent 도구로 실행 필요. rules mode로 fallback.")

    # rules mode
    agent_fns = [
        ("kr_equity_research", lambda: _rules_equity(stock_data, regime)),
        ("kr_technical_strategist", lambda: _rules_technical(stock_data, regime)),
        ("kr_macro_economist", lambda: _rules_macro(stock_data, regime)),
        ("kr_sector_analyst", lambda: _rules_sector(stock_data, regime)),
    ]

    verdicts = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fn): name for name, fn in agent_fns}
        for future in as_completed(futures):
            name = futures[future]
            try:
                verdict = future.result(timeout=30)
                verdicts.append(verdict)
            except Exception as e:
                print(f"[kr_agent_runner] {name} 실패: {e}")

    return verdicts


def aggregate_verdicts(verdicts: list[KRVerdict]) -> dict:
    """KRVerdict[] → 가중 합산 결과.

    Returns:
        {"weighted_score": float, "agree": int, "disagree": int, "caution": int,
         "summary": str}
    """
    if not verdicts:
        return {"weighted_score": 0.0, "agree": 0, "disagree": 0, "caution": 0, "summary": "데이터 없음"}

    total_score = 0.0
    agree = disagree = caution = 0

    for v in verdicts:
        w = CONVICTION_WEIGHTS.get(v.conviction, 0.3)
        total_score += v.confidence_delta * w
        if v.direction == "AGREE":
            agree += 1
        elif v.direction == "DISAGREE":
            disagree += 1
        else:
            caution += 1

    # 요약 판단
    if total_score > 0.15:
        summary = "STRONG BUY 신호 (분석 전용)"
    elif total_score > 0.05:
        summary = "BUY 신호 (분석 전용)"
    elif total_score < -0.15:
        summary = "STRONG SELL 신호 (분석 전용)"
    elif total_score < -0.05:
        summary = "SELL 신호 (분석 전용)"
    else:
        summary = "중립 — 추가 모니터링 권장"

    return {
        "weighted_score": round(total_score, 4),
        "agree": agree,
        "disagree": disagree,
        "caution": caution,
        "summary": summary,
    }
