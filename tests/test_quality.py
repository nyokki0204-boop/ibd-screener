import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import screener


class ScanQualityTests(unittest.TestCase):
    def test_failed_download_keeps_previous_results(self):
        with tempfile.TemporaryDirectory() as temp:
            old_cwd = Path.cwd()
            try:
                os.chdir(temp)
                Path('data').mkdir()
                Path('data/results.csv').write_text('ticker,RS\nOLD,80\n')
                Path('data/last_updated.txt').write_text('2026-08-31')
                with patch.object(screener, 'get_tickers', return_value=[f'T{i}' for i in range(101)]), \
                     patch.object(screener, 'get_sector_map', return_value=None), \
                     patch.object(screener.yf, 'download', return_value=pd.DataFrame()):
                    with self.assertRaises(RuntimeError):
                        screener.run_scan()
                self.assertIn('OLD,80', Path('data/results.csv').read_text())
                self.assertEqual(Path('data/last_updated.txt').read_text(), '2026-08-31')
                self.assertFalse(json.loads(Path('data/scan_status.json').read_text())['ok'])
            finally:
                os.chdir(old_cwd)

    def test_valid_zero_match_updates_trade_date_and_sector_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            old_cwd = Path.cwd()
            try:
                os.chdir(temp)
                Path('data').mkdir()
                dates = pd.bdate_range(end='2026-09-01', periods=60)
                bars = pd.DataFrame({'Close': [10.0] * 60, 'High': [10.0] * 60,
                                     'Low': [10.0] * 60, 'Volume': [600_000] * 60}, index=dates)
                mapping = pd.DataFrame({'ticker': [f'T{i}' for i in range(101)],
                                        'sector': ['Tech'] * 101}).set_index('ticker')
                with patch.object(screener, 'get_tickers', return_value=[f'T{i}' for i in range(101)]), \
                     patch.object(screener, 'get_sector_map', return_value=mapping), \
                     patch.object(screener.yf, 'download', return_value=bars.copy()):
                    screener.run_scan()
                status = json.loads(Path('data/scan_status.json').read_text())
                self.assertTrue(status['ok'])
                self.assertEqual(status['evaluated'], 101)
                self.assertEqual(Path('data/last_updated.txt').read_text(), '2026-09-01')
                metrics = pd.read_csv('data/sector_metrics.csv').iloc[0]
                self.assertEqual((metrics['eligible'], metrics['passed']), (101, 0))
            finally:
                os.chdir(old_cwd)

    def test_market_date_uses_us_session_for_timezone_aware_bars(self):
        bars = pd.DataFrame({'Close': [10, 11]}, index=pd.DatetimeIndex([
            '2026-09-22 19:00:00+00:00', '2026-09-23 00:00:00+00:00']))
        self.assertEqual(screener.session_date(bars), '2026-09-22')

    def test_sector_pass_rate_includes_zero_pass_and_overwrites_same_session(self):
        with tempfile.TemporaryDirectory() as temp:
            old_cwd = Path.cwd()
            try:
                os.chdir(temp)
                Path('data').mkdir()
                mapping = pd.DataFrame({'ticker': ['A', 'B', 'C'],
                                        'sector': ['Tech', 'Tech', 'Health']}).set_index('ticker')
                data = {'A': None, 'B': None, 'C': None}
                winners = pd.DataFrame({'ticker': ['A'], 'sector': ['Tech']})
                screener.save_sector_metrics(winners, data, mapping, '2026-09-22')
                screener.save_sector_metrics(winners, data, mapping, '2026-09-22')
                metrics = pd.read_csv('data/sector_metrics.csv').set_index('sector')
                self.assertEqual(len(metrics), 2)
                self.assertEqual(int(metrics.loc['Health', 'passed']), 0)
                self.assertEqual(float(metrics.loc['Tech', 'pass_rate']), 50.0)
            finally:
                os.chdir(old_cwd)

    def test_empty_result_and_failed_scan_still_show_history(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temp:
            old_cwd = Path.cwd()
            try:
                os.chdir(temp)
                Path('data').mkdir()
                Path('data/results.csv').write_text('ticker,sector,RS\n')
                Path('data/ticker_history.csv').write_text('date,ticker\n2026-09-22,(該当なし)\n')
                Path('data/last_updated.txt').write_text('2026-09-22')
                Path('data/scan_status.json').write_text('{"ok":false,"reason":"取得率が低い"}')
                app = AppTest.from_file(str(old_cwd / 'app.py'), default_timeout=20).run()
                self.assertFalse(app.exception)
                self.assertEqual([tab.label for tab in app.tabs],
                                 ['銘柄一覧', 'セクター', '推移', '履歴'])
                self.assertTrue(app.error)
            finally:
                os.chdir(old_cwd)


if __name__ == '__main__':
    unittest.main()
