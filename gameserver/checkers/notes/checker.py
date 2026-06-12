#!/usr/bin/env python3
"""notes 服務的 ForcAD checker(CONTRACTS.md §1 + §2.1)。

- class-based BaseChecker(checklib==0.7.0)。
- check:register/login/建讀一篇 note 比對(走合法功能跑一輪)。
- put :register + login + POST /note,public(attack_data)= note_id。
- get :login(同帳號)+ GET /notes 找出含 flag 的 note 比對。

可重現性:ForcAD 把同一個 flag_id 分別傳給 put 與 get(public 不回傳給 get)。
故帳號/密碼由 flag_id 「決定性導出」,get 才能用同帳號登入並透過合法的 /notes 取回 flag。
漏洞(IDOR)留給攻擊方利用,checker 本身只走合法 API。
"""
import hashlib
import sys
import requests
from checklib import *

PORT = 8080  # notes 服務埠(契約固定)


def creds_from_flag_id(flag_id):
    """由 flag_id 決定性導出 (帳號, 密碼)。

    put 與 get 收到同一個 flag_id,因此能算出同一組帳密 → get 可登入同帳號。
    用 sha256 取前綴,加前綴字母確保是合法帳號字串。
    """
    h = hashlib.sha256(flag_id.encode()).hexdigest()
    user = 'u_' + h[:24]
    password = 'p_' + h[24:48]
    return user, password


class CheckMachine:
    """用 notes 的合法 wire API 包成 register/login/post_note/list_notes。"""

    def __init__(self, checker):
        self.c = checker

    def base(self):
        return f'http://{self.c.host}:{PORT}'

    def session(self):
        """每次操作開新的 requests.Session 以承載 session cookie。"""
        return requests.Session()

    def register(self, s, u, p):
        """POST /register;成功 200,帳號重複 409(冪等場景,不算錯)。"""
        r = s.post(f'{self.base()}/register', json={'u': u, 'p': p}, timeout=5)
        # 409 = 帳號已存在(get 那輪會撞到),其餘非 200 才算服務異常
        if r.status_code not in (200, 409):
            self.c.cquit(Status.MUMBLE, 'register failed',
                         f'register status={r.status_code}')

    def login(self, s, u, p):
        """POST /login;成功後 cookie 寫進 session s。"""
        r = s.post(f'{self.base()}/login', json={'u': u, 'p': p}, timeout=5)
        self.c.check_response(r, 'login failed')

    def post_note(self, s, body):
        """POST /note,回傳 note_id(int)。"""
        r = s.post(f'{self.base()}/note', json={'body': body}, timeout=5)
        self.c.check_response(r, 'create note failed')
        data = self.c.get_json(r, 'create note: bad json')
        self.c.assert_in('note_id', data, 'create note: no note_id')
        return data['note_id']

    def get_note(self, s, nid):
        """GET /note?id=<nid>,回傳整篇 note dict(check 自讀用)。"""
        r = s.get(f'{self.base()}/note', params={'id': nid}, timeout=5)
        self.c.check_response(r, 'get note failed')
        return self.c.get_json(r, 'get note: bad json')

    def list_notes(self, s):
        """GET /notes,回傳自己的 note 清單(有擁有者過濾,checker GET 用)。"""
        r = s.get(f'{self.base()}/notes', timeout=5)
        self.c.check_response(r, 'list notes failed')
        data = self.c.get_json(r, 'list notes: bad json')
        self.c.assert_in('notes', data, 'list notes: no notes field')
        return data['notes']


class Checker(BaseChecker):
    vulns: int = 1
    timeout: int = 10
    uses_attack_data: bool = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mch = CheckMachine(self)

    def check(self):
        """合法功能跑一輪:註冊→登入→建一篇→單篇讀回比對→列表也找得到。"""
        s = self.mch.session()
        u, p = rnd_string(12), rnd_string(12)
        body = rnd_string(32)
        self.mch.register(s, u, p)
        self.mch.login(s, u, p)
        nid = self.mch.post_note(s, body)
        # 單篇讀回(自己的 note 本就讀得到)比對 body
        note = self.mch.get_note(s, nid)
        self.assert_eq(note.get('body'), body, 'note body mismatch',
                       status=Status.MUMBLE)
        # /notes 列表也要能找到剛建的這篇(GET 路徑健康度)
        mine = self.mch.list_notes(s)
        found = any(n.get('note_id') == nid for n in mine)
        self.assert_eq(found, True, 'note not in /notes list',
                       status=Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        """種 flag:用 flag_id 導出帳密註冊登入,把 flag 存成一篇 note。

        public(attack_data)= note_id —— 攻擊方 GET /note?id=<nid> 即可偷 flag。
        """
        u, p = creds_from_flag_id(flag_id)
        s = self.mch.session()
        self.mch.register(s, u, p)
        self.mch.login(s, u, p)
        nid = self.mch.post_note(s, flag)
        self.cquit(Status.OK, str(nid))

    def get(self, flag_id, flag, vuln):
        """取 flag:用 flag_id 導出同帳密登入,走合法 /notes 找含 flag 的 note。"""
        u, p = creds_from_flag_id(flag_id)
        s = self.mch.session()
        # 帳號已在 put 那輪建立;這裡只需登入(register 撞 409 也吞掉)
        self.mch.register(s, u, p)
        self.mch.login(s, u, p)
        mine = self.mch.list_notes(s)
        bodies = [n.get('body') for n in mine]
        # /notes 只列自己的 note,checker 走這條合法路徑比對 flag
        self.assert_in(flag, bodies, 'flag not found in own notes',
                       status=Status.CORRUPT)
        self.cquit(Status.OK)


if __name__ == '__main__':
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
