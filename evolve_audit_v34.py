"""EVOLVE 3.4: audit diagnostics, no trading authorization."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests
from evolve_history_v32 import fetch
from evolve_risk_v31 import run

SYMBOLS = ('BTC-USD', 'ETH-USD', 'SOL-USD')
HOLDS = (30, 60)
ALLOCATIONS = (.25, .5)

def classify(prices, index):
    if index < 90:
        return 'unknown'
    change = prices[index - 1] / prices[index - 90] - 1
    return 'bull' if change > .15 else 'bear' if change < -.15 else 'sideways'

def audit(candles, symbol):
    prices = [float(c['close']) for c in candles]
    n = len(prices)
    boundaries = [int(n * f) for f in (.55, .70, .85, 1)]
    windows = []
    for j in range(3):
        start, end = boundaries[j:j+2]
        windows.append({'start': candles[start]['time'], 'end': candles[end-1]['time'],
                        'regime_days': {r: sum(classify(prices, i) == r for i in range(start, end))
                                        for r in ('bull', 'bear', 'sideways')}})
    cases = []
    for hold in HOLDS:
        for allocation in ALLOCATIONS:
            folds = []
            for j in range(3):
                start, end = boundaries[j:j+2]
                base = run(prices, start, end, 'crypto', hold, allocation, .06)
                stress = run(prices, start, end, 'crypto', hold, allocation, .06, 2)
                zero = run(prices, start, end, 'crypto', hold, allocation, .06, 0)
                folds.append({'result': base, 'double_cost': stress,
                              'zero_cost': zero,
                              'cost_drag_pct_points': round(zero['return_pct']-base['return_pct'], 3),
                              'double_cost_delta_pct_points': round(stress['return_pct']-base['return_pct'], 3),
                              'regime_day_counts': windows[j]['regime_days'],
                              'regime_specific_pnl_available': False})
            cases.append({'hold_days': hold, 'allocation_fraction': allocation, 'folds': folds})
    return {'symbol': symbol, 'approved_for_trading': False,
            'holdout_windows': windows, 'scenarios': cases}

def main():
    report = {'version': '3.4', 'mode': 'research-only',
              'warnings': ['This is a diagnostic audit, not an independent execution-engine verification.',
                           'Regime day counts do not establish strategy profitability within regimes.',
                           'Daily-close stop orders are simulated and can exceed stop thresholds.',
                           'Backtest shares data and strategy choices with prior experiments.',
                           'No live trading approval.'],
              'results': [], 'errors': []}
    with requests.Session() as session:
        for symbol in SYMBOLS:
            try:
                candles, quality = fetch(session, symbol, 86400, 1825, datetime.now(timezone.utc))
                item = {'symbol': symbol, 'quality': quality, 'approved_for_trading': False}
                if quality['status'] == 'PASS':
                    item['audit'] = audit(candles, symbol)
                else:
                    item['status'] = 'QUARANTINED'
                report['results'].append(item)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                report['errors'].append({'symbol': symbol, 'error': str(exc)})
    Path('validation_audit_v34.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if any(x['quality']['status'] == 'PASS' for x in report['results']) else 2

if __name__ == '__main__':
    raise SystemExit(main())
