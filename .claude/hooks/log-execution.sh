#!/usr/bin/env bash
# Log agent usage for tracking
# Hook: SubagentStop

LOG_DIR="$(dirname "$0")/../logs"
mkdir -p "$LOG_DIR"

echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"agent\":\"${AGENT_TYPE:-unknown}\",\"session\":\"${SESSION_ID:-unknown}\"}" >> "$LOG_DIR/agent-usage.log"

exit 0
