"""菜单目录：菜单结构、排序与显示设置都存在 menus 表。

菜单项分两类：
- 有页面：path 指向前端路由，key 直接用 path，账号权限按 PERMISSIONS 里的权限名匹配。
- 分组 / 占位模块：没有页面，key 用 ``group:名称`` 或 ``item:父:子``，只受显示开关控制。

显示开关是全局的（不区分账号），权限过滤在 /api/state 下发给前端之前完成。
"""
import json
from sqlalchemy import func, select
from db import AppSetting, Menu, SchemaFlag

PROTECTED = {'group:系统设置', '/system/menus'}
MIGRATED_FLAG = 'menu_catalog_migrated'
REVISION_KEY = 'menu_catalog_revision'

# 页面 → 角色菜单权限名（与角色管理页的勾选项一致）
PERMISSIONS = {
    '/reports': '研报中心', '/approval': '审核中心',
    '/data': '数据中心', '/data/indicators': '数据中心',
    '/library/cloud': '云盘', '/library/docs': '文档管理库', '/library/materials': '素材库',
    '/config/categories': '分类配置', '/config/authors': '作者管理',
    '/config/commodities': '系统管理', '/config/flows': '审批流配置',
    '/system/departments': '部门管理', '/system/users': '系统管理', '/system/roles': '角色管理',
    '/system/models': '系统管理', '/system/menus': '系统管理', '/system/scope-library': '系统管理',
}

# 首次建表时写入的默认目录，与《研枢系统用户操作手册》的侧栏一致
DEFAULT_MENU = [
    {'label': 'BI看板', 'icon': 'DataBoard', 'disabled': True},
    {'label': '投研资源库', 'icon': 'Collection', 'disabled': True},
    {'label': '研报管理', 'icon': 'Document', 'children': [
        {'label': '研报中心', 'path': '/reports'},
        {'label': '研报观点跟踪', 'path': '/viewpoints'},
        {'label': '分类列表', 'path': '/config/categories', 'admin': True},
        {'label': '作者管理', 'path': '/config/authors', 'admin': True},
        {'label': '云盘', 'path': '/library/cloud'},
        {'label': '文档管理库', 'path': '/library/docs'},
        {'label': '素材库', 'path': '/library/materials'},
    ]},
    {'label': '智能PPT', 'icon': 'Monitor', 'disabled': True},
    {'label': '审批管理', 'icon': 'Finished', 'children': [{'label': '审批列表', 'path': '/approval'}]},
    {'label': '数据源', 'icon': 'DataLine', 'children': [
        {'label': '数据录入', 'path': '/data'},
        {'label': '指标查询', 'path': '/data/indicators'},
    ]},
    {'label': '指标库', 'icon': 'Odometer', 'disabled': True},
    {'label': 'AI预测模型', 'icon': 'MagicStick', 'disabled': True},
    {'label': '量化策略', 'icon': 'TrendCharts', 'disabled': True, 'children': [
        {'label': '信号生成'}, {'label': '策略回测'}, {'label': '因子库'},
    ]},
    {'label': '预测指标', 'icon': 'Aim', 'disabled': True},
    {'label': '图库', 'icon': 'Picture', 'disabled': True},
    {'label': '我的投研', 'icon': 'User', 'disabled': True, 'children': [
        {'label': '图库框架'}, {'label': '我的图库'}, {'label': '公共图库'},
    ]},
    {'label': '表格', 'icon': 'Grid', 'disabled': True, 'children': [
        {'label': '共享表格'}, {'label': '自定义分析'}, {'label': '时间序列表格'},
        {'label': '混合表格'}, {'label': '平衡表'},
    ]},
    {'label': '逻辑图', 'icon': 'Connection', 'disabled': True},
    {'label': '语义分析', 'icon': 'View', 'disabled': True, 'children': [
        {'label': 'AI纪要'}, {'label': '文档管理'}, {'label': '标签管理'},
        {'label': '文档对比'}, {'label': '语音识别'},
    ]},
    {'label': '统计分析', 'icon': 'PieChart', 'disabled': True, 'children': [
        {'label': '相关性分析'}, {'label': '拟合方程曲线'}, {'label': '统计特征'},
        {'label': '跨品种分析'}, {'label': '区间分析'}, {'label': 'STL趋势分解'}, {'label': '残差分析'},
    ]},
    {'label': '供应分析', 'icon': 'Box', 'disabled': True, 'children': [{'label': '装置检修'}]},
    {'label': '工具箱', 'icon': 'Tools', 'children': [
        {'label': 'AI问答', 'path': '/agent'},
        {'label': 'Skill 管理', 'path': '/system/skills'},
        {'label': '商品价格曲线'}, {'label': '持仓分析'}, {'label': '联储观察'}, {'label': '预警管理'},
    ]},
    {'label': '数据报表管理', 'icon': 'Tickets', 'disabled': True, 'children': [
        {'label': '钢联化工统计表'}, {'label': '同花顺数据统计表'},
        {'label': 'Wind数据统计表'}, {'label': '数据源巡检监控'},
    ]},
    {'label': '系统设置', 'icon': 'Setting', 'admin': True, 'children': [
        {'label': '部门管理', 'path': '/system/departments', 'admin': True},
        {'label': '账号管理', 'path': '/system/users', 'admin': True},
        {'label': '角色管理', 'path': '/system/roles', 'admin': True},
        {'label': '审批流设置', 'path': '/config/flows', 'admin': True},
        {'label': '品种管理', 'path': '/config/commodities', 'admin': True},
        {'label': '外部模型', 'path': '/system/models', 'admin': True},
        {'label': '菜单管理', 'path': '/system/menus', 'admin': True},
        {'label': '指标管理', 'path': '/system/scope-library', 'admin': True},
    ]},
]


def _key(item, parent=None):
    if item.get('path'):
        return item['path']
    return 'item:%s:%s' % (parent['label'], item['label']) if parent else 'group:' + item['label']


def ensure(session, at='') -> None:
    """表为空时写入默认目录；随后把旧的「隐藏项」设置一次性搬进 visible 列。"""
    if not session.execute(select(func.count()).select_from(Menu)).scalar():
        for index, group in enumerate(DEFAULT_MENU):
            row = Menu(key=_key(group), label=group['label'], icon=group.get('icon', ''), path='',
                       sort_order=(index + 1) * 10, visible=1, admin_only=int(bool(group.get('admin'))),
                       disabled=int(bool(group.get('disabled'))), builtin=1, updated=at)
            session.add(row)
            session.flush()
            for child_index, child in enumerate(group.get('children') or []):
                session.add(Menu(parent_id=row.id, key=_key(child, group), label=child['label'], icon='',
                                 path=child.get('path', ''), sort_order=(child_index + 1) * 10, visible=1,
                                 admin_only=int(bool(child.get('admin') or group.get('admin'))),
                                 disabled=int(bool(child.get('disabled') or group.get('disabled'))),
                                 builtin=1, updated=at))
        session.flush()
    _migrate_legacy(session)


def _migrate_legacy(session) -> None:
    """旧版只把 false 存在 app_settings.menu_visibility，搬完后打标记，不再重复覆盖。"""
    if session.get(SchemaFlag, MIGRATED_FLAG):
        return
    hidden = set()
    row = session.get(AppSetting, 'menu_visibility')
    if row:
        try:
            stored = json.loads(row.value)
            visibility = stored.get('visibility', {}) if isinstance(stored, dict) else {}
            hidden = {key for key, value in visibility.items() if value is False}
        except (ValueError, TypeError):
            hidden = set()
    if '/system/settings' in hidden:
        hidden.add('/system/models')
    if hidden:
        for menu in session.execute(select(Menu)).scalars():
            if menu.key in hidden and menu.key not in PROTECTED:
                menu.visible = 0
    session.add(SchemaFlag(name=MIGRATED_FLAG))
    session.flush()


def revision(session) -> int:
    row = session.get(AppSetting, REVISION_KEY)
    try:
        return int(json.loads(row.value)['revision']) if row else 0
    except (ValueError, TypeError, KeyError):
        return 0


def _bump(session, at) -> int:
    value = revision(session) + 1
    row = session.get(AppSetting, REVISION_KEY)
    if row:
        row.value, row.updated = json.dumps({'revision': value}), at
    else:
        session.add(AppSetting(key=REVISION_KEY, value=json.dumps({'revision': value}), updated=at))
    session.flush()
    return value


def _node(row, children):
    return {'id': row.id, 'key': row.key, 'label': row.label, 'icon': row.icon or '',
            'path': row.path or '', 'visible': bool(row.visible),
            'admin_only': bool(row.admin_only), 'disabled': bool(row.disabled),
            'builtin': bool(row.builtin), 'protected': row.key in PROTECTED,
            'children': children or None}


def tree(session) -> list[dict]:
    """全量目录（菜单管理页使用），按 parent_id 组装成两层结构。"""
    rows = session.execute(select(Menu).order_by(Menu.sort_order, Menu.id)).scalars().all()
    by_parent: dict = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    return [_node(row, [_node(child, []) for child in by_parent.get(row.id, [])]) for row in by_parent.get(None, [])]


def hidden_map(session) -> dict:
    """兼容旧前端与旧接口：{菜单标识: false}。"""
    return {row.key: False for row in session.execute(select(Menu)).scalars() if not row.visible}


def visible_tree(session, user, permissions) -> list[dict]:
    """按账号下发的菜单：显示开关 → 仅管理员 → 角色权限，逐层过滤，空分组不返回。"""
    admin = user['role'] == 'admin'
    allowed = permissions or []

    def keep(node):
        if node['admin_only'] and not admin:
            return None
        if not node['visible'] and node['key'] not in PROTECTED:
            return None
        if node['children']:
            children = [child for child in (keep(item) for item in node['children']) if child]
            return {**node, 'children': children} if children else None
        permission = PERMISSIONS.get(node['path'])
        if not admin and permission and '*' not in allowed and permission not in allowed:
            return None
        return {**node, 'children': None}

    return [item for item in (keep(node) for node in tree(session)) if item]


def save(session, data, at):
    """保存显示开关（新版按行、旧版按 hidden map）或恢复默认；revision 防并发覆盖。"""
    current = revision(session)
    if data.get('action') == 'reset':
        for row in session.execute(select(Menu)).scalars():
            if row.key not in PROTECTED:
                row.visible = 1
                row.updated = at
        value = _bump(session, at)
    elif isinstance(data.get('menus'), list):
        if data.get('revision') != current:
            return {'error': '菜单设置已被其他管理员更新，请重新加载后再修改'}, 409
        for item in data['menus']:
            if not isinstance(item, dict):
                continue
            row = session.get(Menu, int(item.get('id') or 0))
            if not row:
                continue
            if 'visible' in item:
                if row.key in PROTECTED and not item['visible']:
                    raise ValueError('系统设置与菜单管理需保留管理员入口')
                row.visible = 1 if item['visible'] else 0
            if 'label' in item:
                label = str(item['label']).strip()
                if not label or len(label) > 60:
                    raise ValueError('菜单名称需为 1–60 个字符')
                row.label = label
            if 'sort' in item:
                row.sort_order = int(item['sort'])
            row.updated = at
        value = _bump(session, at)
    else:
        visibility = data.get('visibility')
        if not isinstance(visibility, dict) or len(visibility) > 200:
            raise ValueError('菜单显示设置需为对象，最多 200 项')
        for key, value in visibility.items():
            if not isinstance(key, str) or not key or len(key) > 200 or type(value) is not bool:
                raise ValueError('菜单显示设置需使用菜单标识及布尔值')
            if key in PROTECTED and not value:
                raise ValueError('系统设置与菜单管理需保留管理员入口')
        if data.get('revision') != current:
            return {'error': '菜单设置已被其他管理员更新，请重新加载后再修改'}, 409
        # 旧前端把「外部模型」记在 /system/settings 下，这里顺着迁移到新标识
        if visibility.get('/system/settings') is False:
            visibility = {key: value for key, value in visibility.items() if key != '/system/settings'}
            visibility.setdefault('/system/models', False)
        for row in session.execute(select(Menu)).scalars():
            row.visible = 0 if visibility.get(row.key) is False else 1
            row.updated = at
        value = _bump(session, at)
    return {'revision': value, 'visibility': hidden_map(session), 'menus': tree(session)}, 200
