"""Regression checks for EVOLVE 2.7 research backtester (no orders)."""
import unittest
from unittest.mock import patch

import evolve_backtest_v27 as bt


class BacktestSafetyTests(unittest.TestCase):
    def setUp(self):
        self.prices = [100.0 * (1.0005 ** i) for i in range(400)]

    def test_constant_prices_do_not_generate_profit(self):
        result = bt.simulate([100.0] * 400, 'trend', bt.WARMUP, 400, 'crypto')
        self.assertEqual(result['orders'], 0)
        self.assertEqual(result['return_pct'], 0)
        self.assertEqual(result['diagnostics']['completed_trades'], 0)

    def test_no_future_price_used_in_signal(self):
        baseline = bt.signal('trend', self.prices, 150, bt.THRESHOLDS['crypto'])
        modified = self.prices.copy()
        modified[150:] = [999999.0] * (len(modified) - 150)
        self.assertEqual(baseline, bt.signal('trend', modified, 150, bt.THRESHOLDS['crypto']))

    def test_costs_cannot_improve_return_for_same_trades(self):
        # A deterministic target keeps entry/exit timing unchanged across cost runs.
        with patch.object(bt, 'market_regime', return_value='trending'), patch.object(bt, 'signal', return_value=True):
            gross = bt.simulate(self.prices, 'trend', bt.WARMUP, 400, 'crypto', hold=6, cost_override=0.0)
            net = bt.simulate(self.prices, 'trend', bt.WARMUP, 400, 'crypto', hold=6, cost_override=0.0025)
        self.assertEqual(gross['orders'], net['orders'])
        self.assertLessEqual(net['return_pct'], gross['return_pct'])

    def test_reject_missing_candles(self):
        market = {'market': 'crypto', 'symbol': 'TEST', 'candles': []}
        self.assertEqual(bt.evaluate(market)['status'], 'INVALID_DATA')

    def test_no_strategy_selected_without_trades(self):
        result = bt.simulate([100.0] * 400, 'trend', bt.WARMUP, 400, 'crypto')
        result['diagnostics']['fee_drag_pct_points'] = 0.0
        chosen, reasons = bt.choose({'trend__signal_exit': result})
        self.assertIsNone(chosen)
        self.assertIn('fewer_than_20_completed_trades', reasons['trend__signal_exit'])


if __name__ == '__main__':
    unittest.main()
