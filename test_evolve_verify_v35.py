import unittest
from evolve_verify_v35 import replay, check

class LedgerTests(unittest.TestCase):
    def test_flat_market_reconciles(self):
        prices=[100.0]*200
        result=replay(prices,100,200)
        self.assertEqual(result['completed_trades'],0)
        self.assertEqual(result['return_pct'],0)
        self.assertTrue(result['ledger_pnl_reconciles'])
    def test_invalid_prices_rejected(self):
        with self.assertRaises(ValueError):
            replay([100.0]*100+[0.0]*100,100,200)
    def test_legacy_matches_on_flat_market(self):
        self.assertTrue(check([100.0]*200,100,200,60,.25)['match'])
if __name__=='__main__':
    unittest.main()
