"""Full acceptance chain with a real local HTTP model simulator and isolated DB."""
import contextlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from test_workflow import Workflow

class ModelSimulator(BaseHTTPRequestHandler):
    requests=[]
    def log_message(self,*args):pass
    def respond(self,body,status=200):
        raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.respond({'data':[{'id':'workflow-test-model'}]})
    def do_POST(self):
        request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path!='/v1/chat/completions' or request.get('model')!='workflow-test-model' or self.headers.get('Authorization')!='Bearer workflow-test-key':
            self.respond({'error':{'message':'unexpected test model configuration'}},400);return
        prompt='\n'.join(message.get('content','') for message in request.get('messages',[]))
        if '验收测试源' not in prompt:
            self.respond({'error':{'message':'test evidence is missing'}},400);return
        match=re.search(r'本章：([^\n]+)',prompt);chapter=match.group(1).strip() if match else '测试章节'
        content=(f'【模拟接口验收内容】本章对应“{chapter}”。\n'
                 '本段由本地模拟模型接口返回，用于验证从候选内容生成、人工确认保存，到审批发布的系统链路。'
                 '验收样本取自独立测试库，记录日期为2026-11-18，样本值为100测试单位。\n'
                 '数据来源：验收测试源，2026-11-18，模拟测试数据，不代表真实行情。\n'
                 '风险提示：以上文字及数字仅用于软件验收，不构成研究结论、投资建议或真实合规审批结果。'
                 '必须核对候选内容、保存版本和审核留痕是否一致，不能把本次测试报告用于业务发布。')
        self.requests.append({'chapter':chapter,'model':request['model'],'body':content,'evidence_received':True})
        self.respond({'choices':[{'message':{'content':content},'finish_reason':'stop'}],
                      'usage':{'prompt_tokens':100,'completion_tokens':160,'total_tokens':260}})

class FullWorkflow(Workflow):
    @classmethod
    def setUpClass(cls):
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),ModelSimulator);ModelSimulator.requests=[]
        threading.Thread(target=cls.model.serve_forever,daemon=True).start()
        with patch.dict(os.environ,{'AI_PROVIDER':'openai','AI_API_KEY':'','AI_MODEL':''}):
            super().setUpClass()
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass();cls.model.shutdown();cls.model.server_close()

    def test_generated_report_to_published(self):
        admin=self.client();self.assertEqual(self.call(admin,'setup',{'name':'验收管理员','password':'test-admin-123'})[0],200)
        clients={}
        roles=[('验收作者','researcher'),('验收复核','reviewer'),('验收合规','compliance'),('验收发布','publisher'),('验收观察者','researcher')]
        for name,role in roles:
            result=self.call(admin,'users',{'name':name,'role':role,'password':'test-user-123'})
            self.assertEqual(result[0],200,result)
            client=self.client();self.assertEqual(self.call(client,'login',{'name':name,'password':'test-user-123'})[0],200);clients[name]=client
        author,reviewer,compliance,publisher=[clients[name] for name in ['验收作者','验收复核','验收合规','验收发布']]
        state=self.call(admin,'state')[1];ids={user['name']:user['id'] for user in state['users']}
        category=next(cat for cat in state['categories'] if not cat['folder'] and cat['config']['kind']=='专题')
        byline=next(person for person in state['authors'] if person['enabled'] and '专题' in json.loads(person['types']))
        profile={'action':'save','revision':0,'name':'完整流程验收模型（模拟）','model':'workflow-test-model',
                 'base_url':f'http://127.0.0.1:{self.model.server_port}/v1','api_key':'workflow-test-key'}
        result=self.call(admin,'ai/profiles',profile);self.assertEqual(result[0],200,result)
        model_config=self.call(admin,'ai/config')[1];saved=next(p for p in model_config['profiles'] if p['name']==profile['name'])
        result=self.call(admin,'ai/profiles',{'action':'activate','id':saved['id'],'revision':model_config['profile_revision']});self.assertEqual(result[0],200,result)
        nodes=[{'label':'研究复核','role':'reviewer','mode':'any','users':[ids['验收复核']]},
               {'label':'合规审核','role':'compliance','mode':'any','users':[ids['验收合规']]}]
        result=self.call(admin,'approval-flows',{'name':'完整链路验收流程','category_ids':[category['id']],'nodes':nodes});self.assertEqual(result[0],200,result)
        csv='source,indicator,date,value,unit\n验收测试源,综合验收样本,2026-11-18,100,测试单位'
        self.assertEqual(self.call(author,'import',{'csv':csv})[0],200)
        title='【模拟接口全流程验收】研报生成与审批发布（2026-11-18）'
        result=self.call(author,'reports',{'manual':True,'category_id':category['id'],'title':title,
              'summary':'独立测试库的模拟模型全流程验收报告','byline_id':byline['id'],'commodity':'综合',
              'report_date':'2026-11-18','collaboration':'personal','layout':'flow','public':True})
        self.assertEqual(result[0],200,result);rid=result[1]['id']
        def report(client=author):return next(r for r in self.call(client,'state')[1]['reports'] if r['id']==rid)
        checkpoints=[]
        def checkpoint(stage,actor):
            r=report();checkpoints.append({'stage':stage,'actor':actor,'status':r['status'],'version':r['version'],'workflow':json.loads(r['workflow_state'])})
            print(stage,actor,r['status'],'v'+str(r['version']),flush=True);return r
        r=checkpoint('创建报告','验收作者');doc=json.loads(r['document']);generated=[]
        self.assertEqual(json.loads(r['config_snapshot'])['workflow'],nodes)
        # Every chapter is generated through /api/generate and the selected HTTP model.
        for section in doc['sections']:
            response=self.call(author,'generate',{'id':rid,'section_id':section['id']})
            self.assertEqual(response[0],200,response);draft=response[1]
            self.assertEqual(draft['model'],'workflow-test-model');self.assertIn('模拟接口验收内容',draft['body'])
            self.assertGreater(len(draft['body']),100)
            section['blocks']=[{'id':'generated-'+section['id'],'type':'text','span':12,'title':'','text':draft['body']}]
            generated.append({'chapter':section['title'],'characters':len(draft['body']),'model':draft['model']})
            print('生成章节',section['title'],len(draft['body']),'字',flush=True)
        self.assertEqual(len(ModelSimulator.requests),len(doc['sections']))
        self.assertTrue(all(not s['blocks'] for s in json.loads(report()['document'])['sections']),'候选内容未经确认不得自动覆盖研报')
        # Simulate the author's explicit adoption and save of all generated chapters.
        response=self.call(author,'personal-save',{'id':rid,'version':r['version'],'document':doc});self.assertEqual(response[0],200,response)
        r=checkpoint('确认候选并保存全文','验收作者')
        self.assertEqual(r['version'],2)
        for section,request in zip(json.loads(r['document'])['sections'],ModelSimulator.requests):self.assertEqual(section['blocks'][0]['text'],request['body'])
        check=self.call(author,'check',{'id':rid});self.assertEqual(check[0],200)
        blockers=[item for item in check[1]['checks'] if item['level']=='阻断'];self.assertEqual(blockers,[])
        checkpoint('提交前规则检查通过','系统')
        def act(client,actor,action,expected):
            current=report();response=self.call(client,'transition',{'id':rid,'action':action,
                    'expected_status':current['status'],'expected_workflow':current['workflow_state']})
            self.assertEqual(response[0],200,response);r=checkpoint(action,actor);self.assertEqual(r['status'],expected)
        act(author,'验收作者','提交','研究复核')
        self.assertIn('通过',report(reviewer)['allowed_actions']);self.assertNotIn('通过',report(author)['allowed_actions'])
        response=self.call(author,'personal-save',{'id':rid,'version':r['version'],'document':doc});self.assertEqual(response[0],403)
        self.assertEqual(self.call(publisher,'transition',{'id':rid,'action':'发布'})[0],403)
        act(reviewer,'验收复核','通过','合规审核')
        self.assertIn('通过',report(compliance)['allowed_actions'])
        act(compliance,'验收合规','通过','待发布')
        self.assertTrue(report()['approved_at']);self.assertIn('发布',report(publisher)['allowed_actions'])
        act(publisher,'验收发布','发布','已发布')
        final=report();self.assertTrue(final['published_at']);self.assertEqual(final['allowed_actions'],[])
        self.assertEqual(json.loads(final['workflow_state']),{'index':2,'approvals':[]})
        self.assertEqual(self.call(publisher,'transition',{'id':rid,'action':'发布'})[0],403)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],403)
        self.assertEqual(self.call(author,'personal-save',{'id':rid,'version':final['version'],'document':doc})[0],403)
        history=self.call(author,'history/'+str(rid))[1]
        self.assertEqual(len(history['versions']),2)
        events=history['events'];approvals=[event for event in events if event['action'] in ['提交','通过','发布']]
        self.assertEqual([(e['actor'],e['action']) for e in sorted(approvals,key=lambda x:x['id'])],
                         [('验收作者','提交'),('验收复核','通过'),('验收合规','通过'),('验收发布','发布')])
        self.assertEqual(sum(e['action']=='生成AI候选草稿' for e in events),len(doc['sections']))
        with contextlib.closing(sqlite3.connect(Path(self.tmp.name)/'research.db')) as db:
            db.row_factory=sqlite3.Row;publications=db.execute('select * from publication_history where report_id=?',(rid,)).fetchall()
        self.assertEqual(len(publications),1);self.assertEqual(publications[0]['version'],2)
        self.assertEqual(json.loads(publications[0]['document']),json.loads(final['document']))
        self.assertEqual(report(clients['验收观察者'])['status'],'已发布')
        code,html=self.raw(author,'report-print/'+str(rid));self.assertEqual(code,200);self.assertIn(title.encode(),html);self.assertIn('模拟接口验收内容'.encode(),html)
        output=os.getenv('WORKFLOW_TEST_OUTPUT')
        summary={'simulation':True,'title':title,'final_status':final['status'],'version':final['version'],
                 'chapters':generated,'model_calls':len(ModelSimulator.requests),'checkpoints':checkpoints,
                 'approval_events':[{'actor':e['actor'],'action':e['action'],'at':e['at'],'version':e['version']} for e in sorted(approvals,key=lambda x:x['id'])],
                 'publication_snapshots':1,'saved_versions':2,'blockers':0,'published_at':final['published_at']}
        if output:
            folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
            (folder/'full-workflow-result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            (folder/'mock-generated-report.html').write_bytes(html)
        print('完整流程验收通过：',len(generated),'章，最终已发布，唯一发布定稿与全文一致',flush=True)


def load_tests(loader,tests,pattern):return unittest.TestSuite([FullWorkflow('test_generated_report_to_published')])
if __name__=='__main__':unittest.main(verbosity=2)
