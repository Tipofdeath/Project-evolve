import unittest
from datetime import datetime,timedelta,timezone
from evolve_smc_context_v39 import context,completed_weekly

def bars(start,count):
    t=datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    return [{'time':(t+timedelta(days=i)).isoformat(),
             'open':100.,'high':102.,'low':98.,'close':100.}
            for i in range(count)]

class SMCContextTests(unittest.TestCase):
    def test_weekly_excludes_incomplete_week(self):
        b=bars('2026-10-05',16)
        w=completed_weekly(b)
        self.assertEqual(len(w),2)
        self.assertEqual(w[-1]['time'],b[13]['time'])
    def test_no_fake_structure_on_flat_data(self):
        c=context(bars('2026-08-03',70))
        self.assertEqual(c['daily_structure'],'unknown')
        self.assertEqual(c['confirmed_range']['price_zone'],'unavailable')
        self.assertEqual(c['order_block_candidate_count'],0)
    def test_bad_ohlc_rejected(self):
        b=bars('2026-10-05',20)
        b[2]['low']=105
        with self.assertRaises(ValueError):context(b)
    def test_incomplete_week_does_not_change_weekly_context(self):
        b=bars('2026-08-03',70)
        first=context(b)
        b.extend(bars('2026-10-12',3))
        b[-1].update({'high':500,'close':400,'open':100,'low':90})
        later=context(b)
        self.assertEqual(first['completed_weekly_candles'],later['completed_weekly_candles'])
        self.assertEqual(first['weekly_structure'],later['weekly_structure'])
if __name__=='__main__':unittest.main()
