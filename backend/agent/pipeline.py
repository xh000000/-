"""AI 日报流水线：取数 → 逐板块写稿 → 自动建报告 → 推进到「研究复核」。

流程（对标同业的「分钟级初稿 + 人工复核」模式）
--------------------------------------------------
1. 定位「日度策略」分类（或显式传入 category_id）；
2. 以触发人身份创建一篇个人报告（复用 manual.handle 全部校验）；
3. 每个章节：按章节挂载的品种取平台指标数据 + 资料库摘录，一次 LLM 调用写正文，
   再走 /api/chapter/save 落稿（版本快照 + 留痕）；
4. 整篇标记 ai_draft=1（前端列表显示「AI 初稿」徽标），并追加留痕事件；
5. 自动「提交」进入研究复核——审批流的后续节点（复核→合规→发布）只允许
   对应角色的人工操作，Agent 无法越过。

触发方式
--------
- 页面手动触发：POST /api/agent/pipeline/run（排进后台任务队列，轮询取结果）；
- 定时触发：.env 设 AGENT_PIPELINE_TIME=HH:MM（UTC），由 app.scheduler 每 30 秒
  检查一次，每天最多跑一次（按 agent_tasks 当日记录去重）；留空则不启用。

LLM 说明：不用 ReAct 图，直接逐章调用 ChatOpenAI——数据由平台代码确定性采集，
模型只负责写作，避免工具循环与幻觉，速度也快得多。
"""
from __future__ import annotations

import json
import os
import time
import uuid

from sqlalchemy import select

import db
import report_engine as report_engine
import agent.config as config
from db import AgentTask, Author, Category, Commodity, LibraryItem, Observation, Report, SessionFactory
from sqlalchemy import func, select

PIPELINE_PREFIX = '/pipeline '      # 任务消息前缀：worker 据此识别流水线任务
_DATA_POINTS = 12                   # 每个指标带回的时间序列点数
_MAX_INDICATORS = 3                 # 每个品种最多取几个指标
_MAX_SNIPPETS = 2                   # 每个品种最多几条资料库摘录
_SYSTEM_RULES = (
    '你是期货公司研究所的投研助理，为日度策略报告撰写章节。硬性规则：'
    '1) 只能使用【最新数据】中给出的数字，引用时注明指标名与日期，禁止编造或推算数据；'
    '2) 不得出现「保本/稳赚/保证收益/必涨/必跌」等承诺性表述；'
    '3) 观点用中性表述（如「预计偏强运行」「建议关注回落风险」）；'
    '4) 300～600 字纯文本，可分 2～3 个自然段，不要用 Markdown 语法。'
)

_COMPLIANCE_FOOTER = '\n\n数据来源：平台指标库与资料库（截至 {date}）。' \
                     '风险提示：期货市场风险较高，以上为 AI 生成初稿，须经研究人员复核后方可对外使用。'


def _stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'


def _today() -> str:
    return time.strftime('%Y-%m-%d')


# ---------------------------------------------------------------------------
# 数据采集（平台代码确定性执行，不经 LLM）
# ---------------------------------------------------------------------------
def _indicators_for(s, name: str) -> list[dict]:
    rows = s.execute(
        select(Observation.source, Observation.indicator, Observation.unit,
               func.count(Observation.id).label('n'), func.max(Observation.date).label('latest'))
        .where(Observation.indicator.contains(name))
        .group_by(Observation.source, Observation.indicator, Observation.unit)
        .order_by(func.count(Observation.id).desc()).limit(_MAX_INDICATORS)).all()
    out = []
    for source, indicator, unit, n, latest in rows:
        series = report_engine.resolve_data(s, source, indicator)[-_DATA_POINTS:]
        out.append({'source': source, 'indicator': indicator, 'unit': unit or '',
                    'points': [{'date': p['date'], 'value': p['value']} for p in series]})
    return out


def _snippets_for(s, name: str) -> list[str]:
    rows = s.execute(select(LibraryItem).where(LibraryItem.deleted == 0, LibraryItem.body.isnot(None))
                     .order_by(LibraryItem.id.desc()).limit(50)).scalars().all()
    out = []
    for item in rows:
        if name in (item.name or '') or name in (item.body or ''):
            out.append('《%s》：%s' % (item.name, (item.body or '')[:300]))
            if len(out) >= _MAX_SNIPPETS:
                break
    return out


def _section_brief(s, section: dict) -> dict:
    names = []
    for cid in section.get('commodity_ids') or []:
        row = s.get(Commodity, int(cid))
        if row and row.enabled and row.name not in names:
            names.append(row.name)
    if names:
        indicators = []
        snippets = []
        for name in names[:3]:
            for ind in _indicators_for(s, name):
                if all(x['indicator'] != ind['indicator'] for x in indicators):
                    indicators.append(ind)
            snippets.extend(x for x in _snippets_for(s, name) if x not in snippets)
        indicators, snippets = indicators[:_MAX_INDICATORS * 2], snippets[:_MAX_SNIPPETS * 2]
    else:  # 无挂载品种的章节（如宏观）：给全局摘要
        names = []
        indicators = _indicators_for(s, '')[:_MAX_INDICATORS]
        snippets = []
    return {'names': names, 'indicators': indicators, 'snippets': snippets}


# ---------------------------------------------------------------------------
# 写作与落稿
# ---------------------------------------------------------------------------
def _write_section(model, section: dict, brief: dict, category_label: str) -> str:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=model['model'], api_key=model['api_key'], base_url=model['base_url'],
                     temperature=model.get('temperature', 0.4), timeout=model.get('timeout', 180),
                     max_retries=1)
    data_json = json.dumps(brief['indicators'], ensure_ascii=False)
    snippets = '\n'.join(brief['snippets']) or '（无）'
    prompt = (
        '章节标题：{title}\n所属报告：{cat}\n关联品种：{names}\n'
        '【最新数据】\n{data}\n【资料库摘录】\n{snips}\n\n请撰写本章节的板块观点。'
        .format(title=section.get('title') or section.get('label') or '未命名章节',
                cat=category_label, names='、'.join(brief['names']) or '（综合）',
                data=data_json, snips=snippets)
    )
    answer = llm.invoke([('system', _SYSTEM_RULES), ('human', prompt)])
    content = answer.content
    if isinstance(content, list):
        content = ''.join(b.get('text', '') if isinstance(b, dict) else str(b) for b in content)
    return content.strip()


def run(s, user: dict, category_id: int = 0) -> dict:
    """执行一次日报流水线；返回摘要 dict（也作为任务 result 存库）。"""
    import app as platform
    import manual_engine as manual

    cfg_model = config.resolve(service_fallback(s))
    if not config.ready(cfg_model):
        raise ValueError('Agent 模型未配置：请设置 AGENT_API_KEY/AGENT_MODEL 或配置平台外部模型')

    # 1. 定位分类
    cat = None
    if category_id:
        cat = s.get(Category, int(category_id))
        if cat and cat.folder:
            cat = None
    if cat is None:
        cat = s.execute(select(Category).where(Category.folder == 0, Category.enabled == 1,
                                               Category.name.contains('日度策略'))
                        .order_by(Category.id)).scalars().first()
    if cat is None:
        raise ValueError('未找到「日度策略」分类：请先在研报中心配置分类，或在触发时指定 category_id')
    cfg = json.loads(cat.config or '{}')

    # 2. 署名作者与报告级品种
    kind = cfg.get('kind', '')
    author = s.execute(select(Author).where(Author.enabled == 1)
                       .order_by(Author.id)).scalars().all()
    author = next((x for x in author if kind in json.loads(x.types or '[]')), None)
    if author is None:
        raise ValueError('没有启用的署名作者适用于「%s」类型，请先在品种/作者库配置' % kind)
    commodity = s.execute(select(Commodity).where(Commodity.enabled == 1)
                          .order_by(Commodity.parent_id.isnot(None), Commodity.parent_id,
                                    Commodity.id)).scalars().first()
    if commodity is None:
        raise ValueError('品种库为空，无法创建报告')

    # 3. 建报告（复用全部校验）
    title = '%s（%s）AI 初稿' % (cat.label or cat.name, time.strftime('%Y.%m.%d'))
    body, status = manual.handle(s, '/api/reports', {
        'manual': True, 'category_id': cat.id, 'commodity': commodity.name,
        'title': title, 'byline_id': author.id, 'report_date': _today(),
        'collaboration': 'personal', 'summary': 'AI 日报流水线生成的候选初稿，待人工复核。',
        'public': True}, user, platform.stamp, platform.snapshot, platform.event, platform.checks)
    if status != 200:
        raise ValueError('创建报告失败：%s' % json.dumps(body, ensure_ascii=False)[:200])
    s.commit()
    rid = body['id']

    # 4. 逐章节写稿
    r = s.get(Report, rid)
    doc = json.loads(r.document)
    footer = _COMPLIANCE_FOOTER.format(date=_today())
    written = []
    for index, section in enumerate(doc['sections']):
        if index:
            time.sleep(2)  # 章节间节流，避免上游接口限流
        brief = _section_brief(s, section)
        content, last_error = '', ''
        for attempt in range(3):  # 上游抖动重试：3 次，间隔递增
            try:
                content = _write_section(cfg_model, section, brief, cat.label or cat.name)
                last_error = ''
                break
            except Exception as exc:
                last_error = str(exc)[:200]
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
        if last_error:
            written.append({'section': section.get('title', section['id']), 'ok': False,
                            'error': last_error})
            continue
        data = {'id': rid, 'section_id': section['id'], 'revision': section['revision'],
                'blocks': [{'id': report_engine.uid(), 'type': 'text', 'span': 12,
                            'title': section.get('title', ''), 'text': content + footer}]}
        result, status = manual.handle(s, '/api/chapter/save', data, user,
                                       platform.stamp, platform.snapshot, platform.event, platform.checks)
        if status != 200:
            written.append({'section': section.get('title', section['id']), 'ok': False,
                            'error': json.dumps(result, ensure_ascii=False)[:200]})
        else:
            written.append({'section': section.get('title', section['id']), 'ok': True})
        s.commit()

    # 5. 合规标记与留痕
    s.expire(r)
    r = s.get(Report, rid)
    r.ai_draft = 1
    platform.event(s, r, user, 'AI 初稿', 'AI 日报流水线生成整篇初稿，待人工复核')
    s.commit()

    # 6. 送审：只推进到「研究复核」，后续节点必须人工操作
    submitted, note = False, ''
    result, status = platform.transition(s, r, {'action': '提交', 'note': ''}, user)
    if status == 200:
        submitted = True
    else:
        note = json.dumps(result, ensure_ascii=False)[:200]
    s.commit()

    return {'report_id': rid, 'title': title, 'status': '研究复核' if submitted else '草稿',
            'submitted': submitted, 'submit_note': note,
            'sections': written, 'finished_at': _stamp()}


def service_fallback(s):
    import agent.service as service
    return service.fallback_profile(s)


# ---------------------------------------------------------------------------
# 定时调度（app.scheduler 每 30 秒调用一次）
# ---------------------------------------------------------------------------
def schedule_due() -> None:
    at = (os.getenv('AGENT_PIPELINE_TIME') or '').strip()
    if not at or ':' not in at:
        return
    hh, mm = at.split(':', 1)
    now = time.gmtime()
    if (now.tm_hour, now.tm_min) != (int(hh) % 24, int(mm) % 60):
        return
    with SessionFactory() as s:
        today = time.strftime('%Y-%m-%d', time.gmtime())
        done = s.execute(select(AgentTask.id).where(AgentTask.message == PIPELINE_PREFIX + '0',
                                                    AgentTask.created_at.like(today + '%'))).first()
        if done:
            return
        admin = s.execute(select(db.User).where(db.User.role == 'admin', db.User.enabled == 1)
                          .order_by(db.User.id)).scalars().first()
        if admin is None:
            print('pipeline: 未找到启用的管理员账号，定时日报跳过', flush=True)
            return
        enqueue(s, {'id': admin.id, 'name': admin.name, 'role': admin.role}, 0)
        print('pipeline: 已排入今日日报任务（%s）' % admin.name, flush=True)


def enqueue(s, user: dict, category_id: int = 0) -> str:
    task_id = uuid.uuid4().hex
    s.add(db.AgentTask(id=task_id, thread_id='', user_id=user['id'],
                       message=PIPELINE_PREFIX + str(int(category_id or 0)),
                       status='排队中', created_at=_stamp()))
    s.commit()
    import agent.service as service
    service.push_task(task_id)
    return task_id
