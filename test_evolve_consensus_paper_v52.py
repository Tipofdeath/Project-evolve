import unittest
from datetime import datetime,timezone
from evolve_consensus_paper_v52 import new_state,apply

class PaperSafetyTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,1,15,41,tzinfo=timezone.utc)
        self.bars={sym:{'t':1793546100,'o':100.,'h':102.,'l':99.,'c':101.}
                   for sym in ('BTC-USD','ETH-USD','SOL-USD')}
        self.consensus={'evaluated_at':'2026-11-01T15:40:00+00:00',
          'approved_for_trading':False,'errors':[],
          'results':[{'symbol':sym,'paper_entry_candidate':False,'confirmation_score':0}
                     for sym in self.bars]}
        self.state=new_state()
    def test_new_portfolio_is_empty(self):
        self.assertEqual(self.state['cash'],1.)
        self.assertEqual(self.state['positions'],{})
        self.assertEqual(self.state['pending'],{})
    def test_duplicate_candle_is_noop(self):
        self.state['last_bar']={sym:bar['t'] for sym,bar in self.bars.items()}
        result=apply(self.state,self.bars,self.consensus,self.now)
        self.assertTrue(result['no_new_candle'])
        self.assertEqual(self.state['trades'],[])
        self.assertEqual(self.state['last_bar']['BTC-USD'],self.bars['BTC-USD']['t'])
    def test_missing_candle_fails_closed(self):
        self.state['last_bar']={sym:bar['t']-1800 for sym,bar in self.bars.items()}
        with self.assertRaises(ValueError):
            apply(self.state,self.bars,self.consensus,self.now)
    def test_partial_advance_fails_closed(self):
        self.state['last_bar']={sym:bar['t'] for sym,bar in self.bars.items()}
        self.state['last_bar']['BTC-USD']-=900
        with self.assertRaises(ValueError):
            apply(self.state,self.bars,self.consensus,self.now)

if __name__=='__main__':unittest.main()
