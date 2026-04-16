# Claude Code 하네스 아키텍처 — Paper Trading System

> 이 문서는 Claude Code를 단순 코딩 도우미가 아닌 **자율 에이전트 오케스트레이션 시스템**으로 구성한 방법을 설명합니다.

---

## 전체 레이어 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER / CLAUDE CODE CLI                    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 0 │ CLAUDE.md          │ 프로젝트 컨텍스트 + 지시 주입    │
├──────────┼────────────────────┼──────────────────────────────────┤
│  Layer 1 │ .claude/settings.json │ 권한 + 훅 설정 (harness)     │
├──────────┼────────────────────┼──────────────────────────────────┤
│  Layer 2 │ .claude/hooks/     │ PreToolUse / SubagentStop 트리거 │
├──────────┼────────────────────┼──────────────────────────────────┤
│  Layer 3 │ .claude/skills/    │ 사용자 호출 슬래시 커맨드        │
├──────────┼────────────────────┼──────────────────────────────────┤
│  Layer 4 │ .claude/agents/    │ 전문 서브에이전트 팀 (10명)      │
├──────────┼────────────────────┼──────────────────────────────────┤
│  Layer 5 │ strategies/ + run_cycle.py │ 결정론적 Python 비즈니스 로직 │
└──────────┴────────────────────┴──────────────────────────────────┘
```

**핵심 철학:**
- **전략 = Python 모듈** (결정론적, 테스트 가능, 재현 가능)
- **에이전트 = 오케스트레이션** (충돌 해소, 리스크 판단, 자연어 추론)
- 두 레이어를 명확히 분리해 AI 판단이 비즈니스 로직을 오염시키지 않음

---

## Layer 0 — CLAUDE.md (컨텍스트 주입)

파일: `CLAUDE.md` (프로젝트 루트에 위치)

Claude Code가 프로젝트를 열 때 자동으로 읽는 **시스템 프롬프트 역할**을 합니다.

### 담는 내용

| 섹션 | 역할 |
|------|------|
| 세션 시작 자동 실행 | 매 세션마다 git log + 계좌 확인 + 이전 상태 복원 |
| 투자 원칙 (Immutable) | AI가 절대 위반할 수 없는 하드 룰 |
| 전략 테이블 | 어떤 전략이 있고 어느 파일인지 맵핑 |
| 에이전트 라우팅 테이블 | 키워드 → 어느 에이전트로 위임할지 |
| 파이프라인 구조 | Phase 1~7 흐름 (AI가 전체 그림을 알고 있어야 함) |
| 검증 체크포인트 | "완료" 선언 전 반드시 실행할 명령어 목록 |

### 핵심 패턴: 금지 표현

```markdown
### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다" -> 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" -> 실행 증거 없이 사용 금지
```

AI가 근거 없이 "완료"를 선언하는 것을 CLAUDE.md 수준에서 차단합니다.

---

## Layer 1 — settings.json (하네스 설정)

파일: `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 -:*)",
      "Bash(git:*)"
    ],
    "deny": [
      "Bash(rm -rf:*)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/protect-api-keys.sh" }]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [{ "type": "command", "command": "bash .claude/hooks/log-execution.sh" }]
      }
    ]
  }
}
```

### 권한 모델
- `allow`: 화이트리스트 — python, pip, git만 허용
- `deny`: 블랙리스트 — `rm -rf` 하드 차단
- 매처 패턴: `Bash(명령어:*)` 형식으로 세밀하게 제어

### 훅 이벤트 종류
| 이벤트 | 트리거 시점 |
|--------|-----------|
| `PreToolUse` | 도구 실행 직전 (차단 가능) |
| `PostToolUse` | 도구 실행 직후 |
| `SubagentStop` | 서브에이전트 종료 시 |
| `SessionStart` | 세션 시작 시 |

---

## Layer 2 — Hooks (보안 + 감사)

디렉토리: `.claude/hooks/`

### protect-api-keys.sh

```bash
#!/usr/bin/env bash
# PreToolUse (Edit|Write) 훅
FILE_PATH="${TOOL_INPUT_FILE_PATH:-}"

case "$FILE_PATH" in
  *.env|*.env.*|*.key|*.pem|*credentials*)
    echo "BLOCKED: Cannot modify sensitive file: $FILE_PATH" >&2
    exit 2  # exit 2 = Hard block (실행 중단)
    ;;
esac
```

**중요:** `exit 2`는 Claude Code에서 **하드 블록** 신호입니다. 에이전트가 민감한 파일을 수정하려 하면 즉시 차단됩니다.

### log-execution.sh

```bash
#!/usr/bin/env bash
# SubagentStop 훅 — 모든 에이전트 실행 기록
echo "{\"ts\":\"...\",\"agent\":\"${AGENT_TYPE:-unknown}\"}" >> logs/agent-usage.log
```

어떤 에이전트가 언제 실행됐는지 자동으로 로깅합니다.

---

## Layer 3 — Skills (슬래시 커맨드)

디렉토리: `.claude/skills/`

사용자가 `/run-cycle` 처럼 슬래시 커맨드를 입력하면 Claude Code가 해당 skill 파일을 로드해 지시를 따릅니다.

### 구조

```
.claude/skills/
├── run-cycle.md    # /run-cycle → 전체 트레이딩 사이클 실행
├── rebalance.md    # /rebalance → 포트폴리오 리밸런싱
├── performance.md  # /performance → 성과 리포트
└── go-live.md      # /go-live → Paper → Live 전환 체크리스트
```

### skill 파일 형식

```markdown
---
name: run-cycle
description: >
  전체 트레이딩 사이클 실행. 트리거: /run-cycle, 사이클 실행
---

# /run-cycle - Full Trading Cycle

## 실행 모드

### 1. Dry-Run (기본 - 안전)
\```bash
python run_cycle.py --phase all --dry-run
\```
...
```

**핵심:** skill은 Claude에게 "이 커맨드가 호출되면 이 절차를 따르라"는 절차서입니다. 코드가 아닌 자연어 지시문입니다.

---

## Layer 4 — Agents (전문 서브에이전트)

디렉토리: `.claude/agents/`

각 에이전트는 독립적인 Claude 인스턴스로, 특정 도메인에 집중합니다.

### 에이전트 팀 구성

```
.claude/agents/
├── trading-commander.md    ← 오케스트레이터 (Opus 모델)
├── signal-engine.md        ← 전략 실행 + 시그널 종합
├── risk-guardian.md        ← 5가지 리스크 게이트 검증
├── execution-broker.md     ← Alpaca 주문 실행
├── performance-accountant.md ← P&L + NAV 계산
├── equity-research.md      ← DCF/DDM 밸류에이션
├── technical-strategist.md ← 차트/추세 분석
├── macro-economist.md      ← Regime Detection, 금리/환율
├── portfolio-architect.md  ← MPT, Black-Litterman 배분
└── risk-controller.md      ← CVaR, VETO 권한 (최종 거부권)
```

### 에이전트 파일 구조

```markdown
---
name: trading-commander
description: >
  Paper Trading 오케스트레이터. 시그널 충돌 중재.
  트리거: 종합, 충돌, 전체 사이클, /run-cycle
tools: [Agent, Read, Write, Bash, Glob, Grep, WebSearch, WebFetch, TodoWrite]
model: claude-opus-4-6
permissionMode: acceptEdits
memory: project
---

# Trading Commander - Paper Trading Orchestrator

## When Invoked (즉시 실행 체크리스트)
1. state/portfolios.json 읽어 현재 전략별 NAV/포지션 파악
...
```

### 핵심 필드 설명

| 필드 | 설명 |
|------|------|
| `description` | Claude가 이 에이전트를 언제 호출할지 판단하는 기준 (트리거 키워드 포함) |
| `tools` | 이 에이전트가 사용할 수 있는 도구 목록 (권한 최소화 원칙) |
| `model` | 에이전트별 모델 선택 (orchestrator = opus, worker = sonnet) |
| `permissionMode` | `acceptEdits`: 편집 자동 승인 |
| `memory` | `project`: 프로젝트 레벨 메모리 공유 |

### 모델 선택 전략

```
Opus   ← 아키텍처 판단, 오케스트레이션, 복잡한 추론
Sonnet ← 코드 실행, 도메인 분석, 일반 작업 (기본값)
Haiku  ← 파일 조회, 단순 검색, 반복 작업
```

---

## Layer 5 — 비즈니스 로직 (Python)

에이전트와 완전히 분리된 결정론적 코드층.

```
strategies/
├── momentum.py         # MOM 전략: 12-1M 모멘텀 top 10
├── value_quality.py    # VAL 전략: P/E + ROE + FCF
├── quant_factor.py     # QNT 전략: Fama-French 5-Factor
└── leveraged_etf.py    # LEV 전략: SMA200 추세추종

execution/
├── alpaca_client.py    # Alpaca API 래퍼
├── order_manager.py    # 주문 사이징 + 실행
└── risk_validator.py   # 5가지 리스크 게이트 (Python 규칙)

run_cycle.py            # 전체 파이프라인 엔트리포인트
```

**에이전트는 Python을 실행하지, 대체하지 않습니다.** `Bash(python run_cycle.py ...)` 형태로 호출합니다.

---

## 오케스트레이션 패턴

### 전체 실행 흐름

```
User: "/run-cycle"
  │
  ▼
[Skill: run-cycle.md 로드]
  │
  ▼
[Trading Commander] ← Opus — 전체 조율
  ├── [Signal Engine] → strategies/*.py 실행 → Signal[]
  │
  ├── [Research Division 병렬 5명] ← Phase 2.5
  │   ├── Macro Economist → Regime Detection (선행)
  │   ├── Equity Research → 밸류에이션 검증
  │   ├── Technical Strategist → 차트 분석
  │   ├── Portfolio Architect → 배분 최적화
  │   └── Risk Controller → VETO 권한
  │
  ├── [Risk Guardian] → 5가지 게이트 통과 여부
  │   ├── PASS → Execution Broker
  │   └── FAIL → [Appeal: Research 재심]
  │
  ├── [Execution Broker] → Alpaca API 주문
  │
  └── [Performance Accountant] → P&L + 리포트
```

### Appeal(재심) 패턴

Risk Guardian이 FAIL을 낼 때 바로 거부하지 않고, Research Division에 재심을 요청합니다:

```
Risk FAIL
  │
  ▼
Research 5명 재심 요청
  │
  ├── 4/5 이상 STRONG_OVERRIDE → override (position_limit 제외)
  └── 과반 미달 → 최종 REJECT
```

단, `position_limit`(20%)와 `cash_buffer`(5%)는 재심 불가 — 하드 리밋.

---

## 플러그인 / 외부 연동

### Graphify (Knowledge Graph)

```bash
pip install graphifyy
```

코드베이스를 자동으로 지식 그래프로 변환합니다:
- `graphify-out/graph.json` — 768 nodes, 1673 edges, 41 communities
- 커밋 시 git hook으로 자동 업데이트
- Claude에서: `/graphify query "질문"` 또는 `/graphify path A B`

### Superpowers Skills (글로벌)

`~/.claude/skills/` 에 설치된 글로벌 스킬들:

| 스킬 | 역할 |
|------|------|
| `superpowers:brainstorming` | 구현 전 요구사항 탐색 |
| `superpowers:writing-plans` | 계획 작성 (코드 수정 전 승인 필수) |
| `superpowers:executing-plans` | 단계별 실행 + 체크포인트 |
| `superpowers:systematic-debugging` | 버그 원인 분석 (수정 전 필수) |
| `superpowers:verification-before-completion` | "완료" 선언 전 증거 수집 |

---

## 핵심 설계 원칙

### 1. Immutable Guard Rails
CLAUDE.md에 절대 위반 불가 원칙을 명시. 에이전트가 추론으로 우회할 수 없음.

### 2. Defense in Depth
```
hooks(파일 보호) → permissions(명령 제한) → agent 금지사항 → Python 리스크 검증
```
여러 레이어가 독립적으로 방어.

### 3. Separation of Concerns
- **비즈니스 로직**: Python (결정론적, 테스트 가능)
- **오케스트레이션**: 에이전트 (유연, 자연어 추론)
- 두 레이어를 섞지 않음

### 4. 증거 기반 완료
```
실행 → 결과 확인 → 증거 있으면 "완료"
```
훅/로그 없이 완료 선언 금지 패턴을 시스템 수준에서 강제.

---

## 디렉토리 구조 한눈에 보기

```
STOCK_WORK/
├── CLAUDE.md                     ← Layer 0: 프로젝트 지시
│
├── .claude/
│   ├── settings.json             ← Layer 1: 권한 + 훅 설정
│   ├── hooks/
│   │   ├── protect-api-keys.sh   ← Layer 2: 민감 파일 보호
│   │   └── log-execution.sh      ← Layer 2: 에이전트 실행 로깅
│   ├── skills/
│   │   ├── run-cycle.md          ← Layer 3: /run-cycle 커맨드
│   │   ├── rebalance.md          ← Layer 3: /rebalance 커맨드
│   │   ├── performance.md        ← Layer 3: /performance 커맨드
│   │   └── go-live.md            ← Layer 3: /go-live 커맨드
│   ├── agents/
│   │   ├── trading-commander.md  ← Layer 4: 오케스트레이터 (Opus)
│   │   ├── signal-engine.md      ← Layer 4: 시그널 생성
│   │   ├── risk-guardian.md      ← Layer 4: 리스크 게이트
│   │   ├── execution-broker.md   ← Layer 4: 주문 실행
│   │   ├── performance-accountant.md
│   │   ├── equity-research.md
│   │   ├── technical-strategist.md
│   │   ├── macro-economist.md
│   │   ├── portfolio-architect.md
│   │   └── risk-controller.md
│   └── logs/
│       └── agent-usage.log       ← 에이전트 실행 감사 로그
│
├── strategies/                   ← Layer 5: Python 비즈니스 로직
│   ├── momentum.py
│   ├── value_quality.py
│   ├── quant_factor.py
│   └── leveraged_etf.py
│
├── execution/
│   ├── alpaca_client.py
│   ├── order_manager.py
│   └── risk_validator.py
│
├── run_cycle.py                  ← 전체 파이프라인 엔트리포인트
│
└── graphify-out/
    └── graph.json                ← 코드베이스 지식 그래프
```

---

## 참고 링크

- [Claude Code Docs](https://docs.anthropic.com/claude-code)
- [Alpaca Paper Trading API](https://alpaca.markets/docs/api-references/trading-api/)
- [Graphify](https://pypi.org/project/graphifyy/)

---

*작성: 2026-04-16*
