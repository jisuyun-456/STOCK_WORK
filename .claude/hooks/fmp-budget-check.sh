#!/usr/bin/env bash
# FMP API 호출 전 일일 사용량 체크
# PreToolUse:Bash 훅으로 실행됨
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

if echo "$COMMAND" | grep -q "fmp\|FMP\|fmp_rate_limiter"; then
  # FMP 관련 명령이면 사용량 체크
  if [ -f "scripts/fmp_rate_limiter.py" ]; then
    USAGE=$(python3 scripts/fmp_rate_limiter.py check 2>/dev/null | tail -1)
    echo "FMP API: $USAGE" >&2
  fi
fi
exit 0
