"""云盘、文档、素材库。数据访问走 ORM（``s`` 为 SQLAlchemy Session）。"""
import base64
from sqlalchemy import func, select, update
import db
import report_engine as e
from db import Event, LibraryItem, Report


def migrate(s):
    db.create_schema()
    db.add_columns(s, 'reports', {'updated_by': "TEXT DEFAULT ''", 'published_at': "TEXT DEFAULT ''",
                                  'approved_at': "TEXT DEFAULT ''", 'views': 'INTEGER DEFAULT 0',
                                  'issue': 'INTEGER DEFAULT 0', 'deleted': 'INTEGER DEFAULT 0'})
    # 期号回填：老数据 issue=0 时，按分类内 id 顺序补齐（与历史行为一致）
    categories = [row[0] for row in s.execute(select(Report.category_id).where(Report.issue == 0).distinct())]
    for cid in categories:
        query = select(Report).where(Report.category_id.is_(None) if cid is None else Report.category_id == cid).order_by(Report.id)
        for index, report in enumerate(s.execute(query).scalars().all(), 1):
            if not report.issue:
                report.issue = index
    # 更新人回填：取该报告最后一条事件的操作者
    latest_actor = (select(Event.actor).where(Event.report_id == Report.id)
                    .order_by(Event.id.desc()).limit(1)).scalar_subquery()
    s.execute(update(Report).where(Report.updated_by == '')
              .values(updated_by=func.coalesce(latest_actor, '')))


def items(s):
    rows = s.execute(
        select(LibraryItem.id, LibraryItem.area, LibraryItem.kind, LibraryItem.name, LibraryItem.parent_id,
               LibraryItem.owner, LibraryItem.body, LibraryItem.mime, LibraryItem.updated,
               func.length(LibraryItem.blob).label('size'))
        .where(LibraryItem.deleted == 0).order_by(LibraryItem.id.desc()))
    return [dict(r._mapping) for r in rows]


def depth(s, item_id):
    level = 0
    cur = item_id
    while cur:
        row = s.get(LibraryItem, cur)
        if not row:
            break
        level += 1
        cur = row.parent_id
    return level


def _descendants(s, item_id):
    seen = set()
    pending = [item_id]
    while pending:
        cur = pending.pop()
        children = s.execute(select(LibraryItem.id).where(LibraryItem.parent_id == cur, LibraryItem.deleted == 0)).scalars()
        for child in children:
            if child not in seen:
                seen.add(child)
                pending.append(child)
    return seen


def _live(s, item_id):
    row = s.get(LibraryItem, item_id) if item_id else None
    return None if not row or row.deleted else row


def _has_children(s, item_id):
    return s.execute(select(LibraryItem.id).where(LibraryItem.parent_id == item_id,
                                                  LibraryItem.deleted == 0).limit(1)).first() is not None


def handle(s, path, d, u, stamp):
    if path == '/api/library/batch':
        ids = [int(x) for x in (d.get('ids') or [])]
        if not ids or len(ids) > 200:
            raise ValueError('请选择1至200项')
        rows = []
        for rid in dict.fromkeys(ids):
            row = _live(s, rid)
            if not row:
                return {'error': '存在无效的资料项，请刷新后重试'}, 404
            if u['role'] != 'admin' and row.owner != u['id']:
                return {'error': '仅创建人或管理员可批量操作'}, 403
            rows.append(row)
        action = d.get('action')
        if action == 'delete':
            for row in rows:
                if _has_children(s, row.id):
                    return {'error': '「' + row.name + '」下仍有内容，请先清空'}, 400
            for row in rows:
                row.deleted = 1
            return {'ok': True, 'count': len(rows)}, 200
        if action == 'move':
            parent = int(d['parent_id']) if d.get('parent_id') else None
            target = None
            if parent:
                target = _live(s, parent)
                if not target or target.kind != 'folder':
                    raise ValueError('目标目录无效')
            for row in rows:
                target_area = target.area if target else row.area
                if target_area != row.area:
                    raise ValueError('不能跨区域移动资料')
                if target and row.kind == 'folder' and (parent == row.id or parent in _descendants(s, row.id)):
                    raise ValueError('不能移动到自身或子目录')
                if row.area == 'materials' and target and depth(s, parent) >= 3:
                    raise ValueError('素材库最多三级分类')
                row.parent_id = parent
                row.updated = stamp()
            return {'ok': True, 'count': len(rows)}, 200
        raise ValueError('不支持的批量操作')
    if path != '/api/library':
        return None
    action = d['action']
    rid = int(d['item_id']) if d.get('item_id') else None
    row = _live(s, rid)
    if rid and not row:
        return {'error': '资料不存在'}, 404
    if row and u['role'] != 'admin' and row.owner != u['id']:
        return {'error': '仅创建人或管理员可修改资料'}, 403
    if action == 'delete':
        if not row:
            return {'ok': True}, 200
        if _has_children(s, rid):
            return {'error': '请先移动或移除文件夹内容'}, 400
        row.deleted = 1
        return {'ok': True}, 200
    if action not in ['create', 'edit']:
        raise ValueError('资料操作无效')
    area = d.get('area', row.area if row else 'cloud')
    kind = d.get('kind', row.kind if row else 'document')
    name = e.text(d['name'], 120).strip()
    parent = int(d['parent_id']) if d.get('parent_id') else None
    if not name or area not in ['cloud', 'docs', 'materials'] or kind not in ['folder', 'document', 'file', 'image']:
        raise ValueError('资料类型或名称无效')
    if row and (area != row.area or kind != row.kind):
        raise ValueError('不能改变资料类型')
    if parent:
        p = _live(s, parent)
        if not p or p.kind != 'folder' or p.area != area:
            raise ValueError('目标目录无效')
        if area == 'materials' and depth(s, parent) >= 3:
            raise ValueError('素材库最多三级分类')
        seen = {rid}
        while p:
            if p.id in seen:
                raise ValueError('不能循环移动文件夹')
            seen.add(p.id)
            p = s.get(LibraryItem, p.parent_id) if p.parent_id else None
    body = e.text(d.get('body', row.body if row else ''), 500000)
    blob = row.blob if row else None
    mime = row.mime if row else ''
    if 'base64' in d:
        blob = base64.b64decode(d['base64'], validate=True)
        if len(blob) > 5_000_000:
            raise ValueError('单个文件最多5MB')
        mime = ('image/png' if blob.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if blob.startswith(b'\xff\xd8\xff')
                else 'image/webp' if blob.startswith(b'RIFF') and blob[8:12] == b'WEBP' else 'application/octet-stream')
        if kind == 'image' and mime == 'application/octet-stream':
            raise ValueError('素材支持PNG、JPEG、WebP图片')
    if kind in ['image', 'file'] and blob is None:
        raise ValueError('请选择文件')
    if row:
        row.name = name
        row.parent_id = parent
        row.body = body
        row.updated = stamp()
    else:
        row = LibraryItem(area=area, kind=kind, name=name, parent_id=parent, owner=u['id'],
                          body=body, blob=blob, mime=mime, updated=stamp())
        s.add(row)
        s.flush()
        rid = row.id
    return {'id': rid}, 200
