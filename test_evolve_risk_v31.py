import unittest
from evolve_risk_v31 import evaluate, run

class RiskTests(unittest.TestCase):
    def test_no_approval_on_invalid_data(self):
        x = evaluate({'symbol':'X','market':'crypto','candles':[{'time':'t','close':-1}]})
        self.assertFalse(x['approved_for_trading'])
        self.assertEqual(x['status'],'INVALID_DATA')

    def test_cost_stress(self):
        p = [100+i*.1 for i in range(320)]
        a = run(p,60,300,'crypto',24,.5,.03,0)
        b = run(p,60,300,'crypto',24,.5,.03,1)
        c = run(p,60,300,'crypto',24,.5,.03,2)
        self.assertGreaterEqual(a['return_pct'],b['return_pct'])
        self.assertGreaterEqual(b['return_pct'],c['return_pct'])

if __name__ == '__main__':
    unittest.main()
