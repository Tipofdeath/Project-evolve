import unittest
from unittest.mock import patch
from evolve_conservative_v37 import simulate

def candle(op,low=None,high=None,close=None):
    return {'open':op,'low':op if low is None else low,
            'high':op if high is None else high,'close':op if close is None else close}

class ConservativeTests(unittest.TestCase):
    def test_no_signal_no_trade(self):
        c=[candle(100) for _ in range(100)]
        self.assertEqual(simulate(c,50,100)['trades'],0)
    def test_entry_day_stop(self):
        c=[candle(100) for _ in range(100)]
        c[50]=candle(100,90,101,95)
        with patch('evolve_conservative_v37.signal',side_effect=lambda p,i:i==50):
            out=simulate(c,50,60)
        self.assertEqual(out['entry_day_stop_exits'],1)
        self.assertTrue(out['ledger_reconciles'])
        self.assertLess(out['return_pct'],0)
    def test_gap_stop(self):
        c=[candle(100) for _ in range(100)]
        c[51]=candle(90,85,91,89)
        with patch('evolve_conservative_v37.signal',side_effect=lambda p,i:i==50):
            out=simulate(c,50,60)
        self.assertEqual(out['gap_stop_exits'],1)
        self.assertTrue(out['ledger_reconciles'])
    def test_hold_exits_at_open_before_low(self):
        c=[candle(100) for _ in range(100)]
        c[51]=candle(101,50,102,60)
        with patch('evolve_conservative_v37.signal',side_effect=lambda p,i:i==50):
            out=simulate(c,50,60,hold=1)
        self.assertEqual(out['ledger'][0]['exit_reason'],'hold_at_open')
    def test_invalid_candle(self):
        c=[candle(100) for _ in range(100)]
        c[51]=candle(100,105,110,100)
        with self.assertRaises(ValueError):simulate(c,50,60)
if __name__=='__main__':unittest.main()
