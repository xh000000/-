"""HTTP acceptance of Skill catalogue -> evidence -> queued model -> review -> report version.
The model is a local simulator; no real credentials, API billing or business database.
"""
import copy
import datetime
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from test_report_creation import ReportCreation

class Model(BaseHTTPRequestHandler):
    mode='ok'; failure_once=False; prompts=[]; started=threading.Event(); release=threading.Event()
    def log_message(self,*args): pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        type(self).prompts.append(data); type(self).started.set()
        if type(self).mode=='delay': type(self).release.wait(8)
        if type(self).mode=='fail-first' and not type(self).failure_once:
            type(self).failure_once=True
            raw=json.dumps({'error':{'message':'temporary upstream failure'}}).encode();self.send_response(500);self.end_headers();self.wfile.write(raw);return
        if type(self).mode=='quota':
            code=429; result={'error':{'message':'insufficient_quota credit_balance_exhausted'}}
        else:
            code=200
            body=('铜未来5天看多，根据证据[D1]观察到价格变化。'+'本段为本地模拟模型生成，用于软件验收，需核对指标日期和研究口径。'*5+
                  '\n数据来源：[D1]，Skill测试源。风险提示：需求、库存及价格变化可能使判断失效。')
            if type(self).mode=='badref': body=body.replace('[D1]','[D999]')
            if type(self).mode in ['viewpoint','viewpoint-bad']:
                body=json.dumps({'items':[{'commodity':'铜','direction':'看多','horizon_days':5,'excerpt':'铜预计未来5天偏强运行，库存下降提供支撑。' if type(self).mode=='viewpoint' else '铜未来上涨百分之十。','basis':'库存变化支持短期偏强判断，仍需关注需求风险。'}]},ensure_ascii=False)
            result={'choices':[{'message':{'content':body},'finish_reason':'stop'}], 'usage':{'total_tokens':50}}
        raw=json.dumps(result,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class SkillReports(ReportCreation):
    @classmethod
    def setUpClass(cls):
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),Model)
        threading.Thread(target=cls.model.serve_forever,daemon=True).start()
        super().setUpClass()
        helper=cls('test_whole_report_review_and_version')
        config=helper.call(cls.admin,'ai/config')[1]
        out=helper.call(cls.admin,'ai/profiles',{'action':'save','name':'Skill模拟模型','revision':config['profile_revision'],'model':'skill-test','base_url':f'http://127.0.0.1:{cls.model.server_port}/v1','api_key':'fake-skill-test-key'})
        helper.assertEqual(out[0],200,out)
        config=helper.call(cls.admin,'ai/config')[1]
        helper.assertEqual(helper.call(cls.admin,'ai/profiles',{'action':'activate','id':next(x['id'] for x in config['profiles'] if x['name']=='Skill模拟模型'),'revision':config['profile_revision']})[0],200)
        helper.assertEqual(helper.call(cls.owner,'import',{'csv':'source,indicator,date,value,unit\nSkill测试源,铜现货价,2026-11-18,100,元/吨'})[0],200)

    @classmethod
    def tearDownClass(cls):
        Model.release.set();super().tearDownClass();cls.model.shutdown();cls.model.server_close()

    def setUp(self):
        Model.mode='ok';Model.started.clear();Model.release.clear()

    def report_fixture(self,**changes):
        import uuid
        cfg=copy.deepcopy(self.cat['config'])
        cfg['commodities']=['铜','原油']
        cfg['sections']=[{'id':'s1','title':'市场分析','required':True,'commodity_ids':[],'default':'先分析库存与价格'},
                         {'id':'s2','title':'风险与来源','required':False,'commodity_ids':[],'default':'区分事实与推断'}]
        out=self.call(self.admin,'categories',{'name':'Skill模板-'+uuid.uuid4().hex[:6],'config':cfg,'enabled':True});self.assertEqual(out[0],200,out)
        return self.create(category_id=out[1]['id'],commodity='铜',**changes)

    def body(self,r,**changes):
        return {'report_id':r['id'],'version':r['version'],'skill_ids':['daily-research'],'section_ids':['s1','s2'],'library_ids':[],**changes}

    def generate_job(self,r,**changes):
        code,out=self.call(self.owner,'report-ai/jobs',self.body(r,**changes));self.assertEqual(code,200,out)
        return out['id']

    def wait_job(self,tid):
        for _ in range(160):
            code,data=self.call(self.owner,'report-ai/jobs/'+tid);self.assertEqual(code,200,data)
            if data['status'] not in ['排队中','运行中']: return data
            time.sleep(.05)
        self.fail('生成任务未完成')

    def test_recent_jobs_are_owned_and_link_to_report(self):
        r=self.report_fixture()
        tid=self.generate_job(r)
        self.wait_job(tid)
        code,data=self.call(self.owner,'report-ai/recent-jobs')
        self.assertEqual(code,200,data)
        item=next(x for x in data['jobs'] if x['id']==tid)
        self.assertEqual(item['report_id'],r['id'])
        self.assertEqual(item['title'],r['title'])
        self.assertTrue(item['editable'])
        other=self.call(self.admin,'report-ai/recent-jobs')[1]
        self.assertNotIn(tid,[x['id'] for x in other['jobs']])

    def test_whole_report_review_and_version(self):
        r=self.report_fixture()
        doc=json.loads(r['document']);doc['sections'][0]['blocks']=[{'id':'old','type':'text','span':12,'title':'','text':'保留测试原文'},
            {'id':'chart','type':'chart','span':12,'title':'铜价格','source':'Skill测试源','indicator':'铜现货价','data':[]}]
        out=self.call(self.owner,'personal-save',{'id':r['id'],'version':r['version'],'document':doc});self.assertEqual(out[0],200,out)
        r=self.report(r['id']);original_chart=json.loads(r['document'])['sections'][0]['blocks'][1]
        preview=self.call(self.owner,'report-ai/preview',self.body(r));self.assertEqual(preview[0],200,preview)
        self.assertEqual(preview[1]['sections'][0]['evidence']['data'][0]['source'],'Skill测试源')
        tid=self.generate_job(r); job=self.wait_job(tid);self.assertEqual(job['status'],'已完成',job)
        self.assertEqual(job['result']['completed'],2)
        self.assertEqual(self.report(r['id'])['version'],r['version'])
        self.assertIn('日度与周度研究写作',Model.prompts[-1]['messages'][0]['content'])
        self.assertEqual(self.call(self.writer,'report-ai/jobs/'+tid)[0],404)
        out=self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':r['version'],'reviewed':False});self.assertEqual(out[0],400,out)
        out=self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':r['version'],'reviewed':True,'mode':'replace'});self.assertEqual(out[0],200,out)
        saved=self.report(r['id']);self.assertEqual(saved['status'],'草稿');self.assertEqual(saved['version'],r['version']+1);self.assertEqual(saved['ai_draft'],1)
        doc=json.loads(saved['document']);self.assertEqual(next(x for x in doc['sections'][0]['blocks'] if x['type']=='chart'),original_chart)
        self.assertNotIn('保留测试原文',saved['body'])
        self.assertIn('铜未来5天看多', saved['body'])
        for generated in job['result']['sections']:
            section=next(x for x in doc['sections'] if x['id']==generated['id'])
            self.assertEqual(next(x['text'] for x in section['blocks'] if x['type']=='text'), generated['body'])
        history=self.call(self.owner,'history/'+str(r['id']))[1]
        self.assertTrue(any(event['action']=='采用 Skill 研报候选' and '日度 / 周度研报@' in event['note'] for event in history['events']))
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':saved['version'],'reviewed':True})[0],400)
        for client,action in [(self.owner,'提交'),(self.clients['create-review'],'通过'),(self.clients['create-compliance'],'通过'),(self.clients['create-publisher'],'发布')]:
            response=self.call(client,'transition',{'id':r['id'],'action':action});self.assertEqual(response[0],200,response)
        self.assertEqual(self.report(r['id'])['status'],'已发布')
        candidates=self.call(self.owner,'viewpoints/candidates')[1]['items']
        self.assertTrue(any(x['report_id']==r['id'] and x['direction']=='看多' for x in candidates))

    def test_skill_snapshots_and_access(self):
        catalog=self.call(self.admin,'report-ai/skills')[1]
        raw='---\nname: copper-special\ndescription: 铜专题写作\n---\n# 铜专属写作方法\n只根据证据包，关注供需反证条件。'
        data={'revision':catalog['revision'],'name':'铜专题Skill','markdown':raw,'enabled':True}
        self.assertEqual(self.call(self.clients['create-review'],'report-ai/skills')[0],200)
        self.assertEqual(self.call(self.client(),'report-ai/skills')[0],401)
        code,out=self.call(self.clients['create-review'],'report-ai/skills',data);self.assertEqual(code,200,out);sid=out['id']
        r=self.report_fixture();tid=self.generate_job(r,skill_ids=[sid]);job=self.wait_job(tid);self.assertEqual(job['status'],'已完成',job)
        original_version=job['result']['skills'][0]['version']
        catalog=self.call(self.admin,'report-ai/skills')[1]
        result=self.call(self.admin,'report-ai/skills',{**data,'id':sid,'revision':catalog['revision'],'markdown':raw+'\n新增方法。','enabled':False});self.assertEqual(result[0],200,result)
        self.assertEqual(self.call(self.owner,'report-ai/jobs/'+tid)[1]['result']['skills'][0]['version'],original_version)
        self.assertEqual(self.call(self.owner,'report-ai/preview',self.body(r,skill_ids=[sid]))[0],400)
        self.assertEqual(self.call(self.admin,'report-ai/skills',data)[0],409)
        self.assertEqual(self.call(self.owner,'report-ai/preview',self.body(r,skill_ids=['../../etc/passwd']))[0],400)

    def test_zip_import_preview_and_reference_use(self):
        import io,zipfile,urllib.request
        stream=io.BytesIO()
        raw='---\nname: zipped-research\ndescription: >\n  铜供需\n  参考资料\n---\n# ZIP 写作方法\n先阅读 references/guide.md。'
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('copper/SKILL.md',raw);z.writestr('copper/references/guide.md','ZIP参考资料验证：库存分析先核对统计口径。')
            z.writestr('copper/scripts/run.py','raise RuntimeError("never run")')
        before=self.call(self.owner,'report-ai/skills')[1]
        req=urllib.request.Request(self.base+'report-ai/skills/inspect-zip',data=stream.getvalue(),headers={'Content-Type':'application/zip'})
        with self.owner.open(req) as response:package=json.load(response)
        self.assertEqual(self.call(self.owner,'report-ai/skills')[1]['revision'],before['revision'])
        self.assertIn('scripts/run.py',package['warnings'][0])
        data={**package,'revision':before['revision'],'enabled':True}
        code,saved=self.call(self.writer,'report-ai/skills',data);self.assertEqual(code,200,saved)
        sid=saved['id'];catalog=self.call(self.owner,'report-ai/skills')[1]
        row=next(x for x in catalog['skills'] if x['id']==sid)
        self.assertIn('references/guide.md',row['resources'])
        # Editing text or toggling status does not discard the imported companion files.
        code,out=self.call(self.writer,'report-ai/skills',{'id':sid,'name':row['name'],'markdown':row['markdown'],'enabled':True,'revision':catalog['revision']})
        self.assertEqual(code,200,out)
        r=self.report_fixture();job=self.wait_job(self.generate_job(r,skill_ids=[sid]));self.assertEqual(job['status'],'已完成',job)
        self.assertIn('ZIP参考资料验证',Model.prompts[-1]['messages'][0]['content'])
        req=urllib.request.Request(self.base+'report-ai/skills/inspect-zip',data=b'bad',headers={'Content-Type':'application/zip'})
        try:self.client().open(req);self.fail('anonymous import permitted')
        except urllib.error.HTTPError as e:self.assertEqual(e.code,401)

    def test_stale_report_and_missing_data(self):
        r=self.report_fixture();tid=self.generate_job(r);self.assertEqual(self.wait_job(tid)['status'],'已完成')
        update=self.call(self.owner,'chapters',{'id':r['id'],'version':r['version'],'section_id':'s1','action':'edit','title':'新标题','editors':[self.ids['create-owner']],'commodity_ids':[]})
        self.assertEqual(update[0],200,update)
        saved=self.report(r['id'])
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':saved['version'],'reviewed':True})[0],409)
        self.assertEqual(self.report(r['id'])['document'],saved['document'])
        before=len(Model.prompts)
        r=self.report_fixture();code,out=self.call(self.owner,'chapters',{'id':r['id'],'version':r['version'],'section_id':'s1','action':'edit','title':'市场','editors':[self.ids['create-owner']],'commodity_ids':[]})
        self.assertEqual(code,200,out)
        # A report marked with another commodity must not silently consume copper data.
        import sqlite3
        with sqlite3.connect(self.tmp.name+'/research.db') as s:s.execute('update reports set commodity=? where id=?',('原油',r['id']))
        r=self.report(r['id']);self.assertEqual(self.call(self.owner,'report-ai/jobs',self.body(r,section_ids=['s1']))[0],400)
        self.assertEqual(len(Model.prompts),before)

    def test_failure_cancel_and_collaboration(self):
        for mode in ['quota','badref']:
            Model.mode=mode;r=self.report_fixture();tid=self.generate_job(r);job=self.wait_job(tid)
            self.assertEqual(job['status'],'失败',job);self.assertEqual(self.report(r['id'])['version'],r['version'])
            self.assertNotIn('fake-skill-test-key',job['error'])
        Model.mode='delay';Model.started.clear();r=self.report_fixture();tid=self.generate_job(r)
        self.assertTrue(Model.started.wait(4));self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/cancel',{})[0],200)
        Model.release.set();job=self.wait_job(tid);self.assertEqual(job['status'],'已取消');self.assertEqual(self.report(r['id'])['version'],r['version'])
        Model.mode='ok'
        r=self.report_fixture(collaboration='shared',collaborators=[self.ids['create-writer']])
        result=self.call(self.owner,'chapters',{'id':r['id'],'version':r['version'],'section_id':'s1','action':'edit','title':'市场分析','editors':[self.ids['create-writer']],'commodity_ids':[]})
        self.assertEqual(result[0],200,result);r=self.report(r['id'])
        self.assertEqual(self.call(self.writer,'report-ai/jobs',self.body(r,section_ids=['s2']))[0],403)
        self.assertEqual(self.call(self.owner,'report-ai/preview',self.body(r,section_ids=['s1']))[0],200)
        result=self.call(self.writer,'report-ai/jobs',self.body(r,section_ids=['s1']));self.assertEqual(result[0],200,result)
        for _ in range(120):
            job=self.call(self.writer,'report-ai/jobs/'+result[1]['id'])[1]
            if job['status'] not in ['运行中','排队中']: break
            time.sleep(.05)
        self.assertEqual(job['status'],'已完成',job)


    def shared_fixture(self):
        r=self.report_fixture(collaboration='shared',collaborators=[self.ids['create-writer']])
        out=self.call(self.owner,'chapters',{'id':r['id'],'version':r['version'],'section_id':'s1','action':'edit','title':'市场分析','editors':[self.ids['create-writer']],'commodity_ids':[]})
        self.assertEqual(out[0],200,out)
        return self.report(r['id'])

    def test_shared_generation_and_independent_confirmation(self):
        from concurrent.futures import ThreadPoolExecutor
        r=self.shared_fixture();Model.mode='delay'
        tid=self.generate_job(r)
        self.assertTrue(Model.started.wait(4))
        self.assertEqual(self.call(self.writer,'report-ai/jobs',self.body(r,section_ids=['s1']))[0],409)
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}/cancel',{})[0],403)
        self.assertEqual(self.call(self.clients['create-outsider'],f'report-ai/jobs/{tid}')[0],404)
        latest=self.call(self.writer,f"report-ai/reports/{r['id']}/latest")[1]
        self.assertEqual(latest['job']['id'],tid)
        self.assertEqual(set(latest['job']['planned_section_ids']),{'s1','s2'})
        self.assertIn(tid,[x['id'] for x in self.call(self.writer,'report-ai/recent-jobs')[1]['jobs']])
        Model.release.set();self.assertEqual(self.wait_job(tid)['status'],'已完成')
        params={'version':r['version'],'reviewed':True}
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/apply',{**params,'section_ids':['s1']})[0],403)
        # A mixed batch must be atomic: a permitted chapter cannot be committed before a forbidden one.
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}/apply',{**params,'section_ids':['s1','s2']})[0],403)
        self.assertEqual(self.report(r['id'])['version'],r['version'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.call,client,f'report-ai/jobs/{tid}/apply',{**params,'section_ids':[sid]}) for client,sid in [(self.writer,'s1'),(self.owner,'s2')]]
            results=[x.result() for x in futures]
        for out in results:self.assertEqual(out[0],200,results)
        job=self.call(self.writer,f'report-ai/jobs/{tid}')[1]
        self.assertEqual(job['status'],'已采用');self.assertEqual(set(job['result']['reviews']),{'s1','s2'})
        saved=self.report(r['id']);self.assertEqual(saved['version'],r['version']+2)
        for client,sid in [(self.writer,'s1'),(self.owner,'s2')]:
            sec=next(x for x in json.loads(self.report(r['id'])['document'])['sections'] if x['id']==sid)
            out=self.call(client,'chapter/submit',{'id':r['id'],'section_id':sid,'revision':sec['revision']});self.assertEqual(out[0],200,out)
        for client,action in [(self.owner,'提交'),(self.clients['create-review'],'通过'),(self.clients['create-compliance'],'通过'),(self.clients['create-publisher'],'发布')]:
            out=self.call(client,'transition',{'id':r['id'],'action':action});self.assertEqual(out[0],200,out)
        self.assertEqual(self.report(r['id'])['status'],'已发布')

    def test_shared_conflict_skip_and_submission_guard(self):
        r=self.shared_fixture();tid=self.generate_job(r);self.wait_job(tid)
        sec=next(x for x in json.loads(r['document'])['sections'] if x['id']=='s1')
        out=self.call(self.writer,'chapter/save',{'id':r['id'],'section_id':'s1','revision':sec['revision'],'blocks':[{'id':'manual-text','type':'text','span':12,'text':'负责人手工修订，不能被旧候选覆盖。'}]})
        self.assertEqual(out[0],200,out)
        saved=self.report(r['id']);sec=next(x for x in json.loads(saved['document'])['sections'] if x['id']=='s1')
        out=self.call(self.writer,'chapter/submit',{'id':r['id'],'section_id':'s1','revision':sec['revision']});self.assertEqual(out[0],400,out);self.assertIn('AI 候选',out[1]['error'])
        params={'version':saved['version'],'reviewed':True,'section_ids':['s1']}
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}/apply',params)[0],409)
        self.assertEqual(self.call(self.writer,'report-ai/jobs',self.body(saved,section_ids=['s1']))[0],409)
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}/apply',{**params,'decision':'skip'})[0],200)
        self.assertEqual(self.report(r['id'])['document'],saved['document'])
        out=self.call(self.writer,'chapter/submit',{'id':r['id'],'section_id':'s1','revision':sec['revision']});self.assertEqual(out[0],200,out)
        self.assertEqual(self.call(self.owner,'transition',{'id':r['id'],'action':'提交'})[0],400)


    def test_shared_private_evidence_and_revoked_membership(self):
        import sqlite3
        r=self.shared_fixture()
        with sqlite3.connect(self.tmp.name+'/research.db') as conn:
            cur=conn.execute("insert into library_items(area,kind,name,owner,body,deleted) values(?,?,?,?,?,0)",('cloud','document','个人私密资料',self.ids['create-owner'],'不可共享的个人资料'))
            private_id=cur.lastrowid
        out=self.call(self.owner,'report-ai/preview',self.body(r,library_ids=[private_id]))
        self.assertEqual(out[0],400,out);self.assertIn('个人云盘',out[1]['error'])
        tid=self.generate_job(r);self.wait_job(tid)
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}')[0],200)
        md=json.loads(r['metadata']);md['collaborators']=[]
        with sqlite3.connect(self.tmp.name+'/research.db') as conn:
            conn.execute('update reports set metadata=? where id=?',(json.dumps(md),r['id']))
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}')[0],404)
        self.assertNotIn(tid,[x['id'] for x in self.call(self.writer,'report-ai/recent-jobs')[1]['jobs']])


    def test_batch_chapter_assignments_atomic_and_versioned(self):
        r=self.report_fixture(collaboration='shared',collaborators=[self.ids['create-writer']])
        writer=self.ids['create-writer'];owner=self.ids['create-owner']
        payload={'id':r['id'],'version':r['version'],'action':'assign','assignments':[{'section_id':'s1','editors':[writer]},{'section_id':'s2','editors':[owner,writer]}]}
        self.assertEqual(self.call(self.writer,'chapters',payload)[0],403)
        bad=copy.deepcopy(payload);bad['assignments'][1]['editors']=[self.ids['create-outsider']]
        self.assertEqual(self.call(self.owner,'chapters',bad)[0],400)
        self.assertEqual(self.report(r['id'])['document'],r['document'])
        out=self.call(self.owner,'chapters',payload);self.assertEqual(out[0],200,out)
        saved=self.report(r['id']);self.assertEqual(saved['version'],r['version']+1)
        previous={x['id']:x for x in json.loads(r['document'])['sections']}
        for chapter in json.loads(saved['document'])['sections']:
            self.assertEqual(chapter['blocks'],previous[chapter['id']]['blocks'])
            self.assertEqual(chapter['revision'],previous[chapter['id']]['revision']+1)
        self.assertEqual(self.call(self.owner,'chapters',payload)[0],409)
        payload['version']=saved['version'];out=self.call(self.owner,'chapters',payload)
        self.assertEqual(out[0],200,out);self.assertFalse(out[1]['changed'])
        self.assertEqual(self.report(r['id'])['version'],saved['version'])
        sec=json.loads(saved['document'])['sections'][0]
        out=self.call(self.writer,'chapter/save',{'id':r['id'],'section_id':'s1','revision':sec['revision'],'blocks':[{'id':'batch-test','type':'text','span':12,'text':'已确认的研究正文'}]});self.assertEqual(out[0],200,out)
        sec=json.loads(self.report(r['id'])['document'])['sections'][0]
        self.assertEqual(self.call(self.writer,'chapter/submit',{'id':r['id'],'section_id':'s1','revision':sec['revision']})[0],200)
        locked=self.report(r['id']);payload['version']=locked['version'];payload['assignments']=[{'section_id':'s2','editors':[owner]},{'section_id':'s1','editors':[owner]}]
        self.assertEqual(self.call(self.owner,'chapters',payload)[0],400)
        self.assertEqual(self.report(r['id'])['document'],locked['document'])


    def test_creation_with_initial_assignments_and_rollback(self):
        writer=self.ids['create-writer'];owner=self.ids['create-owner']
        assignments=[{'section_id':'s1','editors':[writer]},{'section_id':'s2','editors':[owner,writer]}]
        r=self.report_fixture(collaboration='shared',collaborators=[writer],section_assignments=assignments)
        self.assertEqual(r['version'],1)
        doc=json.loads(r['document']);self.assertEqual([x['editors'] for x in doc['sections']],[[writer],[owner,writer]])
        self.assertTrue(all(x['revision']==1 for x in doc['sections']))
        history=self.call(self.owner,'history/'+str(r['id']))[1]
        self.assertEqual(json.loads(history['versions'][0]['document'])['sections'][0]['editors'],[writer])
        count=len(self.call(self.owner,'state')[1]['reports'])
        data={**self.creation_payload,'category_id':r['category_id'],'commodity':'铜','collaboration':'shared','collaborators':[writer]}
        for bad in [[{'section_id':'s1','editors':[writer]}],
                    [{'section_id':'s1','editors':[writer]},{'section_id':'s2','editors':[self.ids['create-outsider']]}],
                    [{'section_id':'s1','editors':[]},{'section_id':'s2','editors':[owner]}]]:
            out=self.call(self.owner,'reports',{**data,'section_assignments':bad});self.assertEqual(out[0],400,out)
            self.assertEqual(len(self.call(self.owner,'state')[1]['reports']),count)
        # Inheritance uses the source snapshot rather than the latest category's chapter IDs.
        import sqlite3
        with sqlite3.connect(self.tmp.name+'/research.db') as conn:conn.execute("update reports set status='已发布' where id=?",(r['id'],))
        out=self.call(self.owner,'reports',{**data,'inherit_id':r['id'],'section_assignments':assignments})
        self.assertEqual(out[0],200,out)
        inherited=self.report(out[1]['id']);self.assertEqual(json.loads(inherited['document'])['sections'][0]['editors'],[writer])


    def test_ai_viewpoint_extraction_source_validation_and_dedup(self):
        import sqlite3
        for mode,day in [('viewpoint','2040-01-01'),('viewpoint-bad','2040-01-02')]:
            Model.mode=mode;r=self.report_fixture();text='铜预计未来5天偏强运行，库存下降提供支撑。'
            with sqlite3.connect(self.tmp.name+'/research.db') as conn:
                conn.execute("update reports set status='已发布' where id=?",(r['id'],))
                conn.execute('insert into publication_history(report_id,version,document,config,metadata,body,published_at) values(?,?,?,?,?,?,?)',(r['id'],r['version'],r['document'],r['config_snapshot'],r['metadata'],text,day+' 12:00:00 UTC'))
            params={'start_date':day,'end_date':day,'method':'ai'}
            out=self.call(self.owner,'viewpoints/extract',params);self.assertEqual(out[0],200,out);self.assertIn('task_id',out[1])
            for _ in range(200):
                job=self.call(self.owner,'viewpoints/extraction-job')[1]['job']
                if job['status'] not in ['排队中','运行中']:break
                time.sleep(.03)
            rows=[x for x in self.call(self.owner,'viewpoints/candidates')[1]['items'] if x['report_id']==r['id']]
            if mode=='viewpoint':
                self.assertEqual(job['status'],'已完成',job);self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['source_method'],'ai');self.assertEqual(rows[0]['draft_basis'],'库存变化支持短期偏强判断，仍需关注需求风险。')
                self.assertIn(rows[0]['excerpt'],text)
                before=len(Model.prompts);self.assertEqual(self.call(self.owner,'viewpoints/extract',params)[1]['added'],0);self.assertEqual(len(Model.prompts),before)
                self.assertIsNone(self.call(self.writer,'viewpoints/extraction-job')[1]['job'])
            else:
                self.assertEqual(job['status'],'失败',job);self.assertEqual(rows,[]);self.assertNotIn('fake-skill-test-key',job['error'])


    def test_retry_preserves_successful_chapter_and_checks_conflicts(self):
        Model.mode='fail-first';Model.failure_once=False;r=self.report_fixture();before=len(Model.prompts)
        tid=self.generate_job(r);failed=self.wait_job(tid)
        self.assertEqual(failed['status'],'失败',failed);self.assertEqual(failed['result']['completed'],1,failed)
        preserved=copy.deepcopy(failed['result']['sections'][0]);self.assertTrue(failed['can_retry'])
        self.assertEqual(len(Model.prompts)-before,2)
        self.assertEqual(self.call(self.writer,f'report-ai/jobs/{tid}/retry',{})[0],404)
        Model.mode='ok';before=len(Model.prompts)
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/retry',{})[0],200)
        done=self.wait_job(tid);self.assertEqual(done['status'],'已完成',done)
        self.assertEqual(len(Model.prompts)-before,1);self.assertIn(preserved,done['result']['sections']);self.assertEqual(done['result']['completed'],2)
        self.assertEqual(self.report(r['id'])['version'],r['version'])
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':r['version'],'reviewed':True})[0],200)
        Model.mode='quota';r=self.report_fixture();tid=self.generate_job(r);self.wait_job(tid)
        self.assertEqual(self.call(self.owner,'chapters',{'id':r['id'],'version':r['version'],'section_id':'s1','action':'edit','title':'已修改章节','editors':[self.ids['create-owner']],'commodity_ids':[]})[0],200)
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/retry',{})[0],409)


    def test_evidence_checks_units_sources_and_future_material(self):
        r=self.report_fixture()
        csv='source,indicator,date,value,unit\n口径A,铜检验价,2026-11-18,100,元/吨\n口径A,铜检验价,2026-11-17,2,美元/吨\n口径B,铜检验价,2026-11-18,150,元/吨'
        self.assertEqual(self.call(self.owner,'import',{'csv':csv})[0],200)
        import sqlite3
        with sqlite3.connect(self.tmp.name+'/research.db') as conn:
            cur=conn.execute('insert into library_items(area,kind,name,owner,body,deleted,updated) values(?,?,?,?,?,0,?)',('docs','document','未来资料',self.ids['create-owner'],'未来才知道的信息','2099-01-01'));mid=cur.lastrowid
        code,data=self.call(self.owner,'report-ai/preview',self.body(r,library_ids=[mid]));self.assertEqual(code,200,data)
        for section in data['sections']:
            evidence=section['evidence'];self.assertEqual(evidence['materials'],[])
            self.assertTrue(any('更新晚于' in x for x in evidence['warnings']))
            self.assertTrue(any('多个单位' in x for x in evidence['warnings']))
            self.assertTrue(any('不同来源数值' in x for x in evidence['warnings']))


    def test_chat_candidate_uses_shared_apply_path(self):
        import os,subprocess,sys
        from pathlib import Path
        r=self.report_fixture();content='铜未来5天偏强，需结合平台数据核对，并关注需求不及预期的风险。'
        script="from agent.tools import _save_chapter_draft; print(_save_chapter_draft(%r)(%r,'s1',%r))" % ({'id':self.ids['create-owner'],'name':'create-owner','role':'researcher'},r['id'],content)
        proc=subprocess.run([sys.executable,'-c',script],env={**os.environ,'DATA_DIR':self.tmp.name,'SKIP_DOTENV':'1','PYTHONPATH':str(Path(__file__).parent)},capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads(proc.stdout.strip().splitlines()[-1]);self.assertTrue(result.get('ok'),result)
        unchanged=self.report(r['id']);self.assertEqual(unchanged['version'],r['version']);self.assertEqual(unchanged['document'],r['document'])
        tid=result['task_id'];job=self.call(self.owner,f'report-ai/jobs/{tid}')[1];self.assertEqual(job['status'],'已完成')
        self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':r['version'],'reviewed':True})[0],200)
        self.assertIn(content,self.report(r['id'])['body']);self.assertEqual(self.report(r['id'])['status'],'草稿')

    def test_shared_failed_candidate_can_be_discarded_and_retried(self):
        r=self.shared_fixture();Model.mode='fail-first';Model.failure_once=False
        tid=self.generate_job(r);failed=self.wait_job(tid);self.assertEqual(failed['status'],'失败')
        sid=failed['result']['sections'][0]['id'];self.assertEqual(sid,'s2')
        out=self.call(self.owner,f'report-ai/jobs/{tid}/apply',{'version':r['version'],'reviewed':True,'section_ids':[sid],'decision':'skip'})
        self.assertEqual(out[0],200,out);self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}')[1]['status'],'失败')
        Model.mode='ok';self.assertEqual(self.call(self.owner,f'report-ai/jobs/{tid}/retry',{})[0],200)
        done=self.wait_job(tid);self.assertEqual(done['status'],'已完成',done);self.assertEqual(done['result']['reviews'][sid]['decision'],'skip')


def load_tests(loader,tests,pattern):
    return unittest.TestSuite(SkillReports(x) for x in ['test_recent_jobs_are_owned_and_link_to_report','test_zip_import_preview_and_reference_use','test_whole_report_review_and_version','test_skill_snapshots_and_access','test_stale_report_and_missing_data','test_failure_cancel_and_collaboration','test_shared_generation_and_independent_confirmation','test_shared_conflict_skip_and_submission_guard','test_shared_private_evidence_and_revoked_membership','test_batch_chapter_assignments_atomic_and_versioned','test_creation_with_initial_assignments_and_rollback','test_ai_viewpoint_extraction_source_validation_and_dedup','test_retry_preserves_successful_chapter_and_checks_conflicts','test_evidence_checks_units_sources_and_future_material','test_chat_candidate_uses_shared_apply_path','test_shared_failed_candidate_can_be_discarded_and_retried'])

if __name__=='__main__':unittest.main(verbosity=2)
