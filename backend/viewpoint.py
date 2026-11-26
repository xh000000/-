"""观点库与策略准确度回溯（对标 ETA「观点考核」+ 中泰后台「策略准确度回溯」）。

闭环
----
1. 研究员登记观点：品种、方向（看多/看空/震荡）、依据、基准价（自动取指标库最新价，
   可手工覆盖）、观察期（1~90 自然日）；
2. 结算（回溯）：到期后取指标库该品种的价格（优先现货价 → 收盘价 → 结算价），
   对照基准价算区间涨跌幅，按 ±1% 阈值判「正确 / 错误 / 持平」，无价格数据则
   「无法结算」并保留原因——绝不编造结果；
3. 画像：按人与按品种统计正确率、方向分布，支撑研究员能力画像。

结算幂等：访问列表时自动结算到期观点（同一时刻只结算一次，status 翻转为已结算）。
"""
from __future__ import annotations

import datetime
import json
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
def price_on(s, commodity: str, date: str) -> dict | None:
    """该品种在指定日期（含）之前最近的入库价格；按指标类型优先级挑选。"""
    rows = s.execute(
        select(Observation.source, Observation.indicator, func.max(Observation.date))
        .where(Observation.indicator.contains(commodity))
        .group_by(Observation.source, Observation.indicator)).all()
    candidates = []
    for source, indicator, _latest in rows:
        rank = next((i for i, key in enumerate(_PRICE_PREFERENCE)
                     if indicator.endswith(key)), len(_PRICE_PREFERENCE))
        candidates.append((rank, source, indicator))
    candidates.sort()
    best = None
    for _rank, source, indicator in candidates:
        points = [p for p in report_engine.resolve_data(s, source, indicator)
                  if p.get('value') is not None and str(p.get('date', ''))[:10] <= date]
        if not points:
            continue
        point = points[-1]
        # 同优先级取日期更新的；不同优先级按 rank 胜出（现货价 > 收盘价 > …）
        if best is None or (_rank == best[0] and point['date'] > best[1]['date']) or _rank < best[0]:
            best = (_rank, point, indicator, source)
    if best is None:
        return None
    return {'value': best[1]['value'], 'date': str(best[1]['date'])[:10],
            'indicator': best[2], 'source': best[3]}


def _outcome(direction: str, change_pct: float) -> str:
    if direction == '看多':
        if change_pct >= SETTLE_THRESHOLD:
            return '正确'
        if change_pct <= -SETTLE_THRESHOLD:
            return '错误'
        return '持平'
    if direction == '看空':
        if change_pct <= -SETTLE_THRESHOLD:
            return '正确'
        if change_pct >= SETTLE_THRESHOLD:
            return '错误'
        return '持平'
    return '正确' if abs(change_pct) < SETTLE_THRESHOLD else '错误'


def settle(s, vp: Viewpoint) -> bool:
    """到期自动结算；返回是否发生状态翻转。无价格数据标记「无法结算」。"""
    if vp.status != '在途' or not vp.expire_date or vp.expire_date > _today():
        return False
    point = price_on(s, vp.commodity, vp.expire_date)
    if point is None or vp.benchmark_price in (None, 0):
        vp.outcome = '无法结算'
        vp.note = ('缺少基准价' if vp.benchmark_price in (None, 0)
                   else '指标库中没有该品种在结算日前可用的价格数据')
        vp.status = '已结算'
        vp.settled_at = _stamp()
        return True
    change = round((point['value'] - vp.benchmark_price) / vp.benchmark_price * 100, 2)
    vp.result_price = point['value']
    vp.result_date = point['date']
    vp.change_pct = change
    vp.outcome = _outcome(vp.direction or '', change)
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
    return {'items': [_dict(x) for x in rows], 'threshold': SETTLE_THRESHOLD}


@router.post('', summary='登记一条研究观点')
async def create_viewpoint(request: Request, session: Session = Depends(get_session)):
    import app as platform
    user = _auth(request, session)
    if user['role'] not in ('admin', 'researcher'):
        raise platform.ApiError(403, '仅研究人员与管理员可登记观点')
    data = await _body(request)
    commodity = str(data.get('commodity') or '').strip()
    direction = str(data.get('direction') or '').strip()
    basis = str(data.get('basis') or '').strip()[:_MAX_BASIS]
    horizon = int(data.get('horizon_days') or 5)
    if direction not in DIRECTIONS:
        raise platform.ApiError(400, '方向必须是：' + '、'.join(DIRECTIONS))
    row = session.execute(select(Commodity).where(Commodity.name == commodity)).scalars().first()
    if not row:
        raise platform.ApiError(400, '品种不存在：' + commodity)
    if not 1 <= horizon <= 90:
        raise platform.ApiError(400, '观察期需在 1~90 个自然日之间')

    benchmark_date = _today()
    point = price_on(session, commodity, benchmark_date)
    benchmark_price = data.get('benchmark_price')
    if benchmark_price in (None, ''):
        if point is None:
            raise platform.ApiError(400, '指标库中没有该品种的价格数据，请手工填写基准价')
        benchmark_price = point['value']
    else:
        try:
            benchmark_price = float(benchmark_price)
        except Exception:
            raise platform.ApiError(400, '基准价需为数字')
        point = None
    expire = (datetime.date.today() + datetime.timedelta(days=horizon)).isoformat()
    vp = Viewpoint(user_id=user['id'], user_name=user['name'], commodity=commodity,
                   direction=direction, basis=basis,
                   benchmark_price=benchmark_price, benchmark_date=benchmark_date,
                   horizon_days=horizon, expire_date=expire,
                   benchmark_indicator=point['indicator'] if point else '（手工填写）',
                   status='在途', created_at=_stamp())
    session.add(vp)
    session.commit()
    return {'item': _dict(vp)}


@router.post('/settle', summary='立即结算一条观点（不足观察期也可提前对照当前价）')
async def settle_viewpoint(request: Request, session: Session = Depends(get_session)):
    import app as platform
    user = _auth(request, session)
    data = await _body(request)
    vp = session.get(Viewpoint, int(data.get('id') or 0))
    if not vp:
        raise platform.ApiError(404, '观点不存在')
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
    if vp.user_id != user['id'] and user['role'] != 'admin':
        raise platform.ApiError(403, '仅本人或管理员可删除')
    session.delete(vp)
    session.commit()
    return {'ok': True}


@router.get('/stats', summary='准确率统计与研究员画像（按人、按品种）')
def viewpoint_stats(request: Request, session: Session = Depends(get_session)):
    _auth(request, session)
    settle_due(session)
    rows = session.execute(select(Viewpoint).where(Viewpoint.status == '已结算')).scalars().all()
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

    return {
        'overall': {'settled': len(settled),
                    'pending': int(session.execute(select(func.count()).select_from(Viewpoint)
                                                   .where(Viewpoint.status == '在途')).scalar()),
                    'unavailable': len([x for x in rows if x.outcome == '无法结算']),
                    'accuracy': (round(len([x for x in settled if x.outcome == '正确'])
                                       / len(settled) * 100, 1) if settled else None),
                    'threshold': SETTLE_THRESHOLD},
        'by_user': bucket(lambda x: x.user_name or ''),
        'by_commodity': bucket(lambda x: x.commodity or ''),
    }
