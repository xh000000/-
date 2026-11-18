"""Public providers: preserve provenance, units and errors without real network."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import feeds


class PublicFeeds(unittest.TestCase):
    def config(self, kind):
        return SimpleNamespace(kind=kind, source='eastmoney' if kind.startswith('eastmoney') else 'sina',
                               base_url=feeds.PUBLIC_URLS[kind])

    def collect(self, kind, metric, payload):
        with patch.object(feeds, '_http', return_value=json.dumps(payload)):
            return feeds._rows_public(self.config(kind), '上证指数', '', metric,
                                      '2026-11-01', '2026-11-30', 10, {})

    def test_provider_volume_units_agree(self):
        em = self.collect('eastmoney_index', 'volume', {'data': {'klines': ['2026-11-18,1,2,3,1,123']}})
        sina = self.collect('sina_index', 'volume', [{'day': '2026-11-18', 'volume': '12300'}])
        self.assertEqual(em[0]['value'], sina[0]['value'])
        self.assertEqual(em[0]['unit'], '股')
        self.assertEqual(em[0]['source'], 'eastmoney')
        self.assertEqual(sina[0]['source'], 'sina')

    def test_snapshot_uses_provider_date_and_precision(self):
        rows = self.collect('eastmoney_snapshot', 'index_last',
                            {'data': {'f43': 358783, 'f59': 2, 'f86': 1794989519}})
        self.assertEqual(rows[0]['value'], 3587.83)
        self.assertEqual(rows[0]['date'], '2026-11-18')
        self.assertIn('最新点位', rows[0]['indicator'])

    def test_snapshot_cannot_impersonate_close(self):
        with self.assertRaises(feeds.FeedError):
            self.collect('eastmoney_snapshot', 'index_close', {})

    def test_bad_response_and_unavailable_metrics_fail(self):
        with self.assertRaises(feeds.FeedError):
            self.collect('sina_index', 'volume', {'error': 'upstream unavailable'})
        with self.assertRaises(feeds.FeedError):
            self.collect('eastmoney_index', 'inventory', {})

    def test_invalid_values_and_out_of_window_rows_are_excluded(self):
        rows = self.collect('sina_index', 'index_close', [
            {'day': '2026-11-18', 'close': 'NaN'},
            {'day': '2026-10-01', 'close': '20'},
            {'day': '2026-11-18', 'close': '35.8'}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['value'], 35.8)


if __name__ == '__main__':
    unittest.main()
