"""Cycle Health Tracker — 사이클별 에러 카운트 추적 + 안정화 판정.

에러 분류:
  CRASH        — sys.exit(non-zero) 또는 처리되지 않은 예외
  PHASE_ERROR  — phase_* 함수의 except 블록에서 잡힌 예외
  ORDER_ERROR  — unfilled / partial_fill / error fill_status
  DATA_WARNING — NaN, inception-drift >=10%, degraded data
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
