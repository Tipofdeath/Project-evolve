import unittest
from datetime import datetime,timedelta,timezone
from evolve_breakout_v42 import indicators,simulate

def candles(n=120):
    start=datetime(2025,1,1,tzinfo=timezone.utc)
    return [{'time':(start+timedelta(days=i)).isoformat(),'open':100.,'high':101.,'low':99.,'close':100.} for i in range(n)]

class BreakoutTests(unittest.TestCase):
    def test_flat_no_trades(self):
        c=candles();x=simulate(c,indicators(c),70,120)
        self.assertEqual(x['trades'],0)
        self.assertTrue(x['ledger_reconciles'])
    def test_prior_close_breakout_excludes_signal_bar(self):
        c=candles();c[69]={'time':c[69]['time'],'open':100.,'high':111.,'low':99.,'close':110.}
        states=indicators(c)
        self.assertEqual(states[70]['upper'],101.)
        self.assertEqual(states[70]['prior_close'],110.)
        self.assertGreater(simulate(c,states,70,120)['trades'],0)
    def test_no_future_data_leak(self):
        c=candles();a=indicators(c)
        c[-1]['high']=999.;c[-1]['close']=999.
        b=indicators(c)
        self.assertEqual(a[-1],b[-1])
    def test_invalid_window(self):
        c=candles()
        with self.assertRaises(ValueError):simulate(c,indicators(c),20,120)
if __name__=='__main__':unittest.main()
