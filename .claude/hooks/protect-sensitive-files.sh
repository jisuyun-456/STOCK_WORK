#!/usr/bin/env bash
# 민감 파일 수정 차단 (D3 기술 아키텍트)
# PreToolUse:Edit|Write 훅으로 실행됨
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""')

PATTERNS=(".env" ".env.local" ".env.production" "credentials" ".key" ".pem" "kis_token" "alpha_vantage" "finnhub" "api_secret")
for pattern in "${PATTERNS[@]}"; do
  if [[ "$FILE_PATH" == *"$pattern"* ]]; then
    echo "BLOCK: 민감 파일 수정 차단 — $FILE_PATH" >&2
    echo "환경 변수나 인증 정보는 직접 수정하지 마세요." >&2
    exit 2
  fi
done
exit 0
