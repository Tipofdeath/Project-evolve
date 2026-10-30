"""EVOLVE 2.9 research diagnostics. No trading, no selection-rule changes."""
import json
import sys
from collections import Counter
from pathlib import Path

REASONS = (
    'fewer_than_20_completed_trades',
    'training_return_not_above_1pct',
    'drawdown_at_least_8pct',
    'execution_drag_above_10_percentage_points',
    'win_rate_below_30pct',
)

def analyze(report):
    markets = []
    for market in report.get('results', []):
        folds = market.get('folds', [])
        counts = Counter()
        rows = []
        for fold_number, fold in enumerate(folds, 1):
            for key, metrics in fold.get('training_results', {}).items():
                diag = metrics.get('diagnostics', {})
                reasons = fold.get('rejection_reasons', {}).get(key, [])
                counts.update(reasons)
                rows.append({
                    'fold': fold_number, 'configuration': key,
                    'completed_trades': diag.get('completed_trades'),
                    'return_pct': metrics.get('return_pct'),
                    'max_drawdown_pct': metrics.get('max_drawdown_pct'),
                    'execution_drag_pct_points': diag.get('execution_drag_pct_points'),
                    'zero_cost_return_pct': diag.get('zero_cost_return_pct'),
                    'win_rate_pct': diag.get('win_rate_pct'),
                    'rejection_reasons': reasons,
                })
        selected = sum(f.get('selected_strategy') not in (None, 'NO_TRADE') for f in folds)
        markets.append({
            'symbol': market.get('symbol'), 'status': market.get('status'),
            'training_configurations_evaluated': len(rows),
            'folds_with_selection': selected,
            'holdouts_executed': sum(f.get('holdout') is not None for f in folds),
            'rejection_counts': dict(counts),
            'lowest_execution_drag': sorted(
                (r for r in rows if isinstance(r['execution_drag_pct_points'], (int, float))),
                key=lambda r: r['execution_drag_pct_points']
            )[:5],
            'highest_net_training_return': sorted(
                (r for r in rows if isinstance(r['return_pct'], (int, float))),
                key=lambda r: r['return_pct'], reverse=True
            )[:5],
        })
    return {
        'version': '2.9', 'mode': 'research-only; no orders',
        'source_backtest_version': report.get('version'),
        'selection_filters_unchanged': report.get('selection_filters', {}),
        'markets': markets,
        'caveats': [
            'Overlapping expanding training folds are not independent observations.',
            'Training rankings are diagnostic, not evidence of out-of-sample profitability.',
            'No strategy is approved unless the existing backtester selects it.',
            'Zero-cost return is a counterfactual, not an executable result.',
            'Historical hourly close fills, fixed slippage and fees are approximations.',
        ],
    }

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('backtest_report_v28.json')
    report = json.loads(path.read_text(encoding='utf-8'))
    result = analyze(report)
    Path('research_diagnostics_v29.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for m in result['markets']:
        print(f"{m['symbol']}: {m['training_configurations_evaluated']} training evaluations; "
              f"{m['folds_with_selection']} selections; {m['holdouts_executed']} holdouts")
    print('Saved research_diagnostics_v29.json')

if __name__ == '__main__':
    main()
