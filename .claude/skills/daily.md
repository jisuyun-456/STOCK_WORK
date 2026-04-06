---
name: daily
description: >
  일일 시장 브리핑 + 포트폴리오 현황.
  "일일 리포트", "오늘 시장", "데일리", "브리핑" 요청 시 자동 트리거.
---

# /daily — Daily Briefing

## 언제 사용
- "일일 리포트"
- "오늘 시장 어때?"
- "데일리 브리핑"
- `/daily` 명시 호출

## Step 1: 데이터 수집

```bash
cd scripts && python3 daily_report.py --format all
```

## Step 2: Market Scanner 보강

Market Scanner에 위임:
- 거래량 급등 종목 TOP 10
- 주요 공시/뉴스 요약
- 수급 동향 (외국인/기관)

## Step 3: Quant Strategist 보강

Quant Strategist에 위임:
- 현재 포트폴리오 리스크 상태
- VIX/변동성 현황
- 리밸런싱 필요 여부 체크

## Step 4: 리포트 출력

4개 섹션:
1. 나스닥/코스피 일일 분석
2. 글로벌/미국 시장 종합
3. 나스닥 떠오르는 기업 (거래량 급등 TOP 10)
4. 매크로 기반 종목 추천

출력 파일: `docs/reports/YYYY-MM-DD-daily.md` + `.html`

## Step 5: Gmail 발송 (선택)

사용자 요청 시 Gmail MCP로 발송:
- Subject: 일일 투자 리포트 — YYYY-MM-DD
- 스케줄: CronCreate "27 8 * * 1-5" (평일 08:27 KST)
