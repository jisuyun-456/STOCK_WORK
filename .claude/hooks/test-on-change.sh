#!/bin/bash
# PostToolUse: .py 파일 수정 시 자동 pytest 실행
# stdin: {"tool_name":"Edit","tool_input":{"file_path":"..."}}
python -c "
import json, sys, subprocess
d = json.load(sys.stdin)
f = d.get('tool_input', {}).get('file_path') or ''
if f.endswith('.py'):
    r = subprocess.run(['python', '-m', 'pytest', 'tests/', '-x', '-q', '--tb=line', '--no-header'],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().split('\n')
    print('\n'.join(out[-10:]))
" 2>/dev/null || true
