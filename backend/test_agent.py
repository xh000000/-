"""Agent 服务层测试：状态、线程、SSE 对话降级、后台任务与工具写入链路。

不需要真实模型密钥：模型未配置时 /chat 应返回明确的 error 事件，
工具链路用内嵌子进程直接调用 agent.tools 验证（读 + 受限写 + 留痕）。
运行方式与 test_workflow 一致：python backend/test_agent.py
"""
from test_environment import prepare
prepare()
import unittest, tempfile, subprocess, os, sys, time, json, urllib.request, urllib.error, http.cookiejar, socket
from pathlib import Path

BACKEND = Path(__file__).parent


CLEAN_MODEL_ENV = {'AGENT_API_KEY': '', 'AGENT_MODEL': '', 'AI_API_KEY': '', 'CODEBUDDY_API_KEY': '',
                   'AI_MODEL': '', 'AI_BASE_URL': ''}
TOOLS_ENV = {}


class AgentApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); cls.port = s.getsockname()[1]
        # 清掉本机残留的模型环境变量，保证「未配置」分支可测
        cls.proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name('server.py'))],
            env={**{k: v for k, v in os.environ.items() if k not in CLEAN_MODEL_ENV},
                 **{k: '' for k in CLEAN_MODEL_ENV},
                 'DATA_DIR': cls.tmp.name, 'PORT': str(cls.port)},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f'http://127.0.0.1:{cls.port}/api/'
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + 'bootstrap', timeout=1); break
            except Exception:
                time.sleep(.05)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            cls.proc.kill(); cls.proc.wait(timeout=15)
        for _ in range(20):
            try:
                cls.tmp.cleanup(); break
            except OSError:
                time.sleep(.25)

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, c, path, data=None, method=None):
        verb = method or ('POST' if data is not None else 'GET')
        req = urllib.request.Request(self.base + path, method=verb,
                                     data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json'})
        try:
            with c.open(req) as res:
                return res.status, json.load(res)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def sse(self, c, path, data):
        """读 SSE 流直到 done/error 事件。"""
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json'})
        events = []
        try:
            with c.open(req, timeout=60) as res:
                for raw in res:
                    line = raw.decode().strip()
                    if line.startswith('data: '):
                        events.append(json.loads(line[6:]))
                        if events[-1]['type'] in ('done', 'error'):
                            break
        except urllib.error.HTTPError as e:
            return [{'type': 'http_error', 'code': e.code}]
        return events

    def test_agent_endpoints(self):
        admin = self.client()
        pw = '123456'
        self.assertEqual(self.call(admin, 'setup', {'name': 'admin', 'password': pw})[0], 200)

        # 未登录一律 401
        self.assertEqual(self.call(self.client(), 'agent/status')[0], 401)

        # 状态：未配置模型也要 200，并给出工具清单与出处说明
        status, body = self.call(admin, 'agent/status')
        self.assertEqual(status, 200)
        self.assertFalse(body['configured'])
        names = {x['name'] for x in body['tools']}
        self.assertTrue({'list_reports', 'get_report', 'save_chapter_draft'} <= names)
        self.assertIn('未配置', body['source'])

        # 线程 CRUD
        tid = self.call(admin, 'agent/threads', {'title': '铜的观点讨论'})[1]['id']
        listed = self.call(admin, 'agent/threads')[1]['threads']
        self.assertEqual([x['id'] for x in listed], [tid])
        self.assertEqual(self.call(admin, f'agent/threads/{tid}/messages')[1]['messages'], [])

        # 对话：模型未配置 → 明确的 error 事件而不是 500
        events = self.sse(admin, 'agent/chat', {'thread_id': tid, 'message': '查一下铜的指标'})
        self.assertTrue(events and events[-1]['type'] == 'error')
        self.assertIn('未配置', events[-1]['message'])

        # 后台任务：同样以失败收场，状态落库可查
        task_id = self.call(admin, 'agent/tasks', {'thread_id': tid, 'message': '测试任务'})[1]['id']
        task = {}
        for _ in range(100):
            task = self.call(admin, f'agent/tasks/{task_id}')[1]
            if task['status'] in ('已完成', '失败'):
                break
            time.sleep(.1)
        self.assertEqual(task['status'], '失败')
        self.assertEqual(self.call(admin, 'agent/tasks')[1]['tasks'][0]['id'], task_id)

        # 删除线程后列表为空；别人的（不存在的）线程删除返回 404
        self.assertEqual(self.call(admin, f'agent/threads/{tid}', method='DELETE')[0], 200)
        self.assertEqual(self.call(admin, 'agent/threads')[1]['threads'], [])
        self.assertEqual(self.call(admin, 'agent/threads/no-such-thread', method='DELETE')[0], 404)


TOOLS_SCRIPT = '''
import os, sys, json, secrets, tempfile
tmp = tempfile.mkdtemp()
os.environ['DATA_DIR'] = tmp
sys.path.insert(0, r'%(backend)s')
import app
app.init()
import agent.tools as tools
import db
from sqlalchemy import select
from db import SessionFactory, User, Event, Observation, Report, Author

salt = secrets.token_hex(16)
with SessionFactory() as s:
    s.add(User(name='boss', role='admin', salt=salt, hash=app.password('123456', salt), enabled=1))
    s.commit()
user = {'id': 1, 'name': 'boss', 'role': 'admin'}

# 页面同款 dispatch 创建一篇日度策略草稿
with SessionFactory() as s:
    u = s.get(User, 1)
    import manual_engine as manual
    cats = [c for c in manual.tree(s) if not c['folder']]
    assert cats, '分类迁移应产生末级分类'
    cid = cats[0]['id']
    cfg = json.loads(s.get(db.Category, cid).config)
    author = s.execute(select(Author).limit(1)).scalars().first()
    if author and cfg['kind'] not in json.loads(author.types):
        author.types = json.dumps(sorted(set(json.loads(author.types) + [cfg['kind']])), ensure_ascii=False)
        s.commit()
    if not author:
        author = Author(name='测试作者', types=json.dumps([cfg['kind']]), enabled=1)
        s.add(author); s.commit()
    body, status = app.dispatch({'s': s, 'u': u}, '/api/reports', {
        'manual': True, 'category_id': cid, 'commodity': cfg['commodities'][0],
        'title': '兴业期货日度策略（2026.11.26）',
        'byline_id': author.id, 'report_date': '2026-11-26', 'collaboration': 'personal',
        'summary': '', 'public': True})
    assert status == 200, body
    s.commit()  # dispatch 不负责提交，与 HTTP 层一致由调用方 commit
    rid = body['id']

built = {tool.name: tool for tool in tools.build_tools(user)}
out = json.loads(built['list_reports'].invoke({'keyword': '', 'status': '', 'limit': 10}))
assert out['count'] >= 1, out

report = json.loads(built['get_report'].invoke({'report_id': rid}))
assert report['id'] == rid and report['sections'], report
target = report['sections'][1]  # 二、宏观资讯速递 → 01 宏观要闻
content = '宏观要闻测试：国内大宗商品市场运行平稳。数据来源：Wind，2026-11-26。风险提示：以上内容仅供参考。'
out = json.loads(built['save_chapter_draft'].invoke(
    {'report_id': rid, 'section_id': target['section_id'], 'content': content, 'title': '测试'}))
assert out.get('ok'), out

# 只新增候选，不修改正文、报告版本或图表。
with SessionFactory() as s:
    r = s.get(Report, rid)
    assert r.version == 1, r.version
    assert r.ai_draft == 0, r.ai_draft
    assert content not in r.body
    task=s.get(db.AgentTask,out['task_id'])
    assert task.kind=='report-skill' and task.status=='已完成'
    result=json.loads(task.result)
    assert result['sections'][0]['body']==content
    assert json.loads(task.payload)['origin']=='chat'

# 已送审的报告不可写
with SessionFactory() as s:
    s.get(Report, rid).status = '研究复核'
    s.commit()
out = json.loads(built['save_chapter_draft'].invoke(
    {'report_id': rid, 'section_id': target['section_id'], 'content': content}))
assert not out.get('ok') and '送审' in out.get('error', ''), out

# 指标与品种工具
with SessionFactory() as s:
    s.add(Observation(source='Wind', indicator='铜库存', date='2026-11-25', value=123456, unit='吨'))
    s.commit()
out = json.loads(built['search_indicators'].invoke({'keyword': '铜'}))
assert out['count'] >= 1 and out['indicators'][0]['indicator'] == '铜库存', out
out = json.loads(built['query_indicator'].invoke({'source': 'Wind', 'indicator': '铜库存'}))
assert out['stats']['latest'] == 123456, out
out = json.loads(built['list_commodities'].invoke({}))
assert out['sectors'], out
out = json.loads(built['list_report_skills'].invoke({}))
assert any(x['id']=='daily-research' for x in out['skills']), out
out = json.loads(built['load_report_skill'].invoke({'skill_id':'daily-research'}))
assert '日度与周度研究写作' in out['markdown'], out
out = json.loads(built['search_library'].invoke({'keyword': '不存在的东西'}))
assert out['count'] == 0, out
print('AGENT_TOOLS_OK')
''' % {'backend': str(BACKEND.resolve())}


class AgentTools(unittest.TestCase):
    """工具链路（含受限写 + 留痕）在内嵌子进程里直接验证。"""

    def test_tool_json_is_valid_when_large(self):
        from agent.tools import _dump, _CLIP
        for value in ({'sectors': [{'name': '品种', 'items': list(range(2000))}]},
                      {str(i): 'x' * 81 for i in range(100)}, {'text': 'a' * 10000}):
            output = _dump(value)
            self.assertLessEqual(len(output), _CLIP)
            self.assertTrue(json.loads(output)['truncated'])

    def test_tools(self):
        with tempfile.TemporaryDirectory() as data_dir:
            proc = subprocess.run([sys.executable, '-c', TOOLS_SCRIPT], env={**os.environ, 'DATA_DIR': data_dir},
                                  capture_output=True, text=True, timeout=300, cwd=str(BACKEND.resolve()))
        self.assertIn('AGENT_TOOLS_OK', proc.stdout,
                      'stdout: %s\nstderr: %s' % (proc.stdout[-2000:], proc.stderr[-3000:]))


PIPELINE_SCRIPT = '''
import os, sys, json, secrets, tempfile
tmp = tempfile.mkdtemp()
os.environ['DATA_DIR'] = tmp
os.environ['AGENT_MODEL'] = 'dummy'      # 只为通过 config.ready 检查；写作函数已被替换，不触网
os.environ['AGENT_API_KEY'] = 'dummy'
sys.path.insert(0, r'%(backend)s')
import app
app.init()
import agent.pipeline as pipeline

# 固定写作函数：流水线测试不调用真实模型
pipeline._write_section = lambda model, section, brief, label: (
    '今日板块运行平稳，主力品种震荡整理，现货成交一般。'
    '库存与基差数据未出现异常波动，短期建议观望为主，等待方向确认后再介入。') * 3

import db
from sqlalchemy import select
from db import SessionFactory, User, Event, Report, Author
import manual_engine as manual

salt = secrets.token_hex(16)
with SessionFactory() as s:
    s.add(User(name='boss', role='admin', salt=salt, hash=app.password('123456', salt), enabled=1))
    s.commit()
user = {'id': 1, 'name': 'boss', 'role': 'admin'}

with SessionFactory() as s:
    u = s.get(User, 1)
    cats = [c for c in manual.tree(s) if not c['folder']]
    assert cats, '分类迁移应产生末级分类'
    cat = s.get(db.Category, cats[0]['id'])
    cat.name = '日度策略'
    cfg = json.loads(cat.config)
    author = s.execute(select(Author).limit(1)).scalars().first()
    if author and cfg['kind'] not in json.loads(author.types):
        author.types = json.dumps(sorted(set(json.loads(author.types) + [cfg['kind']])), ensure_ascii=False)
    if not author:
        author = Author(name='测试作者', types=json.dumps([cfg['kind']]), enabled=1)
        s.add(author)
    s.add(db.Observation(source='Wind', indicator='铜库存', date='2026-11-25', value=123456, unit='吨'))
    s.commit()
    summary = pipeline.run(s, user, int(cat.id))
    s.commit()

assert summary['report_id'], summary
assert not summary['submitted'] and summary['status'] == '草稿', summary
assert any(x['ok'] for x in summary['sections']), summary

with SessionFactory() as s:
    r = s.get(Report, summary['report_id'])
    assert r.ai_draft == 1, r.ai_draft
    assert r.status == '草稿', r.status
    assert '风险提示' in (r.body or ''), (r.body or '')[:200]
    events = s.execute(select(Event).where(Event.report_id == r.id)).scalars().all()
    assert any(x.action == 'AI 初稿' for x in events), [x.action for x in events]
    assert not any(x.action == '提交' for x in events), [x.action for x in events]

# 定时触发函数：未配置时必须为空操作
os.environ.pop('AGENT_PIPELINE_TIME', None)
pipeline.schedule_due()
print('AGENT_PIPELINE_OK')
''' % {'backend': str(BACKEND.resolve())}


class AgentPipeline(unittest.TestCase):
    """AI 日报流水线：建报告 → 逐章写稿 → AI 标记 → 保留草稿人工送审（不触网）。"""

    def test_pipeline(self):
        proc = subprocess.run([sys.executable, '-c', PIPELINE_SCRIPT],
                              capture_output=True, text=True, timeout=300, cwd=str(BACKEND.resolve()))
        self.assertIn('AGENT_PIPELINE_OK', proc.stdout,
                      'stdout: %s\nstderr: %s' % (proc.stdout[-2000:], proc.stderr[-3000:]))


if __name__ == '__main__':
    unittest.main()
