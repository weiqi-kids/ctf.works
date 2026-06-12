#!/usr/bin/env bash
# run.sh — defense-recipe 固定運行流程(輪詢迴圈)
#
# 對齊 spec §2.D 範本與 topology.yml 的 round_time:
#   while true; 每輪起一個「非互動防禦 agent」對本機三服務做巡檢+修補,
#   然後 sleep $ROUND_INTERVAL,進入下一輪。
#
# 角色:這台是 vulnbox(ROLE D 防禦主機)。本腳本是常駐守護的外殼,
#       真正的「看懂漏洞→最小 diff 堵→self_verify→回滾→記 playbook」由 agent 依 PROMPT.md 執行。
#
# ── 可攜性 ──
#   整個 defense-recipe/ 資料夾搬到任一 vulnbox,設好前置(claude CLI、python3/requests、curl/jq、
#   gcc/make for vault),跑 ./run.sh 即開始守。詳見 README.md。
#
# ── 注意:真實多 round 迴圈需 ForcAD + VM 環境才完整跑(留部署期)。──
#   本輪(本機建置)結構正確、可 dry-run;self_verify 可獨立驗證「洞偵測 / SLA 檢查」。
#   用 DRY_RUN=1 可跑「只巡檢、不真的起 agent」的乾跑,驗證迴圈骨架。
set -u

# ── 路徑 ──
RECIPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPT_FILE="${RECIPE_DIR}/PROMPT.md"
PLAYBOOK_FILE="${RECIPE_DIR}/playbook.md"
VERIFY_DIR="${RECIPE_DIR}/self_verify"

# ── 設定(對齊 topology.yml: forcad.round_time=60s)──
# 部署時請讓 ROUND_INTERVAL 對齊計分機 round_time,使每 round 至少巡檢一次。
ROUND_INTERVAL="${ROUND_INTERVAL:-60}"     # 秒;對齊 topology.yml round_time
AGENT_CMD="${AGENT_CMD:-claude}"           # 非互動 agent CLI(可換成其他模型 runner)
DRY_RUN="${DRY_RUN:-0}"                     # 1=不起 agent,只跑巡檢(self_verify),驗迴圈骨架
MAX_ROUNDS="${MAX_ROUNDS:-0}"              # 0=無限;>0 跑指定輪數後停(測試用)
LOG_DIR="${LOG_DIR:-${RECIPE_DIR}/logs}"

mkdir -p "$LOG_DIR"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# 單輪:起一個非互動 agent,把 PROMPT.md 當系統提示,讓它對三服務巡檢+修補。
# agent 內部會自行呼叫 self_verify 並在不過時回滾、把結果 append 進 playbook.md。
run_agent_round() {
  local round="$1"
  local round_log="${LOG_DIR}/round_${round}.log"

  if [ "$DRY_RUN" = "1" ]; then
    log "round ${round}: DRY_RUN — 跳過 agent,直接跑 self_verify/run_all.sh 當巡檢"
    bash "${VERIFY_DIR}/run_all.sh" 2>&1 | tee "$round_log"
    return "${PIPESTATUS[0]}"
  fi

  # 非互動模式把 PROMPT.md 當系統提示;這裡用 claude CLI 的 -p(print/非互動)為例。
  # 不同 runner 旗標不同,部署時依實際 CLI 調整(見 README「前置/agent runner」)。
  local task="現在是第 ${round} 輪巡檢。請依系統提示對本機 notes/filelocker/vault 三服務:
1) 跑 self_verify 巡檢(${VERIFY_DIR}/run_all.sh)確認各洞是否已堵、SLA 是否正常;
2) 對還開著的洞出最小 diff 修補(堵法見 ${PLAYBOOK_FILE});
3) 修補後重跑對應 self_verify,兩條(exploit 失敗 + 合法功能通過)都過才接受,否則回滾;
4) 把本輪擋下/沒擋下什麼 append 進 ${PLAYBOOK_FILE}。
工作目錄:服務碼在 ${RECIPE_DIR}/../../services/。"

  log "round ${round}: 起非互動 agent(${AGENT_CMD})"
  if command -v "$AGENT_CMD" >/dev/null 2>&1; then
    "$AGENT_CMD" -p "$task" --append-system-prompt "$(cat "$PROMPT_FILE")" \
      >"$round_log" 2>&1
    local rc=$?
    log "round ${round}: agent 結束(rc=${rc}),log=${round_log}"
    return "$rc"
  else
    log "round ${round}: 找不到 agent CLI '${AGENT_CMD}' — 降級為 DRY_RUN 巡檢(僅 self_verify)"
    bash "${VERIFY_DIR}/run_all.sh" 2>&1 | tee "$round_log"
    return "${PIPESTATUS[0]}"
  fi
}

log "defense-recipe run.sh 啟動。ROUND_INTERVAL=${ROUND_INTERVAL}s DRY_RUN=${DRY_RUN} AGENT_CMD=${AGENT_CMD}"
log "PROMPT=${PROMPT_FILE}"
log "self_verify=${VERIFY_DIR}/run_all.sh"

round=0
while true; do
  round=$((round + 1))
  log "════════ ROUND ${round} 開始 ════════"

  run_agent_round "$round" || log "round ${round}: 本輪回報非零(有洞未堵或 self_verify FAIL,詳見 log)"

  if [ "$MAX_ROUNDS" -gt 0 ] && [ "$round" -ge "$MAX_ROUNDS" ]; then
    log "達到 MAX_ROUNDS=${MAX_ROUNDS},停止迴圈。"
    break
  fi

  log "round ${round}: sleep ${ROUND_INTERVAL}s 後進入下一輪"
  sleep "$ROUND_INTERVAL"
done

# ─────────────────────────────────────────────────────────────────────────────
# systemd 常駐(部署期)— 把本配方放在 vulnbox,讓 run.sh 開機自啟、崩潰自動重啟:
#
#   1) 把 defense-recipe/ 放到 /opt/defense-recipe(或任一固定路徑)。
#   2) 建 /etc/systemd/system/defense-recipe.service:
#
#      [Unit]
#      Description=A/D CTF defense-recipe guardian loop
#      After=network-online.target
#      Wants=network-online.target
#
#      [Service]
#      Type=simple
#      WorkingDirectory=/opt/defense-recipe
#      Environment=ROUND_INTERVAL=60
#      Environment=AGENT_CMD=claude
#      # 若要先乾跑驗骨架:Environment=DRY_RUN=1
#      ExecStart=/opt/defense-recipe/run.sh
#      Restart=always
#      RestartSec=5
#      # 建議用低權限使用者跑,並限制只能改 services/ 內檔
#      User=defender
#
#      [Install]
#      WantedBy=multi-user.target
#
#   3) systemctl daemon-reload && systemctl enable --now defense-recipe
#      journalctl -u defense-recipe -f   # 看即時日誌
#
# tmux 替代(臨時常駐):tmux new -s defense './run.sh'  → Ctrl-b d 卸離;tmux a -t defense 回看。
# ─────────────────────────────────────────────────────────────────────────────
