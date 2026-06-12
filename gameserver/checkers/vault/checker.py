#!/usr/bin/env python3
"""vault 服務的 ForcAD checker(CONTRACTS.md §1 + §2.3)。

vault 走 **line-based TCP**(非 HTTP),每行 `\n` 結尾,ASCII。協定:
  REGISTER <user>       -> OK <token>      (配 slot,回 token;冪等)
  AUTH <user> <token>   -> OK / ERR        (成功後 session 綁定 my_slot)
  SET <secret>          -> OK              (需 AUTH;存進 secrets[my_slot])
  GET <idx>             -> SECRET <data>   (需 AUTH;**漏洞**:idx 不檢查邊界)
  PING                  -> PONG            (check 用)

可重現性(對齊 services/vault/README.md §2):
  - user 由 flag_id 決定性導出。
  - token = FNV-1a64(seed=0x9e3779b97f4a7c15, user) 取低 64 位 → 16 hex。
  - slot  = FNV-1a64(seed=0xcbf29ce484222325, user) mod 256(無碰撞時即 server 配發值)。
  put 回傳 public(attack_data)= my_slot(int 字串);
  get 由 flag_id 重建同帳號 AUTH 後 GET <own_slot> 比對;
  攻擊方 GET <victim_slot> 跨 slot 偷 flag。
"""
import hashlib
import socket
import sys
from checklib import *

PORT = 10000  # vault 服務埠(契約固定)
N = 256       # secrets 全域陣列大小(slot 數),對齊 vault.c 的 N

# FNV-1a 64 位元種子,對齊 services/vault/README.md 與 vault.c
TOKEN_SEED = 0x9e3779b97f4a7c15
SLOT_SEED = 0xcbf29ce484222325
FNV_PRIME = 0x100000001b3
MASK64 = 0xFFFFFFFFFFFFFFFF


def fnv1a(seed, s):
    """帶可變種子的 FNV-1a 64 位元雜湊,對齊 README/vault.c 的實作。"""
    h = seed & MASK64
    for c in s.encode():
        h ^= c
        h = (h * FNV_PRIME) & MASK64
    return h


def token_of(user):
    """由 user 決定性導出 16 hex token。"""
    return '%016x' % (fnv1a(TOKEN_SEED, user) & MASK64)


def slot_of(user):
    """由 user 決定性導出 slot(無碰撞時等於 server 配發值)。"""
    return fnv1a(SLOT_SEED, user) % N


def user_from_flag_id(flag_id):
    """由 flag_id 決定性導出 vault user(不含空白,符合協定)。"""
    return 'u' + hashlib.sha256(flag_id.encode()).hexdigest()[:16]


class CheckMachine:
    """用 vault 的 line-based TCP 合法協定包成 register/auth/set/get/ping。"""

    def __init__(self, checker):
        self.c = checker

    def connect(self):
        """開一條到 vault 的 TCP 連線並回傳 (sock, file-like)。"""
        try:
            sock = socket.create_connection((self.c.host, PORT), timeout=5)
        except (OSError, socket.timeout):
            self.c.cquit(Status.DOWN, 'connect failed',
                         f'cannot connect {self.c.host}:{PORT}')
        sock.settimeout(5)
        return sock, sock.makefile('r', encoding='latin-1', newline='\n')

    def cmd(self, sock, f, line):
        """送一行指令並讀一行回應(去掉結尾換行)。"""
        try:
            sock.sendall((line + '\n').encode())
            resp = f.readline()
        except (OSError, socket.timeout):
            self.c.cquit(Status.DOWN, 'io error', f'io error on cmd {line!r}')
        if resp == '':
            self.c.cquit(Status.MUMBLE, 'empty response', f'no resp for {line!r}')
        return resp.rstrip('\n')

    def ping(self, sock, f):
        resp = self.cmd(sock, f, 'PING')
        self.c.assert_eq(resp, 'PONG', 'PING did not PONG', status=Status.MUMBLE)

    def register(self, sock, f, user):
        """REGISTER <user> -> OK <token>;回傳 server 給的 token。"""
        resp = self.cmd(sock, f, f'REGISTER {user}')
        parts = resp.split(' ', 1)
        self.c.assert_eq(parts[0], 'OK', 'REGISTER not OK', status=Status.MUMBLE)
        self.c.assert_eq(len(parts), 2, 'REGISTER missing token',
                         status=Status.MUMBLE)
        return parts[1]

    def auth(self, sock, f, user, token):
        """AUTH <user> <token> -> OK / ERR。"""
        resp = self.cmd(sock, f, f'AUTH {user} {token}')
        self.c.assert_eq(resp, 'OK', 'AUTH failed', status=Status.MUMBLE)

    def set_secret(self, sock, f, secret):
        """SET <secret> -> OK(需先 AUTH)。"""
        resp = self.cmd(sock, f, f'SET {secret}')
        self.c.assert_eq(resp, 'OK', 'SET failed', status=Status.MUMBLE)

    def get_secret(self, sock, f, idx, status=Status.MUMBLE):
        """GET <idx> -> SECRET <data>;回傳 data(可為空字串)。"""
        resp = self.cmd(sock, f, f'GET {idx}')
        parts = resp.split(' ', 1)
        self.c.assert_eq(parts[0], 'SECRET', 'GET not SECRET', status=status)
        return parts[1] if len(parts) == 2 else ''


class Checker(BaseChecker):
    vulns: int = 1
    timeout: int = 10
    uses_attack_data: bool = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mch = CheckMachine(self)

    def check(self):
        """PING + 一輪 register/auth/set/get(自讀)比對。"""
        sock, f = self.mch.connect()
        try:
            self.mch.ping(sock, f)
            # 用隨機 user 跑一輪合法流程(slot/token 皆為 user 的決定性函數)
            user = 'c' + rnd_string(15)
            secret = rnd_string(24)
            token = self.mch.register(sock, f, user)
            # checker 端用相同演算法重算 token,驗證與 server 一致
            self.assert_eq(token, token_of(user), 'token mismatch',
                           status=Status.MUMBLE)
            self.mch.auth(sock, f, user, token)
            self.mch.set_secret(sock, f, secret)
            got = self.mch.get_secret(sock, f, slot_of(user))
            self.assert_eq(got, secret, 'self GET secret mismatch',
                           status=Status.MUMBLE)
            self.cquit(Status.OK)
        finally:
            sock.close()

    def put(self, flag_id, flag, vuln):
        """種 flag:flag_id 導出 user → REGISTER + AUTH + SET flag。

        public(attack_data)= my_slot(int 字串);攻擊方 GET <slot> 跨 slot 偷 flag。
        """
        user = user_from_flag_id(flag_id)
        sock, f = self.mch.connect()
        try:
            token = self.mch.register(sock, f, user)
            self.mch.auth(sock, f, user, token)
            self.mch.set_secret(sock, f, flag)
            # slot 權威來源:由 user 算出(無碰撞時 = server 配發值);冪等故穩定
            slot = slot_of(user)
            self.cquit(Status.OK, str(slot))
        finally:
            sock.close()

    def get(self, flag_id, flag, vuln):
        """取 flag:flag_id 重建同 user,AUTH 後 GET <own_slot> 比對 flag。"""
        user = user_from_flag_id(flag_id)
        sock, f = self.mch.connect()
        try:
            token = self.mch.register(sock, f, user)
            self.mch.auth(sock, f, user, token)
            slot = slot_of(user)
            got = self.mch.get_secret(sock, f, slot, status=Status.CORRUPT)
            self.assert_eq(got, flag, 'flag mismatch', status=Status.CORRUPT)
            self.cquit(Status.OK)
        finally:
            sock.close()


if __name__ == '__main__':
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
