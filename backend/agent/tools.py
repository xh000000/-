"""平台工具注册表：把现有引擎包装成 agent 可调用的工具。

原则
----
- 只读工具直接开临时 Session 查库；写工具一律复用平台既有处理器
  （manual.handle → /api/chapter/save），权限校验、版本快照、操作留痕一条不少。
- 工具按当前用户构建（build_tools(user)）：闭包里只携带 user 快照
  （id / name / role 三个标量），不携带 HTTP 上下文，天然线程安全。
- 所有工具返回 JSON 字符串：LLM 读得稳，排查日志也直观。

接入新工具：在下面 _TOOLS 注册表里加一行（名字 → 构建函数），
状态页 /api/agent/status 的工具清单会自动更新。
"""
from __future__ import annotations

import json

from sqlalchemy import func, select

import manual_engine as manual
import report_engine as engine
from db import Commodity, LibraryItem, Observation, Report, SessionFactory

_CLIP = 2000          # 单个工具返回给模型的字符上限，防止大结果挤爆上下文
_LIB_SNIPPET = 400    # 资料库摘要长度


def _dump(value) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= _CLIP else text[:_CLIP] + '…（结果过长已截断，请缩小查询范围）'


def _user_dict(u) -> dict:
    return {'id': u.id, 'name': u.name, 'role': u.role}


# ---------------------------------------------------------------------------
# 只读工具
# ---------------------------------------------------------------------------
def _list_reports(user):
    def run(status: str = '', keyword: str = '', limit: int = 20) -> str:
        """按状态或关键词检索当前用户可见的研报。status 可选：草稿/研究复核/合规审核/待发布/已发布/已退回；留空查全部。"""
        with SessionFactory() as s:
            rows = s.execute(select(Report).where(Report.deleted == 0)
                             .order_by(Report.id.desc())).scalars().all()
            want = (status or '').strip()
            kw = (keyword or '').strip().lower()
            out = []
            for r in rows:
                if want and r['status'] != want:
                    continue
                if kw and kw not in (r['title'] or '').lower() and kw not in (r['commodity'] or ''):
                    continue
                if not manual.can_view(s, r, user):
                    continue
                out.append({'id': r['id'], 'title': r['title'], 'commodity': r['commodity'],
                            'kind': r['kind'], 'status': r['status'], 'issue': r['issue'],
                            'version': r['version'], 'updated': r['updated']})
                if len(out) >= max(1, min(int(limit or 20), 50)):
                    break
            return _dump({'count': len(out), 'reports': out})
    return run


def _get_report(user):
    def run(report_id: int) -> str:
        """读取一篇研报的完整章节内容（含各章节的 section_id 与 revision，写草稿前先调用它拿这些参数）。"""
        with SessionFactory() as s:
            r = s.get(Report, int(report_id))
            if not r or not manual.can_view(s, r, user):
                return _dump({'error': '研报不存在或无权访问'})
            doc = json.loads(r['document']) if r['document'] else None
            if not doc:
                return _dump({'id': r['id'], 'title': r['title'], 'status': r['status'], 'body': (r['body'] or '')[:1500]})
            sections = []
            for sec in doc['sections']:
                blocks = []
                for b in sec['blocks']:
                    if b['type'] == 'text':
                        blocks.append({'type': 'text', 'title': b.get('title', ''), 'text': b.get('text', '')})
                    elif b['type'] == 'image':
                        blocks.append({'type': 'image', 'title': b.get('title', ''), 'asset_name': b.get('asset_name', '')})
                    else:
                        blocks.append({'type': b['type'], 'source': b.get('source', ''), 'indicator': b.get('indicator', ''),
                                       'rows': len(b.get('data', []))})
                sections.append({'section_id': sec['id'], 'label': sec.get('label', ''), 'title': sec['title'],
                                 'group': sec.get('group', ''), 'state': sec.get('state', ''),
                                 'revision': sec.get('revision', 1), 'blocks': blocks})
            return _dump({'id': r['id'], 'title': r['title'], 'commodity': r['commodity'], 'kind': r['kind'],
                          'status': r['status'], 'issue': r['issue'], 'version': r['version'], 'sections': sections})
    return run


def _search_indicators(user):
    def run(keyword: str = '', limit: int = 30) -> str:
        """按关键词检索平台已入库的数据指标（数据来源 + 指标名），再配 query_indicator 取数。"""
        with SessionFactory() as s:
            rows = s.execute(
                select(Observation.source, Observation.indicator, func.count(Observation.id),
                       func.max(Observation.date))
                .group_by(Observation.source, Observation.indicator)
                .order_by(func.count(Observation.id).desc())).all()
            kw = (keyword or '').strip().lower()
            out = [{'source': src, 'indicator': ind, 'points': n, 'latest': latest}
                   for src, ind, n, latest in rows
                   if not kw or kw in (src or '').lower() or kw in (ind or '').lower()]
            return _dump({'count': len(out), 'indicators': out[:max(1, min(int(limit or 30), 100))]})
    return run


def _query_indicator(user):
    def run(source: str, indicator: str, limit: int = 60) -> str:
        """取某个数据来源下某指标的时间序列（最近 limit 条，从旧到新），附最新值与区间统计。"""
        with SessionFactory() as s:
            rows = engine.resolve_data(s, str(source), str(indicator))
        if not rows:
            return _dump({'error': '该来源下没有此指标，先用 search_indicators 确认名称'})
        picked = rows[-max(1, min(int(limit or 60), 500)):]
        values = [r['value'] for r in rows if r['value'] is not None]
        stats = {}
        if values:
            stats = {'latest': values[-1], 'min': min(values), 'max': max(values),
                     'mean': round(sum(values) / len(values), 6), 'points': len(values)}
        return _dump({'source': source, 'indicator': indicator, 'unit': rows[-1].get('unit', ''),
                      'stats': stats, 'series': [{'date': r['date'], 'value': r['value']} for r in picked]})
    return run


def _list_commodities(user):
    def run() -> str:
        """读取期货品种库：板块 → 品种（含合约代码），日度策略各板块与此一一对应。"""
        with SessionFactory() as s:
            rows = s.execute(select(Commodity).order_by(Commodity.id)).scalars().all()
            sectors = [{'id': r.id, 'name': r.name, 'code': r.code or '',
                        'items': [{'id': x.id, 'name': x.name, 'code': x.code or ''}
                                  for x in rows if x.parent_id == r.id]}
                       for r in rows if not r.parent_id and r.enabled]
            return _dump({'sectors': sectors})
    return run


def _search_library(user):
    def run(keyword: str, limit: int = 10) -> str:
        """在资料库里按关键词检索文档，返回名称与正文摘要（写观点时可引用资料内容）。"""
        kw = (keyword or '').strip()
        if not kw:
            return _dump({'error': '请提供检索关键词'})
        with SessionFactory() as s:
            rows = s.execute(select(LibraryItem).where(LibraryItem.deleted == 0, LibraryItem.body.isnot(None))
                             .order_by(LibraryItem.id.desc())).scalars().all()
            out = []
            for item in rows:
                body = item.body or ''
                name = item.name or ''
                pos = body.find(kw)
                if kw not in name and pos < 0:
                    continue
                snippet = body[max(0, pos - 60): pos + _LIB_SNIPPET] if pos >= 0 else body[:_LIB_SNIPPET]
                out.append({'id': item.id, 'name': name, 'area': item.area, 'updated': item.updated,
                            'snippet': snippet})
                if len(out) >= max(1, min(int(limit or 10), 20)):
                    break
            return _dump({'count': len(out), 'items': out})
    return run


# ---------------------------------------------------------------------------
# 受限写工具：复用 /api/chapter/save 的全部校验
# ---------------------------------------------------------------------------
def _save_chapter_draft(user):
    def run(report_id: int, section_id: str, content: str, title: str = '') -> str:
        """把候选草稿写入研报的一个章节（仅草稿/已退回状态、本人可编辑的章节）。

        会替换该章节的原有文字组件（图表/表格/图片组件保留），
        平台自动生成新版本与操作留痕。写之前先调 get_report 拿 section_id 与 revision。
        """
        import app as platform  # 运行时才导入，避免与 app.py 循环依赖
        if len(content or '') < 10:
            return _dump({'error': '内容太短，请写完整的章节草稿再保存'})
        if len(content) > 40000:
            return _dump({'error': '内容超过 4 万字符，请分段保存'})
        with SessionFactory() as s:
            r = s.get(Report, int(report_id))
            if not r or not manual.can_view(s, r, user):
                return _dump({'error': '研报不存在或无权访问'})
            if not manual.editable(r):
                return _dump({'error': '报告已送审或已发布，agent 不能修改；草稿类内容请新建报告承载'})
            doc = json.loads(r['document']) if r['document'] else None
            if not doc:
                return _dump({'error': '旧版报告没有章节结构，无法按章节写入'})
            section = next((x for x in doc['sections'] if x['id'] == section_id), None)
            if not section:
                return _dump({'error': '章节不存在，请先用 get_report 查看章节列表'})
            if not manual.section_allowed(r, user, section):
                return _dump({'error': '当前账号无权编辑此章节（或章节已提交锁定）'})
            kept = [b for b in section['blocks'] if b['type'] != 'text']
            data = {'id': int(report_id), 'section_id': section_id, 'revision': section['revision'],
                    'blocks': [{'id': engine.uid(), 'type': 'text', 'span': 12,
                                'title': str(title or '')[:100], 'text': content}, *kept]}
            result, status = manual.handle(s, '/api/chapter/save', data, user,
                                           platform.stamp, platform.snapshot, platform.event, platform.checks)
            if status != 200:
                s.rollback()
                return _dump(result)
            # 合规标记：Agent 产出的报告永远带 AI 初稿标识，并额外留痕
            r.ai_draft = 1
            platform.event(s, r, user, 'AI 初稿', 'Agent 写入章节「%s」，内容须人工核对后方可送审' % section.get('title', section_id))
            s.commit()
            return _dump({'ok': True, 'report_id': int(report_id), 'section_id': section_id,
                          'new_version': r['version'], 'note': '已写入并留痕；内容为候选草稿，须人工核对后方可送审'})
    return run


# ---------------------------------------------------------------------------
# 注册表与构建
# ---------------------------------------------------------------------------
def _registry(user) -> list[tuple[str, str, object]]:
    """(工具名, 描述, 执行函数)。描述就是给模型看的说明书，要写清何时该用。"""
    return [
        ('list_reports', '检索当前用户可见的研报列表，可按状态（草稿/研究复核/合规审核/待发布/已发布/已退回）或标题关键词过滤', _list_reports(user)),
        ('get_report', '读取一篇研报的完整章节结构与内容；要把草稿写入某章节前，必须先调用它获取 section_id 和 revision', _get_report(user)),
        ('search_indicators', '按关键词检索平台已入库的数据指标（来源+指标名），是取数前的入口', _search_indicators(user)),
        ('query_indicator', '取某来源某指标的时间序列与统计摘要，写品种观点时用真实数据支撑', _query_indicator(user)),
        ('list_commodities', '读取期货品种库（板块→品种→合约代码），对齐日度策略 01～06 板块', _list_commodities(user)),
        ('search_library', '按关键词检索资料库文档并返回正文摘要', _search_library(user)),
        ('save_chapter_draft', '把候选章节草稿写入草稿状态研报的指定章节（保留图表组件、生成新版本与留痕）；仅限本人可编辑章节', _save_chapter_draft(user)),
    ]


def build_tools(user: dict):
    """按用户快照构建 LangChain 工具列表。user 是 {'id','name','role'} 标量字典。"""
    from langchain_core.tools import StructuredTool
    return [
        StructuredTool.from_function(func=run, name=name, description=description)
        for name, description, run in _registry(user)
    ]


def tool_catalog() -> list[dict]:
    """状态页用：不带用户上下文的工具清单（名称+描述）。"""
    return [{'name': name, 'description': description} for name, description, _ in _registry(
        {'id': 0, 'name': '占位', 'role': 'researcher'})]
