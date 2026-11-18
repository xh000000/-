import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from test_workflow import Workflow

class Upstream(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args):pass
    def send(self,data,status=200):
        body=json.dumps(data).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        self.calls.append(('GET',self.path,self.headers.get('Authorization')))
        if self.path.startswith('/echo-error/'):
            self.send({'error':{'message':'invalid key: '+self.headers.get('Authorization','')}},401)
        elif self.path.startswith('/no-models/'):
            self.send({'error':{'message':'models not supported'}},404)
        else:self.send({'data':[{'id':'model-a'},{'id':'model-b'}]})
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(('POST',self.path,self.headers.get('Authorization'),data))
        self.send({'choices':[{'message':{'content':'这是一段接口验证用的候选正文。'},'finish_reason':'stop'}],'usage':{'total_tokens':8}})

class AIProfiles(Workflow):
    @classmethod
    def setUpClass(cls):
        cls.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        threading.Thread(target=cls.upstream.serve_forever,daemon=True).start()
        cls.upstream_base='http://127.0.0.1:'+str(cls.upstream.server_port)
        with patch.dict(os.environ,{'AI_PROVIDER':'openai','AI_API_KEY':'','AI_MODEL':'','AI_BASE_URL':cls.upstream_base}):
            super().setUpClass()
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass();cls.upstream.shutdown();cls.upstream.server_close()

    def test_profiles_switch_and_isolation(self):
        a=self.client();self.assertEqual(self.call(a,'setup',{'name':'admin','password':'123456'})[0],200)
        self.assertEqual(self.call(a,'ai/config',{'base_url':self.upstream_base+'/legacy','model':'legacy-model','api_key':'fake-legacy-key'})[0],200)
        normal=self.client();self.call(a,'users',{'name':'normal-ai','role':'researcher','password':'123456'});self.call(normal,'login',{'name':'normal-ai','password':'123456'})
        self.assertEqual(self.call(normal,'ai/config')[0],403)
        self.assertEqual(self.call(normal,'ai/profiles',{'action':'save'})[0],403)
        self.assertEqual(self.call(self.client(),'ai/profiles',{})[0],401)
        def config():return self.call(a,'ai/config')[1]
        def action(kind,**fields):
            return self.call(a,'ai/profiles',{'action':kind,'revision':config()['profile_revision'],**fields})
        initial=config();self.assertEqual(initial['active_profile_id'],'legacy');self.assertEqual(initial['model'],'legacy-model')
        self.assertEqual(action('save',name='日常写作',base_url=self.upstream_base+'/a',model='model-a',api_key='fake-key-a')[0],200)
        pa=next(p for p in config()['profiles'] if p['name']=='日常写作');self.assertEqual(config()['active_profile_id'],'legacy')
        self.assertEqual(action('save',name='深度分析',base_url=self.upstream_base+'/b',model='model-b',api_key='fake-key-b')[0],200)
        pb=next(p for p in config()['profiles'] if p['name']=='深度分析')
        for key in ['fake-legacy-key','fake-key-a','fake-key-b']:
            self.assertNotIn(key,json.dumps(config()))
        # Enable exactly one profile; normal /state reflects the same active model.
        self.assertEqual(action('activate',id=pa['id'])[0],200)
        self.assertEqual(config()['active_profile_id'],pa['id']);self.assertEqual(self.call(normal,'state')[1]['model'],'model-a')
        # Editing another profile and testing it do not switch the active configuration.
        self.assertEqual(action('save',id=pb['id'],name='深度分析',base_url=self.upstream_base+'/b',model='model-b')[0],200)
        tested=self.call(a,'ai/test',{'profile_id':pb['id'],'base_url':pb['base_url'],'model':pb['model']})[1]
        self.assertTrue(tested['ok'],tested);self.assertEqual(config()['active_profile_id'],pa['id'])
        self.assertEqual(Upstream.calls[-1][2],'Bearer fake-key-b')
        calls_before=len(Upstream.calls)
        for payload in [dict(profile_id='',base_url=self.upstream_base+'/new',model='model-new'),dict(profile_id=pa['id'],base_url=self.upstream_base+'/other',model='model-a')]:
            self.assertFalse(self.call(a,'ai/test',payload)[1]['ok'])
        self.assertEqual(len(Upstream.calls),calls_before,'不能向另一个地址泄露已保存的密钥')
        self.assertEqual(action('save',id=pa['id'],name='错误修改',base_url=self.upstream_base+'/other',model='model-a')[0],400)
        self.assertEqual(action('delete',id=pa['id'])[0],400)
        stale=config()['profile_revision']
        self.assertEqual(action('activate',id=pb['id'])[0],200)
        self.assertEqual(self.call(a,'ai/profiles',{'action':'activate','id':pa['id'],'revision':stale})[0],409)
        # Generation must use the selected model, URL and credential as a matched set.
        st=self.call(a,'state')[1];cat=next(c for c in st['categories'] if not c['folder'])
        self.assertEqual(self.call(a,'import',{'csv':'source,indicator,date,value,unit\n测试数据,铜收盘价,2026-11-18,100,元/吨'})[0],200)
        status,new=self.call(a,'reports',{'category_id':cat['id'],'commodity':'铜','title':'模型切换验证'})
        self.assertEqual(status,200,new)
        report=next(r for r in self.call(a,'state')[1]['reports'] if r['id']==new['id'])
        section=json.loads(report['document'])['sections'][0]
        response=self.call(a,'generate',{'id':report['id'],'section_id':section['id']})
        self.assertEqual(response[0],200,response);self.assertEqual(response[1]['model'],'model-b')
        call=Upstream.calls[-1];self.assertEqual(call[1],'/b/chat/completions');self.assertEqual(call[2],'Bearer fake-key-b');self.assertEqual(call[3]['model'],'model-b')
        # A provider without /models can still test a manually specified model.
        result=self.call(a,'ai/test',{'profile_id':'','base_url':self.upstream_base+'/no-models','model':'model-a','api_key':'fake-manual-key'})[1]
        self.assertTrue(result['ok'],result)
        echo=self.call(a,'ai/test',{'profile_id':'','base_url':self.upstream_base+'/echo-error','model':'','api_key':'fake-echo-key'})[1]
        self.assertFalse(echo['ok']);self.assertNotIn('fake-echo-key',echo['message'])
        self.assertEqual(self.call(a,'ai/config',{'model':'should-not-save','base_url':'invalid-url'})[0],400)
        self.assertEqual(next(p for p in config()['profiles'] if p['id']=='legacy')['model'],'legacy-model')
        self.assertEqual(action('activate',id='legacy')[0],200);self.assertEqual(config()['model'],'legacy-model')
        self.assertEqual(action('delete',id=pa['id'])[0],200)
        other=self.client();self.call(other,'login',{'name':'admin','password':'123456'})
        self.assertEqual(self.call(other,'ai/config')[1]['active_profile_id'],'legacy')
        self.assertNotIn(pa['id'],[p['id'] for p in config()['profiles']])


def load_tests(loader,tests,pattern):return unittest.TestSuite([AIProfiles('test_profiles_switch_and_isolation')])
if __name__=='__main__':unittest.main(verbosity=2)
