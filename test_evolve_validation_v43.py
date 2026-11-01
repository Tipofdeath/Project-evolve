import unittest
from datetime import datetime,timedelta,timezone
from evolve_validation_v43 import causal_audit,analyze

def candles(n=180):
    t=datetime(2025,1,1,tzinfo=timezone.utc)
    return [{'time':(t+timedelta(days=i)).isoformat(),'open':100.,
             'high':101.,'low':99.,'close':100.} for i in range(n)]

class ValidationTests(unittest.TestCase):
    def test_prefix_causality(self):
        c=candles()
        self.assertTrue(causal_audit(c,[99,120,179])['passed'])
    def test_chronological_folds(self):
        result=analyze(candles())
        self.assertEqual(len(result['folds']),3)
        self.assertEqual(result['summary']['breakout']['trades'],0)
        self.assertTrue(all(f['variants']['breakout']['normal']['ledger_reconciles'] for f in result['folds']))
    def test_future_candle_does_not_change_prior_indicator(self):
        c=candles();a=causal_audit(c,[100])
        c[-1]['high']=1000.;c[-1]['close']=1000.
        self.assertEqual(a,causal_audit(c,[100]))
if __name__=='__main__':unittest.main()
