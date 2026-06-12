#!/usr/bin/env bash
# notes_verify.sh — notes 服務(IDOR)補丁驗證
#
# 兩條都過才算「補丁成立」,否則回非零(防禦 agent 據此回滾):
#   (1) 合法功能(模擬 checker):register/login → POST /note → GET 自己的 note 應 200 且 body 正確
#   (2) exploit 應失敗:另一帳號 GET /note?id=<victim note_id> 應「偷不到」(被 403,或拿不到 flag)
#
# 用法:notes_verify.sh [HOST] [PORT]
#   HOST 預設 127.0.0.1、PORT 預設 8080。
# 退出碼:0=兩條都過(補丁 OK / 洞已堵且 SLA 正常);非 0=有 FAIL(需回滾或洞未堵)。
set -u

HOST="${1:-127.0.0.1}"
PORT="${2:-8080}"
BASE="http://${HOST}:${PORT}"
SVC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../services/notes" 2>/dev/null && pwd)"
EXPLOIT="${SVC_DIR}/exploit.py"

# 唯一 flag(用時間戳避免跨輪撞值)
FLAG="FLAG_NOTES_$(date +%s)_$$"
VICTIM="victim_$$_$(date +%s)"
VPASS="vp_$$"

pass=0; fail=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $1"; fail=$((fail+1)); }

echo "== notes_verify @ ${BASE} =="

JAR="$(mktemp -t notesjar.XXXXXX)"
trap 'rm -f "$JAR"' EXIT

# --- (1) 合法功能:種一篇 victim 的 note(=flag),並驗證 victim 自己讀得回 ---
curl -s -c "$JAR" -X POST "${BASE}/register" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${VICTIM}\",\"p\":\"${VPASS}\"}" >/dev/null
curl -s -c "$JAR" -X POST "${BASE}/login" -H 'Content-Type: application/json' \
     -d "{\"u\":\"${VICTIM}\",\"p\":\"${VPASS}\"}" >/dev/null

CREATE_RESP="$(curl -s -b "$JAR" -X POST "${BASE}/note" -H 'Content-Type: application/json' \
     -d "{\"body\":\"${FLAG}\"}")"
NOTE_ID="$(echo "$CREATE_RESP" | jq -r '.note_id // empty' 2>/dev/null)"

if [ -z "$NOTE_ID" ]; then
  bad "合法功能:POST /note 沒回 note_id(resp=${CREATE_RESP}) — 服務可能 DOWN"
  echo "RESULT: FAIL (PASS=${pass} FAIL=${fail})"; exit 1
fi

# victim 自己用 GET /note?id 讀回(合法擁有者讀取必須成功)
OWN_READ="$(curl -s -b "$JAR" "${BASE}/note?id=${NOTE_ID}")"
OWN_BODY="$(echo "$OWN_READ" | jq -r '.body // empty' 2>/dev/null)"
if [ "$OWN_BODY" = "$FLAG" ]; then
  ok "合法功能:擁有者 GET /note?id=${NOTE_ID} 讀回正確 body"
else
  bad "合法功能:擁有者讀自己的 note 失敗(resp=${OWN_READ}) — 補丁可能誤傷 SLA"
fi

# victim 用 GET /notes 也要列得到(checker GET 走這裡)
LIST="$(curl -s -b "$JAR" "${BASE}/notes")"
if echo "$LIST" | jq -e --arg f "$FLAG" '.notes[]? | select(.body==$f)' >/dev/null 2>&1; then
  ok "合法功能:GET /notes 列出自己的 note(checker GET 路徑正常)"
else
  bad "合法功能:GET /notes 沒列出自己的 note(resp=${LIST})"
fi

# --- (2) exploit 應失敗:用攻擊者帳號跑 IDOR exploit,期望偷不到 flag ---
STOLEN="$(python3 "$EXPLOIT" "$HOST" "$PORT" "$NOTE_ID" 2>/dev/null)"
if echo "$STOLEN" | grep -qF "$FLAG"; then
  bad "IDOR 未堵:exploit 偷到了 flag(node_id=${NOTE_ID})"
  echo "        exploit 輸出含 flag:$(echo "$STOLEN" | grep -F "$FLAG" | head -1)"
else
  ok "IDOR 已堵:exploit 偷不到 flag(GET /note 被擋或非擁有者拒絕)"
fi

echo "RESULT: $([ "$fail" -eq 0 ] && echo PASS || echo FAIL) (PASS=${pass} FAIL=${fail})"
[ "$fail" -eq 0 ]
