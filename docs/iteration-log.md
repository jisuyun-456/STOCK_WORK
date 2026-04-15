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
