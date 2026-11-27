"""实时刷新的版本号语义。

前端靠「版本号变了就重新拉快照」工作，所以两条性质必须钉死：
读请求不推进版本号（否则所有在线页面会互相触发刷新，形成风暴）；
写请求成功后一定推进（否则别人永远看不到变化）。

不继承 test_workflow.Workflow：那会把父类的用例一并继承下来，同一个临时库里
先跑完别的用例，setup 就不是首次初始化了。
"""
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class LiveRevision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            cls.port = s.getsockname()[1]
        cls.proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name('server.py'))],
            env={**os.environ, 'DATA_DIR': cls.tmp.name, 'PORT': str(cls.port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f'http://127.0.0.1:{cls.port}/api/'
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + 'bootstrap', timeout=1)
                break
            except Exception:
                time.sleep(.05)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait(timeout=15)
        for _ in range(20):
            try:
                cls.tmp.cleanup()
                break
            except OSError:
                time.sleep(.25)

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, client, path, data=None):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with client.open(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_write_bumps_read_does_not(self):
        admin = self.client()
        self.assertEqual(self.call(admin, 'setup', {'name': 'admin', 'password': '123456'})[0], 200)

        status, state = self.call(admin, 'state')
        self.assertEqual(status, 200)
        self.assertIn('revision', state)
        start = state['revision']

        # 读接口多次调用不应推动版本号
        for _ in range(3):
            self.assertEqual(self.call(admin, 'state')[1]['revision'], start)

        # 一次成功的写操作推进版本号
        self.assertEqual(self.call(admin, 'departments', {'name': '实时刷新测试部'})[0], 200)
        after_write = self.call(admin, 'state')[1]['revision']
        self.assertGreater(after_write, start)

        # 失败的写操作不推进（4xx 不代表数据变了）：用版本冲突稳定构造一次 409
        self.assertEqual(self.call(admin, 'system/menus', {'revision': 999, 'visibility': {}})[0], 409)
        self.assertEqual(self.call(admin, 'state')[1]['revision'], after_write)

        # 后续读取保持稳定
        self.assertEqual(self.call(admin, 'state')[1]['revision'], after_write)


if __name__ == '__main__':
    unittest.main()
