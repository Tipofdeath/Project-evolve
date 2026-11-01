import unittest
from datetime import datetime,timezone
from evolve_consensus_v50 import evaluate

class ConsensusTests(unittest.TestCase):
    def test_missing_reports_never_qualify(self):
        results=evaluate({}, {}, {}, datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertEqual(len(results),3)
        self.assertFalse(any(x['paper_entry_candidate'] for x in results))
    def test_no_mtf_trigger_never_qualifies(self):
        now=datetime(2026,11,1,15,tzinfo=timezone.utc)
        d={'results':[{'symbol':'BTC-USD','last_completed_day':'2026-10-31',
                         'original_signal':True,'breakout_signal':True}]}
        h={'results':[{'symbol':'BTC-USD','strategy':s,'last_hour_utc':'2026-11-01T14:00:00+00:00',
                         'open_position':True,'signal_active':True} for s in ('original','breakout')]}
        m={'results':[{'symbol':'BTC-USD','last_15m_utc':'2026-11-01T14:45:00+00:00',
                         'entry_signal':False}]}
        self.assertFalse(evaluate(d,h,m,now)[0]['paper_entry_candidate'])

    def test_hourly_signal_confirms_without_open_position(self):
        now=datetime(2026,11,1,15,tzinfo=timezone.utc)
        d={'results':[{'symbol':'BTC-USD','last_completed_day':'2026-10-31',
                       'original_signal':True,'breakout_signal':False}]}
        h={'results':[{'symbol':'BTC-USD','strategy':strategy,
                       'last_hour_utc':'2026-11-01T14:00:00+00:00',
                       'open_position':False,'signal_active':strategy=='original'}
                      for strategy in ('original','breakout')]}
        m={'results':[{'symbol':'BTC-USD','last_15m_utc':'2026-11-01T14:45:00+00:00',
                       'entry_signal':True}]}
        self.assertTrue(evaluate(d,h,m,now)[0]['paper_entry_candidate'])
        del h['results'][0]['signal_active']
        self.assertFalse(evaluate(d,h,m,now)[0]['paper_entry_candidate'])
        h['results'][0]['signal_active']=True
        m['results'][0]['last_15m_utc']='2026-11-01T10:00:00+00:00'
        self.assertFalse(evaluate(d,h,m,now)[0]['paper_entry_candidate'])

if __name__=='__main__':unittest.main()
