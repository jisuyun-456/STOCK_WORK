"""Reset inception.strategies to match current allocated amounts.

performance.json[strategies][code][initial_nav]은 portfolios.json[inception][strategies][code]에서
파생된다. RL-2 재분배(LEV $20k→$50k) 후 inception이 stale 상태.
이 스크립트는 portfolios.json[inception]만 rewrite. performance.json은 다음 사이클에 자동 재계산.

Usage:
    python scripts/reset_initial_nav.py --dry-run   # 미리보기
    python scripts/reset_initial_nav.py             # 실제 반영
    python scripts/reset_initial_nav.py --strategies LEV MOM  # 특정 전략만
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIOS_PATH = ROOT / "state" / "portfolios.json"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reset portfolios.json inception.strategies to current allocated values."
    )
    ap.add_argument("--dry-run", action="store_true", help="미리보기만, 저장하지 않음")
    ap.add_argument("--strategies", nargs="*", default=None,
                    help="특정 전략만 리셋 (예: LEV MOM). 생략 시 전체")
    args = ap.parse_args()

    data = json.loads(PORTFOLIOS_PATH.read_text(encoding="utf-8"))
    strategies = data.get("strategies", {})
    inception = data.setdefault("inception", {})
    inception_strats = inception.setdefault("strategies", {})

    codes = args.strategies or sorted(strategies.keys())
    changes: list[tuple[str, float, float]] = []

    for code in codes:
        if code not in strategies:
            print(f"[reset] SKIP {code} — not in portfolios.strategies")
            continue
        old = float(inception_strats.get(code, 0) or 0)
        new = round(float(strategies[code].get("allocated", 0) or 0), 2)
        if abs(old - new) < 0.01:
            print(f"[reset] {code}: ${old:,.2f} (unchanged)")
            continue
        changes.append((code, old, new))
        print(f"[reset] {code}: ${old:,.2f} → ${new:,.2f}")

    if not changes:
        print("[reset] 변경 사항 없음")
        return 0

    new_total = round(
        sum(float(strategies[c].get("allocated", 0) or 0) for c in strategies), 2
    )
    old_total = float(inception.get("total", 0) or 0)
    print(f"[reset] inception.total: ${old_total:,.2f} → ${new_total:,.2f}")

    if args.dry_run:
        print("[reset] --dry-run: 저장하지 않음")
        return 0

    # 백업
    backup = PORTFOLIOS_PATH.with_suffix(
        f".json.bak_reset_{date.today().isoformat()}"
    )
    backup.write_text(PORTFOLIOS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[reset] backup → {backup.name}")

    for code, _old, new in changes:
        inception_strats[code] = new
    inception["total"] = new_total
    inception["reset_date"] = date.today().isoformat()

    PORTFOLIOS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("[reset] 저장 완료. 다음 run_cycle 시 performance.json 자동 재계산")
    return 0


if __name__ == "__main__":
    sys.exit(main())
