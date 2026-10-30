"""Unit tests for read-only EVOLVE 2.9 diagnostics."""
import unittest
from evolve_research_v29 import analyze

class ResearchDiagnosticsTests(unittest.TestCase):
    def test_counts_and_preserves_rejections(self):
        sample = {'version': '2.8', 'selection_filters': {'min_completed_trades': 20},
                  'results': [{'symbol': 'BTC-USD', 'status': 'EXPERIMENTAL_ONLY',
                  'folds': [{'selected_strategy': 'NO_TRADE', 'holdout': None,
                  'rejection_reasons': {'trend__hold_6h': ['drawdown_at_least_8pct']},
                  'training_results': {'trend__hold_6h': {'return_pct': -2,
                  'max_drawdown_pct': 12, 'diagnostics': {'completed_trades': 21,
                  'execution_drag_pct_points': 13, 'zero_cost_return_pct': 11,
                  'win_rate_pct': 33}}}}]}]}
        result = analyze(sample)
        market = result['markets'][0]
        self.assertEqual(market['folds_with_selection'], 0)
        self.assertEqual(market['holdouts_executed'], 0)
        self.assertEqual(market['rejection_counts']['drawdown_at_least_8pct'], 1)
        self.assertEqual(result['selection_filters_unchanged']['min_completed_trades'], 20)

    def test_empty_results(self):
        self.assertEqual(analyze({'results': []})['markets'], [])

if __name__ == '__main__':
    unittest.main()
