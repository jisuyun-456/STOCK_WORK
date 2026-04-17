# /analyze-kr — 한국 주식 시장 분석

한국 주식 시장 분석 커맨드. **2-레이어 분석**: Layer 1은 pykrx 규칙 스코어링, Layer 2는 실제 Claude 에이전트 호출.
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

### Layer 1 — pykrx 자동 스코어링 (Claude 호출 없음)

```python
# Layer 1: 1,200종목 전체 룰 스코어링
from kr_research.scorer import score_universe, select_top_n
from kr_data.pykrx_client import build_universe

universe = build_universe(market="ALL", min_mcap_krw=100_000_000_000)
scored = score_universe(universe, market_snapshot)
top_tickers = select_top_n(scored, n=100)  # Claude 분석 대상
```

**스코어링 팩터 (가중합)**:
- momentum_score (30%): 1개월 수익률 (pykrx)
- value_score (20%): 1/PBR 정규화 (pykrx 시장 펀더멘탈)
- flow_score (30%): 외국인/기관 20일 순매수 (pykrx)
- shorting_score (20%): 공매도 잔고 역수 (pykrx)

### Layer 2 — Claude Code 에이전트 직접 분석 (Claude Code 토큰 사용, API 과금 없음)

**Step 1**: 종목 데이터 fetch (LLM 호출 없음)

```bash
python -m kr_research.analyzer --ticker {SYMBOL} --mode data
```

→ JSON 출력: `regime`, `ticker_data` (현재가/MA/RSI/MACD/볼린저/PBR/PER/수급/공매도), `system_prompt`, `analysis_prompt`

**Step 2**: 에이전트 직접 분석

위 JSON의 `system_prompt` + `analysis_prompt`를 읽고, **에이전트(Claude) 자신이** GS/JPM 수준 분석을 수행하여 KRVerdict JSON 형식으로 verdict 생성. 별도 API 호출 없음.

**Step 3**: 결과 저장 및 리포트

```python
from kr_research.models import KRVerdict, KRRegime, KRAnalysisResult
from kr_research.consensus import aggregate
from kr_research.report_generator import generate_report
import json, dataclasses
from pathlib import Path
from datetime import datetime

# verdict dict → KRVerdict 객체 구성
v = KRVerdict(ticker=SYMBOL, agent="claude", **verdict_fields)
v._ticker_data = ticker_data  # HTML 리포트 8탭 데이터
regime = KRRegime(regime=regime_type, confidence=regime_conf, factors=regime_factors)
consensus = aggregate([v], regime)
result = KRAnalysisResult(ticker=SYMBOL, verdicts=[v], consensus=consensus, regime=regime)
result._ticker_data = ticker_data

# 리포트 생성
report_path = generate_report(result, ticker_data)
print(f"리포트: {report_path}")

# state/kr_verdicts.json 저장
verdicts_path = Path("state/kr_verdicts.json")
state = {"analyzed_at": datetime.now().isoformat(), "count": 1,
         "verdicts": [{"ticker": SYMBOL, "verdict": v.verdict, "confidence": v.confidence,
                        "rationale": v.rationale, "regime": regime.regime,
                        "analyzed_at": result.analyzed_at.isoformat()}]}
verdicts_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
```

### 직접 실행 (CLI)

```bash
# 단일 종목 (rules mode — Claude 호출 없음, 백테스트용)
python -m kr_research.analyzer --ticker 005930 --mode rules

# 단일 종목 데이터 fetch (JSON 출력 — Claude Code 에이전트가 소비)
python -m kr_research.analyzer --ticker 005930 --mode data

# Top N 분석 (rules mode)
python -m kr_research.analyzer --top-n 50 --mode rules
```

## 결과 확인

```bash
cat state/kr_verdicts.json      # 분석 결과 (verdict/confidence/rationale)
cat state/kr_market_state.json  # 시장 스냅샷 (VKOSPI source=pykrx, BOK source=ecos)
cat state/kr_regime_state.json  # KR Regime (US 보정 후)
ls reports/kr/                  # 생성된 분석 리포트
```

## 출력 형식

```
=== /analyze-kr {SYMBOL} ({종목명}) ===
KR Regime: BULL (confidence: 78%)  |  VKOSPI: 17.2 [pykrx]  |  BOK: 3.25% [ecos]

Layer 1 Score: composite=0.73 (momentum=0.8, value=0.6, flow=0.7, shorting=0.6)

Layer 2 (claude-sonnet-4-6):
  verdict: BUY  confidence: 0.75
  rationale: "반도체 수출 YoY+12%, 외인 순매수 3주 연속, PBR 1.2 저평가"

Result → state/kr_verdicts.json
Report → reports/kr/YYYY-MM-DD-{SYMBOL}-analysis.md
```

## 데이터 소스 (신규 아키텍처)

| 소스 | 용도 | API 키 |
|------|------|--------|
| pykrx | OHLCV / 수급 / 공매도 / VKOSPI / 섹터지수 | 불필요 |
| DART OpenAPI (dart-fss) | 공시, 재무제표, corp_code 매핑 | `DART_API_KEY` ✅ |
| 한국은행 ECOS | 기준금리 / 경상수지 / M2 | `ECOS_API_KEY` (선택) |
| 관세청 UNIPASS | 반도체 수출 YoY | `UNIPASS_API_KEY` (선택) |
| KRX KIND | 투자주의/거래정지 | 불필요 (공개) |
| Claude Code 에이전트 | Layer 2 심층 분석 | Claude Code 토큰 (별도 API 키 불필요) |

## 관련 파일 (신규 구조)

```
kr_data/
  pykrx_client.py      # OHLCV / 수급 / VKOSPI (HIGH #2/#10/#11 fixed)
  dart_client.py       # DART corp_code 매핑 (HIGH #5 fixed)
  ecos_client.py       # BOK 실시간 (HIGH #3 fixed — 하드코딩 폐기)
  unipass_client.py    # 반도체 수출 (HIGH #4 fixed — null 폐기)
  sector_feeds/        # 8섹터 딥 피드 (HIGH #6/#7/#12 fixed)

kr_research/
  models.py            # KRVerdict / KRRegime / KRAnalysisResult
  regime.py            # US 보정 포함 KR Regime 판별
  scorer.py            # Layer 1 pykrx 스코어링 (Top N 선별)
  agent_runner.py      # Layer 2 Claude API 실제 호출 (HIGH #1 fixed)
  consensus.py         # Regime-aware 가중 합산
  analyzer.py          # CLI 진입점

kr_overlay/
  us_to_kr.py          # US regime → KR 보정
  kr_to_us.py          # KR 매크로 → US 신뢰도 조정
  signal_bridge.py     # 양방향 드리프트 감지

state/
  kr_market_state.json # Phase 1.65 출력
  kr_regime_state.json # US 보정 후 KR regime
  kr_verdicts.json     # 분석 결과 캐시
```
