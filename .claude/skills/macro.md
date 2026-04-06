---
name: macro
description: >
  거시경제 대시보드 + 시장 시사점.
  "매크로", "경기", "금리", "연준", "한은", "경제 전망" 요청 시 자동 트리거.
---

# /macro — Macro Dashboard

## 언제 사용
- "매크로 현황 알려줘"
- "경기 어떻게 보고 있어?"
- "금리 전망"
- "연준 다음 결정 어떻게 될까?"

## Step 1: 데이터 수집

Fundamental Analyst에 위임하여:
- FRED: Fed Funds Rate, CPI, Core PCE, GDP, Unemployment, ISM PMI, LEI
- BOK ECOS: 기준금리, CPI, GDP, 수출입, 가계부채
- Yahoo Finance: DXY, 원/달러, VIX, 10Y Treasury, Gold

## Step 2: Fundamental Analyst 매크로 분석

- 현재 경기사이클 위치 판단 (NBER 4단계)
- Taylor Rule 적용 → 적정 금리 vs 현재 금리
- Dalio Economic Machine 프레임 → 부채사이클 위치
- 학파 교차 검토 (케인즈/하이에크/통화주의)

## Step 3: 출력

1. 매크로 대시보드 (핵심 지표 테이블)
2. 경기사이클 위치 판단
3. 시나리오: Base / Bull / Bear (확률%)
4. 자산배분 시사점
5. 다음 주요 이벤트 캘린더
