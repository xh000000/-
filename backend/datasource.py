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
import re

from sqlalchemy import func, inspect, select, update, or_, text
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


def _insert_ignore(session, values: dict) -> bool:
    """幂等写入一条观测，命中唯一键就跳过；返回是否真的插进去了。

    三种库的写法互不兼容，这里按方言分开：

    - SQLite / PostgreSQL：``ON CONFLICT DO NOTHING`` 再靠 ``RETURNING`` 判断有没有插入；
    - MySQL：既没有 ``ON CONFLICT`` 也没有 ``RETURNING``，只能用 ``INSERT IGNORE`` 看
      rowcount。代价是 IGNORE 会连带吞掉截断之类的其它告警，但入库前已经做过长度与
      数值清洗，这里只可能是唯一键冲突。
    """
    dialect = session.get_bind().dialect.name
    if dialect == 'mysql':
        result = session.execute(mysql.insert(Observation).prefix_with('IGNORE').values(**values))
        return result.rowcount == 1
    builder = postgresql if dialect == 'postgresql' else sqlite
    inserted = session.execute(
        builder.insert(Observation).values(**values)
        .on_conflict_do_nothing(index_elements=['source', 'indicator', 'date'])
        .returning(Observation.id)
    ).scalar_one_or_none()
    return inserted is not None


def _ensure_unique_index(session, name: str, table: str, columns: str) -> None:
    """建立唯一索引，已存在则跳过。MySQL 没有 ``CREATE INDEX IF NOT EXISTS``。"""
    bind = session.get_bind()
    if bind.dialect.name == 'mysql':
        existing = {index['name'] for index in inspect(bind).get_indexes(table)}
        if name in existing:
            return
        session.execute(text('CREATE UNIQUE INDEX %s ON %s (%s)' % (name, table, columns)))
        return
    session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s (%s)'
                         % (name, table, columns)))

from db import (
    Commodity, DataSource, DataSourceConfig, DataScopePreset, DataSyncJob, DimGroup, DimIndicator,
    Observation, Viewpoint, add_columns, has_flag, set_flag,
)

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
    {'key': 'mysteel', 'name': '钢联 Mysteel', 'product': '我的钢铁网 · 钢材数据',
     'channel': 'Mysteel 终端账号导出 / CSV 导入（现货价、库存、产量、开工率）',
     'scope_mode': 'custom',
     'scope_items': ['螺纹钢现货价', '热轧卷板现货价', '螺纹钢社会库存', '高炉开工率']},
    {'key': 'smm', 'name': 'SMM 上海有色网', 'product': 'SMM 金属现货数据',
     'channel': 'SMM 终端 / WorkBuddy SMM 连接器（基本金属现货均价、库存、升贴水）',
     'scope_mode': 'custom',
     'scope_items': ['电解铜现货价', '电解铝现货价', '锌锭现货价', '镍板现货价',
                     '阴极铜社会库存', '铝锭社会库存']},
    {'key': 'longzhong', 'name': '隆众资讯', 'product': '隆众能源化工数据',
     'channel': '隆众终端账号导出 / CSV 导入（能化现货价、开工率、库存）',
     'scope_mode': 'custom',
     'scope_items': ['甲醇现货价', 'PTA现货价', '乙二醇现货价', '聚丙烯拉丝现货价',
                     '炼厂开工率']},
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
    {'key': 'operation_rate', 'label': '开工率', 'unit': '%'},
    {'key': 'basis', 'label': '升贴水', 'unit': '元/吨'},
    {'key': 'index_close', 'label': '收盘点位', 'unit': '点'},
]

METRIC_LABELS = {m['key']: m['label'] for m in METRICS}
SOURCE_NAMES = {s['key']: s['name'] for s in SEED_SOURCES}

# 候选清单预置库：自定义范围时直接勾选，不必手打；命名都带可归类的指标后缀
SCOPE_PRESETS = [
    {'group': '现货价', 'items': [
        '螺纹钢现货价', '热轧卷板现货价', '铁矿石现货价', '焦炭现货价',
        '电解铜现货价', '电解铝现货价', '氧化铝现货价', '锌锭现货价', '镍板现货价',
        '甲醇现货价', 'PTA现货价', '乙二醇现货价', '聚丙烯拉丝现货价', 'PVC现货价',
    ]},
    {'group': '库存', 'items': [
        '螺纹钢社会库存', '热轧卷板社会库存', '铁矿石港口库存',
        '阴极铜社会库存', '铝锭社会库存', '锌锭社会库存',
        '甲醇港口库存', '乙二醇港口库存',
    ]},
    {'group': '开工率', 'items': ['高炉开工率', '电炉开工率', '炼厂开工率', '甲醇开工率', 'PTA开工率']},
    {'group': '指数', 'items': ['南华商品指数', '南华工业品指数', '南华农产品指数', '南华能化指数', '南华金属指数']},
    {'group': '升贴水', 'items': ['电解铜升贴水', '电解铝升贴水', '锌锭升贴水']},
]

_GROUP_ORDER = [g['group'] for g in SCOPE_PRESETS]


def ensure_scope_presets(session) -> None:
    """【历史】只在老库还没有主数据表内容时，把 SCOPE_PRESETS 补种进 data_scope_presets。

    真正的初始数据现在由 ``migrate_dictionary`` 从这张表搬到 dim_groups / dim_indicators。
    """
    count = session.execute(select(func.count()).select_from(DataScopePreset)).scalar()
    if count:
        return
    position = 0
    for group in SCOPE_PRESETS:
        for item in group['items']:
            session.add(DataScopePreset(group_name=group['group'], item=item, position=position))
            position += 1
    session.flush()


# --------------------------------------------------------------------------
# 指标主数据（dim_groups / dim_indicators）
#
# 为什么要有它：v1 用「分组名 + 指标名」两列裸文本描述指标，改名就把历史数据切成两段，
# 分组也没有身份、空分组存不住。现在按行业指标体系规范落地——编码与名称双轨：
#   code 稳定、发布后不复用；name 可改；改名只动显示名，id 不变，历史数据不断链。
# --------------------------------------------------------------------------
UNGROUPED = '未分组'


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + ' UTC'


def ensure_group(session, name: str, code: str = '') -> DimGroup:
    """按名字取分组，不存在就建。『未分组』是系统组，供未归类的指标兜底。

    ``code`` 为空则自动生成一个（GRP00001 起）；给了就校验唯一性——人工填的编码
    与外部系统对齐时用得上。并发写入（多线程导入 CSV）时两个线程可能同时判定
    「不存在」，所以插入走 ON CONFLICT DO NOTHING 再回查，避免撞 name 唯一约束。
    """
    name = str(name or '').strip()
    row = session.execute(select(DimGroup).where(DimGroup.name == name)).scalar_one_or_none()
    if row:
        return row
    code = normalize_code(code)
    if code:
        taken = _code_taken(session, DimGroup, code)
        if taken:
            raise ValueError('编码 %s 已被分组「%s」占用，请换一个' % (code, taken.name))
    last = session.execute(select(func.max(DimGroup.position))).scalar() or 0
    session.execute(sqlite_insert(DimGroup)
                    .values(name=name, code=code or None, position=last + 1,
                            builtin=1 if name == UNGROUPED else 0, created_at=_now())
                    .on_conflict_do_nothing(index_elements=['name']))
    session.flush()
    row = session.execute(select(DimGroup).where(DimGroup.name == name)).scalar_one()
    # 没指定编码就按已发放的最大号往后排，编码发布后不再变化
    if not row.code:
        row.code = next_code(session, DimGroup, GROUP_CODE_PREFIX)
        session.flush()
    return row


def ungrouped_id(session) -> int:
    return ensure_group(session, UNGROUPED).id


# 编码规范：字母数字加 _ - /，2-20 位。行业惯例是「编码稳定、名称可变」，
# 所以编码允许人工指定（对接外部系统时往往是对方给的号），但必须全局唯一。
CODE_RE = re.compile(r'^[A-Z0-9][A-Z0-9_\-/]{1,19}$')
GROUP_CODE_PREFIX = 'GRP'
ITEM_CODE_PREFIX = 'IND'


def normalize_code(raw) -> str:
    """编码统一大写去空格；空值表示「自动生成」。"""
    code = str(raw or '').strip().upper()
    if not code:
        return ''
    if not CODE_RE.match(code):
        raise ValueError('编码只能用字母、数字与 _ - /，2-20 位；当前为「%s」' % code)
    return code


def _code_taken(session, model, code: str, exclude_id=None):
    stmt = select(model).where(model.code == code)
    if exclude_id:
        stmt = stmt.where(model.id != int(exclude_id))
    return session.execute(stmt).scalar_one_or_none()


def next_code(session, model, prefix: str) -> str:
    """按「已发放的最大编号 + 1」生成，而不是按 id —— 手工填过的编码可能落在前面，
    用 id 推算会撞唯一约束。"""
    numbers = []
    for (code,) in session.execute(select(model.code).where(model.code.like(prefix + '%'))):
        tail = str(code or '')[len(prefix):]
        if tail.isdigit():
            numbers.append(int(tail))
    return '%s%05d' % (prefix, (max(numbers) + 1) if numbers else 1)


def set_indicator_code(session, indicator_id: int, code) -> DimIndicator:
    """改指标编码。编码是给人对接用的稳定标识，改之前先确认没被别的指标占着。"""
    row = find_indicator(session, indicator_id)
    code = normalize_code(code)
    if not code:
        raise ValueError('编码不能为空')
    if code == row.code:
        return row
    taken = _code_taken(session, DimIndicator, code, row.id)
    if taken:
        raise ValueError('编码 %s 已被「%s」占用，请换一个' % (code, taken.name))
    row.code = code
    row.updated_at = _now()
    return row


def set_group_code(session, group_id: int, code) -> DimGroup:
    group = find_group(session, group_id)
    code = normalize_code(code)
    if not code:
        raise ValueError('编码不能为空')
    if code == group.code:
        return group
    taken = _code_taken(session, DimGroup, code, group.id)
    if taken:
        raise ValueError('编码 %s 已被分组「%s」占用，请换一个' % (code, taken.name))
    group.code = code
    return group


def check_commodity(session, name) -> str:
    """品种只能取自品种管理（commodities 表）里已有的名字；空值表示不指定。

    指标上的品种是给选题、章节关联用的维度，不能是自由文本——否则「螺纹钢」和
    「螺纹」会变成两个品种，品种库再也对不上。
    """
    name = str(name or '').strip()[:40]
    if not name:
        return ''
    known = {row[0] for row in session.execute(select(Commodity.name))}
    if name not in known:
        raise ValueError('品种「%s」不在品种管理里，请先到品种管理添加' % name)
    return name


def set_indicator_commodity(session, indicator_id: int, commodity) -> DimIndicator:
    row = find_indicator(session, indicator_id)
    row.commodity = check_commodity(session, commodity)
    row.updated_at = _now()
    return row


def ensure_indicator(session, name: str, group_id: int | None = None,
                     code: str = '', commodity=None) -> DimIndicator:
    """按名字取指标，不存在就建。写入观测数据时调用，保证每条数据都挂得住主数据。

    ``commodity`` 为 None 时按名字自动推断（导入数据的老路径）；给了值就按值写，
    空字符串表示明确不挂品种。
    """
    name = str(name or '').strip()
    row = session.execute(select(DimIndicator).where(DimIndicator.name == name)).scalar_one_or_none()
    if row:
        return row
    code = normalize_code(code)
    if code:
        taken = _code_taken(session, DimIndicator, code)
        if taken:
            raise ValueError('编码 %s 已被「%s」占用，请换一个' % (code, taken.name))
    commodity_name = infer_commodity(session, name) if commodity is None else check_commodity(session, commodity)
    last = session.execute(select(func.max(DimIndicator.position))).scalar() or 0
    session.execute(sqlite_insert(DimIndicator)
                    .values(name=name, code=code or None, group_id=group_id or ungrouped_id(session),
                            commodity=commodity_name, aliases='[]', unit='',
                            enabled=1, position=last + 1, created_at=_now(), updated_at=_now())
                    .on_conflict_do_nothing(index_elements=['name']))
    session.flush()
    row = session.execute(select(DimIndicator).where(DimIndicator.name == name)).scalar_one()
    if not row.code:
        row.code = next_code(session, DimIndicator, ITEM_CODE_PREFIX)
    return row


# 行业惯用叫法 → 品种库标准名。指标名里常写全称（电解铜、热轧卷板），
# 品种库里用的是简称（铜、热卷），差别不该让品种维度留空。
COMMODITY_ALIASES = {
    '热轧卷板': '热卷', '热轧板卷': '热卷', '热轧': '热卷',
    '电解铜': '铜', '阴极铜': '铜', '铜精矿': '铜',
    '电解铝': '铝', '铝锭': '铝', '氧化铝粉': '氧化铝',
    '镍板': '镍', '电解镍': '镍', '镍铁': '镍',
    '聚氯乙烯': 'PVC', '聚丙烯拉丝': 'PP',
}


def _parse_aliases(raw) -> list[str]:
    """品种别名：字典表里存 JSON 数组，兼容早期逗号分隔的写法。"""
    if not raw:
        return []
    text = str(raw).strip()
    if text.startswith('['):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return []
        return [str(x).strip() for x in data if str(x).strip()] if isinstance(data, list) else []
    return [part.strip() for part in re.split(r'[,，]', text) if part.strip()]


def infer_commodity(session, name: str) -> str:
    """从指标名里拆品种：先查字典表别名（含行业补充），再按品种库做最长前缀匹配。

    行业规范里「品种 + 指标类型」是两个维度，名字只是拼出来的显示串；这里能把常见的
    自动拆出来（螺纹钢现货价 → 螺纹钢），拆不出的（上证指数、南华商品指数）留空，
    因为那属于指数而不是商品，硬套品种反而错。
    """
    text = str(name or '')
    rows = list(session.execute(select(Commodity.name, Commodity.aliases)))
    known = [row[0] for row in rows if row[0]]
    mapping = dict(COMMODITY_ALIASES)
    for commodity, raw in rows:
        if not commodity:
            continue
        for alias in _parse_aliases(raw):
            if alias and alias != commodity:
                mapping[alias] = commodity
    for alias, commodity in sorted(mapping.items(), key=lambda item: -len(item[0])):
        if commodity in known and text.startswith(alias):
            return commodity
    best = ''
    for commodity in known:
        if len(commodity) > len(best) and text.startswith(commodity):
            best = commodity
    return best


def migrate_dictionary(session) -> dict:
    """把历史数据里的「裸名字」提升为主数据。全程按名字 upsert，可反复执行。

    三步：老预置库 → 分组 + 指标；观测数据里出现过的指标名 → 未分组；回填 indicator_id。
    """
    add_columns(session, 'observations', {'indicator_id': 'INTEGER'})
    add_columns(session, 'dim_groups', {'code': "TEXT DEFAULT ''"})
    groups_before = session.execute(select(func.count()).select_from(DimGroup)).scalar() or 0
    items_before = session.execute(select(func.count()).select_from(DimIndicator)).scalar() or 0

    # 老分组没有编码：按 id 顺序补上，编码即创建先后
    for row in session.execute(select(DimGroup).where(
            or_(DimGroup.code.is_(None), DimGroup.code == ''))).scalars():
        row.code = 'GRP%05d' % row.id

    for row in session.execute(select(DataScopePreset)
                               .order_by(DataScopePreset.position, DataScopePreset.id)).scalars():
        group = ensure_group(session, str(row.group_name).strip())
        ensure_indicator(session, str(row.item).strip(), group.id)

    for (name,) in session.execute(select(Observation.indicator).distinct()):
        if str(name or '').strip():
            ensure_indicator(session, str(name).strip())

    # 品种维度兜底回填：老指标建得早，commodity 还是空的
    for row in session.execute(select(DimIndicator).where(
            or_(DimIndicator.commodity.is_(None), DimIndicator.commodity == ''))).scalars():
        row.commodity = infer_commodity(session, row.name)

    session.execute(text(
        'UPDATE observations SET indicator_id = ('
        ' SELECT id FROM dim_indicators WHERE dim_indicators.name = observations.indicator)'
        ' WHERE indicator_id IS NULL'))
    session.execute(text('CREATE INDEX IF NOT EXISTS ix_observations_indicator_id '
                         'ON observations (indicator_id)'))
    groups_after = session.execute(select(func.count()).select_from(DimGroup)).scalar() or 0
    items_after = session.execute(select(func.count()).select_from(DimIndicator)).scalar() or 0
    return {'groups': groups_after - groups_before, 'items': items_after - items_before,
            'backfilled': session.execute(select(func.count()).select_from(Observation)
                                          .where(Observation.indicator_id.isnot(None))).scalar() or 0}


def dictionary(session, include_disabled: bool = False) -> list[dict]:
    """指标树：一级分组带 id（空分组也会出现），二级是指标条目。

    同时给出 ``items``（名字数组，兼容数据源配置页的下拉）和 ``entries``（带 id 的条目）。
    """
    groups = session.execute(select(DimGroup).order_by(DimGroup.position, DimGroup.id)).scalars().all()
    buckets: dict[int, list[dict]] = {group.id: [] for group in groups}
    for row in session.execute(select(DimIndicator)
                               .order_by(DimIndicator.position, DimIndicator.id)).scalars():
        if not include_disabled and not row.enabled:
            continue
        buckets.setdefault(row.group_id, []).append({
            'id': row.id, 'code': row.code or '', 'item': row.name, 'name': row.name,
            'commodity': row.commodity or '', 'unit': row.unit or '',
            'aliases': _scope_items(row.aliases), 'enabled': bool(row.enabled),
        })
    library = []
    for group in groups:
        entries = buckets.get(group.id, [])
        library.append({
            'id': group.id, 'code': group.code or '', 'group': group.name,
            'builtin': bool(group.builtin),
            'items': [entry['name'] for entry in entries], 'entries': entries,
        })
    return library


def scope_presets(session) -> list[dict]:
    """兼容旧名：数据源页与预置库接口都从这里取树。"""
    return dictionary(session)


def find_group(session, group_id: int) -> DimGroup:
    row = session.get(DimGroup, int(group_id))
    if row is None:
        raise ValueError('分组不存在')
    return row


def find_indicator(session, indicator_id: int) -> DimIndicator:
    row = session.get(DimIndicator, int(indicator_id))
    if row is None:
        raise ValueError('指标不存在')
    return row


def resolve_indicator(session, indicator_id=None, name=None) -> DimIndicator:
    """按 id 找，找不到再按名字找——兼容老接口只传名字的调用。"""
    if indicator_id not in (None, '', 0):
        return find_indicator(session, indicator_id)
    name = str(name or '').strip()
    if not name:
        raise ValueError('缺少要编辑的指标')
    row = session.execute(select(DimIndicator).where(DimIndicator.name == name)).scalar_one_or_none()
    if row is None:
        raise ValueError('指标不存在：%s' % name)
    return row


def group_name(session, group_id) -> str:
    row = session.get(DimGroup, int(group_id)) if group_id else None
    return row.name if row else ''


def create_group(session, name: str, code: str = '') -> DimGroup:
    """新建分组。主数据化之后空分组是合法状态——先搭目录、后填指标。"""
    name = str(name or '').strip()
    if not name:
        raise ValueError('分组名不能为空')
    exists = session.execute(select(DimGroup).where(DimGroup.name == name)).scalar_one_or_none()
    if exists:
        raise ValueError('分组已存在：%s' % name)
    return ensure_group(session, name, code)


def rename_group(session, group_id: int, name: str, code=None) -> DimGroup:
    """分组改名只动 dim_groups 一行——分组名不再散落在任何业务表里。

    ``code`` 传 None 表示不动编码；传值则一并校验唯一性。
    """
    group = find_group(session, group_id)
    name = str(name or '').strip()
    if not name:
        raise ValueError('分组名不能为空')
    if group.builtin:
        raise ValueError('系统分组不能改名')
    if name != group.name:
        exists = session.execute(select(DimGroup).where(DimGroup.name == name)).scalar_one_or_none()
        if exists:
            raise ValueError('分组已存在：%s' % name)
        group.name = name
    if code is not None:
        code = normalize_code(code)
        if code and code != group.code:
            taken = _code_taken(session, DimGroup, code, group.id)
            if taken:
                raise ValueError('编码 %s 已被分组「%s」占用，请换一个' % (code, taken.name))
            group.code = code
    return group


def delete_group(session, group_id: int) -> None:
    """只允许删空分组。组里还有指标时要求先移走，避免连指标一起消失。"""
    group = find_group(session, group_id)
    if group.builtin:
        raise ValueError('系统分组不能删除')
    count = session.execute(select(func.count()).select_from(DimIndicator)
                            .where(DimIndicator.group_id == group.id)).scalar() or 0
    if count:
        raise ValueError('分组下还有 %d 个指标，请先移走或删除' % count)
    session.delete(group)


def _replace_in_list(raw, old: str, new: str) -> str | None:
    """把 JSON 数组里的旧名字替换成新名字；没命中返回 None，避免无谓写库。"""
    try:
        value = json.loads(raw or '[]')
    except Exception:
        return None
    if not isinstance(value, list) or old not in value:
        return None
    return json.dumps([new if str(x) == old else x for x in value], ensure_ascii=False)


def rename_indicator(session, indicator_id: int, name: str) -> dict:
    """指标改名：id 不变，级联维护所有冗余名字，历史数据不会变成孤儿。

    级联范围：observations.indicator（数据）、data_sources.scope_items（配置候选）、
    data_source_configs.scope.items（同步范围）、viewpoints.benchmark_indicator（观点溯源）。
    目标名字已经有数据时拒绝——那属于两条序列合并，不是改名。
    """
    row = find_indicator(session, indicator_id)
    name = str(name or '').strip()
    if not name:
        raise ValueError('指标名不能为空')
    if name == row.name:
        return {'renamed': 0, 'observations': 0, 'sources': 0, 'configs': 0, 'viewpoints': 0}
    taken = session.execute(select(DimIndicator)
                            .where(DimIndicator.name == name, DimIndicator.id != row.id)).scalar_one_or_none()
    if taken:
        raise ValueError('已存在同名指标：%s' % name)
    old = row.name
    # 目标名字下已经有数据 → 那是两条序列的合并，不是改名，拒绝并说清楚
    conflict = session.execute(select(func.count()).select_from(Observation)
                               .where(Observation.indicator == name)).scalar() or 0
    if conflict:
        raise ValueError('「%s」下已有 %d 条数据，改名会与它冲突；如需合并请先把两条序列分开处理' % (name, conflict))
    # 真正会被改名的历史数据条数（按旧名字算）
    moved = session.execute(select(func.count()).select_from(Observation)
                            .where(Observation.indicator == old)).scalar() or 0

    row.name = name
    row.updated_at = _now()
    session.execute(update(Observation).where(Observation.indicator == old).values(indicator=name))

    sources = 0
    for item in session.execute(select(DataSource)).scalars():
        patched = _replace_in_list(item.scope_items, old, name)
        if patched is not None:
            item.scope_items = patched
            sources += 1

    configs = 0
    for config in session.execute(select(DataSourceConfig)).scalars():
        try:
            scope = json.loads(config.scope or '{}')
        except Exception:
            continue
        items = scope.get('items') if isinstance(scope, dict) else None
        if isinstance(items, list) and old in items:
            scope['items'] = [name if str(x) == old else x for x in items]
            config.scope = json.dumps(scope, ensure_ascii=False)
            configs += 1

    viewpoints = 0
    for viewpoint in session.execute(select(Viewpoint)
                                     .where(Viewpoint.benchmark_indicator == old)).scalars():
        viewpoint.benchmark_indicator = name
        viewpoints += 1

    return {'renamed': 1, 'observations': moved,
            'sources': sources, 'configs': configs, 'viewpoints': viewpoints}


def move_indicator(session, indicator_id: int, group_id: int) -> DimIndicator:
    row = find_indicator(session, indicator_id)
    find_group(session, group_id)
    row.group_id = int(group_id)
    row.updated_at = _now()
    return row


def delete_indicator(session, indicator_id: int) -> dict:
    """删除指标。有观测数据时拒绝——否则历史数据会失去归属，变成查不到的孤儿。"""
    row = find_indicator(session, indicator_id)
    points = session.execute(select(func.count()).select_from(Observation)
                             .where(Observation.indicator_id == row.id)).scalar() or 0
    if not points:
        points = session.execute(select(func.count()).select_from(Observation)
                                 .where(Observation.indicator == row.name)).scalar() or 0
    if points:
        raise ValueError('该指标已有 %d 条数据，不能删除；如不再使用请改为停用' % points)
    name = row.name
    session.delete(row)
    # 顺带把它从各数据源的候选清单里去掉，避免下拉里留下已删除的名字
    for item in session.execute(select(DataSource)).scalars():
        patched = _replace_in_list(item.scope_items, name, '')
        if patched is not None:
            item.scope_items = json.dumps([x for x in json.loads(patched) if x], ensure_ascii=False)
    return {'removed': 1}

# 新鲜度口径：指标最新数据日期距今超过该天数视为「滞后」（周末与节假日会造成 2~3 天）
STALE_DAYS = 3


def stale_days(latest) -> int | None:
    """最新数据日期距今的自然日数；无数据返回 None。"""
    text = str(latest or '')[:10]
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(text)).days
    except Exception:
        return None


def is_stale(latest) -> bool:
    days = stale_days(latest)
    return days is not None and days > STALE_DAYS


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
    _ensure_unique_index(session, 'uq_observation_point', 'observations',
                         'source, indicator, date')
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
    # 指标身份按名字解析一次就缓存，10000 行 CSV 不会变成 10000 次查库
    indicator_ids: dict[str, int] = {}
    for row in unique.values():
        indicator_id = indicator_ids.get(row['indicator'])
        if indicator_id is None:
            indicator_id = ensure_indicator(session, row['indicator']).id
            indicator_ids[row['indicator']] = indicator_id
        point = {k: row[k] for k in ('source', 'indicator', 'date', 'value', 'unit')}
        if _insert_ignore(session, {**point, 'uploaded_by': operator, 'indicator_id': indicator_id}):
            inserted += 1
            continue
        changed = session.execute(update(Observation).where(
            Observation.source == row['source'], Observation.indicator == row['indicator'],
            Observation.date == row['date'],
            or_(Observation.value.is_(None), func.abs(Observation.value - row['value']) >= 1e-9,
                Observation.unit.is_(None), Observation.unit != row['unit'])
        ).values(value=row['value'], unit=row['unit'], uploaded_by=operator,
                 indicator_id=indicator_id))
        if changed.rowcount:
            updated += 1
        else:
            skipped += 1
    return {'inserted': inserted, 'updated': updated, 'skipped': skipped, 'total': len(rows)}


def stats(session) -> list[dict]:
    """按来源汇总：条数、指标数、最新日期、最近一次成功同步的时间、新鲜度。"""
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
    # 滞后指标数：按来源统计「最新数据日期已超过 STALE_DAYS」的指标个数
    late: dict[str, int] = {}
    for source, _indicator, latest in session.execute(
            select(Observation.source, Observation.indicator, func.max(Observation.date))
            .group_by(Observation.source, Observation.indicator)).all():
        if is_stale(latest):
            late[source] = late.get(source, 0) + 1
    result = []
    for item in sources(session):
        hit = counters.get(item['name']) or counters.get(item['key'])
        result.append({
            **item,
            'rows': int(hit[1]) if hit else 0,
            'indicators': int(hit[2]) if hit else 0,
            'latest': (hit[3] or '') if hit else '',
            'last_sync': last.get(item['key']) or '',
            'stale_days': stale_days(hit[3]) if hit else None,
            'late_indicators': late.get(item['name'], 0) + late.get(item['key'], 0),
        })
    return result


def health(session) -> list[dict]:
    """数据源巡检：近 30 天同步成功率、最近成功时间、滞后指标数、异常配置数。

    对照 ETA「数据源巡检监控」：让人不进每个子页就能看出哪家数据源不健康。
    """
    names = source_names(session)                       # key -> 中文名
    by_name = {v: k for k, v in names.items()}          # 中文名 -> key
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    job_stats: dict[str, dict] = {}
    for source, status, count in session.execute(
            select(DataSyncJob.source, DataSyncJob.status, func.count())
            .where(DataSyncJob.created_at >= since)
            .group_by(DataSyncJob.source, DataSyncJob.status)).all():
        bucket = job_stats.setdefault(by_name.get(source, source), {'ok': 0, 'fail': 0})
        if status == '已完成':
            bucket['ok'] += int(count)
        elif status == '失败':
            bucket['fail'] += int(count)
    last_success: dict[str, str] = {}
    for source, at in session.execute(
            select(DataSyncJob.source, func.max(DataSyncJob.finished_at))
            .where(DataSyncJob.status == '已完成', DataSyncJob.created_at >= since)
            .group_by(DataSyncJob.source)).all():
        last_success[by_name.get(source, source)] = at or ''
    bad_configs: dict[str, int] = {}
    for source, count in session.execute(
            select(DataSourceConfig.source, func.count())
            .where(DataSourceConfig.enabled == 1, DataSourceConfig.last_status == '失败')
            .group_by(DataSourceConfig.source)).all():
        bad_configs[by_name.get(source, source)] = int(count)
    result = []
    for item in stats(session):
        key = item['key']
        bucket = job_stats.get(key, {'ok': 0, 'fail': 0})
        total = bucket['ok'] + bucket['fail']
        ok, fail, late, bad = bucket['ok'], bucket['fail'], item['late_indicators'], bad_configs.get(key, 0)
        # 健康度：绿=正常；黄=有滞后指标或近期有失败；红=近期成功率低于一半或配置持续失败
        if total and ok / total < 0.5 or bad:
            level = '红'
        elif fail or late:
            level = '黄'
        else:
            level = '绿'
        result.append({
            'key': key, 'name': item['name'], 'level': level,
            'jobs_30d': total, 'success_rate': round(ok / total * 100, 1) if total else None,
            'failed_30d': fail, 'last_success': last_success.get(key, ''),
            'stale_days': item['stale_days'], 'late_indicators': late,
            'bad_configs': bad,
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
        item['stale_days'] = stale_days(item['last_date'])
        item['stale'] = is_stale(item['last_date'])
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


# ---------------------------------------------------------------------------
# 失败原因分类（对照 ETA「数据源统计表」：点击失败项看原因 + 排查步骤）
# ---------------------------------------------------------------------------
_FAILURE_RULES = [
    ('凭据/鉴权', ('401', '403', 'token', '鉴权', '授权', '凭据', '登录', '过期', '密码',
                  'password', 'apikey', 'api key', 'secret', 'unauthorized', 'forbidden', '认证')),
    ('接口限流', ('429', '限流', '频率', 'rate limit', 'too many', 'throttl', '繁忙', '配额')),
    ('参数/指标编码', ('400', '参数', '编码', '指标不存在', '不存在', '无数据', 'no data',
                     'invalid', '字段', 'code', '编码变更', '未定义', 'missing')),
    ('网络/超时', ('timeout', '超时', 'connection', '连接', 'network', '网络', 'ssl', 'dns',
                 'refused', 'reset', 'unreachable', 'getaddrinfo')),
]
TROUBLESHOOTING = {
    '凭据/鉴权': ['检查取数配置里的账号与密钥是否过期，重新保存一次凭据',
                 '确认终端/API 账号仍在授权有效期内，必要时重新登录授权',
                 '用「试连」按钮验证一次新凭据'],
    '接口限流': ['降低同步频率或缩小单次品种/指标范围',
                 '避开整点等高峰时段，把自动计划错开 10~20 分钟',
                 '若持续出现，联系数据商提升接口配额'],
    '参数/指标编码': ['核对指标编码/品种名是否在数据商侧被更名或下线',
                     '用指标查询页确认该指标近期是否还有新数据入库',
                     '在取数配置中更新指标编码后重跑'],
    '网络/超时': ['检查服务器到数据商的网络连通性与代理设置',
                 '重试一次（多为瞬时抖动）',
                 '若长期超时，联系运维检查出口带宽与防火墙'],
    '其他': ['查看完整报错信息定位环节（请求/解析/入库）',
             '用「试连」验证配置与通道是否正常',
             '仍无法解决时联系平台管理员并附上作业 ID'],
}


def classify_failure(message: str) -> str:
    text = str(message or '').lower()
    for label, keywords in _FAILURE_RULES:
        if any(keyword in text for keyword in keywords):
            return label
    return '其他' if message else ''


def job_dict(job, names: dict | None = None) -> dict:
    item = job.to_dict()
    try:
        item['scope'] = json.loads(item.get('scope') or '{}')
    except Exception:
        item['scope'] = {}
    mapping = names or SOURCE_NAMES
    item['source_name'] = mapping.get(item.get('source'), item.get('source') or '')
    if item.get('status') == '失败':
        item['reason_type'] = classify_failure(item.get('message'))
        item['troubleshooting'] = TROUBLESHOOTING.get(item['reason_type'], TROUBLESHOOTING['其他'])
    else:
        item['reason_type'] = ''
        item['troubleshooting'] = []
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
