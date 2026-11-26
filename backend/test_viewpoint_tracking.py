"""Real HTTP workflow against an isolated database; no model or external prices."""
import datetime
import json
import sqlite3
import unittest
from test_report_creation import ReportCreation

class TrackingTests(ReportCreation):
    def publish_fixture(self, text='铜未来5天看多，库存下降支持价格', days_ago=0, status='已发布'):
        r = self.create(commodity='铜')
        day = (datetime.date.today()-datetime.timedelta(days=days_ago)).isoformat()
        with sqlite3.connect(self.tmp.name+'/research.db') as s:
            s.execute('update reports set status=?,published_at=?,body=? where id=?',(status,day+' 10:00:00 UTC',text,r['id']))
            if status=='已发布':
                s.execute('insert into publication_history(report_id,version,document,config,metadata,body,published_at) values(?,?,?,?,?,?,?)',
                          (r['id'],r['version'],r['document'],r['config_snapshot'],r['metadata'],text,day+' 10:00:00 UTC'))
        return r,day

    def candidates(self, rid):
        self.assertEqual(self.call(self.owner,'viewpoints/extract',{'start_date':'2000-01-01','end_date':'2099-12-31'})[0],200)
        code, data=self.call(self.owner,'viewpoints/candidates')
        self.assertEqual(code,200,data)
        return [x for x in data['items'] if x['report_id']==rid]

    def rule(self, days=5,threshold=2):
        code,rules=self.call(self.admin,'viewpoints/rules');self.assertEqual(code,200)
        values=[r for r in rules['items'] if (r['commodity'],r['horizon_days'])!=('铜',days)]
        result=self.call(self.admin,'viewpoints/rules',{'revision':rules['revision'],'items':values+[{'commodity':'铜','horizon_days':days,'threshold':threshold}]})
        self.assertEqual(result[0],200,result)

    def prices(self, rows):
        csv='source,indicator,date,value,unit\n'+'\n'.join(','.join(map(str,x)) for x in rows)
        result=self.call(self.owner,'import',{'csv':csv});self.assertEqual(result[0],200,result)

    def test_publication_hook_and_private_visibility(self):
        r = self.create(commodity='铜', public=False)
        doc = json.loads(r['document'])
        self.ensure_blocks(doc)
        for section in doc['sections']:
            section['blocks'][0]['text'] = '铜未来5天看多，库存下降支持价格。' + '供需研究分析内容与数据核实。' * 12 + '风险提示：需求变化。数据来源：测试指标库。'
        result = self.call(self.owner,'personal-save',{'id':r['id'],'version':r['version'],'document':doc})
        self.assertEqual(result[0],200,result)
        for client,action in [(self.owner,'提交'),(self.clients['create-review'],'通过'),(self.clients['create-compliance'],'通过'),(self.clients['create-publisher'],'发布')]:
            result=self.call(client,'transition',{'id':r['id'],'action':action}); self.assertEqual(result[0],200,result)
        # Candidate created in the publication transaction, without opening the list.
        with sqlite3.connect(self.tmp.name+'/research.db') as s:
            count=s.execute('select count(*) from viewpoint_candidates where report_id=?',(r['id'],)).fetchone()[0]
        self.assertEqual(count,1)
        visible=self.call(self.writer,'viewpoints/candidates')[1]['items']
        self.assertFalse(any(c['report_id']==r['id'] for c in visible))
        c=self.candidates(r['id'])[0]
        self.assertEqual(self.call(self.writer,'viewpoints/confirm',{'id':c['id'],'reviewed':True})[0],403)

    def test_extraction_dedup_and_permissions(self):
        r,_=self.publish_fixture('铜未来5天看多，库存下降。铜未来5天看多，库存下降。铜如果突破则看涨，一周观察。铜短期震荡后可能下跌。铜昨日上涨2%。')
        rows=self.candidates(r['id']);self.assertEqual(len(rows),3)
        self.assertEqual([x['id'] for x in rows],[x['id'] for x in self.candidates(r['id'])])
        c=next(x for x in rows if x['horizon_days']==5)
        self.assertEqual(c['direction'],'看多');self.assertEqual(c['author_id'],self.ids['create-owner'])
        self.assertTrue(any(x['conditional'] for x in rows));self.assertTrue(any(not x['direction'] for x in rows))
        # An ordinary reader must not confirm or ignore the author's candidate.
        self.assertEqual(self.call(self.writer,'viewpoints/ignore',{'id':c['id']})[0],403)
        self.assertEqual(self.call(self.owner,'viewpoints/ignore',{'id':c['id']})[0],200)
        self.assertEqual(next(x for x in self.candidates(r['id']) if x['id']==c['id'])['status'],'已忽略')
        draft,_=self.publish_fixture(status='草稿');self.assertEqual(self.candidates(draft['id']),[])

    def test_confirmation_uses_published_price_and_snapshots_rule(self):
        r,day=self.publish_fixture(days_ago=10)
        self.rule(threshold=2)
        end=(datetime.date.fromisoformat(day)+datetime.timedelta(days=5)).isoformat()
        self.prices([('锁定来源','铜现货价',day,100,'元/吨'),('锁定来源','铜现货价',end,101.5,'元/吨')])
        c=self.candidates(r['id'])[0]
        payload={'id':c['id'],'direction':'看多','horizon_days':5,'reviewed':True,'benchmark_price':99999,'basis':'人工修订的观点说明，保留原文供追溯。'}
        code,data=self.call(self.owner,'viewpoints/confirm',payload);self.assertEqual(code,200,data)
        item=data['items'][0]
        self.assertEqual(item['basis'],'人工修订的观点说明，保留原文供追溯。');self.assertEqual(item['source_excerpt'],c['excerpt'])
        self.assertEqual(item['benchmark_price'],100);self.assertEqual(item['result_price'],101.5)
        self.assertEqual(item['benchmark_source'],item['result_source']);self.assertEqual(item['outcome'],'持平')
        self.assertEqual(item['evaluation_threshold'],2);self.assertEqual(item['publication_id'],c['publication_id'])
        self.rule(threshold=.5)
        item=next(x for x in self.call(self.owner,'viewpoints')[1]['items'] if x['id']==item['id'])
        self.assertEqual(item['evaluation_threshold'],2)
        self.assertEqual(self.call(self.owner,'viewpoints/confirm',payload)[0],409)
        self.assertEqual(self.call(self.owner,'viewpoints/delete',{'id':item['id']})[0],400)

    def test_review_required_missing_prices_and_batch_atomicity(self):
        r,day=self.publish_fixture('铜未来8天看多。铜未来8天如果突破则看涨。', days_ago=60)
        rows=self.candidates(r['id']);c=rows[0]
        self.assertEqual(self.call(self.owner,'viewpoints/confirm',{'id':c['id'],'horizon_days':8,'direction':'看多'})[0],400)
        code,error=self.call(self.owner,'viewpoints/confirm',{'id':c['id'],'horizon_days':8,'direction':'看多','reviewed':True,'condition_confirmed':True})
        self.assertEqual(code,400,error);self.assertEqual(self.candidates(r['id'])[0]['status'],'待确认')
        self.rule(8,1)
        self.prices([('来源','铜现货价',day,100,'元/吨')])
        plain=next(x for x in rows if not x['conditional']);conditional=next(x for x in rows if x['conditional'])
        code,error=self.call(self.owner,'viewpoints/confirm',{'items':[{'id':plain['id'],'reviewed':True},{'id':conditional['id'],'reviewed':True}]})
        self.assertEqual(code,400,error);self.assertTrue(all(x['status']=='待确认' for x in self.candidates(r['id'])))

    def test_rule_access_and_validation(self):
        self.assertEqual(self.call(self.owner,'viewpoints',{'commodity':'铜','direction':'看多','benchmark_price':100})[0],400)
        data=self.call(self.admin,'viewpoints/rules')[1]
        self.assertEqual(self.call(self.owner,'viewpoints/rules',data)[0],403)
        value={'commodity':'铜','horizon_days':10,'threshold':1}
        self.assertEqual(self.call(self.admin,'viewpoints/rules',{'revision':data['revision'],'items':[value,value]})[0],400)
        self.assertEqual(self.call(self.admin,'viewpoints/rules',{'revision':-1,'items':[]})[0],409)


    def test_date_range_extraction_boundaries_and_dedup(self):
        recent,day=self.publish_fixture();older,old_day=self.publish_fixture(days_ago=10)
        query='viewpoints/candidates?start_date='+day+'&end_date='+day
        self.assertNotIn(recent['id'],[x['report_id'] for x in self.call(self.owner,query)[1]['items']])
        body={'start_date':day,'end_date':day}
        out=self.call(self.owner,'viewpoints/extract',body);self.assertEqual(out[0],200,out)
        ids=[x['report_id'] for x in self.call(self.owner,query)[1]['items']]
        self.assertIn(recent['id'],ids);self.assertNotIn(older['id'],ids)
        with sqlite3.connect(self.tmp.name+'/research.db') as conn:
            self.assertEqual(conn.execute('select count(*) from viewpoint_candidates where report_id=?',(older['id'],)).fetchone()[0],0)
        self.assertEqual(self.call(self.owner,'viewpoints/extract',body)[1]['added'],0)
        self.assertEqual(self.call(self.client(),'viewpoints/extract',body)[0],401)
        for invalid in [{},{'start_date':day,'end_date':old_day},{'start_date':'2026-02-30','end_date':day}]:
            self.assertEqual(self.call(self.owner,'viewpoints/extract',invalid)[0],400)
        out=self.call(self.owner,'viewpoints/extract',{'start_date':old_day,'end_date':old_day});self.assertEqual(out[0],200,out)
        self.assertIn(older['id'],[x['report_id'] for x in self.call(self.owner,'viewpoints/candidates?start_date='+old_day+'&end_date='+old_day)[1]['items']])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(TrackingTests(name) for name in ['test_publication_hook_and_private_visibility','test_extraction_dedup_and_permissions','test_confirmation_uses_published_price_and_snapshots_rule','test_review_required_missing_prices_and_batch_atomicity','test_rule_access_and_validation','test_date_range_extraction_boundaries_and_dedup'])

if __name__=='__main__':unittest.main(verbosity=2)
