---
name: Execution Broker Order Tracking Decisions
description: BUY 사이징, Alpaca sync 전략 귀속, fsync 보장 설계 결정
type: project
owner: execution-broker
---

**Why:** 주문 실행 정확성과 상태 추적 신뢰성이 Paper Trading 데이터 무결성의 핵심.
**How to apply:** order_manager/sync 관련 작업 시 아래 결정 사항 확인 후 변경.

---

## BUY 사이징: target-vs-delta 방식 (2026-04-16 결정)
- **결정:** `trade_value = max(0, target_value - existing_value)` (delta 방식)
- **이전 방식:** target_value 전체를 BUY → 중복 매수 발생
- **적용:** `execution/order_manager.py` BUY 사이징. `get_positions()` 1회 스냅샷으로 existing_value 계산
- **주의:** cash 차감도 delta 기준으로 통일 (target 전체 기준으로 차감하면 cash 이중 차감)

## Alpaca Sync 전략 귀속: 비례 분할 (2026-04-16 결정)
- **결정:** 복수 전략 공동 보유 시 전략별 `allocated` 비율로 포지션 분할
- **폴백:** SELL 이력으로 소유 전략 특정 가능 시 단독 귀속. 불가 시 equal split
- **이전 방식:** last-write-wins → 단일 전략 과다 계상

## LEV rebalance BUY weight_pct (2026-04-16 결정)
- **결정:** `weight_pct = target_weight` (전략의 목표 비중)
- **이전 방식:** `weight_pct = delta / capital` → order_manager에서 target-delta 이중 계산 발생
- **적용:** `strategies/leveraged_etf.py` rebalance 로직

## trade_log 쓰기 보장
- 모든 trade_log 쓰기: `f.flush(); os.fsync(f.fileno())` 필수
- 읽기: per-line try/except JSON 파싱, 손상 라인 스킵 후 경고 로그
