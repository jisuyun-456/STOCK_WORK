---
name: Signal Engine Regression Bugs
description: 시그널 생성 경계에서 발생한 회귀 버그 이력. 유사 패턴 재발 방지용.
type: project
owner: signal-engine
---

Obsidian log(`_AutoResearch/STOCK/wiki/log.md`) + 커밋 이력에서 추출.
작업 시작 전 읽고, 동일 경계 작업 시 Regression guard를 체크리스트로 활용.

---

### [T1] QNT min_composite_score가 실제 score 분포와 불일치 → 모든 QNT 시그널 차단

- **Symptom:** `--phase signals` 결과 QNT 시그널 0건, trade_count=0
- **Root cause:** `strategies/quant_factor.py` min_composite_score=0.3 하드코딩. 실제 FF5 factor score 범위는 0.001~0.1 → 모든 종목 필터 아웃
- **Fix:** min_composite_score=0.01로 낮춤 (commit aabbc1e). `config/strategy_params.json`에서 로드하도록 config화
- **Regression guard:**
  - 임계치 수정 전 score 분포 히스토그램 확인: `python -c "from strategies.quant_factor import ...; print(scores.describe())"`
  - QNT 시그널 0건이면 score 분포 vs 임계치 먼저 확인 (리스크 게이트 아님)
  - `config/strategy_params.json` 수정 시 p5/p50/p95 근거 주석 추가 필수

### [T2] GRW regime 파라미터 self.regime 속성 폴백 누락 → BEAR BUY 차단 실패

- **Symptom:** GRW 전략에서 BEAR 레짐 BUY 차단이 간헐적으로 작동 안 함
- **Root cause:** `strategies/growth_smallcap.py` `__init__`에서 `self.regime` 설정 누락. regime 파라미터 없는 경로로 실행 시 AttributeError 대신 기본값 처리로 BEAR BUY 허용
- **Fix:** `self.regime` 폴백 추가 (commit 8f5135c)
- **Regression guard:**
  - 새 전략 추가 시 `self.regime` 속성 초기화 필수 (`__init__` 체크리스트)
  - BEAR 레짐에서 해당 전략 BUY 시그널 = 0건인지 테스트 추가

### [T11] regime 히스테리시스 카운터가 detected_regime 별도 추적 안 함 → 영구 잠금

- **Symptom:** 레짐이 한번 변경되면 히스테리시스 카운터가 리셋되지 않아 영구 잠금 발생
- **Root cause:** `research/consensus.py` 히스테리시스 로직에서 `current_regime`과 `detected_regime`을 동일 변수로 추적. detected_regime이 바뀌어도 카운터가 이전 상태 기준으로 계속 증가
- **Fix:** `detected_regime` 별도 변수로 분리 추적 (commit e272dc9)
- **Regression guard:**
  - 히스테리시스 로직 수정 시 `current_regime != detected_regime` 시나리오 단위 테스트 추가
  - BULL→NEUTRAL→BULL 전환 시 연속 카운터가 정상 리셋되는지 확인

### [GRW crash] pandas import 누락 → NameError → 전체 파이프라인 crash

- **Symptom:** `run_cycle.py --phase all` 실행 시 GRW 데이터 폴백 블록에서 NameError crash. 이후 모든 전략이 dry_run으로만 처리됨
- **Root cause:** `strategies/growth_smallcap.py` 폴백 블록에 `import pandas as pd` 누락. 정상 경로는 yfinance가 pandas를 transitively import하여 동작, 폴백 경로에서만 실패
- **Fix:** 파일 상단에 `import pandas as pd` 명시 추가
- **Regression guard:**
  - 전략 모듈 추가/수정 시 반드시 `python -c "import strategies.<module_name>"` 스모크 테스트
  - 폴백 코드 경로(try/except)에서 사용하는 외부 라이브러리는 명시적 import 필수
  - 하나의 전략 모듈 crash가 전체 파이프라인을 멈추지 않도록 run_cycle.py의 per-strategy try/except 유지
