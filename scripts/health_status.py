"""Cycle Health 대시보드 — state/cycle_health.json 요약 출력.

사용법:
    python scripts/health_status.py           # 최근 10사이클
    python scripts/health_status.py --last 20 # 최근 20사이클
    python scripts/health_status.py --json    # JSON 출력
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 디렉토리에서 실행 시 필요)
sys.path.insert(0, str(Path(__file__).parent.parent))

STATE_DIR = Path(__file__).parent.parent / "state"
HEALTH_PATH = STATE_DIR / "cycle_health.json"


def main():
    parser = argparse.ArgumentParser(description="Cycle Health Dashboard")
    parser.add_argument("--last", type=int, default=10, help="최근 N사이클 표시")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON 형식 출력")
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

    if args.as_json:
        print(json.dumps({"stabilization": stab, "recent": recent}, indent=2, ensure_ascii=False))
        return

    print(f"=== Cycle Health Dashboard (최근 {len(recent)}사이클) ===")
    print(f"상태: {stab['status']} | 연속 클린: {stab['consecutive_clean']} | 총 사이클: {stab['total_cycles']}")
    print()
    print(f"{'날짜':<12} {'dry':>4} {'total':>6} {'crash':>6} {'phase':>6} {'order':>6} {'data':>5}")
    print("-" * 58)
    for e in recent:
        print(
            f"{e.get('cycle_date', '?'):<12} "
            f"{'Y' if e.get('dry_run') else 'N':>4} "
            f"{e.get('total_errors', 0):>6} "
            f"{e.get('crash', 0):>6} "
            f"{e.get('phase_error', 0):>6} "
            f"{e.get('order_error', 0):>6} "
            f"{e.get('data_warning', 0):>5}"
        )
    print()
    if stab["status"] == "STABILIZED":
        print(f"*** {stab['message']} ***")
    else:
        print(stab["message"])


if __name__ == "__main__":
    main()
