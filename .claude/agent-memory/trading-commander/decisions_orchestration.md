---
name: Trading Commander Orchestration Decisions
description: 재배분 트리거, Research Overlay 라우팅, 전략 자본 활성화 조건 결정
type: project
owner: trading-commander
---

**Why:** 오케스트레이터로서 각 phase 간 상태 일관성 유지와 예외 처리가 핵심 책임.
**How to apply:** run_cycle.py phase 순서/로직 변경 전 아래 결정 사항 확인.

---

## 재배분 트리거 기준 (realloc_flag)
- `phase_regime()`에서 allocated >5% 변화 → `realloc_flag = True`
- `phase_sync()`에서 이 flag를 nav_history realloc 태그에 사용
- 5% 미만 변화는 noise → 트리거 불필요 (레짐 hysteresis와 동일 개념)

## Research Overlay 기본 모드
- 기본값: `--research-mode selective` (confidence 0.5~0.7만 Review)
- dry-run 기본값: `selective`
- 전체 검증 필요 시: `--research-mode full`
- 빠른 실행: `--research-mode skip`

## Regime별 전략 자본 배분 (CLAUDE.md BULL 기준, $100k)
| 전략 | BULL | NEUTRAL | BEAR | CRISIS | EUPHORIA |
|------|------|---------|------|--------|---------|
| MOM | 15% | 12.5% | 10% | 5% | 10% |
| VAL | 10% | 12.5% | 20% | 20% | 12.5% |
| QNT | 12.5% | 15% | 20% | 15% | 15% |
| LEV | 25% | 20% | 0% | 0% | 25% |
| LEV_ST | 25% | 20% | 0% | 0% | 25% |
| GRW | 12.5% | 10% | 0% | 0% | 0% |
| CASH | 0% | 10% | 50% | 60% | 12.5% |

## phase_regime() allocated 업데이트 규칙
- allocated는 레짐 배분 기준으로 **항상** 업데이트 (현금 잔여 조건 불필요)
- `if cash_amount > 0` guard 제거됨 (GRW allocated=$0 버그 원인)
- 단, 실제 BUY 주문 실행은 cash_amount 체크 (order_manager 책임)
