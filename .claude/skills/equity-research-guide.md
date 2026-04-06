---
name: equity-research-guide
description: >
  GS/JPM 수준 Equity Research Report 작성 가이드.
  /analyze 커맨드 실행 시 자동 참조. v1 스키마 prose 필드 작성 기준.
globs:
  - "templates/equity_report.html"
  - "scripts/equity_report_generator.py"
  - ".claude/commands/analyze.md"
---

# Equity Research Report 작성 가이드 (GS/JPM 스탠다드)

## 핵심 원칙: Inverted Pyramid

결론(Rating/Target/Thesis) → 근거(재무/밸류에이션) → 세부사항(리스크/촉매제) 순서로 작성.
첫 문장에 핵심 판단을 명시한다. 예: "PLTR에 대해 HOLD를 유지한다. 12개월 목표가 $175, 현재가 대비 +17.9% 상승여력."

## 챕터별 최소 분량

| 챕터 | 필드 | 최소 분량 |
|------|------|-----------|
| CH1 | `ch1.thesis` | 200자 이상 |
| CH2 | `ch2.platform_overview` | 200자 이상 |
| CH2 | `ch2.platforms[].description` | 150자/플랫폼 |
| CH3 | `ch3.sbc_analysis` | 150자 이상 |
| CH4 | `ch4.dcf_commentary` | 150자 이상 |
| CH5 | `ch5.short_term[].expectation` | 100자/이벤트 |
| CH6 | `ch6.risks[].description` | 150자/리스크 |
| CH7 | `ch7.macro_commentary` | 200자 이상 |
| CH8 | `ch8.conclusion` | 200자 이상 |

## 필수 차트 3개 (Chart.js)

1. **Exhibit 1** — Revenue Stacked Bar: `ch3.revenue_breakdown[]` = [{year, gov_rev, com_rev}]
2. **Exhibit 2** — Revenue + Gross Margin Combo: `ch3.income_stmt[]` (revenue + gross_m)
3. **Exhibit 3** — 12M Relative Performance: `ch7.perf_chart_data[]` = [{date, ticker_pct, spy_pct, qqq_pct}]

## v1 스키마 필수 필드

/analyze 실행 시 아래 prose 필드를 반드시 한국어로 작성 (빈 문자열 금지):

```
ch1.thesis              — 200자+ 투자 thesis (Inverted Pyramid, 첫 문장에 Rating/Target)
ch1.thesis_points[]     — 핵심 논거 3-5개 bullet (수치 포함)
ch2.platform_overview   — 200자+ 플랫폼 아키텍처 설명
ch2.platforms[]         — {name, description(150자+), revenue_contribution}
ch3.revenue_breakdown[] — [{year, gov_rev, com_rev}] FY21~FY26E
ch3.sbc_analysis        — 150자+ SBC/희석 분석 (수치 포함)
ch4.dcf.labels_wacc[]   — ["8%","9%","10%","11%","12%","13%"] (6개)
ch4.dcf.labels_tgr[]    — ["1.5%","2%","2.5%","3%","3.5%"] (5개)
ch4.dcf.matrix[][]      — 6×5 float 민감도 매트릭스
ch4.dcf_commentary      — 150자+ DCF 가정 해석
ch4.comps_commentary    — 150자+ Peer 비교 해석
ch5.short_term[].expectation — 100자+ 기대 효과
ch5.mid_term[].description   — 100자+ 테마 설명
ch6.risks[]             — {tier, title, category, probability, impact, description(150자+), bear_price}
ch7.perf_chart_data[]   — [{date, ticker_pct, spy_pct, qqq_pct}] 12개월
ch7.macro_commentary    — 200자+ 매크로/섹터 종합
ch8.kpis[]              — [{metric, threshold, current, signal, action}] 5개
ch8.conclusion          — 200자+ 최종 투자 결론
```

## 금지 표현

- "의 경우" / "~인 것으로 판단됨" / "~를 감안할 때"
- "높은 밸류에이션이 부담" → "PSR 30x는 FY26E 매출 $3.5B 기준 시총 $105B를 정당화해야 함"
- 숫자 없는 "강력한 성장", "탁월한 실적"

## 숫자 인용 규칙

- 구체적: "매출 성장률 +33% YoY" (O) / "빠른 성장" (X)
- 비교 기준: "S&P 500 대비 +47%p (12개월)"
- 시점: "FY25A 기준 FCF Margin 34%", 추정치: "FY26E"

## 품질 체크리스트

- [ ] CH1 thesis 200자+ / 첫 문장에 Rating+Target
- [ ] thesis_points 3개+ (수치 포함)
- [ ] revenue_breakdown[] 5개년+
- [ ] DCF matrix 6×5 완성
- [ ] ch6.risks[] 4개+ (tier/category 포함)
- [ ] perf_chart_data[] 12개월+
- [ ] ch8.kpis[] 5개 (signal 필드 포함)
- [ ] conclusion 200자+
- [ ] 금지 표현 없음
