#!/usr/bin/env bash
# run_all.sh — 一次跑完三服務的 self_verify
#
# 逐服務跑 <svc>_verify.sh,各自判定「exploit 失敗 + 合法功能通過」。
# 任一服務 FAIL → 整體退出碼非 0(防禦 agent 據此知道哪個服務需回滾)。
#
# 用法:run_all.sh
#   可用環境變數覆寫各服務 host/port:
#     NOTES_HOST/NOTES_PORT (預設 127.0.0.1/8080)
#     FLOCK_HOST/FLOCK_PORT (預設 127.0.0.1/9090)
#     VAULT_HOST/VAULT_PORT (預設 127.0.0.1/10000)
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NOTES_HOST="${NOTES_HOST:-127.0.0.1}"; NOTES_PORT="${NOTES_PORT:-8080}"
FLOCK_HOST="${FLOCK_HOST:-127.0.0.1}"; FLOCK_PORT="${FLOCK_PORT:-9090}"
VAULT_HOST="${VAULT_HOST:-127.0.0.1}"; VAULT_PORT="${VAULT_PORT:-10000}"

overall=0
declare -a RESULTS

run_one() {
  local name="$1"; shift
  echo "────────────────────────────────────────────────────────"
  if bash "$@"; then
    RESULTS+=("$name: PASS")
  else
    RESULTS+=("$name: FAIL")
    overall=1
  fi
  echo
}

run_one "notes"      "${DIR}/notes_verify.sh"      "$NOTES_HOST" "$NOTES_PORT"
run_one "filelocker" "${DIR}/filelocker_verify.sh" "$FLOCK_HOST" "$FLOCK_PORT"
run_one "vault"      "${DIR}/vault_verify.sh"      "$VAULT_HOST" "$VAULT_PORT"

echo "════════════════════ self_verify 總結 ════════════════════"
for r in "${RESULTS[@]}"; do echo "  $r"; done
echo "OVERALL: $([ "$overall" -eq 0 ] && echo 'ALL PASS（三服務洞已堵且 SLA 正常）' || echo 'HAS FAIL（有服務需回滾或洞未堵）')"
exit "$overall"
