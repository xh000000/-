#!/usr/bin/env python3
"""单端口启动入口（用于云端托管：只暴露 $PORT 一个端口）。

为什么需要这个文件
------------------
线上原本是「Nginx 托管 dist + 反代 /api 到 backend:8080」两个容器。托管平台只给一个
HTTP 端口、且不跑 docker compose，所以这里把两件事合成一个进程对外的服务：

    $PORT  ──▶ 本进程 ──┬── /api/*  → 反代到 127.0.0.1:<后端端口>
                        └── 其他     → 对应静态文件（history 路由回落到 index.html）

静态目录优先用 ``webapp/``（构建产物副本，不带 dist 这个名字，避免上传时被当成构建产物
剔除），其次回落到 ``frontend/dist``，再回落到 ``frontend/``（源码，仅供排查）。

后端端口默认自动挑一个空闲端口，避免与平台注入的 $PORT 撞车；可用 API_PORT 固定。

    PORT=3000 python serve.py
"""
from __future__ import annotations

import http.server
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def load_deploy_env() -> None:
    """读取随项目上传的 .env 中的 DATABASE_URL（托管平台没有注入环境变量的入口）。

    后端仍保持 SKIP_DOTENV=1：它不直接读文件，只认进程环境。这里只放行
    白名单里的键，避免上一次部署遗留的 .env 把端口、静态目录之类的运行时配置
    悄悄改掉；命令行/平台已注入的值优先。

    PROBE_DB_URL 只给 /__status 的诊断用，应用本身不读它 —— 这样可以在不切换
    生产库的前提下，反复试不同连接参数。
    """
    wanted = ('DATABASE_URL', 'PROBE_DB_URL')
    env_file = BASE_DIR / '.env'
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if key in wanted and value.strip() and not os.getenv(key):
            os.environ[key] = value.strip().strip('"').strip("'")


def pick_backend_port(preferred: int = 8080) -> int:
    """优先用固定端口：后端用它拼会话 Cookie 名，端口变了等于全员掉线。"""
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', preferred))
            return preferred
        except OSError:
            pass
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def static_root() -> str:
    explicit = os.getenv('STATIC_DIR')
    if explicit:
        return explicit
    for candidate in ('webapp', 'frontend/dist', 'frontend'):
        path = BASE_DIR / candidate
        if (path / 'index.html').is_file():
            return str(path)
    raise SystemExit('未找到前端产物：请先在 frontend/ 执行 npm install && npm run build，'
                     '并把 dist 复制为 webapp/')


def main() -> None:
    port = int(os.getenv('PORT', '3000'))
    root = static_root()
    load_deploy_env()

    # 数据目录固定到项目内 var/，与上传的目录一致；平台重启后沿用同一份文件。
    os.environ.setdefault('DATA_DIR', str(BASE_DIR / 'var'))
    Path(os.environ['DATA_DIR']).mkdir(parents=True, exist_ok=True)

    os.environ['STATIC_DIR'] = root
    os.environ['API_PORT'] = os.getenv('API_PORT') or str(pick_backend_port())
    os.environ['API_HOST'] = '127.0.0.1'
    os.environ['HOST'] = '127.0.0.1'
    # 托管环境的配置只认平台注入的环境变量。沙箱是增量覆盖的，上一次部署遗留的
    # .env 不会被删掉，让后端读它会把配置悄悄改回旧值（曾经因此一直连旧的数据库）。
    os.environ['SKIP_DOTENV'] = '1'

    sys.path.insert(0, str(BASE_DIR))
    import dev  # noqa: E402  （复用它的静态服务 + /api 反代，避免重复实现）

    log_path = Path(os.environ['DATA_DIR']) / 'backend.log'

    # 不在这里 pkill 旧的 server.py：平台可能同时跑两个 serve 实例（预热 + 正式），
    # 互相杀对方的后端会变成谁都起不来。端口冲突交给 pick_backend_port 处理。

    # 日志按次轮转：不然 /__status 看到的是历次部署混在一起的内容，没法判断这次到底
    # 卡在哪一步。
    try:
        if log_path.is_file():
            log_path.replace(log_path.with_name(log_path.name + '.prev'))
    except OSError:
        pass

    # 先占住端口，再在后台线程里拉后端。
    #
    # 原来是 start_backend() 同步等待（最长 60 秒）之后才监听，连 SQLite 时后端两秒
    # 就绪，看不出问题；一旦库在远程，初始化要做几十次网络往返，平台那边 60 秒内
    # 看不到端口就直接判定启动失败。托管平台的健康检查只看端口通不通，所以顺序必须
    # 反过来：端口立刻可连，/api 在就绪前返回 502，页面本身（静态资源）不受影响。
    class Handler(dev.DevHandler):
        """在静态服务上加一个 /__status，用来在托管环境里看后端到底起没起来。

        托管沙箱拿不到子进程输出，启动失败时只剩「Connection refused」这一句，
        所以把后端日志落到 var/backend.log 并从这儿吐出来。
        """

        def do_GET(self):
            if self.path.split('?', 1)[0] == '/__status':
                return self._status()
            super().do_GET()

        def _status(self):
            tail = ''
            try:
                if log_path.is_file():
                    tail = log_path.read_text('utf-8', 'replace')[-4000:]
            except OSError:
                tail = '(读不到后端日志)'
            url = os.getenv('DATABASE_URL', '')
            if url:
                # 只暴露主机名，连接串里的密码不能出现在响应里
                host = url.split('@', 1)[-1].split('/', 1)[0] if '@' in url else '(已配置)'
                db = 'postgresql://***@' + host
            else:
                db = 'sqlite'
            payload = {
                # 远程库上单次请求可能慢到一两秒，探测超时给宽一点
                'backend_ready': dev.api_ready(3),
                'api_base': dev.API_BASE,
                'database': db,
                'log_tail': tail,
            }
            if 'probe=1' in self.path:
                payload['db_probe'] = self._probe(url)
            if 'probe=2' in self.path:
                payload['net2'] = self._net2()
            if 'probe=3' in self.path:
                payload['db2'] = self._db_probe2()
            if 'probe=4' in self.path:
                payload['db3'] = self._db_probe3()
            if 'probe=5' in self.path:
                payload['db4'] = self._db_probe4(self.path)
            # 选数据库供应商前要先量沙箱到目标机房的真实往返：同一台机器上 ping 通
            # 不代表连得上，跨境链路的抖动只有在这里测才准。目标写死，不接受外部
            # 传入主机名，避免这个诊断口变成端口扫描器。
            if 'net=1' in self.path and os.getenv('NET_PROBE') == '1':
                payload['net'] = self._net_probe()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _probe(url):
            """分别量 DNS 与 TCP 握手，并对 pooler / 直连两种地址做对照。

            Neon 的连接池域名（-pooler）与直连域名可能落在不同节点，跨境链路上
            差别很大，所以两个都测。
            """
            if not url.startswith('postgresql'):
                return {'skipped': 'not postgresql'}
            hostport = url.split('@', 1)[-1].split('/', 1)[0]
            host, _, port = hostport.partition(':')
            port = int(port or 5432)
            result = {}
            for label, target in (('pooled', host), ('direct', host.replace('-pooler.', '.'))):
                entry = {}
                started = time.time()
                try:
                    socket.getaddrinfo(target, port, proto=socket.IPPROTO_TCP)
                    entry['dns_ms'] = int((time.time() - started) * 1000)
                except Exception as exc:
                    entry['dns_error'] = type(exc).__name__
                    result[label] = entry
                    continue
                started = time.time()
                try:
                    with socket.create_connection((target, port), timeout=10):
                        entry['tcp_ms'] = int((time.time() - started) * 1000)
                except Exception as exc:
                    entry['tcp_error'] = type(exc).__name__
                result[label] = entry
            return result

        @staticmethod
        def _db_probe2():
            """在沙箱里用 psycopg 试几种连接参数，定位到底哪一步被断。

            probe=2 已证明 TCP/TLS 都通，所以失败只可能来自参数协商：连接池域名、
            channel_binding、或 db.py 注入的 hostaddr。逐个开关试，看哪个能连上。
            """
            url = os.getenv('PROBE_DB_URL') or ''
            if not url:
                return {'skipped': 'PROBE_DB_URL 未配置'}
            try:
                import psycopg
            except Exception as exc:
                return {'skipped': 'psycopg 未安装：%s' % type(exc).__name__}

            def strip_cb(value: str) -> str:
                return re.sub(r'[?&]channel_binding=[^&]*', '', value)

            direct = url.replace('-pooler.', '.')
            variants = [
                ('as_is', url),
                ('no_channel_binding', strip_cb(url)),
                ('direct_host', direct),
                ('direct_no_channel_binding', strip_cb(direct)),
            ]
            # 复刻 db.py 的 hostaddr 注入：host 保留域名做 TLS 校验，TCP 走固定 IPv4
            try:
                hostport = url.split('@', 1)[-1].split('/', 1)[0]
                host = hostport.partition(':')[0]
                ip = socket.getaddrinfo(host, 5432, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
                variants.append(('with_hostaddr', url + ('&' if '?' in url else '?') + 'hostaddr=' + ip))
            except Exception:
                pass

            out = []
            for name, target in variants:
                entry = {'variant': name}
                started = time.time()
                try:
                    with psycopg.connect(target, connect_timeout=5) as conn:
                        with conn.cursor() as cur:
                            cur.execute('select 1')
                            cur.fetchone()
                    entry['ok'] = True
                except Exception as exc:
                    entry['error'] = ('%s: %s' % (type(exc).__name__, str(exc)))[:180]
                entry['ms'] = int((time.time() - started) * 1000)
                out.append(entry)
            return out

        @staticmethod
        def _db_probe3():
            """验证「自动挑一个可达 IPv4 + hostaddr」方案，用于替换 db.py 的固定取第一个。

            probe=3 里 direct_no_channel_binding 能连上但耗时 5.4 秒，全花在 libpq
            先试 IPv6 再回退；with_hostaddr 直接超时，因为写死的是不可达的那个 IP。
            这里先做 800ms 的 TCP 探活挑最快的 IPv4，再把它塞进 hostaddr。
            """
            url = os.getenv('PROBE_DB_URL') or ''
            if not url:
                return {'skipped': 'PROBE_DB_URL 未配置'}
            url = re.sub(r'[?&]channel_binding=[^&]*', '', url)
            try:
                import psycopg
            except Exception as exc:
                return {'skipped': 'psycopg 未安装：%s' % type(exc).__name__}

            hostport = url.split('@', 1)[-1].split('/', 1)[0]
            host, _, port = hostport.partition(':')
            port = int(port or 5432)
            report = {'hosts': {}}
            for label, target in (('pooled', host), ('direct', host.replace('-pooler.', '.'))):
                entry = {}
                try:
                    infos = socket.getaddrinfo(target, port, socket.AF_INET, socket.SOCK_STREAM)
                except Exception as exc:
                    report['hosts'][label] = {'dns_error': type(exc).__name__}
                    continue
                candidates = []
                for info in infos:
                    ip = info[4][0]
                    if ip in [c[1] for c in candidates]:
                        continue
                    started = time.time()
                    try:
                        with socket.create_connection((ip, port), timeout=0.8):
                            candidates.append((int((time.time() - started) * 1000), ip))
                    except OSError:
                        candidates.append((None, ip))
                entry['candidates_ms'] = candidates
                alive = [c for c in candidates if c[0] is not None]
                if alive:
                    ip = min(alive)[1]
                    entry['picked'] = ip
                    target_url = url.replace(host, target)
                    target_url += ('&' if '?' in target_url else '?') + 'hostaddr=' + ip
                    started = time.time()
                    try:
                        with psycopg.connect(target_url, connect_timeout=8) as conn:
                            with conn.cursor() as cur:
                                cur.execute('select count(*) from users')
                                entry['users'] = cur.fetchone()[0]
                        entry['ok'] = True
                    except Exception as exc:
                        entry['error'] = ('%s: %s' % (type(exc).__name__, str(exc)))[:160]
                    entry['ms'] = int((time.time() - started) * 1000)
                report['hosts'][label] = entry
            return report

        @staticmethod
        def _db_probe4(path=''):
            """对比三种「落地可用的连接策略」，每种跑两轮看稳定性。

            已知：TCP/TLS 都能通，但「写死单个 hostaddr」会干等到超时（那条 IP 上
            会话被断），而 libpq 自己轮询全部地址时能连上、代价是慢。所以真正要
            选的是「谁负责挑地址、怎么快速放弃坏地址」。
            """
            url = os.getenv('PROBE_DB_URL') or ''
            if not url:
                return {'skipped': 'PROBE_DB_URL 未配置'}
            url = re.sub(r'[?&]channel_binding=[^&]*', '', url)
            try:
                import psycopg
            except Exception as exc:
                return {'skipped': 'psycopg 未安装：%s' % type(exc).__name__}

            hostport = url.split('@', 1)[-1].split('/', 1)[0]
            host, _, port = hostport.partition(':')
            port = int(port or 5432)
            direct = host.replace('-pooler.', '.')

            def ipv4s(name):
                try:
                    infos = socket.getaddrinfo(name, port, socket.AF_INET, socket.SOCK_STREAM)
                    out = []
                    for i in infos:
                        if i[4][0] not in out:
                            out.append(i[4][0])
                    return out
                except Exception:
                    return []

            def one_connect(target, timeout):
                started = time.time()
                try:
                    with psycopg.connect(target, connect_timeout=timeout) as conn:
                        with conn.cursor() as cur:
                            cur.execute('select count(*) from users')
                            users = cur.fetchone()[0]
                    return {'ok': True, 'users': users, 'ms': int((time.time() - started) * 1000)}
                except Exception as exc:
                    return {'ok': False, 'ms': int((time.time() - started) * 1000),
                            'error': ('%s: %s' % (type(exc).__name__, str(exc)))[:120]}

            def per_ip_failover(base, name, timeout=5):
                ips = ipv4s(name)
                tries = []
                for ip in ips:
                    part = one_connect(base + ('&' if '?' in base else '?') + 'hostaddr=' + ip,
                                       timeout)
                    part['ip'] = ip
                    tries.append(part)
                    if part['ok']:
                        break
                ok = any(t['ok'] for t in tries)
                return {'ok': ok, 'tries': tries,
                        'ms': sum(t['ms'] for t in tries)}

            def list_hostaddr(base, name, timeout=6):
                ips = ipv4s(name)
                if not ips:
                    return {'ok': False, 'error': 'no ipv4'}
                return one_connect(base + ('&' if '?' in base else '?')
                                   + 'hostaddr=' + ','.join(ips), timeout)

            def plain_roundtrip():
                """连上之后再打三次查询：连接建立能否成功只是第一关，"""
                """链路中途是否会断（之前线上报 SSL SYSCALL EOF）才是能不能用的关键。"""
                started = time.time()
                try:
                    with psycopg.connect(url, connect_timeout=10) as conn:
                        conn_ms = int((time.time() - started) * 1000)
                        qs = []
                        for _ in range(3):
                            t0 = time.time()
                            with conn.cursor() as cur:
                                cur.execute('select count(*) from users')
                                users = cur.fetchone()[0]
                            qs.append(int((time.time() - t0) * 1000))
                        return {'ok': True, 'connect_ms': conn_ms, 'query_ms': qs, 'users': users}
                except Exception as exc:
                    return {'ok': False, 'ms': int((time.time() - started) * 1000),
                            'error': ('%s: %s' % (type(exc).__name__, str(exc)))[:120]}

            def shipped_path():
                """直接跑 backend/db.py 里真正要上线的那个建连函数，避免探针和代码跑偏。"""
                """一次请求只跑一轮：六次重试最坏能到 60 秒，两轮就撞上网关超时。"""
                import sys
                sys.path.insert(0, str(BASE_DIR / 'backend'))
                try:
                    import db as backend_db
                except Exception as exc:
                    return {'ok': False, 'error': 'import backend.db 失败: %s' % type(exc).__name__}
                clean = backend_db._sanitize_pg_url(url)
                started = time.time()
                try:
                    conn = backend_db._bounded_connect(
                        clean.replace('postgresql://', 'postgresql://', 1),
                        float(os.getenv('DB_CONNECT_TIMEOUT', '8')))
                except Exception as exc:
                    return {'ok': False, 'ms': int((time.time() - started) * 1000),
                            'error': ('%s: %s' % (type(exc).__name__, str(exc)))[:140]}
                conn_ms = int((time.time() - started) * 1000)
                try:
                    with conn.cursor() as cur:
                        qs = []
                        for _ in range(3):
                            t0 = time.time()
                            cur.execute('select count(*) from users')
                            users = cur.fetchone()[0]
                            qs.append(int((time.time() - t0) * 1000))
                finally:
                    conn.close()
                return {'ok': True, 'connect_ms': conn_ms, 'query_ms': qs, 'users': users}

            cases = {
                'F': ('shipped_bounded_connect', shipped_path),
                'E': ('pooled_plain_roundtrip', plain_roundtrip),
                'A': ('pooled_per_ip_failover', lambda: per_ip_failover(url, host)),
                'B': ('direct_per_ip_failover', lambda: per_ip_failover(url.replace(host, direct), direct)),
                'C': ('pooled_hostaddr_list', lambda: list_hostaddr(url, host)),
                'D': ('pooled_plain_libpq', lambda: one_connect(url, 10)),
            }
            wanted = re.search(r'case=([ABCDEF])', path)
            keys = [wanted.group(1)] if wanted else list(cases)
            out = []
            for key in keys:
                name, fn = cases[key]
                entry = {'variant': key + '_' + name, 'runs': []}
                for _ in range({'E': 4, 'F': 1}.get(key, 2)):
                    try:
                        entry['runs'].append(fn())
                    except Exception as exc:
                        entry['runs'].append({'ok': False,
                                              'error': '%s: %s' % (type(exc).__name__, str(exc))})
                out.append(entry)
            return out

        def _net2():
            """诊断沙箱出网能力：5432 的 TCP/TLS 与 443 的 HTTPS 分别测，不碰密码。

            Neon 的 5432 在这里曾报 SSL SYSCALL EOF，但同一沙箱访问腾讯云 API 的
            443 正常。要判断是「目标不可达」还是「只放 443」，必须把两种协议拆开。
            """
            host = 'ep-holy-math-a1uaaxs0-pooler.ap-southeast-1.aws.neon.tech'
            direct = host.replace('-pooler.', '.')
            result = {}
            for label, target in (('pooled_5432', host), ('direct_5432', direct)):
                entry = {}
                try:
                    infos = socket.getaddrinfo(target, 5432, proto=socket.IPPROTO_TCP)
                    entry['ips'] = sorted({i[4][0] for i in infos})[:3]
                    started = time.time()
                    sock = socket.create_connection(infos[0][4], timeout=8)
                    entry['tcp_ms'] = int((time.time() - started) * 1000)
                    try:
                        started = time.time()
                        with ssl.create_default_context().wrap_socket(sock, server_hostname=target) as tls:
                            entry['tls_ms'] = int((time.time() - started) * 1000)
                            entry['tls'] = 'ok'
                    except Exception as exc:
                        entry['tls_error'] = '%s: %s' % (type(exc).__name__, str(exc)[:90])
                except Exception as exc:
                    entry['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:90])
                result[label] = entry
            for label, url in (('neon_https', 'https://' + direct + '/sql'),
                               ('qq_https', 'https://www.qq.com/')):
                entry = {}
                try:
                    started = time.time()
                    with urllib.request.urlopen(url, timeout=10) as resp:
                        entry['http'] = resp.status
                        entry['bytes'] = len(resp.read(256))
                    entry['ms'] = int((time.time() - started) * 1000)
                except urllib.error.HTTPError as exc:
                    entry['http'] = exc.code  # 有 HTTP 状态码就说明 443/TLS 通了
                except Exception as exc:
                    entry['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:90])
                result[label] = entry
            return result

        @staticmethod
        def _net_probe():
            """量沙箱到几个固定机房的 DNS + TCP 建连耗时，各取 3 次看抖动。

            判断标准：数据库每处理一个请求要做几十次往返，单次 300ms 的库会让
            页面等到不可用；所以看的不是平均值，而是最慢的那次。
            """
            targets = [
                ('tencent-shanghai-gw', 'super-squirrel-d7g341rmr7304d080.api.tcloudbasegateway.com', 443),
                ('tencent-tcb-api', 'tcb-api.cloud.tencent.com', 443),
                ('china-baseline', 'www.qq.com', 443),
            ]
            report = []
            for label, host, port in targets:
                entry = {'target': label, 'host': host, 'tcp_ms': []}
                started = time.time()
                try:
                    socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
                    entry['dns_ms'] = int((time.time() - started) * 1000)
                except Exception as exc:
                    entry['error'] = 'dns:' + type(exc).__name__
                    report.append(entry)
                    continue
                for _ in range(3):
                    started = time.time()
                    try:
                        with socket.create_connection((host, port), timeout=8):
                            entry['tcp_ms'].append(int((time.time() - started) * 1000))
                    except Exception as exc:
                        entry['tcp_ms'].append(type(exc).__name__)
                report.append(entry)
            return report

    server = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)

    def boot_backend() -> None:
        """拉起后端并守着它。

        后端在初始化阶段连不上库就会整个退出（uvicorn 的行为），如果不看护，
        静态页面还能打开、接口却永久 502。这里退出就重来，直到平台回收进程。
        """
        while True:
            # 已经有一个健康的后端就不要重复拉起：平台重启 serve.py 时旧子进程可能
            # 还活着，无脑再起一个会让两个进程各自连库，把远程库的连接和带宽都拖慢。
            if dev.api_ready(1):
                time.sleep(5)
                continue
            try:
                process = dev.start_backend(str(log_path))
                print('serve: 后端就绪 %s' % dev.API_BASE, flush=True)
            except SystemExit as exc:
                print('serve: 后端启动失败：%s' % exc, flush=True)
                time.sleep(5)
                continue
            while process.poll() is None:
                time.sleep(2)
            print('serve: 后端退出（%s），5 秒后重启' % process.returncode, flush=True)
            time.sleep(5)

    threading.Thread(target=boot_backend, name='backend-boot', daemon=True).start()

    print('serve: 监听 http://0.0.0.0:%d  static=%s  api=%s  data=%s'
          % (port, root, dev.API_BASE, os.environ['DATA_DIR']), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
