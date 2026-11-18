"""角色菜单权限、部门/分组、用户账号、修改密码与登录策略。

分工：本模块管“谁能看到什么菜单、属于哪个部门、账号是否可用、密码怎么改”；
审批资格仍由 users.role(researcher/reviewer/compliance/publisher/admin) 决定，
自定义角色只在其 base_role 允许的能力范围内调整可见菜单，避免绕过审批链。
"""
import json
import secrets
import report_engine as e

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


def add_columns(c, table, columns):
    exists = {r[1] for r in c.execute('PRAGMA table_info(' + table + ')')}
    for key, definition in columns.items():
        if key not in exists:
            c.execute('ALTER TABLE ' + table + ' ADD COLUMN ' + key + ' ' + definition)


def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS departments(id INTEGER PRIMARY KEY,name TEXT,parent_id INTEGER,sort_order INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY,name TEXT UNIQUE,base_role TEXT,menus TEXT DEFAULT '[]',builtin INTEGER DEFAULT 0,enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS approval_flows(id INTEGER PRIMARY KEY,name TEXT,category_ids TEXT DEFAULT '[]',nodes TEXT DEFAULT '[]',enabled INTEGER DEFAULT 1);
    ''')
    add_columns(c, 'users', {'dept_id': 'INTEGER', 'phone': "TEXT DEFAULT ''", 'title': "TEXT DEFAULT ''",
                             'enabled': 'INTEGER DEFAULT 1', 'role_id': 'INTEGER',
                             'created_at': "TEXT DEFAULT ''", 'last_login_at': "TEXT DEFAULT ''"})
    add_columns(c, 'sessions', {'remember': 'INTEGER DEFAULT 0', 'last_seen': 'REAL DEFAULT 0'})
    if not c.execute('SELECT COUNT(*) FROM roles').fetchone()[0]:
        for code, label in BASE_ROLES:
            c.execute('INSERT INTO roles(name,base_role,menus,builtin) VALUES(?,?,?,1)',
                      (label, code, e.dump(DEFAULT_MENUS[code])))
    for row in list(c.execute('SELECT id,role FROM users WHERE role_id IS NULL')):
        match = c.execute('SELECT id FROM roles WHERE base_role=?', (row['role'],)).fetchone()
        if match:
            c.execute('UPDATE users SET role_id=? WHERE id=?', (match['id'], row['id']))
    c.execute("UPDATE users SET role='researcher' WHERE role IS NULL OR role=''")
    c.execute('UPDATE users SET enabled=1 WHERE enabled IS NULL')


def menus_for(c, u):
    if u['role'] == 'admin':
        return ['*']
    row = c.execute('SELECT menus FROM roles WHERE id=?', (u['role_id'],)).fetchone() if u['role_id'] else None
    if row:
        try:
            menus = json.loads(row['menus'])
            if isinstance(menus, list):
                return [m for m in menus if m in MENU_KEYS]
        except ValueError:
            pass
    return list(DEFAULT_MENUS.get(u['role'], ['工作台', '研报中心']))


def roles(c):
    return [{**dict(r), 'menus': json.loads(r['menus']), 'users': c.execute('SELECT COUNT(*) FROM users WHERE role_id=?', (r['id'],)).fetchone()[0]}
            for r in c.execute('SELECT * FROM roles ORDER BY builtin DESC,id')]


def departments(c):
    rows = [dict(r) for r in c.execute('SELECT * FROM departments ORDER BY sort_order,id')]
    index = {r['id']: r for r in rows}
    for r in rows:
        r['depth'] = 2 if r['parent_id'] else 1
        parent = index.get(r['parent_id'])
        r['parent_name'] = parent['name'] if parent else ''
        r['users'] = c.execute('SELECT COUNT(*) FROM users WHERE dept_id=?', (r['id'],)).fetchone()[0]
        r['effective_enabled'] = bool(r['enabled']) and (not parent or bool(parent['enabled']))
    return rows


def flows(c):
    return [{**dict(r), 'category_ids': json.loads(r['category_ids']), 'nodes': json.loads(r['nodes'])}
            for r in c.execute('SELECT * FROM approval_flows ORDER BY id')]


def users(c):
    return [dict(r) for r in c.execute('''SELECT u.id,u.name,u.role,u.dept_id,u.phone,u.title,u.enabled,u.role_id,
        u.created_at,u.last_login_at,r.name role_name,d.name dept_name
        FROM users u LEFT JOIN roles r ON r.id=u.role_id LEFT JOIN departments d ON d.id=u.dept_id ORDER BY u.id''')]


def clean_menus(base_role, value):
    if base_role == 'admin':
        return ['*']
    if not isinstance(value, list):
        raise ValueError('菜单权限格式错误')
    return [x for x in MENU_KEYS if x in value]


def clean_nodes(c, nodes):
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
            row = c.execute('SELECT role,enabled FROM users WHERE id=?', (int(raw),)).fetchone()
            if not row or row['role'] != role:
                raise ValueError('审批人「' + label + '」不存在或角色不符')
            picked.append(int(raw))
        picked = list(dict.fromkeys(picked))
        if mode != 'any' and not picked:
            raise ValueError('会签与依次审批必须指定审批人')
        labels.add(label)
        out.append({'label': label, 'role': role, 'mode': mode, 'users': picked})
    if not any(n['role'] == 'compliance' for n in out):
        raise ValueError('审批流必须包含合规审核节点')
    return out


def handle(c, path, d, u, stamp, password):
    if path == '/api/password':
        old = str(d.get('old', ''))
        new = str(d.get('new', ''))
        if len(new) < 6:
            return {'error': '新密码至少6位'}, 400
        if not hmac_equal(u['hash'], password(old, u['salt'])):
            return {'error': '原密码不正确'}, 400
        salt = secrets.token_hex(16)
        c.execute('UPDATE users SET salt=?,hash=? WHERE id=?', (salt, password(new, salt), u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?', (u['id'],))
        return {'ok': True, 'relogin': True}, 200

    if path in ['/api/users', '/api/departments', '/api/roles', '/api/approval-flows'] and u['role'] != 'admin':
        return {'error': '仅管理员可管理系统设置'}, 403

    if path == '/api/users':
        c.execute('BEGIN IMMEDIATE')
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = c.execute('SELECT * FROM users WHERE id=?', (rid,)).fetchone() if rid else None
        if rid and not target:
            return {'error': '账号不存在'}, 404
        if action == 'reset':
            new = str(d.get('password', ''))
            if len(new) < 6:
                raise ValueError('密码至少6位')
            salt = secrets.token_hex(16)
            c.execute('UPDATE users SET salt=?,hash=? WHERE id=?', (salt, password(new, salt), rid))
            c.execute('DELETE FROM sessions WHERE user_id=?', (rid,))
            return {'ok': True}, 200
        if action == 'toggle':
            if rid == u['id']:
                return {'error': '不能停用自己的账号'}, 400
            enabled = 0 if target['enabled'] else 1
            if not enabled and target['role'] == 'admin' and c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1:
                return {'error': '至少保留一个可用管理员'}, 400
            c.execute('UPDATE users SET enabled=? WHERE id=?', (enabled, rid))
            if not enabled:
                c.execute('DELETE FROM sessions WHERE user_id=?', (rid,))
            return {'ok': True}, 200
        name = e.text(d.get('name', target['name'] if target else ''), 40).strip()
        if not name:
            raise ValueError('姓名必填')
        role_row = None
        if d.get('role_id'):
            role_row = c.execute('SELECT * FROM roles WHERE id=?', (int(d['role_id']),)).fetchone()
        elif d.get('role'):
            role_row = c.execute('SELECT * FROM roles WHERE base_role=? ORDER BY builtin DESC,id', (d['role'],)).fetchone()
        if not role_row:
            raise ValueError('请选择有效角色')
        base = role_row['base_role']
        if base not in [x[0] for x in BASE_ROLES]:
            raise ValueError('角色类型无效')
        dept = int(d['dept_id']) if d.get('dept_id') else None
        if dept and not c.execute('SELECT 1 FROM departments WHERE id=?', (dept,)).fetchone():
            raise ValueError('部门不存在')
        phone = e.text(d.get('phone', target['phone'] if target else ''), 20).strip()
        title = e.text(d.get('title', target['title'] if target else ''), 40).strip()
        enabled = int(bool(d.get('enabled', target['enabled'] if target else 1)))
        if rid:
            if target['role'] == 'admin' and (base != 'admin' or not enabled):
                if c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1 AND id<>?").fetchone()[0] == 0:
                    return {'error': '至少保留一个可用管理员'}, 400
            c.execute('UPDATE users SET name=?,role=?,role_id=?,dept_id=?,phone=?,title=?,enabled=? WHERE id=?',
                      (name, base, role_row['id'], dept, phone, title, enabled, rid))
            if not enabled:
                c.execute('DELETE FROM sessions WHERE user_id=?', (rid,))
            return {'id': rid}, 200
        pw = str(d.get('password', ''))
        if len(pw) < 6:
            raise ValueError('初始密码至少6位')
        salt = secrets.token_hex(16)
        new_id = c.execute('INSERT INTO users(name,role,role_id,dept_id,phone,title,enabled,salt,hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (name, base, role_row['id'], dept, phone, title, enabled, salt, password(pw, salt), stamp())).lastrowid
        return {'id': new_id}, 200

    if path == '/api/departments':
        c.execute('BEGIN IMMEDIATE')
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = c.execute('SELECT * FROM departments WHERE id=?', (rid,)).fetchone() if rid else None
        if action == 'delete':
            if not target:
                return {'error': '部门不存在'}, 404
            if c.execute('SELECT 1 FROM departments WHERE parent_id=?', (rid,)).fetchone():
                return {'error': '请先删除下级分组'}, 400
            if c.execute('SELECT 1 FROM users WHERE dept_id=?', (rid,)).fetchone():
                return {'error': '该部门下仍有账号，请先调整所属部门'}, 400
            c.execute('DELETE FROM departments WHERE id=?', (rid,))
            return {'ok': True}, 200
        name = e.text(d.get('name', target['name'] if target else ''), 40).strip()
        if not name:
            raise ValueError('名称必填')
        parent = int(d['parent_id']) if d.get('parent_id') else None
        if parent:
            p = c.execute('SELECT * FROM departments WHERE id=?', (parent,)).fetchone()
            if not p:
                raise ValueError('上级部门不存在')
            if p['parent_id']:
                raise ValueError('部门最多两级，分组下不能再建分组')
            if rid and parent == rid:
                raise ValueError('上级不能是自己')
        if c.execute('SELECT 1 FROM departments WHERE name=? AND IFNULL(parent_id,0)=IFNULL(?,0) AND id<>?', (name, parent, rid or 0)).fetchone():
            raise ValueError('同级下已有同名部门或分组')
        order = int(d.get('sort_order', target['sort_order'] if target else 0) or 0)
        enabled = int(bool(d.get('enabled', target['enabled'] if target else 1)))
        if rid:
            c.execute('UPDATE departments SET name=?,parent_id=?,sort_order=?,enabled=? WHERE id=?', (name, parent, order, enabled, rid))
            return {'id': rid}, 200
        new_id = c.execute('INSERT INTO departments(name,parent_id,sort_order,enabled) VALUES(?,?,?,?)', (name, parent, order, enabled)).lastrowid
        return {'id': new_id}, 200

    if path == '/api/roles':
        c.execute('BEGIN IMMEDIATE')
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = c.execute('SELECT * FROM roles WHERE id=?', (rid,)).fetchone() if rid else None
        if action == 'delete':
            if not target:
                return {'error': '角色不存在'}, 404
            if target['builtin']:
                return {'error': '内置角色不可删除，可修改其菜单权限'}, 400
            if c.execute('SELECT 1 FROM users WHERE role_id=?', (rid,)).fetchone():
                return {'error': '该角色下仍有账号，请先调整账号角色'}, 400
            c.execute('DELETE FROM roles WHERE id=?', (rid,))
            return {'ok': True}, 200
        name = e.text(d.get('name', target['name'] if target else ''), 30).strip()
        base = d.get('base_role', target['base_role'] if target else 'researcher')
        if not name:
            raise ValueError('角色名称必填')
        if base not in [x[0] for x in BASE_ROLES]:
            raise ValueError('角色类型无效')
        if target and target['base_role'] == 'admin' and name != target['name']:
            raise ValueError('内置管理员角色名称不可修改')
        if target and target['builtin'] and base != target['base_role']:
            raise ValueError('内置角色的类型不可修改')
        menus = clean_menus(base, d.get('menus', json.loads(target['menus']) if target else DEFAULT_MENUS[base]))
        if rid:
            c.execute('UPDATE roles SET name=?,menus=? WHERE id=?', (name, e.dump(menus), rid))
            if base != target['base_role']:
                c.execute('UPDATE users SET role_id=?,role=? WHERE role_id=?', (rid, base, rid))
            return {'id': rid}, 200
        new_id = c.execute('INSERT INTO roles(name,base_role,menus,builtin) VALUES(?,?,?,0)', (name, base, e.dump(menus))).lastrowid
        return {'id': new_id}, 200

    if path == '/api/approval-flows':
        c.execute('BEGIN IMMEDIATE')
        action = d.get('action', 'create')
        rid = int(d['id']) if d.get('id') else None
        target = c.execute('SELECT * FROM approval_flows WHERE id=?', (rid,)).fetchone() if rid else None
        if action == 'delete':
            if not target:
                return {'error': '审批流不存在'}, 404
            c.execute('DELETE FROM approval_flows WHERE id=?', (rid,))
            return {'ok': True}, 200
        name = e.text(d.get('name', target['name'] if target else ''), 40).strip()
        if not name:
            raise ValueError('审批流名称必填')
        cats = [int(x) for x in (d.get('category_ids') or [])]
        for cid in cats:
            if not c.execute('SELECT 1 FROM categories WHERE id=?', (cid,)).fetchone():
                raise ValueError('关联的分类不存在')
        nodes = clean_nodes(c, d.get('nodes', json.loads(target['nodes']) if target else []))
        enabled = int(bool(d.get('enabled', target['enabled'] if target else 1)))
        if rid:
            c.execute('UPDATE approval_flows SET name=?,category_ids=?,nodes=?,enabled=? WHERE id=?',
                      (name, e.dump(cats), e.dump(nodes), enabled, rid))
            return {'id': rid}, 200
        new_id = c.execute('INSERT INTO approval_flows(name,category_ids,nodes,enabled) VALUES(?,?,?,?)',
                           (name, e.dump(cats), e.dump(nodes), enabled)).lastrowid
        return {'id': new_id}, 200
    return None


def hmac_equal(a, b):
    import hmac
    return hmac.compare_digest(a, b)
