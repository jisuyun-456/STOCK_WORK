---
name: Execution Broker Regression Bugs
description: 주문 실행/로그 기록 경계에서 발생한 회귀 버그 이력.
type: project
owner: execution-broker
---

### [T6] order_manager에서 항상 status="submitted" 하드코딩 → trade_count=0

- **Symptom:** `state/trade_log.jsonl`에 모든 주문이 status="submitted"로만 기록. trade_count=0
- **Root cause:** `execution/order_manager.py`에서 Alpaca 응답의 `fill_status` 대신 항상 `"submitted"` 문자열 하드코딩
- **Fix:** `fill_status` 변수 직접 사용. `date`, `qty`, `filled_avg_price` 필드 추가 (commit 0d8f3a6)
- **Regression guard:**
  - order 관련 필드 수정 시 `trade_log.jsonl`에서 `status != "submitted"` 레코드 존재 여부 확인
  - Alpaca 응답 구조 변경 시 `fill_status` 매핑 업데이트 필수
  - `trade_count` = 0이면 order_manager 먼저 확인 (risk_validator가 아님)

### [T12] trade_log JSON 파싱 방어 미비 + fsync 없음 → 크래시 시 데이터 손실

- **Symptom:** 파이프라인 crash 후 재시작 시 trade_log.jsonl의 마지막 레코드가 손상 또는 누락
- **Root cause:** trade_log 쓰기 시 `f.write(json.dumps(...) + "\n")` 후 flush/fsync 없음. JSON 파싱 시 방어 코드 없음
- **Fix:** `f.flush(); os.fsync(f.fileno())` 추가. JSON 파싱에 try/except + 손상 라인 스킵 (commit c15a356)
- **Regression guard:**
  - trade_log 쓰기 코드 수정 시 `os.fsync` 유지 필수
  - trade_log 읽기 코드는 항상 per-line try/except JSON 파싱

### [last-write-wins] 복수 전략 동일 종목 보유 시 Alpaca sync가 단일 전략에만 귀속

- **Symptom:** MOM과 QNT가 NVDA를 공동 보유 중인데 sync 후 한 전략(마지막 처리된 전략)의 포지션만 기록됨
- **Root cause:** `run_cycle.py._sync_alpaca_positions()`에서 `symbol_strategy_map` last-write-wins 방식. 같은 종목을 2개 전략이 보유 시 두 번째 전략이 첫 번째를 덮어씀
- **Fix:** `last_action` 추적 + 복수 전략 공동 보유 시 notional 비례 분할 (SELL 이력 있는 전략 제외). 분할 불가 시 equal split fallback (commit 257bd16)
- **Regression guard:**
  - 동일 종목 2개 전략 보유 시 portfolios.json에서 두 전략 모두 qty > 0인지 확인
  - sync 후 `sum(all_strategies.NVDA.qty) ≈ alpaca.NVDA.qty` 일치 검증
