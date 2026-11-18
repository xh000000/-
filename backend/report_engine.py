"""Configurable research documents. Snapshots deliberately detach reports from later config changes.

数据访问一律走 ORM：传进来的 ``s`` 是 SQLAlchemy Session，查询用 select()，
写入用对象赋值 / 构造器 + add()，不再拼 SQL 文本。
"""
import json, re, math, secrets, datetime
from sqlalchemy import func, select
import db
import richtext
from db import ApprovalFlow, Category, Commodity, ConfigEvent, LibraryItem, Observation, Report, User

def dump(value): return json.dumps(value,ensure_ascii=False)
def uid(): return secrets.token_hex(8)
def text(value,limit=20000):
    if not isinstance(value,str) or len(value)>limit: raise ValueError('文本格式或长度不合法')
    return value

def now_utc():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')+' UTC'

# 《兴业期货日度策略》章节骨架：一级章节（一、二、三、四）+ 二级板块（01…06）。
# group 表示所属一级章节，label 为渲染时显示的编号；一级章节自身 group 为空。
DAILY_SECTIONS=[
    {'group':'','label':'一、','title':'重点策略推荐','type':'策略','required':True,
     'default':'1. \n\n2. \n\n3. '},
    {'group':'二、宏观资讯速递','label':'01','title':'宏观要闻','type':'资讯','required':False,
     'default':'1. \n\n2. '},
    {'group':'二、宏观资讯速递','label':'02','title':'行业要闻','type':'资讯','required':False,
     'default':'1. \n\n2. '},
    {'group':'二、宏观资讯速递','label':'03','title':'财经日历','type':'资讯','required':False,
     'default':''},
    {'group':'三、金融与商品基本面展望','label':'01','title':'金融衍生品','type':'板块','required':False,
     'default':'▍股指：\n\n▍国债：'},
    {'group':'三、金融与商品基本面展望','label':'02','title':'贵金属','type':'板块','required':False,
     'default':'▍黄金/白银：'},
    {'group':'三、金融与商品基本面展望','label':'03','title':'有色与新能源','type':'板块','required':False,
     'default':'▍铜：\n\n▍铝：\n\n▍氧化铝：\n\n▍镍：\n\n▍硅能源：'},
    {'group':'三、金融与商品基本面展望','label':'04','title':'黑色建材','type':'板块','required':False,
     'default':'▍钢矿：\n\n▍焦煤/焦炭：\n\n▍纯碱/玻璃：'},
    {'group':'三、金融与商品基本面展望','label':'05','title':'能源化工','type':'板块','required':False,
     'default':'▍原油：\n\n▍甲醇：\n\n▍PVC：'},
    {'group':'三、金融与商品基本面展望','label':'06','title':'农产品','type':'板块','required':False,
     'default':'▍油脂：\n\n▍豆粕：\n\n▍棉花：\n\n▍白糖：'},
    {'group':'四、数据来源与免责声明','label':'01','title':'数据来源与风险提示','type':'声明','required':True,
     'default':'数据来源：Wind、iFinD、钢联、SMM、隆众、兴业期货投资咨询部\n风险提示：以上内容仅供参考，不作为操作依据，投资需谨慎。'},
]

DAILY_PROMISE=('本人具有中国期货业协会授予的期货交易咨询执业资格或相当的专业胜任能力，保证报告所采用的数据均来自合规渠道，'
    '分析逻辑基于作者的职业理解，本报告清晰准确地反映了作者的研究观点，力求独立、客观和公正，结论不受任何第三方的授意或影响。'
    '本人不曾因，不因，也将不会因本报告中的具体推荐意见或观点而直接或间接接收到任何形式的报酬。本报告也不涉及任何利益冲突问题。')

DAILY_FOOTER=('本文非期货交易咨询业务项下服务，其中的观点和信息仅作参考之用，不构成对任何人的投资建议。'
    '兴业期货不因任何订阅或接收本报告的行为而视其为兴业期货的客户。上述信息均来源于公开资料，兴业期货对这些信息的准确性和完整性不做任何保证，'
    '也不保证所包含的信息和建议不会发生任何变更，我们已力求内容的客观、公正，但文中的观点、结论和建议仅供参考，'
    '投资者据此做出的任何形式的任何投资决策与兴业期货和作者无关。上述内容版权仅为兴业期货所有，未经书面授权，任何机构和个人不得以任何形式翻版、复制发布。'
    '如引用、刊发，须注明出处为兴业期货，且不得进行有悖原意的引用、删节和修改。'
    '如本文涉及行业分析或上市公司相关内容，旨在对期货市场及其相关性进行比较论证，列举解释期货品种相关特性及潜在风险，'
    '不涉及对其行业或上市公司的相关推荐，不构成对任何主体进行或不进行某项行为的建议或意见，不得将本文的任何内容据以作为兴业期货所作的承诺或声明。'
    '在任何情况下，任何主体依据本报告所进行的任何作为或不作为，兴业期货不承担任何责任。市场有风险，投资需谨慎。')

def daily_sections():
    """每次新建报告都拿到独立的章节标识，避免分类之间互相串号。"""
    return [{'id':uid(),**s} for s in DAILY_SECTIONS]

def migrate(s):
    db.create_schema()
    db.add_columns(s,'reports',{'document':"TEXT DEFAULT ''",'config_snapshot':"TEXT DEFAULT ''",'category_id':'INTEGER','workflow_state':"TEXT DEFAULT ''",'inherited_from':'INTEGER'})
    db.add_columns(s,'versions',{'document':"TEXT DEFAULT ''",'config_snapshot':"TEXT DEFAULT ''"})
    if not s.execute(select(func.count()).select_from(Category)).scalar():
        presets=[
            ('商品研究 / 日度策略','日报',daily_sections(),'兴业期货日度策略（{日期点分}）','按《兴业期货日度策略》版式组织章节'),
            ('商品研究 / 品种周报','周报',[{'id':uid(),'title':t,'required':True,'default':''} for t in ['本周摘要','供应分析','需求与库存','下周展望','风险提示','数据来源']],'{品种}{类型}｜{日期}','可调整章节、版式、数据引用和审核节点'),
            ('专题研究 / 深度专题','专题',[{'id':uid(),'title':t,'required':True,'default':''} for t in ['研究摘要','研究背景','核心论证','研究结论','风险提示','数据来源']],'{品种}{类型}｜{日期}','可调整章节、版式、数据引用和审核节点'),
        ]
        for name,kind,sections,pattern,description in presets:
            daily=name.endswith('日度策略')
            cfg={'description':description,'kind':kind,'commodities':['综合','螺纹钢','铜','豆粕','原油'],'title_pattern':pattern,'layout':'flow','header':'请务必阅读正文之后的免责条款部分' if daily else '期货研究 · 研究中心','footer':DAILY_FOOTER if daily else '本报告仅供研究参考，不构成收益承诺。','promise':DAILY_PROMISE if daily else '','contact':'021-80220262' if daily else '','color':'#409EFF','font_size':15,'sections':sections,'workflow':[{'label':'研究复核','role':'reviewer','mode':'any','users':[]},{'label':'合规审核','role':'compliance','mode':'any','users':[]}]}
            s.add(Category(name=name,config=dump(cfg)))
    upgrade_daily_template(s)
    upgrade_daily_paper(s)

def _daily_categories(s):
    """所有日度策略分类：名称含「日度策略」或标题规则以「兴业期货日度策略」开头。"""
    out=[]
    for cat in s.execute(select(Category).where(Category.config.isnot(None),Category.config!='').order_by(Category.id)).scalars():
        cfg=json.loads(cat.config)
        if '日度策略' in (cat.name or '') or str(cfg.get('title_pattern','')).startswith('兴业期货日度策略'):
            out.append((cat,cfg))
    return out

def upgrade_daily_template(s):
    """把历史库里的「品种日报」升级为日度策略章节模板。幂等，且只影响后续新建报告。"""
    if db.has_flag(s,'daily-template-v1'):return
    row=s.execute(select(Category).where(Category.name=='商品研究 / 品种日报').order_by(Category.id).limit(1)).scalars().first()
    if row:
        cfg=json.loads(row.config)
        cfg.update(kind='日报',sections=daily_sections(),title_pattern='兴业期货日度策略（{日期点分}）',
            header='请务必阅读正文之后的免责条款部分',footer=DAILY_FOOTER,promise=DAILY_PROMISE,contact='021-80220262',color='#409EFF',
            description='按《兴业期货日度策略》版式组织章节：重点策略推荐、宏观资讯速递、金融与商品基本面展望、数据来源与免责声明')
        row.name='商品研究 / 日度策略';row.label='日度策略';row.config=dump(cfg);row.revision=(row.revision or 1)+1
        s.add(ConfigEvent(category_id=row.id,actor='系统升级',config=dump({'name':'商品研究 / 日度策略','config':cfg,'enabled':True}),revision=row.revision,at=now_utc()))
    db.set_flag(s,'daily-template-v1')

def upgrade_daily_paper(s):
    """拆分「作者承诺」与「免责声明」两段版尾：老配置的 footer 把两者混在一起，打印会重复。幂等。"""
    if db.has_flag(s,'daily-paper-v2'):return
    for cat,cfg in _daily_categories(s):
        if cfg.get('promise'):continue
        cfg['promise']=DAILY_PROMISE;cfg['footer']=DAILY_FOOTER
        cfg.setdefault('contact','021-80220262');cfg.setdefault('header','请务必阅读正文之后的免责条款部分')
        cat.config=dump(cfg);cat.revision=(cat.revision or 1)+1
        s.add(ConfigEvent(category_id=cat.id,actor='系统升级',config=dump({'name':cat.name,'config':cfg,'enabled':True}),revision=cat.revision,at=now_utc()))
    db.set_flag(s,'daily-paper-v2')

def categories(s):
    return [{**cat.to_dict(),'config':json.loads(cat.config)} for cat in s.execute(select(Category).order_by(Category.id)).scalars()]

def flow_nodes(s,category_id):
    """按分类（含上级）匹配「审批流配置」中启用的审批流；无匹配则返回 None，沿用分类自带流程。"""
    chain=[];cur=category_id
    while cur:
        chain.append(cur)
        node=s.get(Category,cur)
        cur=node.parent_id if node else None
    flows=s.execute(select(ApprovalFlow).where(ApprovalFlow.enabled==1).order_by(ApprovalFlow.id)).scalars().all()
    for cid in chain:
        for flow in flows:
            if cid in json.loads(flow.category_ids):return json.loads(flow.nodes)
    return None

def validate_config(s,d):
    name=text(d['name'],100).strip()
    if not name:raise ValueError('分类名称必填')
    cfg=d['config']
    if not isinstance(cfg,dict):raise ValueError('分类配置格式错误')
    out={k:text(cfg.get(k,''),1000) for k in ['description','header','footer']}
    out['contact']=text(cfg.get('contact',''),40).strip()
    out['promise']=text(cfg.get('promise',''),4000)
    out['kind']=text(cfg.get('kind','日报'),30).strip()
    out['title_pattern']=text(cfg.get('title_pattern','{品种}{类型}｜{日期}'),100)
    if not out['kind'] or not out['title_pattern']:raise ValueError('报告类型及标题规则必填')
    if cfg.get('layout') not in ['flow','grid','free']:raise ValueError('不支持的布局')
    out['layout']=cfg['layout'];out['color']=cfg.get('color','#127867')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',out['color']):raise ValueError('主题色格式错误')
    out['font_size']=int(cfg.get('font_size',15))
    if not 12<=out['font_size']<=24:raise ValueError('正文字号应为12至24')
    values=cfg.get('commodities',[])
    if not isinstance(values,list) or not 1<=len(values)<=100:raise ValueError('请配置1至100个品种')
    out['commodities']=list(dict.fromkeys(text(x,50).strip() for x in values if x.strip()))
    if not out['commodities']:raise ValueError('品种不能为空')
    sections=cfg.get('sections',[])
    if not isinstance(sections,list) or not 1<=len(sections)<=30:raise ValueError('请配置1至30个章节')
    out['sections']=[];ids=set()
    for section in sections:
        sid=text(section.get('id') or uid(),80); title=text(section.get('title',''),100).strip()
        # 章节名称允许留空：此时版面只显示编号（label），由调用方自行控制呈现。
        if not sid or sid in ids:raise ValueError('章节标识重复或为空')
        commodity_ids=list(dict.fromkeys(int(x) for x in section.get('commodity_ids',[])))
        for cid in commodity_ids:
            item=s.get(Commodity,cid)
            if not item or not item.enabled:raise ValueError('章节品种不存在或已停用')
        ids.add(sid);out['sections'].append({'id':sid,'title':title,'group':text(section.get('group',''),60).strip(),'label':text(section.get('label',''),20).strip(),'type':text(section.get('type',''),80),'commodity_ids':commodity_ids,'required':bool(section.get('required',False)),'default':text(section.get('default',''))})
    flow=cfg.get('workflow',[])
    if not isinstance(flow,list) or not 1<=len(flow)<=8:raise ValueError('请配置1至8个审核节点')
    out['workflow']=[];labels=set()
    for node in flow:
        label=text(node.get('label',''),30).strip();role=node.get('role');mode=node.get('mode','any');users=node.get('users',[])
        if not label or label in labels or label in ['草稿','已退回','待发布','已发布']:raise ValueError('审核节点名称为空、重复或与保留状态冲突')
        if role not in ['reviewer','compliance'] or mode not in ['any','all','sequential']:raise ValueError('审核角色或方式不合法')
        if not isinstance(users,list) or len(users)>50:raise ValueError('审核人员格式错误')
        users=list(dict.fromkeys(int(x) for x in users))
        if mode!='any' and not users:raise ValueError('会签和依次审批必须指定人员')
        for person in users:
            account=s.get(User,person)
            if not account or account.role!=role:raise ValueError('指定人员不属于节点角色')
        labels.add(label);out['workflow'].append({'label':label,'role':role,'mode':mode,'users':users})
    if not any(n['role']=='compliance' for n in out['workflow']):raise ValueError('审批流程必须包含合规审核节点')
    return name,out

def resolve_data(s,source,indicator):
    """取最近 500 条再按时间正序输出，保持图表 X 轴从旧到新。"""
    recent=(select(Observation.id,Observation.source,Observation.indicator,Observation.date,Observation.value,Observation.unit)
            .where(Observation.source==source,Observation.indicator==indicator)
            .order_by(Observation.date.desc(),Observation.id.desc()).limit(500).subquery())
    rows=[dict(r._mapping) for r in s.execute(
        select(recent.c.source,recent.c.indicator,recent.c.date,recent.c.value,recent.c.unit)
        .order_by(recent.c.date,recent.c.id))]
    if len({r['unit'] for r in rows})>1:raise ValueError('同一来源和指标存在不同单位，请先统一数据单位')
    return rows

def validate_document(s,doc,config,previous=None,refresh=False):
    if not isinstance(doc,dict):raise ValueError('文档结构无效')
    layout=doc.get('layout',config['layout'])
    if layout not in ['flow','grid','free']:raise ValueError('布局无效')
    out={'layout':layout,'sections':[]};sections=doc.get('sections',[]);expected={x['id']:x for x in config['sections']}
    if not isinstance(sections,list) or len(sections)!=len(expected) or {x.get('id') for x in sections}!=set(expected):raise ValueError('章节必须与创建时的分类配置一致')
    old={b['id']:b for x in (previous or {}).get('sections',[]) for b in x['blocks']}
    bids=set();count=0
    for section in sections:
        sc=expected[section['id']];blocks=section.get('blocks',[]);clean=[]
        if not isinstance(blocks,list):raise ValueError('组件列表无效')
        for block in blocks:
            count+=1
            if count>150:raise ValueError('每篇报告最多150个组件')
            bid=text(block.get('id') or uid(),80);kind=block.get('type');span=int(block.get('span',12))
            if not bid or bid in bids or kind not in ['text','chart','table','image'] or span not in [6,12]:raise ValueError('组件标识、类型或宽度无效')
            bids.add(bid);item={'id':bid,'type':kind,'span':span,'title':text(block.get('title',''),100)}
            if layout=='free':
                for key,default,lo,hi in [('x',30,0,700),('y',70+(count-1)*230,0,40000),('width',620,120,740),('height',210,80,1600)]:
                    val=float(block.get(key,default))
                    if not math.isfinite(val) or not lo<=val<=hi:raise ValueError('自由画布元素位置或尺寸越界')
                    item[key]=round(val,1)
                if item['x']+item['width']>760:raise ValueError('元素超出760像素画布宽度')
            if kind=='text':
                if 'html' in block:item['html'],item['text']=richtext.clean(text(block['html'],100000))
                else:item['text']=text(block.get('text',''),50000)
            elif kind=='image':
                prior=old.get(bid);aid=int(block['asset_id'])
                asset=s.get(LibraryItem,aid)
                # 已删除的素材只允许在原有引用上继续保留
                if not asset or asset.kind!='image' or not (not asset.deleted or (prior and prior.get('asset_id')==aid)):
                    raise ValueError('图片素材不存在')
                item.update(asset_id=asset.id,asset_name=asset.name)
            else:
                source=text(block.get('source',''),100);indicator=text(block.get('indicator',''),200)
                if not source or not indicator:raise ValueError('数据组件需要选择来源及指标')
                prior=old.get(bid)
                if prior and prior['type']==kind and prior.get('source')==source and prior.get('indicator')==indicator and not refresh:
                    rows=prior['data'];at=prior['refreshed_at']
                else:rows=resolve_data(s,source,indicator);at=datetime.datetime.now(datetime.timezone.utc).isoformat()
                if not rows:raise ValueError('所选数据源或指标不存在，请先导入数据')
                item.update(source=source,indicator=indicator,data=rows,refreshed_at=at)
            clean.append(item)
        out['sections'].append({'id':sc['id'],'group':sc.get('group',''),'label':sc.get('label',''),'title':sc['title'],'required':sc['required'],'blocks':clean})
    return out

def empty_document(cfg):
    """新报告章节不带空组件；要写字时在编辑器里用「＋文字」插入，空稿也不会带空段落送审。"""
    return {'layout':cfg['layout'],'sections':[{'id':x['id'],'group':x.get('group',''),'label':x.get('label',''),'title':x['title'],'required':x['required'],'blocks':[]} for x in cfg['sections']]}

def plain(doc,config):
    parts=[config.get('header','')]
    for section in doc['sections']:
        # 章节名称允许为空：标题行按「编号 名称」拼接，两者都空则不输出空标题
        heading=' '.join(v for v in (section.get('label',''),section.get('title','')) if v)
        if heading:parts.append('\n## '+heading)
        for block in section['blocks']:
            if block['title']:parts.append(block['title'])
            if block['type']=='text':parts.append(block['text'])
            elif block['type']=='image':parts.append('图片素材：'+block['asset_name'])
            else:
                parts.append('数据来源：'+block['source']+' / '+block['indicator'])
                parts.extend(f"{r['date']}：{r['value']} {r['unit']}" for r in block['data'])
    parts.append(config.get('footer',''))
    return '\n'.join(parts)

def structured_checks(r):
    if not r['document']:return []
    out=[]
    for index,x in enumerate(json.loads(r['document'])['sections'],1):
        filled=any((b.get('text','').strip() if b['type']=='text' else b.get('asset_id') if b['type']=='image' else b.get('data')) for b in x['blocks'])
        if x['required'] and not filled:
            # 章节名称允许为空，提示里退回编号，避免出现「必填章节尚未填写：」后面没内容
            out.append({'level':'阻断','message':'必填章节尚未填写：'+(x.get('title') or x.get('label') or '第%d章'%index)})
    return out

def eligibility(s,r,u):
    if not r['document']:return None
    if r['status'] in ['草稿','已退回']:return ['提交'] if r['author']==u['id'] else []
    if r['author']==u['id']:return []
    if r['status']=='已发布':return []
    if r['status']=='待发布':return ['发布'] if u['role']=='publisher' else []
    config=json.loads(r['config_snapshot']);ws=json.loads(r['workflow_state']);node=config['workflow'][ws['index']]
    if u['role']!=node['role'] or (node['users'] and u['id'] not in node['users']) or u['id'] in ws['approvals']:return []
    if node['mode']=='sequential' and u['id']!=next((v for v in node['users'] if v not in ws['approvals']),None):return []
    return ['通过','退回']

def handle(s,path,d,u,stamp,snapshot,event,checks):
    if path=='/api/categories':
        if u['role']!='admin':return {'error':'仅管理员可配置分类'},403
        name,cfg=validate_config(s,d)
        if d.get('id'):
            old=s.get(Category,int(d['id']))
            if not old:return {'error':'分类不存在'},404
            if int(d['revision'])!=old.revision:return {'error':'分类配置已被修改，请刷新后重试'},409
            revision=old.revision+1;cid=old.id
            old.name=name;old.config=dump(cfg);old.revision=revision;old.enabled=int(bool(d.get('enabled',True)))
        else:
            revision=1
            created=Category(name=name,config=dump(cfg),enabled=int(bool(d.get('enabled',True))))
            s.add(created);s.flush();cid=created.id
        s.add(ConfigEvent(category_id=cid,actor=u['name'],config=dump({'name':name,'config':cfg,'enabled':bool(d.get('enabled',True))}),revision=revision,at=stamp()))
        return {'id':cid},200
    if path=='/api/reports' and d.get('category_id'):
        if u['role'] not in ['admin','researcher']:return {'error':'无创建权限'},403
        cat=s.get(Category,int(d['category_id']))
        if not cat or not cat.enabled:return {'error':'分类不存在或已停用'},400
        cfg=json.loads(cat.config);cfg.update(category_name=cat.name,revision=cat.revision)
        nodes=flow_nodes(s,cat.id)
        if nodes:cfg['workflow']=nodes
        commodity=text(d.get('commodity',''),50)
        if commodity not in cfg['commodities']:raise ValueError('请选择该分类配置的品种')
        title=text(d.get('title',''),200).strip()
        if not title:raise ValueError('标题必填')
        inherited=d.get('inherit_id');note='分类：'+cat.name+'，配置版本：'+str(cat.revision)
        if inherited:
            source=s.get(Report,int(inherited))
            if not source or source.status!='已发布' or not source.document or source.category_id!=cat.id:raise ValueError('仅可继承同分类的已发布结构化报告')
            doc=json.loads(source.document);cfg=json.loads(source.config_snapshot);note+='；继承报告 #'+str(source.id)+' v'+str(source.version)+'，数据快照保留，需人工刷新'
        else:doc=empty_document(cfg)
        doc=validate_document(s,doc,cfg,doc if inherited else None)
        created=Report(title=title,commodity=commodity,kind=cfg['kind'],body=plain(doc,cfg),status='草稿',author=u['id'],updated=stamp(),
                       document=dump(doc),config_snapshot=dump(cfg),category_id=cat.id,workflow_state=dump({'index':0,'approvals':[]}),
                       inherited_from=int(inherited) if inherited else None)
        s.add(created);s.flush();snapshot(s,created,u);event(s,created,u,'继承创建' if inherited else '按分类创建',note)
        return {'id':created.id},200
    if path not in ['/api/save','/api/refresh','/api/transition','/api/convert']:return None
    rid=int(d['id']);r=s.get(Report,rid)
    if not r:return None
    if path=='/api/convert':
        if r.document or r.author!=u['id'] or r.status not in ['草稿','已退回']:return {'error':'仅作者可转换未送审的旧版报告'},403
        cfg={'kind':r.kind,'layout':'flow','header':'','footer':'','color':'#127867','font_size':15,'category_name':'旧版报告转换','revision':1,'sections':[{'id':uid(),'title':'研究正文','required':True,'default':r.body}],'workflow':[{'label':'研究复核','role':'reviewer','mode':'any','users':[]},{'label':'合规审核','role':'compliance','mode':'any','users':[]}]}
        doc=validate_document(s,empty_document(cfg),cfg)
        r.document=dump(doc);r.config_snapshot=dump(cfg);r.workflow_state=dump({'index':0,'approvals':[]})
        r.version=(r.version or 1)+1;r.updated=stamp()
        snapshot(s,r,u);event(s,r,u,'转换组件文档');return {'ok':True},200
    if not r.document:return None
    cfg=json.loads(r.config_snapshot)
    if path in ['/api/save','/api/refresh']:
        if r.author!=u['id'] or r.status not in ['草稿','已退回']:return {'error':'仅作者可编辑草稿或退回稿'},403
        if int(d['version'])!=r.version:return {'error':'版本冲突，请刷新并合并修改'},409
        doc=validate_document(s,d['document'],cfg,json.loads(r.document),path=='/api/refresh');title=text(d['title'],200).strip()
        if not title:raise ValueError('标题必填')
        r.title=title;r.body=plain(doc,cfg);r.document=dump(doc);r.version=(r.version or 1)+1;r.updated=stamp()
        snapshot(s,r,u);event(s,r,u,'刷新数据并保存' if path=='/api/refresh' else '保存组件文档');return {'ok':True},200
    action=d['action'];allowed=eligibility(s,r,u)
    if ('expected_status' in d and d['expected_status']!=r.status) or ('expected_workflow' in d and d['expected_workflow']!=r.workflow_state):return {'error':'审批状态已更新，请刷新后再操作'},409
    if action not in allowed:return {'error':'当前账号、审批顺序或状态不允许此操作'},403
    ws=json.loads(r.workflow_state);note=text(d.get('note',''),2000).strip();target=r.status
    if action=='提交':
        if any(x['level']=='阻断' for x in checks(r)):return {'error':'请先解决规则检查中的阻断项'},400
        for node in cfg['workflow']:
            if node['users'] and r.author in node['users']:return {'error':'作者被指定为审核人，请联系管理员调整分类后重新创建报告'},400
            if node['users']:
                available=s.execute(select(func.count()).select_from(User).where(User.role==node['role'],User.id.in_(node['users']))).scalar()
                if available!=len(node['users']):return {'error':'指定审核人已不可用'},400
            elif not s.execute(select(User.id).where(User.role==node['role'],User.id!=r.author).limit(1)).first():return {'error':'尚未创建可用的'+node['label']+'账号'},400
        ws={'index':0,'approvals':[]};target=cfg['workflow'][0]['label']
    elif action=='退回':
        if not note:raise ValueError('退回原因必填')
        ws={'index':0,'approvals':[]};target='已退回'
    elif action=='发布':target='已发布'
    elif action=='通过':
        node=cfg['workflow'][ws['index']];ws['approvals'].append(u['id'])
        if node['mode']=='any' or set(node['users'])<=set(ws['approvals']):
            ws={'index':ws['index']+1,'approvals':[]};target=cfg['workflow'][ws['index']]['label'] if ws['index']<len(cfg['workflow']) else '待发布'
    r.status=target;r.workflow_state=dump(ws);r.updated=stamp()
    event(s,r,u,action,note);return {'ok':True},200
