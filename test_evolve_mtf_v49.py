import unittest
from evolve_mtf_v49 import hourly,decide,new,advance

class MultiTimeframeTests(unittest.TestCase):
    def test_incomplete_hour_is_excluded(self):
        bars=[{'t':i*900,'o':100.,'h':101.,'l':99.,'c':100.} for i in range(9)]
        self.assertEqual(len(hourly(bars)),2)
    def test_first_run_has_no_backfilled_trades(self):
        p=new(3600)
        self.assertEqual(p['trades'],[])
        self.assertEqual(p['qty'],0.)
    def test_no_future_bar_used_for_entry(self):
        p=new(0)
        b={'t':900,'o':100.,'h':101.,'l':99.,'c':100.}
        advance(p,b,(False,1.),'no_trigger')
        self.assertEqual(p['qty'],0.)
        self.assertEqual(p['last_time'],900)
    def test_warmup_no_signal(self):
        self.assertEqual(decide([{'t':i*900,'o':100.,'h':101.,'l':99.,'c':100.} for i in range(5)])[0],False)

if __name__=='__main__':unittest.main()
