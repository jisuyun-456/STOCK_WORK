"""KR Research Agent Runner — data fetching + rules mode.

두 가지 모드:
  rules: Python 규칙 기반 (LLM 호출 없음, 백테스트용)
  data:  종목 데이터 fetch만 → JSON 출력 → Claude Code 에이전트가 직접 분석
         (analyzer.py --mode data 경유, Claude Code 토큰 사용, API 과금 없음)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from kr_research.models import KRVerdict, KRRegime

_logger = logging.getLogger("kr_research.agent_runner")


# ── rules mode ─────────────────────────────────────────────────────────────

def run_rules(tickers: list[str], regime: KRRegime) -> list[KRVerdict]:
    """Layer 1 rules-only mode (no Claude). Used in backtest / dry-run."""
    verdicts: list[KRVerdict] = []
    regime_type = regime.regime

    for ticker in tickers:
        if regime_type == "CRISIS":
            verdict_str: str = "SELL"
            rationale = "CRISIS regime — all positions SELL (rules mode)"
            confidence = 0.85
        elif regime_type == "BEAR":
            verdict_str = "HOLD"
            rationale = "BEAR regime — hold, no new entries (rules mode)"
            confidence = 0.65
        else:
            verdict_str = "HOLD"
            rationale = f"{regime_type} regime — HOLD pending scorer ranking (rules mode)"
            confidence = 0.5

        verdicts.append(KRVerdict(
            ticker=ticker,
            verdict=verdict_str,  # type: ignore[arg-type]
            confidence=confidence,
            agent="rules",
            rationale=rationale,
        ))

    return verdicts


# ── ticker data enrichment ─────────────────────────────────────────────────

def _fetch_ticker_data(ticker: str) -> dict:
    """종목별 실제 데이터 수집 (현재가, MA, 기초지표, 수급, 공매도).

    Returns empty dict on failure — caller handles gracefully.
    """
    try:
        from kr_data.pykrx_client import (
            fetch_ohlcv_batch,
            fetch_market_fundamental,
            fetch_investor_flow,
            fetch_shorting_balance,
        )

        today = date.today().strftime("%Y%m%d")
        d35 = (date.today() - timedelta(days=35)).strftime("%Y%m%d")
        d20 = (date.today() - timedelta(days=20)).strftime("%Y%m%d")
        d7  = (date.today() - timedelta(days=7)).strftime("%Y%m%d")
        d252 = (date.today() - timedelta(days=365)).strftime("%Y%m%d")

        result: dict = {}

        # OHLCV — current price, MAs, 52w range
        ohlcv = fetch_ohlcv_batch([ticker], d252, today)
        if ohlcv is not None and not ohlcv.empty:
            closes = ohlcv[ohlcv["ticker"] == ticker]["종가"] if "ticker" in ohlcv.columns else ohlcv["종가"]
            if not closes.empty:
                result["current_price"] = int(closes.iloc[-1])
                result["high_52w"] = int(closes.max())
                result["low_52w"] = int(closes.min())
                if len(closes) >= 20:
                    result["sma20"] = int(closes.iloc[-20:].mean())
                if len(closes) >= 60:
                    result["sma60"] = int(closes.iloc[-60:].mean())
                if len(closes) >= 200:
                    result["sma200"] = int(closes.iloc[-200:].mean())
                # 1-month momentum
                if len(closes) >= 21:
                    result["momentum_1m_pct"] = round(
                        (closes.iloc[-1] - closes.iloc[-21]) / closes.iloc[-21] * 100, 1
                    )

        # Fundamentals — PBR, PER, DIV
        fund = fetch_market_fundamental(today)
        if fund is not None and ticker in fund.index:
            row = fund.loc[ticker]
            result["pbr"] = round(float(row.get("PBR", 0)), 2)
            result["per"] = round(float(row.get("PER", 0)), 1)
            result["div_yield"] = round(float(row.get("DIV", 0)), 2)

        # Investor flow — foreign net direction (20d)
        flow = fetch_investor_flow(ticker, d20, today)
        if flow is not None and not flow.empty:
            col = next((c for c in flow.columns if "외국인" in str(c)), None)
            if col:
                net = flow[col].sum()
                result["foreign_flow_20d"] = "순매수" if net > 0 else "순매도"
                result["foreign_flow_raw"] = int(net)

        # Short-selling ratio (7d latest)
        short = fetch_shorting_balance(ticker, d7, today)
        if short is not None and not short.empty:
            ratio_col = next(
                (c for c in short.columns if any(k in str(c) for k in ["비율", "ratio", "Ratio"])),
                None
            )
            if ratio_col:
                result["short_ratio_pct"] = round(float(short[ratio_col].iloc[-1]), 2)

        # ── Technical indicators from OHLCV ──────────────────────────────
        if ohlcv is not None and not ohlcv.empty:
            tkr_ohlcv = ohlcv[ohlcv["ticker"] == ticker] if "ticker" in ohlcv.columns else ohlcv
            closes = tkr_ohlcv["종가"]
            if len(closes) >= 14:
                result.update(_calc_technicals(closes))

            # OHLCV 60일 보존 + 캔들 패턴 감지
            if not tkr_ohlcv.empty:
                last60 = tkr_ohlcv.tail(60).copy()
                date_col = next(
                    (c for c in last60.columns if str(c) in ("날짜", "date", "Date")), None
                )
                if date_col is None:
                    last60 = last60.reset_index()
                    date_col = str(last60.columns[0])
                rows = []
                for _, row in last60.iterrows():
                    try:
                        rows.append({
                            "d": str(row[date_col])[:10],
                            "o": int(row.get("시가", row.get("종가", 0))),
                            "h": int(row.get("고가", row.get("종가", 0))),
                            "l": int(row.get("저가", row.get("종가", 0))),
                            "c": int(row.get("종가", 0)),
                            "v": int(row.get("거래량", 0)),
                        })
                    except Exception:
                        pass
                result["ohlcv_60d"] = rows
                result["candle_patterns"] = _detect_candle_patterns(rows)

        return result

    except Exception as e:
        _logger.warning("_fetch_ticker_data(%s) failed: %s", ticker, e)
        return {}


def _calc_technicals(closes) -> dict:
    """RSI(14), MACD(12/26/9), Bollinger Bands(20,2) 계산."""
    import numpy as np
    out: dict = {}

    arr = closes.values.astype(float)

    # RSI(14)
    if len(arr) >= 15:
        delta = np.diff(arr)
        gain = np.where(delta > 0, delta, 0.0)
        loss = np.where(delta < 0, -delta, 0.0)
        avg_gain = np.mean(gain[-14:])
        avg_loss = np.mean(loss[-14:])
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - 100 / (1 + rs), 1)
        out["rsi14"] = rsi
        if rsi >= 70:
            out["rsi_signal"] = "과매수(매도 주의)"
        elif rsi <= 30:
            out["rsi_signal"] = "과매도(매수 기회)"
        else:
            out["rsi_signal"] = "중립"

    # MACD(12,26,9)
    if len(arr) >= 26:
        def ema(x, n):
            k = 2 / (n + 1)
            result = [x[0]]
            for v in x[1:]:
                result.append(v * k + result[-1] * (1 - k))
            return np.array(result)

        ema12 = ema(arr, 12)
        ema26 = ema(arr, 26)
        macd_line = ema12[-len(ema26):] - ema26
        if len(macd_line) >= 9:
            signal_line = ema(macd_line, 9)
            macd_val = round(float(macd_line[-1]), 0)
            signal_val = round(float(signal_line[-1]), 0)
            hist = macd_val - signal_val
            out["macd"] = macd_val
            out["macd_signal"] = signal_val
            out["macd_hist"] = round(hist, 0)
            if hist > 0 and (len(macd_line) < 10 or macd_line[-2] - signal_line[-2] <= 0):
                out["macd_cross"] = "골든크로스(매수신호)"
            elif hist < 0 and (len(macd_line) < 10 or macd_line[-2] - signal_line[-2] >= 0):
                out["macd_cross"] = "데드크로스(매도신호)"
            elif hist > 0:
                out["macd_cross"] = "상승추세유지"
            else:
                out["macd_cross"] = "하락추세유지"

    # Bollinger Bands(20, 2)
    if len(arr) >= 20:
        window = arr[-20:]
        mid = float(np.mean(window))
        std = float(np.std(window))
        upper = round(mid + 2 * std, 0)
        lower = round(mid - 2 * std, 0)
        current = arr[-1]
        bb_pct = round((current - lower) / (upper - lower) * 100, 1) if upper != lower else 50.0
        out["bb_upper"] = int(upper)
        out["bb_mid"] = int(mid)
        out["bb_lower"] = int(lower)
        out["bb_pct"] = bb_pct  # 0%=하단, 100%=상단
        if bb_pct >= 80:
            out["bb_signal"] = "상단 근접(과매수 주의)"
        elif bb_pct <= 20:
            out["bb_signal"] = "하단 근접(매수 기회)"
        else:
            out["bb_signal"] = "밴드 중간"

    return out


def _detect_candle_patterns(rows: list[dict]) -> list[dict]:
    """망치형/유성형/도지/상승장악형/하락장악형/새벽별/석별형 감지 (최근 8개 반환)."""
    patterns: list[dict] = []
    n = len(rows)
    for i in range(2, n):
        o, h, l, c = rows[i]["o"], rows[i]["h"], rows[i]["l"], rows[i]["c"]
        d = rows[i]["d"]
        total = h - l
        if total == 0:
            continue
        body = abs(c - o)
        upper_wick = h - max(c, o)
        lower_wick = min(c, o) - l
        body_pct = body / total
        is_bull = c >= o

        # Doji
        if body_pct < 0.1:
            patterns.append({"date": d, "pattern": "도지", "signal": "neutral",
                              "desc": "매수/매도 균형 — 방향 전환 대기"})
            continue

        # Hammer: long lower wick ≥ 2×body, after downtrend
        if lower_wick >= 2 * body and upper_wick <= body * 0.5:
            if rows[i - 1]["c"] < rows[i - 2]["c"]:
                patterns.append({"date": d, "pattern": "망치형", "signal": "buy",
                                  "desc": "하락 후 저점 반전 — 매수 신호"})
            continue

        # Shooting Star: long upper wick ≥ 2×body, after uptrend
        if upper_wick >= 2 * body and lower_wick <= body * 0.5:
            if rows[i - 1]["c"] > rows[i - 2]["c"]:
                patterns.append({"date": d, "pattern": "유성형", "signal": "sell",
                                  "desc": "상승 후 고점 거부 — 매도 경계"})
            continue

        # Bullish Engulfing
        po, pc = rows[i - 1]["o"], rows[i - 1]["c"]
        if is_bull and pc < po and o <= pc and c >= po:
            patterns.append({"date": d, "pattern": "상승장악형", "signal": "buy",
                              "desc": "전일 음봉 완전 포함 — 강한 매수 전환"})
            continue

        # Bearish Engulfing
        if not is_bull and pc > po and o >= pc and c <= po:
            patterns.append({"date": d, "pattern": "하락장악형", "signal": "sell",
                              "desc": "전일 양봉 완전 포함 — 강한 매도 전환"})
            continue

        # Morning Star: bearish → small body → bullish
        b0 = abs(rows[i - 2]["c"] - rows[i - 2]["o"])
        b1 = abs(rows[i - 1]["c"] - rows[i - 1]["o"])
        if (rows[i - 2]["c"] < rows[i - 2]["o"] and b1 < b0 * 0.4
                and is_bull and body > b0 * 0.5):
            patterns.append({"date": d, "pattern": "새벽별", "signal": "buy",
                              "desc": "3캔들 바닥 반전 — 강력 매수"})
            continue

        # Evening Star: bullish → small body → bearish
        if (rows[i - 2]["c"] > rows[i - 2]["o"] and b1 < b0 * 0.4
                and not is_bull and body > b0 * 0.5):
            patterns.append({"date": d, "pattern": "석별형", "signal": "sell",
                              "desc": "3캔들 천장 반전 — 경계 신호"})

    return patterns[-8:]


# ── Public data API (for analyze-kr command) ──────────────────────────────

def fetch_ticker_data(ticker: str) -> dict:
    """Public wrapper — returns raw ticker data dict for Claude Code agent consumption."""
    return _fetch_ticker_data(ticker)


# ── Analysis system prompt (exported for analyzer.py --mode data) ──────────

SYSTEM_PROMPT = """You are a senior Korean equity research analyst (Goldman Sachs / JP Morgan level).
Analyze the given KRX ticker using the provided market data and return a JSON object.

CRITICAL: Respond with ONLY the JSON below — no markdown, no extra text, no code fences.

{
  "company_name": "회사명 (한글)",
  "sector": "섹터명 (예: 반도체, 이차전지, 바이오)",
  "verdict": "BUY|HOLD|SELL|VETO",
  "confidence": 0.0-1.0,
  "investment_thesis": "왜 지금 이 기업인가 — 2~3문장. 구조적 경쟁우위, 단기 촉매, 밸류에이션 근거를 포함. 한국어.",
  "rationale": "종합 분석 요약 2~3문장 (기술적+펀더멘털+수급 통합). 한국어.",
  "entry_price_low": number_or_null,
  "entry_price_high": number_or_null,
  "target_price": number_or_null,
  "target_price_2": number_or_null,
  "stop_loss": number_or_null,
  "buy_factors": ["매수 근거1 (구체적 수치/촉매)", "매수 근거2", "매수 근거3"],
  "sell_factors": ["매도/우려 요인1 (구체적)", "매도/우려 요인2"],
  "buy_trigger": "구체적 매수 타이밍 조건 — 기술적 트리거 포함. 한국어.",
  "sell_trigger": "구체적 매도/손절 타이밍 조건. 한국어.",
  "current_status": "현재 기술적 상태 한줄 (RSI/MACD/추세 요약). 한국어.",
  "bull_case": "+N~M%: 강세 시나리오 촉매 설명. 한국어.",
  "base_case": "+N~M%: 기본 시나리오. 한국어.",
  "bear_case": "-N~M%: 약세 리스크 시나리오. 한국어.",
  "risk_factors": ["리스크1 (발생확률·영향도 포함)", "리스크2", "리스크3"]
}

Price rules:
- entry_price_low/high: recommended buy zone in KRW (BUY only; HOLD/SELL → null)
- target_price: conservative T1 target (50% take-profit); target_price_2: aggressive T2
- stop_loss: stop price in KRW (BUY/HOLD → set; SELL/VETO → null)
- buy_factors: 3 concrete bullish reasons with specific data points
- sell_factors: 2-3 concrete risks or bearish factors
- VETO: only for fraud, regulatory halt, delisting risk — extreme cases only
- All prices must be numerically realistic vs. the current price provided"""


# ── Prompt builder ─────────────────────────────────────────────────────────

def _build_analysis_prompt(ticker: str, regime: KRRegime, snapshot: dict, ticker_data: dict) -> str:
    """종목별 실제 데이터를 포함한 분석 프롬프트."""
    factors_str = str(regime.factors)[:300]

    # Price section
    price_lines: list[str] = []
    if ticker_data:
        cp = ticker_data.get("current_price")
        if cp:
            price_lines.append(f"현재가: {cp:,}원")
        for label, key in [("SMA20", "sma20"), ("SMA60", "sma60"), ("SMA200", "sma200")]:
            if key in ticker_data:
                price_lines.append(f"{label}: {ticker_data[key]:,}원")
        if "high_52w" in ticker_data and "low_52w" in ticker_data:
            price_lines.append(f"52주 고가: {ticker_data['high_52w']:,}원 / 저가: {ticker_data['low_52w']:,}원")
        if "momentum_1m_pct" in ticker_data:
            price_lines.append(f"1개월 수익률: {ticker_data['momentum_1m_pct']:+.1f}%")
        for label, key in [("PBR", "pbr"), ("PER", "per"), ("배당수익률", "div_yield")]:
            if key in ticker_data:
                price_lines.append(f"{label}: {ticker_data[key]}")
        if "foreign_flow_20d" in ticker_data:
            price_lines.append(f"외국인 20일 수급: {ticker_data['foreign_flow_20d']}")
        if "short_ratio_pct" in ticker_data:
            price_lines.append(f"공매도 잔고비율: {ticker_data['short_ratio_pct']}%")
        # Technical indicators
        if "rsi14" in ticker_data:
            price_lines.append(f"RSI(14): {ticker_data['rsi14']} [{ticker_data.get('rsi_signal','')}]")
        if "macd_cross" in ticker_data:
            price_lines.append(f"MACD: hist={ticker_data.get('macd_hist',0):+.0f} [{ticker_data.get('macd_cross','')}]")
        if "bb_pct" in ticker_data:
            price_lines.append(f"볼린저밴드: 상단={ticker_data['bb_upper']:,} / 하단={ticker_data['bb_lower']:,} / 위치={ticker_data['bb_pct']}% [{ticker_data.get('bb_signal','')}]")
    else:
        price_lines.append("(종목 데이터 없음 — 시장 컨텍스트만으로 판단)")

    price_section = "\n".join(price_lines)

    return (
        f"KRX 종목 분석 요청: {ticker}\n\n"
        f"시장 Regime: {regime.regime} (신뢰도: {regime.confidence:.0%})\n"
        f"Regime 팩터: {factors_str}\n\n"
        f"[종목 데이터]\n{price_section}\n\n"
        f"위 데이터를 바탕으로 JSON 형식으로 분석 결과를 반환하세요."
    )


# ── Response parser ────────────────────────────────────────────────────────

def _parse_verdict(ticker: str, text: str) -> KRVerdict:
    """Parse Claude response → KRVerdict (전체 필드 파싱)."""
    _VALID_VERDICTS = {"BUY", "HOLD", "SELL", "VETO"}

    # Try full JSON first, then nested JSON
    match = re.search(r'\{[\s\S]*\}', text, re.DOTALL)
    if not match:
        _logger.debug("_parse_verdict(%s): no JSON found", ticker)
        return KRVerdict(ticker=ticker, verdict="HOLD", confidence=0.3,
                         agent="claude", rationale="no json in response")

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        # Fallback: try first simple JSON object
        simple = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if simple:
            try:
                data = json.loads(simple.group())
            except json.JSONDecodeError as e:
                return KRVerdict(ticker=ticker, verdict="HOLD", confidence=0.3,
                                 agent="claude", rationale=f"json_parse_error: {e}")
        else:
            return KRVerdict(ticker=ticker, verdict="HOLD", confidence=0.3,
                             agent="claude", rationale="json_parse_error")

    verdict_str = str(data.get("verdict", "HOLD")).upper()
    if verdict_str not in _VALID_VERDICTS:
        verdict_str = "HOLD"

    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))

    def _to_price(val) -> float | None:
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _to_str_list(val) -> list[str]:
        if isinstance(val, list):
            return [str(x) for x in val]
        return []

    return KRVerdict(
        ticker=ticker,
        verdict=verdict_str,  # type: ignore[arg-type]
        confidence=confidence,
        agent="claude",
        rationale=str(data.get("rationale", "")),
        veto=verdict_str == "VETO",
        veto_reason=str(data.get("rationale", "")) if verdict_str == "VETO" else "",
        # 가격 전략
        entry_price_low=_to_price(data.get("entry_price_low")),
        entry_price_high=_to_price(data.get("entry_price_high")),
        target_price=_to_price(data.get("target_price")),
        target_price_2=_to_price(data.get("target_price_2")),
        stop_loss=_to_price(data.get("stop_loss")),
        # 하위호환
        entry_price=_to_price(data.get("entry_price_low") or data.get("entry_price")),
        # 타이밍
        buy_trigger=str(data.get("buy_trigger", "")),
        sell_trigger=str(data.get("sell_trigger", "")),
        current_status=str(data.get("current_status", "")),
        # 시나리오
        bull_case=str(data.get("bull_case", "")),
        base_case=str(data.get("base_case", "")),
        bear_case=str(data.get("bear_case", "")),
        # 메타
        company_name=str(data.get("company_name", "")),
        sector=str(data.get("sector", "")),
        risk_factors=_to_str_list(data.get("risk_factors", [])),
        investment_thesis=str(data.get("investment_thesis", "")),
        buy_factors=_to_str_list(data.get("buy_factors", [])),
        sell_factors=_to_str_list(data.get("sell_factors", [])),
    )
