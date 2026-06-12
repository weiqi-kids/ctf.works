#!/usr/bin/env python3
"""filelocker 服務的 ForcAD checker(CONTRACTS.md §1 + §2.2)。

- class-based BaseChecker(checklib==0.7.0)。
- check:register/login/PUT 一檔 + GET /file 讀回比對 + GET /files 找得到。
- put :register + login + PUT /file(name=rnd, content=flag),
         public(attack_data)= JSON 字串 {"user": <user>, "name": <name>}。
- get :login(同帳號)+ GET /file?name=<name> 比對 flag。

可重現性:ForcAD 把同一 flag_id 分別傳給 put 與 get;故帳號/密碼/檔名皆由
flag_id 決定性導出,get 才能用同帳號登入並用同檔名合法讀回。
漏洞(path traversal)留給攻擊方,checker 本身只走合法 API。
"""
import hashlib
import json
import sys
import requests
from checklib import *

PORT = 9090  # filelocker 服務埠(契約固定)


def derive_from_flag_id(flag_id):
    """由 flag_id 決定性導出 (帳號, 密碼, 檔名)。put 與 get 算出同一組。"""
    h = hashlib.sha256(flag_id.encode()).hexdigest()
    user = 'u_' + h[:24]
    password = 'p_' + h[24:48]
    name = 'f_' + h[48:64] + '.txt'
    return user, password, name


class CheckMachine:
    """用 filelocker 的合法 wire API 包成 register/login/put_file/get_file。"""

    def __init__(self, checker):
        self.c = checker

    def base(self):
        return f'http://{self.c.host}:{PORT}'

    def session(self):
        return requests.Session()

    def register(self, s, u, p):
        """POST /register;成功 200,帳號重複 409(冪等場景,不算錯)。"""
        r = s.post(f'{self.base()}/register', json={'u': u, 'p': p}, timeout=5)
        if r.status_code not in (200, 409):
            self.c.cquit(Status.MUMBLE, 'register failed',
                         f'register status={r.status_code}')

    def login(self, s, u, p):
        """POST /login;成功後 set-cookie session 寫進 s。"""
        r = s.post(f'{self.base()}/login', json={'u': u, 'p': p}, timeout=5)
        self.c.check_response(r, 'login failed')

    def put_file(self, s, name, content):
        """PUT /file;回 200 {"stored": name}。"""
        r = s.put(f'{self.base()}/file', json={'name': name, 'content': content},
                  timeout=5)
        self.c.check_response(r, 'put file failed')
        data = self.c.get_json(r, 'put file: bad json')
        self.c.assert_eq(data.get('stored'), name, 'put file: stored mismatch',
                         status=Status.MUMBLE)

    def get_file(self, s, name):
        """GET /file?name=<name>;回 200 {"name","content"}。"""
        r = s.get(f'{self.base()}/file', params={'name': name}, timeout=5)
        self.c.check_response(r, 'get file failed')
        return self.c.get_json(r, 'get file: bad json')

    def list_files(self, s):
        """GET /files;回 200 {"files":[...]}(只列自己的)。"""
        r = s.get(f'{self.base()}/files', timeout=5)
        self.c.check_response(r, 'list files failed')
        data = self.c.get_json(r, 'list files: bad json')
        self.c.assert_in('files', data, 'list files: no files field')
        return data['files']


class Checker(BaseChecker):
    vulns: int = 1
    timeout: int = 10
    uses_attack_data: bool = True

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mch = CheckMachine(self)

    def check(self):
        """合法功能跑一輪:註冊→登入→PUT 一檔→GET 讀回比對→/files 找得到。"""
        s = self.mch.session()
        u, p = rnd_string(12), rnd_string(12)
        name = rnd_string(16) + '.txt'
        content = rnd_string(40)
        self.mch.register(s, u, p)
        self.mch.login(s, u, p)
        self.mch.put_file(s, name, content)
        got = self.mch.get_file(s, name)
        self.assert_eq(got.get('content'), content, 'file content mismatch',
                       status=Status.MUMBLE)
        files = self.mch.list_files(s)
        self.assert_in(name, files, 'file not in /files list',
                       status=Status.MUMBLE)
        self.cquit(Status.OK)

    def put(self, flag_id, flag, vuln):
        """種 flag:flag_id 導出帳密/檔名,PUT /file(content=flag)。

        public(attack_data)= JSON 字串 {"user","name"};
        攻擊方 GET /file?name=../<user>/<name> 即可 path traversal 偷 flag。
        """
        user, password, name = derive_from_flag_id(flag_id)
        s = self.mch.session()
        self.mch.register(s, user, password)
        self.mch.login(s, user, password)
        self.mch.put_file(s, name, flag)
        public = json.dumps({'user': user, 'name': name})
        self.cquit(Status.OK, public)

    def get(self, flag_id, flag, vuln):
        """取 flag:flag_id 導出同帳密/檔名,登入後合法 GET /file 比對。"""
        user, password, name = derive_from_flag_id(flag_id)
        s = self.mch.session()
        self.mch.register(s, user, password)
        self.mch.login(s, user, password)
        got = self.mch.get_file(s, name)
        self.assert_eq(got.get('content'), flag, 'flag mismatch',
                       status=Status.CORRUPT)
        self.cquit(Status.OK)


if __name__ == '__main__':
    c = Checker(sys.argv[2])
    try:
        c.action(sys.argv[1], *sys.argv[3:])
    except c.get_check_finished_exception():
        cquit(Status(c.status), c.public, c.private)
