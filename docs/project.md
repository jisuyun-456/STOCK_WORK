# STOCK_WORK — Project Master

> 최종 업데이트: 2026-04-15
> 상태: 🟢 Live Paper Trading 운영 중
> 브로커: Alpaca Paper ($100,000 가상자본)
> 레포: `jisuyun-456/STOCK_WORK`

---

## 1. 시스템 현황 스냅샷

### Phase 완료 현황

| Phase | 내용 | 상태 |
|-------|------|------|
| 0~6.5 | Foundation, 4전략, Regime Gateway, Intraday Monitor, Daily Report | ✅ |
| 7 | 뉴스 크롤링 강화 (6개 RSS) | ✅ |
| 8 | 기술적 분석 (RSI/MACD/Bollinger) | ✅ |
| 9 | Polymarket 예측시장 → Regime Detection 연동 | ✅ |
| 10 | Research Overlay 하이브리드 (rules/Gemini/Claude) | ✅ |

### Iteration 파라미터 최적화 완료

| Iter | 핵심 내용 | 결과 |
|------|---------|------|
| 1 | CRITICAL/HIGH/MEDIUM 버그 수정, LEV 재설계 | 기반 안정화 |
| 2 | strategy_params.json 연결, Variant A/B/C 비교 | NEUTRAL 65.2% gate |
| 3 | Variant D 확정, RESEARCH_AGENTS Secret 설정 | BULL 100% gate |
| 4 | --force-regime CLI, dead config 제거, 4-레짐 시뮬 | BEAR 100%, CRISIS 85.7% |
| 5 | --force-regime allocator 완전 연동, CRISIS 종목 분석 | 완전 연동 완료 |

### 현재 운영 파라미터 (Variant D)

| 전략 | 핵심 파라미터 |
|------|-------------|
| MOM | lookback=252일, max_positions=10, position_pct=10%, stop_loss=10% |
| VAL | max_positions=5, REGIME_FILTERS(BULL: P/E<25, ROE>10%, FCF>3%) |
| QNT | min_composite_score=0.20, max_positions=20, ols_window=60 |
| LEV | SMA50/SMA200 골든크로스, stop_loss=8%, position_pct=100% |

### 실시간 상태 (2026-04-15)

| 항목 | 값 |
|------|-----|
| Alpaca Equity | $99,950 |
| 보유 포지션 | 19개 (LRCX, APLD, RKLB, WBD, MU 등) |
| 현재 레짐 | BULL (VIX=18.4, SPY/SMA200=1.05) |
| 배분 | MOM 20% / VAL 13% / QNT 17% / LEV 50% |
| 운영 시작 | 2026-04-09 (7일차) |
| GitHub Actions cron | 평일 22:30 KST 자동 실행 |
| RESEARCH_AGENTS | rules ($0 비용) |

> **주의:** `performance.json` 상의 수익률(-19%)은 MDD 트리거 후 initial_nav 재산정 아티팩트. 실제 Alpaca 계좌 기준으로 평가할 것.

---

## 2. KPI 목표치

### 수익률 목표 (연간 기준, Alpaca Paper 계좌 기준)

| 지표 | 1차 목표 (6개월) | 2차 목표 (12개월) |
|------|---------------|----------------|
| Alpha vs SPY | **+5%** | **+10%** |
| Sharpe Ratio | ≥ 0.7 | **≥ 1.0** |
| MDD 한도 | -20% 이내 | -20% 이내 |
| Risk gate 통과율 | ≥ 70% (NEUTRAL 기준) | ≥ 75% |
| BULL 레짐 수익률 | SPY 대비 +10% | SPY 대비 +15% |

### 전략별 기여 목표

| 전략 | 목표 역할 | 수익률 기여 |
|------|---------|-----------|
| **LEV** | 핵심 수익 엔진 (BULL 집중) | 전체의 40~50% |
| **MOM** | 모멘텀 팩터 알파 | 월 +1~2% |
| **VAL** | BEAR/CRISIS 손실 완충 | 방어적 역할 |
| **QNT** | FF5 팩터 알파 | 시장 중립적 +1~2% |

### AutoResearch 개선 루프 목표

매 Iteration당 목표:
- Risk gate 통과율 +5%p 이상 개선 (또는 현행 유지 근거 확인)
- Sharpe Ratio 월간 추적 (2주 간격 체크)
- 레짐별 VAL 필터 통과 수 ≥ max_positions 유지

---

## 3. AutoResearch 설정

### 현재 설정

```
RESEARCH_AGENTS=rules          # GitHub Secret ✅ (2026-04-15)
research_mode=selective         # dry-run/cron 기본값
ALPACA_MODE=paper              # GitHub Secret ✅
```

### Paperclip 6에이전트 (Claude 구독 토큰, $0)

| 에이전트 | 역할 | 상태 |
|---------|------|------|
| 01-Chief-Trader | 오케스트레이터, research_results.json 생성 | Instructions 작성 완료 |
| 02-Fundamental-Analyst | PE/ROE/FCF + 뉴스 감성 | Instructions 작성 완료 |
| 03-Market-Scanner | 매크로 뉴스 + 레짐 판단 | Instructions 작성 완료 |
| 04-Portfolio-Monitor | P&L + 리밸런싱 추천 | Instructions 작성 완료 |
| 05-Quant-Strategist | FF5 팩터 해석 | Instructions 작성 완료 |
| 06-Risk-Sentinel | 5-Gate 리스크 + VETO | Instructions 작성 완료 |

**Paperclip 활성화 체크리스트:**
- [x] 6에이전트 Instructions Obsidian 작성 완료
- [ ] Paperclip 대시보드에 Instructions 수동 복사
- [ ] 테스트 Routine 실행 → `state/research_results.json` 생성 확인
- [ ] GitHub Actions dry-run E2E 검증 (`research_mode=rules` → `paperclip` 전환)

### AutoResearch 아키텍처

```
[21:00 KST] Paperclip Routine (수동 or 자동)
  02/03/04/05 (병렬) → 06-Risk → 01-Chief
  → state/research_results.json 생성 → git push

[22:30 KST] GitHub Actions cron
  → research_results.json 존재 + 24h 이내 → Paperclip 결과 사용
  → 없으면 rules fallback
  → 시그널 생성 → Risk gate → 체결
```

---

## 4. 운영 로드맵

### 단기 (2~4주, 2026-04-15 ~ 2026-05-09)

| 우선순위 | 태스크 | 목적 |
|---------|--------|------|
| 🔴 P1 | Alpaca 수익률 데이터 2주 축적 | KPI 측정 기반 확보 |
| 🔴 P1 | Paperclip 대시보드 Instructions 적용 | AutoResearch 활성화 |
| 🟡 P2 | performance.json initial_nav 버그 수정 | 정확한 수익률 추적 |
| 🟡 P2 | Iteration 6 — CRISIS allocator 조정 | CRISIS 85.7% → 95%+ |
| 🟢 P3 | FF5 데이터 지연 모니터링 (90일 임계 전 대응) | QNT 품질 유지 |

### 중기 (1~3개월, 2026-05 ~ 2026-07)

- Sharpe Ratio 실측 후 전략별 position_pct 조정
- BULL 레짐에서 LEV 수익률 50% 기여 달성 확인
- VAL 유니버스 확장 검토 (Russell 1000 → S&P 500)
- Paperclip → AutoResearch 루프 월간 Iteration 정례화

### 장기 (3개월+, 2026-08~)

- Alpha vs SPY +5% 1차 목표 달성 검증
- Real Money 전환 검토 (Alpaca Paper → Live)
- 전략 파라미터 강화학습 자동화 (AutoResearch 고도화)

---

## 5. 빠른 참조

### 핵심 파일 경로

| 파일 | 용도 |
|------|------|
| `run_cycle.py` | 메인 사이클 (`--phase all --dry-run --force-regime CRISIS`) |
| `config/strategy_params.json` | Variant D 파라미터 |
| `state/portfolios.json` | 현재 포지션/할당 |
| `state/performance.json` | NAV/수익률 추적 |
| `docs/iteration-log.md` | Iteration 1~5 기록 |
| `state/research_results.json` | Paperclip 분석 결과 (생성 예정) |

### 자주 쓰는 커맨드

```bash
# 전체 사이클 dry-run
python run_cycle.py --phase all --dry-run --research-mode selective

# 레짐 시뮬레이션
python run_cycle.py --phase all --dry-run --force-regime CRISIS

# 테스트
python -m pytest tests/ -q

# 수동 트리거 (GitHub Actions)
gh workflow run trading-cycle.yml -f dry_run=false -f research_mode=selective
```

### 관련 문서 (Obsidian)

- [[Paper-Trading-System]] — Phase 0~10 시스템 아키텍처
- [[Trading-Process-Flow]] — 8단계 사이클 흐름도
- `STOCK/Agents/` — Paperclip 6에이전트 Instructions
- `STOCK/DailyReport/` — 일일 리포트 자동 저장
