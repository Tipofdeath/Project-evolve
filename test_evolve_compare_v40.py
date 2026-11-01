import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from evolve_compare_v40 import features,simulate

def candles(n=100):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    return [{'time':(start+timedelta(days=i)).isoformat(),
             'open':100.,'high':101.,'low':99.,'close':100.} for i in range(n)]

class CompareTests(unittest.TestCase):
    def test_flat_market_no_trades(self):
        c=candles();f=features(c)
        for variant in ('baseline','daily_smc','daily_weekly_smc'):
            x=simulate(c,f,50,100,variant)
            self.assertEqual(x['trades'],0)
            self.assertTrue(x['ledger_reconciles'])
    def test_smc_filters_block_unknown_structure(self):
        c=candles();f=features(c)
        with patch('evolve_compare_v40.signal',return_value=True):
            self.assertGreater(simulate(c,f,50,90,'baseline')['trades'],0)
            self.assertEqual(simulate(c,f,50,90,'daily_smc')['trades'],0)
            self.assertEqual(simulate(c,f,50,90,'daily_weekly_smc')['trades'],0)
    def test_filter_only_uses_previous_close(self):
        c=candles();f=features(c)
        self.assertEqual(f[0]['daily'],'unknown')
        self.assertEqual(f[0]['weekly'],'unknown')
    def test_unknown_variant_rejected(self):
        c=candles()
        with self.assertRaises(ValueError):simulate(c,features(c),50,90,'magic')
if __name__=='__main__':unittest.main()
