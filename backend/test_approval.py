import json,os,sys,contextlib,sqlite3,subprocess,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from test_report_creation import ReportCreation

class ApprovalChecks(ReportCreation):
 @classmethod
 def setUpClass(cls):
  super().setUpClass();helper=cls('test_modes_and_rejection');cls.flow_id=None
  for name,role in [('review2','reviewer'),('review-unassigned','reviewer'),('review-disabled','reviewer'),('publish2','publisher')]:
   helper.assertEqual(helper.call(cls.admin,'users',{'name':name,'role':role,'password':'123456'})[0],200)
   c=helper.client();helper.assertEqual(helper.call(c,'login',{'name':name,'password':'123456'})[0],200);cls.clients[name]=c
  cls.ids.update({u['name']:u['id'] for u in helper.call(cls.admin,'state')[1]['users']})
  helper.assertEqual(helper.call(cls.admin,'users',{'action':'toggle','id':cls.ids['review-disabled']})[0],200)
 def flow(self,mode='any',reviewers=None):
  nodes=[{'label':'研究复核','role':'reviewer','mode':mode,'users':[self.ids['create-review'],self.ids['review2']] if reviewers is None else reviewers}, {'label':'合规审核','role':'compliance','mode':'any','users':[self.ids['create-compliance']]}]
  data={'name':'专项审批测试','category_ids':[self.cat['id']],'nodes':nodes}
  if self.flow_id:data['id']=self.flow_id
  status,res=self.call(self.admin,'approval-flows',data)
  if status==200:type(self).flow_id=res['id']
  return status,res
 def prepared(self):
  r=self.create();doc=self.ensure_blocks(json.loads(r['document']))
  for sec in doc['sections']:sec['blocks'][0]['text']='风险提示与数据来源均需核验。'+'测试研究观点以真实数据为依据，需要人工复核。'*15
  self.assertEqual(self.call(self.owner,'personal-save',{'id':r['id'],'version':r['version'],'document':doc})[0],200)
  return self.report(r['id'])
 def transition(self,client,rid,action,note='',expected=True):
  r=self.report(rid);data={'id':rid,'action':action,'note':note}
  if expected:data.update(expected_status=r['status'],expected_workflow=r['workflow_state'])
  return self.call(client,'transition',data)
 def through(self,mode='any'):
  self.assertEqual(self.flow(mode)[0],200);r=self.prepared();rid=r['id']
  self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
  self.assertEqual(self.transition(self.clients['create-review'],rid,'通过')[0],200)
  if mode!='any':self.assertEqual(self.transition(self.clients['review2'],rid,'通过')[0],200)
  self.assertEqual(self.transition(self.clients['create-compliance'],rid,'通过')[0],200)
  self.assertEqual(self.report(rid)['status'],'待发布');return rid
 def test_modes_and_rejection(self):
  for mode in ['any','all','sequential']:
   with self.subTest(mode=mode):
    self.assertEqual(self.flow(mode)[0],200);r=self.prepared();rid=r['id']
    self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
    for client,action in [(self.owner,'通过'),(self.clients['create-compliance'],'通过'),(self.clients['create-publisher'],'发布'),(self.clients['review-unassigned'],'通过')]:
     self.assertEqual(self.transition(client,rid,action)[0],403)
    if mode=='sequential':self.assertEqual(self.transition(self.clients['review2'],rid,'通过')[0],403)
    self.assertEqual(self.transition(self.clients['create-review'],rid,'退回')[0],400)
    self.assertEqual(self.transition(self.clients['create-review'],rid,'通过')[0],200)
    self.assertEqual(self.transition(self.clients['create-review'],rid,'通过')[0],403)
    if mode!='any':
     self.assertEqual(self.report(rid)['status'],'研究复核')
     self.assertEqual(self.transition(self.clients['review2'],rid,'通过')[0],200)
    self.assertEqual(self.report(rid)['status'],'合规审核')
    self.assertEqual(self.transition(self.clients['create-compliance'],rid,'退回','补充数据来源')[0],200)
    self.assertEqual(json.loads(self.report(rid)['workflow_state']),{'index':0,'approvals':[]})
    self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
    if mode=='sequential':self.assertEqual(self.transition(self.clients['review2'],rid,'通过')[0],403)
    self.assertEqual(self.transition(self.clients['create-review'],rid,'通过')[0],200)
    if mode!='any':self.assertEqual(self.transition(self.clients['review2'],rid,'通过')[0],200)
    self.assertEqual(self.transition(self.clients['create-compliance'],rid,'通过')[0],200)
    self.assertTrue(self.report(rid)['approved_at'])
    self.assertEqual(self.transition(self.owner,rid,'发布')[0],403)
    self.assertEqual(self.transition(self.clients['create-publisher'],rid,'发布')[0],200)
    self.assertTrue(self.report(rid)['published_at'])
    self.assertEqual(self.transition(self.clients['create-publisher'],rid,'发布')[0],403)
    history=self.call(self.owner,'history/'+str(rid))[1]['events']
    self.assertEqual(sum(e['action']=='发布' for e in history),1)
    self.assertTrue(any(e['action']=='退回' and e['note']=='补充数据来源' for e in history))
    print('审批模式通过:',mode,flush=True)
 def test_edit_lock_follows_flow(self):
  """可编辑性跟着审批节点走：送审即锁、退回解锁、再送审再锁。"""
  self.assertEqual(self.flow('any')[0],200);rid=self.prepared()['id']
  self.assertTrue(self.report(rid)['can_edit'],'草稿应可编辑')
  self.assertEqual(self.report(rid)['current_node'],None)
  self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
  r=self.report(rid)
  self.assertEqual(r['status'],'研究复核')
  self.assertFalse(r['can_edit'],'送审后作者不能改正文')
  self.assertIn('研究复核',r['edit_reason'])
  self.assertEqual(r['current_node']['label'],'研究复核')
  self.assertEqual(r['current_node']['role'],'reviewer')
  sec=json.loads(r['document'])['sections'][0]
  for client in [self.owner,self.clients['create-review']]:
   self.assertEqual(self.call(client,'chapter/save',{'id':rid,'section_id':sec['id'],'revision':sec['revision'],'blocks':sec['blocks']})[0],403,'审批中任何人不能保存章节')
   self.assertEqual(self.call(client,'report-info',{'id':rid,'version':r['version'],'title':'审批中改名'})[0],403,'审批中不能改基础信息')
  # 审批人只能通过/退回，退回后作者恢复可编辑，再送审重新锁定
  self.assertEqual(self.transition(self.clients['create-review'],rid,'退回','补充数据来源')[0],200)
  r=self.report(rid)
  self.assertEqual(r['status'],'已退回');self.assertTrue(r['can_edit'])
  self.assertIn('已退回',r['edit_reason'])
  self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
  self.assertFalse(self.report(rid)['can_edit'])
  print('审批中编辑锁通过',flush=True)
 def test_concurrent_review_and_publish(self):
  self.assertEqual(self.flow('all')[0],200);rid=self.prepared()['id'];self.transition(self.owner,rid,'提交');r=self.report(rid)
  payload={'id':rid,'action':'通过','expected_status':r['status'],'expected_workflow':r['workflow_state']};barrier=threading.Barrier(2)
  def send(args):c,data=args;barrier.wait();return self.call(c,'transition',data)
  reviewers=[self.clients['create-review'],self.clients['review2']]
  with ThreadPoolExecutor(2) as pool:responses=list(pool.map(send,[(c,payload) for c in reviewers]))
  self.assertEqual(sorted(x[0] for x in responses),[200,409],responses)
  failed=reviewers[next(i for i,x in enumerate(responses) if x[0]==409)]
  self.assertEqual(self.transition(failed,rid,'通过')[0],200)
  self.assertEqual(self.report(rid)['status'],'合规审核')
  self.assertEqual(self.transition(self.clients['create-compliance'],rid,'通过')[0],200);r=self.report(rid)
  payload={'id':rid,'action':'发布','expected_status':r['status'],'expected_workflow':r['workflow_state']};barrier=threading.Barrier(2)
  with ThreadPoolExecutor(2) as pool:responses=list(pool.map(send,[(c,payload) for c in [self.clients['create-publisher'],self.clients['publish2']]]))
  self.assertEqual(sorted(x[0] for x in responses),[200,409],responses)
  with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:self.assertEqual(db.execute('select count(*) from publication_history where report_id=?',(rid,)).fetchone()[0],1)
  print('并发会签与并发发布通过',flush=True)
 def test_flow_snapshot_and_validation(self):
  self.assertEqual(self.flow('any')[0],200);old=self.prepared()
  self.assertEqual(self.flow('sequential')[0],200);new=self.prepared()
  self.assertEqual(json.loads(self.report(old['id'])['config_snapshot'])['workflow'][0]['mode'],'any')
  self.assertEqual(json.loads(new['config_snapshot'])['workflow'][0]['mode'],'sequential')
  self.assertEqual(self.call(self.owner,'approval-flows',{'name':'越权','nodes':[]})[0],403)
  self.assertEqual(self.call(self.admin,'approval-flows',{'name':'缺合规','nodes':[{'label':'复核','role':'reviewer','mode':'any','users':[]}]})[0],400)
  print('流程快照和配置权限通过',flush=True)
 def test_scheduled_publication(self):
  rid=self.through();publisher=self.clients['create-publisher']
  self.assertEqual(self.call(self.owner,'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})[0],403)
  self.assertEqual(self.call(publisher,'report-schedule',{'id':rid,'at':'2020-01-01T09:00'})[0],400)
  self.assertEqual(self.call(publisher,'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})[0],200)
  self.assertEqual(self.call(publisher,'report-schedule',{'id':rid,'at':''})[0],200)
  self.assertFalse(self.report(rid)['scheduled_at'])
  self.call(publisher,'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})
  with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:db.execute("update reports set scheduled_at='2020-01-01 00:00:00 UTC' where id=?",(rid,));db.commit()
  subprocess.run([sys.executable,'-c','from app import publish_due; publish_due(); publish_due()'],cwd='backend',env={**os.environ,'DATA_DIR':self.tmp.name},check=True)
  self.assertEqual(self.report(rid)['status'],'已发布')
  with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:self.assertEqual(db.execute('select count(*) from publication_history where report_id=?',(rid,)).fetchone()[0],1)
  print('定时发布、取消与重复扫描通过',flush=True)
 def test_disabled_approver(self):
  status,res=self.flow('all',[self.ids['review-disabled']])
  print('停用审核人配置响应:',status,flush=True)
  if status==200:
   rid=self.prepared()['id'];submitted=self.transition(self.owner,rid,'提交')
   print('含停用审核人的报告提交响应:',submitted,'当前状态:',self.report(rid)['status'],flush=True)
   self.assertNotEqual(submitted[0],200,'报告不应送入只有停用审核人的会签节点')
  else:self.assertEqual(status,400,res)
 def test_withdraw_clears_schedule(self):
  rid=self.through();self.assertEqual(self.call(self.clients['create-publisher'],'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})[0],200)
  self.assertEqual(self.call(self.owner,'report-withdraw',{'id':rid,'note':''})[0],400)
  self.assertEqual(self.call(self.owner,'report-withdraw',{'id':rid,'note':'撤回修改内容'})[0],200)
  r=self.report(rid);print('撤销审批后状态:',r['status'],'残留定时:',r['scheduled_at'],flush=True)
  self.assertFalse(r['scheduled_at'],'撤销审批应取消旧版本的发布预约')
  # Pre-existing returned reports may still carry an appointment from the old version.
  with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:db.execute("update reports set scheduled_at='2020-01-01 00:00:00 UTC' where id=?",(rid,));db.commit()
  self.assertEqual(self.transition(self.owner,rid,'提交')[0],200)
  self.assertFalse(self.report(rid)['scheduled_at'],'重新送审应清除旧库遗留预约')
  self.assertEqual(self.transition(self.clients['create-review'],rid,'通过')[0],200)
  self.assertEqual(self.transition(self.clients['create-compliance'],rid,'通过')[0],200)
  subprocess.run([sys.executable,'-c','from app import publish_due; publish_due()'],cwd='backend',env={**os.environ,'DATA_DIR':self.tmp.name},check=True)
  self.assertEqual(self.report(rid)['status'],'待发布','新版本通过审批后必须由发布专员重新发布或预约')

 def test_disable_after_creation(self):
  self.assertEqual(self.flow('all',[self.ids['review2']])[0],200)
  rid=self.prepared()['id']
  self.call(self.admin,'users',{'action':'toggle','id':self.ids['review2']})
  try:
   self.assertEqual(self.transition(self.owner,rid,'提交')[0],400)
   self.assertEqual(self.report(rid)['status'],'草稿')
  finally:
   self.call(self.admin,'users',{'action':'toggle','id':self.ids['review2']})
   self.call(self.clients['review2'],'login',{'name':'review2','password':'123456'})
  self.assertEqual(self.flow('any',[])[0],200)
  rid=self.prepared()['id'];names=['create-review','review2','review-unassigned']
  for name in names:self.call(self.admin,'users',{'action':'toggle','id':self.ids[name]})
  try:
   self.assertEqual(self.transition(self.owner,rid,'提交')[0],400)
   self.assertEqual(self.report(rid)['status'],'草稿')
  finally:
   for name in names:
    self.call(self.admin,'users',{'action':'toggle','id':self.ids[name]})
    self.call(self.clients[name],'login',{'name':name,'password':'123456'})

 def test_withdraw_beats_inflight_scheduler(self):
  import time
  rid=self.through();self.call(self.clients['create-publisher'],'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})
  with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:db.execute("update reports set scheduled_at='2020-01-01 00:00:00 UTC' where id=?",(rid,));db.commit()
  ready=Path(self.tmp.name)/'scheduler-ready';resume=Path(self.tmp.name)/'scheduler-resume'
  code="""from pathlib import Path
import os,time,app
ready=Path(os.environ['TEST_READY']);resume=Path(os.environ['TEST_RESUME'])
original=app.calendar.timegm
def gated(value):
 ready.touch()
 limit=time.monotonic()+8
 while not resume.exists() and time.monotonic()<limit:time.sleep(.01)
 return original(value)
app.calendar.timegm=gated
app.publish_due()
"""
  worker=subprocess.Popen([sys.executable,'-c',code],cwd='backend',env={**os.environ,'DATA_DIR':self.tmp.name,'TEST_READY':str(ready),'TEST_RESUME':str(resume)})
  try:
   limit=time.monotonic()+5
   while not ready.exists() and time.monotonic()<limit:time.sleep(.01)
   self.assertTrue(ready.exists(),'定时任务应已读取预约，等待执行')
   self.assertEqual(self.call(self.owner,'report-withdraw',{'id':rid,'note':'取消已被定时任务读取的预约'})[0],200)
   resume.touch();self.assertEqual(worker.wait(timeout=5),0)
   self.assertEqual(self.report(rid)['status'],'已退回')
   self.assertFalse(self.report(rid)['scheduled_at'])
   with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:self.assertEqual(db.execute('select count(*) from publication_history where report_id=?',(rid,)).fetchone()[0],0)
  finally:
   resume.touch()
   if worker.poll() is None:worker.terminate();worker.wait()

def load_tests(loader, tests, pattern):
 names=['test_modes_and_rejection','test_concurrent_review_and_publish','test_flow_snapshot_and_validation','test_scheduled_publication','test_disabled_approver','test_withdraw_clears_schedule','test_disable_after_creation','test_withdraw_beats_inflight_scheduler']
 return unittest.TestSuite(ApprovalChecks(n) for n in names)

if __name__ == '__main__':unittest.main(verbosity=2)
