"""Explicit, version-checked template application to editable reports only."""
import hashlib
import json
from db import Category
import manual_engine as manual
import report_engine as e

FIELDS={'title':'','group':'','label':'','type':'','required':False,'commodity_ids':[],'default':''}

def definition(section, previous=None):
    base={**(previous or {}),**section}
    return {'id':section['id'],**{key:base.get(key,default) for key,default in FIELDS.items()}}


def plan(s,r):
    if not r.category_id or not r.document:raise ValueError('当前报告没有可同步的分类模板')
    cat=s.get(Category,r.category_id)
    node=next((node for node in manual.tree(s) if node['id']==r.category_id),None)
    if not cat or not node or node['folder'] or not node['effective_enabled']:raise ValueError('分类不存在或已停用，请先联系管理员维护分类')
    latest=json.loads(cat.config);workflow=e.flow_nodes(s,cat.id) or latest['workflow']
    cfg=json.loads(r.config_snapshot);doc=json.loads(r.document);md=manual.meta(r) or {}
    old_defs={item['id']:item for item in cfg['sections']};old_sections={item['id']:item for item in doc['sections']}
    source_ids=set(md.get('template_section_ids',[item['id'] for item in cfg['sections']]))
    latest_defs=[definition(item) for item in latest['sections']];latest_ids={item['id'] for item in latest_defs}
    added=[];changed=[];kept=[];removed=[];merged=[]
    for item in latest_defs:
        current=old_sections.get(item['id'])
        if current:
            if definition(current,old_defs.get(item['id']))!=item:changed.append(item)
            merged.append({**current,**{k:v for k,v in item.items() if k!='default'}})
        else:
            added.append(item)
            merged.append({**{k:v for k,v in item.items() if k!='default'},'blocks':[],'editors':[r.author],'tags':[],'state':'未提交','revision':0})
    for current in doc['sections']:
        if current['id'] in latest_ids:continue
        if current.get('blocks') or current['id'] not in source_ids:
            merged.append(current);kept.append(definition(current,old_defs.get(current['id'])))
        else:removed.append(definition(current,old_defs.get(current['id'])))
    token=hashlib.sha256(e.dump({'revision':cat.revision,'sections':latest_defs,'workflow':workflow}).encode()).hexdigest()
    workflow_changed=cfg.get('workflow')!=workflow
    order_changed=[item['id'] for item in doc['sections']]!=[item['id'] for item in merged]
    changed_any=bool(added or changed or removed or workflow_changed or order_changed or cfg.get('revision')!=cat.revision)
    return {'category_id':cat.id,'category_name':cat.name,'revision':cat.revision,'report_revision':cfg.get('revision'),
            'report_version':r.version,'token':token,'sections':latest_defs,'workflow':workflow,'workflow_changed':workflow_changed,
            'added':added,'updated':changed,'retained':kept,'removed_empty':removed,'changed':changed_any,
            '_document':{**doc,'sections':merged},'_config':cfg,'_metadata':md,'_latest_ids':[item['id'] for item in latest_defs]}


def preview(s,r):return {key:value for key,value in plan(s,r).items() if not key.startswith('_')}


def apply(s,r,data,u,stamp,snapshot,event):
    if r.author!=u.id:return {'error':'仅创建人可同步当前研报模板'},403
    if r.status not in ['草稿','已退回']:return {'error':'仅草稿或已退回报告可同步，送审后沿用原审批快照'},403
    if not manual.meta(r):return {'error':'旧版报告暂不支持模板同步'},400
    if int(data.get('version') or 0)!=r.version:return {'error':'报告已有新版本，请刷新后再同步'},409
    change=plan(s,r)
    if data.get('token')!=change['token']:return {'error':'分类或审批模板已更新，请重新预览后同步'},409
    if not change['changed']:return {'ok':True,'version':r.version,'changed':False},200
    doc=change['_document'];cfg=change['_config'];md=change['_metadata']
    if len(doc['sections'])>30:return {'error':'同步后章节超过 30 个，请先合并需要保留的章节'},400
    for section in doc['sections']:
        section['state']='未提交';section['revision']=section.get('revision',0)+1
    # Only chapter and approval definitions follow the template; the report keeps its layout and body.
    defaults={item['id']:item for item in cfg['sections']}
    defaults.update({item['id']:item for item in change['sections']})
    cfg['sections']=[definition(section,defaults.get(section['id'])) for section in doc['sections']]
    cfg['workflow']=change['workflow'];cfg['revision']=change['revision'];cfg['category_name']=change['category_name']
    md['template_section_ids']=change['_latest_ids'];md['retained_section_ids']=[item['id'] for item in change['retained']]
    r.config_snapshot=e.dump(cfg);r.workflow_state=e.dump({'index':0,'approvals':[]});r.scheduled_at=''
    return manual.save_doc(s,r,u,doc,stamp,snapshot,event,'同步分类章节与审批模板',
        '分类：%s；版本：%s；新增 %s 章，更新 %s 章，保留 %s 章' % (change['category_name'],change['revision'],len(change['added']),len(change['updated']),len(change['retained'])),metadata=md)
