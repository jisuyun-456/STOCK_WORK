# STOCK_WORK 6레이어 아키텍처

> 생성일: 2026-04-03 | 프로젝트: 미국/한국 주식 투자 분석 시스템

---

## 개요

SCM_WORK의 6레이어 하네스 구조를 1:1 미러링하여, Wall Street 전문 트레이더 + 세계 권위 대학 수준의 투자 분석 시스템을 구축.

```
┌─────────────────────────────────────────────────────┐
│  Layer 6: 오케스트레이션 (Orchestration)               │
│  ┌─────────────────────────────────────────────────┐ │
│  │  Layer 5: 팀 에이전트 (D6, D7 + 전역 D3/D5)      │ │
│  │  ┌─────────────────────────────────────────────┐ │ │
│  │  │  Layer 4: Superpowers 플러그인               │ │ │
│  │  │  ┌─────────────────────────────────────────┐ │ │ │
│  │  │  │  Layer 3: 서브에이전트 (ST-01~08)        │ │ │ │
│  │  │  │  ┌─────────────────────────────────────┐ │ │ │ │
│  │  │  │  │  Layer 2: 스킬 (Skills)              │ │ │ │ │
│  │  │  │  │  ┌─────────────────────────────────┐ │ │ │ │ │
│  │  │  │  │  │  Layer 1: CLAUDE.md + 훅 (기반)  │ │ │ │ │ │
│  │  │  │  │  └─────────────────────────────────┘ │ │ │ │ │
│  │  │  │  └─────────────────────────────────────┘ │ │ │ │
│  │  │  └─────────────────────────────────────────┘ │ │ │
│  │  └─────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Layer 1: CLAUDE.md + Hooks (기반 레이어)

**역할:** 프로젝트 정체성, 투자 원칙, 라우팅 규칙, 보안 훅

### 파일 구조
```
STOCK_WORK/
├── CLAUDE.md                          ← 프로젝트 전용 지침
~/.claude/CLAUDE.md                    ← 전역 지침 (D2/D3/D4/D5 + 공통 원칙)
STOCK_WORK/.claude/settings.json       ← 훅 설정
STOCK_WORK/.claude/hooks/
├── protect-sensitive-files.sh         ← API 키 보호
├── log-agent-usage.sh                 ← 에이전트 사용 로그
└── investment-risk-gate.sh            ← 투자 세션 로그
```

### 전역 vs 프로젝트 CLAUDE.md 분리

| 계층 | 파일 | 내용 |
|------|------|------|
| **전역** | `~/.claude/CLAUDE.md` | D2(재무/세무), D3(기술), D4(프론트), D5(PM), 공통 데이터 원칙, 워크플로우 5단계, 에이전트 작성 표준 |
| **프로젝트** | `STOCK_WORK/CLAUDE.md` | 투자 원칙(분산/손절/세금선행), 에이전트 라우팅 테이블, 데이터 소스, 투자 스타일 |
| **SCM 전용** | `SCM_WORK/CLAUDE.md` | D1(SCM/물류), D2 SCM 확장(더존/SAP), SK-01~08 라우팅 |

### Hooks (3종)

| 이벤트 | 훅 | 동작 |
|--------|---|------|
| PreToolUse(Edit\|Write) | `protect-sensitive-files.sh` | `.env`, `kis_token`, `alpha_vantage` 등 민감 파일 수정 차단 (exit 2) |
| SubagentStop | `log-agent-usage.sh` | `타임스탬프\|에이전트타입\|세션ID` → `.claude/logs/agent-usage.log` |
| Stop | `investment-risk-gate.sh` | 세션 종료 시 투자 활동 로그 기록 |

### 투자 원칙 (CLAUDE.md에 명시된 불변 규칙)
- 분산투자: 단일 종목 최대 20%, 단일 섹터 최대 40%
- 손절 원칙: 개별 종목 -10%, 포트폴리오 MDD -20% 시 검토 의무화
- 세금 선행: 매도 전 ST-06(tax-optimizer) 시뮬레이션 필수
- 데이터 기반: 뉴스·감·소문에 의한 매매 금지, 정량 분석 선행
- 레버리지 경고: 인버스/곱버스는 반드시 ST-08 + ST-05 동시 분석 후 진입

---

## Layer 2: Skills (스킬 레이어)

**역할:** 사용자가 `/명령어`로 호출하는 반복 가능한 워크플로우

### 등록 스킬

| 스킬 | 파일 | 트리거 | 설명 |
|------|------|--------|------|
| `/report` | `.claude/skills/daily-report.md` | "오늘 리포트", "시장 분석" | 일일 투자 리포트 생성 (자동/수동) |
| `/start` | (전역 상속) | 세션 시작 시 | `git log --oneline -5` + 상태 요약 + 다음 태스크 |
| `/brainstorm` | (superpowers 플러그인) | 새 기능 설계 시 | 브레인스토밍 프로세스 |

### `/report` 스킬 상세
```
트리거: /report 또는 "오늘 리포트"
프로세스:
  1. scripts/daily_report.py 실행 (데이터 수집)
  2. ST-01(리서치) + ST-02(기술적) + ST-03(매크로) 에이전트 호출
  3. Markdown 리포트 생성 → docs/reports/YYYY-MM-DD-daily.md
  4. Gmail MCP로 요약본 이메일 전송 (선택)
```

---

## Layer 3: Sub-agents (서브에이전트 레이어 — ST 시리즈)

**역할:** 좁고 깊은 전문 영역을 담당하는 8개 특화 에이전트

### 에이전트 팀 (8개)

| 코드 | 에이전트 | Wall Street 등가 | 핵심 전문성 |
|------|---------|-----------------|------------|
| **ST-01** | equity-research | Goldman Sachs MD + CFA Charterholder 20년 | DCF/Comps/Forensic(Beneish M-Score), 10-K/DART 공시 해석 |
| **ST-02** | technical-strategist | CMT Level III + 15년 Prop Trading | Wyckoff/Elliott/DeMark/VSA, 인터마켓 분석, Ichimoku |
| **ST-03** | macro-economist | PhD Economics (MIT/Chicago) | Taylor Rule, 경기사이클(Dalio), Minsky/Soros 위기 프레임워크 |
| **ST-04** | portfolio-architect | CFA III + Wharton MBA | MPT/Fama-French/Black-Litterman, Core-Satellite, Risk Parity |
| **ST-05** | risk-controller | FRM + Basel III/IV | VaR/CVaR/EVT, Taleb Barbell/Antifragile, GARCH, 스트레스 테스트 |
| **ST-06** | tax-optimizer | CPA+CTA + Big4 Tax Partner | 양도세/배당세/ISA/연금저축, W-8BEN, Tax-Loss Harvesting |
| **ST-07** | market-intelligence | Bloomberg Intelligence 15년 | DART/EDGAR 공시, 13F/Form4 수급, Earnings Call 분석 |
| **ST-08** | leveraged-etf-specialist | Chicago Booth Derivatives | Volatility Drag(L²σ²/2), 괴리율, KODEX/TIGER 인버스·곱버스 |

### 에이전트 공통 구조 (8섹션 표준)
```yaml
---
name: {id}
description: > 트리거 키워드 포함
tools: [Read, Write, Bash, Glob, Grep]
model: claude-opus-4-6
permissionMode: acceptEdits
memory: project
---
# {name} -- 역할명
## When Invoked (즉시 실행 체크리스트)
## Memory 관리 원칙
## 역할 정의
## 참조 표준 체계
## Sub-agent 구조
## 핵심 도메인 지식
## 출력 형식 가이드
## 금지 사항
```

### 라우팅 우선순위
```
사용자 요청 → 키워드 매칭 → ST(세밀한 키워드) > D(일반 키워드) > orchestrator(복합)
```

---

## Layer 4: Superpowers 플러그인

**역할:** 워크플로우 품질 보장 — 5단계 개발 사이클 + 특수 경로

### 메인 워크플로우 사이클

| 단계 | 스킵 매트릭스 | Superpower |
|------|-------------|------------|
| 1. 구상 | `/brainstorm` 명시 시만 | `superpowers:brainstorming` |
| 2. 계획 | 코드 작성 전 필수 | `superpowers:writing-plans` |
| 3. 실행 | 계획대로 구현 | `superpowers:executing-plans` |
| 4. 검토 | 구현 완료 후 | `superpowers:requesting-code-review` |
| 5. 검증 | "완료" 선언 전 | `superpowers:verification-before-completion` |

### 특수 경로
- **버그 대응:** `superpowers:systematic-debugging` → 원인 파악 후 메인 사이클 4부터 합류
- **디자인 작업:** `frontend-design:frontend-design` → 렌더링 시뮬레이션 후 3부터 합류

---

## Layer 5: Team Agents (팀 에이전트 — D 시리즈)

**역할:** 넓은 도메인을 커버하는 범용 전문가. ST 에이전트들의 결과를 통합하는 상위 레이어.

### 프로젝트 전용 (2개)

| 코드 | 에이전트 | 등가 수준 | 역할 |
|------|---------|----------|------|
| **D6** | investment-expert | CFA III + 20년 Wall Street | Graham→Buffett→Munger→Klarman→Marks 가치투자 계보. ST 에이전트 결과 통합, 투자 철학 일관성 검증, 최종 투자 의견 도출 |
| **D7** | economics-expert | PhD Economics (MIT/Princeton) + Nobel Laureate Panel | Fama vs Shiller, Kahneman/Thaler 행동경제학, Bernanke/Friedman/Krugman 거시. 학술적 이론 근거 제공, 이론-실전 괴리 지적 |

### 전역 공유 (2개)

| 코드 | 에이전트 | 공유 범위 |
|------|---------|----------|
| **D3** | tech-architect | 전역 (SCM_WORK + STOCK_WORK 모두) — 코드/API/DB/아키텍처 |
| **D5** | project-manager | 전역 (SCM_WORK + STOCK_WORK 모두) — PMBOK/Agile/KPI/MECE |

### D6 핵심 프레임워크
```
투자 대가 계보:
  가치투자: Graham → Dodd → Buffett → Munger → Klarman → Greenwald → Marks
  성장투자: Philip Fisher → Peter Lynch → Terry Smith
  매크로:   Soros → Druckenmiller → Dalio
  퀀트:     Ed Thorp → Jim Simons → Cliff Asness
  한국:     강방천, 이채원, 박현주
```

### D7 Nobel Laureate Panel
```
금융경제학: Fama(2013 EMH) vs Shiller(2013 Behavioral)
행동경제학: Kahneman(2002), Thaler(2017)
거시경제:   Bernanke(2022), Krugman(2008), Friedman(1976)
제도경제:   Acemoglu/Johnson/Robinson(2024)
금융공학:   Merton/Scholes(1997)
```

---

## Layer 6: Orchestration (오케스트레이션)

**역할:** 복수 에이전트를 조합하여 복합 요청을 처리. Goldman Sachs Investment Committee 의장 수준.

### 5가지 오케스트레이션 패턴

| 패턴 | 이름 | 구조 | 트리거 예시 |
|------|------|------|------------|
| **1** | 종합 종목 분석 | ST-01+02+03 **병렬** → D6 통합 | "삼성전자 분석해줘" |
| **2** | 매수 파이프라인 | ST-01 → ST-04 → ST-05 → ST-06 **순차** | "지금 매수해도 되나?" |
| **3** | 인버스/곱버스 진입 | ST-02+08 **병렬** → ST-05 리스크 | "KODEX 인버스 진입?" |
| **4** | 포트폴리오 종합 리뷰 | ST-04+05+07 **병렬** → D6 통합 → ST-06 세금 | "포트폴리오 점검" |
| **5** | 매도 의사결정 | ST-01+02 **병렬** → ST-06 세금 → ST-05 리스크 | "이 종목 매도할까?" |

### 실행 규칙
1. **병렬 가능** → 단일 메시지에서 Agent 도구 다중 사용으로 동시 호출
2. **순차 의존** → 이전 결과 받은 후 다음 호출
3. **결과 취합** → D6(투자 대가) 관점으로 최종 통합
4. **충돌 결론** → 사용자에게 양쪽 근거와 함께 선택지 제시 (편향 배제)

### 패턴 선택 플로우
```
사용자 요청
    │
    ├── 특정 종목 분석? ────→ 패턴 1 (종합 종목)
    ├── 매수/편입 검토? ────→ 패턴 2 (매수 파이프라인)
    ├── 인버스/곱버스? ─────→ 패턴 3 (레버리지, ST-05 필수)
    ├── 포트폴리오 전체? ───→ 패턴 4 (종합 리뷰)
    └── 매도/이익실현? ────→ 패턴 5 (매도 의사결정)
```

---

## 전체 구조 요약

```
STOCK_WORK/.claude/
├── agents/                    ← Layer 3 (ST-01~08) + Layer 5 (D6, D7) + Layer 6 (orchestrator)
│   ├── equity-research.md         ST-01
│   ├── technical-strategist.md    ST-02
│   ├── macro-economist.md         ST-03
│   ├── portfolio-architect.md     ST-04
│   ├── risk-controller.md         ST-05
│   ├── tax-optimizer.md           ST-06
│   ├── market-intelligence.md     ST-07
│   ├── leveraged-etf-specialist.md ST-08
│   ├── investment-expert.md       D6
│   ├── economics-expert.md        D7
│   └── orchestrator.md            orchestrator
├── hooks/                     ← Layer 1 (훅)
│   ├── protect-sensitive-files.sh
│   ├── log-agent-usage.sh
│   └── investment-risk-gate.sh
├── skills/                    ← Layer 2 (스킬) — 추후 생성
│   └── daily-report.md
├── settings.json              ← Layer 1 (훅 설정)
├── feature_list.json          ← 태스크 관리
└── logs/                      ← 에이전트 사용 로그

STOCK_WORK/CLAUDE.md           ← Layer 1 (프로젝트 지침)
~/.claude/CLAUDE.md            ← Layer 1 (전역 지침)
superpowers 플러그인            ← Layer 4 (외부 설치됨)
```

---

## SCM_WORK vs STOCK_WORK 비교

| 항목 | SCM_WORK | STOCK_WORK |
|------|---------|------------|
| **도메인** | 포장재 물류 SCM | 미국/한국 주식 투자 |
| **ST 에이전트** | SK-01~08 (WMS/TMS) | ST-01~08 (Investment Bank) |
| **D 에이전트** | D1(SCM)+D2(회계 SCM)+D3+D4+D5 | D6(투자)+D7(경제학)+D3+D5 |
| **모델** | claude-sonnet-4-6 | claude-opus-4-6 |
| **전문성 기준** | APICS/SCOR/SAP/GS1 | CFA/CMT/FRM/Nobel/Wall Street |
| **데이터** | Airtable → Supabase | OpenBB/pykrx/FRED → TimescaleDB |
| **훅** | 8종 (SQL안전/브랜치보호/포맷/타입체크 등) | 3종 (API키보호/에이전트로그/세션로그) |
| **공통** | 전역 CLAUDE.md, D3(기술), D5(PM), superpowers, 공통 데이터 원칙 |
