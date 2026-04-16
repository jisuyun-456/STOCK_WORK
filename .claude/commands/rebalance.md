---
name: rebalance
description: >
  특정 전략 강제 리밸런싱. 기존 포지션 정리 후 새 시그널 기반 재구성.
  트리거: /rebalance, 리밸런싱, 비중 조정, 포지션 정리
---

# /rebalance {STRATEGY} - Force Rebalance

## 사용법
```
/rebalance MOM     # Momentum 전략 리밸런싱
/rebalance VAL     # Value Quality 전략 리밸런싱
/rebalance all     # 전체 전략 리밸런싱
```

## 리밸런싱 프로세스

1. **현재 포지션 확인**: Alpaca API + portfolios.json 조회
2. **목표 포지션 계산**: 해당 전략 모듈 재실행 -> 새 Signal[]
3. **차이 계산**: 현재 vs 목표 비중 차이
4. **SELL 먼저**: 목표에서 빠진 종목 매도
5. **BUY 후**: 새로 추가된 종목 매수
6. **Risk Guardian 검증**: 모든 새 시그널은 리스크 체크 통과 필수

## 전략별 리밸런싱 주기
| 전략 | 기본 주기 | 강제 리밸런싱 |
|------|---------|------------|
| MOM | 월간 | /rebalance MOM |
| VAL | 분기 | /rebalance VAL |
| QNT | 월간 | /rebalance QNT |
| LEV | 일간 (자동) | /rebalance LEV |

## 주의사항
- 리밸런싱 = 매도 + 매수 → 두 번의 거래 비용 발생
- dry-run 먼저 실행하여 변경 범위 확인 권장
- 장 마감 후에는 다음 장 개장까지 대기
