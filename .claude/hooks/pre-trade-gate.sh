#!/usr/bin/env bash
# 매수/매도 요청 시 Tax & Compliance 경유 강제
# PreToolUse:Agent 훅으로 실행됨
INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.tool_input.prompt // ""')

TRADE_PATTERNS=("매수" "매도" "진입" "청산" "buy" "sell" "trade" "enter" "exit")
for pattern in "${TRADE_PATTERNS[@]}"; do
  if echo "$PROMPT" | grep -qi "$pattern"; then
    echo "INFO: 매수/매도 감지 — Tax & Compliance 경유를 권장합니다." >&2
    break
  fi
done
exit 0
