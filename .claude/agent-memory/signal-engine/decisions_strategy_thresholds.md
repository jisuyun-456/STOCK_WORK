---
name: Signal Engine Strategy Thresholds
description: 전략별 임계치(QNT min_composite, MOM lookback, GRW 필터) 선택 근거
type: project
owner: signal-engine
---

**Why:** 임계치는 이론적 최적값이 아닌 운용 중 관측된 score 분포 기반으로 설정.
**How to apply:** 임계치 수정 제안 전 아래 근거 섹션 참조. 수정 시 새 근거 엔트리 append.

---

## QNT min_composite_score = 0.01
- **결정 시점:** 2026-04-16 (T1 수정)
- **근거:** FF5 factor score 실측 분포 p5≈0.005, p50≈0.02, p95≈0.08. 0.3은 전체 유니버스를 필터 아웃
- **변경 시 검토:** score 정규화 방식(Z-score vs rank vs raw)이 바뀌면 재조정 필수. 변경 전 `scores.describe()` 출력 확인

## MOM lookback = 252일 (12개월)
- **결정 시점:** 2026-04-14 Iteration 2 (Variant A/B/C 비교)
- **근거:** lookback=126(6개월) 대비 lookback=252(12개월)가 더 안정적인 추세 반영. 6개월은 단기 노이즈에 민감
- **Variant B 비교 결과:** B(lookback=126)는 AMAT/LRCX 1-2위, A(lookback=252)는 APLD/RKLB 1-2위 — 전혀 다른 종목 선택

## GRW composite score = 0.5×모멘텀 + 0.3×매출성장률 + 0.2×퀄리티
- **결정 시점:** 2026-04-15 (growth_smallcap.py 초기 구현)
- **근거:** 소형주 텐배거 발굴 목적. 모멘텀 최우선(50%), 성장성(30%), 퀄리티 안전망(20%)
- **필터:** 시총 $200M~$5B, 매출성장률 10%+, 음수 모멘텀 제외

## GRW BEAR/CRISIS 차단
- **결정:** BEAR → BUY 차단, CRISIS → 전량 청산
- **근거:** 소형주는 하락장에서 대형주 대비 낙폭이 크므로 방어적 운용 필수
