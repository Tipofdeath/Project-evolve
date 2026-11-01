"""Regression checks: independent, prospective v5.5 shadow portfolios."""
import unittest
from evolve_shadow_performance_v55 import initial,process,AUTO_MARKETS

def history(t):
    return {s:[{"t":t,"o":100.,"h":101.,"l":99.,"c":100.}] for s in AUTO_MARKETS}
def signals(at,base=False,structure=False):
    return {"at":at,"baseline":{s:base for s in AUTO_MARKETS},
        "structure":{s:structure for s in AUTO_MARKETS}}

class ShadowTests(unittest.TestCase):
    def test_initialization_has_no_trades(self):
        s=initial()
        self.assertTrue(process(s,history(9000),signals(9900))["initialized"])
        self.assertEqual(s["strategies"]["baseline"]["trades"],[])
    def test_duplicate_is_noop(self):
        s=initial();process(s,history(9000),signals(9900))
        self.assertTrue(process(s,history(9000),signals(9900))["no_new_candle"])
    def test_flat_skip_is_recorded(self):
        s=initial();process(s,history(9000),signals(9900))
        r=process(s,history(11700),signals(12000))
        self.assertTrue(r["skipped_unobserved_intervals"])
        self.assertEqual(s["strategies"]["baseline"]["trades"],[])
    def test_missing_with_pending_fails_closed(self):
        s=initial();process(s,history(9000),signals(9900,True))
        with self.assertRaises(ValueError):
            process(s,history(11700),signals(12000))
    def test_no_entry_before_signal_timestamp(self):
        s=initial();process(s,history(9000),signals(9500,True,False))
        process(s,history(9900),signals(10300))
        self.assertFalse(s["strategies"]["baseline"]["positions"])
        process(s,history(10800),signals(11100))
        self.assertTrue(s["strategies"]["baseline"]["positions"])
        self.assertFalse(s["strategies"]["structure"]["positions"])
    def test_missing_with_position_fails_closed(self):
        s=initial();process(s,history(9000),signals(9500,True))
        process(s,history(9900),signals(10300))
        process(s,history(10800),signals(11100))
        with self.assertRaises(ValueError):
            process(s,history(13500),signals(13800))

if __name__=="__main__":unittest.main()
