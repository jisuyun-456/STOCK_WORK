---
name: analyze
description: >
  특정 심볼에 대해 Research Division 5-에이전트 수동 분석 실행.
  결과는 state/manual_verdicts.json (24h TTL) 에 저장되어 다음 /run-cycle Phase 2.5에서
  auto-rules/cache보다 우선 적용됨.
  트리거: /analyze, 수동분석, manual analysis, 리서치 오버라이드
---

# /analyze {SYMBOL} {STRATEGY} [BUY|SELL] - Manual Research Override

## 사용법
```
/analyze NVDA MOM BUY
/analyze AAPL VAL SELL
/analyze TSLA LEV BUY
```

인자:
- **SYMBOL**: 티커 (대문자)
- **STRATEGY**: `MOM` | `VAL` | `QNT` | `LEV` | `GRW`
- **Direction**: `BUY` | `SELL` (기본 BUY)

---

## 실행 순서

### Step 1: 컨텍스트 수집

다음을 읽어 컨텍스트를 파악한다:
- `state/portfolios.json` → 현재 전략별 포지션
- `state/research_cache.json` → 최근 regime + 기존 verdict 참고
- `state/regime_state.json` → 현재 regime

### Step 2: Research Division 5-에이전트 병렬 실행

**단일 메시지에서 5개 Agent tool을 동시 호출**한다 (병렬 실행).

각 에이전트에게 전달할 공통 컨텍스트:
```
Symbol: {SYMBOL}
Strategy: {STRATEGY}
Direction: {BUY|SELL}
Mode: manual_override (user-initiated Phase 2.5 analysis)

현재 상태:
- Regime: {regime_state에서 읽은 값}
- 전략 포지션: {해당 전략 positions 목록}
- 포지션 수: {pos_count}/{max_pos}

요구사항:
당신의 도메인에 한정하여 분석하고 아래 JSON 하나만 출력하라 (코드펜스 포함 가능):

{
  "agent": "<에이전트명>",
  "symbol": "{SYMBOL}",
  "direction": "AGREE" | "DISAGREE" | "VETO",
  "confidence_delta": <-0.3 ~ +0.3>,
  "conviction": "STRONG" | "MODERATE" | "WEAK",
  "reasoning": "<한국어 1~3문장>",
  "key_metrics": { <도메인 핵심 지표> }
}

주의:
- VETO는 risk_controller만 사용 가능 (BB %B > 1.0, Z-Score < 1.81 등 극단 케이스)
- AGREE → confidence_delta 0 이상, DISAGREE → 0 이하
```

호출 대상 에이전트 (subagent_type):
1. `equity-research` → DCF/밸류에이션/펀더멘탈 (agent명: "equity_research")
2. `technical-strategist` → RSI/MACD/BB/추세 (agent명: "technical_strategist")
3. `macro-economist` → Regime/FOMC/CPI/매크로 (agent명: "macro_economist")
4. `portfolio-architect` → 포트폴리오 적합도/비중 (agent명: "portfolio_architect")
5. `risk-controller` → VETO 권한/리스크 게이트 (agent명: "risk_controller")

### Step 3: JSON 수집 + 검증

각 에이전트 응답에서 JSON을 파싱한다:
- `direction` ∈ {AGREE, DISAGREE, VETO} (아니면 AGREE 기본값)
- `confidence_delta` → [-0.3, +0.3] clamp
- `conviction` ∈ {STRONG, MODERATE, WEAK} (아니면 MODERATE 기본값)
- `risk_controller` 외 에이전트가 VETO 반환 시 → **DISAGREE로 강제 다운그레이드**
- 유효 verdict가 3개 미만이면 저장 중단 + 사용자에게 재시도 안내

### Step 4: 저장

Bash tool로 아래 python을 실행해 저장한다 (verdicts 리스트를 실제 결과로 채울 것):

```bash
python -c "
import sys
sys.path.insert(0, '.')
from research.manual_override import save_manual_verdicts
from research.models import ResearchVerdict
from datetime import datetime, timezone

now = datetime.now(timezone.utc).isoformat()
verdicts = [
    ResearchVerdict(agent='equity_research', symbol='SYMBOL', direction='AGREE',
                    confidence_delta=0.08, conviction='STRONG',
                    reasoning='...', key_metrics={}, timestamp=now),
    # ... 나머지 에이전트 ...
]
save_manual_verdicts('SYMBOL', 'STRATEGY', 'buy', verdicts, ttl_hours=24)
print(f'Saved {len(verdicts)} verdicts')
"
```

### Step 5: 요약 리포트 출력

사용자에게 다음 형식으로 출력:

```
=== /analyze {SYMBOL} {STRATEGY} {BUY|SELL} — Research Division Manual Override ===

Regime: {regime}

Verdicts:
  equity_research      {AGREE|DISAGREE|VETO}  (delta={:+.2f}, {conviction})  {reasoning 50자}
  technical_strategist {AGREE|DISAGREE|VETO}  (delta={:+.2f}, {conviction})  {reasoning 50자}
  macro_economist      {AGREE|DISAGREE|VETO}  (delta={:+.2f}, {conviction})  {reasoning 50자}
  portfolio_architect  {AGREE|DISAGREE|VETO}  (delta={:+.2f}, {conviction})  {reasoning 50자}
  risk_controller      {AGREE|DISAGREE|VETO}  (delta={:+.2f}, {conviction})  {reasoning 50자}

Aggregate: {n_agree} AGREE / {n_disagree} DISAGREE / {n_veto} VETO
Weighted delta (approx): {sum_delta:+.2f}
→ 다음 /run-cycle Phase 2.5에서 signal.confidence에 반영됩니다.

Saved: state/manual_verdicts.json (expires {expires_at})
```

---

## 동작 보장

- 다음 `/run-cycle` 또는 `python run_cycle.py --phase research` 실행 시 Phase 2.5가
  `state/manual_verdicts.json`을 먼저 조회하여 auto-rules/cache를 **완전히 건너뛴다**.
- TTL 24h 경과 시 자동 폐기 (이후 정상 rules 흐름으로 복귀).
- 같은 키 재실행 시 덮어쓰기.

## 관리 커맨드 (참고)

```bash
# 활성 override 목록 확인
python -c "from research.manual_override import list_active; import json; print(json.dumps(list_active(), indent=2))"

# 만료 항목 정리
python -c "from research.manual_override import clear_expired; print(clear_expired(), 'removed')"

# 특정 항목 즉시 삭제
python -c "from research.manual_override import invalidate; print(invalidate('NVDA', 'MOM', 'buy'))"
```
