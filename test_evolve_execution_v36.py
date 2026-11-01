import unittest
from evolve_execution_v36 import simulate,signal

def candle(op,hi,lo,cl):
    return {'open':op,'high':hi,'low':lo,'close':cl}

class ExecutionTests(unittest.TestCase):
    def test_flat_market_no_trades(self):
        data=[candle(100,101,99,100) for _ in range(200)]
        result=simulate(data,100,200)
        self.assertEqual(result['trades'],0)
        self.assertEqual(result['return_pct'],0)
    def test_bad_ohlc_rejected(self):
        data=[candle(100,99,101,100) for _ in range(200)]
        with self.assertRaises(ValueError):simulate(data,100,200)
    def test_signal_uses_only_prior_closes(self):
        prices=[100.]*100
        self.assertEqual(signal(prices,50),signal(prices[:50]+[999.]*50,50))
if __name__=='__main__':unittest.main()
