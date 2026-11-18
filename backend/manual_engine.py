"""Manual-aligned business objects and chapter collaboration. No browser-only authorization.

数据访问一律走 ORM：``s`` 是 SQLAlchemy Session，查询用 select()，写入用对象赋值。
"""
import json,re,datetime
from sqlalchemy import select
import db
import report_engine as e
from db import Author, Category, CategoryMigration, Commodity, ConfigEvent, Event, Report, User, Version

def add_columns(s,table,columns):
    db.add_columns(s,table,columns)

def migrate(s):
    db.create_schema()
    add_columns(s,'categories',{'parent_id':'INTEGER','label':"TEXT DEFAULT ''",'sort_order':'INTEGER DEFAULT 0','folder':'INTEGER DEFAULT 0'})
    add_columns(s,'reports',{'metadata':"TEXT DEFAULT ''"})
    add_columns(s,'versions',{'metadata':"TEXT DEFAULT ''"})
    add_columns(s,'authors',{'license':"TEXT DEFAULT ''"})
    if not db.has_flag(s,'manual-v1'):
        for cat in s.execute(select(Category).order_by(Category.id)).scalars().all():
            original=cat.name
            parts=[x.strip() for x in cat.name.split('/') if x.strip()] or [cat.name]
            if len(parts)>3:parts=parts[:2]+['／'.join(parts[2:])]
            parent=None;path=[]
            for label in parts[:-1]:
                path.append(label);name=' / '.join(path)
                row=s.execute(select(Category).where(Category.name==name)).scalars().first()
                if row:
                    parent=row.id;row.folder=1
                else:
                    folder=Category(name=name,config=cat.config,parent_id=parent,label=label,folder=1)
                    s.add(folder);s.flush();parent=folder.id
            cat.parent_id=parent;cat.label=parts[-1]
            if not s.get(CategoryMigration,cat.id):
                s.add(CategoryMigration(category_id=cat.id,original_name=original,parent_id=parent))
        s.flush()
        names=set()
        for (config,) in s.execute(select(Category.config)):
            names.update(json.loads(config).get('commodities',[]))
        for name in sorted(names):
            if not s.execute(select(Commodity.id).where(Commodity.name==name).limit(1)).first():
                s.add(Commodity(name=name))
        if not s.execute(select(Author.id).where(Author.name=='研究中心').limit(1)).first():
            s.add(Author(name='研究中心',types=e.dump(['日报','周报','专题','调研纪要'])))
        db.set_flag(s,'manual-v1')
    seed_commodity_tree(s)

# 《兴业期货日度策略》覆盖的期货品种：板块 →（品种, 合约代码），与合集「三、金融与商品基本面展望」下的 01～06 一一对应。
COMMODITY_TREE = {
    '金融衍生品': [('股指', 'IF/IH/IC/IM'), ('国债', 'T/TF/TS/TL')],
    '贵金属': [('黄金', 'AU'), ('白银', 'AG')],
    '有色与新能源': [('铜', 'CU'), ('铝', 'AL'), ('氧化铝', 'AO'), ('镍', 'NI'), ('工业硅', 'SI'), ('多晶硅', 'PS')],
    '黑色建材': [('螺纹钢', 'RB'), ('热卷', 'HC'), ('铁矿石', 'I'), ('焦煤', 'JM'), ('焦炭', 'J'), ('纯碱', 'SA'), ('玻璃', 'FG')],
    '能源化工': [('原油', 'SC'), ('甲醇', 'MA'), ('PVC', 'V')],
    '农产品': [('棕榈油', 'P'), ('豆油', 'Y'), ('菜籽油', 'OI'), ('豆粕', 'M'), ('棉花', 'CF'), ('白糖', 'SR')],
}


def _commodity(s,name):
    return s.execute(select(Commodity).where(Commodity.name==name)).scalars().first()


def seed_commodity_tree(s):
    """把品种库补成「板块 → 期货品种（含合约代码）」，并把日度策略各章节的关联品种对上。幂等。"""
    add_columns(s,'commodities',{'code':"TEXT DEFAULT ''"})
    if db.has_flag(s,'commodity-tree-v1'):
        return
    sectors = {}
    for sector, items in COMMODITY_TREE.items():
        row = _commodity(s,sector)
        if row:
            row.parent_id=None;row.enabled=1
            sid = row.id
        else:
            node=Commodity(name=sector,parent_id=None,enabled=1)
            s.add(node);s.flush();sid = node.id
        ids = []
        for name, code in items:
            row = _commodity(s,name)
            if row:
                row.parent_id=sid;row.code=code;row.enabled=1
                ids.append(row.id)
            else:
                node=Commodity(name=name,parent_id=sid,code=code,enabled=1)
                s.add(node);s.flush();ids.append(node.id)
        sectors[sector] = ids
    names = [name for items in COMMODITY_TREE.values() for name, _ in items]
    for cat,cfg in e._daily_categories(s):
        for section in cfg.get('sections', []):
            section['commodity_ids'] = list(sectors[section['title']]) if section.get('title') in sectors else []
        cfg['commodities'] = ['综合'] + names
        cat.config=e.dump(cfg);cat.revision=(cat.revision or 1)+1
        s.add(ConfigEvent(category_id=cat.id,actor='系统升级',config=e.dump({'name':cat.name,'config':cfg,'enabled':True}),revision=cat.revision,at=e.now_utc()))
    db.set_flag(s,'commodity-tree-v1')


def tree(s):
    rows=[dict(r._mapping) for r in s.execute(select(Category.id,Category.name,Category.label,Category.parent_id,Category.sort_order,Category.folder,Category.enabled).order_by(Category.sort_order,Category.id))]
    index={r['id']:r for r in rows}
    for r in rows:
        seen=set();p=r;level=0;enabled=True
        while p:
            if p['id'] in seen:raise ValueError('分类存在循环引用')
            seen.add(p['id']);level+=1;enabled=enabled and bool(p['enabled']);p=index.get(p['parent_id'])
        r['depth']=level;r['effective_enabled']=enabled
    return rows

def catalogs(s):
    return {'category_tree':tree(s),'authors':[x.to_dict() for x in s.execute(select(Author).order_by(Author.id)).scalars()],'commodities':[x.to_dict() for x in s.execute(select(Commodity).order_by(Commodity.id)).scalars()],'members':[dict(r._mapping) for r in s.execute(select(User.id,User.name,User.role,User.enabled).order_by(User.id))]}

def meta(r):return json.loads(r['metadata']) if r['metadata'] else None
def editable(r):return r['status'] in ['草稿','已退回']
def participant(r,u):
    m=meta(r)
    return r['author']==u['id'] or bool(m and u['id'] in m['collaborators'])

def can_view(s,r,u):
    if 'deleted' in r.keys() and r['deleted']:return False
    if u['role']=='admin' or participant(r,u):return True
    m=meta(r)
    if r['status']=='已发布' and (not m or m['public']):return True
    if r['status']=='已撤销':return False
    if not m:
        return bool(r['document'] and e.eligibility(s,r,u)) or (not r['document'] and r['status'] in ['研究复核','合规审核','待发布'] and u['role'] in ['reviewer','compliance','publisher'])
    cfg=json.loads(r['config_snapshot'])
    if any(u['id'] in n['users'] for n in cfg['workflow']):return True
    if s.execute(select(Event.id).where(Event.report_id==r['id'],Event.actor==u['name'],Event.action.in_(['通过','退回','发布'])).limit(1)).first():return True
    return bool(e.eligibility(s,r,u)) if r['status'] not in ['草稿','已退回','已发布'] else False

def section_allowed(r,u,section):
    return editable(r) and section.get('state','未提交')!='已提交' and (u['id'] in section.get('editors',[]) if meta(r)['collaboration']=='shared' else r['author']==u['id'])

def chapter_clean(s,r,doc,section,blocks,refresh=False):
    cfg=json.loads(r['config_snapshot']);cfg['sections']=[{'id':section['id'],'title':section['title'],'required':section['required'],'group':section.get('group',''),'label':section.get('label','')}]
    test={'layout':doc['layout'],'sections':[{'id':section['id'],'blocks':blocks}]}
    return e.validate_document(s,test,cfg,{'sections':[section]},refresh)['sections'][0]['blocks']

def align_section_config(config, doc):
    """Keep current-report chapter definitions aligned with its editable document."""
    previous={item['id']:item for item in config.get('sections',[])}
    fields={'title':'','group':'','label':'','type':'','required':False,'commodity_ids':[]}
    config['sections']=[{**previous.get(section['id'],{}),'id':section['id'],
        **{key:section.get(key,previous.get(section['id'],{}).get(key,default)) for key,default in fields.items()},
        'default':previous.get(section['id'],{}).get('default','')} for section in doc['sections']]


def renumber_chapters(doc):
    """Reorder ordinary numeric chapter labels within each group; custom labels stay intact."""
    groups={}
    for section in doc['sections']:groups.setdefault(section.get('group',''),[]).append(section)
    for sections in groups.values():
        labels=[str(section.get('label') or '').strip() for section in sections]
        numeric=[label for label in labels if re.fullmatch(r'[0-9]{1,3}',label)]
        if not numeric or any(label and not re.fullmatch(r'[0-9]{1,3}',label) for label in labels):continue
        width=max(len(label) for label in numeric)
        for index,section in enumerate(sections,1):
            label=str(index).zfill(width)
            if section.get('label')!=label:
                section['label']=label;section['revision']=section.get('revision',0)+1
                if section.get('state')=='已提交':section['state']='未提交'


def save_doc(s,r,u,doc,stamp,snapshot,event,action,note='',metadata=None,title=None):
    md=metadata or meta(r);cfg=json.loads(r['config_snapshot'])
    r.document=e.dump(doc);r.body=e.plain(doc,cfg);r.metadata_=e.dump(md)
    r.title=title if title is not None else r['title'];r.version=(r['version'] or 1)+1;r.updated=stamp()
    snapshot(s,r,u);event(s,r,u,action,note)
    return {'ok':True,'version':r.version},200

def handle(s,path,d,u,stamp,snapshot,event,checks):
    if path=='/api/reports' and d.get('inherit_id'):
        source=s.get(Report,int(d['inherit_id']))
        if not source or not can_view(s,source,u):return {'error':'无权继承此报告'},403
    if path in ['/api/catalog','/api/category-tree']:
        if u['role']!='admin':return {'error':'仅管理员可管理基础资料'},403
        if path=='/api/catalog':
            kind=d['kind'];name=e.text(d['name'],80).strip();enabled=int(bool(d.get('enabled',True)));rid=int(d['id']) if d.get('id') else None
            if not name or kind not in ['authors','commodities']:raise ValueError('资料类型或名称无效')
            if kind=='authors':
                types=d.get('types',['日报','周报','专题','调研纪要'])
                if not isinstance(types,list) or not types:raise ValueError('请选择适用报告类型')
                types=[e.text(x,30) for x in types]
                lic=e.text(d.get('license',''),40).strip()
                if rid:
                    row=s.get(Author,rid)
                    if not row:raise ValueError('作者不存在')
                    row.name=name;row.types=e.dump(types);row.enabled=enabled;row.license=lic
                else:
                    row=Author(name=name,types=e.dump(types),enabled=enabled,license=lic)
                    s.add(row);s.flush();rid=row.id
            else:
                parent=int(d['parent_id']) if d.get('parent_id') else None
                if parent:
                    p=s.get(Commodity,parent)
                    if not p or p.parent_id or parent==rid:raise ValueError('品种仅支持两级分类')
                    if rid and s.execute(select(Commodity.id).where(Commodity.parent_id==rid).limit(1)).first():raise ValueError('有子品种的分类不能移为二级')
                code=e.text(d.get('code',''),40).strip().upper()
                if code and not re.fullmatch(r'[A-Z0-9/,\-]{1,40}',code):raise ValueError('合约代码只能用字母、数字与斜杠')
                if rid:
                    row=s.get(Commodity,rid)
                    if not row:raise ValueError('品种不存在')
                    row.name=name;row.parent_id=parent;row.code=code;row.enabled=enabled
                else:
                    row=Commodity(name=name,parent_id=parent,code=code,enabled=enabled)
                    s.add(row);s.flush();rid=row.id
            return {'id':rid},200
        label=e.text(d['label'],80).strip();parent=int(d['parent_id']) if d.get('parent_id') else None;rid=int(d['id']) if d.get('id') else None;nodes={n['id']:n for n in tree(s)}
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
            if s.execute(select(Report.id).where(Report.category_id==parent).limit(1)).first():raise ValueError('已有报告的末级分类不能直接变成父分类')
            s.get(Category,parent).folder=1
        if rid:
            row=s.get(Category,rid)
            row.label=label;row.parent_id=parent;row.sort_order=int(d.get('sort_order',0));row.enabled=int(bool(d.get('enabled',True)))
        else:
            cfg=s.execute(select(Category.config).order_by(Category.folder,Category.id).limit(1)).scalar()
            row=Category(name='__new__'+e.uid(),label=label,parent_id=parent,sort_order=int(d.get('sort_order',0)),
                         enabled=int(bool(d.get('enabled',True))),folder=int(bool(d.get('folder',False))),config=cfg)
            s.add(row);s.flush();rid=row.id
        # Build all paths before updating to avoid collisions on parent renames.
        nodes={x.id:x for x in s.execute(select(Category)).scalars().all()}
        def full(n):return full(nodes[n.parent_id])+' / '+n.label if n.parent_id else n.label
        paths={i:full(n) for i,n in nodes.items()}
        if len(set(paths.values()))!=len(paths):raise ValueError('同一上级下已有同名分类')
        for n in nodes.values():n.name='__move__'+str(n.id)
        s.flush()
        for i,name in paths.items():nodes[i].name=name
        s.flush()
        s.add(ConfigEvent(category_id=rid,actor=u['name'],config=e.dump({'tree_change':d}),revision=nodes[rid].revision,at=stamp()))
        return {'id':rid},200
    if path=='/api/categories':
        if u['role']!='admin':return {'error':'仅管理员可配置分类'},403
        if d.get('id'):
            cat=s.get(Category,int(d['id']))
            if cat and cat.folder:return {'error':'请在末级分类配置研报结构'},400
            if cat and d['name']!=cat.name:return {'error':'分类名称及层级请在分类树中调整'},400
        else:
            parts=[x.strip() for x in d['name'].split('/') if x.strip()]
            if not 1<=len(parts)<=3:raise ValueError('分类最多三级')
            result=e.handle(s,path,d,u,stamp,snapshot,event,checks)
            if result[1]!=200:return result
            rid=result[0]['id'];parent=None;prefix=[]
            for label in parts[:-1]:
                prefix.append(label);name=' / '.join(prefix)
                row=s.execute(select(Category).where(Category.name==name)).scalars().first()
                if row:
                    if not row.folder:raise ValueError('上级是现有末级分类，请通过分类树调整')
                    parent=row.id
                else:
                    row=Category(name=name,label=label,parent_id=parent,folder=1,config=e.dump(d['config']))
                    s.add(row);s.flush();parent=row.id
            target=s.get(Category,rid);target.label=parts[-1];target.parent_id=parent
            return result
        return None
    if path=='/api/reports' and d.get('manual'):
        if u['role'] not in ['admin','researcher']:return {'error':'无创建权限'},403
        nodes={x['id']:x for x in tree(s)};node=nodes.get(int(d.get('category_id') or 0))
        if not node or node['folder'] or not node['effective_enabled']:return {'error':'请选择已启用的末级分类'},400
        by=s.get(Author,int(d.get('byline_id') or 0))
        if by and not by.enabled:by=None
        cat=s.get(Category,node['id']);cfg=json.loads(cat.config)
        if not by or cfg['kind'] not in json.loads(by.types):raise ValueError('署名作者未启用或不适用于该报告类型')
        commodity=s.execute(select(Commodity).where(Commodity.name==d.get('commodity',''),Commodity.enabled==1)).scalars().first()
        if not commodity:raise ValueError('研究品种未启用')
        if commodity.parent_id:
            parent=s.get(Commodity,commodity.parent_id)
            if not parent or not parent.enabled:raise ValueError('品种父级已停用')
        collaboration=d.get('collaboration','personal');collaborators=list(dict.fromkeys(int(x) for x in d.get('collaborators',[])))
        if collaboration not in ['personal','shared']:raise ValueError('协作方式无效')
        collaborators=[x for x in collaborators if x!=u['id']]
        if collaboration=='shared' and not collaborators:raise ValueError('多人报告需要至少一名协作人')
        if collaboration=='personal':collaborators=[]
        for person in collaborators:
            row=s.get(User,person)
            if not row or not row.enabled or row.role not in ['researcher','admin']:raise ValueError('协作人必须为已启用的研究员或管理员')
        date=e.text(d.get('report_date',''),10);datetime.date.fromisoformat(date)
        layout=d.get('layout',cfg['layout'])
        if layout not in ['flow','grid','free']:raise ValueError('布局无效')
        inherited=d.get('inherit_id')
        if inherited:
            source=s.get(Report,int(inherited))
            if not source or not can_view(s,source,u):return {'error':'无权继承此报告'},403
        result=e.handle(s,path,d,u,stamp,snapshot,event,checks)
        if result[1]!=200:return result
        rid=result[0]['id'];r=s.get(Report,rid);cfg=json.loads(r.config_snapshot);doc=json.loads(r.document);cfg['layout']=layout;doc['layout']=layout
        for section in doc['sections']:
            template=next((x for x in cfg['sections'] if x['id']==section['id']),{})
            # 日度策略各章节按合集对应到板块品种；其他分类未配置时退回本报告的品种
            linked=template.get('commodity_ids')
            if linked is None or (not linked and '日度策略' not in (cat.name or '')):linked=[commodity.id]
            section.update(editors=[u['id']],tags=[],type=template.get('type',''),group=template.get('group',''),label=template.get('label',''),commodity_ids=linked,state='未提交',revision=1)
        if layout=='free':
            index=0
            for section in doc['sections']:
                for block in section['blocks']:
                    for key,val in {'x':30,'y':70+index*230,'width':620,'height':210}.items():block.setdefault(key,val)
                    index+=1
        md={'schema':1,'summary':e.text(d.get('summary',''),2000),'byline_id':by.id,'byline':by.name,'byline_license':by.license or '','report_date':date,'collaboration':collaboration,'collaborators':collaborators,'public':bool(d.get('public',True)),'layout':layout,'creation':'inherit' if inherited else 'new','template_section_ids':[section['id'] for section in cfg['sections']]}
        r.document=e.dump(doc);r.config_snapshot=e.dump(cfg);r.metadata_=e.dump(md)
        first=s.execute(select(Version).where(Version.report_id==rid,Version.version==1)).scalars().first()
        if first:
            first.document=e.dump(doc);first.config_snapshot=e.dump(cfg);first.metadata_=e.dump(md)
        return result
    if not d.get('id') or path not in ['/api/save','/api/refresh','/api/transition','/api/generate','/api/check','/api/convert','/api/chapter/save','/api/chapter/submit','/api/chapter/reopen','/api/chapters','/api/report-info','/api/personal-save']:return None
    r=s.get(Report,int(d['id']))
    if not r:return {'error':'报告不存在'},404
    if not can_view(s,r,u):return {'error':'无权访问此报告'},403
    m=meta(r)
    if not m:return None
    if path in ['/api/save','/api/refresh']:return {'error':'新版协作报告请按章节保存，不能覆盖整篇文档'},400
    if path=='/api/check':return None
    if path=='/api/transition':
        if d['action']=='提交' and m['collaboration']=='shared' and any(x.get('state')!='已提交' for x in json.loads(r.document)['sections']):return {'error':'多人报告须全部章节提交后才能发起审批'},400
        return None
    doc=json.loads(r.document);section=next((x for x in doc['sections'] if x['id']==d.get('section_id')),None)
    if path=='/api/generate':
        if not section or not section_allowed(r,u,section):return {'error':'当前账号不能生成此章节内容'},403
        return None
    s.flush();doc=json.loads(r.document);m=meta(r);section=next((x for x in doc['sections'] if x['id']==d.get('section_id')),None)
    if not editable(r):return {'error':'报告已送审或发布，不能修改'},403
    if path=='/api/personal-save':
        if m['collaboration']!='personal' or r['author']!=u['id']:return {'error':'仅个人报告创建人可保存整篇'},403
        if int(d['version'])!=r['version']:return {'error':'报告已更新，请刷新后合并'},409
        supplied={x['id']:x for x in d['document']['sections']}
        if set(supplied)!={x['id'] for x in doc['sections']}:raise ValueError('章节结构不一致')
        for sec in doc['sections']:
            sec['blocks']=chapter_clean(s,r,doc,sec,supplied[sec['id']]['blocks'],bool(d.get('refresh')));sec['revision']+=1
        ids=[b['id'] for x in doc['sections'] for b in x['blocks']]
        if len(ids)!=len(set(ids)):raise ValueError('组件标识重复')
        return save_doc(s,r,u,doc,stamp,snapshot,event,'保存个人研报')
    if path=='/api/report-info':
        if r['author']!=u['id']:return {'error':'仅创建人可修改基础信息'},403
        if int(d['version'])!=r['version']:return {'error':'报告版本已更新，请刷新'},409
        title=e.text(d['title'],200).strip()
        if not title:raise ValueError('标题必填')
        m['summary']=e.text(d.get('summary',m['summary']),2000);m['public']=bool(d.get('public',m['public']))
        if 'byline_id' in d and int(d['byline_id'])!=m['byline_id']:
            by=s.get(Author,int(d['byline_id']))
            if by and not by.enabled:by=None
            if not by or r['kind'] not in json.loads(by.types):raise ValueError('署名作者不可用或不适用于本报告类型')
            m.update(byline_id=by.id,byline=by.name,byline_license=by.license or '')
        if 'report_date' in d:
            date=e.text(d['report_date'],10);datetime.date.fromisoformat(date);m['report_date']=date
        return save_doc(s,r,u,doc,stamp,snapshot,event,'更新报告基础信息',metadata=m,title=title)
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
                title=e.text(d.get('title') or '',100).strip();editors=list(dict.fromkeys(int(x) for x in d.get('editors',[])))
                # 章节名称允许留空（版面只显示编号），仅校验编辑人
                if not editors or not set(editors)<=set([r['author']]+m['collaborators']):raise ValueError('编辑人必须为创建人或协作人')
                tags=d.get('tags',[]);commodity_ids=list(dict.fromkeys(int(x) for x in d.get('commodity_ids',[])))
                if not isinstance(tags,list) or len(tags)>20:raise ValueError('标签格式无效')
                for cid in commodity_ids:
                    item=s.get(Commodity,cid)
                    if not item or not item.enabled:raise ValueError('关联品种不存在或已停用')
                section.update(title=title,editors=editors,tags=[e.text(x,30) for x in tags],commodity_ids=commodity_ids,revision=section['revision']+1)
                for key,limit in [('group',60),('label',20),('type',80)]:
                    if key in d:section[key]=e.text(d[key],limit).strip()
                if 'required' in d:
                    if type(d['required']) is not bool:raise ValueError('必填设置无效')
                    section['required']=d['required']
            else:raise ValueError('不支持的章节操作')
        cfg=json.loads(r.config_snapshot)
        if action in ['add','remove','up','down']:renumber_chapters(doc)
        align_section_config(cfg,doc)
        if action=='edit' and 'default' in d:
            next(item for item in cfg['sections'] if item['id']==section['id'])['default']=e.text(d['default'],50000)
        r.config_snapshot=e.dump(cfg)
        return save_doc(s,r,u,doc,stamp,snapshot,event,'管理报告章节',action)
    if not section:raise ValueError('章节不存在')
    if int(d['revision'])!=section['revision']:return {'error':'此章节已有新版本，请刷新后合并修改'},409
    # 章节名称允许为空，审计备注退回编号，避免事件里只有空白
    sname=section['title'] or section.get('label','')
    if path=='/api/chapter/reopen':
        if section['state']!='已提交' or (u['id'] not in section['editors'] and r['author']!=u['id']):return {'error':'无权撤销此章节提交'},403
        section['state']='未提交';section['revision']+=1
        return save_doc(s,r,u,doc,stamp,snapshot,event,'撤销章节提交',sname)
    if not section_allowed(r,u,section):return {'error':'无权编辑此章节，或章节已提交锁定'},403
    if path=='/api/chapter/save':
        blocks=chapter_clean(s,r,doc,section,d['blocks'],bool(d.get('refresh',False)))
        other_ids={b['id'] for x in doc['sections'] if x['id']!=section['id'] for b in x['blocks']}
        if any(b['id'] in other_ids for b in blocks):raise ValueError('组件标识与其他章节重复')
        section['blocks']=blocks;section['revision']+=1
        if section['state']=='编辑中':section['state']='未提交'
        return save_doc(s,r,u,doc,stamp,snapshot,event,'刷新章节数据' if d.get('refresh') else '保存章节',sname)
    if path=='/api/chapter/submit':
        if not any(b.get('text','').strip() or b.get('data') for b in section['blocks']):return {'error':'空章节不能提交'},400
        section['state']='已提交';section['revision']+=1
        return save_doc(s,r,u,doc,stamp,snapshot,event,'提交章节',sname)
    return {'error':'不支持的操作'},400
