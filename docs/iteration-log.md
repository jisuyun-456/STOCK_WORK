# AutoResearch Iteration Log

## Iteration 3 Risk Gate 분석 (2026-04-15)

### 비교: run-d1 (Iteration 2) vs run-d2 (Iteration 3)

| 지표 | d1 (Iteration 2) | d2 (Iteration 3) | 변화 |
|------|-----------------|-----------------|------|
| PASS | 15 | 28 | +13 |
| FAIL | 8 | 0 | -8 |
| **통과율** | **65.2%** | **100.0%** | **+34.8%p** |
| Approved | 14/20 + 1/3 | 28/28 | 완전 통과 |

### d1 Gate 실패 원인 (해소됨)
- cash_buffer: 8회 — LEV 전략 음수 현금 문제
- position_limit: 6회 — 포지션 크기 초과
- sector_concentration: 3회 — 섹터 집중
- portfolio_var: 2회 — VaR 초과

### 개선 원인
1. **Regime 변화**: NEUTRAL → BULL (VIX=18.4, SPY/SMA200=1.05, news=+0.15)
2. **MDD 버그 수정** (`fbceeeb`): nav_history 리셋으로 포트폴리오 상태 정상화
3. **Capital**: $99,753 → $100,421 (현금 여유 회복)

### Iteration 3 결론
- Variant D 파라미터 (lookback=252, min_composite_score=0.20) 현행 유지 확정
- BULL 레짐에서 Risk gate 100% 통과 — 안정적
- cash_buffer 이슈는 BULL 레짐에서 자연 해소됨 (Iteration 4에서 CRISIS/BEAR 레짐 시뮬레이션 필요)

### 다음 Iteration 4 후보 이슈
- CRISIS/BEAR 레짐에서 cash_buffer fail 재현 여부 확인
- QNT FF5 데이터 43일 지연 해소 (pandas_datareader 설치 또는 대안)
- VAL FCF threshold → REGIME_FILTERS 연결 (strategy_params.json dead config 정리)

## Iteration 3 VAL FCF Threshold 진단 (2026-04-15)

### 결과: 변경 불필요 (no-op)

| 항목 | 값 |
|------|-----|
| 현재 레짐 | BULL |
| BULL FCF threshold | 3% (REGIME_FILTERS) |
| 필터 통과 수 | **19개** → 상위 5개 선택 |
| 판정 | ✅ 양호 (max_positions=5 충분히 초과) |

### Dead Config 이슈 발견 (Iteration 4 정리 대상)
- `strategies/value_quality.py:300`: `self.fcf_yield_threshold` 로드됨
- `generate_signals()`: REGIME_FILTERS의 `min_fcf_yield` 사용 (strategy_params.json 값 무시)
- `config/strategy_params.json`의 `fcf_yield_threshold: 0.05` → **실제 미사용 (dead config)**
- Iteration 4에서 둘 중 하나로 통합: strategy_params.json 값을 REGIME_FILTERS에 연결하거나 dead config 제거

### REGIME_FILTERS 현재값
- NEUTRAL: max_pe=20, min_roe=12%, min_fcf_yield=4%
- CRISIS:  max_pe=15, min_roe=15%, min_fcf_yield=6%
- BULL:    max_pe=25, min_roe=10%, min_fcf_yield=3%
- BEAR:    max_pe=18, min_roe=13%, min_fcf_yield=5%

## Iteration 4 (2026-04-15)

### 구현 내용
1. `--force-regime` CLI 플래그 추가 (`run_cycle.py`) — BULL/BEAR/NEUTRAL/CRISIS 강제 오버라이드 (시뮬레이션/테스트용)
2. dead config 제거: `value_quality.py:300` `self.fcf_yield_threshold` 삭제, `strategy_params.json`에서도 제거

### 4-레짐 Risk Gate 통과율 비교

| 레짐 | Gate 통과율 | VAL 필터 통과 | 주요 실패 Gate |
|------|------------|--------------|--------------|
| NEUTRAL (Iter2) | 65.2% (15/23) | 6개 | cash_buffer×8, position_limit×6, sector×3 |
| BULL (Iter3)    | **100%** (28/28) | **19개** | 없음 |
| CRISIS (Iter4)  | 85.7% (12/14) | 2개 | position_limit×2, sector×2, var×2 |
| BEAR (Iter4)    | **100%** (18/18) | 4개 | 없음 |

### 핵심 발견
- **cash_buffer 이슈**: NEUTRAL에서만 발생 — 포트폴리오 음수 현금 상태에서 레짐 전환 직후 임시 현상. BULL/BEAR/CRISIS에선 없음.
- **CRISIS VAL**: P/E<15 + ROE>15% + FCF>6% 필터 통과 2개뿐 → 고퀄 종목 집중 (정상 동작)
- **CRISIS gate fail 2건**: 고변동성 종목이 position_limit + sector_concentration + portfolio_var 3중 실패 → 정상적 리스크 차단
- **BEAR**: 100% 통과 — VAL 4개(P/E<18, ROE>13%, FCF>5%), 방어적이나 과도하게 보수적이지 않음

### FF5 데이터 상태
- 현재: 47일 지연 (최신: 2026-02-27), WARNING 수준 (90일 초과 시 degraded)
- Kenneth French 공식 업데이트 주기 기인 — 코드 수정으로 해결 불가
- 현재 QNT 시그널 정상 생성 중 (degraded 아님)

### 다음 Iteration 5 후보 이슈
- `--force-regime`이 regime_allocator 배분에는 미적용 (신호 생성만 override) → allocator도 연동 검토
- CRISIS 2건 gate fail 원인 종목 상세 분석 (어떤 섹터/종목인지)
- QNT position_pct 조정 검토 (CRISIS 레짐에서 VaR gate 개선 여지)
