---
name: trade-check
description: >
  매수/매도 전 다면 검증 파이프라인.
  "매수해도 돼?", "매도?", "진입?", "청산?" 요청 시 자동 트리거.
---

# /trade-check {SYMBOL} — Pre-Trade Verification

## 언제 사용
- "{종목} 매수해도 돼?"
- "{종목} 매도할까?"
- "{종목} 진입 타이밍?"
- 매수/매도 의사결정 관련 모든 요청

## Step 1: Chief Strategist 총괄

Chief Strategist가 전체 파이프라인을 조율:

### 매수 검증 순서
1. **Fundamental Analyst** → 내재가치, Margin of Safety
2. **Quant Strategist** → 기술적 타이밍, 포지션 사이징, 리스크
3. **Market Scanner** → 수급/공시 크로스체크
4. **Tax & Compliance** → 포트폴리오 한도 검증 (게이트)

### 매도 검증 순서
1. **Fundamental Analyst** → 밸류에이션 변화
2. **Quant Strategist** → 기술적 신호, 리스크 레벨
3. **Tax & Compliance** → 양도세 시뮬레이션 (필수 선행)
4. **Market Scanner** → 수급 변화

## Step 2: Chief Strategist 통합 판단

- 에이전트별 결과 수집
- 다관점 검증 (Graham-Buffett-Munger + 매크로 + 행동재무)
- Believability-Weighted 통합
- Pre-Mortem 실행

## Step 3: 최종 출력

| 항목 | 값 |
|------|---|
| 방향성 | BULLISH / BEARISH / NEUTRAL |
| 확신도 | 1~10 |
| 진입가/목표가/손절가 | 각 레벨 |
| R:R 비율 | 목표:손실 |
| 포지션 크기 | Kelly/Half-Kelly 기반 |
| 세금 영향 | 예상 세금액 |
| 포트폴리오 한도 | PASS / FAIL |
| Bull Case | 1-2문장 |
| Bear Case | 1-2문장 |
| Pre-Mortem | 가장 큰 리스크 |
| 최종 권고 | 매수/매도/관망 + 근거 |
