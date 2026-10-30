"""Safety tests for EVOLVE 3.0 experiments."""
import unittest
from datetime import datetime, timedelta, timezone
from evolve_experiments_v30 import evaluate, filtered_simulate

class ExperimentsTests(unittest.TestCase):
    def test_no_orders_or_live_approval(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        candles = [{'time': (start + timedelta(hours=i)).isoformat(),
                    'close': 100 + i * .05 + (i % 13) * .03}
                   for i in range(320)]
        result = evaluate({'symbol': 'TEST', 'market': 'crypto', 'candles': candles})
        self.assertEqual(result['status'], 'EXPERIMENTAL_ONLY')
        self.assertFalse(result['approved_for_trading'])
        self.assertEqual(len(result['experiments']), 6)
        self.assertTrue(all(len(x['folds']) == 3 for x in result['experiments']))

    def test_invalid_prices_rejected(self):
        result = evaluate({'symbol': 'TEST', 'market': 'crypto',
                           'candles': [{'time': '2026-01-01', 'close': -1}]})
        self.assertEqual(result['status'], 'INVALID_DATA')

    def test_costs_never_improve_identical_trade_returns(self):
        prices = [100 + i * .1 for i in range(320)]
        gross = filtered_simulate(prices, 60, 300, 'crypto', 12, zero_cost=True)
        net = filtered_simulate(prices, 60, 300, 'crypto', 12)
        self.assertLessEqual(net['return_pct'], gross['return_pct'])

if __name__ == '__main__':
    unittest.main()
