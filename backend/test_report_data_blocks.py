import json
import unittest
import printview
from test_workflow import Workflow

class ReportDataBlocks(Workflow):
    def test_snapshot_and_render(self):
        admin=self.client();self.call(admin,'setup',{'name':'admin','password':'123456'})
        csv='source,indicator,date,value,unit\n测试图表源,铜收盘价,2026-11-17,10,元/吨\n测试图表源,铜收盘价,2026-11-18,12,元/吨'
        self.assertEqual(self.call(admin,'import',{'csv':csv})[0],200)
        st=self.call(admin,'state')[1];cat=next(c for c in st['categories'] if not c['folder']);by=st['authors'][0]
        code,result=self.call(admin,'reports',{'manual':True,'category_id':cat['id'],'title':'图表和表格显示测试','byline_id':by['id'],'commodity':'铜','report_date':'2026-11-18','collaboration':'personal','layout':'flow'})
        self.assertEqual(code,200,result);rid=result['id']
        def report():return next(r for r in self.call(admin,'state')[1]['reports'] if r['id']==rid)
        r=report();doc=json.loads(r['document'])
        doc['sections'][0]['blocks']=[{'id':kind,'type':kind,'span':12,'title':'铜收盘价','source':'测试图表源','indicator':'铜收盘价','preview':True,'data':[{'date':'2026-11-18','value':99999,'unit':'元/吨'}]} for kind in ['chart','table']]
        self.assertEqual(self.call(admin,'personal-save',{'id':rid,'version':r['version'],'document':doc})[0],200)
        saved=json.loads(report()['document'])
        for block in saved['sections'][0]['blocks']:
            self.assertEqual([point['value'] for point in block['data']],[10,12]);self.assertNotIn('preview',block)
        code,html=self.raw(admin,'report-print/'+str(rid));self.assertEqual(code,200)
        self.assertIn(b'<svg',html);self.assertIn(b'<table class="data">',html);self.assertIn(b'2026-11-18',html)
        self.assertEqual(self.call(admin,'import',{'csv':'source,indicator,date,value,unit\n测试图表源,铜收盘价,2026-11-19,14,元/吨'})[0],200)
        for refresh,expected in [(False,2),(True,3)]:
            r=report();doc=json.loads(r['document'])
            self.assertEqual(self.call(admin,'personal-save',{'id':rid,'version':r['version'],'document':doc,'refresh':refresh})[0],200)
            for block in json.loads(report()['document'])['sections'][0]['blocks']:self.assertEqual(len(block['data']),expected)

class SinglePointPrint(unittest.TestCase):
    def test_single_zero_point_visible(self):
        html=printview._chart({'data':[{'date':'2026-11-18','value':0}]})
        self.assertIn('<circle',html);self.assertIn('cx="290.0"',html);self.assertNotIn('nan',html.lower())


def load_tests(loader,tests,pattern):return unittest.TestSuite([ReportDataBlocks('test_snapshot_and_render'),SinglePointPrint('test_single_zero_point_visible')])
if __name__=='__main__':unittest.main(verbosity=2)
