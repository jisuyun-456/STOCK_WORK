---
name: screen
description: >
  조건 기반 종목 스크리닝 + 점수 랭킹.
  "스크리닝", "종목 찾아줘", "조건 검색", "필터링" 요청 시 자동 트리거.
---

# /screen — Market Screening

## 언제 사용
- "저PER 종목 찾아줘"
- "배당수익률 높은 종목"
- "종목 스크리닝 해줘"
- 조건 기반 종목 필터링 요청

## Step 1: 스크리닝 조건 확인

사용자 요청에서 조건 추출. 미지정 시 기본 조건 제안:
- 시장: US / KR / Both
- 밸류에이션: PER, PBR, EV/EBITDA 범위
- 수익성: ROE, 영업이익률 최소
- 성장: 매출/이익 성장률
- 배당: 배당수익률, 연속 배당 연수
- 재무 건전성: 부채비율, Piotroski F-Score

## Step 2: 데이터 수집

```bash
cd scripts && python3 market_screener.py --market US --conditions "per<15,roe>15,div>2"
```

Yahoo Finance MCP 보조:
- `mcp__yahoo-finance__screen_stocks` (조건에 따라)

## Step 3: Market Scanner 에이전트 분석

Market Scanner에 위임:
- 스크리닝 결과에 대한 수급/공시 크로스체크
- Piotroski F-Score / Altman Z-Score 부가
- 최종 랭킹 산출

## Step 4: 결과 출력

| 순위 | 티커 | 종목명 | PER | PBR | ROE | 배당률 | F-Score | 비고 |
|------|------|--------|-----|-----|-----|--------|---------|------|

상위 10개 종목 + 각 종목 1줄 코멘트
