"""角色菜单权限、部门/分组、用户账号、修改密码与登录策略。

分工：本模块管“谁能看到什么菜单、属于哪个部门、账号是否可用、密码怎么改”；
审批资格仍由 users.role(researcher/reviewer/compliance/publisher/admin) 决定，
自定义角色只在其 base_role 允许的能力范围内调整可见菜单，避免绕过审批链。

数据访问一律走 ORM：``s`` 是 SQLAlchemy Session。
"""
import json
import secrets
from sqlalchemy import delete, func, select
import db
import report_engine as e
from db import ApprovalFlow, Category, Department, Role, SessionRow, User

BASE_ROLES = [('admin', '管理员'), ('researcher', '研究员'), ('reviewer', '研究复核'),
              ('compliance', '合规审核'), ('publisher', '发布专员')]

MENU_KEYS = ['工作台', '数据中心', '研报中心', '审核中心', '云盘', '文档管理库', '素材库',
             '分类配置', '作者管理', '品种管理', '审批流配置', '角色管理', '部门管理', '系统管理']

DEFAULT_MENUS = {
    'admin': ['*'],
    'researcher': ['工作台', '数据中心', '研报中心', '云盘', '文档管理库', '素材库'],
    'reviewer': ['工作台', '研报中心', '审核中心', '云盘', '文档管理库', '素材库'],
    'compliance': ['工作台', '研报中心', '审核中心', '云盘', '文档管理库', '素材库'],
    'publisher': ['工作台', '研报中心', '审核中心', '云盘', '文档管理库', '素材库'],
}

IDLE_SECONDS = 1800
REMEMBER_DAYS = 30


def add_columns(s, table, columns):
    db.add_columns(s, table, columns)


def migrate(s):
    db.create_schema()
    add_columns(s, 'users', {'dept_id': 'INTEGER', 'phone': "TEXT DEFAULT ''", 'title': "TEXT DEFAULT ''",
                             'enabled': 'INTEGER DEFAULT 1', 'role_id': 'INTEGER',
                             'created_at': "TEXT DEFAULT ''", 'last_login_at': "TEXT DEFAULT ''"})
    add_columns(s, 'sessions', {'remember': 'INTEGER DEFAULT 0', 'last_seen': 'REAL DEFAULT 0'})
    if not s.execute(select(func.count()).select_from(Role)).scalar():
        for code, label in BASE_ROLES:
            s.add(Role(name=label, base_role=code, menus=e.dump(DEFAULT_MENUS[code]), builtin=1))
    s.flush()
    for account in s.execute(select(User).where(User.role_id.is_(None))).scalars().all():
        match = s.execute(select(Role).where(Role.base_role == account.role).limit(1)).scalars().first()
        if match:
            account.role_id = match.id
    for account in s.execute(select(User).where((User.role.is_(None)) | (User.role == ''))).scalars().all():
        account.role = 'researcher'
    for account in s.execute(select(User).where(User.enabled.is_(None))).scalars().all():
        account.enabled = 1


def menus_for(s, u):
    if u['role'] == 'admin':
        return ['*']
    role = s.get(Role, u['role_id']) if u['role_id'] else None
    if role:
        try:
            menus = json.loads(role.menus)
            if isinstance(menus, list):
                return [m for m in menus if m in MENU_KEYS]
        except ValueError:
            pass
    return list(DEFAULT_MENUS.get(u['role'], ['工作台', '研报中心']))


def roles(s):
    counts = dict(s.execute(select(User.role_id, func.count()).group_by(User.role_id)).all())
    out = []
    for role in s.execute(select(Role).order_by(Role.builtin.desc(), Role.id)).scalars():
        item = role.to_dict()
        item['menus'] = json.loads(role.menus)
        item['users'] = counts.get(role.id, 0)
        out.append(item)
    return out


def departments(s):
    rows = [x.to_dict() for x in s.execute(select(Department).order_by(Department.sort_order, Department.id)).scalars()]
    index = {r['id']: r for r in rows}
    counts = dict(s.execute(select(User.dept_id, func.count()).group_by(User.dept_id)).all())
    for r in rows:
        r['depth'] = 2 if r['parent_id'] else 1
        parent = index.get(r['parent_id'])
        r['parent_name'] = parent['name'] if parent else ''
        r['users'] = counts.get(r['id'], 0)
        r['effective_enabled'] = bool(r['enabled']) and (not parent or bool(parent['enabled']))
    return rows


def flows(s):
    return [{**x.to_dict(), 'category_ids': json.loads(x.category_ids), 'nodes': json.loads(x.nodes)}
            for x in s.execute(select(ApprovalFlow).order_by(ApprovalFlow.id)).scalars()]


def users(s):
    rows = s.execute(
        select(User.id, User.name, User.role, User.dept_id, User.phone, User.title, User.enabled,
               User.role_id, User.created_at, User.last_login_at,
               Role.name.label('role_name'), Department.name.label('dept_name'))
        .outerjoin(Role, Role.id == User.role_id)
        .outerjoin(Department, Department.id == User.dept_id)
        .order_by(User.id))
    return [dict(r._mapping) for r in rows]


def clean_menus(base_role, value):
    if base_role == 'admin':
        return ['*']
    if not isinstance(value, list):
        raise ValueError('菜单权限格式错误')
    return [x for x in MENU_KEYS if x in value]


def clean_nodes(s, nodes):
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise ValueError('请配置1至8个审批节点')
    out = []
    labels = set()
    for node in nodes:
        label = e.text(node.get('label', ''), 30).strip()
        role = node.get('role')
        mode = node.get('mode', 'any')
        if not label or label in labels:
            raise ValueError('审批节点名称为空或重复')
        if role not in ['reviewer', 'compliance']:
            raise ValueError('审批角色不合法')
        if mode not in ['any', 'all', 'sequential']:
            raise ValueError('审批方式不合法')
        picked = []
        for raw in node.get('users', []) or []:
            account = s.get(User, int(raw))
            if not account or not account.enabled or account.role != role:
                raise ValueError('审批人「' + label + '」不存在、已停用或角色不符')
            picked.append(int(raw))
        picked = list(dict.fromkeys(picked))
        if mode != 'any' and not picked:
            raise ValueError('会签与依次审批必须指定审批人')
        labels.add(label)
        out.append({'label': label, 'role': role, 'mode': mode, 'users': picked})
    if not any(n['role'] == 'compliance' for n in out):
        raise ValueError('审批流必须包含合规审核节点')
    return out


def _admin_count(s, exclude=None):
    query = select(func.count()).select_from(User).where(User.role == 'admin', User.enabled == 1)
    if exclude is not None:
        query = query.where(User.id != exclude)
    return s.execute(query).scalar()


def _drop_sessions(s, uid):
    s.execute(delete(SessionRow).where(SessionRow.user_id == uid))


def handle(s, path, d, u, stamp, password):
    if path == '/api/password':
        old = str(d.get('old', ''))
        new = str(d.get('new', ''))
        if len(new) < 6:
            return {'error': '新密码至少6位'}, 400
        if not hmac_equal(u['hash'], password(old, u['salt'])):
            return {'error': '原密码不正确'}, 400
        salt = secrets.token_hex(16)
        account = s.get(User, u['id'])
        account.salt = salt
        account.hash = password(new, salt)
        _drop_sessions(s, u['id'])
        return {'ok': True, 'relogin': True}, 200

    if path in ['/api/users', '/api/departments', '/api/roles', '/api/approval-flows'] and u['role'] != 'admin':
        return {'error': '仅管理员可管理系统设置'}, 403

    if path == '/api/users':
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = s.get(User, rid) if rid else None
        if rid and not target:
            return {'error': '账号不存在'}, 404
        if action == 'reset':
            new = str(d.get('password', ''))
            if len(new) < 6:
                raise ValueError('密码至少6位')
            salt = secrets.token_hex(16)
            target.salt = salt
            target.hash = password(new, salt)
            _drop_sessions(s, rid)
            return {'ok': True}, 200
        if action == 'toggle':
            if rid == u['id']:
                return {'error': '不能停用自己的账号'}, 400
            enabled = 0 if target.enabled else 1
            if not enabled and target.role == 'admin' and _admin_count(s) <= 1:
                return {'error': '至少保留一个可用管理员'}, 400
            target.enabled = enabled
            if not enabled:
                _drop_sessions(s, rid)
            return {'ok': True}, 200
        name = e.text(d.get('name', target.name if target else ''), 40).strip()
        if not name:
            raise ValueError('姓名必填')
        role_row = None
        if d.get('role_id'):
            role_row = s.get(Role, int(d['role_id']))
        elif d.get('role'):
            role_row = s.execute(select(Role).where(Role.base_role == d['role'])
                                 .order_by(Role.builtin.desc(), Role.id).limit(1)).scalars().first()
        if not role_row:
            raise ValueError('请选择有效角色')
        base = role_row.base_role
        if base not in [x[0] for x in BASE_ROLES]:
            raise ValueError('角色类型无效')
        dept = int(d['dept_id']) if d.get('dept_id') else None
        if dept and not s.get(Department, dept):
            raise ValueError('部门不存在')
        phone = e.text(d.get('phone', target.phone if target else ''), 20).strip()
        title = e.text(d.get('title', target.title if target else ''), 40).strip()
        enabled = int(bool(d.get('enabled', target.enabled if target else 1)))
        if rid:
            if target.role == 'admin' and (base != 'admin' or not enabled):
                if _admin_count(s, exclude=rid) == 0:
                    return {'error': '至少保留一个可用管理员'}, 400
            target.name = name
            target.role = base
            target.role_id = role_row.id
            target.dept_id = dept
            target.phone = phone
            target.title = title
            target.enabled = enabled
            if not enabled:
                _drop_sessions(s, rid)
            return {'id': rid}, 200
        pw = str(d.get('password', ''))
        if len(pw) < 6:
            raise ValueError('初始密码至少6位')
        salt = secrets.token_hex(16)
        account = User(name=name, role=base, role_id=role_row.id, dept_id=dept, phone=phone, title=title,
                       enabled=enabled, salt=salt, hash=password(pw, salt), created_at=stamp())
        s.add(account)
        s.flush()
        return {'id': account.id}, 200

    if path == '/api/departments':
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = s.get(Department, rid) if rid else None
        if action == 'delete':
            if not target:
                return {'error': '部门不存在'}, 404
            if s.execute(select(Department.id).where(Department.parent_id == rid).limit(1)).first():
                return {'error': '请先删除下级分组'}, 400
            if s.execute(select(User.id).where(User.dept_id == rid).limit(1)).first():
                return {'error': '该部门下仍有账号，请先调整所属部门'}, 400
            s.delete(target)
            return {'ok': True}, 200
        name = e.text(d.get('name', target.name if target else ''), 40).strip()
        if not name:
            raise ValueError('名称必填')
        parent = int(d['parent_id']) if d.get('parent_id') else None
        if parent:
            p = s.get(Department, parent)
            if not p:
                raise ValueError('上级部门不存在')
            if p.parent_id:
                raise ValueError('部门最多两级，分组下不能再建分组')
            if rid and parent == rid:
                raise ValueError('上级不能是自己')
        same_parent = Department.parent_id.is_(None) if parent is None else Department.parent_id == parent
        if s.execute(select(Department.id).where(Department.name == name, same_parent,
                                                 Department.id != (rid or 0)).limit(1)).first():
            raise ValueError('同级下已有同名部门或分组')
        order = int(d.get('sort_order', target.sort_order if target else 0) or 0)
        enabled = int(bool(d.get('enabled', target.enabled if target else 1)))
        if rid:
            target.name = name
            target.parent_id = parent
            target.sort_order = order
            target.enabled = enabled
            return {'id': rid}, 200
        row = Department(name=name, parent_id=parent, sort_order=order, enabled=enabled)
        s.add(row)
        s.flush()
        return {'id': row.id}, 200

    if path == '/api/roles':
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = s.get(Role, rid) if rid else None
        if action == 'delete':
            if not target:
                return {'error': '角色不存在'}, 404
            if target.builtin:
                return {'error': '内置角色不可删除，可修改其菜单权限'}, 400
            if s.execute(select(User.id).where(User.role_id == rid).limit(1)).first():
                return {'error': '该角色下仍有账号，请先调整账号角色'}, 400
            s.delete(target)
            return {'ok': True}, 200
        name = e.text(d.get('name', target.name if target else ''), 30).strip()
        base = d.get('base_role', target.base_role if target else 'researcher')
        if not name:
            raise ValueError('角色名称必填')
        if base not in [x[0] for x in BASE_ROLES]:
            raise ValueError('角色类型无效')
        if target and target.base_role == 'admin' and name != target.name:
            raise ValueError('内置管理员角色名称不可修改')
        if target and target.builtin and base != target.base_role:
            raise ValueError('内置角色的类型不可修改')
        menus = clean_menus(base, d.get('menus', json.loads(target.menus) if target else DEFAULT_MENUS[base]))
        if rid:
            target.name = name
            target.menus = e.dump(menus)
            if base != target.base_role:
                for account in s.execute(select(User).where(User.role_id == rid)).scalars().all():
                    account.role = base
            return {'id': rid}, 200
        row = Role(name=name, base_role=base, menus=e.dump(menus), builtin=0)
        s.add(row)
        s.flush()
        return {'id': row.id}, 200

    if path == '/api/approval-flows':
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = s.get(ApprovalFlow, rid) if rid else None
        if action == 'delete':
            if not target:
                return {'error': '审批流不存在'}, 404
            s.delete(target)
            return {'ok': True}, 200
        name = e.text(d.get('name', target.name if target else ''), 40).strip()
        if not name:
            raise ValueError('审批流名称必填')
        cats = [int(x) for x in (d.get('category_ids') or [])]
        for cid in cats:
            if not s.get(Category, cid):
                raise ValueError('关联的分类不存在')
        nodes = clean_nodes(s, d.get('nodes', json.loads(target.nodes) if target else []))
        enabled = int(bool(d.get('enabled', target.enabled if target else 1)))
        if rid:
            target.name = name
            target.category_ids = e.dump(cats)
            target.nodes = e.dump(nodes)
            target.enabled = enabled
            return {'id': rid}, 200
        row = ApprovalFlow(name=name, category_ids=e.dump(cats), nodes=e.dump(nodes), enabled=enabled)
        s.add(row)
        s.flush()
        return {'id': row.id}, 200
    return None


def hmac_equal(a, b):
    import hmac
    return hmac.compare_digest(a or '', b or '')
