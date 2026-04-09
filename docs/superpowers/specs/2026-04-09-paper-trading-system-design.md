# Paper Trading System — Design Specification
> Date: 2026-04-09
> Status: Approved (brainstorming complete)
> Approach: A — Lean Command Center

---

## 1. Context

### Why
STOCK_WORK 프로젝트는 분석/리포팅 전용 시스템(7 에이전트, 12 스크립트, GitHub Actions)으로 운영 중이나, 실제 거래 실행 능력이 없음. Alpaca Paper Trading API를 통해 시뮬레이션 → 검증 → 실전 투입 파이프라인을 구축하려 함.

### What Changes
- **기존 Stock Reports + Paperclip 관제탑**: 운영 중단 → STOCK_WORK 레포 아카이브
- **신규 paper-trading/ 레포**: 완전 자동 다중 전략 Paper Trading 시스템
- **전략 = Python 모듈** (결정론적, 백테스트 가능), **에이전트 = 오케스트레이션** (충돌 해소, 리스크 판단)

### Decisions Made
| 항목 | 결정 | 근거 |
|------|------|------|
| 자동화 수준 | 완전 자동 | Paper Trading이므로 리스크 없음 |
| 기존 코드 | 완전 새로 시작 | 분석 중심→거래 중심 전환, 레거시 부담 제거 |
| 전략 방식 | 다중 전략 병렬 테스트 | 어떤 전략이 유효한지 검증이 핵심 목표 |
| Agent SDK | 불채택 | 개인 트레이딩에 과잉, Claude Code 하네스 충분 |
| Paperclip | 운영 중단 | Performance Accountant + 리포트로 대체 |

---

## 2. Architecture

### 2.1 Repository Structure

```
paper-trading/
+-- CLAUDE.md                           # 프로젝트 정체성 + 라우팅 규칙
+-- .env                                # API 키 (git 제외)
+-- .gitignore
+-- .claude/
|   +-- agents/
|   |   +-- trading-commander.md        # (opus) 오케스트레이터
|   |   +-- signal-engine.md            # (sonnet) 전략 실행 + 시그널 종합
|   |   +-- risk-guardian.md            # (sonnet) 사전 거래 리스크 검증
|   |   +-- execution-broker.md         # (sonnet) Alpaca 주문 관리
|   |   +-- performance-accountant.md   # (sonnet) 전략별 P&L 귀속
|   +-- hooks/
|   |   +-- protect-api-keys.sh         # .env 커밋 차단
|   |   +-- pre-trade-gate.sh           # Risk Guardian FAIL 시 하드 블록
|   |   +-- log-execution.sh            # 주문 trade_log.jsonl 기록
|   +-- skills/
|   |   +-- run-cycle.md                # /run-cycle
|   |   +-- performance.md              # /performance
|   |   +-- rebalance.md                # /rebalance {strategy}
|   |   +-- go-live.md                  # /go-live
|   +-- settings.json
+-- strategies/
|   +-- base_strategy.py                # BaseStrategy 추상 클래스 + Signal
|   +-- momentum.py                     # MOM: 12-1 모멘텀
|   +-- value_quality.py                # VAL: P/E + ROE + FCF
|   +-- quant_factor.py                 # QNT: Fama-French 5-factor
|   +-- leveraged_etf.py               # LEV: 추세추종
+-- execution/
|   +-- alpaca_client.py                # paper/live 토글 (ENV 기반)
|   +-- order_manager.py                # 주문 제출/취소/추적
|   +-- position_manager.py             # 현재 포지션, 체결, 현금
|   +-- risk_validator.py               # 5가지 리스크 체크
+-- run_cycle.py                        # 메인 엔트리포인트
+-- state/
|   +-- portfolios.json                 # 전략별 서브포트폴리오
|   +-- trade_log.jsonl                 # append-only 주문 저널
|   +-- performance.json                # 일별 NAV 스냅샷
+-- reports/
|   +-- daily/                          # YYYY-MM-DD-daily.md
|   +-- strategy/                       # 전략별 월간 요약
+-- .github/workflows/
|   +-- trading-cycle.yml               # 평일 22:30 KST
|   +-- performance-report.yml          # 주말 성과 리포트
+-- requirements.txt
```

### 2.2 Agent Team

| Agent | Model | Role | Invocation |
|-------|-------|------|------------|
| Trading Commander | claude-opus-4-6 | 오케스트레이션, 시그널 충돌 중재 | 사용자 대화 / /run-cycle |
| Signal Engine | claude-sonnet-4-6 | 4 전략 모듈 실행 + 통합 | Commander 위임 |
| Risk Guardian | claude-sonnet-4-6 | 포지션/섹터/VaR/상관관계 검증 | 매 시그널 |
| Execution Broker | claude-sonnet-4-6 | Alpaca API 주문, 체결 추적 | Risk 통과 후 |
| Performance Accountant | claude-sonnet-4-6 | client_order_id 기반 P&L 귀속 | 사이클 종료 시 |

Agent interaction flow:
```
Trading Commander (opus)
├── Signal Engine → strategies/*.py → Signal[]
├── Risk Guardian → risk_validator.py → approved Signal[]
├── Execution Broker → alpaca_client.py → fills
└── Performance Accountant → performance.json update
```

---

## 3. Strategy Framework

### 3.1 BaseStrategy Interface

```python
class BaseStrategy:
    name: str              # "MOM", "VAL", "QNT", "LEV"
    capital_pct: float     # 전체 계좌 대비 배분 비율
    universe: list[str]    # 종목 유니버스 (또는 스크리닝 함수)
    max_positions: int     # 최대 동시 보유 종목수
    rebalance_freq: str    # "daily" | "weekly" | "monthly"
    stop_loss_pct: float   # 종목별 손절 비율
    take_profit_pct: float # 종목별 익절 비율

    def generate_signals(self, market_data: dict) -> list[Signal]:
        """결정론적 시그널 생성"""
        raise NotImplementedError
```

### 3.2 Strategy Configurations

| Strategy | Code | Capital | Universe | Rebalance | Logic |
|----------|------|---------|----------|-----------|-------|
| Momentum | MOM | 25% ($25K) | NASDAQ 100 | Monthly | 12-1M return top 10, above SMA200 |
| Value Quality | VAL | 25% ($25K) | S&P 500 | Quarterly | P/E<15 + ROE>15% + FCF Yield>5% |
| Quant Factor | QNT | 30% ($30K) | Russell 1000 | Monthly | Fama-French 5-factor composite score |
| Leveraged ETF | LEV | 20% ($20K) | TQQQ/UPRO/SQQQ | Daily | SMA50>SMA200 → long, else cash |

### 3.3 Capital Isolation

Alpaca 계좌 1개, 전략별 가상 서브포트폴리오로 격리:
- `client_order_id` 접두사: `{STRATEGY}-{DATE}-{SYMBOL}-{SEQ}`
  - 예: `MOM-20260409-NVDA-001`
- `state/portfolios.json`에 전략별 positions, cash, NAV 독립 추적
- 전략 간 자본 이동 없음 (배분 고정, 리밸런싱은 전략 내부에서만)
- 전략 현금 소진 시: 신규 매수 시그널 자동 스킵, 기존 포지션은 유지
- 전략별 NAV가 배분 자본의 50% 이하로 하락 시: Trading Commander에 에스컬레이션

---

## 4. Execution Flow

### 4.1 Automated Cycle (GitHub Actions)

```
trading-cycle.yml — 평일 22:30 KST (US 장 개장)

Phase 1: DATA
  python run_cycle.py --phase data
  └─ yfinance + Alpaca positions → data/snapshot.json

Phase 2: SIGNALS
  python run_cycle.py --phase signals
  └─ 4 strategy modules → signals[]

Phase 3: RISK
  python run_cycle.py --phase risk
  └─ risk_validator.py validates each signal
  └─ FAIL → dropped with reason logged

Phase 4: RESOLVE
  충돌 없으면 -> 자동 통과
  충돌 시:
    [GitHub Actions 자동 모드] Python 규칙 기반 해소:
      1. confidence 높은 쪽 우선
      2. 동점 -> 전략 자본 잔여 큰 쪽
      3. 그래도 동점 -> HOLD (보수적)
    [Claude Code 대화형 모드] Signal Engine 에이전트가 판단:
      - 시장 맥락 고려한 자연어 추론
      - 사용자에게 근거 설명 후 실행

Phase 5: EXECUTE
  python run_cycle.py --phase execute
  └─ order_manager.py → Alpaca Paper API
  └─ 체결 → trade_log.jsonl append

Phase 6: REPORT
  python run_cycle.py --phase report
  └─ performance.json 업데이트 + daily report 생성

Phase 7: COMMIT
  git add state/ reports/ && git commit && git push
```

### 4.2 Interactive (Claude Code)

사용자가 Claude Code로 레포 열면:
- `/run-cycle` — 수동으로 전체 사이클 실행
- `/performance` — 전략별 성과 대시보드 조회
- `/rebalance MOM` — 특정 전략 강제 리밸런싱
- `/go-live` — paper→live 전환 10항목 체크리스트

### 4.3 Paper → Live Migration

```python
# execution/alpaca_client.py
def get_client():
    mode = os.environ.get("ALPACA_MODE", "paper")
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=(mode == "paper")
    )
```

전환: GitHub Actions secret `ALPACA_MODE`를 `paper` → `live`로 변경. 코드 변경 0.

---

## 5. Risk Management

### 5.1 Pre-Trade Risk Gates

| Check | Threshold | Action on Fail |
|-------|-----------|---------------|
| Position limit | weight ≤ 20% of strategy capital | REJECT signal |
| Sector concentration | sector_weight ≤ 40% | REJECT signal |
| Portfolio VaR | 95% 1-day VaR ≤ 3% | REJECT signal |
| Correlation | \|corr(new, existing)\| ≤ 0.85 | REJECT signal |
| Cash buffer | strategy cash ≥ 5% | REJECT signal |
| Leverage filter | LEV only: underlying SMA50 > SMA200 | REJECT + cash |

### 5.2 Post-Trade Monitoring

- 종목별 -10% → 다음 사이클에 자동 SELL 시그널 생성
- 전략별 MDD -20% → Trading Commander에 에스컬레이션
- 전체 포트폴리오 MDD -15% → 모든 전략 현금화 경고

---

## 6. State Management

### 6.1 portfolios.json Schema

```json
{
  "account_total": 100000,
  "last_updated": "2026-04-09T22:30:00Z",
  "strategies": {
    "MOM": {
      "allocated": 25000,
      "cash": 5000,
      "positions": {
        "NVDA": {"qty": 10, "avg_price": 850.0, "current": 870.0, "entry_date": "2026-04-03"}
      },
      "nav_history": [{"date": "2026-04-09", "nav": 25200}]
    }
  }
}
```

### 6.2 trade_log.jsonl (Append-Only)

```json
{"ts": "2026-04-09T22:31:00Z", "strategy": "MOM", "symbol": "NVDA", "side": "buy", "qty": 10, "price": 850.0, "order_id": "MOM-20260409-NVDA-001", "alpaca_id": "abc123", "status": "filled", "risk_check": "ALL_PASS"}
```

---

## 7. Monitoring & Reporting (Paperclip Replacement)

| 기능 | 구현 방식 |
|------|---------|
| 일일 모니터링 | `reports/daily/YYYY-MM-DD-daily.md` (자동 생성) |
| 전략 성과 비교 | Performance Accountant가 performance.json 기반 렌더링 |
| 리스크 경보 | Risk Guardian의 FAIL 로그 + MDD 경보 |
| 관제탑 기능 | Trading Commander가 에스컬레이션 판단 |
| 이메일 알림 | GitHub Actions에서 Gmail SMTP (STOCK_WORK 패턴 재사용) |

---

## 8. Technology Stack

| Layer | Tool | Notes |
|-------|------|-------|
| Broker API | alpaca-py >= 0.21.0 | Paper/Live 동일 SDK |
| Market Data | yfinance + Alpaca Data API | 무료 |
| Technical Indicators | pandas-ta or ta-lib | RSI, MACD, SMA |
| Data Processing | pandas >= 2.2.0 | |
| Templating | jinja2 >= 3.1.0 | 리포트 렌더링 |
| CI/CD | GitHub Actions | 평일 cron |
| Agent Harness | Claude Code .claude/agents/ | 5 에이전트 |
| State Persistence | JSON files (git tracked) | portfolios.json, trade_log.jsonl |

---

## 9. Implementation Phases

### Phase 0 — Foundation (Week 1)
- [ ] 신규 `paper-trading/` 레포 생성
- [ ] `execution/alpaca_client.py` (paper/live 토글)
- [ ] `execution/risk_validator.py` (5가지 리스크 체크)
- [ ] `strategies/base_strategy.py` (추상 클래스 + Signal)
- [ ] `state/portfolios.json` 초기 스키마
- [ ] CLAUDE.md + .claude/settings.json
- [ ] Alpaca Paper 계좌 생성 + .env 세팅

### Phase 1 — First Strategy (Week 2)
- [ ] `strategies/momentum.py` (12-1 모멘텀)
- [ ] `execution/order_manager.py` (Alpaca submit_order)
- [ ] `run_cycle.py` (data → signals → risk → execute → report)
- [ ] CLI 수동 테스트: 전체 사이클 1회 실행

### Phase 2 — Agents + Hooks (Week 3)
- [ ] 5개 에이전트 .md 파일 작성
- [ ] 4개 스킬 .md 파일 작성
- [ ] hooks: protect-api-keys.sh, pre-trade-gate.sh, log-execution.sh
- [ ] /run-cycle 스킬로 대화형 실행 테스트

### Phase 3 — GitHub Actions (Week 4)
- [ ] `trading-cycle.yml` (평일 22:30 KST cron)
- [ ] `performance-report.yml` (주말 성과)
- [ ] Secrets 세팅 (ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_MODE=paper)
- [ ] End-to-end 자동 실행 테스트

### Phase 4 — Multi-Strategy (Week 5-6)
- [ ] `strategies/value_quality.py`
- [ ] `strategies/quant_factor.py`
- [ ] `strategies/leveraged_etf.py`
- [ ] `execution/performance_manager.py` (전략별 NAV 계산)
- [ ] 전략 성과 비교 대시보드

### Phase 5 — Live Migration (When Ready)
- [ ] `/go-live` 스킬: 10항목 사전 감사
- [ ] Paper 성과 1~3개월 검증
- [ ] GitHub secret ALPACA_MODE → live 전환
- [ ] 코드 변경 없음

---

## 10. Verification Plan

1. **Phase 0 검증**: `python -c "from execution.alpaca_client import get_client; c=get_client(); print(c.get_account())"` — Alpaca Paper 계좌 연결 확인
2. **Phase 1 검증**: `python run_cycle.py --phase all --dry-run` -- 시그널 생성 + 리스크 검증 (주문 미실행)
3. **Phase 2 검증**: `/run-cycle` 스킬 실행 → 에이전트 오케스트레이션 확인
4. **Phase 3 검증**: GitHub Actions 수동 트리거 → trade_log.jsonl에 체결 기록 확인
5. **Phase 4 검증**: 4개 전략 동시 실행 → portfolios.json에 전략별 포지션 분리 확인
6. **Phase 5 검증**: /go-live 체크리스트 10항목 전부 PASS 확인
