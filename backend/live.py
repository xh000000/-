"""实时刷新：数据版本号 + SSE 事件流。

为什么不让服务端告诉客户端「具体改了什么」：业务状态本来就是一次性全量下发的
（/api/state），增量协议要跟着几十个接口一起演进，改一处漏一处。这里只回答一个
问题——「数据变没变」。变了，前端重新拉一次快照即可，菜单、研报、指标、权限全部
一起跟上，新增页面也不需要再接一次推送。

版本号落在库里（revisions 表）而不是进程内存：托管平台可能起多个进程/实例，内存
计数器各算各的，只有库里的值对所有实例一致。
"""
from __future__ import annotations

import asyncio
import json
import time

from sqlalchemy import update

from db import Revision, SessionFactory

NAME = 'state'
POLL_SECONDS = 1.5        # 服务端轮询版本号的间隔：写操作后最迟约 1.5 秒被发现
HEARTBEAT_SECONDS = 15    # 注释行心跳，防止代理把空闲连接掐掉
REVALIDATE_SECONDS = 30   # 会话存活复核间隔


def _stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def ensure(session) -> None:
    """建版本号那一行（幂等）。启动时调用一次，之后 bump 只管自增。"""
    if session.get(Revision, NAME) is None:
        session.add(Revision(name=NAME, value=0, updated=_stamp()))
        session.commit()


def current(session) -> int:
    row = session.get(Revision, NAME)
    return int(row.value or 0) if row else 0


def bump() -> int:
    """写操作提交后自增。

    用 ``value = value + 1`` 交给数据库算，而不是先读再写：并发写时读改写的两个
    事务会互相覆盖，漏掉一次递增就意味着有客户端收不到刷新。行不存在时先补一行
    再重试（单进程内只有启动和极端情况会走到）。
    """
    with SessionFactory() as session:
        result = session.execute(
            update(Revision).where(Revision.name == NAME)
            .values(value=Revision.value + 1, updated=_stamp()))
        if result.rowcount == 0:
            session.add(Revision(name=NAME, value=1, updated=_stamp()))
        session.commit()
        row = session.get(Revision, NAME)
        return int(row.value or 0) if row else 0


def _read() -> int:
    with SessionFactory() as session:
        return current(session)


async def stream(is_disconnected, session_alive):
    """SSE 生成器。

    - 首帧 ``event: ready`` 带上当前版本号，客户端据此建立基线（重连时也能发现
      断线期间发生过变化）；
    - 之后版本号一变就推一条 ``data: {"revision": n}``；
    - 会话失效推 ``event: expire``，让前端回到登录页而不是无声空转。

    DB 查询放到线程池里跑：同步数据库调用会卡住事件循环，一条长连接卡住会连带
    拖慢所有请求。
    """
    last = None
    last_alive_check = 0.0
    last_beat = time.monotonic()
    while True:
        if await is_disconnected():
            break
        now = time.monotonic()
        if now - last_alive_check >= REVALIDATE_SECONDS:
            last_alive_check = now
            alive = await asyncio.to_thread(session_alive)
            if not alive:
                yield 'event: expire\ndata: {}\n\n'
                break
        revision = await asyncio.to_thread(_read)
        if last is None:
            last = revision
            yield 'event: ready\ndata: %s\n\n' % json.dumps({'revision': revision})
        elif revision != last:
            last = revision
            yield 'data: %s\n\n' % json.dumps({'revision': revision})
        if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
            last_beat = time.monotonic()
            yield ': ping\n\n'
        await asyncio.sleep(POLL_SECONDS)
