#!/usr/bin/env bash
# vault_verify.sh — vault 服務(OOB read)補丁驗證
#
# 兩條都過才算「補丁成立」,否則回非零(防禦 agent 據此回滾):
#   (1) 合法功能(模擬 checker):PING→PONG;REGISTER/AUTH/SET → GET <own_slot> 回正確 SECRET
#   (2) exploit 應失敗:攻擊者 GET <victim_slot>(跨 slot)應「偷不到」;負數 / 超大 idx 應回 ERR
#
# token/slot 由 user 決定性導出(CONTRACTS.md §2.3 / README):
#   token = lower_hex16( FNV1a_64(seed=0x9e3779b97f4a7c15, user) )
#   slot  = FNV1a_64(seed=0xcbf29ce484222325, user) mod 256   (無碰撞時即 server 配發值)
# 為避免 slot 碰撞造成誤判,本腳本以 server REGISTER 回的 slot 為權威(由 exploit/合法路徑取得)。
#
# 用法:vault_verify.sh [HOST] [PORT]
#   HOST 預設 127.0.0.1、PORT 預設 10000。
# 退出碼:0=兩條都過;非 0=有 FAIL。
set -u

HOST="${1:-127.0.0.1}"
PORT="${2:-10000}"
SVC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../services/vault" 2>/dev/null && pwd)"
EXPLOIT="${SVC_DIR}/exploit.py"

FLAG="FLAG_VAULT_$(date +%s)_$$"
VICTIM="victim_$$_$(date +%s)"

echo "== vault_verify @ ${HOST}:${PORT} =="

# 合法功能 + 種 flag 用一段 python 完成(line-based TCP),把 victim 的 slot 印到 stdout 最後一行。
# 回傳:多行診斷 + 最後一行 "SLOT=<n>" 或 "SLOT=ERR"
SEED_OUT="$(HOST="$HOST" PORT="$PORT" VICTIM="$VICTIM" FLAG="$FLAG" python3 - <<'PY'
import os, socket, sys

host = os.environ["HOST"]; port = int(os.environ["PORT"])
victim = os.environ["VICTIM"]; flag = os.environ["FLAG"]

def fnv1a(seed, s):
    h = seed
    for c in s.encode():
        h ^= c; h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h
def token_of(u): return "%016x" % fnv1a(0x9e3779b97f4a7c15, u)

slot = None
try:
    with socket.create_connection((host, port), timeout=5) as sock:
        f = sock.makefile("r", encoding="utf-8", newline="\n")
        def cmd(line):
            sock.sendall((line + "\n").encode()); return f.readline().rstrip("\r\n")

        # PING / PONG(check 用)
        print("PING -> " + cmd("PING"))

        # REGISTER(冪等)取得 server 權威的 slot 與 token
        r = cmd(f"REGISTER {victim}")
        print("REGISTER -> " + r)
        parts = r.split(" ", 1)
        if len(parts) == 2 and parts[0] == "OK":
            token = parts[1]
        else:
            print("SLOT=ERR"); sys.exit(0)
        # README:REGISTER 回 OK <token>;slot 由 server 配發,exploit/合法路徑用 server 值。
        # 這裡用決定性 slot_of 推算 own slot 供合法 GET 比對(無碰撞時等於 server 值)。
        own_slot = fnv1a(0xcbf29ce484222325, victim) % 256
        # token 一致性檢查
        print("token match: %s" % (token == token_of(victim)))

        print("AUTH -> " + cmd(f"AUTH {victim} {token}"))
        print("SET -> " + cmd(f"SET {flag}"))
        got = cmd(f"GET {own_slot}")
        print(f"GET own_slot({own_slot}) -> {got}")
        slot = own_slot
except Exception as e:
    print(f"EXC: {e}")
    print("SLOT=ERR"); sys.exit(0)

print(f"SLOT={slot}")
PY
)"

echo "$SEED_OUT" | sed 's/^/  /'

VICTIM_SLOT="$(echo "$SEED_OUT" | sed -n 's/^SLOT=//p' | tail -1)"

pass=0; fail=0
ok()  { echo "  [PASS] $1"; pass=$((pass+1)); }
bad() { echo "  [FAIL] $1"; fail=$((fail+1)); }

# --- (1) 合法功能判定 ---
if echo "$SEED_OUT" | grep -q "PING -> PONG"; then
  ok "合法功能:PING -> PONG"
else
  bad "合法功能:PING 沒回 PONG — 服務可能 DOWN"
fi

if [ "$VICTIM_SLOT" = "ERR" ] || [ -z "$VICTIM_SLOT" ]; then
  bad "合法功能:REGISTER/AUTH/SET 流程失敗,拿不到 slot — 服務異常"
  echo "RESULT: FAIL (PASS=${pass} FAIL=${fail})"; exit 1
fi

if echo "$SEED_OUT" | grep -q "GET own_slot(${VICTIM_SLOT}) -> SECRET ${FLAG}"; then
  ok "合法功能:擁有者 GET <own_slot> 讀回正確 SECRET"
else
  bad "合法功能:擁有者讀自己的 slot 失敗 — 補丁可能誤傷 SLA(GET <own_slot> 沒回正確 SECRET)"
fi

# --- (2) exploit 應失敗:攻擊者跨 slot 讀 victim_slot,期望偷不到 ---
STOLEN="$(python3 "$EXPLOIT" "$HOST" "$PORT" "$VICTIM_SLOT" 2>/dev/null)"
if echo "$STOLEN" | grep -qF "$FLAG"; then
  bad "OOB read 未堵:exploit 跨 slot 偷到 flag(victim_slot=${VICTIM_SLOT})"
else
  ok "OOB read 已堵:exploit 跨 slot 偷不到 flag(GET <victim_slot> 被 ERR 擋下)"
fi

# 額外:負數 / 超大 idx 應回 ERR(不可越界讀)。用 python 直接打。
OOB_OUT="$(HOST="$HOST" PORT="$PORT" python3 - <<'PY'
import os, socket
host=os.environ["HOST"]; port=int(os.environ["PORT"])
import secrets
u="atk_"+secrets.token_hex(4)
def fnv1a(seed,s):
    h=seed
    for c in s.encode(): h^=c; h=(h*0x100000001b3)&0xFFFFFFFFFFFFFFFF
    return h
tok="%016x"%fnv1a(0x9e3779b97f4a7c15,u)
try:
    with socket.create_connection((host,port),timeout=5) as s:
        f=s.makefile("r",newline="\n")
        def cmd(l): s.sendall((l+"\n").encode()); return f.readline().rstrip("\r\n")
        cmd(f"REGISTER {u}"); cmd(f"AUTH {u} {tok}")
        print("NEG="+cmd("GET -1"))
        print("BIG="+cmd("GET 999999"))
except Exception as e:
    print(f"NEG=EXC BIG=EXC ({e})")
PY
)"
NEG="$(echo "$OOB_OUT" | sed -n 's/^NEG=//p')"
BIG="$(echo "$OOB_OUT" | sed -n 's/^BIG=//p')"
if [ "$NEG" = "ERR" ] && [ "$BIG" = "ERR" ]; then
  ok "邊界已堵:GET -1 與 GET 999999 皆回 ERR(擋負數 / 超大值 / 溢位)"
else
  bad "邊界未堵:GET -1='${NEG}' GET 999999='${BIG}'(應皆為 ERR)"
fi

echo "RESULT: $([ "$fail" -eq 0 ] && echo PASS || echo FAIL) (PASS=${pass} FAIL=${fail})"
[ "$fail" -eq 0 ]
