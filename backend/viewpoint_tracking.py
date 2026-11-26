"""Published report -> auditable candidate -> confirmed, price-bound tracking.
Extraction is deterministic and never calls a paid model or interprets report prices.
"""
import datetime
import hashlib
import json
import math
import re
from html import unescape
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from db import (AppSetting, Commodity, PublicationHistory, Report, User, Viewpoint,
                ViewpointCandidate, ViewpointScan, get_session)
import manual_engine
import viewpoint as vp

router = APIRouter(prefix='/api/viewpoints', tags=['viewpoints'])
RULE_KEY = 'viewpoint_evaluation_rules'


def plain(body):
    body = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '', body or '', flags=re.S|re.I)
    body = re.sub(r'</(?:p|div|h[1-6]|li)>|<br\s*/?>', '\n', body, flags=re.I)
    return unescape(re.sub(r'<[^>]+>', '', body)).replace('\r', '')


def extract(body, names):
    """Only explicit direction sentences become candidates; ambiguity is flagged, never guessed."""
    seen = set()
    for sentence in re.split(r'[。！？\n]+', plain(body)):
        sentence = sentence.strip()
        if not sentence or len(sentence) > 1500: continue
        hits = [direction for direction, pattern in [('看多', r'看多|看涨|偏多|偏强|上涨'), ('看空', r'看空|看跌|偏空|偏弱|下跌'), ('震荡', r'震荡|横盘')] if re.search(pattern, sentence)]
        if not hits: continue
        if not re.search(r'看多|看涨|偏多|偏强|看空|看跌|偏空|偏弱|震荡|横盘', sentence) and not re.search(r'预计|未来|展望|短期|下周|有望|可能|预期|观察期', sentence): continue
        negated = bool(re.search(r'不看|不宜|不建议|避免|不再|并非|不是|不能|不应', sentence))
        direction = hits[0] if len(hits) == 1 and not negated else ''
        horizon = re.search(r'(?:未来|接下来|观察期|预计)?\s*(\d{1,2})\s*(?:个)?(?:自然)?[天日]', sentence)
        days = int(horizon[1]) if horizon else 7 if '一周' in sentence else None
        conditional = bool(re.search(r'如果|若|一旦|除非|条件|突破|跌破|站上|企稳后|回落至', sentence))
        for name in names:
            if name not in sentence: continue
            key = (name, sentence)
            if key in seen: continue
            seen.add(key)
            reasons = []
            if not direction: reasons.append('方向表述不唯一，需核对')
            if not days: reasons.append('原文未明确观察期')
            if conditional: reasons.append('含条件判断，须人工核实适用条件')
            yield {'commodity': name, 'direction': direction, 'horizon_days': days,
                   'excerpt': sentence, 'conditional': int(conditional), 'reason': '；'.join(reasons) or '请核对原文后确认'}


def sync_published(s, start_date=None, end_date=None, user=None):
    """Scan immutable publication snapshots once. Nested transactions make concurrent scans idempotent."""
    names = [x for (x,) in s.execute(select(Commodity.name).where(Commodity.enabled == 1, Commodity.code != ''))]
    query=select(PublicationHistory).join(Report, Report.id == PublicationHistory.report_id).where(Report.deleted == 0, Report.status == '已发布',~PublicationHistory.id.in_(select(ViewpointScan.publication_id)))
    if start_date:query=query.where(func.substr(PublicationHistory.published_at,1,10)>=start_date)
    if end_date:query=query.where(func.substr(PublicationHistory.published_at,1,10)<=end_date)
    publications=s.execute(query.order_by(PublicationHistory.id)).scalars().all()
    added = 0
    for publication in publications:
        report = s.get(Report, publication.report_id)
        if user and not manual_engine.can_view(s,report,user):continue
        author = s.get(User, report.author)
        try:
            with s.begin_nested():
                scan = ViewpointScan(publication_id=publication.id, count=0)
                s.add(scan); s.flush()
                for candidate in extract(publication.body, names):
                    fingerprint = hashlib.sha256(f"{publication.id}|{candidate['commodity']}|{candidate['excerpt']}".encode()).hexdigest()
                    s.add(ViewpointCandidate(fingerprint=fingerprint, report_id=report.id,
                        publication_id=publication.id, author_id=report.author,
                        author_name=author.name if author else report.author_name,
                        report_title=report.title, published_date=(publication.published_at or '')[:10],
                        status='待确认', created_at=vp._stamp(), **candidate))
                    scan.count += 1
                s.flush()
                added += scan.count
        except IntegrityError:
            # A concurrent scan already inserted this publication.
            continue
    return added


def require_candidate(s, user, cid):
    import app
    candidate = s.get(ViewpointCandidate, int(cid or 0))
    if not candidate: raise app.ApiError(404, '候选观点不存在')
    report = s.get(Report, candidate.report_id)
    if not report or report.deleted or not manual_engine.can_view(s, report, user):
        raise app.ApiError(403, '无权访问来源研报')
    if report.status != '已发布': raise app.ApiError(400, '来源研报已撤回，不能确认观点')
    if user['role'] != 'admin' and user['id'] != candidate.author_id:
        raise app.ApiError(403, '仅研报作者或管理员可以确认、忽略候选观点')
    return candidate


def rules(s):
    row = s.get(AppSetting, RULE_KEY)
    return json.loads(row.value) if row else {'revision': 0, 'items': []}


def date_range(start_date,end_date,required=False):
    if not start_date and not end_date and not required:return
    if not start_date or not end_date:raise ValueError('请选择完整的发布日期范围')
    for value in [start_date,end_date]:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('发布日期格式应为 YYYY-MM-DD')
        try:datetime.date.fromisoformat(value)
        except ValueError:raise ValueError('发布日期无效')
    if start_date>end_date:raise ValueError('开始日期不能晚于结束日期')


@router.post('/extract')
async def extract_range(request:Request,session=Depends(get_session)):
    user=vp._auth(request,session);data=await vp._body(request)
    start_date=data.get('start_date');end_date=data.get('end_date');date_range(start_date,end_date,True)
    method=data.get('method','rule')
    if method=='ai':
        import viewpoint_ai
        return viewpoint_ai.enqueue(session,user,start_date,end_date)
    if method!='rule':raise ValueError('提取方式无效')
    added=sync_published(session,start_date,end_date,user);session.commit()
    return {'added':added,'start_date':start_date,'end_date':end_date}


@router.get('/extraction-job')
def extraction_job(request:Request,session=Depends(get_session)):
    from db import AgentTask
    user=vp._auth(request,session)
    job=session.execute(select(AgentTask).where(AgentTask.kind=='viewpoint-extract',AgentTask.user_id==user['id']).order_by(AgentTask.created_at.desc(),AgentTask.id.desc()).limit(1)).scalars().first()
    return {'job':{'id':job.id,'status':job.status,'error':job.error or '','result':json.loads(job.result or '{}')} if job else None}


@router.get('/candidates')
def candidates(request: Request, start_date:str='',end_date:str='', session=Depends(get_session)):
    user = vp._auth(request, session)
    date_range(start_date,end_date)
    items = []
    query=select(ViewpointCandidate)
    if start_date:query=query.where(ViewpointCandidate.published_date>=start_date,ViewpointCandidate.published_date<=end_date)
    for candidate in session.execute(query.order_by(ViewpointCandidate.id.desc())).scalars():
        report = session.get(Report, candidate.report_id)
        if not report or report.deleted or not manual_engine.can_view(session, report, user): continue
        data = candidate.to_dict()
        data['can_confirm'] = report.status == '已发布' and (user['role'] == 'admin' or candidate.author_id == user['id'])
        items.append(data)
    return {'items': items, 'method': '发布定稿中的明确方向句自动提取；不明确的内容需确认，不调用付费模型'}


@router.get('/rules')
def get_rules(request: Request, session=Depends(get_session)):
    vp._auth(request, session)
    return rules(session)


@router.post('/rules')
async def save_rules(request: Request, session=Depends(get_session)):
    import app
    user = vp._auth(request, session)
    if user['role'] != 'admin': raise app.ApiError(403, '仅管理员可配置复盘规则')
    data = await vp._body(request)
    previous = rules(session)
    if data.get('revision') != previous['revision']: raise app.ApiError(409, '规则已更新，请刷新')
    values = data.get('items')
    if not isinstance(values, list) or len(values) > 200: raise app.ApiError(400, '规则格式错误，最多200条')
    seen, cleaned = set(), []
    for item in values:
        name = str(item.get('commodity') or '').strip()
        days = int(item.get('horizon_days') or 0)
        threshold = float(item.get('threshold') or 0)
        if not session.execute(select(Commodity.id).where(Commodity.name == name, Commodity.enabled == 1)).first():
            raise app.ApiError(400, '请选择有效品种')
        if not 1 <= days <= 90 or not math.isfinite(threshold) or not 0 < threshold <= 100:
            raise app.ApiError(400, '观察期应为1至90天，阈值应大于0且不超过100%')
        if (name, days) in seen: raise app.ApiError(400, '同品种和观察期的规则不能重复')
        seen.add((name, days)); cleaned.append({'commodity': name, 'horizon_days': days, 'threshold': threshold})
    value = json.dumps({'revision': previous['revision'] + 1, 'items': cleaned}, ensure_ascii=False)
    row = session.get(AppSetting, RULE_KEY)
    if row:
        old_value = row.value
        changed = session.execute(update(AppSetting).where(AppSetting.key == RULE_KEY, AppSetting.value == old_value).values(value=value, updated=vp._stamp())).rowcount
        if changed != 1: raise app.ApiError(409, '规则已更新，请刷新')
    else:
        session.add(AppSetting(key=RULE_KEY, value=value, updated=vp._stamp()))
    try: session.commit()
    except IntegrityError:
        session.rollback(); raise app.ApiError(409, '规则已更新，请刷新')
    return {'ok': True}


def confirm(s, user, data):
    import app
    # A guarded update claims a candidate before creating a record.
    c = require_candidate(s, user, data.get('id'))
    basis=data.get('basis',c.draft_basis or c.excerpt)
    if not isinstance(basis,str) or not basis.strip() or len(basis)>3000:raise app.ApiError(400,'观点说明需为1至3000字')
    direction = data.get('direction') or c.direction
    days = int(data.get('horizon_days') or c.horizon_days or 0)
    if direction not in vp.DIRECTIONS or not 1 <= days <= 90:
        raise app.ApiError(400, '请确认方向和1至90个自然日的观察期')
    if c.conditional and data.get('condition_confirmed') is not True:
        raise app.ApiError(400, '请先核实原文中的适用条件')
    if not data.get('reviewed'): raise app.ApiError(400, '请先核对来源原文')
    try: published = datetime.date.fromisoformat(c.published_date)
    except ValueError: raise app.ApiError(400, '发布日期无效，无法确定基准价')
    point = vp.price_on(s, c.commodity, published.isoformat())
    if point is None: raise app.ApiError(400, '发布日前7天内无有效价格，先补齐指标数据；候选仍保留待确认')
    rule = next((r for r in rules(s)['items'] if r['commodity'] == c.commodity and r['horizon_days'] == days), None)
    if rule is None: raise app.ApiError(400, '该品种和观察期尚无复盘阈值，请管理员在复盘规则中配置')
    claimed = s.execute(update(ViewpointCandidate).where(ViewpointCandidate.id == c.id, ViewpointCandidate.status == '待确认')
        .values(status='已确认', confirmed_by=user['name'], confirmed_at=vp._stamp())).rowcount
    if claimed != 1: raise app.ApiError(409, '候选观点已处理，请刷新')
    item = Viewpoint(candidate_id=c.id, report_id=c.report_id, publication_id=c.publication_id,
        source_excerpt=c.excerpt, report_title=c.report_title, published_date=c.published_date,
        user_id=c.author_id, user_name=c.author_name, commodity=c.commodity, direction=direction,
        basis=basis.strip(), horizon_days=days, expire_date=(published+datetime.timedelta(days=days)).isoformat(),
        benchmark_price=point['value'], benchmark_date=point['date'], benchmark_source=point['source'],
        benchmark_indicator=point['indicator'], benchmark_unit=point['unit'], benchmark_manual=0,
        evaluation_threshold=rule['threshold'], status='在途', created_at=vp._stamp())
    s.add(item); s.flush()
    from db import Event
    report=s.get(Report,c.report_id)
    s.add(Event(report_id=c.report_id,actor=user['name'],action='确认跟踪观点',version=report.version,at=vp._stamp(),note=json.dumps({'candidate_id':c.id,'viewpoint_id':item.id,'original_excerpt':c.excerpt,'direction':direction,'horizon_days':days,'basis':basis.strip()},ensure_ascii=False)))
    vp.settle(s, item)  # Historical publications may already be due.
    return item


@router.post('/confirm')
async def confirm_candidates(request: Request, session=Depends(get_session)):
    import app
    user = vp._auth(request, session); data = await vp._body(request)
    values = data.get('items') or [data]
    if not isinstance(values, list) or not 1 <= len(values) <= 50: raise app.ApiError(400, '每次确认1至50条')
    if len({x.get('id') for x in values}) != len(values): raise app.ApiError(400, '候选观点重复')
    try:
        records = [confirm(session, user, x) for x in values]
        session.commit()
    except Exception:
        session.rollback(); raise
    return {'items': [x.to_dict() for x in records]}


@router.post('/ignore')
async def ignore(request: Request, session=Depends(get_session)):
    import app
    user = vp._auth(request, session); data = await vp._body(request)
    c = require_candidate(session, user, data.get('id'))
    result = session.execute(update(ViewpointCandidate).where(ViewpointCandidate.id == c.id, ViewpointCandidate.status == '待确认')
        .values(status='已忽略', confirmed_by=user['name'], confirmed_at=vp._stamp())).rowcount
    if result != 1: raise app.ApiError(409, '候选已处理，请刷新')
    session.commit(); return {'ok': True}
