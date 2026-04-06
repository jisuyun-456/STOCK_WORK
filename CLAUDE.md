# STOCK_WORK — 미국/한국 주식 투자 분석 시스템

## 이 프로젝트 열면 자동 실행
다른 것보다 먼저, 아래를 즉시 실행할 것:
1. `git log --oneline -5` → 최근 작업 히스토리 확인
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개"를 나에게 말해줄 것.
세션 종료 시: git commit 필수.

## 투자 원칙 (불변)
- 분산투자: 단일 종목 최대 20%, 단일 섹터 최대 40%
- 손절 원칙: 개별 종목 -10%, 포트폴리오 MDD -20% 시 검토 의무화
- 세금 선행: 매도 전 Tax & Compliance 시뮬레이션 필수
- 데이터 기반: 뉴스·감·소문에 의한 매매 금지, 정량 분석 선행
- 레버리지 경고: 인버스/곱버스는 반드시 Market Scanner + Quant Strategist 동시 분석 후 진입

## 투자 스타일
- 코어: 장기 가치투자 (Graham→Buffett 계보)
- 새틀라이트: 모멘텀/테마/인버스·곱버스 (기회 포착형)
- 시장: 미국/한국 동등 ��버, 기회에 따라 ��동적

## 에이전트 팀 — Lean Trading Desk (5명)

> 핵심 철학: "에이전트는 사고한다. 스킬은 실행한다. 도구가 차별화한다."

```
Chief Strategist (opus) — 다관점 ��합 + 최종 판단 + 동적 오케스트레이션
├── Fundamental Analyst (sonnet) — 기업가치 + 매크로 경제
├── Quant Strategist (sonnet) — 기술적 분석 + 리스크 + ���트폴리오
├── Tax & Compliance (sonnet) — 세금 최적화 + 투자원칙 게이트키퍼
└─��� Market Scanner (sonnet) — 공시/수���/뉴스 + ���버리지ETF
```

### 라우팅 키워드

| 키워드 | 에이전트 |
|--------|---------|
| PER, PBR, ROE, DCF, 밸류에이션, 실적, Moat, 금리, 환율, GDP, CPI, 연준, 매크로 | Fundamental Analyst |
| 이동평균, RSI, MACD, 볼린저, 차트, VaR, MDD, 포지션사이징, 포트폴리오, 리밸런싱, 팩터 | Quant Strategist |
| 양도세, 배당���, ISA, 연금저축, 세금, 절세, 손익통산 | Tax & Compliance |
| 공시, 뉴스, 수급, 13F, 내부자거래, 센티멘트, 인버스, 곱버스, 레버리지ETF, 괴리율 | Market Scanner |
| 종합 분석, 매수/매도 판단, 복합 요청 | Chief Strategist |

> **라우팅 우선순위:** 스킬 매칭 > 단일 에이전트 직접 위임 > Chief Strategist 통합

### 동적 오케스트레이션 규칙 (4개)

| 규칙 | 조건 | 동작 |
|------|------|------|
| 1 | 매수/매도 판단 | Tax & Compliance 경유 필수 |
| 2 | 레버리지 ETF | Quant Strategist 병렬 분석 필수 |
| 3 | 단일 도메인 질문 | 해당 에이전트 직접 위임 |
| 4 | 2개+ 도메인 교차 | Chief Strategist 동적 조합 |

### 스킬 (8개)

| 스킬 | 트리거 | 호출 에이전트 |
|------|--------|-------------|
| `/analyze {SYMBOL}` | 분석해줘, 보고서 | Fundamental + Quant + Market Scanner |
| `/screen` | 스크리닝, 종목 찾아줘 | Market Scanner |
| `/portfolio` | 포트폴리오, ��밸런싱 | Quant + Tax & Compliance |
| `/macro` | 매크로, 경기, ��리 | Fundamental Analyst |
| `/trade-check {SYMBOL}` | 매수해도 돼?, 매도? | Chief Strategist (전체 조율) |
| `/daily` | 일일 리포트, 오늘 시장 | Market Scanner + Quant |
| `/tax-sim` | 세금, 양도세, 절세 | Tax & Compliance |
| `/leverage-check` | 인버스, 곱버스, 레버리지 | Market Scanner + Quant (병렬 필수) |

### 범용 전문가 (전역 CLAUDE.md 상속)

| 역할 | 에이전트 | 트리거 |
|------|---------|--------|
| 코드/인프라 | D3 tech-architect (전역) | 코드, API, DB, 배포 |
| 프로젝트 관리 | D5 project-manager (전역) | 프로젝트 계획, KPI, MECE |

## 데이터 소스
- 한���: Korean Stock MCP (DART+KRX), 네이버 금융, BOK ECOS
- 미국: Yahoo Finance MCP, FMP MCP (SEC 재무 심층), FRED
- API 키: .env 파일 (절대 커밋 금지)

## FMP API 제한 (필수 준수)
- **일일 한도: 250콜** (무료 플랜)
- FMP 호출 전 반드시 `python scripts/fmp_rate_limiter.py check` 실행
- 200콜(80%): WARNING — 알림 표시, 계속 가능
- 245콜(98%): CRITICAL — 필수 분석�� 허용
- 250콜(100%): BLOCKED — FMP 호출 완전 차단, 내일 자동 리셋

## 태스크 관리
`.claude/feature_list.json` — 분석 대기 종목, 리밸런싱 태스크, 세금 이벤트 목록
