"""观点库与策略准确度回溯（对标 ETA「观点考核」+ 中泰后台「策略准确度回溯」）。

闭环
----
1. 研究员登记观点：品种、方向（看多/看空/震荡）、依据、基准价（自动取指标库最新价，
   历史记录保留，新记录从发布研报确认）、观察期（1~90 自然日）；
2. 结算（回溯）：到期后取指标库该品种的价格（优先现货价 → 收盘价 → 结算价），
   对照基准价算区间涨跌幅，按 ±1% 阈值判「正确 / 错误 / 持平」，无价格数据则
   「无法结算」并保留原因——绝不编造结果；
3. 画像：按人与按品种统计正确率、方向分布，支撑研究员能力画像。

结算幂等：访问列表时自动结算到期观点（同一时刻只结算一次，status 翻转为已结算）。
"""
from __future__ import annotations

import datetime
import json
import math
import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import report_engine
from db import Commodity, Observation, Viewpoint, get_session

router = APIRouter(prefix='/api/viewpoints', tags=['viewpoints'])

DIRECTIONS = ('看多', '看空', '震荡')
SETTLE_THRESHOLD = 1.0          # 涨跌幅阈值（%）：区间变化不超过 ±1% 计「持平」
_PRICE_PREFERENCE = ('现货价', '收盘价', '结算价', '最新点位', '收盘点位')
_MAX_BASIS = 1000
MAX_PRICE_AGE_DAYS = 7


def _stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'


def _today() -> str:
    return time.strftime('%Y-%m-%d')


def _auth(request: Request, session: Session) -> dict:
    import app as platform
    user = platform.resolve_user(session, platform._pick_token(request.cookies))
    if not user:
        raise platform.ApiError(401, '请先登录')
    return {'id': user.id, 'name': user.name, 'role': user.role}


async def _body(request: Request) -> dict:
    import app as platform
    return await platform.payload(request)


# ---------------------------------------------------------------------------
# 价格基准：从指标库取（确定性代码，不用 LLM）
# ---------------------------------------------------------------------------
def price_on(s, commodity: str, date: str, *, source=None, indicator=None, unit=None) -> dict | None:
    """只从已入库价格取值；锁定序列时绝不跨来源、跨指标回退。"""
    target = datetime.date.fromisoformat(date)
    query = select(Observation).where(Observation.date <= date + 'T23:59:59',
        Observation.date >= (target - datetime.timedelta(days=MAX_PRICE_AGE_DAYS)).isoformat())
    if source is not None and indicator is not None:
        query = query.where(Observation.source == source, Observation.indicator == indicator)
    else:
        query = query.where(Observation.indicator.contains(commodity))
    candidates = []
    for row in s.execute(query).scalars():
        rank = next((i for i, suffix in enumerate(_PRICE_PREFERENCE) if (row.indicator or '').endswith(suffix)), None)
        if rank is None: continue  # 库存、开工率等非价格指标不能用于结算
        try:
            day = datetime.date.fromisoformat(str(row.date)[:10])
            value = float(row.value)
        except (TypeError, ValueError): continue
        if not math.isfinite(value) or value <= 0 or not 0 <= (target-day).days <= MAX_PRICE_AGE_DAYS: continue
        if unit is not None and (row.unit or '') != unit: continue
        candidates.append((rank, -day.toordinal(), row.source or '', row.indicator or '', row.id, row))
    if not candidates: return None
    row = min(candidates, key=lambda x:x[:5])[-1]
    return {'value': row.value, 'date': str(row.date)[:10], 'indicator': row.indicator,
            'source': row.source, 'unit': row.unit or ''}


def _outcome(direction: str, change_pct: float, threshold: float = SETTLE_THRESHOLD) -> str:
    if direction == '看多':
        if change_pct >= threshold:
            return '正确'
        if change_pct <= -threshold:
            return '错误'
        return '持平'
    if direction == '看空':
        if change_pct <= -threshold:
            return '正确'
        if change_pct >= threshold:
            return '错误'
        return '持平'
    return '正确' if abs(change_pct) < threshold else '错误'


def settle(s, vp: Viewpoint) -> bool:
    """到期自动结算；返回是否发生状态翻转。无价格数据标记「无法结算」。"""
    if vp.status != '在途' or not vp.expire_date or vp.expire_date > _today():
        return False
    point = None
    reason = ''
    if not vp.benchmark_source or not vp.benchmark_indicator:
        reason = '旧观点缺少锁定的价格来源或指标，无法安全比较价格数据，请重新登记'
    elif vp.benchmark_price is None or not math.isfinite(vp.benchmark_price) or vp.benchmark_price <= 0:
        reason = '缺少有效的正数基准价'
    else:
        point = price_on(s, vp.commodity, vp.expire_date, source=vp.benchmark_source,
                         indicator=vp.benchmark_indicator, unit=vp.benchmark_unit or '')
        if point is None:
            reason = '锁定指标在结算日前 %s 个自然日内没有同来源、同单位的有效价格数据' % MAX_PRICE_AGE_DAYS
        elif point['date'] <= vp.benchmark_date:
            reason = '结算价格日期未晚于基准日期，缺少新的价格数据'
    if reason:
        vp.outcome = '无法结算'
        vp.note = reason
        vp.status = '已结算'
        vp.settled_at = _stamp()
        return True
    change = round((point['value'] - vp.benchmark_price) / vp.benchmark_price * 100, 2)
    vp.result_source = point['source']
    vp.result_indicator = point['indicator']
    vp.result_price = point['value']
    vp.result_date = point['date']
    vp.change_pct = change
    vp.outcome = _outcome(vp.direction or '', change, vp.evaluation_threshold or SETTLE_THRESHOLD)
    vp.note = '基准指标：%s（%s，来源 %s）' % (point['indicator'], point['date'], point['source'])
    vp.status = '已结算'
    vp.settled_at = _stamp()
    return True


def settle_due(s, user: dict | None = None) -> int:
    """把所有到期在途观点结算掉；返回翻转条数。"""
    changed = 0
    for vp in s.execute(select(Viewpoint).where(Viewpoint.status == '在途',
                                                Viewpoint.expire_date <= _today())).scalars():
        if settle(s, vp):
            changed += 1
    if changed:
        s.commit()
    return changed


# ---------------------------------------------------------------------------
# CRUD 与路由
# ---------------------------------------------------------------------------
def _dict(vp: Viewpoint) -> dict:
    return vp.to_dict()


@router.get('', summary='观点库列表（到期自动结算）')
def list_viewpoints(request: Request, session: Session = Depends(get_session)):
    _auth(request, session)
    settle_due(session)
    rows = session.execute(select(Viewpoint).order_by(Viewpoint.id.desc())).scalars().all()
    import manual_engine
    from db import Report
    user = _auth(request, session)
    rows = [x for x in rows if not x.report_id or ((report := session.get(Report, x.report_id)) and manual_engine.can_view(session, report, user))]
    return {'items': [_dict(x) for x in rows], 'threshold': SETTLE_THRESHOLD}


@router.post('', summary='原手工登记入口已停用')
async def create_viewpoint(request: Request, session: Session = Depends(get_session)):
    import app as platform
    _auth(request, session)
    raise platform.ApiError(400, '请从已发布研报的候选观点确认入库，不再接受手工登记或手工价格')


@router.post('/settle', summary='立即结算一条观点（不足观察期也可提前对照当前价）')
async def settle_viewpoint(request: Request, session: Session = Depends(get_session)):
    import app as platform
    user = _auth(request, session)
    data = await _body(request)
    vp = session.get(Viewpoint, int(data.get('id') or 0))
    if not vp:
        raise platform.ApiError(404, '观点不存在')
    if vp.report_id and vp.status == '在途' and request.url.path.endswith('/settle'):
        raise platform.ApiError(400, '研报观点按发布时的观察期到期结算，不支持提前结算')
    if vp.user_id != user['id'] and user['role'] != 'admin':
        raise platform.ApiError(403, '仅本人或管理员可结算')
    if vp.status != '在途':
        raise platform.ApiError(400, '该观点已结算')
    vp.expire_date = _today()          # 提前结算 = 以今天为对照日
    if not settle(session, vp):
        point = price_on(session, vp.commodity, vp.expire_date)
        raise platform.ApiError(400, '暂时无法结算：指标库中没有%s在%s前可用的价格'
                                % (vp.commodity, point and point['date'] or vp.expire_date))
    session.commit()
    return {'item': _dict(vp)}


@router.post('/delete', summary='删除观点（本人或管理员）')
async def delete_viewpoint(request: Request, session: Session = Depends(get_session)):
    import app as platform
    user = _auth(request, session)
    data = await _body(request)
    vp = session.get(Viewpoint, int(data.get('id') or 0))
    if not vp:
        raise platform.ApiError(404, '观点不存在')
    if vp.report_id and vp.status == '在途' and request.url.path.endswith('/settle'):
        raise platform.ApiError(400, '研报观点按发布时的观察期到期结算，不支持提前结算')
    if vp.user_id != user['id'] and user['role'] != 'admin':
        raise platform.ApiError(403, '仅本人或管理员可删除')
    if vp.report_id:
        raise platform.ApiError(400, '研报跟踪记录保留复盘依据，不支持删除')
    session.delete(vp)
    session.commit()
    return {'ok': True}


@router.get('/stats', summary='准确率统计与研究员画像（按人、按品种）')
def viewpoint_stats(request: Request, session: Session = Depends(get_session)):
    _auth(request, session)
    settle_due(session)
    rows = session.execute(select(Viewpoint).where(Viewpoint.status == '已结算')).scalars().all()
    from db import Report
    import manual_engine
    user = _auth(request, session)
    rows = [x for x in rows if not x.report_id or ((report := session.get(Report, x.report_id)) and manual_engine.can_view(session, report, user))]
    settled = [x for x in rows if x.outcome in ('正确', '错误', '持平')]

    def bucket(key_of):
        out = {}
        for vp in settled:
            out.setdefault(key_of(vp), {'total': 0, '正确': 0, '错误': 0, '持平': 0,
                                        '看多': 0, '看空': 0, '震荡': 0})
            b = out[key_of(vp)]
            b['total'] += 1
            b[vp.outcome] += 1
            b[vp.direction] = b.get(vp.direction, 0) + 1
        for b in out.values():
            b['accuracy'] = round(b['正确'] / b['total'] * 100, 1) if b['total'] else None
        return out

    pending_rows = session.execute(select(Viewpoint).where(Viewpoint.status == '在途')).scalars().all()
    pending = sum(1 for x in pending_rows if not x.report_id or ((r := session.get(Report, x.report_id)) and manual_engine.can_view(session, r, user)))
    return {
        'overall': {'settled': len(settled),
                    'pending': pending,
                    'unavailable': len([x for x in rows if x.outcome == '无法结算']),
                    'accuracy': (round(len([x for x in settled if x.outcome == '正确'])
                                       / len(settled) * 100, 1) if settled else None),
                    'threshold': SETTLE_THRESHOLD},
        'by_user': bucket(lambda x: x.user_name or ''),
        'by_commodity': bucket(lambda x: x.commodity or ''),
    }
