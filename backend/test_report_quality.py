"""Deterministic source checks, without model calls or business data."""
from test_environment import prepare
prepare()
import unittest
from report_writer import quality_review

class ReportQuality(unittest.TestCase):
    def evidence(self):
        return {'data':[{'id':'D1','value':100,'source':'测试','unit':'元/吨'}], 'materials':[], 'warnings':['数据时效需核对']}

    def test_unknown_citations_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'不存在的来源'):
            quality_review('价格100元/吨[D999]',self.evidence())

    def test_numeric_claims_and_missing_citations_are_flagged(self):
        notes=quality_review('现货价格99999元/吨',self.evidence())
        self.assertIn('数据时效需核对',notes)
        self.assertTrue(any('没有引用' in x for x in notes))
        self.assertTrue(any('99999' in x for x in notes))
        self.assertFalse(any('未与证据' in x for x in quality_review('价格100元/吨[D1]',self.evidence())))
