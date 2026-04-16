---
name: Performance Accountant Regression Bugs
description: NAV/수익률/MDD 귀속 계산 경계에서 발생한 회귀 버그 이력.
type: project
owner: performance-accountant
---

### [T7] portfolios.json inception LEV_ST $25k 오설정 → 합계 $125k 아티팩트

- **Symptom:** 전체 포트폴리오 NAV가 $125k로 표시. LEV inception이 $25k 초과
- **Root cause:** LEV_ST 전략 추가 시 `inception.strategies.LEV_ST`를 $25k로 설정했으나, LEV도 $50k → $25k로 조정했어야 했음. 합계 $125k
- **Fix:** `state/portfolios.json` inception 항목 수동 수정, LEV $25k로 정정 (commit 1743604)
- **Regression guard:**
  - 전략 추가/자본 재배분 시 `sum(inception.strategies.*.allocated) == 100_000` 검증 필수
  - 재배분 후 inception 합계 확인: `python -c "import json; d=json.load(open('state/portfolios.json')); print(sum(s['allocated'] for s in d['inception']['strategies'].values()))"`

### [initial_nav 아티팩트] 재배분 후 inception 미갱신 → 수익률 -80% 아티팩트

- **Symptom:** MOM 수익률 -80%, LEV 수익률 +151% 표시. 실제 거래 없음
- **Root cause:** RL-2 재배분(LEV $20k→$50k) 후 `performance.json`의 `inception.strategies` 미갱신. MOM inception=$25k 상태에서 current=$5k → -80%로 계산
- **Fix:** `scripts/reset_initial_nav.py` 1회 실행으로 전략 수익률 0% 리셋. `_check_inception_drift()` 경고 로그 추가 (commit 19434eb)
- **Regression guard:**
  - 재배분(allocated 변경) 후 반드시 `inception.strategies.*.allocated` 동기화
  - 재배분 >5% 변화 시 수익률 0% 리셋 여부 사용자 확인 필수
  - (cross-ref: trading-commander/bugs_regression_log.md — 재배분 오케스트레이션)

### [MDD peak_nav 미리셋] 재배분 후 peak_nav 미리셋 → MDD -66% 아티팩트

- **Symptom:** MOM MDD=-66.5% (peak=15K, current=5K), QNT MDD=-49.8%, LEV MDD=-49.8%
- **Root cause:** CRISIS 재배분으로 allocated가 줄었을 때 `nav_history`의 peak_nav가 이전 배분 기준 유지. 현재 current_nav와 비교하면 대폭 하락으로 계산
- **Fix:**
  - `run_cycle.py phase_regime()`: allocated >5% 변화 시 `realloc_flag` 설정
  - `run_cycle.py phase_sync()`: `realloc_flag` 있으면 nav_history에 `event="realloc"` 태그
  - `performance_calculator.py`: MDD/peak_nav 계산을 마지막 realloc 이후 window로 한정
  - `portfolios.json`: 기존 nav_history에 realloc 이벤트 소급 태깅 (commit a6b4178)
- **Regression guard:**
  - 재배분 후 MDD가 갑자기 급락하면 realloc 태그 확인
  - peak_nav는 마지막 realloc 이후 window 내 최고값만 사용
