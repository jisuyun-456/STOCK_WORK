#!/usr/bin/env bash
# 에이전트 사용 로그 기록 (D5 프로젝트 매니저)
# SubagentStop 훅으로 실행됨
INPUT=$(cat)

AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // "unknown"')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

LOG_DIR=".claude/logs"
mkdir -p "$LOG_DIR"

echo "${TIMESTAMP}|${AGENT_TYPE}|${SESSION_ID}" >> "$LOG_DIR/agent-usage.log"
exit 0
