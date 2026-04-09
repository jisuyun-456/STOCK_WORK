---
name: performance
description: >
  전략별 성과 대시보드 조회. NAV, 수익률, MDD, Sharpe, 거래 이력 분석.
  트리거: /performance, 성과, 수익률, P&L, 대시보드
---

# /performance - Strategy Performance Dashboard

## 실행 방법

Performance Accountant 에이전트를 호출하여 성과 분석.

### 데이터 소스
1. `state/portfolios.json` - 전략별 포지션, NAV, 현금
2. `state/trade_log.jsonl` - 전체 거래 이력
3. `state/performance.json` - 일별 성과 스냅샷

### 분석 항목
- 전략별 NAV + 수익률 (절대/상대)
- 전략별 MDD (최대 낙폭)
- 거래 횟수 + Win Rate
- 벤치마크 대비 (SPY, QQQ)
- 최근 N일 트렌드

### 출력 형식
테이블 형태의 전략 성과 요약 + 주요 인사이트 1~2줄.

### 리포트 파일
- 일간: `reports/daily/YYYY-MM-DD-daily.md`
- 전략별 월간: `reports/strategy/{CODE}-monthly.md`
