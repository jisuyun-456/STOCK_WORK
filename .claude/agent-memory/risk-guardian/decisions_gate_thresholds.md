---
name: Risk Guardian Gate Thresholds
description: 리스크 게이트 임계치 및 CB NAV 소스 선택 근거
type: project
owner: risk-guardian
---

**Why:** 리스크 게이트 임계치는 Paper Trading 운용 경험 기반 조정. CB는 실계좌 기준.
**How to apply:** 임계치 조정 제안 전 이 파일 참조. 변경 시 근거 append.

---

## 리스크 게이트 임계치

| 게이트 | 임계값 | 근거 |
|--------|--------|------|
| 포지션 한도 | ≤ 20% | 단일 종목 과집중 방지 (CLAUDE.md 투자 원칙) |
| 섹터 집중 (per-strategy) | MOM/VAL ≤ 30%, QNT ≤ 25% | MOM 10종목 기준 3종목/섹터, QNT 20종목 기준 5종목/섹터 |
| 섹터 집중 (cross-strategy) | ≤ 30% | 포트폴리오 전체 1/3 초과 = 과집중 |
| VaR (95%, 1일) | ≤ 3% | Alpaca paper 기준 적정 위험 한도 |
| 상관관계 | ≤ 0.85 | 0.85 이상 = 사실상 동일 포지션 |
| 현금 버퍼 | ≥ 5% | 긴급 리밸런싱/margin call 대비 |

## CB NAV 소스: account_total_history (2026-04-15 결정)
- **결정:** CB MDD 계산 기준 = `portfolios.json.account_total_history` (실제 Alpaca 계좌 잔고)
- **이전 방식:** 전략별 NAV 합계 (`sum(strategies.*.allocated)`) → 재배분 시 오신호
- **트리거:** CRISIS 재배분 후 CB false-EMERGENCY 발동 사고 (commit 5bc230d)

## VaR 가중치 순서 규칙 (2026-04-16 결정)
- yfinance는 가격 데이터를 알파벳 정렬로 반환
- weight 배열은 반드시 `returns.columns` 순서에 맞게 정렬 후 사용
- `zip(symbols, weights)`로 dict 생성 후 `pd.Series(weight_dict)[returns.columns]`로 정렬
