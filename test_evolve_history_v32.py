"""EVOLVE 3.2 extended-history safety tests."""
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone
from evolve_history_v32 import fetch

class HistoryTests(unittest.TestCase):
    def test_missing_history_quarantined(self):
        session = Mock()
        session.get.return_value.json.return_value = []
        session.get.return_value.raise_for_status.return_value = None
        _, quality = fetch(session, 'BTC-USD', 86400, 5, datetime(2026, 10, 30, tzinfo=timezone.utc))
        self.assertNotEqual(quality['status'], 'PASS')

    def test_complete_daily_history_passes(self):
        session = Mock()
        anchor = 1793318400
        session.get.return_value.json.return_value = [
            [anchor - i * 86400, 0, 0, 0, 100, 0] for i in range(1, 6)]
        _, quality = fetch(session, 'BTC-USD', 86400, 5, datetime.fromtimestamp(anchor, timezone.utc))
        self.assertEqual(quality['status'], 'PASS')

if __name__ == '__main__':
    unittest.main()
