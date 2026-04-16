---
name: Risk Guardian Regression Bugs
description: 리스크 게이트/Circuit Breaker 경계에서 발생한 회귀 버그 이력.
type: project
owner: risk-guardian
---

### [T5] VaR weight-to-symbol 순서 불일치 → 잘못된 VaR 계산

- **Symptom:** VaR 계산 결과가 실제 포지션 위험도와 다름. 특정 종목 비중이 다른 종목으로 매핑됨
- **Root cause:** `execution/risk_validator.py` VaR 계산 시 weight 배열은 positions 입력 순서, yfinance 가격 데이터는 알파벳 정렬 반환 → 불일치
- **Fix:** yfinance 반환 컬럼 순서에 맞게 weight 배열 재정렬 (commit 196a90e)
- **Regression guard:**
  - VaR 계산 코드 수정 시 `symbols == returns.columns.tolist()` 순서 일치 assertion 추가
  - `pd.DataFrame(returns)[symbols]` 형태로 명시적 컬럼 선택 사용
  - 새 데이터 소스(yfinance 외) 추가 시 반환 순서 문서화 필수

### [CB false-EMERGENCY] CRISIS 재배분으로 전략 NAV 합계 감소 → CB가 실손실로 오인

- **Symptom:** Circuit Breaker가 EMERGENCY 발동. MDD -19.7% 경보. 실제 Alpaca 잔고는 $100,421 정상
- **Root cause:** `execution/circuit_breaker.py`의 `_get_nav_history()`가 portfolios.json의 전략별 NAV 합계를 사용. CRISIS 재배분으로 LEV $50k→$25k로 줄면서 전략 NAV 합계가 $100k→$80k 감소 → CB가 -19.7% "손실"로 오인
- **Fix:** `_get_nav_history()` → `account_total_history` 우선 사용 (실제 Alpaca 계좌 기준) (commit 5bc230d). `portfolios.json`에 `account_total_history` 백필
- **Regression guard:**
  - CB NAV 소스는 항상 `account_total_history` (실계좌 기준). 전략별 allocated 합계 절대 사용 금지
  - 재배분 후 CB 경보 발동 시 먼저 `account_total_history` vs `sum(allocated)` 차이 확인
  - (cross-ref: trading-commander/bugs_regression_log.md — 재배분 오케스트레이션 관점)
