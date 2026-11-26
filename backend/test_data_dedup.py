from test_environment import prepare
prepare()
import unittest
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from db import Base, Observation, DataSource
import datasource


class Dedup(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + self.tmp.name + '/test.db', connect_args={'timeout': 15})
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add(DataSource(key='sina', name='新浪财经', enabled=1))
            s.commit()

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def row(self, value=1, unit='点', source='新浪财经'):
        return dict(source=source, indicator='上证指数收盘点位', date='2026-11-18', value=value, unit=unit)

    def apply(self, rows):
        with Session(self.engine) as s:
            result = datasource.apply(s, rows, 'test')
            s.commit()
            return result

    def test_batch_last_wins_and_repeat_skips(self):
        result = self.apply([self.row(1), self.row(2), self.row(3, source='sina')])
        self.assertEqual(result, dict(inserted=1, updated=0, skipped=2, total=3))
        self.assertEqual(self.apply([self.row(3)])['skipped'], 1)
        with Session(self.engine) as s:
            self.assertEqual(s.scalar(select(Observation.value)), 3)
            self.assertEqual(s.scalar(select(func.count()).select_from(Observation)), 1)

    def test_values_and_units_update(self):
        self.apply([self.row()])
        self.assertEqual(self.apply([self.row(2)])['updated'], 1)
        self.assertEqual(self.apply([self.row(2, unit='元')])['updated'], 1)

    def test_different_providers_remain_distinct(self):
        self.assertEqual(self.apply([self.row(), self.row(source='东方财富')])['inserted'], 2)

    def test_concurrent_writes_do_not_duplicate(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.apply([self.row()]), range(8)))
        self.assertEqual(sum(r['inserted'] for r in results), 1)
        with Session(self.engine) as s:
            self.assertEqual(s.scalar(select(func.count()).select_from(Observation)), 1)

    def test_legacy_cleanup_keeps_latest_and_is_idempotent(self):
        # Reproduce an old database without the new unique constraint.
        with self.engine.begin() as c:
            c.execute(text('DROP TABLE observations'))
            c.execute(text('CREATE TABLE observations (id INTEGER PRIMARY KEY, source TEXT, indicator TEXT, date TEXT, value FLOAT, unit TEXT, uploaded_by TEXT, indicator_id INTEGER)'))
        with Session(self.engine) as s:
            s.add_all([Observation(**self.row(1)), Observation(**self.row(2, source='sina'))])
            s.commit()
            self.assertEqual(datasource.migrate_observation_uniqueness(s), 1)
            s.commit()
            self.assertEqual(s.scalar(select(Observation.value)), 2)
            self.assertEqual(s.scalar(select(Observation.source)), '新浪财经')
            self.assertEqual(datasource.migrate_observation_uniqueness(s), 0)
        self.assertEqual(self.apply([self.row(2)])['skipped'], 1)


if __name__ == '__main__':
    unittest.main()
