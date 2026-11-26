"""Agent API 路由：/api/agent/*。

全部端点要求登录（沿用平台的 Cookie 会话与 CSRF 同源校验）；
SSE 对话用 POST + text/event-stream，前端用 fetch + ReadableStream 消费。
app.py 在启动时挂载本 router（未安装 langchain 时跳过，平台照常运行）。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import agent.config as agent_config
import agent.service as service
import agent.tools as platform_tools
from db import get_session

router = APIRouter(prefix='/api/agent', tags=['agent'])


def _auth(request: Request, session: Session) -> dict:
    """运行时导入 app：复用平台的会话解析与错误类型。"""
    import app as platform
    user = platform.resolve_user(session, platform._pick_token(request.cookies))
    if not user:
        raise platform.ApiError(401, '请先登录')
    return {'id': user.id, 'name': user.name, 'role': user.role}


async def _body(request: Request) -> dict:
    import app as platform
    return await platform.payload(request)


@router.get('/status', summary='Agent 状态：模型配置出处与可用工具清单')
def get_status(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    fallback = service.fallback_profile(session)
    cfg = agent_config.resolve(fallback)
    return {'configured': agent_config.ready(cfg),
            'model': cfg['model'], 'base_url': cfg['base_url'],
            'source': agent_config.source_of(cfg, fallback),
            'recursion_limit': cfg['recursion_limit'],
            'tools': platform_tools.tool_catalog(),
            'user': {'name': user['name'], 'role': user['role']}}


# ---------------------------------------------------------------------------
# 对话线程
# ---------------------------------------------------------------------------
@router.get('/threads', summary='当前用户的 Agent 对话线程列表')
def get_threads(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    return {'threads': service.list_threads(session, user)}


@router.post('/threads', summary='新建对话线程')
async def post_thread(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    data = await _body(request)
    title = str(data.get('title') or '')[:60]
    return {'id': service.create_thread(session, user, title)}


@router.delete('/threads/{thread_id}', summary='删除对话线程（连同记忆）')
def delete_thread(thread_id: str, request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    if not service.delete_thread(session, user, thread_id):
        import app as platform
        raise platform.ApiError(404, '对话线程不存在')
    return {'ok': True}


@router.get('/threads/{thread_id}/messages', summary='回放某线程的历史消息')
def get_messages(thread_id: str, request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    if not service.own_thread(session, user, thread_id):
        import app as platform
        raise platform.ApiError(404, '对话线程不存在')
    return {'messages': service.thread_messages(thread_id)}


# ---------------------------------------------------------------------------
# 对话（SSE 流式）
# ---------------------------------------------------------------------------
@router.post('/chat', summary='与 Agent 对话（SSE 流式返回 token 与工具事件）')
async def post_chat(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    data = await _body(request)
    message = str(data.get('message') or '').strip()
    if not message:
        import app as platform
        raise platform.ApiError(400, '请输入对话内容')
    if len(message) > 20000:
        import app as platform
        raise platform.ApiError(400, '对话内容过长（最多 2 万字符）')
    thread_id = str(data.get('thread_id') or '')

    def events():
        for event in service.run_stream(session, user, thread_id, message):
            yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'

    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------
@router.post('/tasks', summary='投递一个后台 Agent 任务（排队顺序执行）')
async def post_task(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    data = await _body(request)
    message = str(data.get('message') or '').strip()
    try:
        task_id = service.enqueue_task(session, user, str(data.get('thread_id') or ''), message)
    except ValueError as exc:
        import app as platform
        raise platform.ApiError(400, str(exc))
    return {'id': task_id, 'status': '排队中'}


@router.get('/tasks', summary='当前用户的后台任务列表')
def get_tasks(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    return {'tasks': service.list_tasks(session, user)}


@router.get('/tasks/{task_id}', summary='查询单个后台任务的状态与结果')
def get_task(task_id: str, request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    task = service.get_task(session, user, task_id)
    if not task:
        import app as platform
        raise platform.ApiError(404, '任务不存在')
    return task


# ---------------------------------------------------------------------------
# AI 日报流水线
# ---------------------------------------------------------------------------
@router.post('/pipeline/run', summary='触发 AI 日报流水线（兼容旧客户端生成草稿，人工核对后送审）')
async def post_pipeline(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    if user['role'] not in ('admin', 'researcher'):
        import app as platform
        raise platform.ApiError(403, '仅研究员或管理员可触发日报流水线')
    data = await _body(request)
    import agent.pipeline as pipeline
    task_id = pipeline.enqueue(session, user, int(data.get('category_id') or 0))
    return {'id': task_id, 'status': '排队中'}


# ---------------------------------------------------------------------------
# 研报 AI 摘要卡
# ---------------------------------------------------------------------------
@router.post('/summary', summary='为研报生成三段式 AI 摘要卡（核心观点/逻辑链/数据要点）')
async def post_summary(request: Request, session: Session = Depends(get_session)):
    user = _auth(request, session)
    data = await _body(request)
    import app as platform
    import agent.summarize as summarize
    try:
        return {'summary': summarize.generate(session, user, data.get('id'))}
    except PermissionError as exc:
        raise platform.ApiError(403, str(exc))
    except ValueError as exc:
        raise platform.ApiError(400, str(exc))
    except Exception as exc:  # 模型网络抖动等
        raise platform.ApiError(502, '摘要生成失败：' + str(exc)[:200])
