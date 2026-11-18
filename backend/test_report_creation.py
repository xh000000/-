"""Creation dialog API contract: layouts, collaboration, publishing, inheritance and validation.
All reports and accounts are created in Workflow's temporary database.
"""
import json
import unittest
from itertools import product
from concurrent.futures import ThreadPoolExecutor
import threading
from test_workflow import Workflow

class ReportCreation(Workflow):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        helper=cls('test_creation_matrix')
        cls.admin=helper.client()
        helper.assertEqual(helper.call(cls.admin,'setup',{'name':'admin','password':'123456'})[0],200)
        cls.clients={}
        for name, role in [('create-owner','researcher'),('create-writer','researcher'),('create-outsider','researcher'),('create-review','reviewer'),('create-compliance','compliance'),('create-publisher','publisher'),('create-disabled','researcher')]:
            helper.assertEqual(helper.call(cls.admin,'users',{'name':name,'password':'123456','role':role})[0],200)
            client=helper.client();helper.assertEqual(helper.call(client,'login',{'name':name,'password':'123456'})[0],200)
            cls.clients[name]=client
        st=helper.call(cls.admin,'state')[1]
        cls.ids={u['name']:u['id'] for u in st['users']}
        helper.assertEqual(helper.call(cls.admin,'users',{'action':'toggle','id':cls.ids['create-disabled']})[0],200)
        cls.owner=cls.clients['create-owner'];cls.writer=cls.clients['create-writer']
        cls.cat=next(c for c in st['categories'] if not c['folder'])
        cls.by=next(a for a in st['authors'] if a['enabled'] and cls.cat['config']['kind'] in json.loads(a['types']))
        cls.creation_payload={'manual':True,'category_id':cls.cat['id'],'title':'添加研报功能验证','summary':'摘要验证','byline_id':cls.by['id'],'commodity':cls.cat['config']['commodities'][0],'report_date':'2026-11-18','collaboration':'personal','collaborators':[],'layout':'flow','public':True}

    def report(self,rid,client=None):
        return next(r for r in self.call(client or self.owner,'state')[1]['reports'] if r['id']==rid)

    def create(self, **changes):
        data={**self.creation_payload,**changes}
        status,result=self.call(self.owner,'reports',data)
        self.assertEqual(status,200,result)
        return self.report(result['id'])

    def test_creation_matrix(self):
        for layout,collaboration,public in product(['flow','grid','free'],['personal','shared'],[False,True]):
            with self.subTest(layout=layout,collaboration=collaboration,public=public):
                r=self.create(layout=layout,collaboration=collaboration,public=public,collaborators=[self.ids['create-writer']])
                md=json.loads(r['metadata']);doc=json.loads(r['document'])
                self.assertEqual(r['status'],'草稿');self.assertEqual(r['version'],1)
                self.assertEqual(r['title'],self.creation_payload['title']);self.assertEqual(r['commodity'],self.creation_payload['commodity'])
                self.assertEqual(md['summary'],self.creation_payload['summary']);self.assertEqual(md['report_date'],'2026-11-18')
                self.assertEqual(md['byline_id'],self.by['id']);self.assertEqual(md['public'],public)
                self.assertEqual(md['layout'],layout);self.assertEqual(doc['layout'],layout)
                self.assertEqual(md['collaborators'],[self.ids['create-writer']] if collaboration=='shared' else [])
                self.assertEqual(len(doc['sections']),len(self.cat['config']['sections']))
                self.assertTrue(all(sec['editors']==[r['author']] and sec['state']=='未提交' for sec in doc['sections']))
                outsider=self.call(self.clients['create-outsider'],'state')[1]
                self.assertNotIn(r['id'],[x['id'] for x in outsider['reports']])
                if collaboration=='shared':self.assertEqual(self.report(r['id'],self.writer)['id'],r['id'])
                # Initial version must reflect metadata and chosen layout.
                history=self.call(self.owner,'history/'+str(r['id']))[1]
                self.assertEqual(json.loads(history['versions'][0]['metadata'])['layout'],layout)

    def test_parallel_creation_numbers(self):
        barrier=threading.Barrier(2)
        def create(args):
            client,title=args
            barrier.wait()
            return self.call(client,'reports',{**self.creation_payload,'title':title})
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(create,[(self.owner,'并发创建甲'),(self.writer,'并发创建乙')]))
        self.assertTrue(all(status==200 for status,_ in results),results)
        state=self.call(self.admin,'state')[1]
        created=[r for r in state['reports'] if r['id'] in {data['id'] for _,data in results}]
        self.assertEqual(len(created),2)
        self.assertEqual(len({r['issue'] for r in created}),2,'同分类并发创建不得重复分配期号')

    def test_required_and_invalid_fields(self):
        cases=[{'category_id':None},{'category_id':999999},{'byline_id':None},{'byline_id':999999},
               {'title':'   '},{'commodity':''},{'commodity':'不存在的品种'}, {'report_date':''},
               {'report_date':'2026-02-30'},{'layout':'invalid'},{'collaboration':'invalid'},
               {'collaboration':'shared','collaborators':[]},
               {'collaboration':'shared','collaborators':[self.ids['create-owner']]},
               {'collaboration':'shared','collaborators':[self.ids['create-review']]},
               {'collaboration':'shared','collaborators':[self.ids['create-disabled']]},
               {'collaboration':'shared','collaborators':[999999]}]
        for changes in cases:
            with self.subTest(changes=changes):
                before=len(self.call(self.owner,'state')[1]['reports'])
                status,result=self.call(self.owner,'reports',{**self.creation_payload,**changes})
                self.assertEqual(status,400,result)
                self.assertEqual(len(self.call(self.owner,'state')[1]['reports']),before)
        self.assertEqual(self.call(self.clients['create-review'],'reports',self.creation_payload)[0],403)
        self.assertEqual(self.call(self.client(),'reports',self.creation_payload)[0],401)

    def test_category_author_and_commodity_controls(self):
        st=self.call(self.admin,'state')[1]
        folder=next(c for c in st['category_tree'] if c['folder'])
        self.assertEqual(self.call(self.owner,'reports',{**self.creation_payload,'category_id':folder['id']})[0],400)
        # Disable a classification; all required metadata stays valid.
        node=next(c for c in st['category_tree'] if c['id']==self.cat['id'])
        update={'id':node['id'],'label':node['label'],'parent_id':node['parent_id'],'enabled':False}
        self.assertEqual(self.call(self.admin,'category-tree',update)[0],200)
        self.assertEqual(self.call(self.owner,'reports',self.creation_payload)[0],400)
        self.assertEqual(self.call(self.admin,'category-tree',{**update,'enabled':True})[0],200)
        # An enabled child underneath a disabled ancestor cannot be selected either.
        parent=next(c for c in st['category_tree'] if c['id']==node['parent_id'])
        parent_update={'id':parent['id'],'label':parent['label'],'parent_id':parent['parent_id'],'enabled':False}
        self.assertEqual(self.call(self.admin,'category-tree',parent_update)[0],200)
        self.assertEqual(self.call(self.owner,'reports',self.creation_payload)[0],400)
        self.assertEqual(self.call(self.admin,'category-tree',{**parent_update,'enabled':True})[0],200)
        for types,enabled in [([self.cat['config']['kind']],False),(['不适用类型'],True)]:
            status,result=self.call(self.admin,'catalog',{'kind':'authors','name':'无效署名'+str(enabled),'types':types,'enabled':enabled})
            self.assertEqual(status,200,result)
            self.assertEqual(self.call(self.owner,'reports',{**self.creation_payload,'byline_id':result['id']})[0],400)
        other=next(c for c in st['commodities'] if not c['enabled'] or c['name'] not in self.cat['config']['commodities'])
        self.assertEqual(self.call(self.owner,'reports',{**self.creation_payload,'commodity':other['name']})[0],400)
        # Collaborators are deduplicated and the author is not repeated.
        r=self.create(collaboration='shared',collaborators=[self.ids['create-writer'],self.ids['create-owner'],self.ids['create-writer']])
        self.assertEqual(json.loads(r['metadata'])['collaborators'],[self.ids['create-writer']])

    def publish(self,public=True):
        r=self.create(public=public);rid=r['id'];doc=self.ensure_blocks(json.loads(r['document']))
        for section in doc['sections']:
            section['blocks'][0]['text']='风险提示与数据来源均须核验。'+'研究事实和推断分别说明，供需分析需人工复核。'*15
        result=self.call(self.owner,'personal-save',{'id':rid,'version':r['version'],'document':doc})
        self.assertEqual(result[0],200,result)
        for client,action in [(self.owner,'提交'),(self.clients['create-review'],'通过'),(self.clients['create-compliance'],'通过'),(self.clients['create-publisher'],'发布')]:
            result=self.call(client,'transition',{'id':rid,'action':action})
            self.assertEqual(result[0],200,result)
        return self.report(rid)

    def test_inheritance_and_visibility(self):
        source=self.publish(public=True)
        for layout,collaboration in product(['flow','grid','free'],['personal','shared']):
            with self.subTest(layout=layout,collaboration=collaboration):
                r=self.create(inherit_id=source['id'],layout=layout,collaboration=collaboration,collaborators=[self.ids['create-writer']],report_date='2026-11-19',title='继承验证')
                md=json.loads(r['metadata']);doc=json.loads(r['document'])
                self.assertEqual(md['creation'],'inherit');self.assertEqual(md['report_date'],'2026-11-19')
                self.assertEqual(r['inherited_from'],source['id']);self.assertEqual(r['status'],'草稿')
                self.assertEqual(doc['sections'][0]['blocks'][0]['text'],json.loads(source['document'])['sections'][0]['blocks'][0]['text'])
                self.assertTrue(all(sec['revision']==1 and sec['state']=='未提交' for sec in doc['sections']))
                if layout=='free':self.assertTrue(all('width' in b and 'height' in b for sec in doc['sections'] for b in sec['blocks']))
        draft=self.create()
        self.assertEqual(self.call(self.owner,'reports',{**self.creation_payload,'inherit_id':draft['id']})[0],400)
        other_cat=next(c for c in self.call(self.admin,'state')[1]['categories'] if not c['folder'] and c['id']!=self.cat['id'])
        other_by=next(a for a in self.call(self.admin,'state')[1]['authors'] if a['enabled'] and other_cat['config']['kind'] in json.loads(a['types']))
        wrong={**self.creation_payload,'category_id':other_cat['id'],'byline_id':other_by['id'],'commodity':other_cat['config']['commodities'][0],'inherit_id':source['id']}
        self.assertEqual(self.call(self.owner,'reports',wrong)[0],400)
        outsider_reports=self.call(self.clients['create-outsider'],'state')[1]['reports']
        self.assertIn(source['id'],[r['id'] for r in outsider_reports])
        private=self.publish(public=False)
        self.assertNotIn(private['id'],[r['id'] for r in self.call(self.clients['create-outsider'],'state')[1]['reports']])
        self.assertEqual(self.call(self.clients['create-outsider'],'reports',{**self.creation_payload,'inherit_id':private['id']})[0],403)

    def test_all_enabled_categories(self):
        st=self.call(self.admin,'state')[1]
        for node in st['category_tree']:
            if node['folder'] or not node['effective_enabled']:continue
            cat=next(c for c in st['categories'] if c['id']==node['id'])
            by=next(a for a in st['authors'] if a['enabled'] and cat['config']['kind'] in json.loads(a['types']))
            r=self.create(category_id=cat['id'],byline_id=by['id'],commodity=cat['config']['commodities'][0])
            self.assertEqual(r['kind'],cat['config']['kind'])
            self.assertEqual(len(json.loads(r['document'])['sections']),len(cat['config']['sections']))


def load_tests(loader, tests, pattern):
    names=['test_creation_matrix','test_parallel_creation_numbers','test_required_and_invalid_fields','test_category_author_and_commodity_controls','test_inheritance_and_visibility','test_all_enabled_categories']
    return unittest.TestSuite(ReportCreation(name) for name in names)

if __name__=='__main__':unittest.main(verbosity=2)
