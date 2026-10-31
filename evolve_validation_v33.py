"""EVOLVE 3.3 daily historical diagnostics. Research only; no orders."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests
from evolve_history_v32 import fetch
from evolve_risk_v31 import run

HOLDS = (7, 14, 30, 60)
ALLOCATIONS = (.25, .5)
SYMBOLS = ('BTC-USD', 'ETH-USD', 'SOL-USD')

def evaluate(candles, symbol):
    p = [float(x['close']) for x in candles]
    n = len(p)
    bounds = [int(n * x) for x in (.55, .70, .85, 1)]
    cases = []
    for hold in HOLDS:
        for allocation in ALLOCATIONS:
            folds = []
            for j in range(3):
                a, b = bounds[j:j+2]
                training = run(p, 60, a, 'crypto', hold, allocation, .06)
                holdout = run(p, a, b, 'crypto', hold, allocation, .06)
                stressed = run(p, a, b, 'crypto', hold, allocation, .06, 2)
                matched = round(100 * allocation * (p[b-1] / p[a] - 1), 3)
                folds.append({'training': training, 'holdout_diagnostic_only': holdout,
                              'holdout_double_cost': stressed,
                              'allocation_matched_buy_hold_pct': matched,
                              'holdout_excess_pct_points': round(holdout['return_pct'] - matched, 3),
                              'holdout_start': candles[a]['time'],
                              'holdout_end': candles[b-1]['time']})
            cases.append({'hold_days': hold, 'allocation_fraction': allocation,
                          'close_only_stop_pct': 6, 'folds': folds})
    return {'symbol': symbol, 'approved_for_trading': False,
            'status': 'EXPERIMENTAL_ONLY', 'scenarios': cases}

def main():
    output = {'version': '3.3', 'mode': 'research-only; no orders',
              'caveats': ['Daily-close stops cannot cap intraday losses.',
                          'Historical results are not prospective validation.',
                          'Holdout folds are contiguous; scenarios share the same history.',
                          'Matched initial capital is not matched market exposure.',
                          'No live execution, real spreads, funding, taxes or market impact.'],
              'results': [], 'errors': []}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles, quality = fetch(session, symbol, 86400, 1825, datetime.now(timezone.utc))
                result = {'symbol': symbol, 'history_quality': quality,
                          'approved_for_trading': False}
                if quality['status'] == 'PASS':
                    result['research'] = evaluate(candles, symbol)
                else:
                    result['research_status'] = 'QUARANTINED'
                output['results'].append(result)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                output['errors'].append({'symbol': symbol, 'error': str(exc)})
    Path('market_validation_v33.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    return 0 if any(r['history_quality']['status'] == 'PASS' for r in output['results']) else 2

if __name__ == '__main__':
    raise SystemExit(main())
