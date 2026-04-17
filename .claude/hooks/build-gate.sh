#!/bin/bash
# Stop hook: 세션 종료 전 미커밋/테스트 실패 경고
# stdin: {}
python -c "
import json, sys, subprocess

msgs = []

# Check uncommitted changes
r = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
if r.stdout.strip():
    msgs.append('⚠️  미커밋 변경사항 있음 — git add + git commit 후 종료하세요')

# Quick test run (no-header, no traceback — just pass/fail summary)
r2 = subprocess.run(['python', '-m', 'pytest', 'tests/', '-q', '--tb=no', '--no-header'],
                    capture_output=True, text=True)
last = (r2.stdout + r2.stderr).strip().split('\n')[-1]
if 'failed' in last or ('error' in last.lower() and 'warning' not in last.lower()):
    msgs.append(f'⚠️  테스트 실패: {last}')

if msgs:
    print(json.dumps({'systemMessage': chr(10).join(msgs)}))
" 2>/dev/null || true
