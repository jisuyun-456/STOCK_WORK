#!/usr/bin/env bash
# Block modifications to .env and credential files
# Hook: PreToolUse (Edit|Write)

FILE_PATH="${TOOL_INPUT_FILE_PATH:-}"

case "$FILE_PATH" in
  *.env|*.env.*|*.key|*.pem|*credentials*)
    echo "BLOCKED: Cannot modify sensitive file: $FILE_PATH" >&2
    exit 2  # Hard block
    ;;
esac

exit 0
