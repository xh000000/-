"""LangGraph ReAct 智能体：模型 + 平台工具 + 持久记忆。

- create_react_agent 提供「模型 ↔ 工具」循环；
- checkpointer 用 SqliteSaver（agent_memory.db），thread_id 即 agent_threads.id，
  跨请求延续对话；
- 系统提示词按当前用户与当天日期动态生成，把平台规则（数据溯源、合规用语）
  写进模型的行为约束里。
"""
from __future__ import annotations

import time

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

import agent.config as config
import agent.memory as memory
import agent.tools as platform_tools

ROLE_NAMES = {'admin': '管理员', 'researcher': '研究员', 'reviewer': '研究复核',
              'compliance': '合规审核', 'publisher': '发布专员'}


def system_prompt(user: dict) -> str:
    role = ROLE_NAMES.get(user.get('role') or '', user.get('role') or '用户')
    today = time.strftime('%Y-%m-%d')
    return (
        '你是「研枢投研平台」内置的投研 Agent，服务对象是期货研究所的内部员工。\n'
        '当前用户：%s（%s）。今天是 %s。\n\n'
        '平台能力（通过工具使用）：\n'
        '- 查研报、读章节：list_reports / get_report；\n'
        '- 查数据：search_indicators 找指标，query_indicator 取时间序列；\n'
        '- 查品种库：list_commodities（板块→品种→合约代码）；\n'
        '- 查资料：search_library；\n'
        '- 写章节草稿：save_chapter_draft（唯一写入手段，仅限草稿状态、本人可编辑章节）。\n\n'
        '行为规则：\n'
        '1. 数字必须来自工具返回的真实数据，注明来源与日期；查不到就直说，绝不编造。\n'
        '2. save_chapter_draft 写入的内容是候选草稿，须人工核对；不要替用户做送审、发布等流程决定。\n'
        '3. 任何观点都要带风险提示与数据来源；禁止出现「保本」「稳赚」「保证收益」「必涨」「必跌」类表述。\n'
        '4. 章节草稿请贴合平台版式习惯：品种观点用「▍品种：观点」格式，章节骨架可参考 get_report 返回的现有内容。\n'
        '5. 回答用简体中文，简洁、专业、可执行；先想清楚要调哪些工具，再动手。'
    ) % (user.get('name') or '同事', role, today)


def build(user: dict, cfg: dict):
    """构建一次对话用的 graph。user 为用户快照，cfg 来自 agent.config.resolve。"""
    llm = ChatOpenAI(
        model=cfg['model'],
        api_key=cfg['api_key'],
        base_url=cfg['base_url'] or None,
        temperature=cfg['temperature'],
        max_tokens=cfg['max_tokens'],
        timeout=cfg['timeout'],
    )
    return create_react_agent(
        llm,
        platform_tools.build_tools(user),
        checkpointer=memory.saver(),
        prompt=system_prompt(user),
    )
