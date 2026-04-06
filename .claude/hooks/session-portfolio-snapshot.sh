#!/usr/bin/env bash
# 세션 종료 시 포트폴리오 스냅샷 자동 저장
# Stop 훅으로 실행됨
INPUT=$(cat)

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR=".claude/logs"
mkdir -p "$LOG_DIR"

# 세션 종료 로그
echo "${TIMESTAMP}|STOP|session-end" >> "$LOG_DIR/agent-usage.log"

# 포트폴리오 스냅샷 (simulation_tracker가 있으면)
if [ -f "scripts/simulation_tracker.py" ]; then
  python3 scripts/simulation_tracker.py snapshot 2>/dev/null >> "$LOG_DIR/portfolio-snapshots.log"
fi
exit 0
