import sys,json,unittest,threading
from concurrent.futures import ThreadPoolExecutor
from test_workflow import Workflow

class CollaborationCheck(Workflow):
 def test_parallel_editing(self):
  admin=self.client();pw='123456'
  self.assertEqual(self.call(admin,'setup',{'name':'admin','password':pw})[0],200)
  clients=[]
  for name in ['collab-owner','collab-writer','collab-outsider']:
   self.assertEqual(self.call(admin,'users',{'name':name,'role':'researcher','password':pw})[0],200)
   c=self.client();self.assertEqual(self.call(c,'login',{'name':name,'password':pw})[0],200);clients.append(c)
  owner,writer,outsider=clients
  state=self.call(admin,'state')[1];ids={u['name']:u['id'] for u in state['users']}
  cat=next(c for c in state['categories'] if not c['folder']);by=state['authors'][0]
  status,result=self.call(owner,'reports',{'manual':True,'category_id':cat['id'],'title':'并发协作验证','commodity':'铜','byline_id':by['id'],'report_date':'2026-11-18','collaboration':'shared','collaborators':[ids['collab-writer']],'public':False,'layout':'grid'})
  self.assertEqual(status,200,result);rid=result['id']
  def report():return next(r for r in self.call(owner,'state')[1]['reports'] if r['id']==rid)
  doc=json.loads(report()['document']);s1,s2=doc['sections'][:2]
  for sec in [s1,s2]:
   r=report()
   response=self.call(owner,'chapters',{'id':rid,'version':r['version'],'section_id':sec['id'],'action':'edit','title':sec['title'] or '协作章节','editors':[ids['collab-owner'],ids['collab-writer']],'tags':[],'commodity_ids':[]})
   self.assertEqual(response[0],200,response)
  self.assertNotIn(rid,[r['id'] for r in self.call(outsider,'state')[1]['reports']])
  def payload(sec,text):return {'id':rid,'section_id':sec['id'],'revision':sec['revision'],'blocks':[{'id':'test-'+sec['id'],'type':'text','span':12,'title':'','text':text}]}
  lost=[];errors=[]
  for n in range(8):
   doc=json.loads(report()['document']);a,b=doc['sections'][:2];barrier=threading.Barrier(2)
   def save(args):
    c,p=args;barrier.wait();return self.call(c,'chapter/save',p)
   with ThreadPoolExecutor(2) as pool:responses=list(pool.map(save,[(owner,payload(a,'甲写第'+str(n)+'轮')),(writer,payload(b,'乙写第'+str(n)+'轮'))]))
   fresh=json.loads(report()['document'])['sections'][:2]
   texts=[sec['blocks'][0]['text'] if sec['blocks'] else '' for sec in fresh]
   print('不同章节并发',n+1,[r[0] for r in responses],texts,flush=True)
   if any(r[0]!=200 for r in responses):errors.append(responses)
   if texts!=['甲写第'+str(n)+'轮','乙写第'+str(n)+'轮']:lost.append((responses,texts))
  # Same chapter: both clients send the same revision at the same time.
  a=json.loads(report()['document'])['sections'][0];barrier=threading.Barrier(2)
  with ThreadPoolExecutor(2) as pool:responses=list(pool.map(save,[(owner,payload(a,'同章节甲')),(writer,payload(a,'同章节乙'))]))
  print('同章节并发',[(r[0],r[1]) for r in responses],flush=True)
  print('不同章节丢失轮数',len(lost),'失败轮数',len(errors),flush=True)
  self.assertEqual(len(lost),0,'不同章节同时保存丢失修改')
  self.assertEqual(len(errors),0,'不同章节同时保存失败')
  self.assertEqual(sorted(r[0] for r in responses),[200,409],'同章节并发必须拒绝旧版本')
  latest=report();history=self.call(owner,'history/'+str(rid))[1]
  versions=sorted(row['version'] for row in history['versions'])
  self.assertEqual(versions,list(range(1,latest['version']+1)),'并发保存必须保留完整且唯一的版本历史')

def load_tests(loader, tests, pattern):
 return unittest.TestSuite([CollaborationCheck('test_parallel_editing')])

if __name__ == '__main__':
 unittest.main(verbosity=2)
