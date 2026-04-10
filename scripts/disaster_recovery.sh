#!/usr/bin/env bash
# STOCK_WORK disaster recovery helper — state snapshot + retention.
#
# run_cycle.py already performs automatic backups via _backup_state_files() at
# the end of each cycle. This script is a manual companion for:
#   1. Ad-hoc full snapshots (before risky ops)
#   2. Retention cleanup (keeps last 90 days by default)
#   3. Restore helper (lists available snapshots)
#
# Usage:
#   ./scripts/disaster_recovery.sh snapshot          # Ad-hoc backup now
#   ./scripts/disaster_recovery.sh cleanup [days]    # Prune snapshots older than N days (default 90)
#   ./scripts/disaster_recovery.sh list              # List available snapshots newest first

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/state"
BACKUP_DIR="${STATE_DIR}/backup"

cmd="${1:-snapshot}"

case "${cmd}" in
  snapshot)
    today="$(date -u +%Y-%m-%d)"
    dest="${BACKUP_DIR}/${today}"
    mkdir -p "${dest}"
    count=0
    for f in "${STATE_DIR}"/*.json "${STATE_DIR}"/audit_log.jsonl; do
      [ -e "${f}" ] || continue
      cp -p "${f}" "${dest}/"
      count=$((count + 1))
    done
    echo "[backup] ${count} files → ${dest}"
    ;;

  cleanup)
    days="${2:-90}"
    if [ ! -d "${BACKUP_DIR}" ]; then
      echo "[cleanup] no backup dir at ${BACKUP_DIR}"
      exit 0
    fi
    # Retain last N days of per-date snapshots
    removed=0
    cutoff_ts="$(date -u -d "${days} days ago" +%s 2>/dev/null || date -u -v-"${days}"d +%s)"
    for d in "${BACKUP_DIR}"/*/; do
      [ -d "${d}" ] || continue
      dir_name="$(basename "${d}")"
      # Expect YYYY-MM-DD
      if [[ "${dir_name}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        dir_ts="$(date -u -d "${dir_name}" +%s 2>/dev/null || date -u -jf %Y-%m-%d "${dir_name}" +%s)"
        if [ "${dir_ts}" -lt "${cutoff_ts}" ]; then
          rm -rf "${d}"
          removed=$((removed + 1))
        fi
      fi
    done
    echo "[cleanup] removed ${removed} snapshots older than ${days} days"
    ;;

  list)
    if [ ! -d "${BACKUP_DIR}" ]; then
      echo "[list] no backup dir at ${BACKUP_DIR}"
      exit 0
    fi
    ls -1 "${BACKUP_DIR}" | sort -r | head -20
    ;;

  *)
    echo "Usage: $0 {snapshot|cleanup [days]|list}" >&2
    exit 1
    ;;
esac
