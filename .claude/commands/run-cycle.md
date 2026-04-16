---
name: run-cycle
description: >
  전체 트레이딩 사이클 실행 (DATA -> SIGNALS -> RISK -> RESOLVE -> EXECUTE -> REPORT).
  트리거: /run-cycle, 사이클 실행, 트레이딩, 매매 실행
---

# /run-cycle - Full Trading Cycle

## 실행 모드

### 1. Dry-Run (기본 - 안전)
```bash
python run_cycle.py --phase all --dry-run
```
실제 주문 없이 시그널 생성 + 리스크 검증만. 결과 확인 후 실행 결정.

### 2. Live Execution
```bash
python run_cycle.py --phase all
```
실제 Alpaca Paper API에 주문 전송. **반드시 dry-run 먼저 실행 후 진행.**

### 3. 개별 Phase 실행
```bash
python run_cycle.py --phase data      # 데이터만 수집
python run_cycle.py --phase signals   # 시그널만 생성
python run_cycle.py --phase risk      # 리스크 검증만
python run_cycle.py --phase execute   # 주문 실행만
python run_cycle.py --phase report    # 리포트만 생성
```

## 실행 순서

1. Trading Commander가 전체 조율
2. Signal Engine이 strategies/*.py 실행 -> Signal[] 생성
3. Risk Guardian이 각 시그널 5가지 체크
4. 충돌 해소 (규칙 기반 또는 Trading Commander 판단)
5. Execution Broker가 Alpaca 주문 실행
6. Performance Accountant가 성과 기록 + 리포트

## 실행 전 확인사항
- [ ] .env에 ALPACA_API_KEY, ALPACA_SECRET_KEY 설정됨
- [ ] ALPACA_MODE=paper 확인
- [ ] state/portfolios.json이 유효한 상태

## 실행 후 확인사항
- state/trade_log.jsonl에 거래 기록 추가됨
- state/portfolios.json NAV 업데이트됨
- reports/daily/YYYY-MM-DD-daily.md 생성됨
