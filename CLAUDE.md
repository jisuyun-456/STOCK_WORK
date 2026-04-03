# STOCK_WORK — 미국/한국 주식 투자 분석 시스템

## 이 프로젝트 열면 자동 실행
다른 것보다 먼저, 아래를 즉시 실행할 것:
1. `git log --oneline -5` → 최근 작업 히스토리 확인
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개"를 나에게 말해줄 것.
세션 종료 시: git commit 필수.

## 투자 원칙 (불변)
- 분산투자: 단일 종목 최대 20%, 단일 섹터 최대 40%
- 손절 원칙: 개별 종목 -10%, 포트폴리오 MDD -20% 시 검토 의무화
- 세금 선행: 매도 전 ST-06(tax-optimizer) 시뮬레이션 필수
- 데이터 기반: 뉴스·감·소문에 의한 매매 금지, 정량 분석 선행
- 레버리지 경고: 인버스/곱버스는 반드시 ST-08 + ST-05 동시 분석 후 진입

## 투자 스타일
- 코어: 장기 가치투자 (Graham→Buffett 계보)
- 새틀라이트: 모멘텀/테마/인버스·곱버스 (기회 포착형)
- 시장: 미국/한국 동등 커버, 기회에 따라 유동적

## 에이전트 팀 라우팅

### 프로젝트 특화 에이전트 (세밀한 키워드 우선)

| 키워드 | 에이전트 |
|--------|---------|
| PER, PBR, ROE, DCF, 10-K, 사업보고서, 밸류에이션, 실적, Moat | ST-01 equity-research |
| 이동평균, RSI, MACD, 볼린저, 지지선, 저항선, 차트, 기술적, Elliott | ST-02 technical-strategist |
| 금리, 환율, 경기사이클, GDP, CPI, 연준, 한은, 매크로 | ST-03 macro-economist |
| 포트폴리오, 비중, 리밸런싱, 섹터분산, 편출입, 팩터 | ST-04 portfolio-architect |
| 손절, MDD, VaR, 포지션사이징, 리스크, 스트레스테스트, 켈리 | ST-05 risk-controller |
| 양도세, 배당세, ISA, 연금저축, 세금, 절세, 손익통산 | ST-06 tax-optimizer |
| 공시, 뉴스, 수급, 13F, 내부자거래, 센티멘트, Earnings | ST-07 market-intelligence |
| 인버스, 곱버스, 레버리지ETF, 변동성끌림, 괴리율, KODEX, TIGER | ST-08 leveraged-etf-specialist |

### 범용 전문가 에이전트 (일반 키워드)

| 키워드 | 에이전트 |
|--------|---------|
| 투자 전략, 가치투자, 성장투자, 장기투자, 매수/매도 판단 | D6 investment-expert |
| 경제학, 거시경제 이론, 학술적 분석, 경제 전망 | D7 economics-expert |
| 코드, API, DB, 배포, 아키텍처, 성능 | D3 tech-architect (전역) |
| 프로젝트 계획, 리스크, KPI, MECE, 일정 | D5 project-manager (전역) |
| 종합 분석, 매수/매도 의견, 전체 리뷰, 포트폴리오 점검 | orchestrator |

> **라우팅 우선순위:** 프로젝트 특화(세밀한 키워드) > 범용 전문가(일반 키워드)

## 데이터 소스
- 한국: Korean Stock MCP (DART+KRX), 네이버 금융, BOK ECOS
- 미국: Yahoo Finance MCP, FMP MCP (SEC 재무 심층), FRED
- API 키: .env 파일 (절대 커밋 금지)

## FMP API 제한 (필수 준수)
- **일일 한도: 250콜** (무료 플랜)
- FMP 호출 전 반드시 `python scripts/fmp_rate_limiter.py check` 실행
- 200콜(80%): ⚠️ WARNING — 알림 표시, 계속 가능
- 245콜(98%): 🟡 CRITICAL — 필수 분석만 허용, 사용자에게 알림
- 250콜(100%): 🔴 BLOCKED — FMP 호출 완전 차단, 내일 자동 리셋
- 일일 리포트(자동): ~50콜 예상, 수동 분석 포함 하루 최대 ~150콜
- **에이전트는 FMP 호출 시 `record_calls(n, source)` 로 사용량 기록할 것**

## 태스크 관리
`.claude/feature_list.json` — 분석 대기 종목, 리밸런싱 태스크, 세금 이벤트 목록
