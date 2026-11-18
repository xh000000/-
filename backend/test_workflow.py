import unittest, tempfile, subprocess, os, sys, time, json, urllib.request, urllib.error, http.cookiejar, socket
from pathlib import Path

class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        with socket.socket() as s:s.bind(('127.0.0.1',0)); cls.port=s.getsockname()[1]
        cls.proc=subprocess.Popen([sys.executable,str(Path(__file__).with_name('server.py'))],env={**os.environ,'DATA_DIR':cls.tmp.name,'PORT':str(cls.port)},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.base=f'http://127.0.0.1:{cls.port}/api/'
        for _ in range(100):
            try:urllib.request.urlopen(cls.base+'bootstrap',timeout=1);break
            except Exception:time.sleep(.05)
    @classmethod
    def tearDownClass(cls):cls.proc.terminate();cls.proc.wait();cls.tmp.cleanup()
    def client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def ensure_blocks(self,doc,text=''):
        """新报告章节不再自带空文字块；测试要写字时先补一个，避免依赖编辑器的默认组件。"""
        for s in doc['sections']:
            if not s['blocks']:s['blocks'].append({'id':'blk-'+s['id'],'type':'text','span':12,'title':'','text':text})
        return doc
    def call(self,c,path,data=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        try:
            with c.open(req) as res:return res.status,json.load(res)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def raw(self,c,path):
        try:
            with c.open(self.base+path) as res:return res.status,res.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
    def test_end_to_end(self):
        a=self.client();pw='123456'
        self.assertEqual(self.call(a,'state')[0],401)
        self.assertEqual(self.call(a,'setup',{'name':'admin','password':pw})[0],200)
        self.assertEqual(self.call(a,'setup',{'name':'other','password':pw})[0],403)
        users={}
        for role in ['researcher','reviewer','compliance','publisher']:
            self.assertEqual(self.call(a,'users',{'name':role,'role':role,'password':pw})[0],200)
            users[role]=self.client();self.assertEqual(self.call(users[role],'login',{'name':role,'password':pw})[0],200)
        author=users['researcher']
        bad='source,indicator,date,value,unit\nWind,test,2026-11-16,1,t\nWind,test,broken,2,t'
        self.assertEqual(self.call(author,'import',{'csv':bad})[0],400)
        self.assertEqual(len(self.call(author,'state')[1]['data']),0)
        self.assertEqual(self.call(author,'import',{'csv':'source,indicator,date,value,unit\nWind,test,2026-11-16,10,t'})[0],200)
        rid=self.call(author,'reports',{'title':'铜周报','commodity':'铜','kind':'周报'})[1]['id']
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],400)
        body='研究分析与观点：'+('本段为测试正文，依据已导入数据核实供需变化。'*10)+'\n风险提示：需求变化。\n数据来源：Wind，2026-11-16。'
        save={'id':rid,'version':1,'title':'铜周报','body':body}
        self.assertEqual(self.call(author,'save',save)[0],200)
        self.assertEqual(self.call(author,'save',save)[0],409)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],200)
        self.assertEqual(self.call(author,'save',{**save,'version':2})[0],403)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'通过'})[0],403)
        self.assertEqual(self.call(users['publisher'],'transition',{'id':rid,'action':'发布'})[0],403)
        self.assertEqual(self.call(users['reviewer'],'transition',{'id':rid,'action':'退回','note':'完善论证'})[0],200)
        self.assertEqual(self.call(author,'save',{**save,'version':2})[0],200)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],200)
        for role,action in [('reviewer','通过'),('compliance','通过'),('publisher','发布')]:self.assertEqual(self.call(users[role],'transition',{'id':rid,'action':action})[0],200)
        st=self.call(author,'state')[1];self.assertEqual(st['reports'][0]['status'],'已发布')
        self.assertEqual(self.call(author,'save',{**save,'version':3})[0],403)
        history=self.call(author,'history/'+str(rid))[1];self.assertEqual(len(history['versions']),3);self.assertGreaterEqual(len(history['events']),9)
        self.assertEqual(self.call(users['reviewer'],'users',{'name':'illegal','password':pw,'role':'admin'})[0],403)

    def test_manual_collaboration(self):
        a=self.client();pw='123456'
        if self.call(a,'bootstrap')[1]['setup']:self.call(a,'setup',{'name':'admin','password':pw})
        else:self.call(a,'login',{'name':'admin','password':pw})
        users={}
        for name,role in [('owner-m','researcher'),('writer-m','researcher'),('outsider-m','researcher'),('review-m','reviewer'),('compliance-m','compliance'),('publisher-m','publisher')]:
            self.assertEqual(self.call(a,'users',{'name':name,'role':role,'password':pw})[0],200)
            users[name]=self.client();self.call(users[name],'login',{'name':name,'password':pw})
        st=self.call(a,'state')[1];ids={u['name']:u['id'] for u in st['users']};owner=users['owner-m'];writer=users['writer-m'];outsider=users['outsider-m']
        cat=next(c for c in st['categories'] if not c['folder']);by=st['authors'][0]
        request={'manual':True,'category_id':cat['id'],'title':'私有共享日报','commodity':'铜','byline_id':by['id'],'report_date':'2026-11-17','summary':'协作测试','collaboration':'shared','collaborators':[ids['writer-m']],'public':False,'layout':'grid'}
        status,result=self.call(owner,'reports',request);self.assertEqual(status,200,result);rid=result['id']
        def report(client=owner):return next(r for r in self.call(client,'state')[1]['reports'] if r['id']==rid)
        r=report();doc=json.loads(r['document']);s1,s2=doc['sections'][:2]
        self.assertNotIn(rid,[r['id'] for r in self.call(outsider,'state')[1]['reports']])
        self.assertEqual(self.call(outsider,'history/'+str(rid))[0],403)
        for path in ['check','generate','refresh','save','transition']:
            self.assertEqual(self.call(outsider,path,{'id':rid})[0],403,path)
        self.assertEqual(self.call(owner,'save',{'id':rid,'version':1,'document':doc,'title':r['title']})[0],400)
        self.assertEqual(self.call(writer,'chapter/save',{'id':rid,'section_id':s1['id'],'revision':1,'blocks':s1['blocks']})[0],403)
        self.assertEqual(self.call(owner,'chapters',{'id':rid,'version':r['version'],'section_id':s2['id'],'action':'edit','title':'协作研究','editors':[ids['writer-m']],'tags':['测试'],'commodity_ids':[]})[0],200)
        r=report();doc=json.loads(r['document']);s1,s2=doc['sections'][:2]
        blocks=[{'id':'manual-owner-block','type':'text','span':12,'title':'','text':'风险提示和数据来源均须核验。'+'研究内容。'*40}]
        self.assertEqual(self.call(owner,'chapter/save',{'id':rid,'section_id':s1['id'],'revision':s1['revision'],'blocks':blocks})[0],200)
        self.assertEqual(self.call(writer,'chapter/save',{'id':rid,'section_id':s2['id'],'revision':s2['revision'],'blocks':[{**blocks[0],'id':'manual-writer-block'}]})[0],200)
        self.assertEqual(self.call(owner,'chapter/save',{'id':rid,'section_id':s1['id'],'revision':s1['revision'],'blocks':blocks})[0],409)
        doc=json.loads(report()['document']);self.assertEqual(doc['sections'][0]['blocks'][0]['text'],blocks[0]['text']);self.assertEqual(doc['sections'][1]['blocks'][0]['text'],blocks[0]['text'])
        self.assertEqual(self.call(owner,'transition',{'id':rid,'action':'提交'})[0],400)
        for s in list(doc['sections']):
            client=writer if ids['writer-m'] in s['editors'] else owner
            if not s['blocks'] or not s['blocks'][0]['text']:
                self.assertEqual(self.call(client,'chapter/save',{'id':rid,'section_id':s['id'],'revision':s['revision'],'blocks':[{**blocks[0],'id':'block-'+s['id']}]})[0],200)
            fresh=next(x for x in json.loads(report()['document'])['sections'] if x['id']==s['id'])
            self.assertEqual(self.call(client,'chapter/submit',{'id':rid,'section_id':s['id'],'revision':fresh['revision']})[0],200)
        s=json.loads(report()['document'])['sections'][1]
        self.assertEqual(self.call(writer,'chapter/save',{'id':rid,'section_id':s['id'],'revision':s['revision'],'blocks':blocks})[0],403)
        self.assertEqual(self.call(writer,'chapter/reopen',{'id':rid,'section_id':s['id'],'revision':s['revision']})[0],200)
        self.assertEqual(self.call(owner,'transition',{'id':rid,'action':'提交'})[0],400)
        s=json.loads(report()['document'])['sections'][1];self.assertEqual(self.call(writer,'chapter/submit',{'id':rid,'section_id':s['id'],'revision':s['revision']})[0],200)
        self.assertEqual(self.call(owner,'transition',{'id':rid,'action':'提交'})[0],200)
        for name,action in [('review-m','通过'),('compliance-m','通过'),('publisher-m','发布')]:self.assertEqual(self.call(users[name],'transition',{'id':rid,'action':action})[0],200)
        self.assertNotIn(rid,[r['id'] for r in self.call(outsider,'state')[1]['reports']])
        self.assertEqual(self.call(outsider,'reports',{**request,'inherit_id':rid})[0],403)
        self.assertEqual(self.call(outsider,'reports',{'category_id':cat['id'],'title':'旧接口继承','commodity':'铜','inherit_id':rid})[0],403)
        self.assertEqual(self.call(users['review-m'],'history/'+str(rid))[0],200)
        tree=self.call(a,'state')[1]['category_tree'];self.assertTrue(any(x['parent_id'] for x in tree))
        folder=self.call(a,'category-tree',{'label':'测试根','folder':True})[1]['id'];child=self.call(a,'category-tree',{'label':'子目录','parent_id':folder,'folder':True})[1]['id'];leaf=self.call(a,'category-tree',{'label':'末级','parent_id':child})[1]['id']
        self.assertEqual(self.call(a,'category-tree',{'label':'第四级','parent_id':leaf})[0],400)
        self.assertEqual(self.call(a,'category-tree',{'id':folder,'label':'测试根','parent_id':child})[0],400)
        self.assertEqual(self.call(a,'category-tree',{'label':'末级','parent_id':child})[0],400)
        self.assertEqual(self.call(writer,'catalog',{'kind':'authors','name':'越权作者'})[0],403)

    def test_resources_free_canvas_and_richtext(self):
        a=self.client();pw='123456'
        if self.call(a,'bootstrap')[1]['setup']:self.call(a,'setup',{'name':'admin','password':pw})
        else:self.call(a,'login',{'name':'admin','password':pw})
        st=self.call(a,'state')[1];cat=next(c for c in st['categories'] if not c['folder']);by=st['authors'][0]
        import base64
        image='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        code,res=self.call(a,'library',{'action':'create','area':'materials','kind':'image','name':'test.png','base64':image});self.assertEqual(code,200,res);aid=res['id']
        self.assertEqual(self.call(a,'library',{'action':'create','area':'materials','kind':'image','name':'unsafe.svg','base64':base64.b64encode(b'<svg onload=alert(1)>').decode()})[0],400)
        with a.open(self.base+'library/file/'+str(aid)) as response:self.assertEqual(response.headers['Content-Type'],'image/png')
        rid=self.call(a,'reports',{'manual':True,'category_id':cat['id'],'title':'自由布局测试','commodity':'铜','byline_id':by['id'],'report_date':'2026-11-17','collaboration':'personal','public':True,'layout':'free'})[1]['id']
        def report():return next(r for r in self.call(a,'state')[1]['reports'] if r['id']==rid)
        r=report();doc=self.ensure_blocks(json.loads(r['document']));b=doc['sections'][0]['blocks'][0];b.update(html='<p onclick="alert(1)"><b>观点</b><script>alert(1)</script><img src=x onerror=alert(1)></p>',x=80,y=100,width=500,height=250)
        doc['sections'][0]['blocks'].append({'id':'image-block','type':'image','span':12,'title':'素材','asset_id':aid,'x':80,'y':400,'width':300,'height':150})
        status,res=self.call(a,'personal-save',{'id':rid,'version':1,'document':doc});self.assertEqual(status,200,res)
        r=report();saved=json.loads(r['document']);b=saved['sections'][0]['blocks'][0];self.assertIn('<b>观点</b>',b['html']);self.assertNotIn('script',b['html']);self.assertNotIn('onclick',b['html']);self.assertEqual(b['x'],80)
        saved['sections'][0]['blocks'][0]['x']=700
        self.assertEqual(self.call(a,'personal-save',{'id':rid,'version':r['version'],'document':saved})[0],400)
        self.assertEqual(self.call(a,'report-view',{'id':rid})[0],200);self.assertEqual(report()['views'],1)
        folder=self.call(a,'library',{'action':'create','area':'cloud','kind':'folder','name':'测试文件夹'})[1]['id']
        did=self.call(a,'library',{'action':'create','area':'cloud','kind':'document','name':'说明','parent_id':folder,'body':'文件夹测试'})[1]['id']
        self.assertEqual(self.call(a,'library',{'action':'delete','item_id':folder})[0],400)
        self.assertEqual(self.call(a,'library',{'action':'delete','item_id':did})[0],200)
        self.assertEqual(self.call(a,'library',{'action':'delete','item_id':folder})[0],200)

    def test_structured_reports(self):
        admin=self.client();pw='123456'
        if self.call(admin,'bootstrap')[1]['setup']:self.call(admin,'setup',{'name':'admin','password':pw})
        else:self.call(admin,'login',{'name':'admin','password':pw})
        clients={};ids={}
        for name,role in [('writer2','researcher'),('review1','reviewer'),('review2','reviewer'),('comp2','compliance'),('pub2','publisher')]:
            self.assertEqual(self.call(admin,'users',{'name':name,'role':role,'password':pw})[0],200)
            clients[name]=self.client();self.call(clients[name],'login',{'name':name,'password':pw})
        st=self.call(admin,'state')[1];ids={u['name']:u['id'] for u in st['users']}
        cat=st['categories'][0];cfg=cat['config'];cfg['workflow'][0].update(mode='all',users=[ids['review1'],ids['review2']])
        new={'name':'结构测试 / 会签日报','config':cfg,'enabled':True}
        status,result=self.call(admin,'categories',new);self.assertEqual(status,200,result);cid=result['id']
        self.assertEqual(self.call(clients['writer2'],'categories',new)[0],403)
        author=clients['writer2'];self.assertEqual(self.call(author,'import',{'csv':'source,indicator,date,value,unit\nWind,铜库存,2026-11-15,10,吨\nWind,铜库存,2026-11-16,12,吨'})[0],200)
        status,result=self.call(author,'reports',{'category_id':cid,'commodity':'铜','title':'结构化日报'});self.assertEqual(status,200,result);rid=result['id']
        def report():return next(r for r in self.call(author,'state')[1]['reports'] if r['id']==rid)
        r=report();doc=json.loads(r['document']);self.assertEqual(len(doc['sections']),len(cfg['sections']))
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],400)
        self.ensure_blocks(doc)
        for s in doc['sections']:s['blocks'][0]['text']='研究事实与推断须分开。'+('供需变化需要持续观察，数据以所列来源日期为准。'*3)
        doc['sections'][0]['blocks'].append({'id':'chart-test','type':'chart','span':6,'title':'库存','source':'Wind','indicator':'铜库存','data':[{'value':999999}]})
        status,result=self.call(author,'save',{'id':rid,'version':r['version'],'title':r['title'],'document':doc});self.assertEqual(status,200,result)
        r=report();saved=json.loads(r['document']);self.assertEqual(saved['sections'][0]['blocks'][-1]['data'][-1]['value'],12)
        self.call(author,'import',{'csv':'source,indicator,date,value,unit\nWind,铜库存,2026-11-17,15,吨'})
        self.assertEqual(self.call(author,'save',{'id':rid,'version':r['version'],'title':r['title'],'document':saved})[0],200)
        r=report();self.assertEqual(len(json.loads(r['document'])['sections'][0]['blocks'][-1]['data']),2)
        self.assertEqual(self.call(author,'refresh',{'id':rid,'version':r['version'],'title':r['title'],'document':json.loads(r['document'])})[0],200)
        r=report();self.assertEqual(len(json.loads(r['document'])['sections'][0]['blocks'][-1]['data']),3)
        modified=json.loads(json.dumps(new));modified.update(id=cid,revision=1);modified['config']['header']='新版分类版头'
        self.assertEqual(self.call(admin,'categories',modified)[0],200)
        self.assertEqual(self.call(admin,'categories',modified)[0],409)
        self.assertNotEqual(json.loads(report()['config_snapshot'])['header'],'新版分类版头')
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],200)
        self.assertEqual(self.call(clients['review1'],'transition',{'id':rid,'action':'通过'})[0],200)
        self.assertEqual(report()['status'],'研究复核')
        self.assertEqual(self.call(clients['review1'],'transition',{'id':rid,'action':'通过'})[0],403)
        self.assertEqual(self.call(clients['review2'],'transition',{'id':rid,'action':'通过'})[0],200)
        self.assertEqual(report()['status'],'合规审核')
        self.assertEqual(self.call(author,'refresh',{'id':rid,'version':report()['version'],'title':r['title'],'document':saved})[0],403)
        self.assertEqual(self.call(clients['comp2'],'transition',{'id':rid,'action':'通过'})[0],200)
        self.assertEqual(self.call(clients['pub2'],'transition',{'id':rid,'action':'发布'})[0],200)
        status,result=self.call(author,'reports',{'category_id':cid,'commodity':'铜','title':'继承日报','inherit_id':rid});self.assertEqual(status,200,result)
        inherited=next(r for r in self.call(author,'state')[1]['reports'] if r['id']==result['id'])
        self.assertEqual(inherited['status'],'草稿');self.assertEqual(inherited['version'],1);self.assertEqual(inherited['inherited_from'],rid)
        self.assertEqual(inherited['config_snapshot'],report()['config_snapshot'])
        self.assertEqual(inherited['document'],report()['document'])
        self.assertEqual(self.call(author,'reports',{'category_id':cid,'commodity':'铜','title':'不应继承草稿','inherit_id':inherited['id']})[0],400)
        seq=json.loads(json.dumps(new));seq['name']='结构测试 / 依次审批';seq['config']['workflow'][0]['mode']='sequential'
        cid2=self.call(admin,'categories',seq)[1]['id'];rid2=self.call(author,'reports',{'category_id':cid2,'commodity':'铜','title':'依次审批测试'})[1]['id']
        r2=next(x for x in self.call(author,'state')[1]['reports'] if x['id']==rid2);d2=json.loads(r2['document'])
        self.ensure_blocks(d2)
        for s in d2['sections']:s['blocks'][0]['text']='风险与来源均需说明。'+'测试研究文字。'*30
        self.assertEqual(self.call(author,'save',{'id':rid2,'version':1,'title':r2['title'],'document':d2})[0],200)
        self.assertEqual(self.call(author,'transition',{'id':rid2,'action':'提交'})[0],200)
        self.assertEqual(self.call(clients['review2'],'transition',{'id':rid2,'action':'通过'})[0],403)
        self.assertEqual(self.call(clients['review1'],'transition',{'id':rid2,'action':'通过'})[0],200)
        self.assertEqual(self.call(clients['review2'],'transition',{'id':rid2,'action':'退回','note':'重写观点'})[0],200)
        self.assertEqual(self.call(author,'transition',{'id':rid2,'action':'提交'})[0],200)
        self.assertEqual(self.call(clients['review2'],'transition',{'id':rid2,'action':'通过'})[0],403)

    def test_iam_flows_schedule_and_print(self):
        a=self.client();pw='123456'
        if self.call(a,'bootstrap')[1]['setup']:self.call(a,'setup',{'name':'admin','password':pw})
        else:self.call(a,'login',{'name':'admin','password':pw})
        dept=self.call(a,'departments',{'name':'研究部'});self.assertEqual(dept[0],200,dept[1]);did=dept[1]['id']
        group=self.call(a,'departments',{'name':'黑色组','parent_id':did});self.assertEqual(group[0],200,group[1]);gid=group[1]['id']
        self.assertEqual(self.call(a,'departments',{'name':'三级组','parent_id':gid})[0],400)
        role=self.call(a,'roles',{'name':'研究助理','base_role':'researcher','menus':['工作台','研报中心','不存在的菜单']})
        self.assertEqual(role[0],200,role[1]);role_id=role[1]['id']
        saved=next(r for r in self.call(a,'state')[1]['roles'] if r['id']==role_id)
        self.assertEqual(saved['menus'],['工作台','研报中心'])
        created=self.call(a,'users',{'name':'iam-user','password':pw,'role_id':role_id,'dept_id':gid,'phone':'13800000000','title':'助理'})
        self.assertEqual(created[0],200,created[1]);uid=created[1]['id']
        self.assertEqual(self.call(self.client(),'login',{'name':'iam-user','password':pw})[0],200)
        self.assertEqual(self.call(a,'departments',{'action':'delete','id':gid})[0],400)
        self.assertEqual(self.call(a,'users',{'action':'toggle','id':uid})[0],200)
        self.assertEqual(self.call(self.client(),'login',{'name':'iam-user','password':pw})[0],401)
        self.assertEqual(self.call(a,'users',{'action':'toggle','id':uid})[0],200)
        self.assertEqual(self.call(a,'users',{'action':'reset','id':uid,'password':'654321'})[0],200)
        u=self.client();self.assertEqual(self.call(u,'login',{'name':'iam-user','password':pw})[0],401)
        self.assertEqual(self.call(u,'login',{'name':'iam-user','password':'654321'})[0],200)
        self.assertEqual(self.call(u,'password',{'old':'wrong','new':'abcdef'})[0],400)
        self.assertEqual(self.call(u,'password',{'old':'654321','new':'abcdef'})[0],200)
        self.assertEqual(self.call(u,'state')[0],401)
        u2=self.client();self.assertEqual(self.call(u2,'login',{'name':'iam-user','password':'abcdef'})[0],200)
        self.assertEqual(self.call(u2,'roles',{'name':'越权角色','base_role':'researcher'})[0],403)

        st=self.call(a,'state')[1];cat=next(c for c in st['categories'] if not c['folder'])
        for name,role_code in [('flow-author','researcher'),('flow-review','reviewer'),('flow-comp','compliance'),('flow-pub','publisher')]:
            self.assertEqual(self.call(a,'users',{'name':name,'password':pw,'role':role_code})[0],200)
        st=self.call(a,'state')[1];ids={x['name']:x['id'] for x in st['users']}
        self.assertEqual(self.call(a,'approval-flows',{'name':'缺合规节点','category_ids':[cat['id']],
            'nodes':[{'label':'研究复核','role':'reviewer','mode':'any','users':[]}]})[0],400)
        nodes=[{'label':'研究复核','role':'reviewer','mode':'any','users':[]},
               {'label':'合规审核','role':'compliance','mode':'all','users':[ids['flow-comp']]}]
        flow=self.call(a,'approval-flows',{'name':'标准审批流','nodes':nodes,'category_ids':[cat['id']]})
        self.assertEqual(flow[0],200,flow[1]);fid=flow[1]['id']
        clients={}
        for name in ['flow-author','flow-review','flow-comp','flow-pub']:
            clients[name]=self.client();self.assertEqual(self.call(clients[name],'login',{'name':name,'password':pw})[0],200)
        author=clients['flow-author']
        rid=self.call(author,'reports',{'category_id':cat['id'],'commodity':cat['config']['commodities'][0],'title':'审批流与定时发布'})[1]['id']
        def report():return next(r for r in self.call(a,'state')[1]['reports'] if r['id']==rid)
        r=report();cfg=json.loads(r['config_snapshot'])
        self.assertEqual([n['label'] for n in cfg['workflow']],['研究复核','合规审核'])
        self.assertEqual(cfg['workflow'][1]['mode'],'all')
        doc=self.ensure_blocks(json.loads(r['document']))
        for s in doc['sections']:
            s['blocks'][0]['text']='风险提示与数据来源均已注明。'+('供需分析以入库数据为准，观点需人工复核。'*4)
        self.assertEqual(self.call(author,'save',{'id':rid,'version':r['version'],'title':r['title'],'document':doc})[0],200)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],200)
        self.assertEqual(self.call(author,'transition',{'id':rid,'action':'提交'})[0],403)
        self.assertEqual(self.call(clients['flow-review'],'transition',{'id':rid,'action':'通过'})[0],200)
        self.assertEqual(self.call(clients['flow-review'],'transition',{'id':rid,'action':'通过'})[0],403)
        self.assertEqual(self.call(clients['flow-comp'],'transition',{'id':rid,'action':'通过'})[0],200)
        self.assertEqual(report()['status'],'待发布')
        publisher=clients['flow-pub']
        self.assertEqual(self.call(author,'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})[0],403)
        self.assertEqual(self.call(publisher,'report-schedule',{'id':rid,'at':'2020-01-01T09:00'})[0],400)
        scheduled=self.call(publisher,'report-schedule',{'id':rid,'at':'2030-01-01T09:00'})
        self.assertEqual(scheduled[0],200,scheduled[1])
        self.assertTrue(report()['scheduled_at'].startswith('2030-01-01 01:00:00'))
        self.assertEqual(self.call(author,'report-schedule',{'id':rid,'at':''})[0],403)
        code,html=self.raw(author,'report-print/'+str(rid))
        self.assertEqual(code,200);self.assertIn(b'<html',html);self.assertIn('审批流与定时发布'.encode(),html)
        self.assertEqual(self.raw(clients['flow-pub'],'report-print/'+str(rid))[0],200)
        self.assertEqual(self.call(a,'approval-flows',{'action':'delete','id':fid})[0],200)

        folder=self.call(a,'library',{'action':'create','area':'materials','kind':'folder','name':'图片目录'})[1]['id']
        sub=self.call(a,'library',{'action':'create','area':'materials','kind':'folder','name':'二级','parent_id':folder})[1]['id']
        img='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='
        aid=self.call(a,'library',{'action':'create','area':'materials','kind':'image','name':'a.png','base64':img,'parent_id':sub})[1]['id']
        self.assertEqual(self.call(a,'library/batch',{'action':'move','ids':[aid],'parent_id':folder})[0],200)
        code,blob=self.raw(a,'library/zip?ids='+str(aid));self.assertEqual(code,200);self.assertEqual(blob[:2],b'PK')
        self.assertEqual(self.call(a,'library/batch',{'action':'delete','ids':[folder]})[0],400)
        self.assertEqual(self.call(a,'library/batch',{'action':'delete','ids':[aid]})[0],200)

if __name__=='__main__':unittest.main(verbosity=2)
