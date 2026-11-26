"""服务端直连取数：按「数据源配置」打上游接口，产出观测行并幂等入库。

三种角色的分工
--------------
- 配置（``data_source_configs``）：接口地址、凭据、同步范围、定时计划，由管理员在页面维护；
- 执行（本模块）：按配置逐品种逐指标请求上游，把响应翻译成 ``source,indicator,date,value,unit``；
- 入库（``datasource.apply``）：与同步通道、CSV 通道共用同一套校验与幂等规则。

为什么提供两种 kind
-------------------
- ``generic_json``：GET / POST + JSON 模板，配响应路径与字段映射，任何 REST 行情接口都能接；
- ``ifind_http``：同花顺 iFinD 数据接口的预设（access_token + history_quotes），字段名随官方
  文档可能调整，所以在 ``options.field_map`` 里留了可改的入口，不必改代码。

凭据只存库、只回掩码；错误信息落库前会先把密钥替换成 ``***``，避免日志与页面泄露。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import ssl
import truststore
import urllib.error
import urllib.parse
import urllib.request

import datasource
from db import DataSourceConfig, DataSyncJob

BEIJING = dt.timezone(dt.timedelta(hours=8))

KINDS = [
    {'key': 'eastmoney_snapshot', 'label': '东方财富 · 最新指数快照', 'hint': '最新点位与成交量，按行情时间入库，不是历史日线'},
    {'key': 'eastmoney_index', 'label': '东方财富 · 指数日线', 'hint': '公开指数日线（收盘点位 / 成交量）'},
    {'key': 'sina_index', 'label': '新浪财经 · 指数日线', 'hint': '公开指数日线（收盘点位 / 成交量）'},
    {'key': 'generic_json', 'label': '通用 JSON 接口', 'hint': '任意 HTTP 接口，配请求模板与响应路径（SMM 等自有账号 API 可用此通道）'},
    {'key': 'ifind_http', 'label': '同花顺 iFinD（HTTP）', 'hint': 'access_token + 历史行情，字段名可改'},
    {'key': 'windpy', 'label': 'Wind · 本机终端（WindPy）', 'hint': '本机装有已登录的 Wind 金融终端（MAC 绑定账号），凭据留在终端侧'},
]

FREQS = [
    {'key': 'manual', 'label': '仅手动'},
    {'key': 'daily', 'label': '每个交易日'},
    {'key': 'weekly', 'label': '每周一次'},
]

# 通用接口的请求/解析模板默认值（页面「高级」里可逐项覆盖）
DEFAULT_OPTIONS = {
    'method': 'GET',
    'headers': '{}',
    'body': '',
    'points_path': 'data',
    'date_field': 'date',
    'value_field': 'value',
    'indicator_field': '',
    'indicator_template': '{item}{metric_label}',
    'unit': '',
    'timeout': 20,
    'field_map': {},
}

# iFinD 历史行情的指标字段名（官方文档若调整，在页面 options.field_map 改即可）
IFIND_BASE = 'https://ft.10jqka.com.cn'

IFIND_FIELDS = {
    'close': 'close', 'settle': 'settle', 'volume': 'volume',
    'open_interest': 'openInterest', 'spot': 'close', 'inventory': 'value',
    'index_close': 'close',
}


class FeedError(Exception):
    """取数失败的原因，作为可读文本落进作业说明。"""


def now_str() -> str:
    return dt.datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M:%S')


def today() -> dt.date:
    return dt.datetime.now(BEIJING).date()


def _clip(text: str, limit: int = 240) -> str:
    text = str(text or '').replace('\n', ' ').strip()
    return text if len(text) <= limit else text[:limit] + '…'


def _fill(template: str, values: dict) -> str:
    """占位替换；未知占位原样保留，避免模板笔误直接炸掉。"""
    text = str(template or '')
    for key, value in values.items():
        text = text.replace('{' + key + '}', str(value))
    return text


def _scrub(text: str, secret: str) -> str:
    """把密钥从任何要落库/回显的文本里抹掉。"""
    text = str(text or '')
    if secret and len(secret) >= 6:
        text = text.replace(secret, '***')
    return text


def _json_or_error(text: str, where: str):
    try:
        return json.loads(text)
    except Exception:
        raise FeedError('%s 返回的不是 JSON：%s' % (where, _clip(text, 160)))


def _http(method: str, url: str, headers: dict, body: str, timeout: int) -> str:
    """发一次请求，把上游 HTTP 错误转成带原话的 FeedError。"""
    payload = body.encode('utf-8') if body else None
    request = urllib.request.Request(url, data=payload, method=method.upper(),
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=max(3, min(int(timeout or 20), 120)),
                                    context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)) as response:
            return response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = exc.read().decode('utf-8', errors='replace')
        except Exception:
            pass
        raise FeedError('上游返回 HTTP %s：%s' % (exc.code, _clip(detail, 200)))
    except urllib.error.URLError as exc:
        raise FeedError('连不上接口：%s' % _clip(str(exc.reason), 160))
    except Exception as exc:
        raise FeedError('请求失败：%s' % _clip('%s %s' % (type(exc).__name__, exc), 160))


def _pick(payload, path: str):
    """按 ``a.b.c`` 取嵌套值；数组下标用数字段，路径为空返回原对象。"""
    node = payload
    for part in [p for p in str(path or '').split('.') if p]:
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return None
        if node is None:
            return None
    return node


def _date_of(raw) -> str:
    """把上游日期归一为 YYYY-MM-DD；认 20261118、时间戳与常见分隔符。"""
    text = str(raw or '').strip()
    if not text:
        return ''
    digits = text.replace('-', '').replace('/', '').replace('.', '')[:8]
    if len(digits) == 8 and digits.isdigit():
        return '%s-%s-%s' % (digits[:4], digits[4:6], digits[6:8])
    if text.isdigit() and len(text) in (10, 13):
        stamp = int(text) / (1000 if len(text) == 13 else 1)
        return dt.datetime.fromtimestamp(stamp, BEIJING).strftime('%Y-%m-%d')
    try:
        return dt.date.fromisoformat(text[:10]).isoformat()
    except Exception:
        return ''


def _window(days: int) -> tuple[str, str]:
    """取数窗口：days 个交易日按自然日放宽，回填后再按条数截断。"""
    end = today()
    start = end - dt.timedelta(days=max(days * 2, days + 6))
    return start.isoformat(), end.isoformat()


def _metric_unit(metric: str, options: dict) -> str:
    if options.get('unit'):
        return str(options['unit'])[:20]
    for item in datasource.METRICS:
        if item['key'] == metric:
            return item['unit']
    return ''


def _rows_generic(config: DataSourceConfig, item: str, code: str, metric: str,
                  start: str, end: str, days: int, options: dict) -> list[dict]:
    values = {
        'item': item, 'code': code, 'metric': metric,
        'metric_label': datasource.METRIC_LABELS.get(metric, metric),
        'startdate': start, 'enddate': end, 'days': days,
        'account': config.account or '', 'secret': config.secret or '',
    }
    url = _fill(config.base_url or '', values)
    if not url:raise FeedError('接口地址为空')
    if '?' not in url and urllib.parse.urlparse(url).query == '':
        pass
    headers = {}
    raw_headers = _fill(options.get('headers') or '{}', values)
    try:
        headers = json.loads(raw_headers) if raw_headers.strip() else {}
        if not isinstance(headers, dict):
            raise ValueError
    except Exception:
        raise FeedError('请求头需为 JSON 对象：%s' % _clip(raw_headers, 120))
    headers = {str(k): str(v) for k, v in headers.items()}

    method = str(options.get('method') or 'GET').upper()
    body = ''
    if method == 'POST':
        body = _fill(options.get('body') or '', values).strip()
        headers.setdefault('Content-Type', 'application/json')
    text = _http(method, url, headers, body, options.get('timeout') or 20)
    payload = _json_or_error(text, '通用接口')

    points = _pick(payload, options.get('points_path') or '')
    if points is None and isinstance(payload, list):
        points = payload
    if not isinstance(points, list):
        raise FeedError('按路径「%s」没取到数组，响应片段：%s'
                        % (options.get('points_path') or '(整个响应)', _clip(text, 160)))

    date_field = options.get('date_field') or 'date'
    value_field = options.get('value_field') or 'value'
    unit = _metric_unit(metric, options)
    template = options.get('indicator_template') or '{item}{metric_label}'
    rows = []
    for point in points:
        if not isinstance(point, dict):
            continue
        date = _date_of(point.get(date_field))
        raw = point.get(value_field)
        if not date or raw in (None, ''):
            continue
        rows.append({
            'source': config.source,
            'indicator': _fill(template, {**values, 'item': item,
                                          'metric_label': datasource.METRIC_LABELS.get(metric, metric)}),
            'date': date,
            'value': raw,
            'unit': str(point.get('unit') or unit or ''),
        })
    return rows


PUBLIC_INDEX_CODES = {
    '上证指数': ('1.000001', 'sh000001'),
    '深证成指': ('0.399001', 'sz399001'),
    '沪深300': ('1.000300', 'sh000300'),
}
PUBLIC_URLS = {
    'eastmoney_snapshot': 'https://push2.eastmoney.com/api/qt/stock/get',
    'eastmoney_index': 'https://push2his.eastmoney.com/api/qt/stock/kline/get',
    'sina_index': 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData',
}

# ---------------------------------------------------------------------------
# WindPy 本机终端通道：MAC 绑定的终端账号没有独立 API 凭据，取数靠本机已登录
# 的 Wind 金融终端。凭据始终留在终端侧，平台只负责把取到的行幂等入库。
# 范围条目格式：指标名|Wind代码|通道（wsd=行情，edb=宏观 EDB），如：
#   螺纹钢主连|RBZL.SHF|wsd     南华商品指数|M002122626|edb
# ---------------------------------------------------------------------------
_WSD_FIELDS = {'index_last': 'close', 'index_close': 'close', 'close': 'close',
               'settle': 'settle', 'volume': 'volume', 'open_interest': 'oi'}

_wind_session = None


def _windpy():
    """拿到已连接的 WindPy w 对象；终端没装/没登录时给出人话报错。"""
    global _wind_session
    if _wind_session is not None:
        return _wind_session
    try:
        from WindPy import w
    except ImportError:
        raise FeedError('本机未安装 WindPy：请先安装 Wind 金融终端并执行 pip install WindPy')
    try:
        if not w.isconnected():
            w.start(waitTimeout=60)
        if not w.isconnected():
            raise RuntimeError('连接超时')
    except Exception as exc:
        raise FeedError('连不上 Wind 金融终端：%s。请确认本机装有 Wind 终端且已用授权账号登录（MAC 绑定的账号只能在绑定的机器上登录）' % exc)
    _wind_session = w
    return _wind_session


def _rows_windpy(config: DataSourceConfig, item: str, code: str, metric: str,
                 start: str, end: str, days: int, options: dict) -> list[dict]:
    parts = [p.strip() for p in str(item).split('|')]
    if len(parts) != 3 or not parts[1]:
        raise FeedError('范围条目需为「指标名|Wind代码|通道(wsd或edb)」，如 螺纹钢主连|RBZL.SHF|wsd')
    name, wind_code, channel = parts
    w = _windpy()
    if channel == 'edb':
        # EDB 宏观/行业指标：一个条目一条序列，与所选行情指标无关
        result, df = w.edb(wind_code, start, end, usedf=True)
        if int(result) != 0 or df is None or df.empty:
            raise FeedError('w.edb 返回码 %s，未取到数据（核对 Wind EDB 代码）' % result)
        units = dict(getattr(df, 'attrs', {}).get('Units') or {})
        rows = []
        for day, value in df[wind_code].items() if wind_code in df.columns else []:
            if value in (None, ''):
                continue
            rows.append({'source': config.source, 'indicator': name,
                         'date': _date_of(str(day)), 'value': float(value),
                         'unit': units.get(wind_code) or options.get('unit') or '按EDB口径'})
        return rows
    if channel != 'wsd':
        raise FeedError('通道只支持 wsd（行情）或 edb（宏观），收到：%s' % channel)
    field = (options.get('field_map') or {}).get(metric) or _WSD_FIELDS.get(metric)
    if not field:
        raise FeedError('指标「%s」没有对应的 Wind 字段，可在高级设置 field_map 里补'
                        % datasource.METRIC_LABELS.get(metric, metric))
    result, df = w.wsd(wind_code, field, start, end, "", usedf=True)
    if int(result) != 0 or df is None or df.empty:
        raise FeedError('w.wsd 返回码 %s，未取到数据（核对代码 %s）' % (result, wind_code))
    column = field if field in df.columns else df.columns[0]
    unit = _metric_unit(metric, options)
    rows = []
    for day, value in df[column].items():
        if value in (None, ''):
            continue
        rows.append({'source': config.source,
                     'indicator': _fill(options.get('indicator_template') or '{item}{metric_label}',
                                        {'item': name, 'metric_label': datasource.METRIC_LABELS.get(metric, metric)}),
                     'date': _date_of(str(day)), 'value': float(value), 'unit': unit})
    return rows


def _rows_public(config, item, code, metric, start, end, days, options):
    if item not in PUBLIC_INDEX_CODES:
        raise FeedError('此通道支持上证指数、深证成指、沪深300，请选择对应指数')
    if config.kind == 'eastmoney_snapshot':
        if metric not in ('index_last', 'volume'):
            raise FeedError('最新快照仅支持最新点位和成交量，不提供历史收盘价')
        url = (config.base_url or PUBLIC_URLS[config.kind]) + '?' + urllib.parse.urlencode({
            'secid': PUBLIC_INDEX_CODES[item][0], 'fields': 'f43,f47,f58,f59,f86'})
        payload = _json_or_error(_http('GET', url, {'User-Agent': 'Mozilla/5.0'}, '', options.get('timeout') or 20), '东方财富最新快照')
        data = _pick(payload, 'data')
        if not isinstance(data, dict) or not data.get('f86'):
            raise FeedError('东方财富未返回有效行情及行情时间')
        date = dt.datetime.fromtimestamp(int(data['f86']), BEIJING).date().isoformat()
        value = data.get('f47' if metric == 'volume' else 'f43')
        if value in (None, '', '-'):
            raise FeedError('行情字段暂无数值')
        value = float(value)
        if metric == 'volume':
            value *= 100
        else:
            value /= 10 ** int(data.get('f59', 2))
        if not math.isfinite(value):
            raise FeedError('行情数值无效')
        return [{'source': config.source, 'indicator': item + ('成交量快照' if metric == 'volume' else '最新点位'),
                 'date': date, 'value': value, 'unit': '股' if metric == 'volume' else '点'}]
    if metric not in ('index_close', 'close', 'volume'):
        raise FeedError('指数日线仅支持收盘点位和成交量')
    em, sina = PUBLIC_INDEX_CODES[item]
    if config.kind == 'eastmoney_index':
        params = {'secid': em, 'klt': 101, 'fqt': 0, 'lmt': days,
                  'end': end.replace('-', ''), 'fields1': 'f1,f2,f3',
                  'fields2': 'f51,f52,f53,f54,f55,f56'}
    else:
        params = {'symbol': sina, 'scale': 240, 'ma': 'no', 'datalen': days}
    url = (config.base_url or PUBLIC_URLS[config.kind]) + '?' + urllib.parse.urlencode(params)
    payload = _json_or_error(_http('GET', url, {'User-Agent': 'Mozilla/5.0'}, '',
                                 options.get('timeout') or 20), '指数行情')
    rows = []
    if config.kind == 'eastmoney_index':
        points = _pick(payload, 'data.klines')
        if not isinstance(points, list):
            raise FeedError('东方财富未返回日线数据')
        for point in points:
            fields = str(point).split(',')
            if len(fields) >= 6:
                rows.append((fields[0], fields[5] if metric == 'volume' else fields[2]))
    else:
        if not isinstance(payload, list):
            raise FeedError('新浪财经未返回日线数据')
        for point in payload:
            if isinstance(point, dict):
                rows.append((point.get('day'), point.get('volume' if metric == 'volume' else 'close')))
    result = []
    for date, value in rows:
        date = _date_of(date)
        if not date or not start <= date <= end or value in (None, '', '-'):
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        # 东方财富该接口的成交量为手；新浪为股，统一存为股。
        if metric == 'volume' and config.kind == 'eastmoney_index':
            value *= 100
        result.append({'source': config.source, 'indicator': item + ('成交量' if metric == 'volume' else '收盘点位'),
                       'date': date, 'value': value, 'unit': '股' if metric == 'volume' else '点'})
    return result


def _ifind_base(config: DataSourceConfig) -> str:
    base = (config.base_url or '').rstrip('/')
    return base or IFIND_BASE


def _ifind_token(config: DataSourceConfig, options: dict) -> str:
    base = _ifind_base(config)
    if not base:
        raise FeedError('接口地址为空')
    if not config.secret:
        raise FeedError('缺少 refresh_token（在「密钥」里填）')
    text = _http('POST', base + '/api/v1/get_access_token',
                 {'Content-Type': 'application/json'},
                 json.dumps({'refresh_token': config.secret}), options.get('timeout') or 20)
    payload = _json_or_error(text, 'get_access_token')
    if isinstance(payload, dict) and payload.get('errorcode') not in (0, None):
        raise FeedError('取 token 失败（%s）：%s'
                        % (payload.get('errorcode'), _clip(payload.get('errmsg'), 160)))
    token = _pick(payload, 'data.access_token') or payload.get('access_token')
    if not token:
        raise FeedError('上游没返回 access_token：%s' % _clip(text, 160))
    return str(token)


def _rows_ifind(config: DataSourceConfig, item: str, code: str, metric: str,
                start: str, end: str, days: int, options: dict, token: str) -> list[dict]:
    fields = options.get('field_map') or {}
    field = fields.get(metric) or IFIND_FIELDS.get(metric)
    if not field:
        raise FeedError('指标「%s」没有对应的 iFinD 字段，请在高级设置里补 field_map'
                        % datasource.METRIC_LABELS.get(metric, metric))
    base = _ifind_base(config)
    body = json.dumps({
        'codes': code,
        'indicators': field,
        'startdate': start.replace('-', ''),
        'enddate': end.replace('-', ''),
        'functionpara': {'Fill': 'Blank'},
    }, ensure_ascii=False)
    # 官方手册：历史行情接口为 cmd_history_quotation
    text = _http('POST', base + '/api/v1/cmd_history_quotation',
                 {'Content-Type': 'application/json', 'access_token': token},
                 body, options.get('timeout') or 20)
    payload = _json_or_error(text, 'cmd_history_quotation')
    if isinstance(payload, dict) and payload.get('errorcode') not in (0, None):
        raise FeedError('取历史行情失败（%s）：%s'
                        % (payload.get('errorcode'), _clip(payload.get('errmsg'), 160)))
    # 不同版本响应里 tables 可能挂在顶层或 data 下，两处都认
    tables = None
    if isinstance(payload, dict):
        tables = payload.get('tables')
        if not isinstance(tables, list):
            tables = (payload.get('data') or {}).get('tables') if isinstance(payload.get('data'), dict) else None
    if not isinstance(tables, list) or not tables:
        raise FeedError('上游没有返回 tables，响应片段：%s' % _clip(text, 200))

    unit = _metric_unit(metric, options)
    template = options.get('indicator_template') or '{item}{metric_label}'
    rows = []
    for table in tables:
        grid = (table or {}).get('table') or {}
        if not isinstance(grid, dict):
            continue
        axis = grid.get('time') or grid.get('date') or []
        series = grid.get(field)
        if not isinstance(series, list):
            continue
        for index, raw in enumerate(series):
            if raw in (None, ''):
                continue
            date = _date_of(axis[index] if index < len(axis) else '')
            if not date:
                continue
            rows.append({
                'source': config.source,
                'indicator': _fill(template, {'item': item,
                                              'metric_label': datasource.METRIC_LABELS.get(metric, metric)}),
                'date': date, 'value': raw, 'unit': unit,
            })
    return rows


def _commodity_codes(session) -> dict:
    """品种名 → 合约代码，请求里用代码、入库用中文名，跟已有的数据命名保持一致。"""
    from sqlalchemy import select
    from db import Commodity  # 延迟导入，避免与 db 模块初始化顺序耦合
    mapping = {}
    for row in session.execute(select(Commodity)).scalars():
        if row.name:
            mapping[row.name] = row.code or ''
    return mapping


def _prepare(session, payload: dict, config: DataSourceConfig | None = None) -> dict:
    """校验并标准化一份配置（新增与编辑共用）。"""
    source = datasource.source_key(session, payload.get('source'))
    if not source:
        raise FeedError('数据来源不存在或已停用，请先在「数据来源」里添加')
    kind = str(payload.get('kind') or 'generic_json').strip()
    if kind not in {item['key'] for item in KINDS}:
        raise FeedError('请选择有效的取数方式')
    base_url = str(payload.get('base_url') or PUBLIC_URLS.get(kind, '')).strip()
    # ifind_http 不填地址时回落到官方域名；windpy 走本机终端，没有 URL
    if kind not in ('windpy', 'ifind_http') and not base_url.lower().startswith(('http://', 'https://')):
        raise FeedError('接口地址需以 http:// 或 https:// 开头')

    scope = payload.get('scope') or {}
    if isinstance(scope, str):
        try:
            scope = json.loads(scope)
        except Exception:
            raise FeedError('同步范围不是合法 JSON')
    items = [str(x).strip() for x in (scope.get('items') or []) if str(x).strip()]
    metrics = [str(x).strip() for x in (scope.get('metrics') or []) if str(x).strip()]
    if not items:
        raise FeedError('请至少选择一个品种')
    if not metrics:
        raise FeedError('请至少选择一个指标')
    unknown = [m for m in metrics if m not in datasource.METRIC_LABELS]
    if unknown:
        raise FeedError('未知指标：' + '、'.join(unknown))
    days = int(scope.get('days') or 10)
    if days < 1 or days > 120:
        raise FeedError('区间需在 1 至 120 个交易日之间')

    options = dict(DEFAULT_OPTIONS)
    raw_options = payload.get('options') or {}
    if isinstance(raw_options, str):
        try:
            raw_options = json.loads(raw_options or '{}')
        except Exception:
            raise FeedError('高级设置不是合法 JSON')
    if not isinstance(raw_options, dict):
        raise FeedError('高级设置需为对象')
    options.update({k: v for k, v in raw_options.items() if v not in (None, '')})
    if not isinstance(options.get('field_map'), dict):
        options['field_map'] = {}

    freq = str(payload.get('freq') or 'manual').strip()
    if freq not in {item['key'] for item in FREQS}:
        raise FeedError('计划频率需为 manual / daily / weekly')
    run_at = str(payload.get('run_at') or '08:30').strip()
    try:
        hour, minute = [int(x) for x in run_at.split(':')]
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError
        run_at = '%02d:%02d' % (hour, minute)
    except Exception:
        raise FeedError('执行时间需为 HH:MM')

    return {
        'name': str(payload.get('name') or '').strip()[:60]
                or '%s 自动同步' % datasource.source_names(session).get(source, source),
        'source': source, 'kind': kind, 'base_url': base_url.rstrip('/'),
        'account': str(payload.get('account') or '').strip()[:120],
        'scope': json.dumps({'items': items, 'metrics': metrics, 'days': days,
                             'code_suffix': str(scope.get('code_suffix') or '').strip()[:20]},
                            ensure_ascii=False),
        'options': json.dumps(options, ensure_ascii=False),
        'freq': freq, 'run_at': run_at,
        'weekday': min(7, max(1, int(payload.get('weekday') or 1))),
        'enabled': 1 if payload.get('enabled', True) else 0,
    }


def mask_secret(secret: str) -> str:
    text = str(secret or '')
    if not text:
        return ''
    if len(text) <= 8:
        return text[:2] + '***'
    return text[:4] + '***' + text[-4:]


def config_dict(config: DataSourceConfig, names: dict | None = None) -> dict:
    """对外形态：密钥只给掩码，其余原样。"""
    def _load(raw, fallback):
        try:
            value = json.loads(raw or '')
            return value if isinstance(value, type(fallback)) else fallback
        except Exception:
            return fallback

    return {
        'id': config.id, 'name': config.name, 'source': config.source,
        'source_name': (names or datasource.SOURCE_NAMES).get(config.source, config.source or ''),
        'kind': config.kind,
        'kind_label': next((k['label'] for k in KINDS if k['key'] == config.kind), config.kind or ''),
        'base_url': config.base_url, 'account': config.account or '',
        'secret_set': bool(config.secret), 'secret_masked': mask_secret(config.secret),
        'scope': _load(config.scope, {}),
        'options': _load(config.options, {}),
        'freq': config.freq or 'manual', 'run_at': config.run_at or '08:30',
        'weekday': config.weekday or 1, 'enabled': 1 if config.enabled else 0,
        'last_run': config.last_run or '', 'last_status': config.last_status or '未运行',
        'last_message': config.last_message or '',
        'reason_type': (datasource.classify_failure(config.last_message)
                        if config.last_status == '失败' else ''),
        'troubleshooting': (datasource.TROUBLESHOOTING.get(datasource.classify_failure(config.last_message),
                                                           datasource.TROUBLESHOOTING['其他'])
                            if config.last_status == '失败' else []),
        'operator': config.operator or '', 'created_at': config.created_at or '',
        'updated_at': config.updated_at or '',
    }


def save(session, payload: dict, operator: str, config: DataSourceConfig | None = None) -> DataSourceConfig:
    cleaned = _prepare(session, payload, config)
    target = config or DataSourceConfig(created_at=now_str(), operator=operator)
    for key, value in cleaned.items():
        setattr(target, key, value)
    # 密钥：留空表示沿用旧值，显式 clear_secret 才清掉
    new_secret = str(payload.get('secret') or '').strip()
    if new_secret:
        target.secret = new_secret
    elif payload.get('clear_secret'):
        target.secret = ''
    elif config is None:
        target.secret = target.secret or ''
    target.operator = operator
    target.updated_at = now_str()
    if config is None:
        session.add(target)
    session.flush()
    return target


def _collect(session, config: DataSourceConfig, options: dict) -> tuple[list[dict], list[str]]:
    """逐品种逐指标取数，单个组合失败不拖垮整批（原因汇总后写进作业说明）。"""
    scope = json.loads(config.scope or '{}')
    items = scope.get('items') or []
    metrics = scope.get('metrics') or []
    days = int(scope.get('days') or 10)
    suffix = scope.get('code_suffix') or ''
    codes = _commodity_codes(session)
    start, end = _window(days)

    token = _ifind_token(config, options) if config.kind == 'ifind_http' else ''
    label = datasource.source_names(session).get(config.source, config.source or '')
    rows, problems = [], []
    for item in items:
        if item in codes and not codes.get(item):
            problems.append('%s：是分组类目、没有合约代码，请选择具体品种或改用自定义范围' % item)
            continue
        code = codes.get(item) or item
        if suffix and '.' not in code:
            code = code + suffix
        for metric in metrics:
            try:
                if config.kind in PUBLIC_URLS:
                    got = _rows_public(config, item, code, metric, start, end, days, options)
                elif config.kind == 'ifind_http':
                    got = _rows_ifind(config, item, code, metric, start, end, days, options, token)
                elif config.kind == 'windpy':
                    got = _rows_windpy(config, item, code, metric, start, end, days, options)
                else:
                    got = _rows_generic(config, item, code, metric, start, end, days, options)
            except FeedError as exc:
                problems.append('%s·%s：%s' % (item, datasource.METRIC_LABELS.get(metric, metric),
                                              _scrub(str(exc), config.secret or '')))
                continue
            for row in got:
                row['source'] = label
            got.sort(key=lambda x: x['date'], reverse=True)
            rows.extend(got[:days])
    return rows, problems


def execute(session, config: DataSourceConfig, operator: str, trigger: str = 'manual') -> dict:
    """执行一次取数：入库 + 写作业 + 回写配置状态。异常也要落状态，不静默。"""
    options = json.loads(config.options or '{}') if config.options else dict(DEFAULT_OPTIONS)
    scope = json.loads(config.scope or '{}')
    job = DataSyncJob(source=config.source, status='执行中',
                      scope=json.dumps({**scope, 'config_id': config.id, 'trigger': trigger},
                                       ensure_ascii=False),
                      rows=0, inserted=0, updated=0, operator=operator,
                      created_at=now_str(), finished_at='', message='')
    session.add(job)
    session.flush()

    try:
        rows, problems = _collect(session, config, options)
        if not rows:
            reason = '；'.join(problems[:3]) or '上游没有返回可用数据'
            datasource.fail_job(session, job, now_str(), _scrub(reason, config.secret or ''))
            config.last_status = '失败'
            config.last_message = _scrub(reason, config.secret or '')[:500]
        else:
            cleaned = datasource.normalize(rows)
            counts = datasource.apply(session, cleaned, operator)
            note = '配置「%s」%s取数 %s 行' % (config.name or config.id,
                                            '定时' if trigger == 'schedule' else '手动', counts['total'])
            note += '（新增 %s、更新 %s、重复跳过 %s）' % (counts['inserted'], counts['updated'], counts['skipped'])
            if problems:
                note += '；跳过 %s 组：%s' % (len(problems), '；'.join(problems[:3]))
            datasource.finish_job(session, job, counts, now_str(), _scrub(note, config.secret or ''))
            config.last_status = '成功'
            config.last_message = _scrub(note, config.secret or '')[:500]
    except Exception as exc:
        reason = _scrub('%s：%s' % (type(exc).__name__, exc), config.secret or '')
        datasource.fail_job(session, job, now_str(), reason or '取数异常')
        config.last_status = '失败'
        config.last_message = (reason or '取数异常')[:500]

    config.last_run = now_str()
    session.flush()
    return {'job': job.to_dict(), 'status': config.last_status, 'message': config.last_message}


def preview(session, payload: dict) -> dict:
    """测试连接：沿用与正式执行相同的解析，只取一个品种一个指标，不写库。"""
    cleaned = _prepare(session, payload)
    probe = DataSourceConfig(**{k: v for k, v in cleaned.items() if k != 'options'})
    probe.options = cleaned['options']
    probe.id = 0
    secret = str(payload.get('secret') or '').strip()
    if secret:
        probe.secret = secret
    options = json.loads(cleaned['options'])
    scope = json.loads(cleaned['scope'])
    item = scope['items'][0]
    metric = scope['metrics'][0]
    days = max(1, min(scope['days'], 5))
    codes = _commodity_codes(session)
    code = codes.get(item) or item
    if scope.get('code_suffix') and '.' not in code:
        code = code + scope['code_suffix']
    start, end = _window(days)

    import time as _time
    started = _time.time()
    try:
        if probe.kind in PUBLIC_URLS:
            rows = _rows_public(probe, item, code, metric, start, end, days, options)
        elif probe.kind == 'ifind_http':
            token = _ifind_token(probe, options)
            rows = _rows_ifind(probe, item, code, metric, start, end, days, options, token)
        elif probe.kind == 'windpy':
            rows = _rows_windpy(probe, item, code, metric, start, end, days, options)
        else:
            rows = _rows_generic(probe, item, code, metric, start, end, days, options)
    except FeedError as exc:
        return {'ok': False, 'message': _scrub(str(exc), probe.secret or ''),
                'ms': int((_time.time() - started) * 1000), 'sample': []}
    except Exception as exc:
        return {'ok': False, 'message': _scrub('%s：%s' % (type(exc).__name__, exc), probe.secret or ''),
                'ms': int((_time.time() - started) * 1000), 'sample': []}

    label = datasource.source_names(session).get(probe.source, probe.source or '')
    for row in rows:
        row['source'] = label
    rows.sort(key=lambda x: x['date'], reverse=True)
    if not rows:
        return {'ok': False, 'message': '接口通了，但没有解析到有效数据（检查响应路径与字段名）',
                'ms': int((_time.time() - started) * 1000), 'sample': []}
    return {
        'ok': True,
        'message': '连接正常，取到 %s 条样本（%s · %s）' % (
            len(rows), item, datasource.METRIC_LABELS.get(metric, metric)),
        'ms': int((_time.time() - started) * 1000),
        'sample': rows[:3],
    }


def due(session, at: dt.datetime | None = None) -> list[DataSourceConfig]:
    """到点且今天还没跑过的配置。每天/每周只在 run_at 那一分钟触发一次。"""
    now = at or dt.datetime.now(BEIJING)
    if now.tzinfo is None:
        now = now.replace(tzinfo=BEIJING)
    now = now.astimezone(BEIJING)
    hhmm = now.strftime('%H:%M')
    stamp_day = now.strftime('%Y-%m-%d')
    from sqlalchemy import select
    result = []
    for config in session.execute(
            select(DataSourceConfig).where(DataSourceConfig.enabled == 1)).scalars():
        if (config.freq or 'manual') == 'manual':
            continue
        if (config.run_at or '')[:5] != hhmm:
            continue
        if config.freq == 'weekly' and int(config.weekday or 1) != now.isoweekday():
            continue
        if (config.last_run or '').startswith(stamp_day):
            continue
        result.append(config)
    return result
