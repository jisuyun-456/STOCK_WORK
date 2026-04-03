# Trading Dashboard + $20,000 Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** $20,000 시뮬레이션 포트폴리오 재설정 + Goldman/JPM 스타일 HTML 트레이딩 대시보드 구현 + daily_report.py 파이프라인 연결

**Architecture:**
- `simulation_tracker.py`: TOTAL_CAPITAL $1,000→$20,000, 비중 유지 조정
- `templates/trading_dashboard.html`: Jinja2 템플릿 (세션 탭 + 티커바 + 5종목 패널 + 사이드바)
- `scripts/dashboard_generator.py`: context dict → HTML 생성기
- `daily_report.py`: 파이프라인 마지막에 dashboard 생성 단계 추가

**Tech Stack:** Python, Jinja2, yfinance, HTML/CSS/JS (vanilla), WeasyPrint(PDF 별도)

---

## Task 1: 시뮬레이션 $20,000 재설정

**Files:**
- Modify: `scripts/simulation_tracker.py`
- Delete/Reset: `docs/simulation/portfolio_state.json` (init으로 재생성)

**Allocation ($20,000):**
| 종목 | 비중 | 금액 |
|------|------|------|
| PLTR | 35% | $7,000 |
| RKLB | 25% | $5,000 |
| HIMS | 20% | $4,000 |
| APLD | 15% | $3,000 |
| IONQ | 5%  | $1,000 |

- [ ] `simulation_tracker.py`에서 `TOTAL_CAPITAL = 1000` → `20000`
- [ ] PORTFOLIO_DEFINITION 각 allocation 업데이트 (350→7000, 250→5000, 200→4000, 150→3000, 50→1000)
- [ ] `status` CLI 출력의 "초기 $1,000" 하드코딩 제거 → `TOTAL_CAPITAL` 변수 참조
- [ ] `python scripts/simulation_tracker.py init` 실행 → 4/2 종가로 진입가 설정
- [ ] `python scripts/simulation_tracker.py status` 확인

---

## Task 2: 대시보드 Jinja2 템플릿 생성

**Files:**
- Create: `templates/trading_dashboard.html`

**섹션 구조:**
```
[Header] Trading Desk | PRE / OPEN / INTRADAY / CLOSE 탭 | 시계
[Ticker Bar] NQ Fut | S&P Fut | VIX | 10Y | DXY | Gold | WTI
[Main 2-col]
  [Left]
    포트폴리오 P&L 헤더 (총평가액 / 일간 / 누적)
    Market Overview 4-card (NASDAQ / NASDAQ100 / VIX / 섹터리더)
    종목 패널 × 5 (PLTR/RKLB/HIMS/APLD/IONQ)
      → 기술 지표 4박스 + Bull/Base/Bear + 리스크바 + 일일 인사이트
  [Right Sidebar]
    포트폴리오 배분 바
    리스크 요약 (Beta / MDD한도 / 섹터집중 / 현금)
    Trade Ideas (DCF-based BUY/HOLD/REDUCE)
    Macro Events (경기사이클 + 주요 지표)
```

- [ ] HTML/CSS/JS 전체 템플릿 작성 (기존 daily-trading-report.html 디자인 기준)
- [ ] Jinja2 변수 바인딩:
  - `{{ sim_summary.total_value }}`, `{{ sim_summary.daily_return_pct }}`
  - `{{ sim_stocks }}` 배열 루프
  - `{{ us_indices }}`, `{{ commodities }}`
  - `{{ cycle_info }}`, `{{ sectors_daily }}`
- [ ] 세션 탭 JS (PRE/OPEN/INTRADAY/CLOSE → 배지 색상 변경)
- [ ] 실시간 시계 JS (30초마다 ET 시간 업데이트)

---

## Task 3: 대시보드 생성기 스크립트

**Files:**
- Create: `scripts/dashboard_generator.py`

**인터페이스:**
```python
def generate_dashboard(context: dict, output_path: str) -> bool:
    """daily_report.py context → trading_dashboard.html 생성"""
```

- [ ] Jinja2 Environment 설정 (templates/ 디렉토리)
- [ ] custom filter: `format`, `abs`, `max` 등
- [ ] context에서 대시보드 전용 계산 추가:
  - 각 종목 weight_pct = current_value / total_value * 100
  - 각 종목 signal_pill = daily_view.view_rating
  - Bull/Base/Bear 목표가 계산 (기술적 지표 기반)
- [ ] `docs/` 디렉토리에 `dashboard.html` 저장
- [ ] 에러 시 False 반환 + stderr 로그

---

## Task 4: daily_report.py 파이프라인 연결

**Files:**
- Modify: `scripts/daily_report.py`

- [ ] `from dashboard_generator import generate_dashboard` import 추가
- [ ] `main()` 함수에 dashboard 생성 단계 추가:
  ```python
  # 대시보드 HTML 생성
  dashboard_path = Path(__file__).parent.parent / "docs" / "dashboard.html"
  result = generate_dashboard(context, str(dashboard_path))
  if result:
      print(f"  [dashboard] 생성 완료: {dashboard_path}", file=sys.stderr)
  ```
- [ ] `generate_report()` 함수는 변경 없음 (context 재사용)
- [ ] `python scripts/daily_report.py --format md` 실행 → dashboard.html 생성 확인

---

## Task 5: 최종 검증

- [ ] `python scripts/simulation_tracker.py status` → $20,000 기준 포지션 확인
- [ ] `python scripts/daily_report.py --format md` → dashboard.html 생성 확인
- [ ] 브라우저에서 `docs/dashboard.html` 열어 시각적 확인:
  - 포트폴리오 P&L 헤더 표시 ✓
  - 5종목 패널 (PLTR/RKLB/HIMS/APLD/IONQ) ✓
  - 티커바 데이터 표시 ✓
  - 사이드바 배분 바 ✓
- [ ] git commit

---

## 참고: 데이터 매핑

| 대시보드 영역 | context 키 | 필드 |
|-------------|-----------|------|
| 포트폴리오 P&L | `sim_summary` | total_value, daily_return_pct, cumulative_return_pct |
| 종목 패널 가격 | `sim_stocks[i].technical` | current_price, change_pct |
| 종목 Bull/Base/Bear | `sim_stocks[i].thesis` | bull, bear + technical targets |
| 종목 시그널 | `sim_stocks[i].daily_view` | view_rating, view_reason, today |
| 티커바 | `us_indices`, `commodities` | close, change_pct |
| 섹터 리더 | `sectors_daily` | 최고/최저 섹터 |
| 경기사이클 | `cycle_info` | cycle, sectors |
