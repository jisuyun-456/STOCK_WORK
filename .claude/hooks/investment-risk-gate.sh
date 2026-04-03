#!/usr/bin/env bash
# 투자 판단 리스크 경고 게이트 (D5 프로젝트 매니저)
# Stop 훅으로 실행됨 — 세션 종료 시 투자 활동 로그 기록
INPUT=$(cat)

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR=".claude/logs"
mkdir -p "$LOG_DIR"

echo "${TIMESTAMP}|STOP|investment-session-end" >> "$LOG_DIR/agent-usage.log"
exit 0
