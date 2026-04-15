# STOCK_WORK 6전략 자동매매 시스템 — 워크플로우 전체 정리

> 기준일: 2026-04-15 | 자본: $100,000 (Alpaca Paper Trading)

---

## 1. 전체 사이클 개요

```
[22:30 KST — GitHub Actions Cron]
        │
        ▼
  python run_cycle.py --phase all
        │
        ├─ Phase 1  : DATA      ← 시장 데이터 fetch
        ├─ Phase 1.5: REGIME    ← 시장 레짐 감지
        ├─ Phase 1.8: STOP-LOSS ← 손절 체크
        ├─ Phase 2  : SIGNALS   ← 6전략 시그널 생성
        ├─ Phase 3  : EXECUTE   ← Alpaca 주문 전송
        ├─ Phase 4  : REBALANCE ← 포지션 리밸런싱
        └─ Phase 5  : REPORT    ← 성과 리포트 저장
```

---

## 2. Phase 1 — DATA (시장 데이터 fetch)

| 데이터 | 대상 | 사용 전략 |
|--------|------|-----------|
| 나스닥100 / S&P500 / Russell 1000 가격 | 130~400일 종가 | MOM · VAL · QNT |
| Russell 2000 소형주 90종목 가격 | 150일 종가 (배치 1회) | GRW |
| GRW 펀더멘탈 (시총·매출성장률·ROE·FCF) | 모멘텀 상위 30종목만 | GRW |
| VIX · SPY 가격 | 5~20일 | LEV · LEV_ST |
| Fama-French 5팩터 | Ken French 사이트 (월 단위, 47일 래그) | QNT |
| 뉴스 (FOMC·실적발표·8-K) | 트리거 조건 충족 시만 | Research Overlay |

---

## 3. Phase 1.5 — REGIME (레짐 감지)

**5가지 레짐** → 전략 배분 비율 자동 조정

| 레짐 | 감지 조건 |
|------|-----------|
| **BULL** | SPY > SMA50 > SMA200, VIX < 20, RSI 45~74 |
| **NEUTRAL** | 중간 상태 (BULL/BEAR 기준 미달) |
| **BEAR** | SPY < SMA50 또는 SMA50 < SMA200, VIX > 25 |
| **CRISIS** | VIX > 35 또는 SPY 급락 (-10%/20일) |
| **EUPHORIA** | RSI ≥ 75, VIX < 15, SPY > SMA50 > SMA200 |

**레짐 안정화:** 3-bar 히스테리시스 (같은 신호 3회 연속 → 전환)

---

## 4. Phase 2 — SIGNALS (6전략 시그널 생성)

### 전략별 투자 유니버스 & 로직

#### MOM — 모멘텀 전략
- **유니버스:** 나스닥100 서브셋 (~80종목)
- **로직:** 12개월 모멘텀 기준 상위 10종목 BUY
- **레짐 제한:** BEAR·CRISIS에서 50~100% 청산

#### VAL — 가치+퀄리티 전략
- **유니버스:** S&P500 Top 100
- **로직:** PER · PBR · ROE · FCF 복합 점수 상위 5종목
- **레짐 제한:** CRISIS에서 50% 청산

#### QNT — 퀀트 팩터 전략
- **유니버스:** Russell 1000 서브셋 (~80종목)
- **로직:** Fama-French 5팩터(시장·규모·가치·수익성·투자성향) 복합 스코어
- **최대 포지션:** 20종목 (각 5%)
- **레짐 제한:** CRISIS에서 50% 청산

#### GRW — 소형 성장주 전략 ⭐ NEW
- **유니버스:** Russell 2000 서브셋 (90종목)
- **복합 스코어:**
  ```
  score = 0.5 × 모멘텀_순위
        + 0.3 × 매출성장률_순위
        + 0.2 × 퀄리티_순위 (ROE>0 or FCF>0)
  ```
- **필터:** 시총 $200M~$5B, 매출성장률 > 10%, 음수 모멘텀 제외
- **최대 포지션:** 8종목 (각 12.5%)
- **레짐 제한:** BEAR BUY 차단, CRISIS 전량 청산

#### LEV — 레버리지 ETF 바벨 전략
- **투자 대상:** SPY · TQQQ · SQQQ · BND · GLD
- **레짐별 포지션:**
  | 레짐 | 포지션 |
  |------|--------|
  | BULL | SPY 50% + TQQQ 50% |
  | NEUTRAL | SPY 50% + TQQQ 50% |
  | BEAR | SPY 50% + SQQQ 50% |
  | CRISIS | BND 60% + GLD 40% (방어) |
  | EUPHORIA | SPY 70% + TQQQ 30% |

#### LEV_ST — 단기 VIX/SPY 모멘텀 전략
- **투자 대상:** TQQQ · SQQQ · CASH
- **로직:** VIX 5일 변화율 + SPY 3일 변화율 조합
  - VIX↓ + SPY↑ → TQQQ
  - VIX↑ + SPY↓ → SQQQ
  - 중립 → CASH

---

## 5. 레짐별 자본 배분표

| 전략 | BULL | NEUTRAL | BEAR | CRISIS | EUPHORIA |
|------|------|---------|------|--------|----------|
| **MOM** | 15% | 12.5% | 5% | 5% | 10% |
| **VAL** | 10% | 12.5% | 15% | 10% | 10% |
| **QNT** | 12.5% | 15% | 10% | 7.5% | 10% |
| **LEV** | 25% | 25% | 25% | 25% | 25% |
| **LEV_ST** | 25% | 25% | 25% | 25% | 25% |
| **GRW** | **12.5%** | **10%** | **0%** | **0%** | **7.5%** |
| **CASH** | 0% | 0% | 20% | 27.5% | 12.5% |
| **합계** | 100% | 100% | 100% | 100% | 100% |

### NEUTRAL 레짐 기준 $100k 배분 (현재 상태)

| 전략 | 금액 | 투자 대상 |
|------|------|-----------|
| LEV | $25,105 | SPY + TQQQ |
| LEV_ST | $25,105 | TQQQ (VIX↓ SPY↑) |
| QNT | $15,063 | FF5 퀀트 top20 |
| MOM | $12,553 | 나스닥100 모멘텀 top10 |
| VAL | $12,553 | S&P500 가치주 top5 |
| GRW | $10,042 | Russell 2000 성장주 top8 |
| CASH | $0 | - |

---

## 6. Phase 3 — EXECUTE (주문 실행)

```
시그널 → Research Overlay 필터 (신뢰도 < 0.4 차단)
       → Risk Gates 체크
         ├─ 단일 포지션 최대 15%
         ├─ 포트폴리오 집중도 최대 25%
         └─ 상관관계 최대 0.85
       → Alpaca Paper Trading API 주문 전송
       → state/trade_log.jsonl 기록
```

**미국 장 시간 (KST 기준):**
- 정규장: 23:30 ~ 06:00 (다음날)
- 사전 시장: 18:00 ~ 23:30
- Cron 22:30 → 시그널 준비 → 23:30 개장과 동시에 체결

---

## 7. Phase 5 — REPORT (성과 추적)

### 주요 파일

| 파일 | 내용 |
|------|------|
| `state/portfolios.json` | 전략별 NAV · 포지션 · 배분금액 |
| `state/performance.json` | 수익률 · 샤프지수 · MDD |
| `state/trade_log.jsonl` | 전체 주문 이력 |
| `state/audit_log.jsonl` | 시스템 이벤트 이력 |
| `reports/daily/YYYY-MM-DD-daily.md` | 일간 리포트 |

### 성과 지표

- **TOTAL NAV:** Alpaca 실계좌 equity 기준 (`account_total_history` 추적)
- **전략별 return:** `(current_nav - inception_nav) / inception_nav`
- **Sharpe Ratio:** 일일 수익률 기준, 무위험 수익률 5% 적용
- **MDD:** 최고점 대비 최대 낙폭

---

## 8. AutoResearch 연계

매주 GitHub Actions가 자동으로 성과 분석 리포트 생성:

```
주간 AutoResearch (GitHub Actions)
  ├─ 전략별 수익률 분석
  ├─ 레짐 감지 정확도 평가
  ├─ 파라미터 최적화 제안 (모멘텀 기간, 포지션 수 등)
  └─ docs/ 폴더에 분석 리포트 저장
```

---

## 9. 주요 파일 구조

```
STOCK_WORK/
├─ run_cycle.py              # 메인 사이클 진입점
├─ strategies/
│   ├─ base_strategy.py      # BaseStrategy · Signal 공통 인터페이스
│   ├─ regime_allocator.py   # 레짐별 자본 배분
│   ├─ momentum.py           # MOM 전략
│   ├─ value_quality.py      # VAL 전략
│   ├─ quant_factor.py       # QNT 전략
│   ├─ leveraged_etf.py      # LEV 전략
│   ├─ lev_short_term.py     # LEV_ST 전략
│   └─ growth_smallcap.py    # GRW 전략 ⭐ NEW
├─ state/
│   ├─ universe.json         # 전략별 종목 유니버스
│   ├─ portfolios.json       # 실시간 포트폴리오 상태
│   └─ performance.json      # 성과 지표
└─ config/
    └─ strategy_params.json  # 전략별 파라미터
```
