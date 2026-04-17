# /analyze-kr — 한국 주식 시장 5-Agent 병렬 분석

한국 주식 시장 분석 커맨드. **2-레이어 분석**: Layer 1은 pykrx 규칙 스코어링, Layer 2는 5개 KR 에이전트 병렬 독립 분석 → Consensus 합의.
**분석 전용 — 매매 실행 없음.**

## 사용법

```
/analyze-kr {TARGET}

TARGET 예시:
  005930            종목 코드 (삼성전자)
  삼성전자           종목명 (universe 자동 검색)
  sector:반도체      섹터 전체 분석
  all               KOSPI TOP100 자동 선별 분석
```

## 실행 흐름 (2-Layer 파이프라인)

### Layer 1 — pykrx 자동 스코어링 (LLM 호출 없음)

```python
from kr_research.scorer import score_universe, select_top_n
from kr_data.pykrx_client import build_universe

universe = build_universe(market="ALL", min_mcap_krw=100_000_000_000)
scored = score_universe(universe, market_snapshot)
top_tickers = select_top_n(scored, n=100)
```

**스코어링 팩터 (가중합)**:
- momentum_score (30%): 1개월 수익률 (pykrx)
- value_score (20%): 1/PBR 정규화 (pykrx 시장 펀더멘탈)
- flow_score (30%): 외국인/기관 20일 순매수 (pykrx)
- shorting_score (20%): 공매도 잔고 역수 (pykrx)

---

### Layer 2 — 5-Agent 병렬 독립 분석 + Consensus 합의

#### Step 1: 데이터 fetch (LLM 호출 없음)

```bash
python -m kr_research.analyzer --ticker {TICKER} --mode data
```

→ JSON 출력: `ticker_data`, `regime`, `system_prompt`, `analysis_prompt`

#### Step 2: 5 에이전트 병렬 dispatch (단일 메시지, 동시 실행)

아래 5개 Agent 호출을 **한 메시지에** 전송:

```
Agent(subagent_type="kr-equity-research",     model="claude-opus-4-7",   prompt=<equity_prompt>)
Agent(subagent_type="kr-technical-strategist", model="claude-sonnet-4-6", prompt=<tech_prompt>)
Agent(subagent_type="kr-macro-economist",      model="claude-opus-4-7",   prompt=<macro_prompt>)
Agent(subagent_type="kr-sector-analyst",       model="claude-sonnet-4-6", prompt=<sector_prompt>)
Agent(subagent_type="kr-risk-controller",      model="claude-opus-4-7",   prompt=<risk_prompt>)
```

**각 에이전트 공통 prompt 템플릿**:
```
[KR Research Division — 독립 분석 요청]

Ticker: {TICKER}
KR Regime: {regime.regime} (confidence: {regime.confidence:.0%})
Regime Factors: {regime.factors}

[종목 데이터]
{ticker_data_formatted}

당신의 도메인에 한정하여 분석 후 아래 JSON만 출력하라 (마크다운 코드펜스 포함 가능):

{
  "agent": "<에이전트명>",
  "symbol": "{TICKER}",
  "direction": "AGREE" | "DISAGREE" | "VETO",
  "confidence_delta": <-0.30 ~ +0.30>,
  "conviction": "STRONG" | "MODERATE" | "WEAK",
  "reasoning": "<한국어 2~3문장. 구체적 수치 포함>",
  "key_metrics": { <도메인 핵심 지표 3~5개> }
}

규칙:
- VETO는 kr-risk-controller만 사용 가능
- AGREE → confidence_delta 0 이상
- DISAGREE → confidence_delta 0 이하
- 데이터 부족 시 conviction="WEAK" (DISAGREE 금지)
```

#### Step 3: Verdict 수집 + Consensus 계산

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

verdicts = []  # 5개 에이전트 응답 파싱 결과

# VETO 체크 (즉시 중단)
veto_reason = None
consensus = None
for v in verdicts:
    if v.get("direction") == "VETO":
        consensus = "VETO"
        veto_reason = v.get("reasoning", "")
        final_confidence = 0.0
        break

if consensus != "VETO":
    valid = [v for v in verdicts if v.get("direction") in ("AGREE", "DISAGREE")]
    if len(valid) < 3:
        consensus = "HOLD"
        final_confidence = 0.5
    else:
        weights = {"STRONG": 1.0, "MODERATE": 0.7, "WEAK": 0.4}
        weighted_score = sum(
            v["confidence_delta"] * weights.get(v.get("conviction", "WEAK"), 0.4)
            for v in valid
        )
        final_confidence = max(0.0, min(1.0, 0.5 + weighted_score))
        if final_confidence >= 0.62:
            consensus = "BUY"
        elif final_confidence <= 0.42:
            consensus = "SELL"
        else:
            consensus = "HOLD"
```

#### Step 4: kr_verdicts.json 저장 (research/kr_manual_override.py 사용)

```python
from research.kr_manual_override import save_kr_verdicts

save_kr_verdicts(
    ticker=TICKER,
    verdicts=verdicts,
    consensus=consensus,
    final_confidence=final_confidence,
    veto_reason=veto_reason,
    regime=regime_type,
)
```

#### Step 5: 리포트 생성

```python
from kr_research.models import KRVerdict, KRRegime, KRAnalysisResult
from kr_research.consensus import aggregate
from kr_research.report_generator import generate_report

v = KRVerdict(
    ticker=TICKER, agent="kr-commander",
    verdict=consensus, confidence=final_confidence,
    rationale="5-agent consensus: " + ", ".join(
        f"{x['agent']}={x['direction']}" for x in verdicts
    )
)
result = KRAnalysisResult(ticker=TICKER, verdicts=[v], consensus=consensus_obj, regime=regime)
report_path = generate_report(result, ticker_data)
print(f"리포트: {report_path}")
```

#### Step 6: 콘솔 출력

```
=== /analyze-kr {TICKER} ({종목명}) ===
KR Regime: {regime} ({confidence:.0%})  |  VKOSPI: {vkospi}  |  BOK: {bok_rate}%

Layer 1 Score: composite={score:.2f} (momentum={m:.2f}, value={v:.2f}, flow={f:.2f})

┌─ 5-Agent Verdict ──────────────────────────────────────────────┐
│ kr-equity-research    [Opus 4.7]   {direction}  {delta:+.2f}  {conviction} │
│ kr-technical-strategist [Sonnet]  {direction}  {delta:+.2f}  {conviction} │
│ kr-macro-economist    [Opus 4.7]   {direction}  {delta:+.2f}  {conviction} │
│ kr-sector-analyst     [Sonnet]    {direction}  {delta:+.2f}  {conviction} │
│ kr-risk-controller    [Opus 4.7]   {direction}  {delta:+.2f}  {conviction} │
└────────────────────────────────────────────────────────────────┘
Consensus: {consensus}  |  Final Confidence: {final_confidence:.0%}
Report → {report_path}
```

---

### 직접 실행 (CLI)

```bash
# 단일 종목 데이터 fetch (JSON 출력)
python -m kr_research.analyzer --ticker 005930 --mode data

# Layer 1 rules 스코어링만 (Claude 호출 없음)
python -m kr_research.analyzer --ticker 005930 --mode rules

# Top N 분석 (rules mode)
python -m kr_research.analyzer --top-n 50 --mode rules
```

## 결과 확인

```bash
cat state/kr_verdicts.json      # 5-agent consensus 결과
cat state/kr_market_state.json  # 시장 스냅샷
ls reports/kr/                  # 생성된 분석 리포트
```

## 데이터 소스

| 소스 | 용도 | API 키 |
|------|------|--------|
| pykrx | OHLCV / 수급 / 공매도 / VKOSPI / 섹터지수 | 불필요 |
| DART OpenAPI (dart-fss) | 공시, 재무제표, corp_code 매핑 | `DART_API_KEY` ✅ |
| 한국은행 ECOS | 기준금리 / 경상수지 / M2 | `ECOS_API_KEY` ✅ |
| 관세청 UNIPASS | 반도체 수출 YoY | `UNIPASS_API_KEY` ✅ |
| KRX KIND | 투자주의/거래정지 | 불필요 (공개) |

## 관련 파일

```
.claude/agents/
  kr-equity-research.md      # Opus 4.7 — 밸류에이션
  kr-technical-strategist.md # Sonnet 4.6 — 차트/수급
  kr-macro-economist.md      # Opus 4.7 — 거시경제/Regime
  kr-sector-analyst.md       # Sonnet 4.6 — 섹터 순환
  kr-risk-controller.md      # Opus 4.7 — VETO 권한

research/
  kr_manual_override.py      # kr_verdicts.json 저장/로드/TTL

state/
  kr_verdicts.json           # 5-agent consensus + 24h TTL
  kr_market_state.json       # Phase 1.65 출력
  kr_regime_state.json       # US 보정 후 KR regime
```
