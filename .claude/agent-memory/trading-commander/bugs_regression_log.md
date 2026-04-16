---
name: Trading Commander Regression Bugs
description: 오케스트레이션 레벨에서 발생한 교차 도메인 회귀 버그 이력.
type: project
owner: trading-commander
---

개별 에이전트 버그는 해당 에이전트 메모리 참조. 이 파일은 오케스트레이션 관점에서만 기록.

### [CB false-EMERGENCY] 재배분 후 CB가 실손실로 오인하는 파이프라인 패턴

- **Symptom:** CRISIS 레짐 전환 + 재배분 후 CB EMERGENCY 발동. 실제 Alpaca 잔고 정상
- **Root cause (오케스트레이션):** `phase_regime()`이 전략 자본을 줄인 후 `phase_sync()`가 portfolios.json을 업데이트하기 전에 CB가 이전 NAV 기준으로 계산. 전략 NAV 합계 기반 CB가 아닌 실계좌 기반 CB 필요
- **Fix:** CB NAV 소스 → `account_total_history`. `phase_sync()`에서 `account_total_history` 갱신 (commit 5bc230d)
- **Regression guard:**
  - 재배분 사이클 후 CB 경보 발동 시 먼저 Alpaca 실계좌 잔고 확인
  - (세부: risk-guardian/bugs_regression_log.md [CB false-EMERGENCY])

### [GRW allocated=$0] BULL/NEUTRAL 레짐에서 GRW allocated 미업데이트

- **Symptom:** GRW 전략이 시그널은 생성하나 실제 자본 없음. portfolios.json GRW.allocated=$0
- **Root cause:** `phase_regime()`의 `if cash_amount > 0` guard가 allocated 업데이트 경로를 차단. BULL/NEUTRAL 레짐에서 현금이 없으면 allocated 업데이트 스킵
- **Fix:** guard 제거 → allocated는 레짐 배분 기준으로 항상 업데이트 (commit 592aa05)
- **Regression guard:**
  - 새 전략 추가 시 `phase_regime()` 이후 `portfolios.json.strategies.<NEW>.allocated > 0` 확인
  - BULL/NEUTRAL 레짐에서 시그널은 있으나 포지션이 없으면 allocated 확인 먼저

### [MDD 아티팩트] 재배분 후 peak_nav 미리셋 → 허위 MDD

- **Symptom:** MOM MDD=-66%, QNT MDD=-49%, LEV MDD=-49% (실제 거래 없음)
- **Root cause (오케스트레이션):** `phase_regime()`이 allocated를 변경할 때 `realloc_flag` 미설정 → `phase_sync()`가 realloc 이벤트 태깅 안 함 → `performance_calculator`가 전체 nav_history 기준으로 MDD 계산
- **Fix:** realloc_flag 설정 + realloc window MDD (commit a6b4178)
- **Regression guard:**
  - (세부: performance-accountant/bugs_regression_log.md [MDD peak_nav 미리셋])
  - 재배분 >5% 변화 시 `realloc_flag` 설정 확인
