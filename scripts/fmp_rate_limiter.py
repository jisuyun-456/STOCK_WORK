"""
FMP API Rate Limiter — 250콜/일 한도 관리
사용법:
  python scripts/fmp_rate_limiter.py check    → 현재 사용량 확인
  python scripts/fmp_rate_limiter.py add N    → N콜 기록
  python scripts/fmp_rate_limiter.py reset    → 수동 리셋
  python scripts/fmp_rate_limiter.py status   → 상세 상태 출력

에이전트/스크립트에서 import하여 사용:
  from scripts.fmp_rate_limiter import can_call, record_calls, get_status
"""

import json
import sys
from datetime import datetime, date
from pathlib import Path

USAGE_FILE = Path(__file__).parent.parent / ".claude" / "logs" / "fmp_usage.json"
DAILY_LIMIT = 250
WARN_THRESHOLD = 200   # 80% — 경고 시작
STOP_THRESHOLD = 245   # 98% — 분석 중단 권고
HARD_LIMIT = 250       # 100% — 완전 차단


def _load() -> dict:
    if USAGE_FILE.exists():
        data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        if data.get("date") == str(date.today()):
            return data
    return {"date": str(date.today()), "calls": 0, "log": []}


def _save(data: dict):
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_status() -> dict:
    """현재 FMP 사용량 상태 반환"""
    data = _load()
    calls = data["calls"]
    remaining = DAILY_LIMIT - calls
    pct = (calls / DAILY_LIMIT) * 100

    if calls >= HARD_LIMIT:
        level = "BLOCKED"
    elif calls >= STOP_THRESHOLD:
        level = "CRITICAL"
    elif calls >= WARN_THRESHOLD:
        level = "WARNING"
    else:
        level = "OK"

    return {
        "date": data["date"],
        "calls_used": calls,
        "calls_remaining": remaining,
        "percentage": round(pct, 1),
        "level": level,
        "daily_limit": DAILY_LIMIT,
    }


def can_call(n: int = 1) -> tuple[bool, str]:
    """
    n콜을 실행할 수 있는지 확인.
    Returns: (허용 여부, 메시지)
    """
    data = _load()
    after = data["calls"] + n
    remaining = DAILY_LIMIT - data["calls"]

    if after > HARD_LIMIT:
        return False, f"🔴 BLOCKED: FMP 일일 한도 초과! 사용 {data['calls']}/{DAILY_LIMIT}, 요청 {n}콜, 남은 {remaining}콜. 내일까지 대기하세요."

    if after > STOP_THRESHOLD:
        return True, f"🟡 CRITICAL: FMP {data['calls']+n}/{DAILY_LIMIT} ({round((after/DAILY_LIMIT)*100,1)}%). 남은 {DAILY_LIMIT-after}콜. 필수 분석만 진행하세요."

    if after > WARN_THRESHOLD:
        return True, f"⚠️ WARNING: FMP {data['calls']+n}/{DAILY_LIMIT} ({round((after/DAILY_LIMIT)*100,1)}%). 남은 {DAILY_LIMIT-after}콜."

    return True, f"✅ OK: FMP {data['calls']+n}/{DAILY_LIMIT} ({round((after/DAILY_LIMIT)*100,1)}%). 남은 {DAILY_LIMIT-after}콜."


def record_calls(n: int = 1, source: str = "unknown") -> str:
    """n콜 사용 기록. 차단 시 기록하지 않고 에러 반환."""
    allowed, msg = can_call(n)
    if not allowed:
        return msg

    data = _load()
    data["calls"] += n
    data["log"].append({
        "time": datetime.now().isoformat(),
        "count": n,
        "source": source,
        "total": data["calls"],
    })
    _save(data)
    return msg


def main():
    if len(sys.argv) < 2:
        print("Usage: python fmp_rate_limiter.py [check|add N|reset|status]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        allowed, msg = can_call(1)
        print(msg)
        sys.exit(0 if allowed else 1)

    elif cmd == "add":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        source = sys.argv[3] if len(sys.argv) > 3 else "manual"
        msg = record_calls(n, source)
        print(msg)

    elif cmd == "reset":
        _save({"date": str(date.today()), "calls": 0, "log": []})
        print("✅ FMP 사용량 리셋 완료.")

    elif cmd == "status":
        s = get_status()
        print(f"📊 FMP API 사용량 ({s['date']})")
        print(f"   사용: {s['calls_used']}/{s['daily_limit']} ({s['percentage']}%)")
        print(f"   남은: {s['calls_remaining']}콜")
        print(f"   상태: {s['level']}")
        if s['level'] == "BLOCKED":
            print("   🔴 일일 한도 도달. 내일 자동 리셋됩니다.")
        elif s['level'] == "CRITICAL":
            print("   🟡 한도 임박. 필수 분석만 진행하세요.")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
