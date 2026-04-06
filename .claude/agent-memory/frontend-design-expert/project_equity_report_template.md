---
name: Equity Report HTML Template
description: STOCK_WORK 프로젝트 Equity Research Report Jinja2 HTML 템플릿 설계 결정 사항 (크림 에디토리얼 2종)
type: project
---

`templates/equity_report.html` — 8탭 싱글페이지 Jinja2 Equity Research 템플릿 (크림 에디토리얼 테마, 브라우저 전용).
`templates/equity_report_pdf.html` — WeasyPrint PDF 전용 Jinja2 템플릿 (크림 테마, JavaScript/Chart.js 없음).

**Why:** 두 파일 모두 GS 리서치 스타일 크림/화이트 에디토리얼 테마 통일. 브라우저판은 검은 상단바(#1A1814) + 코랄 악센트(#C8523A) 적용으로 차별화.

**How to apply:** 이 템플릿 수정 시 아래 설계 결정 참조. 두 파일은 동일한 Jinja2 변수 구조 공유.

## 디자인 토큰 (equity_report.html — 크림 에디토리얼)
`--bg:#FAF8F4 --bg2:#FFFFFF --bg3:#F2EDE3 --border:#E0DBD0 --text:#1A1814`
`--muted:#8A857C --up:#1E7A45 --down:#C8523A --gold:#A87228`
`--blue:#1E5FA8 --purple:#6B46C1 --cyan:#0E7490`
`--font: 'Pretendard', -apple-system, 'Segoe UI', sans-serif`

## Jinja2 필터 의존성 (반드시 호출 스크립트에서 등록)
- `fmt_num(v)` — 숫자를 $1.2B/$500M/$3.5K 형식으로
- `fmt_pct(v)` — +12.3% / -5.1% 형식
- `pct_class(v)` — 'up'/'dn'/'nt' CSS 클래스 반환
- `enumerate` 는 Jinja2 필터가 아님 — loop.index0 으로 대체 처리됨

## 탭 구조 (id 기준)
ch1=Summary, ch2=Business, ch3=Financials, ch4=Valuation,
ch5=Catalysts, ch6=Risks, ch7=Industry, ch8=Conclusion

## 감지된 패턴
- DCF sensitivity_matrix: `loop.index0`으로 row_label 인덱싱 (enumerate 필터 미지원)
- 리스크 카드: prob/impact 문자열 'high'/'mid'/'low' 소문자 비교로 badge 색상 분기
- 민감도 히트맵: current_price_num(숫자형) 기준 ±5%/±20% 5단계 색상

## 브라우저판 GS 스타일 특이사항 (equity_report.html)
- NAV 헤더: background #1A1814 (검정) + border-bottom 2px solid #C8523A (코랄 악센트)
- 탭 활성: background #C8523A / 비활성 text #8A857C
- data-table thead: background #1A1814, color #FAF8F4 (검은 헤더 — GS 스타일)
- sens-table th/row-label: 동일하게 #1A1814 배경 처리
- 히트맵: high=#1E7A45(텍스트 #E8F5EE), mid2=#c8e8d4, mid=#E8F5EE(텍스트 #1E7A45), mid3=#f0c4b8, low=#C8523A(텍스트 #FBF0ED)
- rating/scenario/prob/impact 배지: 밝은 배경 + 진한 텍스트 (light-bg pattern)
- body font-size: 13px (가독성 향상)
- 스크롤바 thumb: #d4cfc6

## PDF 크림 테마 설계 (equity_report_pdf.html)
- `@page { size: A4; margin: 2cm; }` — WeasyPrint 전용
- JS/Chart.js 없음, 탭 없음, 모든 챕터 순차 배치
- 챕터 간 `.page-break { page-break-before: always; }` 적용
- 폰트: 제목/Rating = Georgia serif, 본문 = Pretendard/system sans, 숫자 = DM Mono/Consolas
- 시스템 폰트만 사용 (CDN 로드 없음)
- 커버 페이지: 검은 배경 헤더 + 크림 바디
- .fin-table: `th { background: var(--ink); color: var(--cream); }` — 재무 테이블 전용
- 히트맵: print-safe 밝은 톤 (C8ECD5/DFF0E5/FBF3E2/FCDDD4/F8C9BE)
- 리스크 배지: High=coral-bg, Medium=gold-bg, Low=up-bg (인쇄 가능 밝은 배경)
