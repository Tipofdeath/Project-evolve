import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from evolve_diagnostics_v41 import rejection_reasons,diagnostic

def candles(n=100):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    return [{'time':(start+timedelta(days=i)).isoformat(),
             'open':100.,'high':101.,'low':99.,'close':100.} for i in range(n)]

class DiagnosticsTests(unittest.TestCase):
    def test_overlapping_reasons(self):
        self.assertEqual(rejection_reasons({'daily':'bearish','weekly':'unknown','discount':False}),
            ['daily_not_bullish','not_discount','weekly_not_bullish'])
    def test_all_accepted(self):
        self.assertEqual(rejection_reasons({'daily':'bullish','weekly':'bullish','discount':True}),[])
    def test_flat_no_entries(self):
        x=diagnostic(candles(),50,100)
        self.assertEqual(x['baseline_entries'],0)
        self.assertEqual(x['rejection_reason_counts_overlapping']['not_discount'],0)
    def test_forced_entries_are_audited(self):
        with patch('evolve_diagnostics_v41.signal',return_value=True),patch('evolve_compare_v40.signal',return_value=True):
            x=diagnostic(candles(),50,90)
        self.assertGreater(x['baseline_entries'],0)
        self.assertEqual(x['daily_smc_accepted_baseline_entries'],0)
        self.assertEqual(x['weekly_smc_accepted_baseline_entries'],0)
if __name__=='__main__':unittest.main()
