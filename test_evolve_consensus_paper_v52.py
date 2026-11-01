import unittest
from evolve_consensus_paper_v52 import new_state

class PaperSafetyTests(unittest.TestCase):
    def test_new_portfolio_is_paper_only_and_empty(self):
        state=new_state()
        self.assertEqual(state['cash'],1.)
        self.assertEqual(state['positions'],{})
        self.assertEqual(state['trades'],[])
        self.assertEqual(state['pending'],{})

if __name__=='__main__':unittest.main()
