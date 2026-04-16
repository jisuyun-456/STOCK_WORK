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
