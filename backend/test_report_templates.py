import copy,json,unittest,uuid
from test_report_creation import ReportCreation

class TemplateLinkage(ReportCreation):
 def category(self):
  cfg=copy.deepcopy(self.cat['config'])
  cfg['sections']=[{'id':key,'title':title,'group':'模板分组','label':str(i).zfill(2),'type':'供需','required':i==1,'default':'模板提示'+key,'commodity_ids':[]} for i,(key,title) in enumerate([('t1','第一章'),('t2','第二章'),('t3','第三章')],1)]
  result=self.call(self.admin,'categories',{'name':'模板联动-'+uuid.uuid4().hex[:6],'config':cfg,'enabled':True});self.assertEqual(result[0],200,result)
  return next(c for c in self.call(self.admin,'state')[1]['categories'] if c['id']==result[1]['id'])
 def update_category(self,cat,config):
  result=self.call(self.admin,'categories',{'id':cat['id'],'name':cat['name'],'revision':cat['revision'],'config':config,'enabled':True});self.assertEqual(result[0],200,result)
  return next(c for c in self.call(self.admin,'state')[1]['categories'] if c['id']==cat['id'])
 def chapter(self,r,section,action='edit',**payload):
  data={'id':r['id'],'version':r['version'],'section_id':section,'action':action,**payload}
  result=self.call(self.owner,'chapters',data);self.assertEqual(result[0],200,result);return self.report(r['id'])
 def preview(self,r):
  result=self.call(self.owner,'report-template/'+str(r['id']));self.assertEqual(result[0],200,result);return result[1]
 def sync(self,r,plan=None,client=None):
  plan=plan or self.preview(r)
  return self.call(client or self.owner,'report-template-sync',{'id':r['id'],'version':plan['report_version'],'token':plan['token']})

 def test_category_selects_shared_approval_flow(self):
  cat=self.category()
  before=self.create(category_id=cat['id'],commodity='铜')
  nodes=[{'label':'关联流程合规','role':'compliance','mode':'any','users':[]}]
  status,created=self.call(self.admin,'approval-flows',{'name':'分类选择验证','nodes':nodes,'category_ids':[],'enabled':True})
  self.assertEqual(status,200,created)
  payload={'id':cat['id'],'revision':cat['revision'],'name':cat['name'],'config':cat['config'],'enabled':True,'approval_flow_id':created['id']}
  self.assertEqual(self.call(self.admin,'categories',payload)[0],200)
  state=self.call(self.admin,'state')[1]
  self.assertIn(cat['id'],next(f for f in state['flows'] if f['id']==created['id'])['category_ids'])
  after=self.create(category_id=cat['id'],commodity='铜')
  self.assertEqual(json.loads(after['config_snapshot'])['workflow'],nodes)
  self.assertEqual(self.report(before['id'])['config_snapshot'],before['config_snapshot'])
  # Reassign atomically, removing the previous direct link.
  status,second=self.call(self.admin,'approval-flows',{'name':'另一个流程','nodes':nodes,'category_ids':[],'enabled':True})
  self.assertEqual(status,200)
  cat=next(c for c in state['categories'] if c['id']==cat['id'])
  payload.update(revision=cat['revision'],approval_flow_id=second['id'])
  self.assertEqual(self.call(self.admin,'categories',payload)[0],200)
  state=self.call(self.admin,'state')[1]
  self.assertNotIn(cat['id'],next(f for f in state['flows'] if f['id']==created['id'])['category_ids'])
  self.assertIn(cat['id'],next(f for f in state['flows'] if f['id']==second['id'])['category_ids'])
  # A disabled flow cannot be associated.
  self.call(self.admin,'approval-flows',{'id':second['id'],'name':'另一个流程','nodes':nodes,'category_ids':[cat['id']],'enabled':False})
  payload.update(revision=next(c for c in state['categories'] if c['id']==cat['id'])['revision'],approval_flow_id=second['id'])
  self.assertEqual(self.call(self.admin,'categories',payload)[0],400)

 def test_local_settings_and_numbering(self):
  cat=self.category();r=self.create(category_id=cat['id'],commodity='铜')
  doc=json.loads(r['document']);self.assertEqual([s['label'] for s in doc['sections']],['01','02','03'])
  r=self.chapter(r,'t2','up');doc=json.loads(r['document'])
  self.assertEqual([s['id'] for s in doc['sections']],['t2','t1','t3'])
  self.assertEqual([s['label'] for s in doc['sections']],['01','02','03'])
  self.assertEqual([s['label'] for s in json.loads(r['config_snapshot'])['sections']],['01','02','03'])
  r=self.chapter(r,'t2',title='当前研报自定义名称',group='当前分组',label='附录A',type='当前类型',required=False,default='当前写作提示',editors=[r['author']],tags=['本篇'],commodity_ids=[])
  chapter=next(s for s in json.loads(r['document'])['sections'] if s['id']=='t2')
  snapshot=next(s for s in json.loads(r['config_snapshot'])['sections'] if s['id']=='t2')
  for key,value in {'title':'当前研报自定义名称','group':'当前分组','label':'附录A','type':'当前类型','required':False}.items():self.assertEqual(chapter[key],value);self.assertEqual(snapshot[key],value)
  self.assertEqual(snapshot['default'],'当前写作提示')
  untouched=next(c for c in self.call(self.admin,'state')[1]['categories'] if c['id']==cat['id'])
  self.assertEqual(untouched['config']['sections'],cat['config']['sections'])

 def test_sync_preserves_content_and_applies_effective_workflow(self):
  cat=self.category();r=self.create(category_id=cat['id'],commodity='铜')
  r=self.chapter(r,'t1','add');doc=json.loads(r['document']);custom=doc['sections'][-1]['id']
  for section in doc['sections']:
   if section['id'] in ['t1','t3']:section['blocks']=[{'id':'text-'+section['id'],'type':'text','span':12,'title':'','text':'正文必须保留。风险提示、数据来源仅用于联动测试。'*8}]
  self.assertEqual(self.call(self.owner,'personal-save',{'id':r['id'],'version':r['version'],'document':doc})[0],200)
  r=self.report(r['id']);original_blocks={s['id']:s['blocks'] for s in json.loads(r['document'])['sections']}
  changed=copy.deepcopy(cat['config']);changed['sections']=[{**changed['sections'][0],'title':'模板新标题','group':'新分组','default':'新的生成提示'}, {'id':'t4','title':'新增必填章节','group':'新分组','label':'02','type':'新增类型','required':True,'default':'新章提示','commodity_ids':[]}]
  cat=self.update_category(cat,changed)
  workflow=[{'label':'研究复核','role':'reviewer','mode':'all','users':[self.ids['create-review']]},{'label':'合规审核','role':'compliance','mode':'any','users':[self.ids['create-compliance']]}]
  result=self.call(self.admin,'approval-flows',{'name':'模板联动审批','category_ids':[cat['id']],'nodes':workflow});self.assertEqual(result[0],200,result)
  plan=self.preview(r);self.assertEqual(len(plan['added']),1);self.assertEqual(len(plan['updated']),1);self.assertEqual(len(plan['removed_empty']),1)
  self.assertEqual({s['id'] for s in plan['retained']},{'t3',custom});self.assertEqual(plan['workflow'],workflow)
  self.assertEqual(self.report(r['id'])['version'],r['version'],'查看模板不应自动改写已有研报')
  result=self.sync(r,plan);self.assertEqual(result[0],200,result)
  updated=self.report(r['id']);doc=json.loads(updated['document']);cfg=json.loads(updated['config_snapshot'])
  self.assertEqual([s['id'] for s in doc['sections']],['t1','t4','t3',custom])
  for section in doc['sections']:
   if section['id'] in ['t1','t3']:self.assertEqual(section['blocks'],original_blocks[section['id']])
   self.assertEqual(section['state'],'未提交')
  self.assertEqual(cfg['workflow'],workflow);self.assertEqual(cfg['sections'][0]['default'],'新的生成提示')
  self.assertEqual(doc['layout'],json.loads(r['document'])['layout']);self.assertEqual(updated['title'],r['title'])
  self.assertEqual([s['id'] for s in cfg['sections']],[s['id'] for s in doc['sections']])
  checks=self.call(self.owner,'check',{'id':r['id']})[1]['checks']
  self.assertTrue(any('新增必填章节' in check['message'] and check['level']=='阻断' for check in checks))
  second=self.sync(updated);self.assertEqual(second[0],200,second);self.assertFalse(second[1]['changed']);self.assertEqual(self.report(r['id'])['version'],updated['version'])

 def test_stale_tokens_permissions_and_submitted_snapshot(self):
  cat=self.category();r=self.create(category_id=cat['id'],commodity='铜',collaboration='shared',collaborators=[self.ids['create-writer']])
  plan=self.preview(r)
  self.assertEqual(self.sync(r,plan,self.writer)[0],403)
  change=copy.deepcopy(cat['config']);change['sections'][0]['title']='更新后的分类章节';cat=self.update_category(cat,change)
  self.assertEqual(self.sync(r,plan)[0],409);self.assertEqual(self.report(r['id'])['version'],r['version'])
  plan=self.preview(r);r=self.chapter(r,'t1',title='用户刚修改的名称',editors=[r['author']],tags=[],commodity_ids=[])
  self.assertEqual(self.sync(r,plan)[0],409)
  self.assertEqual(self.sync(r)[0],200)
  # Changing effective flow configuration invalidates a previously previewed token too.
  plan=self.preview(self.report(r['id']))
  result=self.call(self.admin,'approval-flows',{'name':'并发修改审批','category_ids':[cat['id']],'nodes':[{'label':'研究复核','role':'reviewer','mode':'all','users':[self.ids['create-review']]},{'label':'合规审核','role':'compliance','mode':'any','users':[]}]})
  self.assertEqual(result[0],200,result);self.assertEqual(self.sync(self.report(r['id']),plan)[0],409)
  # Create a personal report to verify sent reports remain immutable.
  sent=self.create(category_id=cat['id'],commodity='铜');doc=self.ensure_blocks(json.loads(sent['document']))
  for section in doc['sections']:section['blocks'][0]['text']='风险提示与数据来源均已核验。'+'审批快照测试正文。'*30
  self.assertEqual(self.call(self.owner,'personal-save',{'id':sent['id'],'version':sent['version'],'document':doc})[0],200)
  self.assertEqual(self.call(self.owner,'transition',{'id':sent['id'],'action':'提交'})[0],200)
  snapshot=self.report(sent['id'])['config_snapshot']
  plan=self.preview(self.report(sent['id']));self.assertEqual(self.sync(self.report(sent['id']),plan)[0],403)
  self.assertEqual(self.report(sent['id'])['config_snapshot'],snapshot)


def load_tests(loader,tests,pattern):return unittest.TestSuite(TemplateLinkage(name) for name in ['test_category_selects_shared_approval_flow','test_local_settings_and_numbering','test_sync_preserves_content_and_applies_effective_workflow','test_stale_tokens_permissions_and_submitted_snapshot'])
if __name__=='__main__':unittest.main(verbosity=2)
