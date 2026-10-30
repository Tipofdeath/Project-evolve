"""Research scanner quality gates: deterministic, no network access."""
import unittest
from datetime import datetime, timedelta, timezone

from evolve_market_scan_v23 import clean_and_measure


def candles(count=40, missing=None):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    return [
        {'time': (start + timedelta(hours=i)).isoformat(), 'close': 100.0}
        for i in range(count) if i != missing
    ]


class MarketDataQualityTests(unittest.TestCase):
    def test_continuous_crypto_passes(self):
        rows, report = clean_and_measure(candles(), 'crypto', 'TEST', 40)
        self.assertEqual(len(rows), 40)
        self.assertEqual(report['quality_status'], 'PASS')
        self.assertEqual(report['retained_missing_hours'], 0)

    def test_missing_crypto_hour_is_quarantined(self):
        _, report = clean_and_measure(candles(missing=20), 'crypto', 'TEST', 40)
        self.assertEqual(report['quality_status'], 'BLOCKED_CRYPTO_GAPS')

    def test_short_crypto_history_is_quarantined(self):
        _, report = clean_and_measure(candles(count=35), 'crypto', 'TEST', 40)
        self.assertEqual(report['quality_status'], 'BLOCKED_INCOMPLETE_CRYPTO_HISTORY')

    def test_duplicate_hour_is_deduplicated(self):
        rows = candles()
        rows.append(rows[-1].copy())
        cleaned, report = clean_and_measure(rows, 'crypto', 'TEST', 40)
        self.assertEqual(len(cleaned), 40)
        self.assertEqual(report['duplicate_rows'], 1)
        self.assertEqual(report['quality_status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
