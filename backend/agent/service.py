"""Agent 运行服务：SSE 事件流、线程管理、后台任务队列。

事件流协议（SSE，每条 data: 一个 JSON 对象）
------------------------------------------
- {'type':'start','thread_id','model'}   本次运行开始（thread_id 可能在对话时新分配）
- {'type':'token','content'}             模型正文增量
- {'type':'tool_start','name','args'}    模型发起一次工具调用
- {'type':'tool_end','name','output'}    工具返回（output 已截断）
- {'type':'done','thread_id'}            正常结束
- {'type':'error','message'}             出错（模型未配置、上游断连、递归超限…）

后台任务队列：单 worker 线程顺序消费 agent_tasks 表的任务，
适合「把六个板块各写一版初稿」这类长事务；结果与错误都落在表里，页面轮询。
"""
from __future__ import annotations

import json
import queue
import threading
import time
import uuid

import db
import agent.config as config
import agent.memory as memory
from db import SessionFactory

# langchain / langgraph 是可选重依赖，且导入要好几秒：
# 一律等到真正运行 Agent 时才加载，保证「import app」保持秒级（定时任务等子进程依赖它）。

_OUTPUT_CLIP = 800


def _stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'


def _text_of(msg) -> str:
    """兼容 OpenAI 的 str 与推理模型的分段 content。"""
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ''.join(block.get('text', '') if isinstance(block, dict) else str(block) for block in content)
    return str(content)


# ---------------------------------------------------------------------------
# 线程管理
# ---------------------------------------------------------------------------
def create_thread(s, user: dict, title: str = '') -> str:
    tid = uuid.uuid4().hex
    s.add(db.AgentThread(id=tid, user_id=user['id'], title=(title or '新对话')[:60],
                         created_at=_stamp(), updated_at=_stamp()))
    s.commit()
    return tid


def list_threads(s, user: dict) -> list[dict]:
    rows = s.execute(db.select(db.AgentThread).where(db.AgentThread.user_id == user['id'])
                     .order_by(db.AgentThread.updated_at.desc())).scalars().all()
    return [x.to_dict() for x in rows]


def own_thread(s, user: dict, thread_id: str):
    row = s.get(db.AgentThread, str(thread_id or ''))
    return row if row and row.user_id == user['id'] else None


def delete_thread(s, user: dict, thread_id: str) -> bool:
    row = own_thread(s, user, thread_id)
    if not row:
        return False
    s.delete(row)
    s.commit()
    try:
        memory.saver().delete_thread(thread_id)  # 连 checkpoint 一起清
    except AttributeError:
        pass
    return True


def touch_thread(s, thread_id: str, first_message: str = '') -> None:
    row = s.get(db.AgentThread, thread_id)
    if not row:
        return
    row.updated_at = _stamp()
    title = (row.title or '').strip()
    if first_message and title in ('', '新对话'):
        row.title = first_message.strip().replace('\n', ' ')[:60]
    s.commit()


def thread_messages(thread_id: str) -> list[dict]:
    """从 checkpoint 回放对话：user / assistant 消息按顺序返回。"""
    from langchain_core.messages import AIMessage, HumanMessage
    snapshot = memory.saver().get_tuple({'configurable': {'thread_id': str(thread_id)}})
    if not snapshot:
        return []
    # CheckpointTuple.checkpoint['channel_values']['messages'] 才是消息列表；
    # .state 是 graph.get_state() 返回的 StateSnapshot 才有的属性
    messages = (snapshot.checkpoint or {}).get('channel_values', {}).get('messages', [])
    out = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            out.append({'role': 'user', 'content': _text_of(msg)})
        elif isinstance(msg, AIMessage) and _text_of(msg).strip():
            out.append({'role': 'assistant', 'content': _text_of(msg)})
    return out


# ---------------------------------------------------------------------------
# 同步流式运行（SSE）
# ---------------------------------------------------------------------------
def fallback_profile(s) -> dict:
    """Agent 未配置项回落到平台外部模型；运行时导入避免循环依赖。"""
    import app as platform
    return {'base_url': platform._ai_base(s), 'api_key': platform._ai_key(s), 'model': platform._ai_model(s)}


def run_stream(s, user: dict, thread_id: str, message: str):
    """生成 SSE 事件字典序列。调用方（routes）负责序列化成 data: 行。"""
    import agent.graph as graph
    from langchain_core.messages import AIMessageChunk, ToolMessage
    from langgraph.errors import GraphRecursionError
    cfg = config.resolve(fallback_profile(s))
    if not config.ready(cfg):
        yield {'type': 'error',
               'message': 'Agent 模型未配置：请在 .env 设置 AGENT_API_KEY 与 AGENT_MODEL，'
                          '或先在「基本配置 → 外部模型」配置平台模型作为回落'}
        return
    if not own_thread(s, user, thread_id):
        thread_id = create_thread(s, user, message)
    touch_thread(s, thread_id, message)
    yield {'type': 'start', 'thread_id': thread_id, 'model': cfg['model']}
    try:
        agent = graph.build(user, cfg)
        run_cfg = {'recursion_limit': cfg['recursion_limit'],
                   'configurable': {'thread_id': thread_id}}
        for mode, chunk in agent.stream({'messages': [('user', message)]}, run_cfg,
                                        stream_mode=['messages', 'updates']):
            if mode == 'messages':
                msg = chunk[0] if isinstance(chunk, tuple) else chunk
                if isinstance(msg, AIMessageChunk) and _text_of(msg):
                    yield {'type': 'token', 'content': _text_of(msg)}
            else:  # updates：节点完成时的整块输出，用来发工具事件
                for node, payload in (chunk or {}).items():
                    if node == 'agent' and payload.get('messages'):
                        for call in payload['messages'][-1].tool_calls or []:
                            yield {'type': 'tool_start', 'name': call.get('name', ''),
                                   'args': call.get('args', {})}
                    elif node == 'tools' and isinstance(payload.get('messages'), list):
                        for result in payload['messages']:
                            if isinstance(result, ToolMessage):
                                yield {'type': 'tool_end', 'name': result.name or '',
                                       'output': str(result.content)[:_OUTPUT_CLIP]}
        yield {'type': 'done', 'thread_id': thread_id}
    except GraphRecursionError:
        yield {'type': 'error', 'message': '工具调用轮数超出上限（AGENT_RECURSION_LIMIT），请缩小任务范围后重试'}
    except Exception as exc:  # 上游断连、鉴权失败等：把原因交回前端，不中断服务
        yield {'type': 'error', 'message': 'Agent 运行失败：%s' % str(exc)[:300]}


# ---------------------------------------------------------------------------
# 后台任务队列
# ---------------------------------------------------------------------------
_tasks: queue.Queue = queue.Queue()
_started = threading.Event()


def start_worker() -> None:
    """在 app lifespan 里调用一次；重复调用无害。"""
    if _started.is_set():
        return
    _started.set()
    threading.Thread(target=_worker, daemon=True, name='agent-task-worker').start()


def push_task(task_id: str) -> None:
    """把任务 ID 推入队列（pipeline 等模块复用同一 worker）。"""
    _tasks.put(task_id)


def enqueue_task(s, user: dict, thread_id: str, message: str) -> str:
    if len((message or '').strip()) < 1:
        raise ValueError('任务内容不能为空')
    if len(message) > 20000:
        raise ValueError('任务内容过长（最多 2 万字符）')
    if thread_id and not own_thread(s, user, thread_id):
        raise ValueError('对话线程不存在或不属于当前账号')
    task_id = uuid.uuid4().hex
    s.add(db.AgentTask(id=task_id, thread_id=thread_id or '', user_id=user['id'],
                       message=message, status='排队中', created_at=_stamp()))
    s.commit()
    _tasks.put(task_id)
    return task_id


def list_tasks(s, user: dict, limit: int = 50) -> list[dict]:
    rows = s.execute(db.select(db.AgentTask).where(db.AgentTask.user_id == user['id'])
                     .order_by(db.AgentTask.created_at.desc()).limit(max(1, min(limit, 100)))).scalars().all()
    return [x.to_dict() for x in rows]


def get_task(s, user: dict, task_id: str):
    task = s.get(db.AgentTask, str(task_id or ''))
    return task.to_dict() if task and task.user_id == user['id'] else None


def _worker() -> None:
    while True:
        task_id = _tasks.get()
        try:
            _run_task(task_id)
        except Exception as exc:  # worker 不能因单条任务崩溃退出
            print('agent-task', type(exc).__name__, flush=True)
            _mark(task_id, '失败', error='任务执行异常：%s' % str(exc)[:300])
        finally:
            _tasks.task_done()


def _mark(task_id: str, status: str, result: str | None = None, error: str | None = None) -> None:
    with SessionFactory() as s:
        task = s.get(db.AgentTask, task_id)
        if not task:
            return
        task.status = status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if status in ('已完成', '失败'):
            task.finished_at = _stamp()
        s.commit()


def _run_task(task_id: str) -> None:
    with SessionFactory() as s:
        task = s.get(db.AgentTask, task_id)
        if not task or task.status != '排队中':
            return
        task.status = '运行中'
        task.started_at = _stamp()
        s.commit()
        account = s.get(db.User, task.user_id)
        if not account or not account.enabled:
            _mark(task_id, '失败', error='任务发起账号已不存在或停用')
            return
        user = {'id': account.id, 'name': account.name, 'role': account.role}
        if task.message.startswith('/pipeline '):  # AI 日报流水线任务
            _run_pipeline_task(s, task, user)
            return
        thread_id = task.thread_id
        final_text = ''
        error = ''
        for event in run_stream(s, user, thread_id, task.message):
            if event['type'] == 'token':
                final_text += event['content']
            elif event['type'] == 'start':
                thread_id = event['thread_id']
            elif event['type'] == 'error':
                error = event['message']
        if error and not final_text:
            _mark(task_id, '失败', error=error)
            return
        _mark(task_id, '已完成', result=final_text or error,
              error=error or None)
        if thread_id:
            touch_thread(s, thread_id, '')


def _run_pipeline_task(s, task, user: dict) -> None:
    """执行 AI 日报流水线：结果摘要存 result，失败原因存 error。"""
    import agent.pipeline as pipeline
    try:
        category_id = int(task.message[len('/pipeline '):] or 0)
        summary = pipeline.run(s, user, category_id)
        _mark(task.id, '已完成', result=json.dumps(summary, ensure_ascii=False))
    except Exception as exc:
        _mark(task.id, '失败', error='流水线执行失败：%s' % str(exc)[:300])
