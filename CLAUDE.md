# Paper Trading System

Alpaca Paper Trading API를 통한 완전 자동 다중 전략 시뮬레이션 시스템.
전략 = Python 모듈 (결정론적), 에이전트 = 오케스트레이션 (충돌 해소, 리스크 판단).

## 이 프로젝트 열면 자동 실행
1. `git log --oneline -10` → 최근 작업 확인
2. `python -c "from execution.alpaca_client import get_account_info; print(get_account_info())"` → 계좌 상태 확인 (실패 시 .env 미세팅 안내)
실행 후 "현재 상태 요약 + 다음 추천 태스크 1개" 말해줄 것.
세션 종료 시: git commit 필수.

## 투자 원칙 (Immutable)
- 분산투자: 단일 종목 20% 이하, 단일 섹터 40% 이하
- 손절 기준: 종목 -10% 리뷰, 포트폴리오 MDD -20% 필수 검토
- 데이터 기반: 뉴스/감 거래 금지, 정량 분석 우선
- 레버리지 경고: 인버스/레버리지 ETF는 추세 필터(SMA200) 통과 필수

## 기술 스택
| 레이어 | 도구 | 상태 |
|--------|------|------|
| 브로커 API | Alpaca (alpaca-py) | Paper Trading |
| 시장 데이터 | yfinance + Alpaca Data API | 무료 |
| 기술 지표 | pandas / numpy | |
| CI/CD | GitHub Actions | 평일 cron |
| 에이전트 하네스 | Claude Code .claude/agents/ | 5 에이전트 |
| 상태 저장 | JSON (git tracked) | portfolios.json |

## 환경변수 (.env)
```
ALPACA_API_KEY=xxx
ALPACA_SECRET_KEY=xxx
ALPACA_MODE=paper          # "paper" or "live" — 코드 변경 없이 전환
```

## 전략 (strategies/)
| 코드 | 전략 | 자본 | 리밸런싱 | 파일 |
|------|------|------|---------|------|
| MOM | Momentum (12-1M top 10) | 25% | 월간 | momentum.py |
| VAL | Value Quality (P/E+ROE+FCF) | 25% | 분기 | value_quality.py |
| QNT | Quant Factor (FF5) | 30% | 월간 | quant_factor.py |
| LEV | Leveraged ETF 추세추종 | 20% | 일간 | leveraged_etf.py |

## 에이전트 팀

| 에이전트 | 모델 | 역할 |
|---------|------|------|
| Trading Commander | opus | 오케스트레이션, 시그널 충돌 중재 |
| Signal Engine | sonnet | 전략 모듈 실행 + 시그널 종합 |
| Risk Guardian | sonnet | 5가지 사전 거래 리스크 검증 |
| Execution Broker | sonnet | Alpaca 주문 실행 + 체결 추적 |
| Performance Accountant | sonnet | 전략별 P&L 귀속 + 리포트 |

### 에이전트 라우팅

| 키워드 | 에이전트 |
|--------|---------|
| 시그널, 전략, 매수, 매도, 분석 | Signal Engine |
| 리스크, VaR, 한도, 집중도 | Risk Guardian |
| 주문, 체결, Alpaca, 포지션 | Execution Broker |
| 성과, P&L, NAV, 수익률, 대시보드 | Performance Accountant |
| 종합, 충돌, 전체 사이클 | Trading Commander |

## 실행 파이프라인 (run_cycle.py)

```
Phase 1: DATA      -> yfinance + Alpaca positions -> snapshot
Phase 2: SIGNALS   -> 4 strategy modules -> Signal[]
Phase 3: RISK      -> risk_validator.py -> approved Signal[]
Phase 4: RESOLVE   -> 충돌 해소 (Python 규칙 / 에이전트 판단)
Phase 5: EXECUTE   -> Alpaca Paper API -> fills
Phase 6: REPORT    -> performance.json + daily report
Phase 7: COMMIT    -> git add + commit + push
```

## 리스크 게이트 (execution/risk_validator.py)
| 체크 | 임계값 | 실패 시 |
|------|--------|--------|
| 포지션 한도 | <= 20% | REJECT |
| 섹터 집중 | <= 40% | REJECT |
| VaR (95%, 1d) | <= 3% | REJECT |
| 상관관계 | <= 0.85 | REJECT |
| 현금 버퍼 | >= 5% | REJECT |

## 태스크 관리
`.claude/feature_list.json` -- 전체 태스크 목록

## 검증 체크포인트 (코딩 완료 후 필수)
1. 훅 결과 확인
2. "typecheck: pass / test: pass N개 통과" 형식 보고
3. "다음 단계로 진행할까요?" 사용자에게 확인

### 금지 표현 (검증 없이 사용 불가)
- "완료됐습니다", "구현했습니다" -> 훅 결과 없이 사용 금지
- "잘 동작할 것입니다" -> 실행 증거 없이 사용 금지
