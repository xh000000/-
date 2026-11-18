"""研究数据的来源、同步作业与幂等入库。

为什么拆成「取数」和「入库」
--------------------------
同花顺 iFinD 与 Wind 都是授权数据：本机的凭据由 WorkBuddy 连接器托管（加密、绑定桌面
登录），服务端既拿不到、也不该代持。所以这个模块不去「假装有接口」，而是把两端分开：

- 取数：由已授权通道完成——助手用同花顺/Wind 连接器，或生产环境用 WindPy / iFinD API，
  统一产出 ``source, indicator, date, value, unit`` 观测行；
- 入库：本模块负责幂等写入（同一来源 + 指标 + 日期只留一行）、来源统计与同步作业。

页面上的「同步」因此做的是登记作业，``sync_worker.py`` 执行回填；换通道不影响页面与库。
"""
from __future__ import annotations

import datetime
import json
import math

from sqlalchemy import func, select, update, or_, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db import DataSource, DataSourceConfig, DataSyncJob, Observation, has_flag, set_flag

# 内置来源：仅在 data_sources 表里没有时补种，之后以表为准（页面可再加别家）
SEED_SOURCES = [
    {'key': 'eastmoney', 'name': '东方财富', 'product': '公开指数最新行情',
     'channel': '最新行情快照：上证指数、深证成指、沪深300；最新点位与成交量（非历史日线）',
     'scope_mode': 'custom', 'scope_items': ['上证指数', '深证成指', '沪深300']},
    {'key': 'sina', 'name': '新浪财经', 'product': '公开指数日线',
     'channel': '公开行情：上证指数、深证成指、沪深300；收盘点位与成交量',
     'scope_mode': 'custom', 'scope_items': ['上证指数', '深证成指', '沪深300']},
    {'key': 'ifind', 'name': '同花顺', 'product': 'iFinD',
     'channel': 'WorkBuddy 连接器（期货期权 / 行业经济指标）',
     'scope_mode': 'commodity', 'scope_items': []},
    {'key': 'wind', 'name': 'Wind', 'product': 'Wind 金融终端',
     'channel': 'WorkBuddy 连接器（EDB 宏观 / 行业指标）',
     'scope_mode': 'custom',
     'scope_items': ['南华商品指数', '南华工业品指数', '南华农产品指数',
                     '螺纹钢现货价', '铁矿石港口库存']},
]
SOURCES = SEED_SOURCES  # 兼容旧引用；业务请用 sources(session)

# 可同步的指标：key 用于作业范围，label 与单位用于指标命名（如「螺纹钢收盘价」）
METRICS = [
    {'key': 'index_last', 'label': '最新点位', 'unit': '点'},
    {'key': 'close', 'label': '收盘价', 'unit': '元/吨'},
    {'key': 'settle', 'label': '结算价', 'unit': '元/吨'},
    {'key': 'volume', 'label': '成交量', 'unit': '手'},
    {'key': 'open_interest', 'label': '持仓量', 'unit': '手'},
    {'key': 'spot', 'label': '现货价', 'unit': '元/吨'},
    {'key': 'inventory', 'label': '库存', 'unit': '万吨'},
    {'key': 'index_close', 'label': '收盘点位', 'unit': '点'},
]

METRIC_LABELS = {m['key']: m['label'] for m in METRICS}
SOURCE_NAMES = {s['key']: s['name'] for s in SEED_SOURCES}


def _scope_items(raw) -> list[str]:
    try:
        value = json.loads(raw or '[]')
        return [str(x) for x in value] if isinstance(value, list) else []
    except Exception:
        return []


def ensure_sources(session) -> None:
    """内置两家按需补种；已存在的记录不覆盖（用户可以自己改说明或停用）。"""
    existing = {row.key for row in session.execute(select(DataSource)).scalars()}
    for item in SEED_SOURCES:
        if item['key'] in existing:
            continue
        session.add(DataSource(
            key=item['key'], name=item['name'], product=item['product'], channel=item['channel'],
            scope_mode=item.get('scope_mode', 'commodity'),
            scope_items=json.dumps(item.get('scope_items') or [], ensure_ascii=False),
            enabled=1, builtin=1, created_at=''))
        if item['key'] in ('eastmoney', 'sina'):
            from feeds import PUBLIC_URLS
            kind = 'eastmoney_snapshot' if item['key'] == 'eastmoney' else 'sina_index'
            session.add(DataSourceConfig(
                name=item['name'] + (' · 最新指数快照' if item['key'] == 'eastmoney' else ' · 指数日线'), source=item['key'], kind=kind,
                base_url=PUBLIC_URLS[kind], account='', secret='',
                scope=json.dumps({'items': item['scope_items'], 'metrics': ['index_last' if item['key'] == 'eastmoney' else 'index_close', 'volume'], 'days': 10}),
                options='{}', freq='manual', enabled=1, operator='system', created_at=''))
    session.flush()


def sources(session, include_disabled: bool = False) -> list[dict]:
    """来源清单（含页面新增的）。入库标签是 name，接口里 key 与 name 都认。"""
    rows = session.execute(select(DataSource).order_by(DataSource.id)).scalars().all()
    result = []
    for row in rows:
        if not include_disabled and not row.enabled:
            continue
        result.append({
            'id': row.id, 'key': row.key, 'name': row.name,
            'product': row.product or '', 'channel': row.channel or '',
            'scope_mode': row.scope_mode or 'commodity',
            'scope_items': _scope_items(row.scope_items),
            'enabled': 1 if row.enabled else 0, 'builtin': 1 if row.builtin else 0,
        })
    return result


def source_names(session) -> dict:
    return {item['key']: item['name'] for item in sources(session, include_disabled=True)}


def source_key(session, value: str) -> str:
    """把 key 或中文名统一成 key；不认识返回空串。"""
    text = str(value or '').strip()
    for item in sources(session, include_disabled=True):
        if text in (item['key'], item['name']):
            return item['key']
    return ''


def metric_of(indicator: str) -> str:
    """按指标名反推指标类型，用于页面归类（螺纹钢收盘价 → close）。"""
    for item in METRICS:
        if indicator.endswith(item['label']):
            return item['key']
    return ''


def _value(raw) -> float:
    """数值化的唯一入口：去掉千分位、全角符号，拒绝 NaN / inf。"""
    text = str(raw).strip().replace(',', '').replace('，', '')
    value = float(text)
    if not math.isfinite(value):
        raise ValueError('数值必须有限')
    return value


def normalize(rows) -> list[dict]:
    """校验并标准化请求里的观测行，整批失败即整批不入库。"""
    if not isinstance(rows, list) or not rows:
        raise ValueError('需要至少一行数据')
    if len(rows) > 10000:
        raise ValueError('单次最多 10000 行')
    cleaned = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError('第 %s 行不是对象' % index)
        source = str(row.get('source') or '').strip()
        indicator = str(row.get('indicator') or '').strip()
        date = str(row.get('date') or '').strip()
        unit = str(row.get('unit') or '').strip()
        if not source or not indicator or not date or not unit:
            raise ValueError('第 %s 行缺少 source / indicator / date / unit' % index)
        try:
            day = datetime.date.fromisoformat(date).isoformat()
        except Exception:
            raise ValueError('第 %s 行日期需为 YYYY-MM-DD：%s' % (index, date))
        cleaned.append({'source': source[:40], 'indicator': indicator[:120], 'date': day,
                        'value': _value(row.get('value')), 'unit': unit[:20]})
    return cleaned


def migrate_observation_uniqueness(session) -> int:
    """清理存量重复，保留 ID 最大的一条，并为并发写入建立唯一约束。"""
    if has_flag(session, 'observation-unique-v1'):
        return 0
    names = source_names(session)
    aliases = {**names, **{name: name for name in names.values()}}
    seen, removed, survivors = set(), 0, []
    for row in session.scalars(select(Observation).order_by(Observation.id.desc())):
        source = str(row.source or '').strip()
        source = aliases.get(source, source)
        indicator, date = str(row.indicator or '').strip(), str(row.date or '').strip()
        key = (source, indicator, date)
        if key in seen:
            session.delete(row)
            removed += 1
        else:
            seen.add(key)
            survivors.append((row, key))
    session.flush()
    for row, key in survivors:
        row.source, row.indicator, row.date = key
    session.flush()
    session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_observation_point '
                         'ON observations (source, indicator, date)'))
    set_flag(session, 'observation-unique-v1')
    return removed


def apply(session, rows: list[dict], operator: str) -> dict:
    """按来源、指标、日期幂等写入；批内最后一条有效记录优先，数据库兜底去重。"""
    if not rows:
        return {'inserted': 0, 'updated': 0, 'skipped': 0, 'total': 0}
    names = source_names(session)
    aliases = {**names, **{name: name for name in names.values()}}
    unique = {}
    for row in rows:
        source = str(row['source']).strip()
        key = (aliases.get(source, source), str(row['indicator']).strip(), row['date'])
        unique[key] = {**row, 'source': key[0], 'indicator': key[1]}
    inserted = updated = 0
    skipped = len(rows) - len(unique)
    for row in unique.values():
        point = {k: row[k] for k in ('source', 'indicator', 'date', 'value', 'unit')}
        result = session.execute(sqlite_insert(Observation).values(**point, uploaded_by=operator)
                                 .on_conflict_do_nothing(index_elements=['source', 'indicator', 'date'])
                                 .returning(Observation.id)).scalar_one_or_none()
        if result is not None:
            inserted += 1
            continue
        changed = session.execute(update(Observation).where(
            Observation.source == row['source'], Observation.indicator == row['indicator'],
            Observation.date == row['date'],
            or_(Observation.value.is_(None), func.abs(Observation.value - row['value']) >= 1e-9,
                Observation.unit.is_(None), Observation.unit != row['unit'])
        ).values(value=row['value'], unit=row['unit'], uploaded_by=operator))
        if changed.rowcount:
            updated += 1
        else:
            skipped += 1
    return {'inserted': inserted, 'updated': updated, 'skipped': skipped, 'total': len(rows)}


def stats(session) -> list[dict]:
    """按来源汇总：条数、指标数、最新日期、最近一次成功同步的时间。"""
    rows = session.execute(
        select(Observation.source, func.count(), func.count(func.distinct(Observation.indicator)),
               func.max(Observation.date))
        .group_by(Observation.source)).all()
    counters = {r[0]: r for r in rows}
    last = {}
    for source, at in session.execute(
            select(DataSyncJob.source, func.max(DataSyncJob.finished_at))
            .where(DataSyncJob.status == '已完成').group_by(DataSyncJob.source)).all():
        last[source] = at
    result = []
    for item in sources(session):
        hit = counters.get(item['name']) or counters.get(item['key'])
        result.append({
            **item,
            'rows': int(hit[1]) if hit else 0,
            'indicators': int(hit[2]) if hit else 0,
            'latest': (hit[3] or '') if hit else '',
            'last_sync': last.get(item['key']) or '',
        })
    return result


def catalog(session, source: str = '', keyword: str = '') -> list[dict]:
    """指标目录：把观测行按「来源 + 指标 + 单位」归拢成一行，供指标查询页使用。

    带上起止日期、首末值、区间涨跌，让人不点进去也能判断这条序列是否可用。
    """
    stmt = select(Observation.source, Observation.indicator, Observation.unit,
                  Observation.date, Observation.value)
    if source:
        # 库里 source 存的是来源中文名；入参可能是 key，也可能直接是中文名，两种都认
        names = source_names(session)
        stmt = stmt.where(Observation.source.in_(
            [source, source_key(session, source), names.get(source_key(session, source), '')]))
    if keyword:
        stmt = stmt.where(Observation.indicator.contains(keyword))
    buckets: dict[tuple, dict] = {}
    for row in session.execute(stmt.order_by(Observation.date)):
        key = (row.source or '', row.indicator or '', row.unit or '')
        item = buckets.get(key)
        if item is None:
            buckets[key] = {
                'source': key[0], 'indicator': key[1], 'unit': key[2],
                'points': 1, 'first_date': row.date, 'last_date': row.date,
                'first_value': row.value, 'last_value': row.value,
                'min_value': row.value, 'max_value': row.value,
            }
            continue
        item['points'] += 1
        item['last_date'] = row.date
        item['last_value'] = row.value
        if row.value is not None:
            item['min_value'] = row.value if item['min_value'] is None else min(item['min_value'], row.value)
            item['max_value'] = row.value if item['max_value'] is None else max(item['max_value'], row.value)
    result = []
    for item in buckets.values():
        first, last = item['first_value'], item['last_value']
        item['change'] = round(last - first, 6) if None not in (first, last) else None
        item['change_pct'] = (round((last - first) / first * 100, 2)
                              if first not in (None, 0) and last is not None else None)
        item['metric'] = metric_of(item['indicator'])
        result.append(item)
    result.sort(key=lambda x: (x['source'], x['indicator']))
    return result


def series(session, source: str, indicator: str, start: str = '', end: str = '') -> dict:
    """单条指标的连续序列。按日期升序返回，附带区间统计。"""
    names = source_names(session)
    key = source_key(session, source)
    stmt = select(Observation).where(
        Observation.source.in_([source, key, names.get(key, '')]),
        Observation.indicator == indicator)
    if start:
        stmt = stmt.where(Observation.date >= start)
    if end:
        stmt = stmt.where(Observation.date <= end)
    rows = session.execute(stmt.order_by(Observation.date)).scalars().all()
    points = [{'date': row.date, 'value': row.value, 'unit': row.unit,
               'uploaded_by': row.uploaded_by} for row in rows]
    values = [p['value'] for p in points if p['value'] is not None]
    change = round(values[-1] - values[0], 6) if len(values) > 1 else None
    return {
        'source': source, 'indicator': indicator,
        'unit': points[0]['unit'] if points else '',
        'points': points,
        'stats': {
            'count': len(points), 'first_date': points[0]['date'] if points else '',
            'last_date': points[-1]['date'] if points else '',
            'last_value': values[-1] if values else None,
            'min_value': min(values) if values else None,
            'max_value': max(values) if values else None,
            'avg_value': round(sum(values) / len(values), 4) if values else None,
            'change': change,
            'change_pct': (round(change / values[0] * 100, 2)
                           if change is not None and values[0] else None),
        },
    }


def job_dict(job, names: dict | None = None) -> dict:
    item = job.to_dict()
    try:
        item['scope'] = json.loads(item.get('scope') or '{}')
    except Exception:
        item['scope'] = {}
    mapping = names or SOURCE_NAMES
    item['source_name'] = mapping.get(item.get('source'), item.get('source') or '')
    return item


_job_dict = job_dict  # 兼容旧调用


def pending(session) -> list[dict]:
    jobs = session.execute(select(DataSyncJob).where(DataSyncJob.status == '待执行')
                           .order_by(DataSyncJob.id)).scalars().all()
    names = source_names(session)
    return [job_dict(job, names) for job in jobs]


def jobs(session, limit: int = 10) -> list[dict]:
    items = session.execute(select(DataSyncJob).order_by(DataSyncJob.id.desc()).limit(limit)).scalars()
    names = source_names(session)
    return [job_dict(job, names) for job in items]


def create_job(session, data: dict, user, at: str) -> dict:
    """登记同步范围。items 是「品种」或「指数/指标名」，随来源不同而不同。"""
    source = source_key(session, data.get('source'))
    if not source:
        raise ValueError('数据来源不存在或已停用')
    items = [str(x).strip() for x in (data.get('items') or data.get('commodities') or [])
             if str(x).strip()]
    metrics = [str(x).strip() for x in (data.get('metrics') or []) if str(x).strip()]
    if not items:
        raise ValueError('请至少选择一个品种或指标')
    if len(items) > 40:
        raise ValueError('单次最多选择 40 个品种/指标')
    unknown = [m for m in metrics if m not in METRIC_LABELS]
    if unknown:
        raise ValueError('未知指标：' + '、'.join(unknown))
    if source == 'ifind' and not metrics:
        raise ValueError('同花顺行情至少选择一个指标')
    days = int(data.get('days') or 10)
    if days < 1 or days > 120:
        raise ValueError('区间需在 1 至 120 个交易日之间')
    job = DataSyncJob(source=source, status='待执行', rows=0, inserted=0, updated=0,
                      operator=user['name'], created_at=at, finished_at='', message='',
                      scope=json.dumps({'items': items, 'metrics': metrics, 'days': days},
                                       ensure_ascii=False))
    session.add(job)
    session.flush()
    return job_dict(job)


def fail_job(session, job: DataSyncJob, at: str, message: str) -> None:
    """取数通道明确回不来时也要落状态，免得作业永远挂在「待执行」上。"""
    job.status = '失败'
    job.rows = 0
    job.finished_at = at
    job.message = message[:500]


def finish_job(session, job: DataSyncJob, counts: dict, at: str, message: str = '') -> None:
    job.status = '已完成'
    job.rows = counts.get('total', 0)
    job.inserted = counts.get('inserted', 0)
    job.updated = counts.get('updated', 0)
    job.finished_at = at
    job.message = message[:500]
