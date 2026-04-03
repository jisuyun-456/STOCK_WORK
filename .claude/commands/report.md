# /report — 일일 투자 리포트 생성 & Gmail 발송

일일 투자 리포트를 자동 생성하고 이메일로 발송합니다.

## 사용법

- `/report` — 일일 리포트 생성 + Gmail 발송
- `/report manual` — ST 에이전트 연동 심층 분석 (향후)
- `/report schedule` — CronCreate 주간 스케줄 등록

## 실행 절차

### 1. 리포트 생성

```bash
cd /c/Users/yjisu/Desktop/STOCK_WORK/scripts
python3 daily_report.py --format all
```

- `--format all`: Markdown(상세본) + HTML(이메일용) 동시 생성
- `--format md`: Markdown만
- `--format html`: HTML만 (stdout 출력)

생성 파일: `docs/reports/YYYY-MM-DD-daily.md`

### 2. 리포트 내용 확인

생성된 `docs/reports/YYYY-MM-DD-daily.md` 파일을 읽어서 사용자에게 핵심 요약을 보여줍니다:
- 미국/한국 주요 지수 등락
- 거래량 급등 종목 TOP 3
- 매크로 기반 추천 섹터/종목

### 3. Gmail 발송 (선택)

HTML 리포트를 Gmail MCP로 발송합니다:

1. HTML 출력을 변수에 저장: `python3 daily_report.py --format html 2>/dev/null`
2. Gmail MCP `send_email` 도구 호출:
   - **To:** `.env`의 `REPORT_EMAIL_TO` 또는 사용자에게 질문
   - **Subject:** `📊 일일 투자 리포트 — YYYY-MM-DD`
   - **Body:** 생성된 HTML

Gmail MCP 인증이 안 되어 있으면 `/mcp` → "claude.ai Gmail" 선택으로 먼저 인증.

### 4. 스케줄 등록 (`/report schedule`)

CronCreate로 자동 실행 등록:
- **cron:** `"27 8 * * 1-5"` (평일 08:27 KST)
- **prompt:** `/report`
- **recurring:** true
- **durable:** true (세션 재시작 후에도 유지)

⚠️ 7일 자동 만료 — 재등록 필요

## 리포트 4개 섹션

1. **나스닥/코스피 일일 분석** — 전일 종가, 변동률, 거래량
2. **글로벌/미국 시장 종합** — S&P500, DJI, VIX, 국채, 금/유가, 섹터 등락
3. **나스닥 떠오르는 기업** — 거래량 급등 TOP 10, 52주 신고가
4. **매크로 기반 종목 추천** — 경기사이클 → 유리 섹터 → 대표 종목

## 데이터 소스

| 소스 | 용도 | 라이브러리 |
|------|------|-----------|
| Yahoo Finance | 미국/글로벌 지수, 종목, 원자재 | yfinance |
| Yahoo Finance | 한국 KOSPI/KOSDAQ | yfinance (^KS11, ^KQ11) |
| FRED | 매크로 경제지표 (optional) | fredapi |
