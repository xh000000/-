"""Agent 会话记忆：LangGraph SqliteSaver，独立文件 agent_memory.db。

与业务库分开：checkpoint 结构是 LangGraph 的内部格式，随框架版本演进，
混进 research.db 会把业务库的备份/迁移复杂化。消息回放走 service.thread_messages。
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SAVER = None


def db_path() -> Path:
    root = Path(os.getenv('DATA_DIR', str(Path(__file__).parent.parent / 'data')))
    return root / 'agent_memory.db'


def saver():
    """进程内单例。SqliteSaver 的连接允许跨线程（check_same_thread=False），
    SSE 流、后台任务 worker、HTTP 请求都可能触碰它。"""
    global _SAVER
    if _SAVER is None:
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        _SAVER = SqliteSaver(conn)
    return _SAVER
