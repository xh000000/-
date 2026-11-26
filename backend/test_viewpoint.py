"""观点库 / AI 摘要 / 数据巡检的功能测试（不触网，不启动服务器）。

运行方式（从项目根目录）：python backend/test_viewpoint.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
import unittest

os.environ['DATA_DIR'] = tempfile.mkdtemp()          # 必须在导入 db 之前设置
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from db import (Commodity, DataSource, Observation, Report, User, Viewpoint,
                SessionFactory, create_schema)
from sqlalchemy import select


def _seed(s):
    """造基础数据：用户、品种、价格序列。app.init 已种默认品种，所以要幂等。"""
    user = s.execute(select(User).where(User.name == '张研究员')).scalars().first()
    if user:
        return user
    user = User(name='张研究员', role='researcher', salt='', hash='', enabled=1, created_at='')
    s.add(user)
    for name, code in (('螺纹钢', 'RB'), ('铁矿石', 'I')):
        if not s.execute(select(Commodity).where(Commodity.name == name)).scalars().first():
            s.add(Commodity(name=name, parent_id=None, enabled=1, code=code))
    # 现货价序列（优先级高于收盘价）
    today = datetime.date.today()
    if not s.execute(select(Observation).where(Observation.indicator == '螺纹钢现货价')).scalars().first():
        for offset in range(10):
            day = (today - datetime.timedelta(days=offset)).isoformat()
            s.add(Observation(source='钢联', indicator='螺纹钢现货价', date=day, value=4000 + offset * 10,
                              unit='元/吨', uploaded_by='测试'))
        for offset in range(4):
            day = (today - datetime.timedelta(days=offset)).isoformat()
            s.add(Observation(source='同花顺', indicator='螺纹钢收盘价', date=day, value=3900 + offset * 5,
                              unit='元/吨', uploaded_by='测试'))
        # 铁矿石只有滞后数据：最新一条是 10 天前
        s.add(Observation(source='钢联', indicator='铁矿石现货价',
                          date=(today - datetime.timedelta(days=10)).isoformat(),
                          value=900, unit='元/吨', uploaded_by='测试'))
    s.commit()
    return user


def setUpModule():
    """完整初始化（建表 + 默认分类/数据源种子）；类按字母序执行，数据不能放在某个类里。"""
    import app as platform_app
    platform_app.init()
    with SessionFactory() as s:
        _seed(s)


class ViewpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionFactory() as s:
            cls.user_id = s.execute(select(User.id).where(User.name == '张研究员')).scalar_one()

    def test_price_on_prefers_spot_and_as_of_date(self):
        """取价优先级：现货价 > 收盘价，且只取结算日之前的数据。"""
        import viewpoint
        with SessionFactory() as s:
            point = viewpoint.price_on(s, '螺纹钢', datetime.date.today().isoformat())
            self.assertIsNotNone(point)
            self.assertEqual(point['indicator'], '螺纹钢现货价')
            self.assertEqual(point['date'], datetime.date.today().isoformat())
            self.assertEqual(point['value'], 4000)  # offset=0（今天）那行
            # as-of：只要 5 天前的数据，现货序列里那天值 = 4000 + 5*10 = 4050
            past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
            old = viewpoint.price_on(s, '螺纹钢', past)
            self.assertEqual(old['value'], 4050)

    def test_settle_outcomes(self):
        """结算判定：基准价低于现价 → 涨幅 +2.56%，看多正确、看空错误、震荡错误。"""
        import viewpoint
        today = datetime.date.today().isoformat()
        with SessionFactory() as s:
            up = Viewpoint(user_id=self.user_id, user_name='张研究员', commodity='螺纹钢', direction='看多',
                           basis='旺季需求回升', benchmark_price=3900, benchmark_date=today,
                           horizon_days=5, expire_date=today, benchmark_indicator='螺纹钢现货价',
                           status='在途', created_at='now')
            down = Viewpoint(user_id=self.user_id, user_name='张研究员', commodity='螺纹钢', direction='看空',
                             basis='库存累积', benchmark_price=3900, benchmark_date=today,
                             horizon_days=5, expire_date=today, benchmark_indicator='螺纹钢现货价',
                             status='在途', created_at='now')
            flat = Viewpoint(user_id=self.user_id, user_name='张研究员', commodity='螺纹钢', direction='震荡',
                             basis='多空交织', benchmark_price=4000, benchmark_date=today,
                             horizon_days=5, expire_date=today, benchmark_indicator='螺纹钢现货价',
                             status='在途', created_at='now')
            s.add_all([up, down, flat])
            s.commit()
            self.assertTrue(viewpoint.settle(s, up))
            self.assertTrue(viewpoint.settle(s, down))
            self.assertTrue(viewpoint.settle(s, flat))
            # 今日现货 4000：up/down 基准 3900 → +2.56%；flat 基准 4000 → 0%
            self.assertEqual(up.outcome, '正确', up.change_pct)
            self.assertEqual(down.outcome, '错误', down.change_pct)
            self.assertEqual(flat.outcome, '正确', flat.change_pct)
            for vp in (up, down, flat):
                self.assertEqual(vp.status, '已结算')
                self.assertIn('螺纹钢现货价', vp.note)

    def test_settle_no_price_marks_unavailable(self):
        """无价格数据：标「无法结算」而不是编造结果。"""
        import viewpoint
        with SessionFactory() as s:
            vp = Viewpoint(user_id=self.user_id, user_name='张研究员', commodity='不存在品种',
                           direction='看多', basis='测试', benchmark_price=100, benchmark_date='2026-01-01',
                           horizon_days=3, expire_date='2026-01-04', status='在途', created_at='now')
            s.add(vp)
            s.commit()
            self.assertTrue(viewpoint.settle(s, vp))
            self.assertEqual(vp.outcome, '无法结算')
            self.assertIn('价格数据', vp.note)

    def test_outcome_math(self):
        import viewpoint
        self.assertEqual(viewpoint._outcome('看多', 2.5), '正确')
        self.assertEqual(viewpoint._outcome('看多', -2.5), '错误')
        self.assertEqual(viewpoint._outcome('看空', -2.5), '正确')
        self.assertEqual(viewpoint._outcome('看空', 2.5), '错误')
        self.assertEqual(viewpoint._outcome('看多', 0.5), '持平')
        self.assertEqual(viewpoint._outcome('震荡', 0.9), '正确')
        self.assertEqual(viewpoint._outcome('震荡', 1.5), '错误')


class FailureClassifyTests(unittest.TestCase):
    def test_classify(self):
        import datasource
        self.assertEqual(datasource.classify_failure('401 Unauthorized：token 过期'), '凭据/鉴权')
        self.assertEqual(datasource.classify_failure('接口返回 429 too many requests'), '接口限流')
        self.assertEqual(datasource.classify_failure('指标不存在或编码变更'), '参数/指标编码')
        self.assertEqual(datasource.classify_failure('Connection timeout after 30s'), '网络/超时')
        self.assertEqual(datasource.classify_failure('奇怪的错误'), '其他')
        self.assertEqual(datasource.classify_failure(''), '')
        # 每类都有排查步骤
        for label in ('凭据/鉴权', '接口限流', '参数/指标编码', '网络/超时', '其他'):
            self.assertTrue(datasource.TROUBLESHOOTING[label])


class FreshnessTests(unittest.TestCase):
    def test_stale_days_and_stats(self):
        import datasource
        self.assertEqual(datasource.stale_days(datetime.date.today().isoformat()), 0)
        self.assertEqual(datasource.stale_days(''), None)
        self.assertTrue(datasource.is_stale((datetime.date.today() - datetime.timedelta(days=10)).isoformat()))
        self.assertFalse(datasource.is_stale((datetime.date.today() - datetime.timedelta(days=1)).isoformat()))
        with SessionFactory() as s:
            # 数据源补种（stats/health 以 data_sources 表为准）
            datasource.ensure_sources(s)
            s.commit()
            stats = {x['key']: x for x in datasource.stats(s)}
            # 螺纹钢现货（钢联来源不在内置清单里，这里直接校验滞后字段存在且数值合理）
            for item in stats.values():
                self.assertIn('stale_days', item)
                self.assertIn('late_indicators', item)
            health = {x['key']: x for x in datasource.health(s)}
            for item in health.values():
                self.assertIn(item['level'], ('绿', '黄', '红'))
                self.assertIn('success_rate', item)

    def test_catalog_stale_flag(self):
        import datasource
        with SessionFactory() as s:
            rows = datasource.catalog(s, keyword='铁矿石')
            self.assertTrue(rows)
            iron = [x for x in rows if x['indicator'] == '铁矿石现货价'][0]
            self.assertTrue(iron['stale'])
            self.assertGreaterEqual(iron['stale_days'], 9)


class SummaryNormalizeTests(unittest.TestCase):
    def test_extract_json_variants(self):
        import agent.summarize as summarize
        plain = '{"core":"多单持有","logic":"因为库存降所以偏强","data":["库存 512 万吨"]}'
        fenced = '```json\n' + plain + '\n```'
        noisy = '好的，以下是摘要：\n' + plain + '\n以上。'
        for text in (plain, fenced, noisy):
            parsed = summarize._extract_json(text)
            self.assertEqual(parsed['core'], '多单持有')
        with self.assertRaises(ValueError):
            summarize._extract_json('不是 JSON')

    def test_normalize(self):
        import agent.summarize as summarize
        normalized = summarize._normalize({'core': '核心观点', 'logic': '链路', 'data': ['a', 'b', 3, 'c', 'd', 'e']})
        self.assertEqual(normalized['core'], '核心观点')
        self.assertEqual(len(normalized['data']), 4)   # 上限 4 条
        self.assertEqual(normalized['data'][2], '3')   # 数字转字符串
        with self.assertRaises(ValueError):
            summarize._normalize({'logic': '没有核心观点'})

    def test_ai_summary_column_roundtrip(self):
        """reports.ai_summary 列随 to_dict 自动带出（列表接口零改动）。"""
        import manual_engine as manual
        with SessionFactory() as s:
            cats = [c for c in manual.tree(s) if not c['folder']]
            self.assertTrue(cats, '分类迁移应产生末级分类')
            cid = cats[0]['id']
            kind = json.loads(s.get(db.Category, cid).config).get('kind', '')
            author = db.Author(name='测试作者', types=json.dumps([kind]), enabled=1)
            s.add(author)
            s.commit()
            aid = author.id
        with SessionFactory() as s:
            cfg = json.loads(s.get(db.Category, cid).config)
            user = {'id': 1, 'name': '张研究员', 'role': 'researcher'}
            import app as platform
            body, status = manual.handle(
                s, '/api/reports', {'manual': True, 'category_id': cid,
                                    'commodity': cfg['commodities'][0],
                                    'title': '摘要列测试', 'byline_id': aid,
                                    'report_date': '2026-11-26', 'collaboration': 'personal',
                                    'summary': '', 'public': True},
                user, platform.stamp, platform.snapshot, platform.event, platform.checks)
            self.assertEqual(status, 200, body)
            rid = body['id']
            s.commit()
            report = s.get(Report, rid)
            report.ai_summary = json.dumps({'core': 'c', 'logic': 'l', 'data': ['d']}, ensure_ascii=False)
            s.commit()
            d = s.get(Report, rid).to_dict()
            self.assertIn('ai_summary', d)
            self.assertEqual(json.loads(d['ai_summary'])['core'], 'c')


if __name__ == '__main__':
    unittest.main(verbosity=2)
