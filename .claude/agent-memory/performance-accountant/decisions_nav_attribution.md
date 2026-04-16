---
name: Performance Accountant NAV Attribution Decisions
description: 재배분 후 inception 갱신, realloc window MDD, account_total_history 백필 결정
type: project
owner: performance-accountant
---

**Why:** 재배분은 실손실이 아니므로 수익률/MDD 계산 window를 재시작해야 한다.
**How to apply:** NAV 계산/리포트 로직 수정 전 아래 규칙 확인.

---

## 재배분(realloc) 후 수익률 window 리셋 규칙
- `phase_regime()`에서 allocated >5% 변화 → `realloc_flag = True`
- `phase_sync()`에서 `realloc_flag` → nav_history에 `{"event": "realloc", ...}` 태그
- `performance_calculator.py` MDD/return 계산 → 마지막 realloc 이후 window만 사용
- **이유:** 재배분 자체는 손실이 아님. realloc 이전 peak를 기준으로 삼으면 항상 허위 MDD 발생

## inception.strategies 동기화 규칙
- 재배분 후 반드시 `inception.strategies.*.allocated` = 새 allocated 값으로 업데이트
- 수익률 = `(current_nav - inception_nav) / inception_nav` → inception이 틀리면 수익률 오계산
- 리셋 스크립트: `scripts/reset_initial_nav.py` (1회성 수동 실행용)

## account_total_history 백필 (2026-04-15 결정)
- CB와 전체 포트폴리오 MDD 기준 = `account_total_history` (실제 Alpaca 잔고)
- 전략별 NAV 합계는 재배분 때마다 변동 → 절대 포트폴리오 기준으로 사용 금지
- 신규 환경에서 history 없을 시 Alpaca account history API로 백필
