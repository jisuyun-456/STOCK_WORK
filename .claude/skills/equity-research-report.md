---
name: equity-research-report
description: >
  GS/JPM 수준 8챕터 Equity Research Report 생성.
  "분석해줘", "보고서 작성", "리서치 리포트", "equity research" 키워드로 트리거.
globs:
  - "scripts/equity_report_generator.py"
  - "templates/equity_report*.html"
---

# Equity Research Report 생성

사용자가 특정 종목에 대한 분석을 요청하면, /analyze 커맨드와 동일한 프로세스를 실행합니다.

## 트리거 키워드
- "{종목명} 분석해줘"
- "{종목명} 보고서 작성해줘"
- "{티커} equity research"
- "리서치 리포트"

## 실행
요청에서 종목 심볼을 추출한 후, `/analyze {SYMBOL}` 커맨드의 절차를 동일하게 따릅니다.
