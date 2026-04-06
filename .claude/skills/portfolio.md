---
name: portfolio
description: >
  포트폴리오 리뷰 + 리밸런싱 제안 + 세금 영향 분석.
  "포트폴리오", "점검", "리밸런싱", "비중 조정" 요청 시 자동 트리거.
---

# /portfolio — Portfolio Review

## 언제 사용
- "포트폴리오 점검해줘"
- "리밸런싱 필요한지 봐줘"
- "내 포트폴리오 분석"

## Step 1: 현재 포트폴리오 로드
- `scripts/simulation_tracker.py`에서 현재 포지션 조회
- 또는 사용자가 직접 제공한 포트폴리오

## Step 2: Quant Strategist 분석
- 비중/섹터/팩터 노출 진단
- VaR/CVaR/MDD 리스크 측정
- 최적 비중 제안 (Mean-Variance / HRP)
- 리밸런싱 필요 여부 판단

## Step 3: Tax & Compliance 검증
- 리밸런싱 시 발생하는 양도세 시뮬레이션
- 종목/섹터 한도 준수 여부
- Tax-Loss Harvesting 기회

## Step 4: 통합 결과 출력
1. 현재 포트폴리오 현황표
2. 리스크 대시보드
3. 리밸런싱 제안 (Before → After)
4. 세금 영향 시뮬레이션
5. 최종 권고
