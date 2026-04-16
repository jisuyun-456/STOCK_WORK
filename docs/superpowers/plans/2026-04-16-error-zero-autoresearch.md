# Error-Zero Pipeline & AutoResearch 최적화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `run_cycle.py` 종료 시 에러를 정량 추적하여 연속 5사이클 에러 0 = "STABILIZED" 선언 → 안정화 후 AutoResearch Iteration 4 수익률 최적화 실행.

**Architecture:** `state/cycle_health.py` CycleHealthTracker가 에러 카운트를 메모리에 누적하고, `run_cycle.py main()` 종료 직전에 `state/cycle_health.json` (atomic write)에 저장. 5회 연속 에러=0 시 STABILIZED 플래그 설정 + 로그 출력.

**Tech Stack:** Python 3.11+, pathlib, json, os (atomic write), pytest (TDD)

---

## 에러 분류 체계 (Error Taxonomy)

| 타입 | 설명 | 발생 위치 |
|------|------|---------|
| CRASH | sys.exit(non-zero) or unhandled exception | main() 최상단 except |
| PHASE_ERROR | 각 phase_* 함수 except에서 잡힌 예외 | phase_data/signals/regime/... |
| ORDER_ERROR | unfilled / partial_fill / error fill_status | execute_signal 결과 |
| DATA_WARNING | NaN, inception-drift ≥10%, degraded data | phase_data, performance |

> 목표: 모든 타입 합산 = 0 × 5연속 → STABILIZED

---

## 파일 구조

| 파일 | 변경 유형 | 역할 |
|------|--------|------|
| `state/cycle_health.py` | 신규 생성 | CycleHealthTracker 클래스, `save()`, `load_history()`, `check_stabilization()` |
| `run_cycle.py` | 수정 | main() 상단 tracker 초기화, phase별 error 기록, 종료 직전 `tracker.save()` + `check_stabilization()` |
| `state/cycle_health.json` | 런타임 생성 | 사이클별 에러 기록 JSONL (append 방식) |
| `tests/test_cycle_health.py` | 신규 생성 | TDD 테스트 9개 |

---

## Task 1: CycleHealthTracker 클래스 (TDD)

**Files:**
- Create: `state/cycle_health.py`
- Create: `tests/test_cycle_health.py`

### Step 1-1: 실패하는 테스트 작성

- [ ] `tests/test_cycle_health.py` 생성:

```python
"""TDD: CycleHealthTracker 클래스 검증 (2026-04-16)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ─── T1: 기본 에러 카운트 ────────────────────────────────────────────────────

class TestCycleHealthTracker:
    def _make_tracker(self, tmp_path):
        from state.cycle_health import CycleHealthTracker
        return CycleHealthTracker(health_path=tmp_path / "cycle_health.json")

    def test_initial_counts_all_zero(self, tmp_path):
        """새 tracker는 모든 카운트 0."""
        t = self._make_tracker(tmp_path)
        assert t.crash == 0
        assert t.phase_error == 0
        assert t.order_error == 0
        assert t.data_warning == 0
        assert t.total == 0

    def test_record_error_increments_count(self, tmp_path):
        """record() 호출 시 해당 타입 카운트 증가."""
        t = self._make_tracker(tmp_path)
        t.record("PHASE_ERROR", "phase_signals", "timeout")
        t.record("ORDER_ERROR", "execute", "unfilled NVDA")
        assert t.phase_error == 1
        assert t.order_error == 1
        assert t.total == 2

    def test_unknown_error_type_raises(self, tmp_path):
        """미정의 에러 타입 → ValueError."""
        t = self._make_tracker(tmp_path)
        with pytest.raises(ValueError, match="Unknown error type"):
            t.record("BOGUS_TYPE", "phase", "msg")

    def test_save_creates_json_line(self, tmp_path):
        """save() → cycle_health.json에 JSON 라인 추가."""
        t = self._make_tracker(tmp_path)
        t.record("DATA_WARNING", "phase_data", "NaN SPY")
        t.save(cycle_date="2026-04-16", dry_run=False)

        lines = (tmp_path / "cycle_health.json").read_text().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["total_errors"] == 1
        assert entry["data_warning"] == 1
        assert entry["cycle_date"] == "2026-04-16"
        assert entry["dry_run"] is False

    def test_save_appends_multiple_cycles(self, tmp_path):
        """두 번 save() → 두 줄 append (덮어쓰기 아님)."""
        for i in range(2):
            t = self._make_tracker(tmp_path)
            t.save(cycle_date=f"2026-04-1{i+6}", dry_run=False)

        lines = (tmp_path / "cycle_health.json").read_text().splitlines()
        assert len(lines) == 2

    def test_save_atomic_no_tmp_leak(self, tmp_path):
        """save() 성공 후 .tmp 파일이 남지 않아야 한다."""
        t = self._make_tracker(tmp_path)
        t.save(cycle_date="2026-04-16", dry_run=False)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"tmp file leaked: {tmp_files}"


# ─── T2: 안정화 체크 ─────────────────────────────────────────────────────────

class TestCheckStabilization:
    def _make_health_file(self, tmp_path, entries: list[dict]) -> Path:
        p = tmp_path / "cycle_health.json"
        lines = [json.dumps(e) for e in entries]
        p.write_text("\n".join(lines) + "\n")
        return p

    def test_five_zero_error_cycles_returns_stabilized(self, tmp_path):
        """최근 5사이클 모두 total_errors=0 → STABILIZED."""
        from state.cycle_health import check_stabilization
        p = self._make_health_file(tmp_path, [
            {"total_errors": 0, "cycle_date": f"2026-04-{10+i}"} for i in range(5)
        ])
        result = check_stabilization(p)
        assert result["status"] == "STABILIZED"
        assert result["consecutive_clean"] == 5

    def test_four_zero_then_one_error_not_stabilized(self, tmp_path):
        """4개 clean + 1개 error → NOT_STABILIZED."""
        from state.cycle_health import check_stabilization
        entries = [{"total_errors": 0, "cycle_date": f"2026-04-{10+i}"} for i in range(4)]
        entries.append({"total_errors": 1, "cycle_date": "2026-04-15"})
        p = self._make_health_file(tmp_path, entries)
        result = check_stabilization(p)
        assert result["status"] == "NOT_STABILIZED"
        assert result["consecutive_clean"] < 5

    def test_fewer_than_five_cycles_not_stabilized(self, tmp_path):
        """기록이 3개뿐 (모두 0) → NOT_STABILIZED."""
        from state.cycle_health import check_stabilization
        p = self._make_health_file(tmp_path, [
            {"total_errors": 0, "cycle_date": f"2026-04-{10+i}"} for i in range(3)
        ])
        result = check_stabilization(p)
        assert result["status"] == "NOT_STABILIZED"

    def test_missing_file_returns_no_data(self, tmp_path):
        """파일 없으면 status=NO_DATA."""
        from state.cycle_health import check_stabilization
        result = check_stabilization(tmp_path / "nonexistent.json")
        assert result["status"] == "NO_DATA"
```

### Step 1-2: 테스트 실패 확인

- [ ] 실행: `python -m pytest tests/test_cycle_health.py -v`
- 예상: `ModuleNotFoundError: No module named 'state.cycle_health'`

### Step 1-3: `state/cycle_health.py` 구현

- [ ] `state/__init__.py` 없으면 생성 (비어있어도 됨):

```python
# state/__init__.py
```

- [ ] `state/cycle_health.py` 생성:

```python
"""Cycle Health Tracker — 사이클별 에러 카운트 추적 + 안정화 판정.

에러 분류:
  CRASH        — sys.exit(non-zero) 또는 처리되지 않은 예외
  PHASE_ERROR  — phase_* 함수의 except 블록에서 잡힌 예외
  ORDER_ERROR  — unfilled / partial_fill / error fill_status
  DATA_WARNING — NaN, inception-drift ≥10%, degraded data
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

VALID_ERROR_TYPES = frozenset({"CRASH", "PHASE_ERROR", "ORDER_ERROR", "DATA_WARNING"})

_DEFAULT_PATH = Path(__file__).parent / "cycle_health.json"


class CycleHealthTracker:
    """단일 사이클 에러 카운트 누적기.

    사용법:
        tracker = CycleHealthTracker()
        tracker.record("PHASE_ERROR", "phase_signals", "yfinance timeout")
        tracker.save(cycle_date="2026-04-16", dry_run=False)
    """

    def __init__(self, health_path: Path | None = None):
        self._path = Path(health_path) if health_path else _DEFAULT_PATH
        self.crash: int = 0
        self.phase_error: int = 0
        self.order_error: int = 0
        self.data_warning: int = 0
        self._events: list[dict] = []

    @property
    def total(self) -> int:
        return self.crash + self.phase_error + self.order_error + self.data_warning

    def record(self, error_type: str, source: str, detail: str = "") -> None:
        """에러 카운트 증가 + 이벤트 기록.

        Args:
            error_type: CRASH | PHASE_ERROR | ORDER_ERROR | DATA_WARNING
            source: 발생 위치 (예: "phase_signals", "execute_signal")
            detail: 추가 설명 (예: 종목코드, 예외 메시지)

        Raises:
            ValueError: 미정의 error_type
        """
        if error_type not in VALID_ERROR_TYPES:
            raise ValueError(
                f"Unknown error type: {error_type!r}. "
                f"Valid types: {sorted(VALID_ERROR_TYPES)}"
            )
        if error_type == "CRASH":
            self.crash += 1
        elif error_type == "PHASE_ERROR":
            self.phase_error += 1
        elif error_type == "ORDER_ERROR":
            self.order_error += 1
        elif error_type == "DATA_WARNING":
            self.data_warning += 1

        self._events.append({
            "type": error_type,
            "source": source,
            "detail": detail,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    def save(self, cycle_date: str, dry_run: bool) -> None:
        """현재 사이클 결과를 cycle_health.json에 atomic append.

        Atomic: tmp 파일 write → fsync → os.replace (crash-safe).
        기존 기록은 보존 (append-only, Immutable Ledger 원칙).
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # 기존 내용 읽기
        existing = ""
        if self._path.exists():
            existing = self._path.read_text(encoding="utf-8")

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "cycle_date": cycle_date,
            "dry_run": dry_run,
            "total_errors": self.total,
            "crash": self.crash,
            "phase_error": self.phase_error,
            "order_error": self.order_error,
            "data_warning": self.data_warning,
            "events": self._events,
        }
        new_content = existing + json.dumps(entry, ensure_ascii=False) + "\n"

        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise


def check_stabilization(
    health_path: Path | None = None,
    required_clean: int = 5,
) -> dict:
    """최근 N사이클이 모두 에러 0인지 확인.

    Returns:
        {
            "status": "STABILIZED" | "NOT_STABILIZED" | "NO_DATA",
            "consecutive_clean": int,
            "total_cycles": int,
            "message": str,
        }
    """
    path = Path(health_path) if health_path else _DEFAULT_PATH

    if not path.exists():
        return {
            "status": "NO_DATA",
            "consecutive_clean": 0,
            "total_cycles": 0,
            "message": "cycle_health.json 없음 — 아직 사이클 미실행",
        }

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 손상 라인 스킵

    if not entries:
        return {
            "status": "NO_DATA",
            "consecutive_clean": 0,
            "total_cycles": 0,
            "message": "cycle_health.json에 유효한 엔트리 없음",
        }

    recent = entries[-required_clean:]  # 최근 N개
    consecutive_clean = 0
    for e in reversed(entries):
        if e.get("total_errors", 1) == 0:
            consecutive_clean += 1
        else:
            break

    if len(entries) >= required_clean and all(
        e.get("total_errors", 1) == 0 for e in recent
    ):
        return {
            "status": "STABILIZED",
            "consecutive_clean": consecutive_clean,
            "total_cycles": len(entries),
            "message": (
                f"STABILIZED: 최근 {required_clean}사이클 연속 에러 0 "
                f"(총 {len(entries)}사이클 기록)"
            ),
        }

    return {
        "status": "NOT_STABILIZED",
        "consecutive_clean": consecutive_clean,
        "total_cycles": len(entries),
        "message": (
            f"NOT_STABILIZED: 연속 클린 {consecutive_clean}/{required_clean} "
            f"(총 {len(entries)}사이클)"
        ),
    }
```

### Step 1-4: 테스트 통과 확인

- [ ] 실행: `python -m pytest tests/test_cycle_health.py -v`
- 예상: 9개 모두 PASSED

### Step 1-5: 커밋

```bash
git add state/cycle_health.py tests/test_cycle_health.py
git commit -m "feat(health): CycleHealthTracker + check_stabilization TDD 구현"
```

---

## Task 2: run_cycle.py — 에러 훅 연결

**Files:**
- Modify: `run_cycle.py` (main() 함수 내)

이 태스크는 기존 `except` 블록에 `tracker.record()` 호출을 추가한다.
소스 변경이 작고 분산되어 있으므로 테스트를 먼저 작성하기 어렵다 — 대신 통합 검증(Step 2-4)으로 확인.

### Step 2-1: tracker 임포트 + 초기화 추가

- [ ] `run_cycle.py` 상단 임포트 섹션에 추가 (`from pathlib import Path` 근처):

```python
from state.cycle_health import CycleHealthTracker, check_stabilization
```

- [ ] `main()` 함수에서 `_audit_log("main", "start", ...)` 직후에 tracker 초기화 추가:

```python
    # Cycle Health Tracker — 에러 카운트 누적
    _health_tracker = CycleHealthTracker()
```

(기존 코드 `_audit_log("main", "start", {"phase": args.phase, "dry_run": args.dry_run})` 바로 다음 줄)

### Step 2-2: Phase ERROR 훅 연결

각 phase 호출 블록에 except 보강. 현재 `phase_data()`, `phase_signals()`, `phase_regime()`, `phase_research()`, `phase_risk()`, `phase_resolve()`, `phase_execute()`, `phase_report()` 는 try-except 없이 직접 호출됨. 아래처럼 감싸거나 기존 except에 record 추가.

- [ ] **Phase 1 DATA** — `phase_data()` 호출 블록을 다음으로 교체:

```python
    # Phase 1: DATA
    if args.phase in ("all", "data"):
        try:
            market_data = phase_data()
        except Exception as e:
            _health_tracker.record("PHASE_ERROR", "phase_data", str(e))
            print(f"  [ERROR] phase_data: {e}")
            market_data = None
        print()
    else:
        market_data = None
```

- [ ] **Phase 1.5 REGIME** — 기존 `except Exception: detected_consec = 1; regime = detected_regime` 블록(line ~1867)에 record 추가:

```python
            except Exception as e:
                _health_tracker.record("PHASE_ERROR", "phase_regime_hysteresis", str(e))
                detected_consec = 1
                regime = detected_regime
```

- [ ] **Phase 2 SIGNALS** — `phase_signals()` 호출 블록을 다음으로 교체:

```python
    # Phase 2: SIGNALS
    if args.phase in ("all", "signals"):
        _audit_log("signals", "start", {"regime": regime if 'regime' in dir() else "unknown"})
        try:
            raw_signals = phase_signals(regime=regime if 'regime' in dir() else "NEUTRAL",
                                        allocations=allocations)
        except Exception as e:
            _health_tracker.record("PHASE_ERROR", "phase_signals", str(e))
            print(f"  [ERROR] phase_signals: {e}")
            raw_signals = []
        _audit_log("signals", "end", {"count": len(raw_signals)})
        print()
    else:
        raw_signals = []
```

> **주의**: 실제 run_cycle.py의 phase_signals 호출 시그니처를 읽고 정확히 맞출 것. 위 코드는 패턴 예시임.

- [ ] **Phase 5 EXECUTE** — `phase_execute()` 결과에서 ORDER_ERROR 카운트:

```python
    # Phase 5: EXECUTE
    if args.phase in ("all", "execute"):
        _audit_log("execute", "start", {"signals": len(resolved), "dry_run": args.dry_run})
        results = phase_execute(resolved, dry_run=args.dry_run)
        # ORDER_ERROR 카운트
        for r in (results or []):
            if r.get("status") in ("unfilled", "error"):
                _health_tracker.record(
                    "ORDER_ERROR", "phase_execute",
                    f"{r.get('symbol','?')} status={r.get('status')}"
                )
            elif r.get("status") == "partial_fill":
                _health_tracker.record(
                    "ORDER_ERROR", "phase_execute",
                    f"{r.get('symbol','?')} partial_fill"
                )
        _audit_log("execute", "end", {"results": len(results)})
        print()
    else:
        results = []
```

### Step 2-3: DATA_WARNING 훅

- [ ] `phase_data()` 내부 또는 main() 안에서 inception-drift 체크 후 record 추가:

`run_cycle.py`의 `_check_allocation_integrity()` 함수 호출 블록 (~line 1793):

```python
    try:
        _pre_portfolios = load_portfolios()
        _check_allocation_integrity(_pre_portfolios)
    except Exception as e:
        _health_tracker.record("DATA_WARNING", "allocation_integrity", str(e))
        print(f"  [integrity] pre-flight check skipped: {e}")
```

그리고 degraded data 경고 블록 (~line 1775):

```python
    try:
        if DEGRADED_COUNT_PATH.exists():
            _dc = json.loads(DEGRADED_COUNT_PATH.read_text(encoding="utf-8"))
            consec = int(_dc.get("consecutive", 0))
            if consec >= 2:
                _health_tracker.record(
                    "DATA_WARNING", "degraded_data",
                    f"consecutive_degraded={consec}"
                )
                print(
                    f"  [WARNING] 이전 사이클 degraded {consec}회 연속 — "
                    f"데이터 소스 확인 권장"
                )
    except Exception:
        pass
```

### Step 2-4: save + stabilization 호출 (main() 종료 직전)

- [ ] `run_cycle.py`에서 `print("=== Cycle Complete ===")` 바로 뒤, `_backup_state_files()` 호출 전에 추가:

```python
    print("=== Cycle Complete ===")

    # Cycle Health: 에러 카운트 저장 + 안정화 판정
    _cycle_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        _health_tracker.save(cycle_date=_cycle_date, dry_run=args.dry_run)
        _stab = check_stabilization()
        if _stab["status"] == "STABILIZED":
            print(f"\n{'='*50}")
            print(f"  *** {_stab['message']} ***")
            print(f"{'='*50}\n")
        else:
            print(f"  [health] {_stab['message']}")
    except Exception as e:
        print(f"  [health] WARNING: 저장 실패 ({e})")

    _backup_state_files()
    _audit_log("main", "end", {"phase": args.phase, "resolved": len(resolved)})
```

### Step 2-5: 통합 검증 (dry-run)

- [ ] 실행: `python run_cycle.py --phase all --dry-run`
- 예상: 
  - `[health] NOT_STABILIZED: 연속 클린 ...` 또는 STABILIZED 메시지 출력
  - `state/cycle_health.json` 파일 생성 확인
  - `python -c "import json; [print(json.loads(l)) for l in open('state/cycle_health.json')]"` 으로 내용 확인

- [ ] 실행: `python -m pytest tests/test_cycle_health.py tests/test_workflow_hardening.py -q`
- 예상: 전체 PASS (새 테스트 포함)

### Step 2-6: 커밋

```bash
git add run_cycle.py
git commit -m "feat(health): run_cycle.py 에러 훅 연결 + cycle_health.json 저장"
```

---

## Task 3: 안정화 대시보드 스크립트

**Files:**
- Create: `scripts/health_status.py`

사이클 헬스 현황을 CLI에서 빠르게 확인하는 유틸리티.

### Step 3-1: 스크립트 생성

- [ ] `scripts/health_status.py` 생성:

```python
"""Cycle Health 대시보드 — state/cycle_health.json 요약 출력.

사용법:
    python scripts/health_status.py           # 최근 10사이클
    python scripts/health_status.py --last 20 # 최근 20사이클
    python scripts/health_status.py --json    # JSON 출력
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STATE_DIR = Path(__file__).parent.parent / "state"
HEALTH_PATH = STATE_DIR / "cycle_health.json"


def main():
    parser = argparse.ArgumentParser(description="Cycle Health Dashboard")
    parser.add_argument("--last", type=int, default=10, help="최근 N사이클 표시")
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = parser.parse_args()

    from state.cycle_health import check_stabilization

    if not HEALTH_PATH.exists():
        print("cycle_health.json 없음 — 아직 사이클 미실행")
        return

    entries = []
    for line in HEALTH_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    recent = entries[-args.last:]
    stab = check_stabilization(HEALTH_PATH)

    if args.json:
        print(json.dumps({"stabilization": stab, "recent": recent}, indent=2, ensure_ascii=False))
        return

    print(f"=== Cycle Health Dashboard (최근 {len(recent)}사이클) ===")
    print(f"상태: {stab['status']} | 연속 클린: {stab['consecutive_clean']} | 총 사이클: {stab['total_cycles']}")
    print()
    print(f"{'날짜':<12} {'dry':>4} {'total':>6} {'crash':>6} {'phase':>6} {'order':>>6} {'data':>5}")
    print("-" * 58)
    for e in recent:
        print(
            f"{e.get('cycle_date','?'):<12} "
            f"{'Y' if e.get('dry_run') else 'N':>4} "
            f"{e.get('total_errors',0):>6} "
            f"{e.get('crash',0):>6} "
            f"{e.get('phase_error',0):>6} "
            f"{e.get('order_error',0):>6} "
            f"{e.get('data_warning',0):>5}"
        )
    print()
    if stab["status"] == "STABILIZED":
        print(f"*** {stab['message']} ***")
    else:
        print(stab["message"])


if __name__ == "__main__":
    main()
```

### Step 3-2: 동작 확인

- [ ] 실행: `python scripts/health_status.py`
- 예상: 대시보드 테이블 출력

### Step 3-3: 커밋

```bash
git add scripts/health_status.py
git commit -m "feat(health): health_status.py 대시보드 CLI 추가"
```

---

## Task 4: 안정화 조건 달성 전략 (운영 가이드)

이 태스크는 코드 변경 없이, 안정화 달성까지의 운영 체크리스트다.

### Step 4-1: 알려진 에러 원인 체크

- [ ] `state/audit_log.jsonl`에서 최근 PHASE_ERROR 확인:

```bash
python -c "
import json
from pathlib import Path
for line in Path('state/audit_log.jsonl').read_text().splitlines()[-50:]:
    try:
        e = json.loads(line)
        if e.get('action') == 'error':
            print(e)
    except: pass
"
```

- [ ] inception-drift 확인 후 필요시 리셋:

```bash
python scripts/reset_initial_nav.py
```

- [ ] 연속 5사이클 dry-run 실행:

```bash
for i in 1 2 3 4 5; do
    echo "=== Cycle $i ==="
    python run_cycle.py --phase all --dry-run
    echo ""
done
```

- [ ] 안정화 확인:

```bash
python scripts/health_status.py
```

- 예상: `STABILIZED: 최근 5사이클 연속 에러 0`

---

## Task 5: AutoResearch Iteration 4 — Variant A vs D 비교

> **전제조건**: Task 4에서 STABILIZED 선언 후 실행

**Goal**: 연구 오버레이 선택적 적용 (selective vs full vs skip) 성과를 비교하여 수익률 개선 전략 결정.

**Files:**
- Modify: `docs/superpowers/plans/2026-04-16-error-zero-autoresearch.md` (this file) — Iteration 4 결과 기록
- Create: `_AutoResearch/STOCK/outputs/iteration4_comparison.md` (결과 파일)

### Step 5-1: 현재 성과 베이스라인 수집

- [ ] 실행: `python scripts/performance_calculator.py`
- 결과를 `_AutoResearch/STOCK/outputs/iteration4_baseline.json`에 저장

### Step 5-2: Variant A (현재: selective mode) 10사이클 실행

- [ ] dry-run으로 10사이클:

```bash
for i in $(seq 1 10); do
    python run_cycle.py --phase all --dry-run --research-mode selective
done
python scripts/health_status.py --last 10
python scripts/performance_calculator.py
```

### Step 5-3: Variant D (full research) 10사이클 실행

- [ ] dry-run으로 10사이클:

```bash
for i in $(seq 1 10); do
    python run_cycle.py --phase all --dry-run --research-mode full
done
python scripts/performance_calculator.py
```

### Step 5-4: 비교 분석

비교 지표:
- 총 수익률 (NAV 변화)
- Sharpe Ratio
- MDD (Max Drawdown)
- 에러율 (cycle_health.json)
- 실행 시간 (selective vs full)

- [ ] 결과를 `_AutoResearch/STOCK/outputs/iteration4_comparison.md`에 정리

### Step 5-5: 결정 + AutoResearch log 업데이트

- [ ] 비교 결과에 따라 기본 research_mode 결정 (run_cycle.py 기본값 변경 또는 CLAUDE.md 업데이트)
- [ ] `_AutoResearch/STOCK/wiki/log.md`에 Iteration 4 결과 기록:

```markdown
## [2026-04-16] AutoResearch | Iteration 4 — Variant A vs D 비교
- 파이프라인 STABILIZED (연속 5사이클 에러 0) 달성 후 실행
- 결과: [Variant X 선택 + 근거]
- 다음: Iteration 5 — [다음 최적화 항목]
```

### Step 5-6: 커밋

```bash
git add _AutoResearch/STOCK/ docs/superpowers/plans/
git commit -m "research: AutoResearch Iteration 4 Variant A vs D 비교 완료"
```

---

## 검증 체크리스트 (전체)

```bash
# 1. 단위 테스트 전체
python -m pytest tests/test_cycle_health.py tests/test_workflow_hardening.py -v

# 2. cycle_health.json 생성 확인
python run_cycle.py --phase all --dry-run
cat state/cycle_health.json

# 3. 대시보드 확인
python scripts/health_status.py

# 4. 안정화 상태 확인
python -c "
from state.cycle_health import check_stabilization
import pprint
pprint.pprint(check_stabilization())
"
```

---

## 수정 파일 요약

| 파일 | 타입 | 설명 |
|------|------|------|
| `state/cycle_health.py` | 신규 | CycleHealthTracker + check_stabilization |
| `state/__init__.py` | 신규 (없으면) | 패키지 초기화 |
| `tests/test_cycle_health.py` | 신규 | TDD 9개 테스트 |
| `run_cycle.py` | 수정 | tracker 초기화, phase 에러 훅, main() 종료 전 save |
| `scripts/health_status.py` | 신규 | CLI 대시보드 |
