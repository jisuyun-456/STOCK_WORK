# Disaster Recovery Runbook

STOCK_WORK Paper Trading 시스템의 장애 복구 절차. `run_cycle.py` 가 매 사이클 종료 시 `state/backup/YYYY-MM-DD/` 에 주요 state 파일을 스냅샷으로 저장한다.

---

## 시나리오 1: `portfolios.json` 손상

**증상**: `run_cycle.py` 실행 시 `json.JSONDecodeError` 또는 `[load_portfolios] WARNING: 메인 파일 손상` 로그 출력.

**자동 복구**: `load_portfolios()` 가 `state/portfolios.backup.json` (매 사이클 pre-write 복사본) 에서 자동 복구.

**수동 복구 (자동 복구 실패 시)**:
1. 가장 최근 스냅샷 확인: `ls state/backup/ | sort -r | head -5`
2. 복구 대상 선택 후 복사: `cp state/backup/YYYY-MM-DD/portfolios.json state/portfolios.json`
3. inception NAV 검증: `python -c "import json; print(json.load(open('state/portfolios.json'))['inception'])"`
4. dry-run 1회: `python run_cycle.py --phase all --dry-run`
5. 정상 확인 후 live 복귀.

**주의**: 복구 대상은 **가장 최근 정상 사이클 스냅샷**. 손상 당일 스냅샷은 손상된 파일을 포함할 수 있으므로 전날 것을 우선 시도.

---

## 시나리오 2: Alpaca API 키 분실/노출

**증상**: `[CRITICAL] Alpaca 연결 실패 — BUY 시그널 전면 차단` 로그, 또는 API 키가 git 히스토리에 노출되었다는 보안 경고.

**즉시 조치**:
1. **Alpaca 대시보드에서 기존 키 즉시 revoke** (https://app.alpaca.markets/paper/dashboard/overview)
2. 새 API 키 발급 (Paper Trading)
3. `.env` 또는 GitHub Secrets 업데이트:
   - 로컬: `.env` 에 `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` 갱신
   - CI: GitHub repo → Settings → Secrets → `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` 갱신
4. 노출 여부 확인: `git log -p | grep -i "alpaca" | grep -i "key"` (히스토리 스캔)
5. 노출되었다면: `git filter-repo` 또는 BFG Repo-Cleaner 로 히스토리 정리 + force-push (**팀 사전 공지 필수**)

**검증**: `python -c "from execution.alpaca_client import get_account_info; print(get_account_info())"`

---

## 시나리오 3: GitHub Actions 실패 (사이클 미실행)

**증상**: `trading-cycle.yml` 워크플로우가 하루 이상 실패, 포트폴리오가 정체됨.

**원인 분류**:
- **네트워크**: `state/network_down.flag` 존재 → 외부 API DNS 실패. hosts 파일/VPN 확인.
- **데이터 품질**: `state/degraded_count.json` 의 `consecutive ≥ 2` → yfinance 또는 데이터 소스 장애. `python run_cycle.py --phase data` 로 단독 실행하여 원인 파악.
- **코드 오류**: Actions 로그에서 `Traceback` 확인. 로컬에서 동일 버전 재현 후 수정.

**복구 단계**:
1. Actions 로그 확인: `gh run list --workflow=trading-cycle.yml --limit 5`
2. 최신 실패 로그: `gh run view <run-id> --log-failed`
3. 로컬 수정 + 테스트: `python run_cycle.py --phase all --dry-run`
4. 수정 커밋 푸시 → Actions 재실행: `gh workflow run trading-cycle.yml`
5. 누락된 사이클 백필: 일반적으로 **백필 금지** (중복 주문 위험). Paper 환경이므로 다음 사이클부터 정상 동작이면 충분.

**긴급 수동 실행**: `python run_cycle.py --phase all` (로컬에서 LIVE 모드 직접 실행)

---

## 공통 사전 점검 (월 1회)

- [ ] `state/backup/` 디렉터리 용량 확인 → 90일 이전 스냅샷 아카이브 또는 삭제
- [ ] `state/audit_log.jsonl` 용량 확인 → 분기별로 `state/backup/audit_YYYY-Q.jsonl.gz` 로 아카이브 (append-only 원칙 유지)
- [ ] Alpaca API 키 만료일 확인
- [ ] `python scripts/universe_audit.py --dry-run` 으로 유니버스 무결성 점검
