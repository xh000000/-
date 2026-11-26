"""本地开发服务器：静态页面 + /api 代理，模拟 Nginx 的职责。

生产由 frontend 容器内的 Nginx 承担同样工作；本脚本仅用于开发调试，
标准库实现，无第三方依赖。浏览器只访问一个地址，前后端同源，
Cookie 与「Origin / Host 同源」校验都能正常通过。

    python dev.py                    # 页面 + 代理，后端需另开
    python dev.py --with-backend     # 一条命令：拉起本地后端 + 页面 + 代理
    DEV_PORT=9000 python dev.py      # 换页面端口

环境变量：
    DEV_PORT    页面端口，默认 8090
    API_HOST    后端地址，默认 127.0.0.1
    API_PORT    后端端口，默认 8080
    DATA_DIR    仅 --with-backend 时透传给后端，默认后端自身 data 目录
"""
import atexit
import http.server
import os
import posixpath
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 生产形态：Vite 构建产物 frontend/dist 由 Nginx 托管。本地默认也跑这份产物，
# 与线上路径（history 路由、/assets 指纹文件）完全一致。
_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
ROOT = os.getenv('STATIC_DIR') or (_DIST if os.path.isdir(_DIST) else os.path.join(BASE_DIR, 'frontend'))
API_HOST = os.getenv('API_HOST', '127.0.0.1')
API_PORT = os.getenv('API_PORT', '8080')
API_BASE = 'http://%s:%s' % (API_HOST, API_PORT)

MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
}

HOP = {'host', 'connection', 'content-length', 'transfer-encoding', 'keep-alive', 'accept-encoding'}


class DevHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'research-dev/1.0'

    def log_message(self, fmt, *args):
        print('%s %s' % (self.command, self.path), flush=True)

    def proxy(self, method):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        # 与 Nginx 的 proxy_set_header Host $http_host 保持一致：后端按 Origin 与 Host 同源做 CSRF 校验，
        # 改写成后端地址会让浏览器发来的 Origin 对不上，POST 一律被判为跨站请求。
        headers['Host'] = self.headers.get('Host', '')
        headers['X-Forwarded-For'] = self.client_address[0]
        headers['X-Forwarded-Proto'] = 'http'
        request = urllib.request.Request(API_BASE + self.path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP:
                        self.send_header(key, value)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            for key, value in error.headers.items():
                if key.lower() not in HOP:
                    self.send_header(key, value)
        except urllib.error.URLError as error:
            payload = ('{"error":"后端未启动：%s"}' % error.reason).encode()
            self.send_response(502)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_file(self):
        raw = urllib.parse.unquote(self.path.split('?')[0].split('#')[0]).replace('\\', '/')
        parts = [part for part in raw.split('/') if part not in ('', '.')]
        if '..' in parts or not parts:
            parts = ['index.html']
        elif not posixpath.splitext(parts[-1])[1]:
            # history 路由：/reports、/config/flows 之类没有扩展名，一律回落到 SPA 入口
            parts = ['index.html']
        target = os.path.normpath(os.path.join(ROOT, *parts))
        if target.startswith(os.path.join(ROOT, '..')) or not target.startswith(ROOT):
            self.send_error(404, 'Not Found')
            return
        if not os.path.isfile(target):
            self.send_error(404, 'Not Found')
            return
        with open(target, 'rb') as handle:
            payload = handle.read()
        self.send_response(200)
        self.send_header('Content-Type', MIME.get(os.path.splitext(target)[1].lower(), 'application/octet-stream'))
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self.proxy('GET')
        return self.serve_file()

    def do_POST(self):
        if self.path.startswith('/api/'):
            return self.proxy('POST')
        self.send_error(405, 'Method Not Allowed')

    def do_PUT(self):
        if self.path.startswith('/api/'):
            return self.proxy('PUT')
        self.send_error(405, 'Method Not Allowed')


def api_ready(timeout=0.6):
    try:
        with urllib.request.urlopen(API_BASE + '/api/bootstrap', timeout=timeout):
            return True
    except Exception:
        return False


def start_backend(log_path=None):
    server = os.path.join(BASE_DIR, 'backend', 'server.py')
    if not os.path.isfile(server):
        raise SystemExit('未找到后端入口：' + server)
    env = dict(os.environ, HOST=API_HOST, PORT=API_PORT)
    env.pop('API_ONLY', None)
    # log_path 给了就把后端的 stdout/stderr 落到文件，托管环境里拿不到子进程输出，
    # 排查启动失败只能靠它。
    sink = open(log_path, 'ab', buffering=0) if log_path else None
    try:
        process = subprocess.Popen([sys.executable, server], cwd=os.path.join(BASE_DIR, 'backend'), env=env,
                                   stdout=sink or None, stderr=subprocess.STDOUT if sink else None)
    finally:
        if sink:
            sink.close()
    atexit.register(lambda: process.poll() is None and process.terminate())
    # 用 SQLite 时后端 2 秒内就能起来；连远程库（Neon / 云数据库）时，初始化要对
    # 21 张表逐张做列检查，每张一个网络往返，十几秒是正常的，所以超时放到 60 秒。
    deadline = time.time() + float(os.getenv('BACKEND_START_TIMEOUT', '60'))
    while time.time() < deadline:
        if api_ready(0.4):
            return process
        if process.poll() is not None:
            raise SystemExit('后端启动失败，退出码 %s' % process.returncode)
        time.sleep(0.25)
    # 超时说明后端还在初始化（远程库常见），但不能留着它再起一个新的，否则会越滚越多
    if process.poll() is None:
        process.terminate()
    raise SystemExit('后端 %s 秒内未就绪：%s' % (os.getenv('BACKEND_START_TIMEOUT', '60'), API_BASE))


if __name__ == '__main__':
    port = int(os.getenv('DEV_PORT', '8090'))
    if not os.path.isdir(ROOT):
        raise SystemExit('未找到静态目录：' + ROOT)
    if not os.path.isfile(os.path.join(ROOT, 'index.html')):
        raise SystemExit('静态目录缺少 index.html，请先在 frontend/ 执行 npm install && npm run build（或开发时用 npm run dev）')

    if '--with-backend' in sys.argv[1:]:
        if api_ready():
            print('后端已在运行，复用 %s' % API_BASE, flush=True)
        else:
            print('启动本地后端 %s …' % API_BASE, flush=True)
            start_backend()
            print('后端就绪', flush=True)

    print('dev page:  http://127.0.0.1:%d' % port, flush=True)
    print('static:    %s' % ROOT, flush=True)
    print('api proxy: %s' % API_BASE, flush=True)
    try:
        http.server.ThreadingHTTPServer(('127.0.0.1', port), DevHandler).serve_forever()
    except KeyboardInterrupt:
        pass
