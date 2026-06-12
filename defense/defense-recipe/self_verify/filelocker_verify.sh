#!/usr/bin/env bash
# filelocker_verify.sh — filelocker 服務(path traversal)補丁驗證
#
# 兩條都過才算「補丁成立」,否則回非零(防禦 agent 據此回滾):
#   (1) 合法功能(模擬 checker):register/login → PUT /file → GET 自己的檔 應 200 且 content 正確
#   (2) exploit 應失敗:攻擊者 GET /file?name=../<victim>/<file> 應「偷不到」(403 / 拿不到 flag)
#       另測 URL 編碼繞過 %2e%2e 變體也要被擋。
#
# 用法:filelocker_verify.sh [HOST] [PORT]
#   HOST 預設 127.0.0.1、PORT 預設 9090。
# 退出碼:0=兩條都過;非 0=有 FAIL。
set -u

HOST="${1:-127.0.0.1}"
PORT="${2:-9090}"
BASE="http://${HOST}:${PORT}"
SVC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../services/filelocker" 2>/dev/null && pwd)"
EXPLOIT="${SVC_DIR}/exploit.py"

FLAG="FLAG_FLOCK_$(date +%s)_$$"
VICTIM="victim_$$_$(date +%s)"
VPASS="vp_$$"
FNAME="flag_$$.txt"

pass=0; fail=0
ok()  { echo "  [PASS] $1"; pass=$((pass+1)); }
bad() { echo "  [FAIL] $1"; fail=$((fail+1)); }

echo "== filelocker_verify @ ${BASE} =="

JAR="$(mktemp -t flockjar.XXXXXX)"
trap 'rm -f "$JAR"' EXIT

# --- (1) 合法功能:victim 存一個檔(=flag),並驗證自己讀得回 ---
curl -s -c "$JAR" -X POST "${BASE}/register" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${VICTIM}\",\"p\":\"${VPASS}\"}" >/dev/null
curl -s -c "$JAR" -X POST "${BASE}/login" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${VICTIM}\",\"p\":\"${VPASS}\"}" >/dev/null

PUT_RESP="$(curl -s -b "$JAR" -X PUT "${BASE}/file" -H 'Content-Type: application/json' \
     -d "{\"name\":\"${FNAME}\",\"content\":\"${FLAG}\"}")"
STORED="$(echo "$PUT_RESP" | jq -r '.stored // empty' 2>/dev/null)"
if [ -z "$STORED" ]; then
  bad "合法功能:PUT /file 沒回 stored(resp=${PUT_RESP}) — 服務可能 DOWN"
  echo "RESULT: FAIL (PASS=${pass} FAIL=${fail})"; exit 1
fi

# victim 自己用合法 name 讀回(同目錄,必須成功)
OWN_READ="$(curl -s -b "$JAR" "${BASE}/file?name=${FNAME}")"
OWN_CONTENT="$(echo "$OWN_READ" | jq -r '.content // empty' 2>/dev/null)"
if [ "$OWN_CONTENT" = "$FLAG" ]; then
  ok "合法功能:擁有者 GET /file?name=${FNAME} 讀回正確 content"
else
  bad "合法功能:擁有者讀自己的檔失敗(resp=${OWN_READ}) — 補丁可能誤傷 SLA"
fi

LIST="$(curl -s -b "$JAR" "${BASE}/files")"
if echo "$LIST" | jq -e --arg n "$FNAME" '.files[]? | select(.==$n)' >/dev/null 2>&1; then
  ok "合法功能:GET /files 列出自己的檔(checker GET 路徑正常)"
else
  bad "合法功能:GET /files 沒列出自己的檔(resp=${LIST})"
fi

# --- (2) exploit 應失敗:攻擊者用 ../<victim>/<file> traversal 讀,期望偷不到 ---
STOLEN="$(python3 "$EXPLOIT" "$HOST" "$VICTIM" "$FNAME" --port "$PORT" 2>/dev/null)"
if echo "$STOLEN" | grep -qF "$FLAG"; then
  bad "path traversal 未堵:exploit 偷到了 flag(../${VICTIM}/${FNAME})"
else
  ok "path traversal 已堵:exploit 偷不到 flag(GET /file 被 403 擋下)"
fi

# 額外:URL 編碼繞過 %2e%2e 變體,直接打一個攻擊者 session 試讀
AJAR="$(mktemp -t flockatk.XXXXXX)"
ATK="atk_$$"
curl -s -c "$AJAR" -X POST "${BASE}/register" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${ATK}\",\"p\":\"x\"}" >/dev/null
curl -s -c "$AJAR" -X POST "${BASE}/login" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${ATK}\",\"p\":\"x\"}" >/dev/null
ENC_RESP="$(curl -s -b "$AJAR" "${BASE}/file?name=%2e%2e%2f${VICTIM}%2f${FNAME}")"
rm -f "$AJAR"
if echo "$ENC_RESP" | grep -qF "$FLAG"; then
  bad "URL 編碼繞過未堵:%2e%2e 變體偷到 flag(resp=${ENC_RESP})"
else
  ok "URL 編碼繞過已堵:%2e%2e 變體偷不到 flag"
fi

echo "RESULT: $([ "$fail" -eq 0 ] && echo PASS || echo FAIL) (PASS=${pass} FAIL=${fail})"
[ "$fail" -eq 0 ]
