import unittest
from evolve_smc_v38 import detect

def bar(o,h,l,c):
    return {'open':o,'high':h,'low':l,'close':c}

class SMCTests(unittest.TestCase):
    def test_requires_future_confirmation(self):
        b=[bar(10,11,9,10),bar(10,13,9,11),bar(11,12,9,11),bar(11,11,9,10),
           bar(10,12,9,11),bar(11,14,10,14)]
        x=detect(b)
        self.assertEqual(x['pivot_highs'][0]['pivot'],1)
        self.assertEqual(x['pivot_highs'][0]['confirmed_at'],3)
        self.assertEqual([e for e in x['events'] if e['type']=='structure_break'][0]['bar'],5)
    def test_fvg_three_candle(self):
        b=[bar(10,11,9,10),bar(10,12,10,11),bar(13,15,12.5,14),bar(14,15,13,14),bar(14,15,13,14)]
        self.assertTrue(any(e['type']=='FVG' and e['direction']=='bullish' and e['bar']==4 for e in detect(b)['events']))
    def test_bad_ohlc_rejected(self):
        with self.assertRaises(ValueError):detect([bar(10,9,8,10)]*5)
    def test_flat_has_no_structure(self):
        x=detect([bar(10,11,9,10)]*30)
        self.assertFalse(x['pivot_highs'])
        self.assertFalse(x['pivot_lows'])
if __name__=='__main__':unittest.main()
