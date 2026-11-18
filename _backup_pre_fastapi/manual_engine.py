"""Manual-aligned business objects and chapter collaboration. No browser-only authorization."""
import json,re,datetime
import report_engine as e

def add_columns(c,table,columns):
    exists={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
    for k,v in columns.items():
        if k not in exists:c.execute('ALTER TABLE '+table+' ADD COLUMN '+k+' '+v)

def migrate(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS schema_flags(name TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS authors(id INTEGER PRIMARY KEY,name TEXT UNIQUE,types TEXT,enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS commodities(id INTEGER PRIMARY KEY,name TEXT UNIQUE,parent_id INTEGER,enabled INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS category_migration(category_id INTEGER PRIMARY KEY,original_name TEXT,parent_id INTEGER);
    ''')
    add_columns(c,'categories',{'parent_id':'INTEGER','label':"TEXT DEFAULT ''",'sort_order':'INTEGER DEFAULT 0','folder':'INTEGER DEFAULT 0'})
    add_columns(c,'reports',{'metadata':"TEXT DEFAULT ''"})
    add_columns(c,'versions',{'metadata':"TEXT DEFAULT ''"})
    add_columns(c,'authors',{'license':"TEXT DEFAULT ''"})
    if not c.execute('SELECT 1 FROM schema_flags WHERE name=?',('manual-v1',)).fetchone():
        for cat in list(c.execute('SELECT * FROM categories ORDER BY id')):
            parts=[s.strip() for s in cat['name'].split('/') if s.strip()] or [cat['name']]
            if len(parts)>3:parts=parts[:2]+['／'.join(parts[2:])]
            parent=None;path=[]
            for label in parts[:-1]:
                path.append(label);name=' / '.join(path);row=c.execute('SELECT id FROM categories WHERE name=?',(name,)).fetchone()
                if row:parent=row['id'];c.execute('UPDATE categories SET folder=1 WHERE id=?',(parent,))
                else:parent=c.execute('INSERT INTO categories(name,config,parent_id,label,folder) VALUES(?,?,?,?,1)',(name,cat['config'],parent,label)).lastrowid
            c.execute('UPDATE categories SET parent_id=?,label=? WHERE id=?',(parent,parts[-1],cat['id']))
            c.execute('INSERT OR IGNORE INTO category_migration VALUES(?,?,?)',(cat['id'],cat['name'],parent))
        names=set()
        for r in c.execute('SELECT config FROM categories'):
            names.update(json.loads(r['config']).get('commodities',[]))
        for name in sorted(names):c.execute('INSERT OR IGNORE INTO commodities(name) VALUES(?)',(name,))
        c.execute('INSERT OR IGNORE INTO authors(name,types) VALUES(?,?)',('研究中心',e.dump(['日报','周报','专题','调研纪要'])))
        c.execute('INSERT INTO schema_flags VALUES(?)',('manual-v1',))
    seed_commodity_tree(c)

# 《兴业期货日度策略》覆盖的期货品种：板块 →（品种, 合约代码），与合集「三、金融与商品基本面展望」下的 01～06 一一对应。
COMMODITY_TREE = {
    '金融衍生品': [('股指', 'IF/IH/IC/IM'), ('国债', 'T/TF/TS/TL')],
    '贵金属': [('黄金', 'AU'), ('白银', 'AG')],
    '有色与新能源': [('铜', 'CU'), ('铝', 'AL'), ('氧化铝', 'AO'), ('镍', 'NI'), ('工业硅', 'SI'), ('多晶硅', 'PS')],
    '黑色建材': [('螺纹钢', 'RB'), ('热卷', 'HC'), ('铁矿石', 'I'), ('焦煤', 'JM'), ('焦炭', 'J'), ('纯碱', 'SA'), ('玻璃', 'FG')],
    '能源化工': [('原油', 'SC'), ('甲醇', 'MA'), ('PVC', 'V')],
    '农产品': [('棕榈油', 'P'), ('豆油', 'Y'), ('菜籽油', 'OI'), ('豆粕', 'M'), ('棉花', 'CF'), ('白糖', 'SR')],
}


def seed_commodity_tree(c):
    """把品种库补成「板块 → 期货品种（含合约代码）」，并把日度策略各章节的关联品种对上。幂等。"""
    add_columns(c, 'commodities', {'code': "TEXT DEFAULT ''"})
    if c.execute("SELECT 1 FROM schema_flags WHERE name='commodity-tree-v1'").fetchone():
        return
    sectors = {}
    for sector, items in COMMODITY_TREE.items():
        row = c.execute('SELECT id FROM commodities WHERE name=?', (sector,)).fetchone()
        if row:
            c.execute('UPDATE commodities SET parent_id=NULL,enabled=1 WHERE id=?', (row['id'],))
            sid = row['id']
        else:
            sid = c.execute('INSERT INTO commodities(name,parent_id,enabled) VALUES(?,?,1)', (sector, None)).lastrowid
        ids = []
        for name, code in items:
            row = c.execute('SELECT id FROM commodities WHERE name=?', (name,)).fetchone()
            if row:
                c.execute('UPDATE commodities SET parent_id=?,code=?,enabled=1 WHERE id=?', (sid, code, row['id']))
                ids.append(row['id'])
            else:
                ids.append(c.execute('INSERT INTO commodities(name,parent_id,code,enabled) VALUES(?,?,?,1)', (name, sid, code)).lastrowid)
        sectors[sector] = ids
    names = [name for items in COMMODITY_TREE.values() for name, _ in items]
    for cat in list(c.execute("SELECT * FROM categories WHERE config IS NOT NULL AND config<>''")):
        cfg = json.loads(cat['config'])
        daily = '日度策略' in (cat['name'] or '') or str(cfg.get('title_pattern', '')).startswith('兴业期货日度策略')
        if not daily:
            continue
        for sec in cfg.get('sections', []):
            if sec.get('title') in sectors:
                sec['commodity_ids'] = list(sectors[sec['title']])
            else:
                sec['commodity_ids'] = []
        cfg['commodities'] = ['综合'] + names
        c.execute('UPDATE categories SET config=?,revision=revision+1 WHERE id=?', (e.dump(cfg), cat['id']))
        c.execute('INSERT INTO config_events(category_id,actor,config,revision,at) VALUES(?,?,?,?,?)',
                  (cat['id'], '系统升级', e.dump({'name': cat['name'], 'config': cfg, 'enabled': True}), cat['revision'] + 1,
                   datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' UTC'))
    c.execute('INSERT INTO schema_flags VALUES(?)', ('commodity-tree-v1',))


def tree(c):
    rows=[dict(r) for r in c.execute('SELECT id,name,label,parent_id,sort_order,folder,enabled FROM categories ORDER BY sort_order,id')];index={r['id']:r for r in rows}
    for r in rows:
        seen=set();p=r;level=0;enabled=True
        while p:
            if p['id'] in seen:raise ValueError('分类存在循环引用')
            seen.add(p['id']);level+=1;enabled=enabled and bool(p['enabled']);p=index.get(p['parent_id'])
        r['depth']=level;r['effective_enabled']=enabled
    return rows

def catalogs(c):
    return {'category_tree':tree(c),'authors':[dict(r) for r in c.execute('SELECT * FROM authors ORDER BY id')],'commodities':[dict(r) for r in c.execute('SELECT * FROM commodities ORDER BY id')],'members':[dict(r) for r in c.execute('SELECT id,name,role FROM users ORDER BY id')]}

def meta(r):return json.loads(r['metadata']) if r['metadata'] else None
def editable(r):return r['status'] in ['草稿','已退回']
def participant(r,u):
    m=meta(r)
    return r['author']==u['id'] or bool(m and u['id'] in m['collaborators'])

def can_view(c,r,u):
    if 'deleted' in r.keys() and r['deleted']:return False
    if u['role']=='admin' or participant(r,u):return True
    m=meta(r)
    if r['status']=='已发布' and (not m or m['public']):return True
    if r['status']=='已撤销':return False
    if not m:
        return bool(r['document'] and e.eligibility(c,r,u)) or (not r['document'] and r['status'] in ['研究复核','合规审核','待发布'] and u['role'] in ['reviewer','compliance','publisher'])
    cfg=json.loads(r['config_snapshot'])
    if any(u['id'] in n['users'] for n in cfg['workflow']):return True
    if c.execute("SELECT 1 FROM events WHERE report_id=? AND actor=? AND action IN ('通过','退回','发布')",(r['id'],u['name'])).fetchone():return True
    return bool(e.eligibility(c,r,u)) if r['status'] not in ['草稿','已退回','已发布'] else False

def section_allowed(r,u,s):
    return editable(r) and s.get('state','未提交')!='已提交' and (u['id'] in s.get('editors',[]) if meta(r)['collaboration']=='shared' else r['author']==u['id'])

def chapter_clean(c,r,doc,section,blocks,refresh=False):
    cfg=json.loads(r['config_snapshot']);cfg['sections']=[{'id':section['id'],'title':section['title'],'required':section['required'],'group':section.get('group',''),'label':section.get('label','')}]
    test={'layout':doc['layout'],'sections':[{'id':section['id'],'blocks':blocks}]}
    return e.validate_document(c,test,cfg,{'sections':[section]},refresh)['sections'][0]['blocks']

def save_doc(c,r,u,doc,stamp,snapshot,event,action,note='',metadata=None,title=None):
    md=metadata or meta(r);cfg=json.loads(r['config_snapshot'])
    c.execute('UPDATE reports SET document=?,body=?,metadata=?,title=?,version=version+1,updated=? WHERE id=?',(e.dump(doc),e.plain(doc,cfg),e.dump(md),title if title is not None else r['title'],stamp(),r['id']))
    r=c.execute('SELECT * FROM reports WHERE id=?',(r['id'],)).fetchone();snapshot(c,r,u);event(c,r,u,action,note)
    return {'ok':True,'version':r['version']},200

def handle(c,path,d,u,stamp,snapshot,event,checks):
    if path=='/api/reports' and d.get('inherit_id'):
        source=c.execute('SELECT * FROM reports WHERE id=?',(int(d['inherit_id']),)).fetchone()
        if not source or not can_view(c,source,u):return {'error':'无权继承此报告'},403
    if path in ['/api/catalog','/api/category-tree']:
        if u['role']!='admin':return {'error':'仅管理员可管理基础资料'},403
        c.execute('BEGIN IMMEDIATE')
        if path=='/api/catalog':
            kind=d['kind'];name=e.text(d['name'],80).strip();enabled=int(bool(d.get('enabled',True)));rid=int(d['id']) if d.get('id') else None
            if not name or kind not in ['authors','commodities']:raise ValueError('资料类型或名称无效')
            if kind=='authors':
                types=d.get('types',['日报','周报','专题','调研纪要'])
                if not isinstance(types,list) or not types:raise ValueError('请选择适用报告类型')
                types=[e.text(x,30) for x in types]
                lic=e.text(d.get('license',''),40).strip()
                if rid:c.execute('UPDATE authors SET name=?,types=?,enabled=?,license=? WHERE id=?',(name,e.dump(types),enabled,lic,rid))
                else:rid=c.execute('INSERT INTO authors(name,types,enabled,license) VALUES(?,?,?,?)',(name,e.dump(types),enabled,lic)).lastrowid
            else:
                parent=int(d['parent_id']) if d.get('parent_id') else None
                if parent:
                    p=c.execute('SELECT * FROM commodities WHERE id=?',(parent,)).fetchone()
                    if not p or p['parent_id'] or parent==rid:raise ValueError('品种仅支持两级分类')
                    if rid and c.execute('SELECT 1 FROM commodities WHERE parent_id=?',(rid,)).fetchone():raise ValueError('有子品种的分类不能移为二级')
                code=e.text(d.get('code',''),40).strip().upper()
                if code and not re.fullmatch(r'[A-Z0-9/,\-]{1,40}',code):raise ValueError('合约代码只能用字母、数字与斜杠')
                if rid:c.execute('UPDATE commodities SET name=?,parent_id=?,code=?,enabled=? WHERE id=?',(name,parent,code,enabled,rid))
                else:rid=c.execute('INSERT INTO commodities(name,parent_id,code,enabled) VALUES(?,?,?,?)',(name,parent,code,enabled)).lastrowid
            return {'id':rid},200
        label=e.text(d['label'],80).strip();parent=int(d['parent_id']) if d.get('parent_id') else None;rid=int(d['id']) if d.get('id') else None;nodes={n['id']:n for n in tree(c)}
        if not label or '/' in label:raise ValueError('名称必填；层级通过上级分类设置')
        if rid and rid not in nodes:raise ValueError('分类不存在')
        if parent and parent not in nodes:raise ValueError('上级分类不存在')
        descendants=set();pending=[rid] if rid else []
        while pending:
            p=pending.pop();descendants.add(p);pending.extend(n['id'] for n in nodes.values() if n['parent_id']==p)
        if parent in descendants:raise ValueError('不能移动到自身或子分类下')
        level=nodes[parent]['depth']+1 if parent else 1;height=max((nodes[x]['depth']-nodes[rid]['depth'] for x in descendants),default=0)
        if level+height>3:raise ValueError('研报分类最多三级')
        if parent and not nodes[parent]['folder']:
            if c.execute('SELECT 1 FROM reports WHERE category_id=?',(parent,)).fetchone():raise ValueError('已有报告的末级分类不能直接变成父分类')
            c.execute('UPDATE categories SET folder=1 WHERE id=?',(parent,))
        if rid:c.execute('UPDATE categories SET label=?,parent_id=?,sort_order=?,enabled=? WHERE id=?',(label,parent,int(d.get('sort_order',0)),int(bool(d.get('enabled',True))),rid))
        else:
            cfg=c.execute('SELECT config FROM categories ORDER BY folder,id LIMIT 1').fetchone()['config']
            rid=c.execute('INSERT INTO categories(name,label,parent_id,sort_order,enabled,folder,config) VALUES(?,?,?,?,?,?,?)',('__new__'+e.uid(),label,parent,int(d.get('sort_order',0)),int(bool(d.get('enabled',True))),int(bool(d.get('folder',False))),cfg)).lastrowid
        # Build all paths before updating to avoid collisions on parent renames.
        nodes={r['id']:dict(r) for r in c.execute('SELECT * FROM categories')}
        def full(n):return full(nodes[n['parent_id']])+' / '+n['label'] if n['parent_id'] else n['label']
        paths={i:full(n) for i,n in nodes.items()}
        if len(set(paths.values()))!=len(paths):raise ValueError('同一上级下已有同名分类')
        for i in nodes:c.execute('UPDATE categories SET name=? WHERE id=?',('__move__'+str(i),i))
        for i,name in paths.items():c.execute('UPDATE categories SET name=? WHERE id=?',(name,i))
        c.execute('INSERT INTO config_events(category_id,actor,config,revision,at) VALUES(?,?,?,?,?)',(rid,u['name'],e.dump({'tree_change':d}),nodes[rid]['revision'],stamp()))
        return {'id':rid},200
    if path=='/api/categories':
        if u['role']!='admin':return {'error':'仅管理员可配置分类'},403
        if d.get('id'):
            cat=c.execute('SELECT * FROM categories WHERE id=?',(int(d['id']),)).fetchone()
            if cat and cat['folder']:return {'error':'请在末级分类配置研报结构'},400
            if cat and d['name']!=cat['name']:return {'error':'分类名称及层级请在分类树中调整'},400
        else:
            parts=[x.strip() for x in d['name'].split('/') if x.strip()]
            if not 1<=len(parts)<=3:raise ValueError('分类最多三级')
            result=e.handle(c,path,d,u,stamp,snapshot,event,checks)
            if result[1]!=200:return result
            rid=result[0]['id'];parent=None;prefix=[]
            for label in parts[:-1]:
                prefix.append(label);name=' / '.join(prefix);row=c.execute('SELECT * FROM categories WHERE name=?',(name,)).fetchone()
                if row:
                    if not row['folder']:raise ValueError('上级是现有末级分类，请通过分类树调整')
                    parent=row['id']
                else:parent=c.execute('INSERT INTO categories(name,label,parent_id,folder,config) VALUES(?,?,?,1,?)',(name,label,parent,e.dump(d['config']))).lastrowid
            c.execute('UPDATE categories SET label=?,parent_id=? WHERE id=?',(parts[-1],parent,rid))
            return result
        return None
    if path=='/api/reports' and d.get('manual'):
        if u['role'] not in ['admin','researcher']:return {'error':'无创建权限'},403
        nodes={x['id']:x for x in tree(c)};node=nodes.get(int(d['category_id']))
        if not node or node['folder'] or not node['effective_enabled']:return {'error':'请选择已启用的末级分类'},400
        by=c.execute('SELECT * FROM authors WHERE id=? AND enabled=1',(int(d['byline_id']),)).fetchone()
        cat=c.execute('SELECT * FROM categories WHERE id=?',(node['id'],)).fetchone();cfg=json.loads(cat['config'])
        if not by or cfg['kind'] not in json.loads(by['types']):raise ValueError('署名作者未启用或不适用于该报告类型')
        commodity=c.execute('SELECT * FROM commodities WHERE name=? AND enabled=1',(d['commodity'],)).fetchone()
        if not commodity:raise ValueError('研究品种未启用')
        if commodity['parent_id'] and not c.execute('SELECT 1 FROM commodities WHERE id=? AND enabled=1',(commodity['parent_id'],)).fetchone():raise ValueError('品种父级已停用')
        collaboration=d.get('collaboration','personal');collaborators=list(dict.fromkeys(int(x) for x in d.get('collaborators',[])))
        if collaboration not in ['personal','shared']:raise ValueError('协作方式无效')
        collaborators=[x for x in collaborators if x!=u['id']]
        if collaboration=='shared' and not collaborators:raise ValueError('多人报告需要至少一名协作人')
        if collaboration=='personal':collaborators=[]
        for person in collaborators:
            row=c.execute('SELECT role FROM users WHERE id=?',(person,)).fetchone()
            if not row or row['role'] not in ['researcher','admin']:raise ValueError('协作人必须为研究员或管理员')
        date=e.text(d.get('report_date',''),10);datetime.date.fromisoformat(date)
        layout=d.get('layout',cfg['layout'])
        if layout not in ['flow','grid','free']:raise ValueError('布局无效')
        inherited=d.get('inherit_id')
        if inherited:
            source=c.execute('SELECT * FROM reports WHERE id=?',(int(inherited),)).fetchone()
            if not source or not can_view(c,source,u):return {'error':'无权继承此报告'},403
        result=e.handle(c,path,d,u,stamp,snapshot,event,checks)
        if result[1]!=200:return result
        rid=result[0]['id'];r=c.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone();cfg=json.loads(r['config_snapshot']);doc=json.loads(r['document']);cfg['layout']=layout;doc['layout']=layout
        for section in doc['sections']:
            template=next((s for s in cfg['sections'] if s['id']==section['id']),{})
            # 日度策略各章节按合集对应到板块品种；其他分类未配置时退回本报告的品种
            linked=template.get('commodity_ids')
            if linked is None or (not linked and '日度策略' not in (cat['name'] or '')):linked=[commodity['id']]
            section.update(editors=[u['id']],tags=[],type=template.get('type',''),group=template.get('group',''),label=template.get('label',''),commodity_ids=linked,state='未提交',revision=1)
        if layout=='free':
            index=0
            for section in doc['sections']:
                for block in section['blocks']:
                    for key,val in {'x':30,'y':70+index*230,'width':620,'height':210}.items():block.setdefault(key,val)
                    index+=1
        md={'schema':1,'summary':e.text(d.get('summary',''),2000),'byline_id':by['id'],'byline':by['name'],'byline_license':by['license'] or '','report_date':date,'collaboration':collaboration,'collaborators':collaborators,'public':bool(d.get('public',True)),'layout':layout,'creation':'inherit' if inherited else 'new'}
        c.execute('UPDATE reports SET document=?,config_snapshot=?,metadata=? WHERE id=?',(e.dump(doc),e.dump(cfg),e.dump(md),rid))
        c.execute('UPDATE versions SET document=?,config_snapshot=?,metadata=? WHERE report_id=? AND version=1',(e.dump(doc),e.dump(cfg),e.dump(md),rid))
        return result
    if not d.get('id') or path not in ['/api/save','/api/refresh','/api/transition','/api/generate','/api/check','/api/convert','/api/chapter/save','/api/chapter/submit','/api/chapter/reopen','/api/chapters','/api/report-info','/api/personal-save']:return None
    r=c.execute('SELECT * FROM reports WHERE id=?',(int(d['id']),)).fetchone()
    if not r:return {'error':'报告不存在'},404
    if not can_view(c,r,u):return {'error':'无权访问此报告'},403
    m=meta(r)
    if not m:return None
    if path in ['/api/save','/api/refresh']:return {'error':'新版协作报告请按章节保存，不能覆盖整篇文档'},400
    if path=='/api/check':return None
    if path=='/api/transition':
        if d['action']=='提交' and m['collaboration']=='shared' and any(s.get('state')!='已提交' for s in json.loads(r['document'])['sections']):return {'error':'多人报告须全部章节提交后才能发起审批'},400
        return None
    doc=json.loads(r['document']);section=next((s for s in doc['sections'] if s['id']==d.get('section_id')),None)
    if path=='/api/generate':
        if not section or not section_allowed(r,u,section):return {'error':'当前账号不能生成此章节内容'},403
        return None
    c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM reports WHERE id=?',(r['id'],)).fetchone();doc=json.loads(r['document']);m=meta(r);section=next((s for s in doc['sections'] if s['id']==d.get('section_id')),None)
    if not editable(r):return {'error':'报告已送审或发布，不能修改'},403
    if path=='/api/personal-save':
        if m['collaboration']!='personal' or r['author']!=u['id']:return {'error':'仅个人报告创建人可保存整篇'},403
        if int(d['version'])!=r['version']:return {'error':'报告已更新，请刷新后合并'},409
        supplied={s['id']:s for s in d['document']['sections']}
        if set(supplied)!={s['id'] for s in doc['sections']}:raise ValueError('章节结构不一致')
        for s in doc['sections']:
            s['blocks']=chapter_clean(c,r,doc,s,supplied[s['id']]['blocks'],bool(d.get('refresh')));s['revision']+=1
        ids=[b['id'] for s in doc['sections'] for b in s['blocks']]
        if len(ids)!=len(set(ids)):raise ValueError('组件标识重复')
        return save_doc(c,r,u,doc,stamp,snapshot,event,'保存个人研报')
    if path=='/api/report-info':
        if r['author']!=u['id']:return {'error':'仅创建人可修改基础信息'},403
        if int(d['version'])!=r['version']:return {'error':'报告版本已更新，请刷新'},409
        title=e.text(d['title'],200).strip()
        if not title:raise ValueError('标题必填')
        m['summary']=e.text(d.get('summary',m['summary']),2000);m['public']=bool(d.get('public',m['public']))
        if 'byline_id' in d and int(d['byline_id'])!=m['byline_id']:
            by=c.execute('SELECT * FROM authors WHERE id=? AND enabled=1',(int(d['byline_id']),)).fetchone()
            if not by or r['kind'] not in json.loads(by['types']):raise ValueError('署名作者不可用或不适用于本报告类型')
            m.update(byline_id=by['id'],byline=by['name'],byline_license=by['license'] or '')
        if 'report_date' in d:
            date=e.text(d['report_date'],10);datetime.date.fromisoformat(date);m['report_date']=date
        return save_doc(c,r,u,doc,stamp,snapshot,event,'更新报告基础信息',metadata=m,title=title)
    if path=='/api/chapters':
        if r['author']!=u['id']:return {'error':'仅创建人可管理章节'},403
        if int(d['version'])!=r['version']:return {'error':'结构版本已更新，请刷新'},409
        action=d['action']
        if action=='add':
            if len(doc['sections'])>=30:raise ValueError('最多30章')
            doc['sections'].append({'id':e.uid(),'title':'新增章节','required':False,'blocks':[],'editors':[u['id']],'tags':[],'commodity_ids':[],'state':'编辑中','revision':1})
        else:
            if not section:raise ValueError('章节不存在')
            if section['state']=='已提交':return {'error':'请先撤销章节提交'},400
            i=doc['sections'].index(section)
            if action=='remove':
                if len(doc['sections'])==1:raise ValueError('至少保留一章')
                doc['sections'].pop(i)
            elif action in ['up','down']:
                j=i+(-1 if action=='up' else 1)
                if 0<=j<len(doc['sections']):doc['sections'][i],doc['sections'][j]=doc['sections'][j],doc['sections'][i]
            elif action=='edit':
                title=e.text(d['title'],100).strip();editors=list(dict.fromkeys(int(x) for x in d.get('editors',[])))
                if not title or not editors or not set(editors)<=set([r['author']]+m['collaborators']):raise ValueError('标题必填，编辑人必须为创建人或协作人')
                tags=d.get('tags',[]);commodity_ids=list(dict.fromkeys(int(x) for x in d.get('commodity_ids',[])))
                if not isinstance(tags,list) or len(tags)>20:raise ValueError('标签格式无效')
                for cid in commodity_ids:
                    if not c.execute('SELECT 1 FROM commodities WHERE id=? AND enabled=1',(cid,)).fetchone():raise ValueError('关联品种不存在或已停用')
                section.update(title=title,editors=editors,tags=[e.text(x,30) for x in tags],commodity_ids=commodity_ids,revision=section['revision']+1)
            else:raise ValueError('不支持的章节操作')
        return save_doc(c,r,u,doc,stamp,snapshot,event,'管理报告章节',action)
    if not section:raise ValueError('章节不存在')
    if int(d['revision'])!=section['revision']:return {'error':'此章节已有新版本，请刷新后合并修改'},409
    if path=='/api/chapter/reopen':
        if section['state']!='已提交' or (u['id'] not in section['editors'] and r['author']!=u['id']):return {'error':'无权撤销此章节提交'},403
        section['state']='未提交';section['revision']+=1
        return save_doc(c,r,u,doc,stamp,snapshot,event,'撤销章节提交',section['title'])
    if not section_allowed(r,u,section):return {'error':'无权编辑此章节，或章节已提交锁定'},403
    if path=='/api/chapter/save':
        blocks=chapter_clean(c,r,doc,section,d['blocks'],bool(d.get('refresh',False)))
        other_ids={b['id'] for s in doc['sections'] if s['id']!=section['id'] for b in s['blocks']}
        if any(b['id'] in other_ids for b in blocks):raise ValueError('组件标识与其他章节重复')
        section['blocks']=blocks;section['revision']+=1
        if section['state']=='编辑中':section['state']='未提交'
        return save_doc(c,r,u,doc,stamp,snapshot,event,'刷新章节数据' if d.get('refresh') else '保存章节',section['title'])
    if path=='/api/chapter/submit':
        if not any(b.get('text','').strip() or b.get('data') for b in section['blocks']):return {'error':'空章节不能提交'},400
        section['state']='已提交';section['revision']+=1
        return save_doc(c,r,u,doc,stamp,snapshot,event,'提交章节',section['title'])
    return {'error':'不支持的操作'},400
