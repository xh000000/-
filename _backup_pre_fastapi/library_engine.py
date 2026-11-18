import base64
import report_engine as e

def migrate(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS library_items(id INTEGER PRIMARY KEY,area TEXT,kind TEXT,name TEXT,parent_id INTEGER,owner INTEGER,body TEXT DEFAULT '',blob BLOB,mime TEXT DEFAULT '',updated TEXT,deleted INTEGER DEFAULT 0);''')
    for key,definition in [('updated_by',"TEXT DEFAULT ''"),('published_at',"TEXT DEFAULT ''"),('approved_at',"TEXT DEFAULT ''"),('views','INTEGER DEFAULT 0'),('issue','INTEGER DEFAULT 0'),('deleted','INTEGER DEFAULT 0')]:
        if key not in {r[1] for r in c.execute('PRAGMA table_info(reports)')}:c.execute('ALTER TABLE reports ADD COLUMN '+key+' '+definition)
    for cid, in c.execute('SELECT DISTINCT category_id FROM reports WHERE issue=0'):
        for i,r in enumerate(c.execute('SELECT id FROM reports WHERE category_id IS ? ORDER BY id',(cid,)),1):c.execute('UPDATE reports SET issue=? WHERE id=? AND issue=0',(i,r['id']))
    c.execute("UPDATE reports SET updated_by=COALESCE((SELECT actor FROM events WHERE report_id=reports.id ORDER BY id DESC LIMIT 1),'') WHERE updated_by=''")
def items(c):return [dict(r) for r in c.execute('SELECT id,area,kind,name,parent_id,owner,body,mime,updated,length(blob) size FROM library_items WHERE deleted=0 ORDER BY id DESC')]
def depth(c,item_id):
    level=0;cur=item_id
    while cur:
        row=c.execute('SELECT parent_id FROM library_items WHERE id=?',(cur,)).fetchone()
        if not row:break
        level+=1;cur=row['parent_id']
    return level
def _descendants(c,item_id):
    seen=set();pending=[item_id]
    while pending:
        cur=pending.pop()
        for row in c.execute('SELECT id FROM library_items WHERE parent_id=? AND deleted=0',(cur,)):
            if row['id'] not in seen:seen.add(row['id']);pending.append(row['id'])
    return seen
def handle(c,path,d,u,stamp):
    if path=='/api/library/batch':
        c.execute('BEGIN IMMEDIATE')
        ids=[int(x) for x in (d.get('ids') or [])]
        if not ids or len(ids)>200:raise ValueError('请选择1至200项')
        rows=[]
        for rid in dict.fromkeys(ids):
            row=c.execute('SELECT * FROM library_items WHERE id=? AND deleted=0',(rid,)).fetchone()
            if not row:return {'error':'存在无效的资料项，请刷新后重试'},404
            if u['role']!='admin' and row['owner']!=u['id']:return {'error':'仅创建人或管理员可批量操作'},403
            rows.append(row)
        action=d.get('action')
        if action=='delete':
            for row in rows:
                if c.execute('SELECT 1 FROM library_items WHERE parent_id=? AND deleted=0',(row['id'],)).fetchone():return {'error':'「'+row['name']+'」下仍有内容，请先清空'},400
            for row in rows:c.execute('UPDATE library_items SET deleted=1 WHERE id=?',(row['id'],))
            return {'ok':True,'count':len(rows)},200
        if action=='move':
            parent=int(d['parent_id']) if d.get('parent_id') else None
            if parent:
                p=c.execute('SELECT * FROM library_items WHERE id=? AND deleted=0',(parent,)).fetchone()
                if not p or p['kind']!='folder':raise ValueError('目标目录无效')
            for row in rows:
                target_area=p['area'] if parent else row['area']
                if target_area!=row['area']:raise ValueError('不能跨区域移动资料')
                if parent and row['kind']=='folder' and (parent==row['id'] or parent in _descendants(c,row['id'])):raise ValueError('不能移动到自身或子目录')
                if row['area']=='materials' and parent and depth(c,parent)>=3:raise ValueError('素材库最多三级分类')
                c.execute('UPDATE library_items SET parent_id=?,updated=? WHERE id=?',(parent,stamp(),row['id']))
            return {'ok':True,'count':len(rows)},200
        raise ValueError('不支持的批量操作')
    if path!='/api/library':return None
    c.execute('BEGIN IMMEDIATE');action=d['action'];rid=int(d['item_id']) if d.get('item_id') else None;r=c.execute('SELECT * FROM library_items WHERE id=? AND deleted=0',(rid,)).fetchone() if rid else None
    if rid and not r:return {'error':'资料不存在'},404
    if r and u['role']!='admin' and r['owner']!=u['id']:return {'error':'仅创建人或管理员可修改资料'},403
    if action=='delete':
        if c.execute('SELECT 1 FROM library_items WHERE parent_id=? AND deleted=0',(rid,)).fetchone():return {'error':'请先移动或移除文件夹内容'},400
        c.execute('UPDATE library_items SET deleted=1 WHERE id=?',(rid,));return {'ok':True},200
    if action not in ['create','edit']:raise ValueError('资料操作无效')
    area=d.get('area',r['area'] if r else 'cloud');kind=d.get('kind',r['kind'] if r else 'document');name=e.text(d['name'],120).strip();parent=int(d['parent_id']) if d.get('parent_id') else None
    if not name or area not in ['cloud','docs','materials'] or kind not in ['folder','document','file','image']:raise ValueError('资料类型或名称无效')
    if r and (area!=r['area'] or kind!=r['kind']):raise ValueError('不能改变资料类型')
    if parent:
        p=c.execute('SELECT * FROM library_items WHERE id=? AND deleted=0',(parent,)).fetchone()
        if not p or p['kind']!='folder' or p['area']!=area:raise ValueError('目标目录无效')
        if area=='materials' and depth(c,parent)>=3:raise ValueError('素材库最多三级分类')
        seen={rid}
        while p:
            if p['id'] in seen:raise ValueError('不能循环移动文件夹')
            seen.add(p['id']);p=c.execute('SELECT * FROM library_items WHERE id=?',(p['parent_id'],)).fetchone() if p['parent_id'] else None
    body=e.text(d.get('body',r['body'] if r else ''),500000);blob=r['blob'] if r else None;mime=r['mime'] if r else ''
    if 'base64' in d:
        blob=base64.b64decode(d['base64'],validate=True)
        if len(blob)>5_000_000:raise ValueError('单个文件最多5MB')
        mime='image/png' if blob.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if blob.startswith(b'\xff\xd8\xff') else 'image/webp' if blob.startswith(b'RIFF') and blob[8:12]==b'WEBP' else 'application/octet-stream'
        if kind=='image' and mime=='application/octet-stream':raise ValueError('素材支持PNG、JPEG、WebP图片')
    if kind in ['image','file'] and blob is None:raise ValueError('请选择文件')
    if r:c.execute('UPDATE library_items SET name=?,parent_id=?,body=?,updated=? WHERE id=?',(name,parent,body,stamp(),rid))
    else:rid=c.execute('INSERT INTO library_items(area,kind,name,parent_id,owner,body,blob,mime,updated) VALUES(?,?,?,?,?,?,?,?,?)',(area,kind,name,parent,u['id'],body,blob,mime,stamp())).lastrowid
    return {'id':rid},200
